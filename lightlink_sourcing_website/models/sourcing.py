from odoo import fields, models


class PublishingProject(models.Model):
    _inherit = "psc.publishing.project"

    website_inquiry_enabled = fields.Boolean(
        string="接收网站采购询盘",
        help="启用后，当前网站的采购询盘会进入此运营项目。",
    )
    website_public_name = fields.Char(string="网站公开名称", translate=True)
    website_public_summary = fields.Text(string="网站公开简介", translate=True)
    website_service_email = fields.Char(string="网站服务邮箱")
    website_whatsapp_url = fields.Char(string="WhatsApp 链接")


class CustomerRequirement(models.Model):
    _inherit = "psc.customer.requirement"

    request_type = fields.Selection(
        [
            ("find_supplier", "寻找供应商"),
            ("manage_supplier", "供应商管理"),
            ("product_development", "产品开发"),
            ("private_label", "定制/自有品牌"),
        ],
        string="服务需求",
    )
    product_category = fields.Char(string="产品类别")
    target_unit_price = fields.Monetary(string="目标单价", currency_field="currency_id")
    customization_requirements = fields.Text(string="定制要求")
    packaging_requirements = fields.Text(string="包装要求")
    incoterm = fields.Char(string="贸易条款")
    sample_required = fields.Boolean(string="需要样品")
    reference_url = fields.Char(string="参考产品链接")
    website_source_url = fields.Char(string="网站来源页面")
    website_language = fields.Char(string="网站语言")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "psc_customer_requirement_attachment_rel",
        "requirement_id",
        "attachment_id",
        string="客户附件",
    )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    sourcing_inquiry_only = fields.Boolean(
        string="仅接受采购询盘",
        help="网站产品页显示采购询价入口，不作为普通零售商品宣传。",
    )
