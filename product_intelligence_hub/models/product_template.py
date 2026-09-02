from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    pi_candidate_id = fields.Many2one(
        "product.intelligence.candidate", string="来源产品机会", copy=False, readonly=True, index=True
    )
    pi_source_name = fields.Char(string="数据来源", copy=False, readonly=True)
    pi_external_url = fields.Char(string="原始产品链接", copy=False, readonly=True)
    pi_supplier_name = fields.Char(string="来源供应商", copy=False, readonly=True)
    pi_source_category = fields.Char(string="来源产品分类", copy=False, readonly=True)
    pi_detail_updated_at = fields.Datetime(string="详情同步时间", copy=False, readonly=True)
    pi_video_ids = fields.One2many(
        "product.intelligence.product.video", "product_tmpl_id", string="产品视频", copy=False,
    )

    @api.model
    def action_cleanup_odootranslate_native_field_configs(self):
        """Remove dynamic configs accidentally created for native fields."""
        field_names = [
            "pi_core_industry_attributes",
            "pi_important_attributes",
            "pi_packaging_information",
            "pi_shipping_information",
        ]
        configs = self.env["dynamic.translatable.field.config"].with_context(
            active_test=False
        ).search([
            ("model_name", "=", "product.template"),
            ("field_name", "in", field_names),
        ])
        configs.unlink()
        return True

    @api.model
    def action_migrate_product_intelligence_ecommerce_descriptions(self):
        """Build responsive details in the native eCommerce description."""
        products = self.search([("pi_candidate_id", "!=", False)])
        for product in products:
            ecommerce_description = product.pi_candidate_id._prepare_ecommerce_description(
                product.description_ecommerce
            )
            product.with_context(lang="zh_CN", tracking_disable=True).write({
                "description_sale": product.pi_candidate_id.description or False,
                "description_ecommerce": ecommerce_description,
            })
            product.pi_candidate_id._sync_standard_product_attributes(product)
        return True

    def action_open_product_intelligence_candidate(self):
        self.ensure_one()
        if not self.pi_candidate_id:
            raise UserError(_("该产品没有关联的产品机会。"))
        return {
            "type": "ir.actions.act_window",
            "name": self.pi_candidate_id.display_name,
            "res_model": "product.intelligence.candidate",
            "view_mode": "form",
            "res_id": self.pi_candidate_id.id,
        }

    def action_sync_product_intelligence_details(self):
        self.ensure_one()
        if not self.pi_candidate_id:
            raise UserError(_("该产品没有关联的产品机会。"))
        self.write(self.pi_candidate_id._prepare_product_values(self))
        self.pi_candidate_id._sync_standard_product_attributes(self)
        self.pi_candidate_id._sync_product_media(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("产品详情同步完成"),
                "message": _("已从产品机会重新同步最新详情。"),
                "type": "success",
                "sticky": False,
            },
        }


class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    pi_managed = fields.Boolean(string="选品情报管理", default=False, index=True)
    pi_technical_key = fields.Char(string="选品属性标识", copy=False, index=True)
