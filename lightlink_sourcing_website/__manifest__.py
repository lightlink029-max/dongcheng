{
    "name": "LightLink 采购服务官网",
    "version": "19.0.1.0.0",
    "summary": "面向采购服务获客的多语言官网与结构化询盘入口",
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
        "views/sourcing_backend_views.xml",
        "views/sourcing_website_templates.xml",
        "views/sourcing_website_menus.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "lightlink_sourcing_website/static/src/scss/sourcing_website.scss",
        ],
    },
    "application": False,
    "installable": True,
}
