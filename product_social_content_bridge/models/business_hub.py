from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


NAVIGATION_CATEGORIES = (
    ("business", "业务中心", False, "fa-home"),
    ("web_marketing", "网站与营销", "product_social_content_bridge.menu_psc_category_web_marketing", "fa-globe"),
    ("customer", "客户管理", "product_social_content_bridge.menu_psc_category_customer", "fa-handshake-o"),
    ("supply_chain", "供应链管理", "product_social_content_bridge.menu_psc_category_supply_chain", "fa-cubes"),
    ("finance", "财务与数据", "product_social_content_bridge.menu_psc_category_finance", "fa-line-chart"),
    ("collaboration", "协同办公", "product_social_content_bridge.menu_psc_category_collaboration", "fa-comments-o"),
    ("system", "系统设置", "product_social_content_bridge.menu_psc_category_system", "fa-cogs"),
    ("other", "其他", "product_social_content_bridge.menu_psc_category_other", "fa-ellipsis-h"),
)


APP_MENU_GROUPS = {
    "product_social_content_bridge.menu_psc_category_web_marketing": (
        "website.menu_website_configuration",
        "social.menu_social_global",
        "mass_mailing.mass_mailing_menu_root",
        "utm.menu_link_tracker_root",
    ),
    "product_social_content_bridge.menu_psc_category_customer": (
        "contacts.menu_contacts",
        "crm.crm_menu_root",
        "helpdesk.menu_helpdesk_root",
        "im_livechat.menu_livechat_root",
        "whatsapp.whatsapp_menu_main",
        "appointment.main_menu_appointments",
    ),
    "product_social_content_bridge.menu_psc_category_supply_chain": (
        "product_intelligence_hub.menu_product_intelligence_root",
        "purchase.menu_purchase_root",
        "stock.menu_stock_root",
        "stock_barcode.stock_barcode_menu",
    ),
    "product_social_content_bridge.menu_psc_category_finance": (
        "account.menu_finance",
        "spreadsheet_dashboard.spreadsheet_dashboard_menu_root",
    ),
    "product_social_content_bridge.menu_psc_category_collaboration": (
        "mail.menu_root_discuss",
        "calendar.mail_menu_calendar",
        "hr.menu_hr_root",
        "hr_recruitment.menu_hr_recruitment_root",
    ),
    "product_social_content_bridge.menu_psc_category_system": (
        "base.menu_management",
        "base.menu_administration",
        "base.menu_tests",
    ),
}


