from odoo import fields, http
from odoo.http import request
from werkzeug.exceptions import Forbidden, NotFound
from urllib.parse import urlparse

from .local_worker import LocalWorkerController


class RegistrationWorkerController(LocalWorkerController):
    def _registration_task(self, task_id, require_owner=True):
        task = request.env["psc.social.registration.task"].sudo().browse(task_id).exists()
        if not task:
            raise NotFound()
        worker_id = self._worker_id()
        if task.worker_node_id.name != worker_id:
            raise Forbidden()
        if require_owner and task.worker_id and task.worker_id != worker_id:
            raise Forbidden()
        return task

    @http.route("/psc/local-worker/registration/tasks", type="http", auth="none", methods=["GET"], csrf=False)
    def registration_tasks(self, **kwargs):
        self._authorize()
        worker_id = self._worker_id()
        if not worker_id:
            raise Forbidden()
        self._touch_worker_node(worker_id)
        tasks = request.env["psc.social.registration.task"].sudo().search([
            ("worker_node_id.name", "=", worker_id),
            ("state", "in", ("ready", "environment_check", "awaiting_verification")),
        ], order="create_date, id", limit=100)
        return request.make_json_response({"tasks": [{
            "id": task.id,
            "name": task.name,
            "state": task.state,
            "platform": task.platform,
            "email": task.email_asset_id.email,
            "display_name": task.display_name or "",
            "desired_username": task.desired_username or "",
            "environment_id": task.bitbrowser_environment_id.environment_id,
            "environment_name": task.bitbrowser_environment_id.name,
            "expected_ip": task.expected_ip,
            "expected_country_code": task.expected_country_id.code or "",
            "expected_timezone": task.expected_timezone,
            "status_message": task.status_message or "",
        } for task in tasks]})

    @http.route("/psc/local-worker/registration/tasks/<int:task_id>/start", type="http", auth="none", methods=["POST"], csrf=False)
    def registration_start(self, task_id, **kwargs):
        self._authorize()
        task = self._registration_task(task_id, require_owner=False)
        worker_id = self._worker_id()
        if task.state not in ("ready", "environment_check", "awaiting_verification"):
            return request.make_json_response({"error": "task_not_ready"}, status=409)
        if task.worker_id and task.worker_id != worker_id:
            return request.make_json_response({"error": "task_owned_by_another_worker"}, status=409)
        task.write({
            "state": "environment_check", "worker_id": worker_id,
            "started_at": task.started_at or fields.Datetime.now(),
            "status_message": "正在校验固定 IP、国家和时区", "error_message": False,
        })
        return request.make_json_response({"ok": True})

    @http.route("/psc/local-worker/registration/tasks/<int:task_id>/environment", type="http", auth="none", methods=["POST"], csrf=False)
    def registration_environment(self, task_id, **kwargs):
        self._authorize()
        task = self._registration_task(task_id)
        if task.state != "environment_check":
            return request.make_json_response({"error": "task_not_checking_environment"}, status=409)
        payload = request.httprequest.get_json(silent=True) or {}
        actual_ip = str(payload.get("actual_ip") or "").strip()[:128]
        actual_country = str(payload.get("actual_country_code") or "").strip().upper()[:8]
        actual_timezone = str(payload.get("actual_timezone") or "").strip()[:128]
        mismatches = []
        if actual_ip != task.expected_ip.strip():
            mismatches.append("IP")
        if actual_country != (task.expected_country_id.code or "").upper():
            mismatches.append("国家")
        if actual_timezone != task.expected_timezone.strip():
            mismatches.append("时区")
        values = {
            "actual_ip": actual_ip, "actual_country_code": actual_country,
            "actual_timezone": actual_timezone,
        }
        if mismatches:
            message = "%s不匹配，已停止注册" % "、".join(mismatches)
            task.write({**values, "state": "environment_mismatch", "error_message": message,
                        "status_message": message, "finished_at": fields.Datetime.now()})
            return request.make_json_response({"error": "environment_mismatch", "message": message}, status=409)
        task.write({**values, "state": "awaiting_verification", "status_message": "环境校验通过，等待人工验证码和身份验证"})
        return request.make_json_response({"ok": True})

    @http.route("/psc/local-worker/registration/tasks/<int:task_id>/complete", type="http", auth="none", methods=["POST"], csrf=False)
    def registration_complete(self, task_id, **kwargs):
        self._authorize()
        task = self._registration_task(task_id)
        if task.state != "awaiting_verification":
            return request.make_json_response({"error": "task_not_waiting_for_verification"}, status=409)
        username = str(request.httprequest.form.get("username") or "").strip()[:256]
        profile_url = str(request.httprequest.form.get("profile_url") or "").strip()[:1024]
        platform_account_id = str(request.httprequest.form.get("platform_account_id") or "").strip()[:256]
        upload = request.httprequest.files.get("screenshot")
        if not username or not profile_url or not upload:
            return request.make_json_response({"error": "username_profile_url_and_screenshot_required"}, status=400)
        allowed_hosts = {
            "facebook": ("facebook.com",), "instagram": ("instagram.com",),
            "tiktok": ("tiktok.com",), "linkedin": ("linkedin.com",),
        }
        parsed = urlparse(profile_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not any(
            host == suffix or host.endswith("." + suffix)
            for suffix in allowed_hosts.get(task.platform, ())
        ):
            return request.make_json_response({"error": "invalid_platform_profile_url"}, status=400)
        if upload.mimetype not in ("image/png", "image/jpeg"):
            return request.make_json_response({"error": "invalid_screenshot_type"}, status=400)
        screenshot_data = upload.read(10 * 1024 * 1024 + 1)
        if len(screenshot_data) > 10 * 1024 * 1024:
            return request.make_json_response({"error": "screenshot_too_large"}, status=413)
        attachment = request.env["ir.attachment"].sudo().create({
            "name": upload.filename or ("registration-%s.png" % task.id),
            "raw": screenshot_data, "mimetype": upload.mimetype,
            "res_model": "psc.social.registration.task", "res_id": task.id,
        })
        account_model = request.env["psc.social.publishing.account"].sudo()
        account = account_model.search([("bitbrowser_environment_id", "=", task.bitbrowser_environment_id.id)], limit=1)
        account_values = {
            "name": task.display_name or username,
            "product_line_id": task.product_line_id.id,
            "channel_id": task.channel_id.id,
            "target_market_id": task.target_market_id.id,
            "username": username, "profile_url": profile_url,
            "platform_account_id": platform_account_id,
            "email_asset_id": task.email_asset_id.id,
            "registration_task_id": task.id,
            "worker_node_id": task.worker_node_id.id,
            "bitbrowser_environment_id": task.bitbrowser_environment_id.id,
            "expected_ip": task.expected_ip,
            "expected_country_id": task.expected_country_id.id,
            "account_state": "available", "active": True,
            "last_validation_at": fields.Datetime.now(), "last_validation_state": "passed",
            "last_validation_message": "注册完成；IP %s，国家 %s，时区 %s" % (
                task.actual_ip, task.actual_country_code, task.actual_timezone,
            ),
        }
        if account:
            account.write(account_values)
        else:
            account = account_model.create(account_values)
        task.write({
            "state": "done", "platform_account_id": platform_account_id,
            "registered_username": username, "profile_url": profile_url,
            "screenshot_attachment_id": attachment.id, "social_account_id": account.id,
            "status_message": "注册资料已确认，账号可发布", "error_message": False,
            "finished_at": fields.Datetime.now(),
        })
        return request.make_json_response({"ok": True, "account_id": account.id})

    @http.route("/psc/local-worker/registration/tasks/<int:task_id>/fail", type="http", auth="none", methods=["POST"], csrf=False)
    def registration_fail(self, task_id, **kwargs):
        self._authorize()
        task = self._registration_task(task_id)
        payload = request.httprequest.get_json(silent=True) or {}
        message = str(payload.get("error") or "人工终止注册")[:4000]
        task.write({"state": "failed", "error_message": message, "status_message": message,
                    "finished_at": fields.Datetime.now()})
        return request.make_json_response({"ok": True})
