# -*- coding: utf-8 -*-
"""Append-only receipts for atomic native text writes."""

from odoo import fields, models, _
from odoo.exceptions import UserError


class OdooTranslateNativeTextOperation(models.Model):
    _name = 'odoo_translate.native_text_operation'
    _description = 'OdooTranslate Native Text Operation Receipt'
    _order = 'id desc'
    _rec_name = 'operation_id'

    config_id = fields.Many2one(
        'odoo_translate.config',
        required=True,
        index=True,
        ondelete='cascade',
        readonly=True,
    )
    link_attempt_id = fields.Char(required=True, index=True, readonly=True)
    operation_id = fields.Char(required=True, index=True, readonly=True)
    request_hash = fields.Char(required=True, index=True, readonly=True)
    receipt_id = fields.Char(required=True, index=True, readonly=True)
    model_name = fields.Char(index=True, readonly=True)
    record_id = fields.Integer(index=True, readonly=True)
    field_name = fields.Char(readonly=True)
    source_lang = fields.Char(readonly=True)
    target_lang = fields.Char(readonly=True)
    source_hash_algorithm = fields.Char(readonly=True)
    source_hash = fields.Char(readonly=True)
    translation_hash = fields.Char(readonly=True)
    status = fields.Selection(
        [
            ('applied', 'Applied'),
            ('refused', 'Refused'),
            ('sealed_without_write', 'Sealed Without Write'),
        ],
        required=True,
        index=True,
        readonly=True,
    )
    reason_code = fields.Char(index=True, readonly=True)
    completed_at = fields.Datetime(required=True, index=True, readonly=True)

    if hasattr(models, 'Constraint'):
        _operation_identity_unique = models.Constraint(
            'UNIQUE(config_id, operation_id)',
            'A native text operation ID can only be used once per configuration.',
        )
        _receipt_identity_unique = models.Constraint(
            'UNIQUE(receipt_id)',
            'A native text operation receipt ID can only be used once.',
        )
    else:
        _sql_constraints = [
            (
                'native_text_operation_identity_unique',
                'unique(config_id, operation_id)',
                'A native text operation ID can only be used once per configuration.',
            ),
            (
                'native_text_operation_receipt_unique',
                'unique(receipt_id)',
                'A native text operation receipt ID can only be used once.',
            ),
        ]

    def write(self, values):
        raise UserError(_('Native text operation receipts are append-only.'))

    def unlink(self):
        raise UserError(_('Native text operation receipts are append-only.'))
