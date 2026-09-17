import base64
import gzip
import hashlib
import html
import json
import re
from urllib.parse import urlencode

from odoo import _, api, fields, models, tools
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

    ll_business_type = fields.Selection([
        ("general", "通用企业网站"),
        ("sourcing_agency", "采购代理网站"),
        ("factory", "工厂网站"),
    ], string="网站业务类型", required=True, default="general", index=True)
    ll_operations_note = fields.Text(
        string="运营说明",
        help="记录该网站的定位、负责人和当前运营重点，仅供内部使用。",
    )
    sourcing_enabled = fields.Boolean(string="独立采购服务网站")
    sourcing_brand_name = fields.Char(
        string="网站品牌名", translate=True,
    )
    sourcing_tagline = fields.Char(
        string="网站标语", translate=True,
    )
    sourcing_service_email = fields.Char(string="服务邮箱")
    sourcing_whatsapp_url = fields.Char(string="WhatsApp 链接")
    sourcing_project_ids = fields.One2many(
        "psc.publishing.project", "website_id", string="网站运营项目",
    )
    sourcing_asset_ids = fields.One2many(
        "ll.sourcing.asset", "website_id", string="网站图片资产",
    )
    sourcing_offering_ids = fields.One2many(
        "ll.sourcing.offering", "website_id", string="服务与解决方案",
    )
    sourcing_content_page_ids = fields.One2many(
        "ll.sourcing.content.page", "website_id", string="网站内容页面",
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
        "ll.sourcing.footer.column", "website_id", string="网站页脚",
    )
    sourcing_mirror_footer_html = fields.Html(
        string="采购网站页脚源码",
        sanitize=False,
        translate=True,
        help="由本地采购网站镜像初始化，可在后台继续编辑。",
    )
    ll_factory_capability_ids = fields.One2many(
        "ll.website.factory.capability", "website_id", string="工厂能力",
    )
    ll_product_presentation_ids = fields.One2many(
        "ll.website.product.presentation", "website_id", string="网站产品内容",
    )
    ll_source_lead_ids = fields.One2many(
        "crm.lead", "ll_source_website_id", string="网站线索",
    )
    ll_source_requirement_ids = fields.One2many(
        "psc.customer.requirement", "website_id", string="网站询盘",
    )
    ll_source_touchpoint_ids = fields.One2many(
        "psc.customer.touchpoint", "website_id", string="网站触点",
    )
    ll_menu_ids = fields.One2many(
        "website.menu", "website_id", string="网站导航",
    )
    ll_product_category_ids = fields.One2many(
        "product.public.category", "website_id", string="网站产品分类",
    )
    ll_project_count = fields.Integer(string="运营项目", compute="_compute_ll_operations_counts")
    ll_page_count = fields.Integer(string="网站页面", compute="_compute_ll_operations_counts")
    ll_asset_count = fields.Integer(string="图片素材", compute="_compute_ll_operations_counts")
    ll_inquiry_count = fields.Integer(string="网站询盘", compute="_compute_ll_operations_counts")
    ll_factory_capability_count = fields.Integer(
        string="工厂能力", compute="_compute_ll_operations_counts",
    )
    ll_product_presentation_count = fields.Integer(
        string="产品内容", compute="_compute_ll_operations_counts",
    )

    def _compute_ll_operations_counts(self):
        for website in self:
            website.ll_project_count = len(website.sourcing_project_ids)
            website.ll_page_count = len(website.sourcing_content_page_ids)
            website.ll_asset_count = len(website.sourcing_asset_ids)
            website.ll_inquiry_count = len(website.ll_source_requirement_ids)
            website.ll_factory_capability_count = len(website.ll_factory_capability_ids)
            website.ll_product_presentation_count = len(website.ll_product_presentation_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if "ll_business_type" in values and "sourcing_enabled" not in values:
                values["sourcing_enabled"] = values["ll_business_type"] == "sourcing_agency"
        return super().create(vals_list)

    def write(self, values):
        if "ll_business_type" in values and "sourcing_enabled" not in values:
            values = dict(values, sourcing_enabled=values["ll_business_type"] == "sourcing_agency")
        return super().write(values)

    def _ll_open_related(self, model, name, domain=None):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "%s · %s" % (self.display_name, name),
            "res_model": model,
            "view_mode": "list,form",
            "domain": domain or [("website_id", "=", self.id)],
            "context": {"default_website_id": self.id},
            "target": "current",
        }

    def action_ll_open_projects(self):
        return self._ll_open_related("psc.publishing.project", _("网站运营项目"))

    def action_ll_open_pages(self):
        return self._ll_open_related("ll.sourcing.content.page", _("网站页面与指南"))

    def action_ll_open_assets(self):
        return self._ll_open_related("ll.sourcing.asset", _("网站图片素材"))

    def action_ll_open_inquiries(self):
        return self._ll_open_related("psc.customer.requirement", _("网站询盘"))

    def action_ll_open_factory_capabilities(self):
        return self._ll_open_related("ll.website.factory.capability", _("工厂能力"))

    def action_ll_open_product_presentations(self):
        return self._ll_open_related("ll.website.product.presentation", _("网站产品内容"))

    def action_ll_open_public_site(self):
        self.ensure_one()
        base_url = (self.domain or self.get_base_url()).rstrip("/")
        path = self.homepage_url or (
            "/sourcing" if self.ll_business_type == "sourcing_agency" else "/"
        )
        if not path.startswith("/"):
            path = "/%s" % path
        switch_url = "%s/website/force/%s?%s" % (
            base_url,
            self.id,
            urlencode({"path": path}),
        )
        return {"type": "ir.actions.act_url", "url": switch_url, "target": "new"}

    @api.model
    def initialize_lightlink_sourcing_site(self):
        """Finish the idempotent links that XML data cannot express safely."""
        website = self.env.ref(
            "lightlink_sourcing_website.website_global_sourcing", raise_if_not_found=False,
        )
        if not website:
            return False

        website_values = {
            "sourcing_enabled": True,
            "ll_business_type": "sourcing_agency",
        }
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
    def sync_lightlink_sourcing_mirror(self):
        """Replace the unused demo website content with the local mirror bundle."""
        website = self.env.ref(
            "lightlink_sourcing_website.website_global_sourcing", raise_if_not_found=False,
        )
        try:
            bundle_path = tools.file_path(
                "lightlink_sourcing_website/data/mirror_pages.json.gz"
            )
        except FileNotFoundError:
            bundle_path = False
        if not website or not bundle_path:
            return False
        with gzip.open(bundle_path, "rt", encoding="utf-8") as archive:
            payload = json.load(archive)
        if payload.get("schema_version") != 1 or not payload.get("pages"):
            raise ValidationError(_("采购网站镜像数据包无效或为空。"))

        # These records belonged only to the pre-launch demo website.  Project,
        # CRM, product, purchase and sales records are deliberately untouched.
        for model_name in (
            "ll.sourcing.content.page",
            "ll.sourcing.offering",
            "ll.sourcing.metric",
            "ll.sourcing.testimonial",
            "ll.sourcing.payment.method",
            "ll.sourcing.footer.column",
            "ll.sourcing.asset",
        ):
            self.env[model_name].search([("website_id", "=", website.id)]).unlink()

        # Remove only the public categories seeded by the retired demo site.
        # User-created categories and every product record remain untouched.
        demo_categories = self.env["product.public.category"]
        for xmlid in (
            "product_category_apparel",
            "product_category_furniture",
            "product_category_bags_cases",
            "product_category_bags_handbags",
            "product_category_bags_backpacks",
            "product_category_bags_toiletry",
            "product_category_bags_travel",
            "product_category_bags_pouches",
            "product_category_bags_special",
            "product_category_beauty",
            "product_category_toys",
            "product_category_sports",
            "product_category_home",
            "product_category_garden_tools",
            "product_category_electronics",
            "product_category_pet",
            "product_category_mother_kids",
            "product_category_hardware",
            "product_category_office",
            "product_category_automotive",
            "product_category_industrial",
            "product_category_packaging",
            "product_category_outdoors",
            "product_category_jewelry",
            "product_category_lighting",
            "product_category_other",
        ):
            category = self.env.ref(
                "lightlink_sourcing_website.%s" % xmlid,
                raise_if_not_found=False,
            )
            if category:
                demo_categories |= category
        demo_categories.unlink()

        Page = self.env["ll.sourcing.content.page"].with_context(lang="en_US")
        values = []
        for item in payload["pages"]:
            source_path = item["path"]
            code_suffix = hashlib.sha1(source_path.encode("utf-8")).hexdigest()[:16]
            values.append({
                "name": item["title"],
                "code": "mirror-%s" % code_suffix,
                "website_id": website.id,
                "kicker": "LightLink Global Sourcing",
                "summary": item.get("description") or item["title"],
                "body_html": item["body_html"],
                "source_path": source_path,
                "source_file": item.get("source_file"),
                "source_hash": item["source_hash"],
                "source_stylesheets": "\n".join(item.get("stylesheets") or []),
                "source_style_hash": item.get("style_hash") or False,
                "page_type": item.get("page_type") or "page",
                "imported_from_mirror": True,
                "published": True,
                "active": True,
            })
        for start in range(0, len(values), 25):
            Page.create(values[start:start + 25])

        website.write({
            "sourcing_enabled": True,
            "ll_business_type": "sourcing_agency",
            "homepage_url": "/sourcing",
            "sourcing_mirror_footer_html": payload.get("footer_html") or False,
        })
        project = self.env["psc.publishing.project"].browse(5).exists()
        if project:
            project.write({
                "website_id": website.id,
                "website_inquiry_enabled": True,
            })
        return len(values)

    @api.model
    def seed_lightlink_sourcing_catalog(self):
        """Create editable categories and images represented by the mirror pages."""
        website = self.env.ref(
            "lightlink_sourcing_website.website_global_sourcing",
            raise_if_not_found=False,
        )
        if not website:
            return 0
        catalog_path = tools.file_path(
            "lightlink_sourcing_website/data/mirror_catalog.json"
        )
        with open(catalog_path, encoding="utf-8") as stream:
            payload = json.load(stream)
        if payload.get("schema_version") != 1:
            raise ValidationError(_("采购网站产品分类数据包无效。"))

        Category = self.env["product.public.category"].with_context(
            active_test=False, lang="en_US",
        )
        created = 0

        def image_value(relative_path):
            if not relative_path:
                return False
            module_path = relative_path.lstrip("/")
            if not module_path.startswith("lightlink_sourcing_website/"):
                module_path = "lightlink_sourcing_website/%s" % module_path
            try:
                with tools.file_open(module_path, "rb") as stream:
                    return base64.b64encode(stream.read())
            except (FileNotFoundError, OSError):
                return False

        def create_if_missing(item, parent=False, sequence=10):
            nonlocal created
            source_key = item["source_key"]
            category = Category.search([
                ("website_id", "=", website.id),
                ("sourcing_source_key", "=", source_key),
            ], limit=1)
            if category:
                return category
            description = item.get("description") or ""
            values = {
                "name": item["name"],
                "website_id": website.id,
                "parent_id": parent.id if parent else False,
                "sequence": sequence,
                "website_description": (
                    "<p>%s</p>" % html.escape(description) if description else False
                ),
                "sourcing_source_key": source_key,
                "sourcing_source_path": item["source_path"],
                "sourcing_source_name": item["name"],
                "sourcing_source_image_path": item.get("image_path") or False,
                "sourcing_imported_from_mirror": True,
            }
            image = image_value(item.get("image_path"))
            if image:
                values["image_1920"] = image
            category = Category.create(values)
            created += 1
            translated = {}
            if item.get("name_zh"):
                translated["name"] = item["name_zh"]
            if item.get("description_zh"):
                translated["website_description"] = (
                    "<p>%s</p>" % html.escape(item["description_zh"])
                )
            if translated:
                category.with_context(lang="zh_CN").write(translated)
            return category

        for root_sequence, item in enumerate(payload.get("categories", []), 1):
            root_item = {
                "source_key": item["path"],
                "source_path": item["path"],
                "name": item["name"],
                "name_zh": item.get("name_zh"),
                "image_path": item.get("icon_path"),
            }
            root = create_if_missing(root_item, sequence=root_sequence * 10)
            for child_sequence, child in enumerate(item.get("children", []), 1):
                child_item = dict(child)
                child_item.update({
                    "source_key": "%s#%s" % (item["path"], child["key"]),
                    "source_path": item["path"],
                })
                create_if_missing(
                    child_item, parent=root, sequence=child_sequence * 10,
                )
        return created

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
    sourcing_source_key = fields.Char(
        string="镜像分类标识", index=True, readonly=True, copy=False,
    )
    sourcing_source_path = fields.Char(
        string="对应公开页面", index=True, readonly=True, copy=False,
    )
    sourcing_source_name = fields.Char(
        string="原始分类名称", readonly=True, copy=False,
    )
    sourcing_source_image_path = fields.Char(
        string="原始图片路径", readonly=True, copy=False,
    )
    sourcing_imported_from_mirror = fields.Boolean(
        string="本地镜像导入", default=False, index=True, readonly=True, copy=False,
    )
    sourcing_image_customized = fields.Boolean(
        string="已替换原始图片", default=False, readonly=True, copy=False,
        help="管理员上传新图片后自动启用；前台会改用带版本号的缓存图片。",
    )

    _website_sourcing_source_key_unique = models.Constraint(
        "UNIQUE(website_id, sourcing_source_key)",
        "同一网站不能重复导入同一个镜像产品分类。",
    )

    def write(self, values):
        if (
            "image_1920" in values
            and "sourcing_image_customized" not in values
            and any(self.mapped("sourcing_imported_from_mirror"))
        ):
            values = dict(values, sourcing_image_customized=True)
        return super().write(values)


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
    body_html = fields.Html(
        string="页面正文", required=True, translate=True, sanitize=False,
        help="本地镜像初始化后的页面正文；管理员可在后台直接编辑。",
    )
    source_path = fields.Char(string="公开路径", index=True)
    source_file = fields.Char(string="本地来源文件", readonly=True)
    source_hash = fields.Char(string="来源版本", readonly=True, index=True)
    source_stylesheets = fields.Text(string="页面样式资源", readonly=True)
    source_style_hash = fields.Char(string="页面内联样式版本", readonly=True, index=True)
    page_type = fields.Selection([
        ("home", "首页"),
        ("service", "服务页"),
        ("product_index", "产品总览"),
        ("product_category", "产品分类"),
        ("archive", "内容目录"),
        ("article", "文章"),
        ("page", "普通页面"),
    ], string="页面类型", required=True, default="page", index=True)
    imported_from_mirror = fields.Boolean(string="本地镜像导入", default=False, index=True)
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
    _website_source_path_unique = models.Constraint(
        "UNIQUE(website_id, source_path)", "同一网站的公开路径不能重复。",
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


class WebsiteFactoryCapability(models.Model):
    _name = "ll.website.factory.capability"
    _description = "工厂网站能力内容"
    _order = "category, sequence, id"

    name = fields.Char(string="能力名称", required=True, translate=True)
    category = fields.Selection([
        ("profile", "工厂介绍"),
        ("production_line", "生产线"),
        ("equipment", "设备"),
        ("process", "生产工艺"),
        ("quality", "质量控制"),
        ("certification", "认证资质"),
        ("case", "客户案例"),
        ("factory_tour", "验厂与参观"),
    ], string="能力类型", required=True, default="profile", index=True)
    website_id = fields.Many2one(
        "website", string="工厂网站", required=True, ondelete="cascade", index=True,
    )
    summary = fields.Text(string="公开摘要", required=True, translate=True)
    body_html = fields.Html(string="详细内容", translate=True)
    image_asset_id = fields.Many2one(
        "ll.sourcing.asset", string="展示图片", ondelete="set null",
    )
    evidence_note = fields.Text(
        string="核实依据",
        help="填写设备台账、认证文件、验厂记录或其他可复核依据。",
    )
    evidence_url = fields.Char(string="证据链接")
    verified = fields.Boolean(string="已核实", default=False, index=True)
    published = fields.Boolean(string="网站发布", default=False, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.constrains("published", "verified", "evidence_note")
    def _check_publish_evidence(self):
        for record in self:
            if record.published and (not record.verified or not record.evidence_note):
                raise ValidationError(_("工厂能力发布前必须完成核实并填写核实依据。"))

    @api.constrains("website_id", "image_asset_id")
    def _check_image_website(self):
        for record in self:
            if record.image_asset_id and record.image_asset_id.website_id != record.website_id:
                raise ValidationError(_("工厂能力与展示图片必须属于同一个网站。"))


class WebsiteProductPresentation(models.Model):
    _name = "ll.website.product.presentation"
    _description = "网站产品展示内容"
    _rec_name = "public_name"
    _order = "sequence, id"

    website_id = fields.Many2one(
        "website", string="网站", required=True, ondelete="cascade", index=True,
    )
    product_tmpl_id = fields.Many2one(
        "product.template", string="Odoo 产品", required=True, ondelete="cascade", index=True,
    )
    public_name = fields.Char(string="网站展示名称", required=True, translate=True)
    summary = fields.Text(string="产品摘要", required=True, translate=True)
    application_scenarios = fields.Text(string="应用场景", translate=True)
    moq_text = fields.Char(string="起订量说明", translate=True)
    customization_scope = fields.Text(string="定制范围", translate=True)
    manufacturing_process = fields.Text(string="生产与质量说明", translate=True)
    call_to_action = fields.Selection([
        ("quote", "获取报价"),
        ("sample", "申请样品"),
        ("contact", "联系咨询"),
    ], string="主要行动按钮", required=True, default="quote")
    image_asset_id = fields.Many2one(
        "ll.sourcing.asset", string="展示图片", ondelete="set null",
    )
    evidence_note = fields.Text(
        string="核实依据",
        help="记录规格、起订量、定制范围和生产信息的内部依据。",
    )
    verified = fields.Boolean(string="已核实", default=False, index=True)
    published = fields.Boolean(string="网站发布", default=False, index=True)
    featured = fields.Boolean(string="重点展示", default=False)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _website_product_unique = models.Constraint(
        "UNIQUE(website_id, product_tmpl_id)", "同一网站不能重复配置同一个产品。",
    )

    @api.constrains("published", "verified", "evidence_note")
    def _check_publish_evidence(self):
        for record in self:
            if record.published and (not record.verified or not record.evidence_note):
                raise ValidationError(_("网站产品发布前必须完成核实并填写核实依据。"))

    @api.constrains("website_id", "image_asset_id")
    def _check_image_website(self):
        for record in self:
            if record.image_asset_id and record.image_asset_id.website_id != record.website_id:
                raise ValidationError(_("网站产品与展示图片必须属于同一个网站。"))


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
    website_id = fields.Many2one(
        "website", string="来源网站", index=True, ondelete="set null",
    )


class CustomerTouchpoint(models.Model):
    _inherit = "psc.customer.touchpoint"

    website_id = fields.Many2one(
        "website", string="来源网站", index=True, ondelete="set null",
    )


class CrmLead(models.Model):
    _inherit = "crm.lead"

    ll_source_website_id = fields.Many2one(
        "website", string="来源网站", index=True, ondelete="set null",
    )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    sourcing_inquiry_only = fields.Boolean(
        string="仅接受采购询盘",
        help="网站产品页显示采购询价入口，不作为普通零售商品宣传。",
    )
