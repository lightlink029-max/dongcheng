import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


REQUEST_TYPES = [
    ("find_supplier", "寻找供应商 / 采购代理"),
    ("manage_supplier", "管理已有供应商"),
    ("product_development", "产品开发"),
    ("private_label", "定制 / 自有品牌"),
    ("quality_inspection", "验货与质量管理"),
    ("shipping_consolidation", "集货与国际物流"),
    ("dropshipping", "一件代发"),
    ("design_customization", "产品与包装设计"),
    ("photography_video", "产品摄影与视频"),
    ("warehousing_kitting", "仓储、换标与组合包装"),
    ("supplier_audit", "工厂与供应商审核"),
    ("marketplace_prep", "电商平台 / FBA 备货"),
]


class Website(models.Model):
    _inherit = "website"

    sourcing_enabled = fields.Boolean(string="独立采购服务网站")
    sourcing_brand_name = fields.Char(
        string="采购网站品牌名", default="LightLink Global Sourcing", translate=True,
    )
    sourcing_tagline = fields.Char(
        string="采购网站标语",
        default="China sourcing, product development and delivery control",
        translate=True,
    )
    sourcing_service_email = fields.Char(string="采购服务邮箱")
    sourcing_whatsapp_url = fields.Char(string="采购服务 WhatsApp 链接")
    sourcing_project_ids = fields.One2many(
        "psc.publishing.project", "website_id", string="采购运营项目",
    )
    sourcing_asset_ids = fields.One2many(
        "ll.sourcing.asset", "website_id", string="网站图片资产",
    )
    sourcing_offering_ids = fields.One2many(
        "ll.sourcing.offering", "website_id", string="服务与解决方案",
    )

    @api.model
    def initialize_lightlink_sourcing_site(self):
        """Finish the idempotent links that XML data cannot express safely."""
        website = self.env.ref(
            "lightlink_sourcing_website.website_global_sourcing", raise_if_not_found=False,
        )
        if not website:
            return False

        website_values = {"sourcing_enabled": True}
        language = self.env["res.lang"].search([
            ("code", "in", ("en_US", "en_GB")), ("active", "=", True),
        ], order="code desc", limit=1)
        chinese_language = self.env["res.lang"].search([
            ("code", "in", ("zh_CN", "zh_TW")), ("active", "=", True),
        ], order="code", limit=1)
        if "homepage_url" in website._fields:
            website_values["homepage_url"] = "/sourcing"
        if language and "default_lang_id" in website._fields:
            website_values["default_lang_id"] = language.id
        if language and "language_ids" in website._fields:
            website_values["language_ids"] = [(6, 0, (language | chinese_language).ids)]
        website.write(website_values)

        managed_menus = self.env["website.menu"]
        for xmlid in (
            "menu_sourcing_home",
            "menu_sourcing_services",
            "menu_sourcing_solutions",
            "menu_sourcing_pricing",
            "menu_sourcing_products",
            "menu_sourcing_insights",
            "menu_sourcing_about",
            "menu_sourcing_quote",
        ):
            menu = self.env.ref(
                "lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False,
            )
            if menu:
                managed_menus |= menu
        root_menu = website.menu_id
        if not root_menu:
            root_menu = self.env["website.menu"].create({
                "name": "Main Menu", "url": "/", "website_id": website.id,
            })
        for menu in managed_menus:
            menu.write({"website_id": website.id, "parent_id": root_menu.id})

        product_line = self.env["psc.product.line"].search([
            ("code", "=", "lightlink_global_sourcing"),
        ], limit=1)
        if not product_line:
            product_line = self.env["psc.product.line"].create({
                "name": "LightLink 全球综合采购",
                "code": "lightlink_global_sourcing",
                "brand_name": "LightLink Global Sourcing",
                "website_id": website.id,
                "target_customer": "Importers, wholesalers, retailers, online sellers and private-label buyers.",
                "key_selling_points": "Supplier sourcing, development, quality control, consolidation and delivery coordination.",
                "compliance_notes": "Only verified supplier, product, certification, price and delivery facts may be published.",
            })
        elif product_line.website_id != website:
            product_line.website_id = website

        channel = self.env["psc.publishing.channel"].search([
            ("name", "=", "LightLink Global Sourcing Website"),
            ("platform", "=", "website"),
        ], limit=1)
        if not channel:
            channel = self.env["psc.publishing.channel"].create({
                "name": "LightLink Global Sourcing Website",
                "platform": "website",
                "default_instructions": "English-first B2B sourcing content. Publish only verified operational evidence.",
            })

        country = self.env["res.country"].search([("code", "=", "US")], limit=1)
        currency = self.env["res.currency"].search([("name", "=", "USD")], limit=1)
        market = self.env["psc.target.market"].search([
            ("name", "=", "Global English B2B Buyers"),
        ], limit=1)
        if not market and country and language and currency:
            market = self.env["psc.target.market"].create({
                "name": "Global English B2B Buyers",
                "country_id": country.id,
                "lang_id": language.id,
                "currency_id": currency.id,
                "customer_type": "b2b",
                "customer_profile": "Importers and business buyers seeking accountable sourcing from China.",
                "keywords": "China sourcing, supplier management, product development, quality inspection, shipping",
            })

        project = self.env["psc.publishing.project"].search([
            ("website_id", "=", website.id),
        ], order="create_date desc, id desc", limit=1)
        if not project and market:
            project = self.env["psc.publishing.project"].create({
                "name": "LightLink 全球采购服务运营项目",
                "product_line_id": product_line.id,
                "market_ids": [(6, 0, market.ids)],
                "channel_ids": [(6, 0, channel.ids)],
                "website_id": website.id,
                "website_inquiry_enabled": True,
                "website_public_name": "Source from China with a clear plan and accountable execution.",
                "website_public_summary": "From supplier discovery and product development to quality control, consolidation and delivery coordination.",
                "operation_state": "active",
                "business_goal": "Acquire qualified international sourcing inquiries and manage them through one traceable Odoo workflow.",
                "content_brief": "Explain practical China sourcing decisions with verified evidence and clear buyer next steps.",
            })
        if project:
            self.env["psc.publishing.project"].search([
                ("website_id", "=", website.id),
                ("id", "!=", project.id),
                ("website_inquiry_enabled", "=", True),
            ]).write({"website_inquiry_enabled": False})
            project.write({"website_inquiry_enabled": True, "website_id": website.id})
        return True

    @api.model
    def _cleanup_lightlink_sourcing_bootstrap_menus(self):
        """Remove menus copied by Odoo when the dedicated website is created."""
        website = self.env.ref(
            "lightlink_sourcing_website.website_global_sourcing", raise_if_not_found=False,
        )
        if not website or not website.menu_id:
            return 0

        managed_menus = self.env["website.menu"]
        for xmlid in (
            "menu_sourcing_home",
            "menu_sourcing_services",
            "menu_sourcing_solutions",
            "menu_sourcing_pricing",
            "menu_sourcing_products",
            "menu_sourcing_insights",
            "menu_sourcing_about",
            "menu_sourcing_quote",
        ):
            menu = self.env.ref(
                "lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False,
            )
            if menu:
                managed_menus |= menu

        bootstrap_menus = self.env["website.menu"].search([
            ("website_id", "=", website.id),
            ("id", "not in", (website.menu_id | managed_menus).ids),
        ])
        count = len(bootstrap_menus)
        bootstrap_menus.unlink()
        return count


