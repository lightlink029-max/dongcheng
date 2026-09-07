from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EmailAsset(models.Model):
    _name = "psc.email.asset"
    _description = "社媒注册邮箱资产"
    _order = "email"

    email = fields.Char(string="邮箱地址", required=True, index=True)
    provider = fields.Selection([
        ("gmail", "Gmail"), ("outlook", "Outlook/Hotmail"),
        ("enterprise", "企业邮箱"), ("other", "其他"),
    ], string="邮箱类型/服务商", required=True, default="gmail")
    product_line_id = fields.Many2one("psc.product.line", string="品牌/产品线", required=True)
    target_market_id = fields.Many2one("psc.target.market", string="目标市场", required=True)
    user_id = fields.Many2one("res.users", string="负责人", required=True, default=lambda self: self.env.user)
    recovery_email_configured = fields.Boolean(string="已设置恢复邮箱")
    recovery_phone_configured = fields.Boolean(string="已设置恢复手机")
    two_factor_state = fields.Selection([
        ("disabled", "未开启"), ("enabled", "已开启"), ("unknown", "未确认"),
    ], string="2FA 状态", required=True, default="unknown")
    notes = fields.Text(string="备注", help="不得填写密码、Cookie、手机号或 2FA 密钥。")
    active = fields.Boolean(default=True)
    registration_task_ids = fields.One2many("psc.social.registration.task", "email_asset_id", string="注册任务")

    _email_unique = models.Constraint("UNIQUE(email)", "邮箱地址不能重复。")


class SocialRegistrationTask(models.Model):
    _name = "psc.social.registration.task"
    _description = "社媒账号注册任务"
    _order = "create_date desc, id desc"

    name = fields.Char(string="任务名称", required=True, default=lambda self: _("社媒账号注册"))
    task_mode = fields.Selection([
        ("new", "新注册"), ("replace", "替换账号"),
    ], string="任务类型", required=True, default="new")
    email_asset_id = fields.Many2one("psc.email.asset", string="注册邮箱", ondelete="restrict")
    slot_id = fields.Many2one("psc.social.account.slot", string="账号槽位", readonly=True, ondelete="restrict")
    replacement_account_id = fields.Many2one(
        "psc.social.publishing.account", string="待替换账号", readonly=True, ondelete="restrict",
    )
    channel_id = fields.Many2one("psc.publishing.channel", string="平台/渠道", required=True)
    platform = fields.Selection(related="channel_id.platform", store=True, readonly=True)
    product_line_id = fields.Many2one(related="email_asset_id.product_line_id", store=True, readonly=True)
    target_market_id = fields.Many2one(related="email_asset_id.target_market_id", store=True, readonly=True)
    worker_node_id = fields.Many2one("psc.local.worker.node", string="Windows 工作节点", required=True)
    bitbrowser_environment_id = fields.Many2one(
        "psc.bitbrowser.environment", string="比特环境", required=True,
        domain="[('worker_node_id', '=', worker_node_id), ('available', '=', True)]",
    )
    expected_ip = fields.Char(string="预期固定 IP", required=True)
    expected_country_id = fields.Many2one("res.country", string="预期国家/地区", required=True)
    expected_timezone = fields.Char(string="预期时区", required=True, help="例如 America/New_York")
    display_name = fields.Char(string="显示名称")
    desired_username = fields.Char(string="期望用户名")
    state = fields.Selection([
        ("draft", "草稿"), ("ready", "待执行"), ("environment_check", "环境检查"),
        ("awaiting_verification", "等待人工验证"), ("done", "已完成"),
        ("failed", "失败"), ("environment_mismatch", "IP/环境不匹配"),
    ], default="draft", required=True, index=True)
    worker_id = fields.Char(string="执行工作节点", readonly=True)
    actual_ip = fields.Char(string="实际 IP", readonly=True)
    actual_country_code = fields.Char(string="实际国家代码", readonly=True)
    actual_timezone = fields.Char(string="实际时区", readonly=True)
    platform_account_id = fields.Char(string="平台账号 ID", readonly=True)
    registered_username = fields.Char(string="实际用户名", readonly=True)
    profile_url = fields.Char(string="账号主页", readonly=True)
    screenshot_attachment_id = fields.Many2one("ir.attachment", string="结果截图", readonly=True)
    social_account_id = fields.Many2one("psc.social.publishing.account", string="社媒账号", readonly=True)
    status_message = fields.Char(string="状态说明", readonly=True)
    error_message = fields.Text(string="失败原因", readonly=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)

    @api.onchange("email_asset_id")
    def _onchange_email_asset(self):
        if self.email_asset_id:
            self.expected_country_id = self.email_asset_id.target_market_id.country_id

    @api.onchange("worker_node_id")
    def _onchange_worker_node(self):
        if self.bitbrowser_environment_id.worker_node_id != self.worker_node_id:
            self.bitbrowser_environment_id = False

    def action_submit(self):
        for task in self:
            if not task.email_asset_id:
                raise UserError(_("请先选择新账号使用的邮箱资产。"))
            if task.task_mode == "replace" and (not task.replacement_account_id or not task.slot_id):
                raise UserError(_("替换任务必须从原社媒账号的“替换账号”按钮创建。"))
            if task.task_mode == "replace" and task.email_asset_id == task.replacement_account_id.email_asset_id:
                raise UserError(_("替换账号必须选择与旧账号不同的邮箱资产。"))
            if task.task_mode == "replace" and (
                task.email_asset_id.product_line_id != task.slot_id.product_line_id
                or task.email_asset_id.target_market_id != task.slot_id.target_market_id
            ):
                raise UserError(_("新邮箱资产必须与账号槽位属于同一品牌/产品线和目标市场。"))
            if task.platform not in ("facebook", "instagram", "tiktok", "linkedin"):
                raise UserError(_("第一期只支持 Facebook、Instagram、TikTok 和 LinkedIn 注册。"))
            if task.bitbrowser_environment_id.worker_node_id != task.worker_node_id:
                raise UserError(_("比特环境不属于所选 Windows 工作节点。"))
            if not task.bitbrowser_environment_id.available:
                raise UserError(_("所选比特环境当前不可用，请先在 Windows 工具同步环境。"))
            task.write({"state": "ready", "error_message": False, "status_message": "等待 Windows 工具处理"})
        return True

    def action_retry(self):
        self.write({
            "state": "ready", "worker_id": False, "actual_ip": False,
            "actual_country_code": False, "actual_timezone": False,
            "error_message": False, "status_message": "等待 Windows 工具重试",
            "started_at": False, "finished_at": False,
        })
        return True
