import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LocalProductionTask(models.Model):
    _name = "psc.local.production.task"
    _description = "本地媒体生产任务"
    _order = "priority desc, create_date, id"

    name = fields.Char(required=True, default=lambda self: _("本地媒体生产任务"))
    content_id = fields.Many2one("psc.content.variant", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="content_id.project_id", store=True, index=True)
    product_id = fields.Many2one(related="content_id.product_id", store=True, index=True)
    task_type = fields.Selection([
        ("image", "生成图片"), ("video", "生成视频"),
        ("translate_mix", "翻译并混剪视频"),
    ], required=True, default="video", index=True)
    state = fields.Selection([
        ("queued", "等待本地工具"), ("claimed", "已领取"),
        ("processing", "处理中"), ("done", "已完成"),
        ("failed", "失败"), ("cancelled", "已取消"),
    ], required=True, default="queued", index=True)
    priority = fields.Integer(default=10)
    worker_id = fields.Char(string="工作节点", readonly=True, index=True)
    claimed_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    target_language = fields.Char(required=True)
    source_mode = fields.Selection([
        ("project_script", "按项目生成脚本"),
        ("translate_original", "翻译原视频"),
        ("auto", "自动判断"),
    ], required=True, default="auto")
    keywords = fields.Text()
    source_urls = fields.Text(string="素材网址（每行一个）")
    prompt = fields.Text(string="生成/混剪要求")
    video_script = fields.Text()
    aspect_ratio = fields.Char(default="9:16")
    duration_seconds = fields.Integer(default=15)
    source_image_attachment_id = fields.Many2one("ir.attachment", ondelete="set null")
    source_media_attachment_ids = fields.Many2many(
        "ir.attachment", "psc_local_task_source_attachment_rel", "task_id", "attachment_id",
        string="输入素材",
    )
    output_attachment_id = fields.Many2one("ir.attachment", readonly=True, ondelete="set null")
    output_subtitle_attachment_id = fields.Many2one("ir.attachment", readonly=True, ondelete="set null")
    progress = fields.Integer(default=0, readonly=True)
    status_message = fields.Char(readonly=True)
    error_message = fields.Text(readonly=True)

    @api.model
    def get_or_create_worker_token(self):
        params = self.env["ir.config_parameter"].sudo()
        token = params.get_param("psc.local_worker_token")
        if not token:
            token = secrets.token_urlsafe(36)
            params.set_param("psc.local_worker_token", token)
        return token

    def action_cancel(self):
        self.filtered(lambda task: task.state in ("queued", "claimed", "processing")).write({"state": "cancelled"})

    def action_retry(self):
        self.write({
            "state": "queued", "worker_id": False, "claimed_at": False,
            "finished_at": False, "progress": 0, "status_message": False,
            "error_message": False,
        })


class ContentVariant(models.Model):
    _inherit = "psc.content.variant"

    local_task_ids = fields.One2many("psc.local.production.task", "content_id", string="本地生产任务")
    local_task_count = fields.Integer(compute="_compute_local_task_count")
    source_video_urls = fields.Text(string="原视频网址（每行一个）")
    local_source_mode = fields.Selection([
        ("project_script", "按项目生成脚本"),
        ("translate_original", "翻译原视频"),
        ("auto", "自动判断"),
    ], string="视频处理模式", default="auto", required=True)
    requested_duration = fields.Integer(string="目标时长（秒）", default=15)

    @api.depends("local_task_ids")
    def _compute_local_task_count(self):
        for record in self:
            record.local_task_count = len(record.local_task_ids)

    def _queue_local_task(self, task_type):
        task_model = self.env["psc.local.production.task"]
        task_model.get_or_create_worker_token()
        for variant in self:
            language = variant.language_id.name or variant.language_id.code or "English"
            source_image = variant.image_attachment_id
            if not source_image and variant.product_id.image_1920:
                source_image = self.env["ir.attachment"].create({
                    "name": "product-%s-reference.jpg" % variant.product_id.id,
                    "type": "binary", "datas": variant.product_id.image_1920,
                    "mimetype": "image/jpeg", "res_model": variant._name, "res_id": variant.id,
                })
            values = {
                "name": "%s - %s" % (variant.display_name, dict(task_model._fields["task_type"].selection)[task_type]),
                "content_id": variant.id,
                "task_type": task_type,
                "target_language": language,
                "source_mode": variant.local_source_mode,
                "keywords": "\n".join(filter(None, [variant.title, variant.hashtags])),
                "source_urls": variant.source_video_urls,
                "prompt": variant.image_prompt if task_type == "image" else variant.caption,
                "video_script": variant.video_script,
                "aspect_ratio": (variant.channel_id.image_ratio or "9_16").replace("_", ":"),
                "duration_seconds": variant.requested_duration or 15,
                "source_image_attachment_id": source_image.id if source_image else False,
            }
            task_model.create(values)
            if task_type == "image":
                variant.write({"image_ai_state": "pending", "image_ai_model": "Windows本地工具", "error_message": False})
            else:
                variant.write({"video_ai_state": "pending", "video_ai_model": "Windows本地工具", "error_message": False})
        return True

    def action_generate_social_image(self):
        return self._queue_local_task("image")

    def action_generate_social_video(self):
        return self._queue_local_task("translate_mix")

    def action_open_local_tasks(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("本地生产任务"),
            "res_model": "psc.local.production.task", "view_mode": "list,form",
            "domain": [("content_id", "=", self.id)],
            "context": {"default_content_id": self.id},
        }
