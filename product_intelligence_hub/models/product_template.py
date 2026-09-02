from odoo import _, fields, models
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
    pi_core_industry_attributes = fields.Text(string="核心行业属性", copy=False, readonly=True)
    pi_important_attributes = fields.Text(string="重要属性", copy=False, readonly=True)
    pi_packaging_information = fields.Text(string="包装信息", copy=False, readonly=True)
    pi_shipping_information = fields.Text(string="发货信息", copy=False, readonly=True)
    pi_detail_updated_at = fields.Datetime(string="详情同步时间", copy=False, readonly=True)

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

