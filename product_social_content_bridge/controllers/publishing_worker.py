from urllib.parse import urlparse

from odoo import fields, http
from odoo.http import request
from werkzeug.exceptions import Forbidden, NotFound

from .local_worker import LocalWorkerController


class PublishingWorkerController(LocalWorkerController):
    def _publication_task(self, task_id, require_owner=True):
        task = request.env["psc.publication.task"].sudo().browse(task_id).exists()
        if not task:
            raise NotFound()
        worker_id = self._worker_id()
        if not worker_id or task.worker_node_id.name != worker_id:
            raise Forbidden()
        if require_owner and task.worker_id and task.worker_id != worker_id:
            raise Forbidden()
        return task

    @http.route("/psc/local-worker/publication/tasks", type="http", auth="none", methods=["GET"], csrf=False)
    def publication_tasks(self, **kwargs):
        self._authorize()
        worker_id = self._worker_id()
        if not worker_id:
            raise Forbidden()
        self._touch_worker_node(worker_id)
        now = fields.Datetime.now()
        tasks = request.env["psc.publication.task"].sudo().search([
            ("worker_node_id.name", "=", worker_id),
            ("state", "=", "queued"),
            "|", ("scheduled_at", "=", False), ("scheduled_at", "<=", now),
        ], order="scheduled_at, id", limit=100)
        return request.make_json_response({"tasks": [{
            "id": task.id,
            "name": task.name,
            "destination_type": task.destination_type,
            "destination": task.destination_id.name,
            "platform": task.channel_id.platform,
            "account_username": task.publishing_account_id.username or "",
            "environment_id": task.bitbrowser_environment_id.environment_id,
            "expected_ip": task.publishing_account_id.expected_ip,
            "expected_country_code": task.publishing_account_id.expected_country_id.code or "",
            "expected_timezone": task.publishing_account_id.expected_timezone,
            "title": task.content_id.title or "",
            "caption": task.content_id.caption or "",
            "hashtags": task.content_id.hashtags or "",
            "video_script": task.content_id.video_script or "",
            "has_image": bool(task.content_id.image_attachment_id),
            "has_video": bool(task.content_id.video_attachment_id),
            "scheduled_at": fields.Datetime.to_string(task.scheduled_at) if task.scheduled_at else False,
        } for task in tasks]})

    @http.route("/psc/local-worker/publication/tasks/<int:task_id>/start", type="http", auth="none", methods=["POST"], csrf=False)
    def publication_start(self, task_id, **kwargs):
        self._authorize()
        task = self._publication_task(task_id, require_owner=False)
        worker_id = self._worker_id()
        if task.state != "queued":
            return request.make_json_response({"error": "task_not_queued"}, status=409)
        if task.worker_id and task.worker_id != worker_id:
            return request.make_json_response({"error": "task_owned_by_another_worker"}, status=409)
        task.write({
            "state": "validating", "worker_id": worker_id,
            "attempt_count": task.attempt_count + 1,
            "started_at": fields.Datetime.now(), "finished_at": False,
            "status_message": "正在校验固定 IP、国家、时区和登录账号", "error_message": False,
        })
        task._sync_project_state()
        return request.make_json_response({"ok": True})

    @http.route("/psc/local-worker/publication/tasks/<int:task_id>/environment", type="http", auth="none", methods=["POST"], csrf=False)
    def publication_environment(self, task_id, **kwargs):
        self._authorize()
        task = self._publication_task(task_id)
        if task.state != "validating":
            return request.make_json_response({"error": "task_not_validating"}, status=409)
        payload = request.httprequest.get_json(silent=True) or {}
        actual_ip = str(payload.get("actual_ip") or "").strip()[:128]
        actual_country = str(payload.get("actual_country_code") or "").strip().upper()[:8]
        actual_timezone = str(payload.get("actual_timezone") or "").strip()[:128]
        actual_username = str(payload.get("actual_username") or "").strip()[:256]
        account = task.publishing_account_id
        mismatches = []
        if actual_ip != (account.expected_ip or "").strip():
            mismatches.append("IP")
        if actual_country != (account.expected_country_id.code or "").upper():
            mismatches.append("国家")
        if actual_timezone != (account.expected_timezone or "").strip():
            mismatches.append("时区")
        if actual_username.casefold() != (account.username or "").strip().casefold():
            mismatches.append("登录账号")
        if mismatches:
            message = "%s不匹配，已停止发布" % "、".join(mismatches)
            task.write({
                "actual_ip": actual_ip, "state": "failed", "status_message": message,
                "error_message": message, "finished_at": fields.Datetime.now(),
            })
            task._sync_content_state()
            task._sync_project_state()
            return request.make_json_response({"error": "environment_mismatch", "message": message}, status=409)
        task.write({
            "actual_ip": actual_ip, "state": "publishing",
            "status_message": "环境和账号校验通过，正在发布",
        })
        return request.make_json_response({"ok": True})

    @http.route(
        "/psc/local-worker/publication/tasks/<int:task_id>/media/<string:media_type>",
        type="http", auth="none", methods=["GET"], csrf=False,
    )
    def publication_media(self, task_id, media_type, **kwargs):
        self._authorize()
        task = self._publication_task(task_id)
        attachment = {
            "image": task.content_id.image_attachment_id,
            "video": task.content_id.video_attachment_id,
        }.get(media_type)
        if not attachment:
            raise NotFound()
        return request.make_response(
            attachment.raw,
            headers=[
                ("Content-Type", attachment.mimetype or "application/octet-stream"),
                ("Content-Disposition", 'inline; filename="%s"' % (attachment.name or media_type)),
            ],
        )

    @http.route("/psc/local-worker/publication/tasks/<int:task_id>/complete", type="http", auth="none", methods=["POST"], csrf=False)
    def publication_complete(self, task_id, **kwargs):
        self._authorize()
        task = self._publication_task(task_id)
        if task.state != "publishing":
            return request.make_json_response({"error": "task_not_publishing"}, status=409)
        published_url = str(request.httprequest.form.get("published_url") or "").strip()[:2048]
        upload = request.httprequest.files.get("screenshot")
        if not published_url or not upload:
            return request.make_json_response({"error": "published_url_and_screenshot_required"}, status=400)
        allowed_hosts = {
            "facebook": ("facebook.com",), "instagram": ("instagram.com",),
            "tiktok": ("tiktok.com",), "linkedin": ("linkedin.com",),
            "youtube": ("youtube.com", "youtu.be"),
            "twitter": ("x.com", "twitter.com"), "alibaba": ("alibaba.com",),
        }
        parsed = urlparse(published_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not any(
            host == suffix or host.endswith("." + suffix)
            for suffix in allowed_hosts.get(task.channel_id.platform, ())
        ):
            return request.make_json_response({"error": "invalid_published_url"}, status=400)
        if upload.mimetype not in ("image/png", "image/jpeg"):
            return request.make_json_response({"error": "invalid_screenshot_type"}, status=400)
        screenshot_data = upload.read(10 * 1024 * 1024 + 1)
        if len(screenshot_data) > 10 * 1024 * 1024:
            return request.make_json_response({"error": "screenshot_too_large"}, status=413)
        attachment = request.env["ir.attachment"].sudo().create({
            "name": upload.filename or ("publication-%s.png" % task.id),
            "raw": screenshot_data, "mimetype": upload.mimetype,
            "res_model": task._name, "res_id": task.id,
        })
        task.write({
            "state": "published", "published_url": published_url,
            "screenshot_attachment_id": attachment.id,
            "status_message": "发布完成", "error_message": False,
            "finished_at": fields.Datetime.now(),
        })
        task.content_id.published_url = published_url
        task._sync_content_state()
        task._sync_project_state()
        return request.make_json_response({"ok": True})

    @http.route("/psc/local-worker/publication/tasks/<int:task_id>/fail", type="http", auth="none", methods=["POST"], csrf=False)
    def publication_fail(self, task_id, **kwargs):
        self._authorize()
        task = self._publication_task(task_id)
        payload = request.httprequest.get_json(silent=True) or {}
        message = str(payload.get("error") or "发布失败")[:4000]
        task.write({
            "state": "failed", "status_message": message,
            "error_message": message, "finished_at": fields.Datetime.now(),
        })
        task._sync_content_state()
        task._sync_project_state()
        return request.make_json_response({"ok": True})
