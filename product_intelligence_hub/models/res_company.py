from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    pi_weight_demand = fields.Float(default=25.0)
    pi_weight_growth = fields.Float(default=15.0)
    pi_weight_margin = fields.Float(default=20.0)
    pi_weight_competition = fields.Float(default=15.0)
    pi_weight_logistics = fields.Float(default=10.0)
    pi_weight_compliance = fields.Float(default=10.0)
    pi_weight_content = fields.Float(default=5.0)
    pi_approval_threshold = fields.Float(default=75.0)
    pi_review_threshold = fields.Float(default=60.0)

