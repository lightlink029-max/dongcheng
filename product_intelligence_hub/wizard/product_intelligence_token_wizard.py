from odoo import fields, models


class ProductIntelligenceTokenWizard(models.TransientModel):
    _name = "product.intelligence.token.wizard"
    _description = "产品智能推送凭证"

    source_id = fields.Many2one("product.intelligence.source", required=True, readonly=True)
    endpoint = fields.Char(readonly=True)
    token = fields.Char(readonly=True)
