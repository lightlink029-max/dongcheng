import secrets
from urllib.parse import quote

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
    content_scope_id = fields.Many2one(related="content_id.scope_id", store=True, index=True)
    content_format = fields.Selection(related="content_id.content_format", store=True, index=True)
    task_type = fields.Selection([
        ("image", "生成图片"), ("video", "生成视频"),
        ("translate_mix", "翻译并混剪视频"),
        ("douyin_select", "抖音图片选片"),
    ], required=True, default="video", index=True)
    state = fields.Selection([
        ("queued", "等待本地工具"), ("claimed", "已领取"),
        ("processing", "处理中"), ("done", "已完成"),
        ("failed", "失败"), ("cancelled", "已取消"),
    ], required=True, default="queued", index=True)
    priority = fields.Integer(default=10)
    worker_id = fields.Char(string="工作节点", readonly=True, index=True)
    claimed_at = fields.Datetime(readonly=True)
    lease_expires_at = fields.Datetime(string="任务租约到期", readonly=True, index=True)
    attempt_count = fields.Integer(string="领取次数", readonly=True, default=0)
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
    video_plan_summary = fields.Text(string="视频整体方案", readonly=True)
    storyboard_snapshot = fields.Json(string="分镜要求快照", readonly=True)
    output_manifest = fields.Json(string="本地成片清单", readonly=True)
    used_local_asset_ids = fields.Many2many(
        "psc.local.media.asset", "psc_local_task_asset_rel", "task_id", "asset_id",
        string="最终使用的本地分镜", readonly=True,
    )

    @api.model
    def get_or_create_worker_token(self):
        params = self.env["ir.config_parameter"].sudo()
        token = params.get_param("psc.local_worker_token")
        if not token:
            token = secrets.token_urlsafe(36)
            params.set_param("psc.local_worker_token", token)
        return token

    def action_cancel(self):
        self.filtered(lambda task: task.state in ("queued", "claimed", "processing")).write({
            "state": "cancelled", "lease_expires_at": False,
        })

    def action_retry(self):
        self.write({
            "state": "queued", "worker_id": False, "claimed_at": False,
            "lease_expires_at": False,
            "finished_at": False, "progress": 0, "status_message": False,
            "error_message": False,
        })


class ContentVariant(models.Model):
    _inherit = "psc.content.variant"

    local_task_ids = fields.One2many("psc.local.production.task", "content_id", string="本地生产任务")
    local_task_count = fields.Integer(compute="_compute_local_task_count")
    source_video_urls = fields.Text(string="原视频网址（每行一个）")
    douyin_search_keyword = fields.Char(string="抖音素材关键词")
    local_source_mode = fields.Selection([
        ("project_script", "按项目生成脚本"),
        ("translate_original", "翻译原视频"),
        ("auto", "自动判断"),
    ], string="视频处理模式", default="auto", required=True)
    requested_duration = fields.Integer(string="目标时长（秒）", default=15)
    video_plan_summary = fields.Text(
        string="视频整体方案",
        help="先说明整条视频为什么制作、面向谁、核心观点和叙事顺序，再定义分镜。",
    )
    video_production_state = fields.Selection([
        ("plan", "待确认方案"), ("storyboard", "待确认分镜"),
        ("locked", "故事板已锁定"), ("processing", "本地制作中"),
        ("review", "待审核"), ("done", "已完成"),
    ], string="视频制作状态", default="plan", required=True, index=True)
    storyboard_locked = fields.Boolean(string="故事板已锁定", readonly=True)
    video_shot_ids = fields.One2many(
        "psc.video.shot.requirement", "content_id", string="分镜需求",
    )

    @api.depends("local_task_ids")
    def _compute_local_task_count(self):
        for record in self:
            record.local_task_count = len(record.local_task_ids)

    def _queue_local_task(self, task_type):
        task_model = self.env["psc.local.production.task"]
        task_model.get_or_create_worker_token()
        for variant in self:
            active_task = variant.local_task_ids.filtered(
                lambda task: task.task_type == task_type
                and task.state in ("queued", "claimed", "processing")
            )
            if active_task:
                raise UserError(_("该内容已有同类型任务正在排队或处理中：%s") % active_task[0].display_name)
            if task_type in ("video", "translate_mix"):
                if not variant.storyboard_locked:
                    raise UserError(_("请先确认视频整体方案、分镜需求并锁定故事板。"))
                if not variant.video_shot_ids:
                    raise UserError(_("故事板至少需要一个分镜。"))
            language = variant.language_id.name or variant.language_id.code or "English"
            source_image = variant.image_attachment_id
            if not source_image and variant.product_id and variant.product_id.image_1920:
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
                "video_plan_summary": variant.video_plan_summary or "",
                "storyboard_snapshot": variant._storyboard_payload(),
            }
            task_model.create(values)
            if task_type == "image":
                variant.write({"image_ai_state": "pending", "image_ai_model": "Windows本地工具", "error_message": False})
            elif task_type != "douyin_select":
                variant.write({
                    "video_ai_state": "pending", "video_ai_model": "Windows本地工具",
                    "video_production_state": "processing", "error_message": False,
                })
        return True

    def _storyboard_payload(self):
        self.ensure_one()
        return [{
            "id": shot.id,
            "slot_key": shot.slot_key,
            "sequence": shot.sequence,
            "name": shot.name,
            "purpose": shot.purpose or "",
            "visual_requirement": shot.visual_requirement or "",
            "narration": shot.narration or "",
            "target_duration": shot.target_duration,
            "required": shot.required,
            "state": shot.state,
            "selected_asset_uuid": shot.selected_asset_id.asset_uuid or "",
        } for shot in self.video_shot_ids.sorted("sequence")]

    def action_lock_storyboard(self):
        for variant in self:
            if not (variant.video_plan_summary or "").strip():
                raise UserError(_("请先填写视频整体方案。"))
            if not variant.video_shot_ids:
                raise UserError(_("请至少添加一个分镜需求。"))
            invalid = variant.video_shot_ids.filtered(
                lambda shot: not (shot.name and shot.visual_requirement and shot.target_duration > 0)
            )
            if invalid:
                raise UserError(_("每个分镜都必须填写名称、画面要求和目标时长。"))
            variant.write({"storyboard_locked": True, "video_production_state": "locked"})
        return True

    def action_unlock_storyboard(self):
        self.write({"storyboard_locked": False, "video_production_state": "storyboard"})
        return True

    def action_generate_social_image(self):
        return self._queue_local_task("image")

    def action_generate_social_video(self):
        return self._queue_local_task("translate_mix")

    def _douyin_search_action(self, search_mode):
        self.ensure_one()
        keyword = (
            self.douyin_search_keyword
            or self.title
            or (self.product_id.name if self.product_id else "")
        ).strip()
        if not keyword:
            raise UserError(_("请先填写抖音素材关键词。"))
        url = "https://www.douyin.com/search/%s?type=video&pih_content_id=%s&pih_search_mode=%s" % (
            quote(keyword), self.id, search_mode,
        )
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}

    def action_open_douyin_keyword_search(self):
        return self._douyin_search_action("text")

    def action_open_douyin_image_search(self):
        self.ensure_one()
        active_task = self.local_task_ids.filtered(
            lambda task: task.task_type == "douyin_select" and task.state in ("queued", "claimed", "processing")
        )
        if not active_task:
            self._queue_local_task("douyin_select")
        return self.action_open_local_tasks()

    def action_open_local_tasks(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("本地生产任务"),
            "res_model": "psc.local.production.task", "view_mode": "list,form",
            "domain": [("content_id", "=", self.id)],
            "context": {"default_content_id": self.id},
        }


