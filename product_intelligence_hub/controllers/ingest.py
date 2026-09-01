import json
import logging

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class ProductIntelligenceIngestController(http.Controller):

    @http.route(
        "/product-intelligence/v1/ingest/<int:source_id>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def ingest(self, source_id, **kwargs):
        source = request.env["product.intelligence.source"].sudo().browse(source_id).exists()
        authorization = request.httprequest.headers.get("Authorization", "")
        token = request.httprequest.headers.get("X-PIH-Token", "")
        if authorization.startswith("Bearer "):
            token = authorization[7:].strip()
        if not source or not source._check_webhook_token(token):
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
