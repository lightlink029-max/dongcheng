# -*- coding: utf-8 -*-
"""Durable idempotency and replay journals for the module API."""

import hashlib
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import api, fields, models


NONCE_TTL_SECONDS = 601


class OdooTranslateModuleApiOperation(models.Model):
    _name = 'odoo_translate.module_api_operation'
    _description = 'OdooTranslate Module API Operation'
    _order = 'id desc'
    _rec_name = 'operation_id'

    config_id = fields.Many2one(
        'odoo_translate.config',
        required=True,
        index=True,
        ondelete='cascade',
    )
    link_attempt_id = fields.Char(index=True, readonly=True)
    operation = fields.Selection(
        [('update_status', 'Update API Key Status')],
        string='Operation Type',
        required=True,
        readonly=True,
    )
    operation_id = fields.Char(
        string='Operation ID',
        required=True,
        index=True,
        readonly=True,
    )
    payload_hash = fields.Char(required=True, readonly=True)
    requested_has_api_key = fields.Boolean(required=True, readonly=True)
    status = fields.Selection(
        [
            ('processing', 'Processing'),
            ('succeeded', 'Succeeded'),
            ('failed', 'Failed'),
        ],
        required=True,
        default='processing',
        index=True,
        readonly=True,
    )
    attempt_count = fields.Integer(required=True, default=1, readonly=True)
    first_request_id = fields.Char(required=True, readonly=True)
    last_request_id = fields.Char(required=True, readonly=True)
    last_error_code = fields.Char(readonly=True)
    completed_at = fields.Datetime(readonly=True)

    if hasattr(models, 'Constraint'):
        _operation_identity_unique = models.Constraint(
            'UNIQUE(config_id, operation, operation_id)',
            'A module API operation ID can only be used once per configuration.',
        )
    else:
        _sql_constraints = [
            (
                'module_api_operation_identity_unique',
                'unique(config_id, operation, operation_id)',
                'A module API operation ID can only be used once per configuration.',
            ),
        ]

    @api.model
    def apply_status_update(
        self,
        config,
        operation_id,
        payload_hash,
        has_api_key,
        request_id,
    ):
        """Apply or recover an exact status operation under a config lock."""
        config.ensure_one()
        config.flush_recordset([
            'has_api_key',
            'link_attempt_id',
            'connection_status',
            'shared_secret',
        ])
        self.env.cr.execute(
            'SELECT id FROM odoo_translate_config WHERE id = %s FOR UPDATE',
            [config.id],
        )
        config.invalidate_recordset([
            'has_api_key',
            'link_attempt_id',
            'connection_status',
            'shared_secret',
        ])

        if config.connection_status != 'connected' or not config.shared_secret:
            return {
                'succeeded': False,
                'code': 'stale_link_generation',
                'http_status': 409,
            }

        link_attempt_id = config.link_attempt_id or False
        operation = self.sudo().search([
            ('config_id', '=', config.id),
            ('operation', '=', 'update_status'),
            ('operation_id', '=', operation_id),
        ], limit=1)

        if operation:
            is_exact_retry = (
                operation.payload_hash == payload_hash
                and (operation.link_attempt_id or False) == link_attempt_id
                and operation.requested_has_api_key == has_api_key
            )
            if not is_exact_retry:
                return {
                    'succeeded': False,
                    'code': 'module_operation_conflict',
                    'http_status': 409,
                }

            operation.sudo().write({
                'attempt_count': operation.attempt_count + 1,
                'last_request_id': request_id,
            })
            if operation.status == 'succeeded':
                return {
                    'succeeded': True,
                    'has_api_key': operation.requested_has_api_key,
                    'idempotent': True,
                }

            if operation.status == 'processing':
                return {
                    'succeeded': False,
                    'code': 'module_operation_in_progress',
                    'http_status': 409,
                }

            operation.sudo().write({
                'status': 'processing',
                'last_error_code': False,
                'completed_at': False,
            })
        else:
            operation = self.sudo().create({
                'config_id': config.id,
                'link_attempt_id': link_attempt_id,
                'operation': 'update_status',
                'operation_id': operation_id,
                'payload_hash': payload_hash,
                'requested_has_api_key': has_api_key,
                'status': 'processing',
                'attempt_count': 1,
                'first_request_id': request_id,
                'last_request_id': request_id,
            })

        config.sudo().write({'has_api_key': has_api_key})
        operation.sudo().write({
            'status': 'succeeded',
            'last_error_code': False,
            'completed_at': fields.Datetime.now(),
        })

        return {
            'succeeded': True,
            'has_api_key': has_api_key,
            'idempotent': False,
        }

    @api.model
    def record_status_failure(
        self,
        config,
        operation_id,
        payload_hash,
        has_api_key,
        request_id,
        error_code,
    ):
        """Persist a recoverable failure after the operation savepoint rolled back."""
        config.ensure_one()
        link_attempt_id = config.link_attempt_id or False
        operation = self.sudo().search([
            ('config_id', '=', config.id),
            ('operation', '=', 'update_status'),
            ('operation_id', '=', operation_id),
        ], limit=1)

        if operation:
            is_exact_operation = (
                operation.payload_hash == payload_hash
                and (operation.link_attempt_id or False) == link_attempt_id
                and operation.requested_has_api_key == has_api_key
            )
            if not is_exact_operation:
                raise ValueError('The failed module operation conflicts with its journal.')

            if operation.status == 'succeeded':
                return

            operation.sudo().write({
                'status': 'failed',
                'attempt_count': operation.attempt_count + 1,
                'last_request_id': request_id,
                'last_error_code': error_code,
                'completed_at': fields.Datetime.now(),
            })
            return

        self.sudo().create({
            'config_id': config.id,
            'link_attempt_id': link_attempt_id,
            'operation': 'update_status',
            'operation_id': operation_id,
            'payload_hash': payload_hash,
            'requested_has_api_key': has_api_key,
            'status': 'failed',
            'attempt_count': 1,
            'first_request_id': request_id,
            'last_request_id': request_id,
            'last_error_code': error_code,
            'completed_at': fields.Datetime.now(),
        })