class VideoShotRequirement(models.Model):
    _name = "psc.video.shot.requirement"
    _description = "视频分镜需求"
    _order = "sequence, id"

    content_id = fields.Many2one(
        "psc.content.variant", string="渠道内容版本", required=True,
        ondelete="cascade", index=True,
    )
    sequence = fields.Integer(string="顺序", default=10)
    slot_key = fields.Char(string="分镜编号", required=True, default=lambda self: secrets.token_hex(6), index=True)
    name = fields.Char(string="分镜名称", required=True)
    purpose = fields.Char(string="叙事作用")
    visual_requirement = fields.Text(string="画面要求", required=True)
    narration = fields.Text(string="对应文案")
    target_duration = fields.Float(string="目标时长（秒）", default=3.0, required=True)
    required = fields.Boolean(string="必要分镜", default=True)
    state = fields.Selection([
        ("missing", "缺少素材"), ("producing", "制作中"),
        ("ready", "已有候选"), ("selected", "已选定"),
    ], string="状态", default="missing", required=True, index=True)
    selected_asset_id = fields.Many2one(
        "psc.local.media.asset", string="选用本地分镜", ondelete="set null",
    )

    _slot_unique = models.Constraint(
        "UNIQUE(content_id, slot_key)", "同一视频中的分镜编号不能重复。",
    )

    @api.onchange("selected_asset_id")
    def _onchange_selected_asset(self):
        for shot in self:
            shot.state = "selected" if shot.selected_asset_id else "missing"


class LocalMediaAsset(models.Model):
    _name = "psc.local.media.asset"
    _description = "本地分镜素材索引"
    _order = "last_seen_at desc, id desc"

    name = fields.Char(string="素材名称", required=True)
    asset_uuid = fields.Char(string="素材ID", required=True, index=True, readonly=True)
    worker_id = fields.Char(string="本地工作节点", required=True, index=True, readonly=True)
    active = fields.Boolean(default=True)
    asset_kind = fields.Selection([
        ("standard_shot", "标准分镜"), ("voice_variant", "配音分镜"),
        ("heygen_variant", "HeyGen分镜"), ("music", "背景音乐"),
    ], string="素材类型", default="standard_shot", required=True)
    clip_type = fields.Selection([
        ("talking_face", "口播人脸"), ("face_no_speech", "非口播人脸"),
        ("no_face", "无人脸"), ("unknown", "未分类"),
    ], string="画面类型", default="unknown")
    business_role_id = fields.Many2one("psc.business.role", string="经营角色", ondelete="set null")
    track_id = fields.Many2one("psc.industry.track", string="项目赛道", ondelete="set null")
    scope_id = fields.Many2one("psc.content.scope", string="内容场景", ondelete="set null")
    shot_purpose = fields.Char(string="分镜用途")
    duration = fields.Float(string="时长（秒）")
    aspect_ratio = fields.Char(string="画幅")
    language = fields.Char(string="语言")
    subtitle_state = fields.Selection([
        ("clean", "无硬字幕"), ("cleaned", "已清理"),
        ("present", "保留硬字幕"), ("unknown", "未确认"),
    ], string="字幕状态", default="unknown")
    voice_signature = fields.Char(string="音色版本")
    copyright_status = fields.Char(string="版权状态")
    local_relative_path = fields.Char(string="本地文件标识", readonly=True)
    file_size = fields.Integer(string="文件大小", readonly=True)
    content_hash = fields.Char(string="文件校验值", readonly=True)
    metadata = fields.Json(string="其他本地元数据", readonly=True)
    last_seen_at = fields.Datetime(string="最近同步", readonly=True)

    _asset_worker_unique = models.Constraint(
        "UNIQUE(asset_uuid, worker_id)", "同一工作节点中的素材ID不能重复。",
    )
