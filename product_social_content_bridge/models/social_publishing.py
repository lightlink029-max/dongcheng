from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LocalWorkerNode(models.Model):
    _name = "psc.local.worker.node"
    _description = "Windows 本地工作节点"
    _order = "name"

    name = fields.Char(string="工作节点名称", required=True, index=True)
    active = fields.Boolean(default=True)
    last_seen_at = fields.Datetime(string="最后连接时间", readonly=True)
    bitbrowser_environment_ids = fields.One2many(
        "psc.bitbrowser.environment", "worker_node_id", string="比特环境",
    )

    _name_unique = models.Constraint("UNIQUE(name)", "工作节点名称不能重复。")


class BitBrowserEnvironment(models.Model):
    _name = "psc.bitbrowser.environment"
    _description = "比特浏览器环境"
    _order = "worker_node_id, sequence, name"

    name = fields.Char(string="环境名称", required=True)
    environment_id = fields.Char(string="环境 ID", required=True, index=True, readonly=True)
    sequence = fields.Integer(string="序号", readonly=True)
    worker_node_id = fields.Many2one(
        "psc.local.worker.node", string="工作节点", required=True,
        ondelete="cascade", index=True, readonly=True,
    )
    platform = fields.Char(string="平台", readonly=True)
    username = fields.Char(string="账号", readonly=True)
    state = fields.Selection([
        ("open", "已启动"), ("closed", "已关闭"), ("unknown", "未知"),
    ], string="状态", default="unknown", required=True, readonly=True)
    available = fields.Boolean(string="可用", default=True, readonly=True)
    last_synced_at = fields.Datetime(string="最后同步时间", readonly=True)

    _environment_unique = models.Constraint("UNIQUE(environment_id)", "比特环境 ID 不能重复。")


class SocialPublishingAccount(models.Model):
    _name = "psc.social.publishing.account"
    _description = "本地自动发布社媒账号"
    _order = "channel_id, name"

    name = fields.Char(string="账号名称", required=True)
    active = fields.Boolean(default=True)
    product_line_id = fields.Many2one("psc.product.line", string="品牌/产品线")
    channel_id = fields.Many2one("psc.publishing.channel", string="发布渠道", required=True)
    platform = fields.Selection(related="channel_id.platform", string="平台", store=True, readonly=True)
    target_market_id = fields.Many2one("psc.target.market", string="目标市场", required=True)
    username = fields.Char(string="平台用户名", required=True)
    profile_url = fields.Char(string="账号主页")
    worker_node_id = fields.Many2one("psc.local.worker.node", string="Windows 工作节点", required=True)
    bitbrowser_environment_id = fields.Many2one(
        "psc.bitbrowser.environment", string="比特环境", required=True,
        domain="[('worker_node_id', '=', worker_node_id), ('available', '=', True)]",
    )
    bitbrowser_id = fields.Char(
        related="bitbrowser_environment_id.environment_id", string="比特环境 ID",
        store=True, readonly=True,
    )
    expected_ip = fields.Char(string="预期固定 IP", required=True)
    expected_country_id = fields.Many2one("res.country", string="预期 IP 国家/地区", required=True)
    daily_publish_limit = fields.Integer(string="每日发布上限", default=3, required=True)
    last_validation_at = fields.Datetime(string="最后校验时间", readonly=True)
    last_validation_state = fields.Selection([
        ("untested", "未校验"), ("passed", "通过"), ("failed", "失败"),
    ], string="连接校验", default="untested", required=True, readonly=True)
    last_validation_message = fields.Text(string="校验结果", readonly=True)

    _environment_unique = models.Constraint(
        "UNIQUE(bitbrowser_environment_id)", "一个比特环境只能绑定一个社媒账号。",
    )

    @api.onchange("target_market_id")
    def _onchange_target_market(self):
        if self.target_market_id:
            self.expected_country_id = self.target_market_id.country_id

    @api.onchange("worker_node_id")
    def _onchange_worker_node(self):
        if self.bitbrowser_environment_id.worker_node_id != self.worker_node_id:
            self.bitbrowser_environment_id = False

    @api.constrains("daily_publish_limit")
    def _check_daily_publish_limit(self):
        for account in self:
            if account.daily_publish_limit < 1:
                raise ValidationError(_("每日发布上限必须大于 0。"))

    @api.constrains("worker_node_id", "bitbrowser_environment_id")
    def _check_environment_worker(self):
        for account in self:
            environment = account.bitbrowser_environment_id
            if environment and environment.worker_node_id != account.worker_node_id:
                raise ValidationError(_("比特环境不属于所选 Windows 工作节点。"))
