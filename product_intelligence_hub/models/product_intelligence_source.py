import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class ProductIntelligenceSource(models.Model):
    _name = "product.intelligence.source"
    _description = "产品智能数据来源"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name"

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    source_type = fields.Selection(
        [
            ("manual", "手工录入"),
            ("supplier", "供应商"),
            ("marketplace", "电商平台"),
            ("search", "搜索趋势"),
            ("social", "社交媒体"),
            ("api", "自定义 API"),
        ],
        required=True,
        default="manual",
        tracking=True,
    )
    base_url = fields.Char()
    credential_parameter = fields.Char(
        help="Technical key in Odoo System Parameters containing the credential. "
        "Secrets must not be stored on this record."
    )
    sync_interval = fields.Selection(
        [("manual", "手动"), ("daily", "每天"), ("weekly", "每周")],
        default="manual",
        required=True,
    )
    status = fields.Selection(
        [("draft", "未测试"), ("connected", "已连接"), ("error", "错误")],
        default="draft",
        readonly=True,
        tracking=True,
    )
    last_sync_at = fields.Datetime(readonly=True)
    last_sync_message = fields.Text(readonly=True)
    candidate_count = fields.Integer(compute="_compute_candidate_count")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    notes = fields.Html()

    @api.depends("company_id")
    def _compute_candidate_count(self):
        grouped = self.env["product.intelligence.candidate"]._read_group(
            [("source_id", "in", self.ids)], ["source_id"], ["__count"]
        )
        counts = {source.id: count for source, count in grouped}
        for record in self:
            record.candidate_count = counts.get(record.id, 0)

    def _fetch_candidates(self):
        """Connector extension point.

        Connector modules should return a list of dictionaries accepted by
        ``product.intelligence.candidate.create``. The base module deliberately
        performs no web scraping.
        """
        self.ensure_one()
        if self.source_type == "manual":
            return []
        raise UserError(
            _("数据来源“%s”尚未安装连接器。") % self.display_name
        )

    def action_sync(self):
        Candidate = self.env["product.intelligence.candidate"]
        for source in self:
            try:
                values_list = source._fetch_candidates()
                for values in values_list:
                    values.setdefault("source_id", source.id)
                    values.setdefault("company_id", source.company_id.id)
                if values_list:
                    Candidate.create(values_list)
                source.write(
                    {
                        "status": "connected",
                        "last_sync_at": fields.Datetime.now(),
                        "last_sync_message": _("已导入 %s 个候选产品。")
                        % len(values_list),
                    }
                )
            except Exception as exc:
                source.write(
                    {
                        "status": "error",
                        "last_sync_at": fields.Datetime.now(),
                        "last_sync_message": str(exc),
                    }
                )
                _logger.exception("Product intelligence source sync failed: %s", source.name)
                if not self.env.context.get("cron_run"):
                    raise
        return True

    @api.model
    def _cron_sync_sources(self):
        sources = self.search(
            [("active", "=", True), ("sync_interval", "!=", "manual")]
        )
        sources.with_context(cron_run=True).action_sync()

    def action_view_candidates(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "product_intelligence_hub.action_product_intelligence_candidate"
        )
        action["domain"] = [("source_id", "=", self.id)]
        action["context"] = {"default_source_id": self.id}
        return action
