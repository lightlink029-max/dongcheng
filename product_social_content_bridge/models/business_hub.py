from odoo import api, fields, models


class BusinessHub(models.Model):
    _name = "psc.business.hub"
    _description = "LightLink 业务中心"

    name = fields.Char(required=True, default="LightLink 业务中心")
    today_task_count = fields.Integer(compute="_compute_metrics")
    overdue_task_count = fields.Integer(compute="_compute_metrics")
    waiting_approval_count = fields.Integer(compute="_compute_metrics")
    failed_publication_count = fields.Integer(compute="_compute_metrics")
    active_project_count = fields.Integer(compute="_compute_metrics")
    lead_followup_count = fields.Integer(compute="_compute_metrics")
    open_sale_count = fields.Integer(compute="_compute_metrics")
    open_purchase_count = fields.Integer(compute="_compute_metrics")
    pending_delivery_count = fields.Integer(compute="_compute_metrics")
    unpaid_invoice_count = fields.Integer(compute="_compute_metrics")

    @api.depends_context("uid", "company")
    def _compute_metrics(self):
        today = fields.Date.context_today(self)
        values = {
            "today_task_count": self.env["psc.project.readiness.item"].search_count([
                ("owner_id", "=", self.env.user.id),
                ("state", "!=", "done"),
                ("due_date", "<=", today),
            ]),
            "overdue_task_count": self.env["psc.project.readiness.item"].search_count([
                ("owner_id", "=", self.env.user.id),
                ("state", "!=", "done"),
                ("due_date", "<", today),
            ]),
            "waiting_approval_count": self.env["psc.ai.action"].search_count([
                ("state", "=", "waiting_approval"),
            ]),
            "failed_publication_count": self.env["psc.publication.task"].search_count([
                ("state", "=", "failed"),
            ]),
            "active_project_count": self.env["psc.publishing.project"].search_count([
                ("operation_state", "=", "active"),
            ]),
            "lead_followup_count": self.env["crm.lead"].search_count([
                ("active", "=", True),
                ("activity_state", "in", ("today", "overdue")),
            ]),
            "open_sale_count": self.env["sale.order"].search_count([
                ("state", "=", "sale"),
            ]),
            "open_purchase_count": self.env["purchase.order"].search_count([
                ("state", "in", ("draft", "sent", "to approve", "purchase")),
            ]),
            "pending_delivery_count": self.env["stock.picking"].search_count([
                ("state", "not in", ("done", "cancel")),
            ]),
            "unpaid_invoice_count": self.env["account.move"].search_count([
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "in", ("not_paid", "partial", "in_payment")),
            ]),
        }
        for hub in self:
            for field_name, value in values.items():
                hub[field_name] = value

    def _open_action(self, xmlid, *, domain=None, context=None):
        action = self.env["ir.actions.actions"]._for_xml_id(xmlid)
        if domain is not None:
            action["domain"] = domain
        if context is not None:
            action["context"] = context
        return action

    def action_refresh(self):
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_open_today(self):
        return self._open_action(
            "product_social_content_bridge.action_psc_project_readiness_items",
            domain=[("owner_id", "=", self.env.user.id), ("state", "!=", "done")],
            context={"search_default_my_work": 1},
        )

    def action_open_ai(self):
        return self._open_action("product_social_content_bridge.action_psc_ai_cockpit")

    def action_open_publication_failures(self):
        return self._open_action(
            "product_social_content_bridge.action_psc_publication_tasks",
            domain=[("state", "=", "failed")],
        )

    def action_open_projects(self):
        return self._open_action("product_social_content_bridge.action_psc_project")

    def action_open_content(self):
        return self._open_action("product_social_content_bridge.action_psc_content_plans")

    def action_open_assets(self):
        return self._open_action("product_social_content_bridge.action_psc_media_asset")

    def action_open_crm(self):
        return self._open_action("crm.crm_lead_action_pipeline")

    def action_open_contacts(self):
        return self._open_action("contacts.action_contacts")

    def action_open_sales(self):
        return self._open_action("sale.action_orders")

    def action_open_purchase(self):
        return self._open_action("purchase.purchase_rfq")

    def action_open_inventory(self):
        return self._open_action("stock.action_picking_tree_all")

    def action_open_invoices(self):
        return self._open_action("account.action_move_out_invoice_type")

    def action_open_performance(self):
        return self._open_action("product_social_content_bridge.action_psc_performance_snapshots")

    def action_open_calendar(self):
        return self._open_action("calendar.action_calendar_event")

    def action_open_resources(self):
        return self._open_action("product_social_content_bridge.action_psc_social_account_clusters")

    def action_open_settings(self):
        return self._open_action("product_social_content_bridge.action_psc_local_worker_settings")
