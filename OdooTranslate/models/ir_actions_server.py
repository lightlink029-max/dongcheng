# -*- coding: utf-8 -*-

import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .auth_mail_policy import (
    AUTH_TRANSACTIONAL_REASON,
    is_auth_transactional_context,
)
from .rule_identity import MAIL_ACTION_RULE_KEY

_logger = logging.getLogger(__name__)


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

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
            'An OdooTranslate server action rule key can only be used once.',
        )
    else:
        _sql_constraints = [
            (
                'odootranslate_server_action_rule_key_unique',
                'unique(odootranslate_rule_key)',
                'An OdooTranslate server action rule key can only be used once.',
            ),
        ]

    @api.model
    def odootranslate_rule_identity_capability(self):
        action_fields = self._fields
        automation_fields = self.env['base.automation']._fields
        required_fields = {
            'odootranslate_managed',
            'odootranslate_rule_key',
        }
        return (
            required_fields.issubset(action_fields)
            and required_fields.issubset(automation_fields)
        )

    def _run_action_webhook(self, eval_context=None):
        """Suppress auth mail loops and tag managed internal writes."""
        self.ensure_one()

        if self._is_auth_transactional_mail_webhook():
            _logger.info(
                '[OdooTranslate] webhook skipped: reason=%s action_id=%s '
                'model=mail.mail record_id=%s',
                AUTH_TRANSACTIONAL_REASON,
                self.id,
                self.env.context.get('active_id'),
            )

            return None

        if self._should_tag_odootranslate_operation_webhook():
            return self._run_tagged_odootranslate_operation_webhook()

        return super()._run_action_webhook(eval_context=eval_context)

    def _should_tag_odootranslate_operation_webhook(self):
        operation_id = self.env.context.get('odootranslate_operation_id')

        return (
            self.odootranslate_managed
            and self.state == 'webhook'
            and isinstance(operation_id, str)
            and bool(operation_id)
        )

    def _run_tagged_odootranslate_operation_webhook(self):
        active_id = self.env.context.get('active_id')
        record = self.env[self.model_id.model].browse(active_id)
        if not record:
            return None

        if not self.webhook_url:
            raise UserError(_('Webhook URL is not configured.'))

        values = {
            '_model': self.model_id.model,
            '_id': record.id,
            '_action': '%s(#%s)' % (self.name, self.id),
        }
        if self.webhook_field_ids:
            values.update(record.read(self.webhook_field_ids.mapped('name'))[0])
        values['odootranslate_operation_id'] = self.env.context[
            'odootranslate_operation_id'
        ]

        try:
            response = requests.post(
                self.webhook_url,
                data=json.dumps(values, sort_keys=True, default=str),
                headers={'Content-Type': 'application/json'},
                timeout=10,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as exception:
            _logger.warning(
                '[OdooTranslate] tagged webhook failed: action_id=%s '
                'model=%s record_id=%s reason=%s',
                self.id,
                self.model_id.model,
                record.id,
                exception,
            )
        return None

    def _is_auth_transactional_mail_webhook(self):
        return (
            is_auth_transactional_context(self.env.context)
            and self.odootranslate_managed
            and self.odootranslate_rule_key == MAIL_ACTION_RULE_KEY
            and self.state == 'webhook'
            and self.model_id.model == 'mail.mail'
        )
