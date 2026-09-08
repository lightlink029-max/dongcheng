from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PublishingDestination(models.Model):
    _name = "psc.publishing.destination"
    _description = "内容发布目标"
    _order = "destination_type, name"

    name = fields.Char(string="发布目标", required=True)
    active = fields.Boolean(default=True)
    destination_type = fields.Selection([
        ("website", "Odoo 网站"),
        ("social", "社媒账号"),
        ("alibaba", "阿里国际站店铺"),
    ], string="目标类型", required=True, default="social")
    product_line_id = fields.Many2one("psc.product.line", string="品牌/产品线", required=True)
    market_id = fields.Many2one("psc.target.market", string="目标市场", required=True)
    channel_id = fields.Many2one("psc.publishing.channel", string="内容渠道", required=True)
    website_id = fields.Many2one("website", string="Odoo 网站")
    publishing_account_id = fields.Many2one(
        "psc.social.publishing.account",
        string="发布账号",
        domain="[('channel_id', '=', channel_id), ('target_market_id', '=', market_id), ('account_state', '=', 'available')]",
    )
    store_name = fields.Char(string="阿里国际站店铺名称")
    store_id = fields.Char(string="阿里国际站店铺 ID")
    store_url = fields.Char(string="店铺主页")
    notes = fields.Text(string="发布说明")
    state = fields.Selection([
        ("draft", "待配置"),
        ("ready", "可发布"),
        ("paused", "暂停"),
    ], string="目标状态", default="draft", required=True)
    publication_task_ids = fields.One2many(
        "psc.publication.task", "destination_id", string="发布任务",
    )

    @api.onchange("publishing_account_id")
    def _onchange_publishing_account(self):
        if self.publishing_account_id:
            self.product_line_id = self.publishing_account_id.product_line_id
            self.market_id = self.publishing_account_id.target_market_id
            self.channel_id = self.publishing_account_id.channel_id

    @api.constrains(
        "destination_type", "channel_id", "website_id", "publishing_account_id",
        "store_name", "product_line_id", "market_id",
    )
    def _check_configuration(self):
        for destination in self:
            if destination.destination_type == "website":
                if destination.channel_id.platform != "website" or not destination.website_id:
                    raise ValidationError(_("网站发布目标必须选择 Odoo 网站和网站类型的内容渠道。"))
            elif destination.destination_type == "social":
                if destination.channel_id.platform in ("website", "alibaba"):
                    raise ValidationError(_("社媒发布目标不能使用网站或阿里国际站渠道。"))
                if not destination.publishing_account_id:
                    raise ValidationError(_("社媒发布目标必须选择一个可发布账号。"))
            elif destination.destination_type == "alibaba":
                if destination.channel_id.platform != "alibaba" or not destination.store_name:
                    raise ValidationError(_("阿里国际站发布目标必须填写店铺名称并选择阿里国际站渠道。"))
                if not destination.publishing_account_id:
                    raise ValidationError(_("阿里国际站发布目标必须绑定本地发布账号和比特环境。"))

            account = destination.publishing_account_id
            if account and (
                account.channel_id != destination.channel_id
                or account.target_market_id != destination.market_id
                or (account.product_line_id and account.product_line_id != destination.product_line_id)
            ):
                raise ValidationError(_("发布账号与发布目标的产品线、市场或渠道不一致。"))

    def action_mark_ready(self):
        for destination in self:
            destination._check_configuration()
            if destination.publishing_account_id and destination.publishing_account_id.account_state != "available":
                raise UserError(_("绑定账号当前不可发布，请先恢复账号或更换账号。"))
            destination.state = "ready"
        return True

    def action_pause(self):
        self.write({"state": "paused"})
        return True


