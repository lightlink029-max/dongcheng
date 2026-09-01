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
    pi_oss_enabled = fields.Boolean(string="启用阿里云 OSS", config_parameter="product_intelligence_hub.oss_enabled")
    pi_oss_endpoint = fields.Char(string="Endpoint", config_parameter="product_intelligence_hub.oss_endpoint")
    pi_oss_bucket = fields.Char(string="Bucket", config_parameter="product_intelligence_hub.oss_bucket")
    pi_oss_access_key_id = fields.Char(string="AccessKey ID", config_parameter="product_intelligence_hub.oss_access_key_id")
    pi_oss_access_key_secret = fields.Char(string="AccessKey Secret", config_parameter="product_intelligence_hub.oss_access_key_secret")
    pi_oss_prefix = fields.Char(string="存储目录", default="product-intelligence", config_parameter="product_intelligence_hub.oss_prefix")
    pi_oss_public_base_url = fields.Char(string="公开访问域名", config_parameter="product_intelligence_hub.oss_public_base_url")
    pi_oss_delete_on_unlink = fields.Boolean(string="删除记录时同步删除 OSS 图片", config_parameter="product_intelligence_hub.oss_delete_on_unlink")

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
