{
    "name": "产品线社媒发布中心",
    "version": "19.0.1.1.1",
    "summary": "按产品线、市场和渠道批量生成并管理社媒内容",
    "category": "Marketing/Social Marketing",
    "author": "LightLink",
    "license": "LGPL-3",
    "depends": ["product_intelligence_hub", "social", "crm", "website_sale", "purchase", "stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/social_content_views.xml",
        "views/crm_lead_views.xml",
        "views/social_content_menus.xml",
    ],
    "application": True,
    "installable": True,
}
