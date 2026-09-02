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
    pi_core_industry_attributes = fields.Text(string="核心行业属性", copy=False, translate=True)
    pi_important_attributes = fields.Text(string="重要属性", copy=False, translate=True)
    pi_packaging_information = fields.Text(string="包装信息", copy=False, translate=True)
    pi_shipping_information = fields.Text(string="发货信息", copy=False, translate=True)
    pi_detail_updated_at = fields.Datetime(string="详情同步时间", copy=False, readonly=True)

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
        for config in configs:
            if config.is_translatable or config.state == "applied":
                config.action_remove_translation()
        configs.unlink()
        return True

    @api.model
    def action_seed_odootranslate_english_source_slots(self):
        """Seed a missing en_US slot from zh_CN for OdooTranslate mapping.

        OdooTranslate's native source inspector requires the canonical en_US
        slot to exist before it can map a Chinese source value.  Only missing
        English slots are initialized; existing translations are preserved.
        """
        field_names = [
            "pi_core_industry_attributes",
            "pi_important_attributes",
            "pi_packaging_information",
            "pi_shipping_information",
        ]
        products = self.search([])
        for product in products:
            english_values = {}
            for field_name in field_names:
                field = product._fields[field_name]
                stored = field._get_stored_translations(product) or {}
                chinese_value = stored.get("zh_CN")
                if (
                    isinstance(chinese_value, str)
                    and chinese_value.strip()
                    and not stored.get("en_US")
                ):
                    english_values[field_name] = chinese_value
            if english_values:
                product.with_context(
                    lang="en_US",
                    skip_ai_translation=True,
                    tracking_disable=True,
                ).write(english_values)
        return True

    @api.model
    def action_migrate_product_intelligence_ecommerce_descriptions(self):
        """Move existing sourced details to standard no-variant attributes."""
        products = self.search([("pi_candidate_id", "!=", False)])
        for product in products:
            description = product.pi_candidate_id._prepare_ecommerce_description(
                product.description_ecommerce
            )
            if description != (product.description_ecommerce or ""):
                product.with_context(lang="zh_CN", tracking_disable=True).write({
                    "description_ecommerce": description,
                })
            product.pi_candidate_id._sync_standard_product_attributes(product)
        return True

    def odootranslate_get_stored_field_translation_source(self, field_name, lang):
        """Allow OdooTranslate to use a non-English native source value.

        OdooTranslate 19 currently marks a native field as incomplete when its
        ``en_US`` slot does not exist, even when the requested source language
        contains valid text.  Imported product intelligence fields can begin
        with Chinese as their only stored language, so provide that stored
        value as the source block until the English translation is created.
        """
        result = super().odootranslate_get_stored_field_translation_source(field_name, lang)
        supported_fields = {
            "pi_core_industry_attributes",
            "pi_important_attributes",
            "pi_packaging_information",
            "pi_shipping_information",
        }
        if field_name not in supported_fields or result.get("mapping_complete"):
            return result

        field = self._fields.get(field_name)
        if not field or field.translate is not True:
            return result
        stored_translations = field._get_stored_translations(self) or {}
        source_value = stored_translations.get(lang)
        if not isinstance(source_value, str) or not source_value.strip():
            return result

        result.update({
            "is_stored": True,
            "value": source_value,
            "blocks": [{"source": source_value, "value": source_value}],
            "mapping_complete": True,
        })
        return result

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
