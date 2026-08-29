# -*- coding: utf-8 -*-
{
    'name': 'OdooTranslate',
    'version': '1.16.0',
    'category': 'Tools',
    'summary': 'Dynamic Translation Management for Odoo',
    'author': 'OdooTranslate',
    'license': 'OPL-1',
    'depends': ['base', 'mail', 'auth_signup', 'base_automation'],
    'website': 'https://odootranslate.com',
    'images': ['static/description/img/thumbnail.jpg'],
    'data': [
        'security/ir.model.access.csv',
        'views/odoo_translate_config_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'OdooTranslate/static/src/js/article_links.js',
        ],
        'web.assets_backend': [
            'OdooTranslate/static/src/js/article_links.js',
        ],
        'website.assets_frontend': [
            'OdooTranslate/static/src/js/article_links.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
