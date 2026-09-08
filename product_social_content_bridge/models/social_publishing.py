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


class SocialAccountSlot(models.Model):
    _name = "psc.social.account.slot"
    _description = "社媒账号槽位"
    _order = "worker_node_id, bitbrowser_environment_id, channel_id"

    name = fields.Char(string="槽位名称", required=True)
    product_line_id = fields.Many2one("psc.product.line", string="品牌/产品线")
    channel_id = fields.Many2one("psc.publishing.channel", string="发布渠道", required=True)
    platform = fields.Selection(related="channel_id.platform", string="平台", store=True, readonly=True)
    target_market_id = fields.Many2one("psc.target.market", string="目标市场", required=True)
    worker_node_id = fields.Many2one("psc.local.worker.node", string="Windows 工作节点", required=True)
    bitbrowser_environment_id = fields.Many2one(
        "psc.bitbrowser.environment", string="比特环境", required=True,
        domain="[('worker_node_id', '=', worker_node_id), ('available', '=', True)]",
    )
    expected_ip = fields.Char(string="预期固定 IP", required=True)
    expected_country_id = fields.Many2one("res.country", string="预期国家/地区", required=True)
    expected_timezone = fields.Char(string="预期时区", required=True)
    state = fields.Selection([
        ("active", "正常"), ("replacing", "替换中"), ("suspended", "暂停"),
    ], string="槽位状态", default="active", required=True)
    current_account_id = fields.Many2one(
        "psc.social.publishing.account", string="当前可发布账号", readonly=True,
    )
    account_ids = fields.One2many("psc.social.publishing.account", "slot_id", string="账号历史")

    _environment_channel_unique = models.Constraint(
        "UNIQUE(bitbrowser_environment_id, channel_id)",
        "同一比特环境的同一发布渠道只能有一个账号槽位。",
    )

    @api.constrains("worker_node_id", "bitbrowser_environment_id")
    def _check_environment_worker(self):
        for slot in self:
            if slot.bitbrowser_environment_id.worker_node_id != slot.worker_node_id:
                raise ValidationError(_("比特环境不属于所选 Windows 工作节点。"))


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
    platform_account_id = fields.Char(string="平台账号 ID")
    email_asset_id = fields.Many2one("psc.email.asset", string="注册邮箱", ondelete="restrict")
    registration_task_id = fields.Many2one("psc.social.registration.task", string="注册任务", readonly=True)
    slot_id = fields.Many2one("psc.social.account.slot", string="账号槽位", ondelete="restrict", index=True)
    replaces_account_id = fields.Many2one(
        "psc.social.publishing.account", string="替换的旧账号", readonly=True,
    )
    replaced_by_account_id = fields.Many2one(
        "psc.social.publishing.account", string="替换后的新账号", readonly=True,
    )
    unavailable_reason = fields.Text(string="不可用/替换原因")
    unavailable_at = fields.Datetime(string="标记不可用时间", readonly=True)
    replaced_at = fields.Datetime(string="替换完成时间", readonly=True)
    account_state = fields.Selection([
        ("pending", "待校验"), ("available", "可发布"),
        ("unavailable", "不可用"), ("replacement_pending", "待替换"),
        ("replaced", "已替换"), ("suspended", "暂停发布"),
    ], string="账号状态", required=True, default="pending")
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
    expected_timezone = fields.Char(string="预期时区", required=True, default="UTC")
    daily_publish_limit = fields.Integer(string="每日发布上限", default=3, required=True)
    last_validation_at = fields.Datetime(string="最后校验时间", readonly=True)
    last_validation_state = fields.Selection([
        ("untested", "未校验"), ("passed", "通过"), ("failed", "失败"),
    ], string="连接校验", default="untested", required=True, readonly=True)
    last_validation_message = fields.Text(string="校验结果", readonly=True)

    _environment_unique = models.Constraint(
        "UNIQUE(bitbrowser_environment_id, channel_id, platform_account_id)",
        "同一环境和渠道下的平台账号 ID 不能重复。",
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

    def _ensure_slot(self):
        self.ensure_one()
        slot_model = self.env["psc.social.account.slot"]
        slot = self.slot_id or slot_model.search([
            ("bitbrowser_environment_id", "=", self.bitbrowser_environment_id.id),
            ("channel_id", "=", self.channel_id.id),
        ], limit=1)
        values = {
            "name": "%s · %s" % (self.bitbrowser_environment_id.name, self.channel_id.name),
            "product_line_id": self.product_line_id.id,
            "channel_id": self.channel_id.id,
            "target_market_id": self.target_market_id.id,
            "worker_node_id": self.worker_node_id.id,
            "bitbrowser_environment_id": self.bitbrowser_environment_id.id,
            "expected_ip": self.expected_ip,
            "expected_country_id": self.expected_country_id.id,
            "expected_timezone": self.expected_timezone,
        }
        if not slot:
            slot = slot_model.create(values)
        if not self.slot_id:
            self.slot_id = slot
        if not slot.current_account_id and self.account_state == "available":
            slot.current_account_id = self
        return slot

    def action_mark_unavailable(self):
        for account in self:
            if account.account_state != "available":
                raise ValidationError(_("只有可发布账号可以标记为不可用。"))
            if not (account.unavailable_reason or "").strip():
                raise ValidationError(_("请先填写“不可用/替换原因”。"))
            slot = account._ensure_slot()
            account.write({"account_state": "unavailable", "unavailable_at": fields.Datetime.now()})
            if slot.current_account_id == account:
                slot.write({"current_account_id": False, "state": "suspended"})
        return True

    def action_create_replacement(self):
        self.ensure_one()
        if self.account_state not in ("available", "unavailable", "replacement_pending"):
            raise ValidationError(_("当前账号状态不能创建替换任务。"))
        if not (self.unavailable_reason or "").strip():
            raise ValidationError(_("请先填写“不可用/替换原因”。"))
        slot = self._ensure_slot()
        if slot.current_account_id and slot.current_account_id != self:
            raise ValidationError(_("该槽位已经切换到其他账号，不能再次替换此历史账号。"))
        active_task = self.env["psc.social.registration.task"].search([
            ("replacement_account_id", "=", self.id),
            ("state", "in", ("draft", "ready", "environment_check", "awaiting_verification")),
        ], limit=1)
        if active_task:
            task = active_task
        else:
            task = self.env["psc.social.registration.task"].create({
                "name": _("替换 %s") % self.display_name,
                "task_mode": "replace", "slot_id": slot.id,
                "cluster_id": self.cluster_id.id,
                "replacement_account_id": self.id,
                "channel_id": self.channel_id.id,
                "worker_node_id": self.worker_node_id.id,
                "bitbrowser_environment_id": self.bitbrowser_environment_id.id,
                "expected_ip": self.expected_ip,
                "expected_country_id": self.expected_country_id.id,
                "expected_timezone": self.expected_timezone,
                "display_name": self.name,
            })
        self.write({
            "account_state": "replacement_pending",
            "unavailable_at": self.unavailable_at or fields.Datetime.now(),
        })
        slot.write({"state": "replacing", "current_account_id": False})
        return {
            "type": "ir.actions.act_window", "name": _("替换社媒账号"),
            "res_model": "psc.social.registration.task", "res_id": task.id,
            "view_mode": "form", "target": "current",
        }

    def action_suspend(self):
        for account in self:
            account.account_state = "suspended"
            slot = account._ensure_slot()
            if slot.current_account_id == account:
                slot.state = "suspended"
        return True

    def action_restore_available(self):
        for account in self:
            if account.account_state not in ("unavailable", "suspended"):
                raise ValidationError(_("只有不可用或暂停发布的账号可以恢复。"))
            slot = account._ensure_slot()
            if slot.current_account_id and slot.current_account_id != account:
                raise ValidationError(_("该槽位已有其他可发布账号，不能恢复此账号。"))
            account.account_state = "available"
            slot.write({"current_account_id": account.id, "state": "active"})
        return True

    def action_open_account_history(self):
        self.ensure_one()
        slot = self._ensure_slot()
        return {
            "type": "ir.actions.act_window", "name": _("账号替换历史"),
            "res_model": "psc.social.publishing.account", "view_mode": "list,form",
            "domain": [("slot_id", "=", slot.id)], "context": {"active_test": False},
        }
