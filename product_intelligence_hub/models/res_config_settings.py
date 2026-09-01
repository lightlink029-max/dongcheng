from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pi_weight_demand = fields.Float(related="company_id.pi_weight_demand", readonly=False)
    pi_weight_growth = fields.Float(related="company_id.pi_weight_growth", readonly=False)
    pi_weight_margin = fields.Float(related="company_id.pi_weight_margin", readonly=False)
    pi_weight_competition = fields.Float(
        related="company_id.pi_weight_competition", readonly=False
    )
    pi_weight_logistics = fields.Float(
        related="company_id.pi_weight_logistics", readonly=False
    )
    pi_weight_compliance = fields.Float(
        related="company_id.pi_weight_compliance", readonly=False
    )
    pi_weight_content = fields.Float(related="company_id.pi_weight_content", readonly=False)
    pi_approval_threshold = fields.Float(
        related="company_id.pi_approval_threshold", readonly=False
    )
    pi_review_threshold = fields.Float(
        related="company_id.pi_review_threshold", readonly=False
    )

    @api.constrains(
        "pi_weight_demand",
        "pi_weight_growth",
        "pi_weight_margin",
        "pi_weight_competition",
        "pi_weight_logistics",
        "pi_weight_compliance",
        "pi_weight_content",
    )
    def _check_pi_weights(self):
        for record in self:
            total = sum(
                [
                    record.pi_weight_demand,
                    record.pi_weight_growth,
                    record.pi_weight_margin,
                    record.pi_weight_competition,
                    record.pi_weight_logistics,
                    record.pi_weight_compliance,
                    record.pi_weight_content,
                ]
            )
            if abs(total - 100.0) > 0.01:
                raise ValidationError("产品智能评分权重之和必须为 100%。")
