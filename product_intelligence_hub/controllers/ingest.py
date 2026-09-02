import json
import logging

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
                candidate.write({
                    "category": str(payload.get("category") or candidate.category or "")[:512],
                    "important_attributes": str(payload.get("important_attributes") or "")[:10000],
                    "packaging_information": str(payload.get("packaging_information") or "")[:10000],
                    "shipping_information": str(payload.get("shipping_information") or "")[:10000],
                    "detail_state": "done", "detail_error": False,
                    "detail_updated_at": fields.Datetime.now(),
                })
            return request.make_json_response({"ok": True})
        except Exception:
            _logger.exception("Product detail update failed for source %s", source_id)
            return request.make_json_response({"ok": False, "error": "internal_error"}, status=500)
