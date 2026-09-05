from datetime import timedelta

from odoo import fields, http
from odoo.http import request
from werkzeug.exceptions import Forbidden, NotFound


class LocalWorkerController(http.Controller):
    def _worker_id(self):
        return request.httprequest.headers.get("X-LightLink-Worker-ID", "").strip()[:128]

    def _lease_seconds(self):
        value = request.env["ir.config_parameter"].sudo().get_param("psc.local_worker_lease_seconds", "900")
        try:
            return max(60, min(3600, int(value)))
        except (TypeError, ValueError):
            return 900

    def _lease_expiry(self):
        return fields.Datetime.now() + timedelta(seconds=self._lease_seconds())

    def _authorize(self):
        expected = request.env["ir.config_parameter"].sudo().get_param("psc.local_worker_token")
        supplied = request.httprequest.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not expected or not supplied or supplied != expected:
            raise Forbidden()

    def _owned_task(self, task_id):
        task = request.env["psc.local.production.task"].sudo().browse(task_id).exists()
        worker_id = self._worker_id()
        if not task:
            raise NotFound()
        if not worker_id or task.worker_id != worker_id:
            raise Forbidden()
        return task

    @http.route("/psc/local-worker/ping", type="http", auth="none", methods=["GET"], csrf=False)
    def ping(self, **kwargs):
        self._authorize()
        return request.make_json_response({"ok": True})

    @http.route("/psc/local-worker/claim", type="http", auth="none", methods=["POST"], csrf=False)
    def claim(self, **kwargs):
        self._authorize()
        payload = request.httprequest.get_json(silent=True) or {}
        worker_id = self._worker_id() or str(payload.get("worker_id") or "")[:128]
        if not worker_id:
            raise Forbidden()
        task_model = request.env["psc.local.production.task"].sudo()
        now = fields.Datetime.now()
        stale_tasks = task_model.search([
            ("state", "in", ("claimed", "processing")),
            "|", ("lease_expires_at", "=", False), ("lease_expires_at", "<", now),
        ])
        if stale_tasks:
            stale_tasks.write({
                "state": "queued", "worker_id": False, "claimed_at": False,
                "lease_expires_at": False, "progress": 0,
                "status_message": "工作节点超时，已自动重新排队",
            })
        request.env.cr.execute("""
            SELECT id
              FROM psc_local_production_task
             WHERE state = 'queued'
             ORDER BY priority DESC, create_date, id
             FOR UPDATE SKIP LOCKED
             LIMIT 1
        """)
        row = request.env.cr.fetchone()
        task = task_model.browse(row[0]) if row else task_model
        if not task:
            return request.make_json_response({"task": None})
        task.write({
            "state": "claimed", "worker_id": worker_id, "claimed_at": now,
            "lease_expires_at": self._lease_expiry(), "attempt_count": task.attempt_count + 1,
            "status_message": "本地工具已领取",
        })
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
        task = self._owned_task(task_id)
        if task.state in ("done", "failed", "cancelled"):
            return request.make_json_response({"error": "task is no longer active"}, status=409)
        payload = request.httprequest.get_json(silent=True) or {}
        task.write({
            "state": "processing", "progress": max(0, min(100, int(payload.get("progress", 0)))),
            "status_message": str(payload.get("message") or "处理中")[:256],
            "lease_expires_at": self._lease_expiry(),
        })
        return request.make_json_response({"ok": True})

    @http.route("/psc/local-worker/tasks/<int:task_id>/heartbeat", type="http", auth="none", methods=["POST"], csrf=False)
    def heartbeat(self, task_id, **kwargs):
        self._authorize()
        task = self._owned_task(task_id)
        if task.state == "cancelled":
            return request.make_json_response({"ok": False, "cancelled": True}, status=409)
        if task.state not in ("claimed", "processing"):
            return request.make_json_response({"ok": False}, status=409)
        task.write({"lease_expires_at": self._lease_expiry()})
        return request.make_json_response({"ok": True})

    @http.route("/psc/local-worker/tasks/<int:task_id>/complete", type="http", auth="none", methods=["POST"], csrf=False)
    def complete(self, task_id, **kwargs):
        self._authorize()
        task = self._owned_task(task_id)
        if task.state in ("done", "failed", "cancelled"):
            return request.make_json_response({"error": "task is no longer active"}, status=409)
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
                    "output_subtitle_attachment_id": subtitle_attachment.id if subtitle_attachment else False,
                    "lease_expires_at": False})
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
        task = self._owned_task(task_id)
        if task.state in ("done", "cancelled"):
            return request.make_json_response({"error": "task is no longer active"}, status=409)
        payload = request.httprequest.get_json(silent=True) or {}
        message = str(payload.get("error") or "本地处理失败")[:4000]
        task.write({"state": "failed", "finished_at": fields.Datetime.now(), "error_message": message,
                    "lease_expires_at": False})
        task.content_id.sudo().write({"error_message": message})
        return request.make_json_response({"ok": True})