class OdooTranslateModuleApiNonce(models.Model):
    _name = 'odoo_translate.module_api_nonce'
    _description = 'OdooTranslate Module API Nonce'
    _order = 'id desc'

    config_id = fields.Many2one(
        'odoo_translate.config',
        required=True,
        index=True,
        ondelete='cascade',
    )
    nonce_hash = fields.Char(required=True, readonly=True)
    request_id = fields.Char(required=True, readonly=True)
    expires_at = fields.Datetime(required=True, index=True, readonly=True)

    if hasattr(models, 'Constraint'):
        _nonce_identity_unique = models.Constraint(
            'UNIQUE(config_id, nonce_hash)',
            'A module API nonce can only be used once per configuration.',
        )
    else:
        _sql_constraints = [
            (
                'module_api_nonce_identity_unique',
                'unique(config_id, nonce_hash)',
                'A module API nonce can only be used once per configuration.',
            ),
        ]

    @api.model
    def reserve(self, config, nonce, request_id):
        """Reserve a nonce atomically, returning false when it was replayed."""
        config.ensure_one()
        self._purge_expired(limit=200)
        nonce_hash = hashlib.sha256(nonce.encode('ascii')).hexdigest()

        try:
            with self.env.cr.savepoint():
                self.sudo().create({
                    'config_id': config.id,
                    'nonce_hash': nonce_hash,
                    'request_id': request_id,
                    'expires_at': fields.Datetime.now() + timedelta(
                        seconds=NONCE_TTL_SECONDS,
                    ),
                })
        except IntegrityError:
            return False

        return True

    @api.autovacuum
    def _gc_expired_nonces(self):
        self._purge_expired(limit=1000)

    @api.model
    def _purge_expired(self, limit):
        expired = self.sudo().search([
            ('expires_at', '<=', fields.Datetime.now()),
        ], limit=limit)
        if expired:
            expired.unlink()
