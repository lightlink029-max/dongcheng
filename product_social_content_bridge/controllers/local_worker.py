from odoo import fields, http
from odoo.http import request
from werkzeug.exceptions import Forbidden, NotFound


class LocalWorkerController(http.Controller):
    def _authorize(self):
        expected = request.env["ir.config_parameter"].sudo().get_param("psc.local_worker_token")
        supplied = request.httprequest.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not expected or not supplied or supplied != expected:
            raise Forbidden()

    @http.route("/psc/local-worker/claim", type="http", auth="none", methods=["POST"], csrf=False)
    def claim(self, **kwargs):
        self._authorize()
        payload = request.httprequest.get_json(silent=True) or {}
        worker_id = str(payload.get("worker_id") or "windows-worker")[:128]
        task = request.env["psc.local.production.task"].sudo().search(
            [("state", "=", "queued")], order="priority desc, create_date, id", limit=1,
        )
        if not task:
            return request.make_json_response({"task": None})
        task.write({"state": "claimed", "worker_id": worker_id, "claimed_at": fields.Datetime.now(),
                    "status_message": "本地工具已领取"})
        attachments = task.source_media_attachment_ids
        return request.make_json_response({"task": {
            "id": task.id, "type": task.task_type, "target_language": task.target_language,
            "source_mode": task.source_mode, "keywords": task.keywords or "",
            "source_urls": [x.strip() for x in (task.source_urls or "").splitlines() if x.strip()],
            "prompt": task.prompt or "", "video_script": task.video_script or "",
            "aspect_ratio": task.aspect_ratio, "duration_seconds": task.duration_seconds,
            "source_image_id": task.source_image_attachment_id.id or None,
            "source_media": [{"id": item.id, "name": item.name} for item in attachments],
        }})

    @http.route("/psc/local-worker/attachments/<int:attachment_id>", type="http", auth="none", methods=["GET"], csrf=False)
    def attachment(self, attachment_id, **kwargs):
        self._authorize()
        attachment = request.env["ir.attachment"].sudo().browse(attachment_id).exists()
        if not attachment:
            raise NotFound()
        return request.make_response(
            attachment.raw or b"",
            headers=[
                ("Content-Type", attachment.mimetype or "application/octet-stream"),
                ("Content-Disposition", 'attachment; filename="%s"' % (attachment.name or "asset")),
            ],
        )

    @http.route("/psc/local-worker/tasks/<int:task_id>/progress", type="http", auth="none", methods=["POST"], csrf=False)
    def progress(self, task_id, **kwargs):
        self._authorize()
        task = request.env["psc.local.production.task"].sudo().browse(task_id).exists()
        if not task:
            raise NotFound()
        payload = request.httprequest.get_json(silent=True) or {}
        task.write({
            "state": "processing", "progress": max(0, min(100, int(payload.get("progress", 0)))),
            "status_message": str(payload.get("message") or "处理中")[:256],
        })
        return request.make_json_response({"ok": True})

    @http.route("/psc/local-worker/tasks/<int:task_id>/complete", type="http", auth="none", methods=["POST"], csrf=False)
    def complete(self, task_id, **kwargs):
        self._authorize()
        task = request.env["psc.local.production.task"].sudo().browse(task_id).exists()
        if not task:
            raise NotFound()
        upload = request.httprequest.files.get("file")
        if not upload:
            return request.make_json_response({"error": "missing file"}, status=400)
        data = upload.read()
        attachment = request.env["ir.attachment"].sudo().create({
            "name": upload.filename or ("local-output-%s.mp4" % task.id),
            "raw": data, "mimetype": upload.mimetype or "application/octet-stream",
            "res_model": "psc.content.variant", "res_id": task.content_id.id,
        })
        subtitle = request.httprequest.files.get("subtitle")
        subtitle_attachment = False
        if subtitle:
            subtitle_attachment = request.env["ir.attachment"].sudo().create({
                "name": subtitle.filename or ("subtitle-%s.srt" % task.id), "raw": subtitle.read(),
                "mimetype": subtitle.mimetype or "text/plain", "res_model": "psc.content.variant",
                "res_id": task.content_id.id,
            })
        task.write({"state": "done", "progress": 100, "finished_at": fields.Datetime.now(),
                    "status_message": "成品已回传", "output_attachment_id": attachment.id,
                    "output_subtitle_attachment_id": subtitle_attachment.id if subtitle_attachment else False})
        if task.task_type == "image":
            task.content_id.sudo().write({"image_attachment_id": attachment.id, "image_ai_state": "done",
                                          "image_ai_model": "Windows本地工具", "image_generated_at": fields.Datetime.now()})
        else:
            task.content_id.sudo().write({"video_attachment_id": attachment.id, "video_ai_state": "done",
                                          "video_ai_model": "Windows本地工具", "video_generated_at": fields.Datetime.now()})
        return request.make_json_response({"ok": True, "attachment_id": attachment.id})

    @http.route("/psc/local-worker/tasks/<int:task_id>/fail", type="http", auth="none", methods=["POST"], csrf=False)
    def fail(self, task_id, **kwargs):
        self._authorize()
        task = request.env["psc.local.production.task"].sudo().browse(task_id).exists()
        if not task:
            raise NotFound()
        payload = request.httprequest.get_json(silent=True) or {}
        message = str(payload.get("error") or "本地处理失败")[:4000]
        task.write({"state": "failed", "finished_at": fields.Datetime.now(), "error_message": message})
        task.content_id.sudo().write({"error_message": message})
        return request.make_json_response({"ok": True})
