# -*- coding: utf-8 -*-

{
    "name": "Odoo Website Translator",
    "version": "19.0.1.0",
    "author": "ADream Innovations",
    'category': 'Website',
    "website": "https://adreaminnovations.odoo.com/",
    "description": """
        Sleek, customizable Google-powered translation widget for Odoo websites.
        Features multiple layout styles, configurable placement, branding-aligned colors,
        and smooth page translation transitions to prevent Flash of Untranslated Text (FOUC).
        """,
    'depends': ["website"],
    'data': [
        "views/website_navbar_template.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        'web.assets_frontend': [
            "ad_website_translator/static/src/css/translator.css",
            "ad_website_translator/static/src/js/language_translator.js",
        ],
    },
    "price": 0,
    "currency": "USD",
    "license": "LGPL-3",
    'installable': True,
    'application': False,
    'images': ['static/description/banner.png']
}
