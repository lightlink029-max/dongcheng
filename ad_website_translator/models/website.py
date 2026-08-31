# -*- coding: utf-8 -*-

from odoo import fields, models

class Website(models.Model):
    _inherit = 'website'

    translator_lang_ids = fields.Many2many(
        'res.lang',
        'website_translator_lang_rel',
        'website_id',
        'lang_id',
        string='Translator Languages',
        help='Select active languages for the translator widget.'
    )
    translator_position = fields.Selection([
        ('both', 'Both (Navbar and Floating)'),
        ('navbar', 'Navbar Only'),
        ('floating', 'Floating Only'),
    ], string='Translator Position', default='both')
    translator_style = fields.Selection([
        ('pill', 'Pill shape (Rounded)'),
        ('minimal', 'Minimal (Flags Only)'),
        ('flat', 'Flat list'),
    ], string='Translator Style', default='pill')
    translator_primary_color = fields.Char(
        string='Translator Primary Color', 
        default='#714B67'
    )

    def get_translator_languages_json(self):
        import json
        langs = []
        emoji_map = {
            'en': '🇺🇸', 'es': '🇪🇸', 'fr': '🇫🇷', 'de': '🇩🇪', 'it': '🇮🇹', 'pt': '🇵🇹',
            'ar': '🇸🇦', 'zh': '🇨🇳', 'ja': '🇯🇵', 'hi': '🇮🇳', 'ru': '🇷🇺', 'nl': '🇳🇱',
            'pl': '🇵🇱', 'tr': '🇹🇷', 'sv': '🇸🇪', 'fi': '🇫🇮', 'no': '🇳🇴', 'da': '🇩🇰',
            'he': '🇮🇱', 'ko': '🇰🇷', 'vi': '🇻🇳', 'id': '🇮🇩', 'th': '🇹🇭', 'uk': '🇺🇦',
            'cs': '🇨🇿', 'el': '🇬🇷', 'hu': '🇭🇺', 'ro': '🇷🇴', 'sk': '🇸🇰', 'bg': '🇧🇬'
        }
        for lang in self.translator_lang_ids:
            # Map code to Google format
            google_code = lang.code
            if lang.code.startswith('zh_'):
                google_code = lang.code.replace('_', '-')
            else:
                google_code = lang.code.split('_')[0]
                
            emoji = emoji_map.get(google_code, '🏳️')
            name = lang.name.split('/')[-1].strip() if '/' in lang.name else lang.name
            
            langs.append({
                'code': google_code,
                'name': name,
                'flag': emoji
            })
            
        # Ensure default English is present
        if not any(l['code'] == 'en' for l in langs):
            langs.insert(0, {'code': 'en', 'name': 'English', 'flag': '🇺🇸'})
            
        return json.dumps(langs)
