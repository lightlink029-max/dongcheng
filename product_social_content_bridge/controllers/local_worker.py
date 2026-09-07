from datetime import timedelta
import re
from urllib.parse import urlparse

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

    def _touch_worker_node(self, worker_id):
        if not worker_id:
            return request.env["psc.local.worker.node"]
        model = request.env["psc.local.worker.node"].sudo()
        node = model.search([("name", "=", worker_id)], limit=1)
        values = {"last_seen_at": fields.Datetime.now(), "active": True}
        if node:
            node.write(values)
        else:
            node = model.create({"name": worker_id, **values})
        return node

    @http.route("/psc/local-worker/ping", type="http", auth="none", methods=["GET"], csrf=False)
    def ping(self, **kwargs):
        self._authorize()
        self._touch_worker_node(self._worker_id())
        return request.make_json_response({"ok": True})

    @http.route("/psc/local-worker/bitbrowser/environments", type="http", auth="none", methods=["POST"], csrf=False)
    def sync_bitbrowser_environments(self, **kwargs):
        self._authorize()
        payload = request.httprequest.get_json(silent=True) or {}
        worker_id = self._worker_id() or str(payload.get("worker_id") or "").strip()[:128]
        if not worker_id:
            raise Forbidden()
        environments = payload.get("environments") or []
        if not isinstance(environments, list) or len(environments) > 500:
            return request.make_json_response({"error": "invalid_environments"}, status=400)
        node = self._touch_worker_node(worker_id)
        model = request.env["psc.bitbrowser.environment"].sudo()
        incoming_ids = []
        now = fields.Datetime.now()
        for item in environments:
            if not isinstance(item, dict):
                continue
            environment_id = str(item.get("id") or item.get("browserId") or "").strip()[:128]
            if not environment_id:
                continue
            environment = model.search([("environment_id", "=", environment_id)], limit=1)
            if environment and environment.worker_node_id != node:
                return request.make_json_response({
                    "error": "environment_worker_conflict", "environment_id": environment_id,
                }, status=409)
            raw_state = item.get("isOpen", item.get("opened", item.get("status", "")))
            opened = raw_state is True or str(raw_state).lower() in (
                "1", "true", "open", "opened", "running",
            )
            try:
                sequence = int(item.get("seq") or 0)
            except (TypeError, ValueError):
                sequence = 0
            values = {
                "name": str(item.get("name") or ("比特环境 %s" % (sequence or environment_id[:8])))[:256],
                "environment_id": environment_id,
                "sequence": sequence,
                "worker_node_id": node.id,
                "platform": str(item.get("platform") or item.get("platformName") or "")[:256],
                "username": str(item.get("userName") or item.get("username") or "")[:256],
                "state": "open" if opened else "closed",
                "available": True,
                "last_synced_at": now,
            }
            if environment:
                environment.write(values)
            else:
                model.create(values)
            incoming_ids.append(environment_id)
        missing = node.bitbrowser_environment_ids.filtered(
            lambda environment: environment.environment_id not in incoming_ids
        )
        if missing:
            missing.write({"available": False, "state": "unknown", "last_synced_at": now})
        return request.make_json_response({"ok": True, "saved": len(incoming_ids)})

    @http.route("/psc/local-worker/claim", type="http", auth="none", methods=["POST"], csrf=False)
    def claim(self, **kwargs):
        self._authorize()
        payload = request.httprequest.get_json(silent=True) or {}
        worker_id = self._worker_id() or str(payload.get("worker_id") or "")[:128]
        if not worker_id:
            raise Forbidden()
        self._touch_worker_node(worker_id)
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
        return request.env["ir.binary"]._get_stream_from(attachment).get_response(
            as_attachment=True,
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

    @http.route("/psc/local-worker/tasks/<int:task_id>/selection-ready", type="http", auth="none", methods=["POST"], csrf=False)
    def selection_ready(self, task_id, **kwargs):
        self._authorize()
        task = self._owned_task(task_id)
        if task.task_type != "douyin_select" or task.state in ("done", "failed", "cancelled"):
            return request.make_json_response({"error": "task is not an active selection"}, status=409)
        task.write({
            "state": "processing", "progress": 40,
            "status_message": "图片已传入 MuMu，选片与混剪由 Windows 工具处理",
            "lease_expires_at": self._lease_expiry(),
        })
        return request.make_json_response({"ok": True})

    @http.route("/psc/local-worker/tasks/<int:task_id>/selection-complete", type="http", auth="none", methods=["POST"], csrf=False)
    def selection_complete(self, task_id, **kwargs):
        self._authorize()
        task = self._owned_task(task_id)
        if task.task_type != "douyin_select" or task.state not in ("claimed", "processing"):
            return request.make_json_response({"error": "task is not an active selection"}, status=409)
        payload = request.httprequest.get_json(silent=True) or {}
        text = str(payload.get("urls") or "")[:20000]
        urls, seen = [], set()
        for raw in re.findall(r"https?://[^\s<>\"']+", text):
            url = raw.rstrip(".,;，。；!！?？)]}")
            try:
                host = (urlparse(url).hostname or "").lower()
            except ValueError:
                continue
            if host not in ("douyin.com", "www.douyin.com", "v.douyin.com", "v.iesdouyin.com") or url in seen:
                continue
            seen.add(url)
            urls.append(url)
            if len(urls) >= 100:
                break
        if not urls:
            return request.make_json_response({"error": "no_valid_douyin_urls"}, status=400)
        task.content_id.sudo().write({"source_video_urls": "\n".join(urls)})
        task.write({
            "state": "done", "progress": 100, "finished_at": fields.Datetime.now(),
            "status_message": "已同步 %s 条抖音视频链接" % len(urls), "lease_expires_at": False,
        })
        return request.make_json_response({"ok": True, "saved": len(urls)})

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
