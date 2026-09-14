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
    sourcing_content_page_ids = fields.One2many(
        "ll.sourcing.content.page", "website_id", string="采购网站内容页面",
    )
    sourcing_metric_ids = fields.One2many(
        "ll.sourcing.metric", "website_id", string="可信经营数据",
    )
    sourcing_testimonial_ids = fields.One2many(
        "ll.sourcing.testimonial", "website_id", string="客户评价",
    )
    sourcing_payment_method_ids = fields.One2many(
        "ll.sourcing.payment.method", "website_id", string="付款方式",
    )
    sourcing_footer_column_ids = fields.One2many(
        "ll.sourcing.footer.column", "website_id", string="采购网站页脚",
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

        child_menu_map = {
            "menu_sourcing_services": (
                "menu_sourcing_service_procurement",
                "menu_sourcing_service_dropshipping",
                "menu_sourcing_service_photo_design",
                "menu_sourcing_pricing",
            ),
            "menu_sourcing_solutions": (
                "menu_sourcing_solution_private_label",
                "menu_sourcing_solution_product_development",
                "menu_sourcing_solution_shipping",
                "menu_sourcing_solution_fba",
                "menu_sourcing_solution_quality",
                "menu_sourcing_solution_credit",
                "menu_sourcing_solution_affiliate",
            ),
            "menu_sourcing_insights": (
                "menu_sourcing_blog",
                "menu_sourcing_import_guide",
                "menu_sourcing_agent_guide",
                "menu_sourcing_yiwu",
            ),
            "menu_sourcing_about": (
                "menu_sourcing_payment",
                "menu_sourcing_about_us",
                "menu_sourcing_founder",
            ),
        }
        for parent_xmlid, child_xmlids in child_menu_map.items():
            parent = self.env.ref(
                "lightlink_sourcing_website.%s" % parent_xmlid,
                raise_if_not_found=False,
            )
            if not parent:
                continue
            for child_xmlid in child_xmlids:
                child = self.env.ref(
                    "lightlink_sourcing_website.%s" % child_xmlid,
                    raise_if_not_found=False,
                )
                if child:
                    child.write({"website_id": website.id, "parent_id": parent.id})

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
            "menu_sourcing_service_procurement",
            "menu_sourcing_service_dropshipping",
            "menu_sourcing_service_photo_design",
            "menu_sourcing_solutions",
            "menu_sourcing_solution_private_label",
            "menu_sourcing_solution_product_development",
            "menu_sourcing_solution_shipping",
            "menu_sourcing_solution_fba",
            "menu_sourcing_solution_quality",
            "menu_sourcing_solution_credit",
            "menu_sourcing_solution_affiliate",
            "menu_sourcing_pricing",
            "menu_sourcing_products",
            "menu_sourcing_insights",
            "menu_sourcing_blog",
            "menu_sourcing_import_guide",
            "menu_sourcing_agent_guide",
            "menu_sourcing_yiwu",
            "menu_sourcing_about",
            "menu_sourcing_payment",
            "menu_sourcing_about_us",
            "menu_sourcing_founder",
            "menu_sourcing_quote",
        ):
            menu = self.env.ref(
                "lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False,
            )
            if menu:
                managed_menus |= menu

        unmanaged_menus = self.env["website.menu"].search([
            ("website_id", "=", website.id),
            ("id", "not in", (website.menu_id | managed_menus).ids),
        ])
        bootstrap_urls = {"/", "/shop", "/contactus", "/event", "/jobs"}
        bootstrap_menus = unmanaged_menus.filtered(
            lambda menu: menu.url in bootstrap_urls
        )
        count = len(bootstrap_menus)
        bootstrap_menus.unlink()
        return count


class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    sourcing_image_asset_id = fields.Many2one(
        "ll.sourcing.asset",
        string="采购分类页图片",
        ondelete="set null",
        help="采购分类页公开显示的图片；从网站图片资产中选择。",
    )
    sourcing_hero_subtitle = fields.Char(
        string="分类页副标题",
        translate=True,
        help="显示在采购产品分类落地页主标题下方。",
    )
    sourcing_highlight_1 = fields.Char(string="分类亮点 1", translate=True)
    sourcing_highlight_2 = fields.Char(string="分类亮点 2", translate=True)
    sourcing_highlight_3 = fields.Char(string="分类亮点 3", translate=True)
    sourcing_inquiry_heading = fields.Char(
        string="询盘表单标题", translate=True,
    )


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


class SourcingContentPage(models.Model):
    _name = "ll.sourcing.content.page"
    _description = "采购网站内容页面"
    _order = "sequence, id"

    name = fields.Char(string="页面标题", required=True, translate=True)
    code = fields.Char(string="页面代码", required=True, index=True)
    website_id = fields.Many2one(
        "website", string="网站", required=True, ondelete="cascade", index=True,
    )
    kicker = fields.Char(string="栏目眉题", translate=True)
    summary = fields.Text(string="页面摘要", required=True, translate=True)
    body_html = fields.Html(string="页面正文", required=True, translate=True)
    image_asset_id = fields.Many2one("ll.sourcing.asset", string="主图")
    chapter_ids = fields.One2many(
        "ll.sourcing.guide.chapter", "page_id", string="指南章节",
    )
    sequence = fields.Integer(default=10)
    published = fields.Boolean(string="网站发布", default=False, index=True)
    active = fields.Boolean(default=True)

    _website_code_unique = models.Constraint(
        "UNIQUE(website_id, code)", "同一网站的页面代码不能重复。",
    )

    @api.constrains("code")
    def _check_code(self):
        for record in self:
            if not re.fullmatch(r"[a-z0-9-]+", record.code or ""):
                raise ValidationError(_("页面代码只能包含小写字母、数字和连字符。"))


