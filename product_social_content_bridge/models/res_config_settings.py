from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


MEDICAL_TEST_PROJECT_NAME = "[TEST] 西非医疗类综合采购商运营项目"
MEDICAL_TEST_PRODUCT_LINE_NAME = "[TEST] 西非医疗综合采购产品线"
MEDICAL_TEST_PRODUCT_LINE_CODE = "test_medical_west_africa"
MEDICAL_TEST_MARKET_NAME = "[TEST] Nigeria Medical B2B"
MEDICAL_TEST_CHANNEL_NAME = "[TEST] Website - Nigeria Medical"
MEDICAL_TEST_SOCIAL_CHANNEL_NAME = "[TEST] Instagram - Nigeria Medical"
MEDICAL_TEST_CLUSTER_NAME = "[TEST] Existing BitBrowser Placeholder Cluster"
MEDICAL_TEST_ACCOUNT_NAME = "[TEST] Placeholder Instagram Account"
MEDICAL_TEST_DESTINATION_NAME = "[TEST] Placeholder Instagram Destination"
MEDICAL_TEST_PUBLICATION_TASK_NAME = "[TEST] Placeholder publication task"
MEDICAL_TEST_SOCIAL_CONTENT_TITLE = "[TEST] Instagram placeholder workflow draft"
MEDICAL_TEST_PARTNER_NAME = "[TEST] Lagos Integrated Medical Procurement Ltd."
MEDICAL_TEST_LEAD_NAME = "[TEST] Lagos 综合医疗采购项目"
MEDICAL_TEST_REQUIREMENT_NAME = "[TEST] 基础诊疗设备与医用耗材综合采购"
MEDICAL_TEST_QUOTATION_REFERENCE = "[TEST] Medical attribution quotation"
MEDICAL_TEST_FULFILLMENT_REFERENCE = "[TEST] CRM procurement inventory order"
MEDICAL_TEST_PURCHASE_REFERENCE = "[TEST] Purchase for CRM inventory flow"
MEDICAL_TEST_VENDOR_NAME = "[TEST] Shenzhen Medical Equipment Supplier"
MEDICAL_TEST_CUSTOMER_INVOICE_REFERENCE = "[TEST] Customer invoice for CRM fulfillment"
MEDICAL_TEST_VENDOR_BILL_REFERENCE = "[TEST] Vendor bill for CRM fulfillment"
MEDICAL_TEST_CUSTOMER_REFUND_REFERENCE = "[TEST] Customer refund for returned goods"
MEDICAL_TEST_VENDOR_REFUND_REFERENCE = "[TEST] Vendor refund for returned goods"
MEDICAL_TEST_TOUCHPOINT_PREFIX = "test-medical-funnel-"
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

        product_model = self.env["product.template"].with_context(active_test=False)
        products = product_model
        for product_name in MEDICAL_TEST_PRODUCT_NAMES:
            product = product_model.search([("name", "=", product_name)], limit=1)
            product_values = {
                "name": product_name,
                "sale_ok": True,
                "purchase_ok": True,
                "active": True,
            }
            if product:
                product.write(product_values)
            else:
                product = product_model.create(product_values)
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
        for pool_item in project.project_product_ids:
            existing_rules = pool_item.score_line_ids.mapped("rule_id")
            missing_rules = track.scoring_rule_ids.filtered(
                lambda rule: rule.active and rule not in existing_rules
            )
            if missing_rules:
                pool_item.score_line_ids = [(0, 0, {
                    "rule_id": rule.id,
                    "name": rule.name,
                    "sequence": rule.sequence,
                    "weight": rule.weight,
                    "hard_gate": rule.hard_gate,
                    "gate_passed": not rule.hard_gate,
                }) for rule in missing_rules]
            existing_attributes = pool_item.attribute_value_ids.mapped("attribute_id")
            missing_attributes = track.product_attribute_ids.filtered(
                lambda attribute: attribute.active and attribute not in existing_attributes
            )
            if missing_attributes:
                pool_item.attribute_value_ids = [(0, 0, {
                    "attribute_id": attribute.id,
                    "name": attribute.name,
                    "required_for_publish": attribute.required_for_publish,
                    "hard_gate": attribute.hard_gate,
                    "sequence": attribute.sequence,
                }) for attribute in missing_attributes]

        partner_model = self.env["res.partner"].with_context(active_test=False)
        partner = partner_model.search([("name", "=", MEDICAL_TEST_PARTNER_NAME)], limit=1)
        partner_values = {
            "name": MEDICAL_TEST_PARTNER_NAME,
            "company_type": "company",
            "country_id": country.id,
            "active": True,
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

    def _complete_test_pickings(self, record, field_name, label):
        """Validate every step of a synthetic receipt or delivery chain."""
        for _iteration in range(10):
            record.invalidate_recordset([field_name])
            pickings = record[field_name]
            if not pickings:
                raise UserError(_("%s未生成库存单据。") % label)
            pending = pickings.filtered(lambda item: item.state not in ("done", "cancel"))
            if not pending:
                return pickings.filtered(lambda item: item.state == "done")
            progressed = False
            for picking in pending.sorted("id"):
                picking.action_assign()
                if picking.state not in ("assigned", "confirmed"):
                    continue
                for move in picking.move_ids.filtered(lambda item: item.state not in ("done", "cancel")):
                    move.write({"quantity": move.product_uom_qty, "picked": True})
                picking.with_context(
                    skip_backorder=True,
                    picking_ids_not_to_backorder=picking.ids,
                    skip_sms=True,
                ).button_validate()
                if picking.state == "done":
                    progressed = True
            if not progressed:
                raise UserError(_("%s无法继续，仍有等待中的库存移动。") % label)
        raise UserError(_("%s超过最大库存处理步数。") % label)

    def _complete_medical_procurement_inventory_flow(self, project, lead, product_item):
        """Build a repeatable CRM-to-purchase-to-stock synthetic flow."""
        product_template = product_item.product_id
        product_template.write({"sale_ok": True, "purchase_ok": True, "is_storable": True})
        product = product_template.product_variant_id

        vendor_model = self.env["res.partner"].with_context(active_test=False)
        vendor = vendor_model.search([("name", "=", MEDICAL_TEST_VENDOR_NAME)], limit=1)
        vendor_values = {
            "name": MEDICAL_TEST_VENDOR_NAME,
            "company_type": "company",
            "supplier_rank": 1,
            "active": True,
        }
        if vendor:
            vendor.write(vendor_values)
        else:
            vendor = vendor_model.create(vendor_values)

        sale_order = self.env["sale.order"].search([
            ("opportunity_id", "=", lead.id),
            ("client_order_ref", "=", MEDICAL_TEST_FULFILLMENT_REFERENCE),
        ], limit=1)
        if not sale_order:
            sale_order = self.env["sale.order"].create({
                "partner_id": lead.partner_id.id,
                "opportunity_id": lead.id,
                "client_order_ref": MEDICAL_TEST_FULFILLMENT_REFERENCE,
            })
        if not sale_order.order_line:
            self.env["sale.order.line"].create({
                "order_id": sale_order.id,
                "product_id": product.id,
                "name": "[TEST] CRM-to-inventory fulfillment item",
                "product_uom_qty": 2.0,
                "product_uom_id": product.uom_id.id,
                "price_unit": 1000.0,
            })
        if sale_order.state in ("draft", "sent"):
            sale_order.action_confirm()

        purchase_order = self.env["purchase.order"].search([
            ("partner_id", "=", vendor.id),
            ("partner_ref", "=", MEDICAL_TEST_PURCHASE_REFERENCE),
        ], limit=1)
        if not purchase_order:
            purchase_order = self.env["purchase.order"].create({
                "partner_id": vendor.id,
                "partner_ref": MEDICAL_TEST_PURCHASE_REFERENCE,
                "psc_sale_order_id": sale_order.id,
                "picking_type_id": sale_order.warehouse_id.in_type_id.id,
            })
        elif not purchase_order.psc_sale_order_id:
            purchase_order.write({
                "psc_sale_order_id": sale_order.id,
                "psc_project_id": project.id,
            })
        if not purchase_order.order_line:
            self.env["purchase.order.line"].create({
                "order_id": purchase_order.id,
                "product_id": product.id,
                "name": "[TEST] Purchase for CRM inventory fulfillment",
                "product_qty": 2.0,
                "product_uom_id": product.uom_id.id,
                "price_unit": 600.0,
                "date_planned": fields.Datetime.now(),
            })
        if purchase_order.state in ("draft", "sent"):
            purchase_order.button_confirm()
        if purchase_order.state == "to approve":
            purchase_order.button_approve()

        receipt_pickings = self._complete_test_pickings(
            purchase_order, "picking_ids", _("测试采购收货"),
        )
        delivery_pickings = self._complete_test_pickings(
            sale_order, "picking_ids", _("测试销售出库"),
        )
        purchase_order.order_line.invalidate_recordset(["qty_received"])
        sale_order.order_line.invalidate_recordset(["qty_delivered"])
        internal_quants = self.env["stock.quant"].search([
            ("product_id", "=", product.id),
            ("location_id.usage", "=", "internal"),
            ("company_id", "=", sale_order.company_id.id),
        ])
        return {
            "vendor": vendor.id,
            "fulfillment_order": sale_order.id,
            "purchase_order": purchase_order.id,
            "receipt_pickings": receipt_pickings.ids,
            "delivery_pickings": delivery_pickings.ids,
            "purchased_qty": sum(purchase_order.order_line.mapped("qty_received")),
            "delivered_qty": sum(sale_order.order_line.mapped("qty_delivered")),
            "internal_stock_qty": sum(internal_quants.mapped("quantity")),
        }

    def _complete_test_return(self, picking, quantity, label):
        """Create and validate one repeatable return for a completed test picking."""
        returned = self.env["stock.picking"].search([
            ("move_ids.origin_returned_move_id", "in", picking.move_ids.ids),
            ("state", "!=", "cancel"),
        ], order="id", limit=1)
        if not returned:
            wizard = self.env["stock.return.picking"].with_context(
                active_model="stock.picking",
                active_id=picking.id,
                active_ids=picking.ids,
            ).create({})
            return_lines = wizard.product_return_moves.filtered(
                lambda line: line.product_id in picking.move_ids.product_id
            )
            if not return_lines:
                raise UserError(_("%s没有可退回的产品。") % label)
            wizard.product_return_moves.quantity = 0.0
            return_lines[:1].quantity = quantity
            action = wizard.action_create_returns()
            returned = self.env["stock.picking"].browse(action.get("res_id")).exists()
        if not returned:
            raise UserError(_("%s未生成退货单。") % label)
        if returned.state not in ("done", "cancel"):
            returned.action_assign()
            for move in returned.move_ids.filtered(lambda item: item.state not in ("done", "cancel")):
                move.write({"quantity": move.product_uom_qty, "picked": True})
            returned.with_context(
                skip_backorder=True,
                picking_ids_not_to_backorder=returned.ids,
                skip_sms=True,
            ).button_validate()
        if returned.state != "done":
            raise UserError(_("%s未完成。") % label)
        return returned

    def _register_test_payment(self, move, label):
        """Register a synthetic payment/refund against one posted test document."""
        payments = move.reconciled_payment_ids | move.matched_payment_ids
        if move.payment_state not in ("paid", "in_payment"):
            payments |= self.env["account.payment.register"].with_context(
                active_model="account.move",
                active_id=move.id,
                active_ids=move.ids,
            ).create({
                "payment_date": fields.Date.context_today(self),
            })._create_payments()
            move.invalidate_recordset(["payment_state", "amount_residual"])
        if (
            move.payment_state not in ("paid", "in_payment")
            or not move.currency_id.is_zero(move.amount_residual)
        ):
            raise UserError(_("%s未进入已付款或付款中状态。") % label)
        return payments

    def _complete_medical_finance_return_flow(self, project, product_item, flow):
        """Complete invoices, payments, returns and refunds for the test flow."""
        sale_order = self.env["sale.order"].browse(flow["fulfillment_order"]).exists()
        purchase_order = self.env["purchase.order"].browse(flow["purchase_order"]).exists()
        if (
            not sale_order or not purchase_order
            or sale_order.psc_project_id != project
        ):
            raise UserError(_("缺少测试销售订单或采购订单。"))

        customer_invoice = sale_order.invoice_ids.filtered(
            lambda move: move.move_type == "out_invoice" and move.state != "cancel"
        )[:1]
        if not customer_invoice:
            customer_invoice = sale_order._create_invoices()[:1]
        if not customer_invoice:
            raise UserError(_("测试销售订单未生成客户发票。"))
        if customer_invoice.state == "draft":
            customer_invoice.write({
                "invoice_date": fields.Date.context_today(self),
                "ref": MEDICAL_TEST_CUSTOMER_INVOICE_REFERENCE,
            })
            customer_invoice.action_post()
        customer_payments = self._register_test_payment(
            customer_invoice, _("[TEST] Customer payment for %s") % sale_order.name,
        )

        vendor_bill = purchase_order.invoice_ids.filtered(
            lambda move: move.move_type == "in_invoice" and move.state != "cancel"
        )[:1]
        if not vendor_bill:
            purchase_order.action_create_invoice()
            purchase_order.invalidate_recordset(["invoice_ids"])
            vendor_bill = purchase_order.invoice_ids.filtered(
                lambda move: move.move_type == "in_invoice" and move.state != "cancel"
            )[:1]
        if not vendor_bill:
            raise UserError(_("测试采购订单未生成供应商账单。"))
        if vendor_bill.state == "draft":
            vendor_bill.write({
                "invoice_date": fields.Date.context_today(self),
                "ref": MEDICAL_TEST_VENDOR_BILL_REFERENCE,
            })
            vendor_bill.action_post()
        vendor_payments = self._register_test_payment(
            vendor_bill, _("[TEST] Vendor payment for %s") % purchase_order.name,
        )

        delivery = self.env["stock.picking"].browse(flow["delivery_pickings"][:1]).exists()
        receipt = self.env["stock.picking"].browse(flow["receipt_pickings"][:1]).exists()
        customer_return = self._complete_test_return(delivery, 2.0, _("测试客户退货"))
        vendor_return = self._complete_test_return(receipt, 2.0, _("测试供应商退货"))

        customer_refund = self.env["account.move"].search([
            ("reversed_entry_id", "=", customer_invoice.id),
            ("ref", "=", MEDICAL_TEST_CUSTOMER_REFUND_REFERENCE),
            ("state", "!=", "cancel"),
        ], limit=1)
        if not customer_refund:
            refund_date = fields.Date.context_today(self)
            customer_refund = customer_invoice._reverse_moves([{
                "date": refund_date,
                "invoice_date": refund_date,
                "ref": MEDICAL_TEST_CUSTOMER_REFUND_REFERENCE,
            }], cancel=False)
        if customer_refund.state == "draft":
            customer_refund.action_post()
        customer_refund_payments = self._register_test_payment(
            customer_refund, _("[TEST] Customer refund for %s") % customer_invoice.name,
        )

        vendor_refund = self.env["account.move"].search([
            ("reversed_entry_id", "=", vendor_bill.id),
            ("ref", "=", MEDICAL_TEST_VENDOR_REFUND_REFERENCE),
            ("state", "!=", "cancel"),
        ], limit=1)
        if not vendor_refund:
            refund_date = fields.Date.context_today(self)
            vendor_refund = vendor_bill._reverse_moves([{
                "date": refund_date,
                "invoice_date": refund_date,
                "ref": MEDICAL_TEST_VENDOR_REFUND_REFERENCE,
            }], cancel=False)
        if vendor_refund.state == "draft":
            vendor_refund.action_post()
        vendor_refund_payments = self._register_test_payment(
            vendor_refund, _("[TEST] Vendor refund for %s") % vendor_bill.name,
        )

        product = product_item.product_id.product_variant_id
        internal_quants = self.env["stock.quant"].search([
            ("product_id", "=", product.id),
            ("location_id.usage", "=", "internal"),
            ("company_id", "=", sale_order.company_id.id),
        ])
        return {
            "customer_invoice": customer_invoice.id,
            "customer_invoice_state": customer_invoice.state,
            "customer_invoice_payment_state": customer_invoice.payment_state,
            "customer_invoice_residual": customer_invoice.amount_residual,
            "customer_payments": customer_payments.ids,
            "vendor_bill": vendor_bill.id,
            "vendor_bill_state": vendor_bill.state,
            "vendor_bill_payment_state": vendor_bill.payment_state,
            "vendor_bill_residual": vendor_bill.amount_residual,
            "vendor_payments": vendor_payments.ids,
            "customer_return": customer_return.id,
            "customer_return_qty": sum(customer_return.move_ids.mapped("quantity")),
            "vendor_return": vendor_return.id,
            "vendor_return_qty": sum(vendor_return.move_ids.mapped("quantity")),
            "customer_refund": customer_refund.id,
            "customer_refund_payment_state": customer_refund.payment_state,
            "customer_refund_residual": customer_refund.amount_residual,
            "customer_refund_payments": customer_refund_payments.ids,
            "vendor_refund": vendor_refund.id,
            "vendor_refund_payment_state": vendor_refund.payment_state,
            "vendor_refund_residual": vendor_refund.amount_residual,
            "vendor_refund_payments": vendor_refund_payments.ids,
            "internal_stock_after_returns": sum(internal_quants.mapped("quantity")),
        }

    def _complete_medical_test_scenario(
        self, worker_node_id=None, environment_id=None, include_procurement_inventory=False,
        include_finance_workflow=False,
    ):
        """Complete the fixed dataset with safe synthetic records for end-to-end testing."""
        self.ensure_one()
        project = self._upsert_medical_test_data()
        project.operation_state = "active"

        product_item = project.project_product_ids.filtered(
            lambda item: item.product_id.name == MEDICAL_TEST_PRODUCT_NAMES[0]
        )[:1]
        if not product_item:
            raise UserError(_("医疗测试项目缺少主测试产品。"))
        product_item.write({
            "compliance_state": "passed",
            "material_state": "complete",
            "positioning": "[TEST] Synthetic positioning for workflow validation only.",
            "selling_points": "[TEST] Synthetic selling points; not approved for external use.",
            "target_purchase_price": 100.0,
            "target_sale_price": 150.0,
            "minimum_order_qty": 1.0,
            "lead_time_days": 30,
        })
        product_item.attribute_value_ids.write({
            "value": "[TEST] Synthetic verified value",
            "verified": True,
            "evidence": "[TEST] Synthetic evidence for workflow validation only.",
        })
        product_item.score_line_ids.write({"score": 80.0, "gate_passed": True})
        product_item.action_mark_active()

        plan_model = self.env["psc.content.plan"]
        pillars = project.track_id.content_pillar_ids.filtered(
            lambda pillar: pillar.active
            and (not pillar.role_ids or project.business_role_id in pillar.role_ids)
        )
        for pillar in pillars:
            plan = plan_model.search([
                ("project_id", "=", project.id),
                ("pillar_id", "=", pillar.id),
                ("market_id", "=", project.market_ids[:1].id),
                ("channel_id", "=", project.channel_ids[:1].id),
            ], limit=1)
            if not plan:
                plan_model.create({
                    "name": "[TEST] %s · %s" % (pillar.name, project.market_ids[:1].name),
                    "project_id": project.id,
                    "pillar_id": pillar.id,
                    "product_id": product_item.product_id.id,
                    "market_id": project.market_ids[:1].id,
                    "channel_id": project.channel_ids[:1].id,
                    "brief": "[TEST] Synthetic content plan; no external publication.",
                })

        lead = self.env["crm.lead"].search([
            ("name", "=", MEDICAL_TEST_LEAD_NAME), ("psc_project_id", "=", project.id),
        ], limit=1)
        if not lead.stage_id.is_won:
            lead.probability = 40.0
        touchpoint_model = self.env["psc.customer.touchpoint"]
        for sequence, event_type in enumerate(("impression", "visit", "click", "inquiry"), start=1):
            reference = "%s%s" % (MEDICAL_TEST_TOUCHPOINT_PREFIX, sequence)
            touchpoint = touchpoint_model.search([
                ("lead_id", "=", lead.id), ("external_reference", "=", reference),
            ], limit=1)
            values = {
                "lead_id": lead.id,
                "event_type": event_type,
                "source_type": "website",
                "project_id": project.id,
                "market_id": project.market_ids[:1].id,
                "channel_id": project.channel_ids[:1].id,
                "product_id": product_item.product_id.id,
                "external_reference": reference,
                "verified": True,
                "notes": "[TEST] Synthetic funnel event for workflow validation.",
            }
            if touchpoint:
                touchpoint.write(values)
            else:
                touchpoint_model.create(values)

        quotation = self.env["sale.order"].search([
            ("opportunity_id", "=", lead.id),
            ("client_order_ref", "=", MEDICAL_TEST_QUOTATION_REFERENCE),
        ], limit=1)
        if not quotation:
            quotation = self.env["sale.order"].create({
                "partner_id": lead.partner_id.id,
                "opportunity_id": lead.id,
                "client_order_ref": MEDICAL_TEST_QUOTATION_REFERENCE,
            })

        if not quotation.order_line:
            self.env["sale.order.line"].create({
                "order_id": quotation.id,
                "product_id": product_item.product_id.product_variant_id.id,
                "name": "[TEST] Portable Patient Monitor workflow validation item",
                "product_uom_qty": 2.0,
                "product_uom_id": product_item.product_id.uom_id.id,
                "price_unit": 1000.0,
            })
        if quotation.state in ("draft", "sent"):
            quotation.action_confirm()

        procurement_inventory = {}
        if include_procurement_inventory:
            procurement_inventory = self._complete_medical_procurement_inventory_flow(
                project, lead, product_item,
            )
        finance_workflow = {}
        if include_finance_workflow:
            if not procurement_inventory:
                raise UserError(_("财务退货测试必须同时启用采购库存测试。"))
            finance_workflow = self._complete_medical_finance_return_flow(
                project, product_item, procurement_inventory,
            )

        worker = self.env["psc.local.worker.node"].browse(worker_node_id).exists()
        environment = self.env["psc.bitbrowser.environment"].browse(environment_id).exists()
        if not worker or not environment or environment.worker_node_id != worker or not environment.available:
            raise UserError(_("现有 Windows 工作节点或比特环境不存在、未同步或不可用。"))

        social_channel = self.env["psc.publishing.channel"].search([
            ("name", "=", MEDICAL_TEST_SOCIAL_CHANNEL_NAME),
        ], limit=1)
        social_channel_values = {
            "name": MEDICAL_TEST_SOCIAL_CHANNEL_NAME,
            "platform": "instagram",
            "image_ratio": "1_1",
            "max_caption_length": 2200,
            "default_instructions": "[TEST] Placeholder channel; never publish before replacing account authorization.",
            "active": True,
        }
        if social_channel:
            social_channel.write(social_channel_values)
        else:
            social_channel = self.env["psc.publishing.channel"].create(social_channel_values)
        project.channel_ids = [(4, social_channel.id)]

        cluster = self.env["psc.social.account.cluster"].search([
            ("name", "=", MEDICAL_TEST_CLUSTER_NAME),
        ], limit=1)
        cluster_values = {
            "name": MEDICAL_TEST_CLUSTER_NAME,
            "project_ids": [(4, project.id)],
            "track_id": project.track_id.id,
            "product_line_id": project.product_line_id.id,
            "target_market_id": project.market_ids[:1].id,
            "persona": "[TEST] Pending real platform authorization",
            "positioning": "[TEST] Placeholder only; replace proxy, platform identity and authorization before publishing.",
            "worker_node_id": worker.id,
            "bitbrowser_environment_id": environment.id,
            "expected_ip": "[TEST] pending-real-fixed-ip",
            "expected_country_id": project.market_ids[:1].country_id.id,
            "expected_timezone": "Africa/Lagos",
            "state": "draft",
        }
        if cluster:
            cluster.write(cluster_values)
        else:
            cluster = self.env["psc.social.account.cluster"].create(cluster_values)

        account = self.env["psc.social.publishing.account"].search([
            ("name", "=", MEDICAL_TEST_ACCOUNT_NAME),
            ("cluster_id", "=", cluster.id),
        ], limit=1)
        account_values = {
            "name": MEDICAL_TEST_ACCOUNT_NAME,
            "cluster_id": cluster.id,
            "channel_id": social_channel.id,
            "username": "[TEST] pending-real-username",
            "platform_account_id": "[TEST] pending-real-account-id",
            "account_state": "pending",
            "daily_publish_limit": 3,
        }
        if account:
            account.write(account_values)
        else:
            account = self.env["psc.social.publishing.account"].create(account_values)

        destination = self.env["psc.publishing.destination"].search([
            ("name", "=", MEDICAL_TEST_DESTINATION_NAME),
        ], limit=1)
        destination_values = {
            "name": MEDICAL_TEST_DESTINATION_NAME,
            "destination_type": "social",
            "product_line_id": project.product_line_id.id,
            "market_id": project.market_ids[:1].id,
            "channel_id": social_channel.id,
            "publishing_account_id": account.id,
            "notes": "[TEST] Placeholder destination; intentionally blocked until real account validation passes.",
            "state": "draft",
        }
        if destination:
            destination.write(destination_values)
        else:
            destination = self.env["psc.publishing.destination"].create(destination_values)

        content = self.env["psc.content.variant"].search([
            ("project_id", "=", project.id),
            ("channel_id", "=", social_channel.id),
            ("title", "=", MEDICAL_TEST_SOCIAL_CONTENT_TITLE),
        ], limit=1)
        if not content:
            content = self.env["psc.content.variant"].create({
                "project_id": project.id,
                "pillar_id": project.content_plan_ids[:1].pillar_id.id,
                "product_id": product_item.product_id.id,
                "market_id": project.market_ids[:1].id,
                "channel_id": social_channel.id,
                "language_id": project.market_ids[:1].lang_id.id,
                "title": MEDICAL_TEST_SOCIAL_CONTENT_TITLE,
                "caption": "[TEST] Synthetic workflow-validation copy; not approved for external publication.",
                "state": "draft",
                "ai_state": "done",
                "ai_model": "LightLink test fixture",
                "ai_generated_at": fields.Datetime.now(),
            })

        publication_task = self.env["psc.publication.task"].search([
            ("name", "=", MEDICAL_TEST_PUBLICATION_TASK_NAME),
            ("project_id", "=", project.id),
        ], limit=1)
        publication_values = {
            "name": MEDICAL_TEST_PUBLICATION_TASK_NAME,
            "content_id": content.id,
            "project_id": project.id,
            "destination_id": destination.id,
            "state": "failed",
            "status_message": "[TEST] Blocked as expected: real platform authorization is not configured.",
            "error_message": "[TEST] Authentication/configuration placeholder; automatic retry is forbidden.",
            "finished_at": fields.Datetime.now(),
        }
        if publication_task:
            publication_task.write(publication_values)
        else:
            publication_task = self.env["psc.publication.task"].create(publication_values)

        self.env["psc.performance.snapshot"].cron_build_project_snapshots()
        test_records = {
            "project_product": product_item.id,
            "content_plans": project.content_plan_ids.ids,
            "lead": lead.id,
            "quotation": quotation.id,
            "order": quotation.id,
            "content": content.id,
            "account_cluster": cluster.id,
            "publishing_account": account.id,
            "publishing_destination": destination.id,
            "publication_task": publication_task.id,
        }
        test_records.update(procurement_inventory)
        test_records.update(finance_workflow)
        return {
            "model": project._name,
            "id": project.id,
            "display_name": project.display_name,
            "test_records": test_records,
        }

    def _cleanup_medical_test_data(self, exclude_action_id=None):
        """Delete only the fixed smoke-test dataset, inside one transaction."""
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("只有系统管理员可以清理测试数据。"))

        project = self.env["psc.publishing.project"].search([
            ("name", "=", MEDICAL_TEST_PROJECT_NAME),
        ], limit=1)
        if not project:
            return {"model": "psc.publishing.project", "id": 0, "display_name": MEDICAL_TEST_PROJECT_NAME, "deleted": {}}

        products = self.env["product.template"].with_context(active_test=False).search([
            ("name", "in", list(MEDICAL_TEST_PRODUCT_NAMES)),
        ])
        product_line = self.env["psc.product.line"].search([
            ("code", "=", MEDICAL_TEST_PRODUCT_LINE_CODE),
        ], limit=1)
        market = self.env["psc.target.market"].search([
            ("name", "=", MEDICAL_TEST_MARKET_NAME),
        ], limit=1)
        channel = self.env["psc.publishing.channel"].search([
            ("name", "=", MEDICAL_TEST_CHANNEL_NAME),
        ], limit=1)
        social_channel = self.env["psc.publishing.channel"].search([
            ("name", "=", MEDICAL_TEST_SOCIAL_CHANNEL_NAME),
        ], limit=1)
        shared_domains = []
        if product_line:
            shared_domains.append([("product_line_id", "=", product_line.id)])
        if products:
            shared_domains.append([("product_ids", "in", products.ids)])
        if market:
            shared_domains.append([("market_ids", "in", market.ids)])
        if channel:
            shared_domains.append([("channel_ids", "in", channel.ids)])
        if social_channel:
            shared_domains.append([("channel_ids", "in", social_channel.ids)])
        for shared_domain in shared_domains:
            if self.env["psc.publishing.project"].search_count([
                ("id", "!=", project.id), *shared_domain,
            ]):
                raise UserError(_("测试产品、产品线、市场或渠道已被非测试项目引用，已拒绝清理。"))
        cluster = self.env["psc.social.account.cluster"].search([
            ("name", "=", MEDICAL_TEST_CLUSTER_NAME),
        ], limit=1)
        if cluster and cluster.project_ids.filtered(lambda item: item != project):
            raise UserError(_("测试账号集群已被非测试项目引用，已拒绝清理。"))

        deleted = {}
        retained_audit = {}

        def remove(model_name, domain):
            records = self.env[model_name].search(domain)
            if records:
                deleted[model_name] = records.ids
                records.unlink()

        action_domain = [
            ("project_id", "=", project.id),
            ("state", "=", "waiting_approval"),
        ]
        if exclude_action_id:
            action_domain.append(("id", "!=", exclude_action_id))
        pending_actions = self.env["psc.ai.action"].search(action_domain)
        if pending_actions:
            deleted["rejected_psc.ai.action"] = pending_actions.ids
            pending_actions.action_reject()
        lead = self.env["crm.lead"].search([
            ("name", "=", MEDICAL_TEST_LEAD_NAME),
            ("psc_project_id", "=", project.id),
        ], limit=1)
        fulfillment_orders = self.env["sale.order"].search([
            ("client_order_ref", "=", MEDICAL_TEST_FULFILLMENT_REFERENCE),
        ])
        purchase_orders = self.env["purchase.order"].search([
            ("partner_ref", "=", MEDICAL_TEST_PURCHASE_REFERENCE),
        ])
        if fulfillment_orders:
            retained_audit["sale.order"] = fulfillment_orders.ids
        if purchase_orders:
            retained_audit["purchase.order"] = purchase_orders.ids
        audit_pickings = fulfillment_orders.picking_ids | purchase_orders.picking_ids
        if audit_pickings:
            retained_audit["stock.picking"] = audit_pickings.ids
        audit_move_domain = [("ref", "in", (
            MEDICAL_TEST_CUSTOMER_INVOICE_REFERENCE,
            MEDICAL_TEST_VENDOR_BILL_REFERENCE,
            MEDICAL_TEST_CUSTOMER_REFUND_REFERENCE,
            MEDICAL_TEST_VENDOR_REFUND_REFERENCE,
        ))]
        if fulfillment_orders:
            audit_move_domain = [
                "|", *audit_move_domain,
                ("invoice_origin", "in", fulfillment_orders.mapped("name")),
            ]
        audit_moves = self.env["account.move"].search(audit_move_domain)
        if audit_moves:
            retained_audit["account.move"] = audit_moves.ids
            audit_payments = audit_moves.reconciled_payment_ids | audit_moves.matched_payment_ids
            if audit_payments:
                retained_audit["account.payment"] = audit_payments.ids
        if lead:
            remove("mail.activity", [
                ("res_model_id", "=", self.env["ir.model"]._get_id("crm.lead")),
                ("res_id", "=", lead.id),
                ("summary", "like", "[TEST]"),
            ])
            test_orders = self.env["sale.order"].search([
                ("opportunity_id", "=", lead.id),
                ("client_order_ref", "=", MEDICAL_TEST_QUOTATION_REFERENCE),
            ])
            if test_orders:
                for order in test_orders.filtered(lambda item: item.state not in ("draft", "cancel")):
                    order.action_cancel()
                deleted["sale.order"] = test_orders.ids
                test_orders.unlink()
        remove("psc.publication.task", [("name", "=", MEDICAL_TEST_PUBLICATION_TASK_NAME)])
        remove("psc.publishing.destination", [("name", "=", MEDICAL_TEST_DESTINATION_NAME)])
        remove("psc.social.publishing.account", [("name", "=", MEDICAL_TEST_ACCOUNT_NAME)])
        remove("psc.social.account.cluster", [("name", "=", MEDICAL_TEST_CLUSTER_NAME)])
        remove("psc.customer.requirement", [
            ("name", "=", MEDICAL_TEST_REQUIREMENT_NAME),
            ("project_id", "=", project.id),
        ])
        remove("crm.lead", [
            ("name", "=", MEDICAL_TEST_LEAD_NAME),
            ("psc_project_id", "=", project.id),
        ])
        remove("psc.publishing.project", [("id", "=", project.id)])
        customer = self.env["res.partner"].with_context(active_test=False).search([
            ("name", "=", MEDICAL_TEST_PARTNER_NAME),
        ], limit=1)
        if customer and fulfillment_orders:
            customer.active = False
            deleted["archived_res.partner"] = customer.ids
        else:
            remove("res.partner", [("name", "=", MEDICAL_TEST_PARTNER_NAME)])
        vendor = self.env["res.partner"].with_context(active_test=False).search([
            ("name", "=", MEDICAL_TEST_VENDOR_NAME),
        ], limit=1)
        if vendor and purchase_orders:
            vendor.active = False
            deleted.setdefault("archived_res.partner", []).extend(vendor.ids)
        elif vendor:
            deleted["res.partner.vendor"] = vendor.ids
            vendor.unlink()
        remove("psc.target.market", [("name", "=", MEDICAL_TEST_MARKET_NAME)])
        remove("psc.publishing.channel", [("name", "=", MEDICAL_TEST_CHANNEL_NAME)])
        remove("psc.publishing.channel", [("name", "=", MEDICAL_TEST_SOCIAL_CHANNEL_NAME)])
        remove("psc.product.line", [("code", "=", MEDICAL_TEST_PRODUCT_LINE_CODE)])
        stock_moves = self.env["stock.move"].search([
            ("product_id.product_tmpl_id", "in", products.ids),
        ], limit=1)
        if products and stock_moves:
            products.active = False
            deleted["archived_product.template"] = products.ids
        else:
            remove("product.template", [("name", "in", list(MEDICAL_TEST_PRODUCT_NAMES))])
        return {
            "model": "psc.publishing.project",
            "id": project.id,
            "display_name": MEDICAL_TEST_PROJECT_NAME,
            "deleted": deleted,
            "retained_audit": retained_audit,
        }

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
