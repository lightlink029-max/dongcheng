import base64
import json
import logging
import re
from io import BytesIO

from PIL import Image

from odoo import fields, http
from odoo.http import request


_logger = logging.getLogger(__name__)


class ProductIntelligenceIngestController(http.Controller):

    @staticmethod
    def _authorized_source(source_id):
        source = request.env["product.intelligence.source"].sudo().browse(source_id).exists()
        authorization = request.httprequest.headers.get("Authorization", "")
        token = request.httprequest.headers.get("X-PIH-Token", "")
        if authorization.startswith("Bearer "):
            token = authorization[7:].strip()
        return source if source and source._check_webhook_token(token) else False

    @http.route(
        "/product-intelligence/v1/ingest/<int:source_id>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def ingest(self, source_id, **kwargs):
        source = self._authorized_source(source_id)
        if not source:
            return request.make_json_response({"ok": False, "error": "unauthorized"}, status=401)
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            items = payload if isinstance(payload, list) else payload.get("items", [])
            if not isinstance(items, list) or len(items) > 1000:
                return request.make_json_response(
                    {"ok": False, "error": "items must be a list with at most 1000 entries"},
                    status=400,
                )
            result = source.ingest_candidates(items)
            return request.make_json_response({"ok": True, **result})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return request.make_json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception:
            _logger.exception("Product intelligence push failed for source %s", source_id)
            return request.make_json_response({"ok": False, "error": "internal_error"}, status=500)

    @http.route(
        "/product-intelligence/v1/detail-queue/<int:source_id>", type="http", auth="public",
        methods=["GET"], csrf=False, save_session=False,
    )
    def detail_queue(self, source_id, **kwargs):
        source = self._authorized_source(source_id)
        if not source:
            return request.make_json_response({"ok": False, "error": "unauthorized"}, status=401)
        candidates = request.env["product.intelligence.candidate"].sudo().search([
            ("source_id", "=", source.id), ("detail_state", "=", "queued"),
            ("external_url", "!=", False),
        ], order="write_date asc", limit=20)
        return request.make_json_response({"ok": True, "items": [
            {"product_id": item.external_id, "product_title": item.name, "product_url": item.external_url}
            for item in candidates
        ]})

    @http.route(
        "/product-intelligence/v1/detail-result/<int:source_id>", type="http", auth="public",
        methods=["POST"], csrf=False, save_session=False,
    )
    def detail_result(self, source_id, **kwargs):
        source = self._authorized_source(source_id)
        if not source:
            return request.make_json_response({"ok": False, "error": "unauthorized"}, status=401)
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            product_id = str(payload.get("product_id") or "")[:128]
            candidate = request.env["product.intelligence.candidate"].sudo().search([
                ("source_id", "=", source.id), ("external_id", "=", product_id),
            ], limit=1)
            if not candidate:
                return request.make_json_response({"ok": False, "error": "candidate_not_found"}, status=404)
            if payload.get("error"):
                candidate.write({"detail_state": "failed", "detail_error": str(payload["error"])[:512]})
            else:
                media_commands = []
                seen_urls = set()
                for media_type, entries, limit in (
                    ("image", payload.get("photos") or [], 30),
                    ("video", payload.get("videos") or [], 8),
                ):
                    if not isinstance(entries, list):
                        continue
                    for sequence, entry in enumerate(entries[:limit], start=1):
                        url = entry.get("url") if isinstance(entry, dict) else entry
                        name = entry.get("name") if isinstance(entry, dict) else False
                        url = str(url or "").strip()[:2048]
                        if not url.startswith(("http://", "https://")) or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        media_commands.append((0, 0, {
                            "media_type": media_type,
                            "source_url": url,
                            "name": str(name or "")[:256],
                            "sequence": sequence if media_type == "image" else 100 + sequence,
                        }))
                candidate.write({
                    "category": str(payload.get("category") or candidate.category or "")[:512],
                    "core_industry_attributes": str(payload.get("core_industry_attributes") or "")[:10000],
                    "important_attributes": str(payload.get("important_attributes") or "")[:10000],
                    "packaging_information": str(payload.get("packaging_information") or "")[:10000],
                    "shipping_information": str(payload.get("shipping_information") or "")[:10000],
                    "detail_state": "done", "detail_error": False,
                    "detail_updated_at": fields.Datetime.now(),
                    **({"media_ids": [(5, 0, 0), *media_commands]} if media_commands else {}),
                })
            return request.make_json_response({"ok": True})
        except Exception:
            _logger.exception("Product detail update failed for source %s", source_id)
            return request.make_json_response({"ok": False, "error": "internal_error"}, status=500)

    @http.route(
        "/product-intelligence/v1/sourcing-result/<int:source_id>", type="http",
        auth="public", methods=["POST"], csrf=False, save_session=False,
    )
    def sourcing_result(self, source_id, **kwargs):
        source = self._authorized_source(source_id)
        if not source:
            return request.make_json_response({"ok": False, "error": "unauthorized"}, status=401)
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            candidate_id = int(payload.get("candidate_id") or 0)
            items = payload.get("items") or []
            source_insights = payload.get("source_insights") or []
            if (
                not candidate_id or not isinstance(items, list) or len(items) > 200
                or not isinstance(source_insights, list) or len(source_insights) > 50
            ):
                return request.make_json_response({"ok": False, "error": "invalid_payload"}, status=400)
            candidate = request.env["product.intelligence.candidate"].sudo().browse(candidate_id).exists()
            if not candidate or candidate.company_id != source.company_id:
                return request.make_json_response({"ok": False, "error": "candidate_not_found"}, status=404)
            Offer = request.env["product.intelligence.sourcing.offer"].sudo()
            Insight = request.env["product.intelligence.source.insight"].sudo()
            ai_snapshot = Offer._prepare_ai_opportunity_snapshot(candidate)
            created = updated = skipped = 0
            for item in items:
                if not isinstance(item, dict):
                    skipped += 1
                    continue
                external_id = str(item.get("product_id") or "")[:128]
                name = str(item.get("product_title") or "").strip()[:512]
                platform = str(item.get("source_platform") or "1688").strip().lower()
                if platform not in ("1688", "yiwugo"):
                    skipped += 1
                    continue
                if not external_id or not name:
                    skipped += 1
                    continue
                image_url = str(item.get("main_image") or "")[:2048]
                raw_product_url = str(item.get("product_url") or "")[:2048]
                product_url = (
                    Offer._validated_1688_product_url(external_id, raw_product_url)
                    if platform == "1688" else raw_product_url
                )
                values = {
                    "candidate_id": candidate.id,
                    "platform": platform,
                    "external_id": external_id,
                    "name": name,
                    "product_url": product_url,
                    "image_url": image_url,
                    "supplier_name": str(item.get("supplier_name") or "")[:512],
                    "merchant_features": str(item.get("merchant_features") or "")[:256],
                    "merchant_join_time": str(item.get("merchant_join_time") or "")[:128],
                    "supplier_url": str(item.get("supplier_url") or "")[:2048],
                    "contact_name": str(item.get("contact_name") or "")[:256],
                    "contact_phone": str(item.get("contact_phone") or "")[:128],
                    "contact_landline": str(item.get("contact_landline") or "")[:128],
                    "contact_email": str(item.get("contact_email") or "")[:256],
                    "contact_qq": str(item.get("contact_qq") or "")[:256],
                    "contact_details": str(item.get("contact_details") or "")[:2000],
                    "supplier_location": str(item.get("supplier_location") or "")[:256],
                    "price_text": str(item.get("price_text") or "")[:256],
                    "purchase_price": float(item.get("min_price") or 0),
                    "minimum_order_qty": float(item.get("moq") or 1),
                    "sales_text": str(item.get("sales_text") or "")[:256],
                    "ai_business_opportunity": str(
                        item.get("ai_business_opportunity") or ""
                    )[:4000],
                    "ai_opportunity_snapshot": ai_snapshot,
                    "delivery_days": int(float(item.get("delivery_days") or 0)),
                    "captured_at": fields.Datetime.now(),
                }
                offer = Offer.search([
                    ("candidate_id", "=", candidate.id),
                    ("platform", "=", platform),
                    ("external_id", "=", external_id),
                ], limit=1)
                if image_url and (not offer or offer.image_url != image_url or not offer.image_512):
                    try:
                        download_url = re.sub(
                            r"_\.(?:webp|avif)(?=\?|#|$)", "", image_url, flags=re.IGNORECASE,
                        )
                        image_data, _content_type = request.env[
                            "product.image.storage.oss"
                        ].sudo().download_image(download_url)
                        with Image.open(BytesIO(image_data)) as source_image:
                            source_image.thumbnail((512, 512), Image.Resampling.LANCZOS)
                            if source_image.mode not in ("RGB", "RGBA"):
                                source_image = source_image.convert("RGBA")
                            output = BytesIO()
                            source_image.save(output, format="PNG", optimize=True)
                        values["image_512"] = base64.b64encode(output.getvalue())
                    except Exception:
                        _logger.warning(
                            "Unable to cache sourcing image %s", image_url, exc_info=True,
                        )
                if offer:
                    offer.write(values)
                    updated += 1
                else:
                    Offer.create(values)
                    created += 1
                insight_content = str(item.get("ai_business_opportunity") or "").strip()[:4000]
                if insight_content:
                    insight_values = {
                        "candidate_id": candidate.id,
                        "source_platform": dict(Offer._fields["platform"].selection).get(platform, platform),
                        "external_ref": external_id,
                        "source_product_name": name,
                        "source_url": values["product_url"],
                        "insight_content": insight_content,
                        "captured_at": fields.Datetime.now(),
                    }
                    insight = Insight.search([
                        ("candidate_id", "=", candidate.id),
                        ("source_platform", "=", dict(Offer._fields["platform"].selection).get(platform, platform)),
                        ("external_ref", "=", external_id),
                    ], limit=1)
                    if insight:
                        insight.write(insight_values)
                    else:
                        Insight.create(insight_values)
            for source_insight in source_insights:
                if not isinstance(source_insight, dict):
                    continue
                content = str(source_insight.get("insight_content") or "").strip()[:4000]
                external_ref = str(source_insight.get("external_ref") or "").strip()[:256]
                platform = str(source_insight.get("source_platform") or "1688").strip()[:64]
                if not content or not external_ref or not platform:
                    continue
                insight_values = {
                    "candidate_id": candidate.id,
                    "source_platform": platform,
                    "external_ref": external_ref,
                    "source_product_name": str(
                        source_insight.get("source_product_name") or ""
                    ).strip()[:512],
                    "source_url": str(source_insight.get("source_url") or "").strip()[:2048],
                    "insight_content": content,
                    "captured_at": fields.Datetime.now(),
                }
                insight = Insight.search([
                    ("candidate_id", "=", candidate.id),
                    ("source_platform", "=", platform),
                    ("external_ref", "=", external_ref),
                ], limit=1)
                if insight:
                    insight.write(insight_values)
                else:
                    Insight.create(insight_values)
            if created or updated:
                candidate.message_post(body=(
                    "1688货源采集完成：新增 %s，更新 %s，跳过 %s。" % (created, updated, skipped)
                ))
            return request.make_json_response({
                "ok": True, "created": created, "updated": updated, "skipped": skipped,
            })
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return request.make_json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception:
            _logger.exception("1688 sourcing update failed for source %s", source_id)
            return request.make_json_response({"ok": False, "error": "internal_error"}, status=500)

    @http.route(
        "/product-intelligence/v1/sourcing-image-info/<int:source_id>/<int:candidate_id>",
        type="http", auth="public", methods=["GET", "OPTIONS"], csrf=False,
        save_session=False,
    )
    def sourcing_image_info(self, source_id, candidate_id, **kwargs):
        cors_headers = [
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET, OPTIONS"),
            ("Access-Control-Allow-Headers", "Authorization, X-PIH-Token, Content-Type"),
            ("Access-Control-Max-Age", "600"),
        ]
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=cors_headers, status=204)
        source = self._authorized_source(source_id)
        if not source:
            return request.make_json_response(
                {"ok": False, "error": "unauthorized"}, status=401, headers=cors_headers,
            )
        candidate = request.env["product.intelligence.candidate"].sudo().browse(candidate_id).exists()
        if not candidate or candidate.source_id != source:
            return request.make_json_response(
                {"ok": False, "error": "candidate_not_found"}, status=404, headers=cors_headers,
            )
        image_url = candidate.sourcing_image_url or candidate.image_url or candidate.original_image_url
        if not image_url:
            return request.make_json_response(
                {"ok": False, "error": "image_not_found"}, status=404, headers=cors_headers,
            )
        return request.make_json_response(
            {"ok": True, "image_url": image_url}, headers=cors_headers,
        )

    @http.route(
        "/product-intelligence/v1/sourcing-image/<int:source_id>/<int:candidate_id>",
        type="http", auth="public", methods=["GET", "OPTIONS"], csrf=False,
        save_session=False,
    )
    def sourcing_image(self, source_id, candidate_id, **kwargs):
        cors_headers = [
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET, OPTIONS"),
            ("Access-Control-Allow-Headers", "Authorization, X-PIH-Token, Content-Type"),
            ("Access-Control-Max-Age", "600"),
        ]
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=cors_headers, status=204)
        source = self._authorized_source(source_id)
        if not source:
            return request.make_json_response(
                {"ok": False, "error": "unauthorized"}, status=401, headers=cors_headers,
            )
        candidate = request.env["product.intelligence.candidate"].sudo().browse(candidate_id).exists()
        if not candidate or candidate.company_id != source.company_id:
            return request.make_json_response(
                {"ok": False, "error": "candidate_not_found"}, status=404, headers=cors_headers,
            )
        image_url = candidate.sourcing_image_url or candidate.image_url or candidate.original_image_url
        if not image_url:
            return request.make_json_response(
                {"ok": False, "error": "image_not_found"}, status=404, headers=cors_headers,
            )
        try:
            data, _content_type = request.env["product.image.storage.oss"].sudo().download_image(image_url)
            with Image.open(BytesIO(data)) as image:
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                if image.mode in ("RGBA", "LA"):
                    background = Image.new("RGB", image.size, "white")
                    background.paste(image, mask=image.getchannel("A"))
                    image = background
                elif image.mode != "RGB":
                    image = image.convert("RGB")
                output = BytesIO()
                image.save(output, format="JPEG", quality=90, optimize=True)
            return request.make_response(output.getvalue(), headers=[
                ("Content-Type", "image/jpeg"),
                ("Content-Disposition", 'inline; filename="pih-reference.jpg"'),
                ("Cache-Control", "private, max-age=300"),
                *cors_headers,
            ])
        except Exception:
            _logger.exception("Unable to prepare sourcing image for candidate %s", candidate_id)
            return request.make_json_response(
                {"ok": False, "error": "image_prepare_failed"}, status=422, headers=cors_headers,
            )