class PublicationTask(models.Model):
    _name = "psc.publication.task"
    _description = "内容发布任务"
    _order = "scheduled_at, id"

    name = fields.Char(string="发布任务", required=True)
    content_id = fields.Many2one(
        "psc.content.variant", string="渠道内容", required=True, ondelete="cascade", index=True,
    )
    project_id = fields.Many2one(
        "psc.publishing.project", string="发布项目", required=True,
        ondelete="cascade", readonly=True, index=True,
    )
    product_id = fields.Many2one(related="content_id.product_id", string="产品", store=True, readonly=True)
    market_id = fields.Many2one(related="content_id.market_id", string="目标市场", store=True, readonly=True)
    channel_id = fields.Many2one(related="content_id.channel_id", string="内容渠道", store=True, readonly=True)
    destination_id = fields.Many2one(
        "psc.publishing.destination", string="发布目标", required=True, ondelete="restrict", index=True,
    )
    destination_type = fields.Selection(
        related="destination_id.destination_type", string="目标类型", store=True, readonly=True,
    )
    publishing_account_id = fields.Many2one(
        related="destination_id.publishing_account_id", string="发布账号", store=True, readonly=True,
    )
    worker_node_id = fields.Many2one(
        related="publishing_account_id.worker_node_id", string="Windows 工作节点", store=True, readonly=True,
    )
    bitbrowser_environment_id = fields.Many2one(
        related="publishing_account_id.bitbrowser_environment_id", string="比特环境", store=True, readonly=True,
    )
    scheduled_at = fields.Datetime(string="计划发布时间")
    state = fields.Selection([
        ("draft", "草稿"), ("queued", "待发布"), ("validating", "环境检查"),
        ("publishing", "发布中"), ("published", "已发布"),
        ("failed", "失败"), ("cancelled", "已取消"),
    ], string="任务状态", default="draft", required=True, index=True)
    worker_id = fields.Char(string="执行工作节点", readonly=True)
    attempt_count = fields.Integer(string="尝试次数", readonly=True)
    status_message = fields.Char(string="状态说明", readonly=True)
    error_message = fields.Text(string="失败原因", readonly=True)
    actual_ip = fields.Char(string="实际出口 IP", readonly=True)
    published_url = fields.Char(string="发布链接", readonly=True)
    screenshot_attachment_id = fields.Many2one("ir.attachment", string="结果截图", readonly=True)
    started_at = fields.Datetime(string="开始时间", readonly=True)
    finished_at = fields.Datetime(string="完成时间", readonly=True)

    _content_destination_unique = models.Constraint(
        "UNIQUE(content_id, destination_id)",
        "同一份渠道内容不能向同一个发布目标重复创建任务。",
    )

    def _sync_project_state(self):
        for project in self.mapped("project_id"):
            states = set(project.publication_task_ids.mapped("state"))
            if states and states <= {"published"}:
                project.state = "published"
            elif "failed" in states:
                project.state = "failed"
            elif states & {"queued", "validating", "publishing"}:
                project.state = "publishing"
            else:
                project.state = "ready"

    def _sync_content_state(self):
        for content in self.mapped("content_id"):
            states = set(content.publication_task_ids.mapped("state"))
            if states and states <= {"published"}:
                content.state = "published"
            elif "failed" in states:
                content.state = "failed"
            else:
                content.state = "ready"

    def action_publish_website(self):
        for task in self:
            if task.destination_type != "website":
                raise UserError(_("只有 Odoo 网站任务可以使用此操作。"))
            if task.destination_id.state != "ready" or not task.destination_id.website_id:
                raise UserError(_("网站发布目标尚未配置完成。"))
            content = task.content_id
            if content.ai_state != "done":
                raise UserError(_("请先生成并审核渠道内容。"))
            product = content.product_id.with_context(lang=content.language_id.code)
            product.write({
                "description_ecommerce": content.caption or product.description_ecommerce,
                "website_meta_title": content.title or product.name,
                "website_meta_description": (content.caption or "")[:160],
                "website_id": task.destination_id.website_id.id,
                "is_published": True,
            })
            website = task.destination_id.website_id
            base_url = (
                website.domain
                or self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
            ).rstrip("/")
            published_url = "%s%s" % (base_url, product.website_url)
            task.write({
                "state": "published", "published_url": published_url,
                "status_message": _("已发布到 Odoo 网站"),
                "started_at": task.started_at or fields.Datetime.now(),
                "finished_at": fields.Datetime.now(), "error_message": False,
            })
            content.published_url = published_url
        self._sync_content_state()
        self._sync_project_state()
        return True

    def action_queue(self):
        for task in self:
            if task.destination_id.state != "ready":
                raise UserError(_("发布目标尚未配置为可发布。"))
            if task.destination_type == "website":
                task.action_publish_website()
                continue
            if task.destination_type in ("social", "alibaba"):
                account = task.publishing_account_id
                if not account or account.account_state != "available":
                    raise UserError(_("发布账号当前不可用，请先更换或恢复账号。"))
                if account.last_validation_state != "passed":
                    raise UserError(_("发布账号尚未通过环境校验。"))
            if not task.content_id.image_attachment_id and not task.content_id.video_attachment_id:
                raise UserError(_("渠道内容没有可发布的图片或视频。"))
            task.write({
                "state": "queued", "status_message": _("等待发布执行"),
                "error_message": False, "worker_id": False,
                "started_at": False, "finished_at": False,
            })
        self._sync_project_state()
        self._sync_content_state()
        return True

    def action_retry(self):
        self.filtered(lambda task: task.state in ("failed", "cancelled")).action_queue()
        return True

    def action_cancel(self):
        self.filtered(lambda task: task.state in ("draft", "queued")).write({
            "state": "cancelled", "status_message": _("已人工取消"),
        })
        self._sync_content_state()
        self._sync_project_state()
        return True
