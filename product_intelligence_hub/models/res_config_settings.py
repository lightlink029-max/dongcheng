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
    pi_qdrant_enabled = fields.Boolean(
        string="启用网站以图搜产品",
        config_parameter="product_intelligence_hub.qdrant_enabled",
    )
    pi_qdrant_url = fields.Char(
        string="Qdrant 集群地址",
        config_parameter="product_intelligence_hub.qdrant_url",
    )
    pi_qdrant_api_key = fields.Char(
        string="Qdrant API Key",
        config_parameter="product_intelligence_hub.qdrant_api_key",
    )
    pi_qdrant_collection = fields.Char(
        string="向量集合",
        default="odoo_product_images",
        config_parameter="product_intelligence_hub.qdrant_collection",
    )
    pi_qdrant_image_model = fields.Char(
        string="向量生成方式",
        default="local/pillow-visual-v1",
        config_parameter="product_intelligence_hub.qdrant_image_model",
    )
    pi_qdrant_vector_dimension = fields.Integer(
        string="向量维度",
        default=512,
        config_parameter="product_intelligence_hub.qdrant_vector_dimension",
    )
    pi_qdrant_result_limit = fields.Integer(
        string="搜索结果数",
        default=12,
        config_parameter="product_intelligence_hub.qdrant_result_limit",
    )
    pi_qdrant_score_threshold = fields.Float(
        string="最低相似度",
        default=0.18,
        config_parameter="product_intelligence_hub.qdrant_score_threshold",
    )
    pi_qdrant_upload_limit_mb = fields.Integer(
        string="上传上限（MB）",
        default=5,
        config_parameter="product_intelligence_hub.qdrant_upload_limit_mb",
    )
    pi_qdrant_rate_limit = fields.Integer(
        string="每分钟搜索上限",
        default=20,
        config_parameter="product_intelligence_hub.qdrant_rate_limit",
    )

    def action_pi_qdrant_test_connection(self):
        self.ensure_one()
        self.env["product.image.search.service"].test_connection()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Qdrant 连接正常",
                "message": "集群可访问，图片向量集合已经准备完成。",
                "type": "success",
                "sticky": False,
            },
        }

    def action_pi_qdrant_reindex_all(self):
        self.ensure_one()
        count = self.env["product.template"].search_count([])
        self.env["product.template"].search([]).with_context(
            pi_skip_image_search_dirty=True
        ).write({"pi_image_search_state": "pending", "pi_image_search_error": False})
        self.env["product.image.search.service"].action_index_pending_products(limit=20)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "商品图片索引已启动",
                "message": f"已将 {count} 个商品加入索引队列，系统会在后台分批完成。",
                "type": "success",
                "sticky": False,
            },
        }

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