class BusinessHub(models.Model):
    _name = "psc.business.hub"
    _description = "LightLink 业务中心"

    name = fields.Char(required=True, default="LightLink 业务中心")
    navigation_widget = fields.Char(default="ready")
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

    @api.model
    def organize_application_menus(self, force=False):
        """Group installed root apps without requiring optional apps as dependencies."""
        categories = self._category_records()
        category_ids = set(menu.id for menu in categories.values())
        default_menu_ids = set()
        for category_xmlid, app_xmlids in APP_MENU_GROUPS.items():
            category = self.env.ref(category_xmlid)
            for sequence, app_xmlid in enumerate(app_xmlids, start=1):
                app_menu = self.env.ref(app_xmlid, raise_if_not_found=False)
                if app_menu and app_menu != category:
                    default_menu_ids.add(app_menu.id)
                    if force or not app_menu.parent_id or app_menu.parent_id.id not in category_ids:
                        app_menu.write({
                            "parent_id": category.id,
                            "sequence": sequence * 10,
                        })
        if force:
            other = categories["other"]
            custom_menus = self.env["ir.ui.menu"].search([
                ("parent_id", "in", list(category_ids)),
                ("id", "not in", list(default_menu_ids)),
            ])
            for sequence, menu in enumerate(custom_menus, start=1):
                menu.write({"parent_id": other.id, "sequence": sequence * 10})
        self._ensure_dashboard_performance_menu()
        return True

    @api.model
    def _ensure_dashboard_performance_menu(self):
        """Expose the same operating data action inside the optional Dashboards app."""
        dashboard = self.env.ref(
            "spreadsheet_dashboard.spreadsheet_dashboard_menu_root",
            raise_if_not_found=False,
        )
        action = self.env.ref(
            "product_social_content_bridge.action_psc_performance_snapshots",
            raise_if_not_found=False,
        )
        if not dashboard or not action:
            return False

        menu = self.env.ref(
            "product_social_content_bridge.menu_psc_dashboard_performance",
            raise_if_not_found=False,
        )
        values = {
            "name": _("经营数据"),
            "parent_id": dashboard.id,
            "action": f"{action._name},{action.id}",
            "sequence": 90,
        }
        if menu:
            menu.write(values)
        else:
            menu = self.env["ir.ui.menu"].create(values)
            self.env["ir.model.data"].create({
                "module": "product_social_content_bridge",
                "name": "menu_psc_dashboard_performance",
                "model": "ir.ui.menu",
                "res_id": menu.id,
                "noupdate": False,
            })
        return menu

    @api.model
    def _category_records(self):
        return {
            code: self.env.ref(xmlid)
            for code, _name, xmlid, _icon in NAVIGATION_CATEGORIES
            if xmlid
        }

    @api.model
    def _movable_application_menus(self):
        categories = self._category_records()
        business_menu = self.env.ref("product_social_content_bridge.menu_psc_root")
        menus = self.env["ir.ui.menu"]
        for category in categories.values():
            menus |= category.child_id
        for app_xmlids in APP_MENU_GROUPS.values():
            for app_xmlid in app_xmlids:
                menu = self.env.ref(app_xmlid, raise_if_not_found=False)
                if menu:
                    menus |= menu
        excluded_ids = {business_menu.id, *(menu.id for menu in categories.values())}
        menus |= self.env["ir.ui.menu"].search([
            ("parent_id", "=", False),
            ("id", "not in", list(excluded_ids)),
        ])
        return menus.exists()

    @api.model
    def get_application_navigation(self):
        categories = self._category_records()
        business_menu = self.env.ref("product_social_content_bridge.menu_psc_root")
        workflow_menu = self.env.ref("product_social_content_bridge.menu_psc_workflow")
        performance_menu = self.env.ref("product_social_content_bridge.menu_psc_finance_performance")
        visible_ids = self.env["ir.ui.menu"]._visible_menu_ids()
        movable = self._movable_application_menus().filtered(
            lambda menu: menu.id in visible_ids
        )
        result = []
        for code, name, _xmlid, icon in NAVIGATION_CATEGORIES:
            item_icons = {}
            if code == "business":
                items = (business_menu | workflow_menu | performance_menu).filtered(
                    lambda menu: menu.id in visible_ids
                )
                item_icons = {
                    business_menu.id: "fa-home",
                    workflow_menu.id: "fa-briefcase",
                    performance_menu.id: "fa-line-chart",
                }
            elif code == "other":
                items = movable.filtered(
                    lambda menu: not menu.parent_id or menu.parent_id == categories[code]
                )
            else:
                items = movable.filtered(lambda menu: menu.parent_id == categories[code])
            items = items.sorted(key=lambda menu: (menu.sequence, menu.id))
            result.append({
                "code": code,
                "name": _(name),
                "icon": icon,
                "locked": code == "business",
                "items": [{
                    "id": menu.id,
                    "name": menu.name,
                    "web_icon": menu.web_icon or "",
                    "fallback_icon": item_icons.get(menu.id, "fa-cube"),
                    "locked": code == "business",
                } for menu in items],
            })
        return {
            "can_edit": self.env.user.has_group("base.group_system"),
            "categories": result,
        }

    @api.model
    def save_application_navigation(self, layout):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("只有系统管理员可以调整功能分类。"))
        if not isinstance(layout, list) or len(layout) > len(NAVIGATION_CATEGORIES):
            raise ValidationError(_("功能导航布局格式无效。"))

        categories = self._category_records()
        valid_codes = set(categories)
        visible_ids = self.env["ir.ui.menu"]._visible_menu_ids()
        allowed_ids = set(self._movable_application_menus().ids) & visible_ids
        seen_ids = set()
        normalized = []
        for section in layout:
            if not isinstance(section, dict):
                raise ValidationError(_("功能导航分类格式无效。"))
            code = section.get("code")
            if code == "business":
                continue
            if code not in valid_codes:
                raise ValidationError(_("未知的功能分类：%s") % code)
            menu_ids = section.get("menu_ids", [])
            if not isinstance(menu_ids, list):
                raise ValidationError(_("功能导航项目格式无效。"))
            normalized_ids = []
            for menu_id in menu_ids:
                if not isinstance(menu_id, int) or menu_id not in allowed_ids or menu_id in seen_ids:
                    raise ValidationError(_("功能导航包含无效或重复的菜单。"))
                seen_ids.add(menu_id)
                normalized_ids.append(menu_id)
            normalized.append((code, normalized_ids))

        if seen_ids != allowed_ids:
            raise ValidationError(_("必须保留所有有权访问的功能模块。"))

        for code, menu_ids in normalized:
            category = categories[code]
            for sequence, menu_id in enumerate(menu_ids, start=1):
                self.env["ir.ui.menu"].browse(menu_id).write({
                    "parent_id": category.id,
                    "sequence": sequence * 10,
                })
        return self.get_application_navigation()

    @api.model
    def reset_application_navigation(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("只有系统管理员可以恢复默认功能分类。"))
        self.organize_application_menus(force=True)
        return self.get_application_navigation()

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
