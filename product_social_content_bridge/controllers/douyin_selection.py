import base64
import re

from odoo import http
from odoo.http import request


DOUYIN_VIDEO_RE = re.compile(r"^https://(?:www\.)?douyin\.com/video/(\d+)(?:[/?#].*)?$", re.I)


class DouyinSelectionController(http.Controller):
    @staticmethod
    def _authorized_records(source_id, content_id):
        source = request.env["product.intelligence.source"].sudo().browse(source_id).exists()
        authorization = request.httprequest.headers.get("Authorization", "")
        token = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
        content = request.env["psc.content.variant"].sudo().browse(content_id).exists()
        if (
            not source or not source._check_webhook_token(token) or not content
            or source.company_id != content.project_id.company_id
        ):
            return False, False
        return source, content

    @http.route(
        "/product-intelligence/v1/douyin-selection/<int:source_id>/<int:content_id>",
        type="http", auth="public", methods=["POST"], csrf=False, save_session=False,
    )
    def save_selection(self, source_id, content_id, **kwargs):
        _source, content = self._authorized_records(source_id, content_id)
        if not content:
            return request.make_json_response({"ok": False, "error": "unauthorized"}, status=401)
        payload = request.httprequest.get_json(silent=True) or {}
        urls = payload.get("urls") or []
        if not isinstance(urls, list) or len(urls) > 100:
            return request.make_json_response({"ok": False, "error": "invalid_urls"}, status=400)
        normalized = []
        seen = set()
        for raw_url in urls:
            match = DOUYIN_VIDEO_RE.match(str(raw_url or "").strip())
            if not match:
                continue
            url = "https://www.douyin.com/video/%s" % match.group(1)
            if url not in seen:
                seen.add(url)
                normalized.append(url)
        content.write({"source_video_urls": "\n".join(normalized)})
        return request.make_json_response({"ok": True, "saved": len(normalized)})

    @http.route(
        "/product-intelligence/v1/douyin-image/<int:source_id>/<int:content_id>",
        type="http", auth="public", methods=["GET"], csrf=False, save_session=False,
    )
    def reference_image(self, source_id, content_id, **kwargs):
        _source, content = self._authorized_records(source_id, content_id)
        if not content:
            return request.make_json_response({"ok": False, "error": "unauthorized"}, status=401)
        attachment = content.image_attachment_id
        raw = attachment.raw if attachment else False
        mimetype = attachment.mimetype if attachment else False
        if not raw and content.product_id.image_1920:
            raw = base64.b64decode(content.product_id.image_1920)
            mimetype = "image/jpeg"
        if not raw:
            return request.make_json_response({"ok": False, "error": "image_not_found"}, status=404)
        return request.make_response(raw, headers=[
            ("Content-Type", mimetype or "image/jpeg"),
            ("Cache-Control", "private, max-age=60"),
        ])
