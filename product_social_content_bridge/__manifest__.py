{
    "name": "产品线社媒发布中心",
    "version": "19.0.2.1.0",
    "summary": "按产品线、市场和渠道批量生成并管理社媒内容",
    "category": "Marketing/Social Marketing",
    "author": "LightLink",
    "license": "LGPL-3",
    "depends": ["product_intelligence_hub", "social", "crm", "website_sale", "purchase", "stock"],
    "data": [
        "security/ir.model.access.csv",
        "data/media_models.xml",
        "views/social_content_views.xml",
        "views/crm_lead_views.xml",
        "views/social_content_menus.xml",
        "views/local_production_views.xml",
    ],
    "application": True,
    "installable": True,
}