class SourcingGuideChapter(models.Model):
    _name = "ll.sourcing.guide.chapter"
    _description = "采购指南章节"
    _order = "sequence, id"

    name = fields.Char(string="章节标题", required=True, translate=True)
    page_id = fields.Many2one(
        "ll.sourcing.content.page", string="所属指南", required=True,
        ondelete="cascade", index=True,
    )
    summary = fields.Text(string="章节摘要", required=True, translate=True)
    reading_time = fields.Char(string="阅读时长", translate=True)
    video_time = fields.Char(string="视频时长", translate=True)
    target_url = fields.Char(
        string="详情链接",
        help="可链接到 Odoo 博客文章、知识页或外部视频；留空时只展示章节说明。",
    )
    sequence = fields.Integer(default=10)
    published = fields.Boolean(string="网站发布", default=True, index=True)
    active = fields.Boolean(default=True)


class SourcingMetric(models.Model):
    _name = "ll.sourcing.metric"
    _description = "采购网站可信经营数据"
    _order = "sequence, id"

    value_text = fields.Char(string="展示数值", required=True, translate=True)
    label = fields.Char(string="指标说明", required=True, translate=True)
    website_id = fields.Many2one(
        "website", string="网站", required=True, ondelete="cascade", index=True,
    )
    evidence_note = fields.Text(string="核实依据", help="填写内部记录、报表口径或可复核说明。")
    evidence_url = fields.Char(string="证据链接")
    verified = fields.Boolean(string="已核实", default=False, index=True)
    published = fields.Boolean(string="网站发布", default=False, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.constrains("published", "verified", "evidence_note")
    def _check_publish_evidence(self):
        for record in self:
            if record.published and (not record.verified or not record.evidence_note):
                raise ValidationError(_("经营数据发布前必须完成核实并填写核实依据。"))


class SourcingTestimonial(models.Model):
    _name = "ll.sourcing.testimonial"
    _description = "采购网站客户评价"
    _order = "sequence, id"

    client_name = fields.Char(string="客户姓名", required=True, translate=True)
    client_role = fields.Char(string="客户职务", translate=True)
    company_name = fields.Char(string="客户公司", translate=True)
    quote = fields.Text(string="评价内容", required=True, translate=True)
    client_image = fields.Binary(string="客户图片", attachment=True)
    website_id = fields.Many2one(
        "website", string="网站", required=True, ondelete="cascade", index=True,
    )
    source_url = fields.Char(string="来源链接")
    permission_note = fields.Text(string="授权与核实说明")
    permission_confirmed = fields.Boolean(string="已取得公开授权", default=False)
    verified = fields.Boolean(string="内容已核实", default=False, index=True)
    published = fields.Boolean(string="网站发布", default=False, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.constrains("published", "permission_confirmed", "verified", "permission_note")
    def _check_publish_permission(self):
        for record in self:
            if record.published and (
                not record.permission_confirmed
                or not record.verified
                or not record.permission_note
            ):
                raise ValidationError(_("客户评价发布前必须确认授权、完成核实并填写说明。"))


class SourcingPaymentMethod(models.Model):
    _name = "ll.sourcing.payment.method"
    _description = "采购网站付款方式"
    _order = "sequence, id"

    name = fields.Char(string="付款方式", required=True, translate=True)
    summary = fields.Text(string="适用说明", required=True, translate=True)
    instructions = fields.Html(string="付款说明", required=True, translate=True)
    fee_note = fields.Char(string="费用说明", translate=True)
    verification_notice = fields.Text(string="防诈骗核验提示", required=True, translate=True)
    website_id = fields.Many2one(
        "website", string="网站", required=True, ondelete="cascade", index=True,
    )
    published = fields.Boolean(string="网站发布", default=False, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class SourcingFooterColumn(models.Model):
    _name = "ll.sourcing.footer.column"
    _description = "采购网站页脚栏目"
    _order = "sequence, id"

    name = fields.Char(string="栏目名称", required=True, translate=True)
    column_type = fields.Selection([
        ("links", "链接列表"),
        ("content", "文本内容"),
    ], string="栏目类型", required=True, default="links")
    website_id = fields.Many2one(
        "website", string="网站", required=True, ondelete="cascade", index=True,
    )
    body_html = fields.Html(string="栏目内容", translate=True)
    link_ids = fields.One2many(
        "ll.sourcing.footer.link", "column_id", string="页脚链接",
    )
    published = fields.Boolean(string="网站发布", default=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class SourcingFooterLink(models.Model):
    _name = "ll.sourcing.footer.link"
    _description = "采购网站页脚链接"
    _order = "sequence, id"

    name = fields.Char(string="链接名称", required=True, translate=True)
    url = fields.Char(string="链接地址", required=True)
    column_id = fields.Many2one(
        "ll.sourcing.footer.column", string="页脚栏目", required=True,
        ondelete="cascade", index=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


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
