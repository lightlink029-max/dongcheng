{
    "name": "LightLink 采购服务官网",
    "version": "19.0.3.2.2",
    "summary": "独立多语言采购服务官网、内容资产与结构化询盘运营闭环",
    "category": "Website/Website",
    "author": "LightLink",
    "license": "LGPL-3",
    "depends": [
        "website",
        "website_blog",
        "website_sale",
        "crm",
        "product_social_content_bridge",
        "OdooTranslate",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sourcing_site.xml",
        "views/sourcing_backend_views.xml",
        "views/website_operations_views.xml",
        "views/sourcing_website_templates.xml",
        "views/sourcing_website_menus.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "lightlink_sourcing_website/static/src/scss/sourcing_website.scss",
            "lightlink_sourcing_website/static/src/js/mirror_interactions.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "application": False,
    "installable": True,
}
