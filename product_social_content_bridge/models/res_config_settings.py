from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


MEDICAL_TEST_PROJECT_NAME = "[TEST] 西非医疗类综合采购商运营项目"
MEDICAL_TEST_PRODUCT_LINE_NAME = "[TEST] 西非医疗综合采购产品线"
MEDICAL_TEST_PRODUCT_LINE_CODE = "test_medical_west_africa"
MEDICAL_TEST_MARKET_NAME = "[TEST] Nigeria Medical B2B"
MEDICAL_TEST_CHANNEL_NAME = "[TEST] Website - Nigeria Medical"
MEDICAL_TEST_PARTNER_NAME = "[TEST] Lagos Integrated Medical Procurement Ltd."
MEDICAL_TEST_LEAD_NAME = "[TEST] Lagos 综合医疗采购项目"
MEDICAL_TEST_REQUIREMENT_NAME = "[TEST] 基础诊疗设备与医用耗材综合采购"
MEDICAL_TEST_PRODUCT_NAMES = (
    "[TEST] Portable Patient Monitor",
    "[TEST] Manual Hospital Bed",
    "[TEST] Disposable Examination Gloves",
)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    psc_local_worker_token = fields.Char(
        string="工作节点令牌", config_parameter="psc.local_worker_token",
    )
    psc_local_worker_lease_seconds = fields.Integer(
        string="任务租约（秒）", default=900,
        config_parameter="psc.local_worker_lease_seconds",
    )

    @api.model
    def get_values(self):
        values = super().get_values()
        values["psc_local_worker_token"] = self.env[
            "psc.local.production.task"
        ].get_or_create_worker_token()
        return values

    @api.constrains("psc_local_worker_lease_seconds")
    def _check_local_worker_lease(self):
        for settings in self:
            if not 60 <= settings.psc_local_worker_lease_seconds <= 3600:
                raise ValidationError("本地任务租约必须在 60 到 3600 秒之间。")

    def _upsert_medical_test_data(self):
        """Create or repair the repeatable medical-procurement smoke dataset."""
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("只有系统管理员可以初始化测试数据。"))

        country = self.env["res.country"].search([("code", "=", "NG")], limit=1)
        language = self.env["res.lang"].with_context(active_test=False).search(
            [("code", "=", "en_US")], limit=1,
        )
        currency = self.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", "USD")], limit=1,
        )
        track = self.env.ref("product_social_content_bridge.track_medical", raise_if_not_found=False)
        role = self.env.ref("product_social_content_bridge.role_integrator", raise_if_not_found=False)
        if not all((country, language, currency, track, role)):
            raise UserError(_("缺少 Nigeria、English (US)、USD 或医疗赛道模板，请先升级模块基础数据。"))

        product_line_model = self.env["psc.product.line"]
        product_line = product_line_model.search([
            ("code", "=", MEDICAL_TEST_PRODUCT_LINE_CODE),
        ], limit=1)
        if not product_line:
            product_line = product_line_model.search([
                ("name", "=", MEDICAL_TEST_PRODUCT_LINE_NAME),
            ], limit=1)
        product_line_values = {
            "name": MEDICAL_TEST_PRODUCT_LINE_NAME,
            "code": MEDICAL_TEST_PRODUCT_LINE_CODE,
            "brand_name": "LightLink Test Medical",
            "tone": "professional",
            "target_customer": "West African hospitals, clinics, medical distributors and integrated procurement buyers.",
            "key_selling_points": "One-stop sourcing, product selection, compliance coordination, training and after-sales support.",
            "compliance_notes": "All certifications, registrations, intended uses and performance claims require documentary verification.",
            "active": True,
        }
        if product_line:
            product_line.write(product_line_values)
        else:
            product_line = product_line_model.create(product_line_values)

        market_model = self.env["psc.target.market"]
        market = market_model.search([("name", "=", MEDICAL_TEST_MARKET_NAME)], limit=1)
        market_values = {
            "name": MEDICAL_TEST_MARKET_NAME,
            "country_id": country.id,
            "lang_id": language.id,
            "currency_id": currency.id,
            "customer_type": "b2b",
            "customer_profile": "Private hospitals, clinics, medical distributors and project procurement teams in Nigeria.",
            "keywords": "patient monitor, hospital bed, examination gloves, clinic equipment, medical supplies Nigeria",
            "compliance_notes": "Verify NAFDAC or other applicable registration, certificates, labeling and electrical requirements before publishing.",
            "active": True,
        }
        if market:
            market.write(market_values)
        else:
            market = market_model.create(market_values)

        channel_model = self.env["psc.publishing.channel"]
        channel = channel_model.search([("name", "=", MEDICAL_TEST_CHANNEL_NAME)], limit=1)
        channel_values = {
            "name": MEDICAL_TEST_CHANNEL_NAME,
            "platform": "website",
            "image_ratio": "1_1",
            "max_caption_length": 2200,
            "default_instructions": "Professional English B2B content for Nigerian medical procurement buyers; do not make unverified clinical claims.",
            "active": True,
        }
        if channel:
            channel.write(channel_values)
        else:
            channel = channel_model.create(channel_values)

        product_model = self.env["product.template"]
        products = product_model
        for product_name in MEDICAL_TEST_PRODUCT_NAMES:
            product = product_model.search([("name", "=", product_name)], limit=1)
            if not product:
                product = product_model.create({"name": product_name, "sale_ok": True, "purchase_ok": True})
            products |= product
        product_line.product_ids = [(6, 0, products.ids)]

        project_model = self.env["psc.publishing.project"].with_context(
            tracking_disable=True, mail_notrack=True,
        )
        project = project_model.search([("name", "=", MEDICAL_TEST_PROJECT_NAME)], limit=1)
        project_values = {
            "name": MEDICAL_TEST_PROJECT_NAME,
            "track_id": track.id,
            "business_role_id": role.id,
            "capability_ids": [(6, 0, role.capability_ids.ids)],
            "product_line_id": product_line.id,
            "product_ids": [(6, 0, products.ids)],
            "market_ids": [(6, 0, market.ids)],
            "channel_ids": [(6, 0, channel.ids)],
            "business_goal": "Build a maintainable West African medical procurement product portfolio and validate demand through website and social content.",
            "content_brief": "Create factual English content for integrated medical procurement. Emphasize selection, supply coordination, training and after-sales service.",
        }
        if project:
            project.write(project_values)
        else:
            project = project_model.create(project_values)
        project.action_sync_product_pool()

        partner_model = self.env["res.partner"]
        partner = partner_model.search([("name", "=", MEDICAL_TEST_PARTNER_NAME)], limit=1)
        partner_values = {
            "name": MEDICAL_TEST_PARTNER_NAME,
            "company_type": "company",
            "country_id": country.id,
        }
        if partner:
            partner.write(partner_values)
        else:
            partner = partner_model.create(partner_values)

        lead_model = self.env["crm.lead"]
        lead = lead_model.search([
            ("name", "=", MEDICAL_TEST_LEAD_NAME), ("psc_project_id", "=", project.id),
        ], limit=1)
        lead_values = {
            "name": MEDICAL_TEST_LEAD_NAME,
            "type": "opportunity",
            "partner_id": partner.id,
            "country_id": country.id,
            "expected_revenue": 50000.0,
            "psc_project_id": project.id,
            "psc_product_line_id": product_line.id,
            "psc_market_id": market.id,
            "psc_channel_id": channel.id,
        }
        if lead:
            lead.write(lead_values)
        else:
            lead = lead_model.create(lead_values)

        requirement_model = self.env["psc.customer.requirement"]
        requirement = requirement_model.search([
            ("name", "=", MEDICAL_TEST_REQUIREMENT_NAME),
            ("project_id", "=", project.id),
        ], limit=1)
        requirement_values = {
            "name": MEDICAL_TEST_REQUIREMENT_NAME,
            "lead_id": lead.id,
            "project_id": project.id,
            "product_ids": [(6, 0, products.ids)],
            "organization_type": "Private hospital group",
            "contact_role": "Procurement manager",
            "requirement_details": "Integrated purchase of basic diagnostic equipment, ward equipment and recurring medical consumables.",
            "quantity": 1.0,
            "budget": 50000.0,
            "currency_id": currency.id,
            "certification_requirements": "Applicable Nigerian registration, product certificates, labeling and electrical compliance documents.",
            "delivery_country_id": country.id,
            "delivery_port": "Lagos",
            "stage": "new",
        }
        if requirement:
            requirement.write(requirement_values)
        else:
            requirement_model.create(requirement_values)
        return project

    def action_prepare_medical_test_data(self):
        project = self._upsert_medical_test_data()
        return {
            "type": "ir.actions.act_window",
            "name": _("医疗综合采购测试项目"),
            "res_model": "psc.publishing.project",
            "res_id": project.id,
            "view_mode": "form",
            "target": "current",
        }