class SourcingAsset(models.Model):
    _name = "ll.sourcing.asset"
    _description = "采购网站图片资产"
    _order = "sequence, id"

    name = fields.Char(string="资产名称", required=True, translate=True)
    key = fields.Char(string="资产位代码", required=True, index=True)
    website_id = fields.Many2one(
        "website", string="网站", required=True, ondelete="cascade", index=True,
    )
    image = fields.Binary(string="图片", required=True, attachment=True)
    alt_text = fields.Char(string="图片替代文字", required=True, translate=True)
    caption = fields.Text(string="图片说明", translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _website_key_unique = models.Constraint(
        "UNIQUE(website_id, key)", "同一网站的图片资产位代码不能重复。",
    )

    @api.constrains("key")
    def _check_key(self):
        for record in self:
            if not re.fullmatch(r"[a-z0-9_]+", record.key or ""):
                raise ValidationError(_("资产位代码只能包含小写字母、数字和下划线。"))


class SourcingOffering(models.Model):
    _name = "ll.sourcing.offering"
    _description = "采购网站服务与解决方案"
    _order = "kind, sequence, id"

    name = fields.Char(string="名称", required=True, translate=True)
    slug = fields.Char(string="网址短名", required=True, index=True)
    kind = fields.Selection([
        ("service", "服务"),
        ("solution", "客户方案"),
        ("plan", "服务方案"),
    ], string="内容类型", required=True, default="service", index=True)
    website_id = fields.Many2one(
        "website", string="网站", required=True, ondelete="cascade", index=True,
    )
    kicker = fields.Char(string="栏目眉题", translate=True)
    summary = fields.Text(string="卡片摘要", required=True, translate=True)
    introduction = fields.Text(string="详情页介绍", translate=True)
    benefits = fields.Text(
        string="核心能力", translate=True,
        help="每行一项，网站详情页会显示为清单。",
    )
    process = fields.Text(
        string="交付步骤", translate=True,
        help="每行一步，网站详情页会按顺序显示。",
    )
    icon = fields.Char(
        string="图标名称", default="check",
        help="使用 Font Awesome 名称，例如 search、cubes、ship。",
    )
    image_asset_id = fields.Many2one("ll.sourcing.asset", string="主图")
    price_label = fields.Char(
        string="价格说明", translate=True,
        help="例如 Free sourcing / Service fee by quotation。",
    )
    badge = fields.Char(string="角标", translate=True)
    request_type = fields.Selection(REQUEST_TYPES, string="默认询盘类型")
    sequence = fields.Integer(default=10)
    featured = fields.Boolean(string="首页展示", default=True)
    active = fields.Boolean(default=True)

    _website_slug_unique = models.Constraint(
        "UNIQUE(website_id, slug)", "同一网站的网址短名不能重复。",
    )

    @api.constrains("slug")
    def _check_slug(self):
        for record in self:
            if not re.fullmatch(r"[a-z0-9-]+", record.slug or ""):
                raise ValidationError(_("网址短名只能包含小写字母、数字和连字符。"))


class PublishingProject(models.Model):
    _inherit = "psc.publishing.project"

    website_id = fields.Many2one(
        "website", string="独立采购官网", index=True,
        help="网站询盘将直接归属到该运营项目，不再通过产品线间接推断。",
    )
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

    request_type = fields.Selection(REQUEST_TYPES, string="服务需求")
    product_category = fields.Char(string="产品类别")
    business_stage = fields.Selection([
        ("idea", "只有产品想法"),
        ("testing", "正在打样 / 测试"),
        ("buying", "已经采购"),
        ("scaling", "正在扩大采购"),
    ], string="业务阶段")
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
