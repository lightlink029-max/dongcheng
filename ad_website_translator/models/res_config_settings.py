# -*- coding: utf-8 -*-

from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    translator_lang_ids = fields.Many2many(
        related='website_id.translator_lang_ids',
        readonly=False,
        string='Translator Languages'
    )
    translator_position = fields.Selection(
        related='website_id.translator_position',
        readonly=False,
        string='Translator Position'
    )
    translator_style = fields.Selection(
        related='website_id.translator_style',
        readonly=False,
        string='Translator Style'
    )
    translator_primary_color = fields.Char(
        related='website_id.translator_primary_color',
        readonly=False,
        string='Translator Primary Color'
    )
