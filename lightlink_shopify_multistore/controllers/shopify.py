import base64
import hashlib
import json
import logging

from psycopg2 import IntegrityError

from odoo import fields, http
from odoo.exceptions import ValidationError
from odoo.http import request

from ..models.shopify_api import (
    ShopifyAPIError,
    exchange_oauth_code,
    normalize_shop_domain,
    verify_oauth_hmac,
    verify_webhook_hmac,
)


_logger = logging.getLogger(__name__)


class LightLinkShopifyController(http.Controller):
    @http.route(
        "/lightlink/shopify/oauth/callback", type="http", auth="user", methods=["GET"], csrf=False
    )
    def oauth_callback(self, **params):
        oauth_state = request.env["ll.shopify.oauth.state"].sudo().search(
            [("token", "=", params.get("state")), ("used", "=", False)], limit=1
        )
        if not oauth_state or oauth_state.expires_at < fields.Datetime.now():
            return request.make_response("OAuth 状态已失效，请回到 Odoo 重新连接。", status=400)
        store = oauth_state.store_id.sudo()
        if oauth_state.user_id != request.env.user:
            return request.make_response("OAuth 用户与发起人不一致。", status=403)
        try:
            shop = normalize_shop_domain(params.get("shop"))
        except ValueError:
            return request.make_response("Shopify 店铺域名不合法。", status=400)
        if shop != store.shop_domain or not verify_oauth_hmac(store.client_secret, params):
            return request.make_response("OAuth 回调校验失败。", status=400)
        try:
            token, scopes = exchange_oauth_code(
                store.shop_domain,
                store.api_version,
                store.client_id,
                store.client_secret,
                params.get("code"),
            )
        except ShopifyAPIError as error:
            return request.make_response(f"OAuth 连接失败：{error}", status=502)
        store.write(
            {
                "access_token": token,
                "granted_scopes": scopes,
                "state": "connected",
                "last_connection_at": fields.Datetime.now(),
                "last_error": False,
            }
        )
        oauth_state.used = True
        missing_scopes = store._missing_granted_scopes()
        if missing_scopes:
            message = "Shopify 授权缺少权限：%s，请更新应用权限后重新连接。" % ", ".join(
                missing_scopes
            )
            store.write({"state": "error", "last_error": message})
            return request.make_response(message, status=400)
        job_model = request.env["ll.shopify.job"].sudo()
        connection_marker = hashlib.sha256(token.encode()).hexdigest()[:16]
        job_model.enqueue(store, "fetch_locations", store, payload={"connection": connection_marker})
        job_model.enqueue(store, "register_webhooks", store, payload={"connection": connection_marker})
        action_id = request.env.ref("lightlink_shopify_multistore.action_shopify_store").id
        return request.redirect(f"/odoo/action-{action_id}/{store.id}")

    @http.route(
        "/lightlink/shopify/webhook/<string:route_token>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def webhook(self, route_token, **kwargs):
        store = request.env["ll.shopify.store"].sudo().search(
            [("webhook_secret", "=", route_token), ("active", "=", True)], limit=1
        )
        if not store:
            return request.make_response("not found", status=404)
        raw = request.httprequest.get_data(cache=False)
        signature = request.httprequest.headers.get("X-Shopify-Hmac-Sha256")
        if not verify_webhook_hmac(store.client_secret, raw, signature):
            return request.make_response("invalid signature", status=401)
        shop_domain = request.httprequest.headers.get("X-Shopify-Shop-Domain", "")
        try:
            if normalize_shop_domain(shop_domain) != store.shop_domain:
                return request.make_response("shop mismatch", status=403)
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return request.make_response("invalid payload", status=400)
        webhook_id = request.httprequest.headers.get("X-Shopify-Webhook-Id")
        topic = request.httprequest.headers.get("X-Shopify-Topic", "unknown")
        if not webhook_id:
            return request.make_response("missing webhook id", status=400)
        event_model = request.env["ll.shopify.webhook.event"].sudo()
        existing = event_model.search(
            [("store_id", "=", store.id), ("webhook_id", "=", webhook_id)], limit=1
        )
        if existing:
            return request.make_response("duplicate", status=200)
        try:
            with request.env.cr.savepoint():
                event = event_model.create(
                    {
                        "store_id": store.id,
                        "webhook_id": webhook_id,
                        "topic": topic,
                        "shop_domain": shop_domain,
                        "payload_json": payload,
                    }
                )
        except IntegrityError:
            return request.make_response("duplicate", status=200)
        if topic == "app/uninstalled":
            store.write({"state": "paused", "access_token": False, "last_error": "Shopify 应用已卸载。"})
            event.state = "done"
        elif topic in {"orders/create", "orders/updated"}:
            request.env["ll.shopify.job"].sudo().enqueue(
                store, "import_orders", store, payload={"webhook_id": webhook_id}
            )
            event.state = "queued"
        else:
            event.state = "done"
        return request.make_response("ok", status=200)

    @http.route(
        "/lightlink/shopify/inquiry/<string:token>",
        type="http",
        auth="public",
        methods=["OPTIONS", "POST"],
        csrf=False,
        save_session=False,
    )
    def inquiry(self, token, **kwargs):
        store = request.env["ll.shopify.store"].sudo().search(
            [("public_inquiry_token", "=", token), ("active", "=", True)], limit=1
        )
        if not store:
            return request.make_json_response({"ok": False, "error": "not_found"}, status=404)
        origin = request.httprequest.headers.get("Origin", "").rstrip("/")
        allowed = {
            line.strip().rstrip("/")
            for line in (store.allowed_origins or "").splitlines()
            if line.strip()
        }
        headers = {
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
        }
        if origin not in allowed:
            return request.make_json_response(
                {"ok": False, "error": "origin_not_allowed"}, headers=headers, status=403
            )
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=headers, status=204)
        try:
            values = request.httprequest.get_json(silent=False)
        except Exception:
            return request.make_json_response(
                {"ok": False, "error": "invalid_json"}, headers=headers, status=400
            )
        if values.get("website"):
            return request.make_json_response({"ok": True}, headers=headers)
        remote_ip = request.httprequest.remote_addr or ""
        ip_hash = hashlib.sha256(f"{store.id}:{remote_ip}".encode()).hexdigest()
        recent = request.env["ll.shopify.inquiry"].sudo().search_count(
            [
                ("store_id", "=", store.id),
                ("ip_hash", "=", ip_hash),
                ("create_date", ">=", fields.Datetime.subtract(fields.Datetime.now(), hours=1)),
            ]
        )
        if recent >= 5:
            return request.make_json_response(
                {"ok": False, "error": "rate_limited"}, headers=headers, status=429
            )
        try:
            inquiry = request.env["ll.shopify.inquiry"].sudo().create_from_public(
                store,
                values,
                remote_ip=remote_ip,
                user_agent=request.httprequest.headers.get("User-Agent", ""),
            )
        except ValidationError as error:
            return request.make_json_response(
                {"ok": False, "error": str(error)}, headers=headers, status=400
            )
        return request.make_json_response(
            {"ok": True, "reference": f"LL-{inquiry.id:06d}"}, headers=headers, status=201
        )

    @http.route(
        "/lightlink/shopify/media/<string:token>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def media(self, token, **kwargs):
        image = request.env["ll.shopify.channel.image"].sudo().search(
            [
                ("public_token", "=", token),
                ("channel_product_id.active", "=", True),
                ("channel_product_id.store_id.active", "=", True),
            ],
            limit=1,
        )
        if not image or not image.image:
            return request.make_response("not found", status=404)
        return request.make_response(
            base64.b64decode(image.image),
            headers=[
                ("Content-Type", image.mimetype or "image/jpeg"),
                ("Cache-Control", "public, max-age=86400"),
                ("X-Content-Type-Options", "nosniff"),
            ],
        )

    @http.route(
        "/lightlink/shopify/collection-media/<string:token>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def collection_media(self, token, **kwargs):
        collection = request.env["ll.shopify.collection"].sudo().search(
            [
                ("image_public_token", "=", token),
                ("active", "=", True),
                ("store_id.active", "=", True),
            ],
            limit=1,
        )
        if not collection or not collection.image:
            return request.make_response("not found", status=404)
        return request.make_response(
            base64.b64decode(collection.image),
            headers=[
                ("Content-Type", "image/jpeg"),
                ("Cache-Control", "public, max-age=86400"),
                ("X-Content-Type-Options", "nosniff"),
            ],
        )
