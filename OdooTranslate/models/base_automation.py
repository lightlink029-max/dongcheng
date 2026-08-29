# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models

from .rule_identity import MAIL_AUTOMATION_RULE_KEY

_logger = logging.getLogger(__name__)

MAIL_TRANSLATION_FILTER = '[["needs_translation","=",True]]'


class BaseAutomation(models.Model):
    _inherit = 'base.automation'

    odootranslate_managed = fields.Boolean(
        string='Managed by OdooTranslate',
        default=False,
        index=True,
        copy=False,
    )
    odootranslate_rule_key = fields.Char(
        string='OdooTranslate Rule Key',
        index=True,
        copy=False,
    )

    if hasattr(models, 'Constraint'):
        _odootranslate_rule_key_unique = models.Constraint(
            'UNIQUE(odootranslate_rule_key)',
            'An OdooTranslate automation rule key can only be used once.',
        )
    else:
        _sql_constraints = [
            (
                'odootranslate_automation_rule_key_unique',
                'unique(odootranslate_rule_key)',
                'An OdooTranslate automation rule key can only be used once.',
            ),
        ]

    def init(self):
        super().init()
        self._odootranslate_reconcile_mail_filters()

    @api.model
    def _odootranslate_reconcile_mail_filters(self):
        automations = self.sudo().search([
            ('odootranslate_managed', '=', True),
            ('odootranslate_rule_key', '=', MAIL_AUTOMATION_RULE_KEY),
            ('model_id.model', '=', 'mail.mail'),
        ])
        stale_automations = automations.filtered(
            lambda automation:
                automation.filter_domain != MAIL_TRANSLATION_FILTER
        )
        if stale_automations:
            stale_automations.write({
                'filter_domain': MAIL_TRANSLATION_FILTER,
            })
            _logger.info(
                '[OdooTranslate] reconciled mail automation filters: count=%s',
                len(stale_automations),
            )
        return len(stale_automations)
