"""Language setup for the imported LightLink sourcing website."""


MENU_ENGLISH = {
    "menu_sourcing_home": ("Home", "/sourcing", 10),
    "menu_sourcing_services": ("Our Services", "#", 20),
    "menu_sourcing_service_procurement": ("Sourcing & Purchasing", "/sourcing/site/pricing", 10),
    "menu_sourcing_service_dropshipping": ("Dropshipping Service", "/sourcing/site/dropshipping", 20),
    "menu_sourcing_service_photo_design": ("Photos & Designs", "/sourcing/site/graphics-and-design-service", 30),
    "menu_sourcing_pricing": ("Extra Service", "/sourcing/site/extra-service", 40),
    "menu_sourcing_solutions": ("Solutions", "#", 30),
    "menu_sourcing_solution_private_label": ("Private Label", "/sourcing/site/private-label-packaging-service", 10),
    "menu_sourcing_solution_product_development": ("Product Development", "/sourcing/site/product-development", 20),
    "menu_sourcing_solution_shipping": ("Shipping Solution", "/sourcing/site/shipping-and-cargo-consolidation-service", 30),
    "menu_sourcing_solution_fba": ("Amazon FBA", "/sourcing/site/amazon-fba-prep-service", 40),
    "menu_sourcing_solution_quality": ("Quality Control", "/sourcing/site/quality-control-service", 50),
    "menu_sourcing_solution_credit": ("Credit Payment Terms", "/sourcing/site/credit-payment-terms", 60),
    "menu_sourcing_solution_affiliate": ("Affiliate Program", "/sourcing/site/affiliates", 70),
    "menu_sourcing_products": ("Products", "/sourcing/site/our-products", 40),
    "menu_sourcing_about": ("About", "/sourcing/site/about-us", 50),
    "menu_sourcing_insights": ("Resources", "/sourcing/site/blog", 60),
    "menu_sourcing_blog": ("Our Blog", "/sourcing/site/blog", 10),
    "menu_sourcing_import_guide": ("Import from China Tutorial", "/sourcing/site/blog/c-import-from-china-guide", 20),
    "menu_sourcing_agent_guide": ("Sourcing Agent Guide", "/sourcing/site/find-china-sourcing-agents-company", 30),
    "menu_sourcing_yiwu": ("Visit Yiwu", "/sourcing/site/yiwu-china", 40),
    "menu_sourcing_payment": ("Payment Information", "/sourcing/site/payment", 10),
    "menu_sourcing_about_us": ("About Us", "/sourcing/site/about-us", 20),
    "menu_sourcing_founder": ("About Founder", "/sourcing/site/jing", 30),
    "menu_sourcing_quote": ("Get a Quote", "/sourcing/request", 70),
}


MENU_CHINESE = {
    "menu_sourcing_home": "首页",
    "menu_sourcing_services": "我们的服务",
    "menu_sourcing_service_procurement": "采购与供应",
    "menu_sourcing_service_dropshipping": "代发货服务",
    "menu_sourcing_service_photo_design": "照片与设计",
    "menu_sourcing_pricing": "额外服务",
    "menu_sourcing_solutions": "解决方案",
    "menu_sourcing_solution_private_label": "自有品牌",
    "menu_sourcing_solution_product_development": "产品开发",
    "menu_sourcing_solution_shipping": "运输解决方案",
    "menu_sourcing_solution_fba": "亚马逊 FBA",
    "menu_sourcing_solution_quality": "质量控制",
    "menu_sourcing_solution_credit": "信用付款条款",
    "menu_sourcing_solution_affiliate": "联盟计划",
    "menu_sourcing_products": "产品",
    "menu_sourcing_about": "关于",
    "menu_sourcing_insights": "资源",
    "menu_sourcing_blog": "我们的博客",
    "menu_sourcing_import_guide": "从中国进口教程",
    "menu_sourcing_agent_guide": "采购代理指南",
    "menu_sourcing_yiwu": "访问义乌",
    "menu_sourcing_payment": "付款信息",
    "menu_sourcing_about_us": "关于我们",
    "menu_sourcing_founder": "关于创始人",
    "menu_sourcing_quote": "提交采购需求",
}


def apply_sourcing_translations(env):
    website = env.ref("lightlink_sourcing_website.website_global_sourcing", raise_if_not_found=False)
    if not website:
        return False
    english = env["res.lang"].search([("code", "=", "en_US"), ("active", "=", True)], limit=1)
    chinese = env["res.lang"].search([("code", "=", "zh_CN"), ("active", "=", True)], limit=1)
    languages = english | chinese
    values = {"sourcing_brand_name": "LightLink Global Sourcing"}
    if languages:
        values["language_ids"] = [(6, 0, languages.ids)]
    if english:
        values["default_lang_id"] = english.id
    website.with_context(lang="en_US").write(values)

    for xmlid, (name, url, sequence) in MENU_ENGLISH.items():
        menu = env.ref("lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False)
        if menu:
            menu.with_context(lang="en_US").write({
                "name": name, "url": url, "sequence": sequence,
            })

    if chinese:
        website.with_context(lang="zh_CN").write({
            "sourcing_brand_name": "LightLink 全球采购服务",
            "sourcing_tagline": "中国采购、产品开发与交付过程管理",
        })
        for xmlid, name in MENU_CHINESE.items():
            menu = env.ref("lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False)
            if menu:
                menu.with_context(lang="zh_CN").write({"name": name})

    project = env["psc.publishing.project"].browse(5).exists()
    if project and chinese:
        project.with_context(lang="zh_CN").write({
            "website_public_name": "用清晰方案和可追责执行完成中国采购。",
            "website_public_summary": "从寻找供应商、产品开发到质量控制、集货和交付协调。",
        })
    return True
