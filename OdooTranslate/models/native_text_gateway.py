# -*- coding: utf-8 -*-
"""Atomic, idempotent native text writes for OdooTranslate."""

import re
import uuid

from odoo import api, fields, models
from odoo.exceptions import AccessDenied, AccessError, UserError
from odoo.tools import SQL

from ..module_api import (
    NATIVE_TEXT_CONTRACT,
    NATIVE_TEXT_SOURCE_HASH_ALGORITHM,
    native_text_request_hash,
    native_text_value_hash,
    verify_native_text_operation_signature,
)


APPLY_FIELDS = {
    'contract',
    'expected_source_hash',
    'field_name',
    'link_attempt_id',
    'model_name',
    'module_uuid',
    'operation_id',
    'record_id',
    'request_hash',
    'signature',
    'source_hash_algorithm',
    'source_lang',
    'target_lang',
    'translation_hash',
    'translation_value',
}
DIGEST_PATTERN = re.compile(r'^[0-9a-f]{64}$')
IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_.]*$')
RECONCILE_FIELDS = {
    'contract',
    'link_attempt_id',
    'module_uuid',
    'operation_id',
    'request_hash',
    'signature',
}


class NativeTextRefusal(Exception):
    """A deterministic refusal known to have committed no business write."""

    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


class OdooTranslateTranslationGateway(models.AbstractModel):
    _name = 'odoo_translate.translation_gateway'
    _description = 'OdooTranslate Atomic Translation Gateway'

    @api.model
    def apply_native_text_v1(self, payload):
        """Verify source, apply one translation, and persist its receipt."""
        self._validate_apply_payload(payload)
        config, auth_failure = self._authenticate_and_lock(
            payload,
            operation='apply',
        )
        if auth_failure:
            return self._unpersisted_result(payload, 'refused', auth_failure)

        existing = self._find_operation(config, payload['operation_id'])
        if existing:
            return self._existing_result(existing, payload['request_hash'])
        committed_result = self._find_committed_operation_result(
            config.id,
            payload['operation_id'],
            payload['request_hash'],
        )
        if committed_result:
            return committed_result

        try:
            with self.env.cr.savepoint():
                self._apply_business_write(payload)
        except NativeTextRefusal as refusal:
            operation = self._create_operation(
                config,
                payload,
                'refused',
                refusal.reason_code,
            )
            return self._operation_result(operation, idempotent=False)
        except AccessError:
            operation = self._create_operation(
                config,
                payload,
                'refused',
                'native_text_access_denied',
            )
            return self._operation_result(operation, idempotent=False)
        except UserError:
            operation = self._create_operation(
                config,
                payload,
                'refused',
                'native_translation_write_not_confirmed',
            )
            return self._operation_result(operation, idempotent=False)

        operation = self._create_operation(
            config,
            payload,
            'applied',
            False,
        )
        return self._operation_result(operation, idempotent=False)

    @api.model
    def reconcile_native_text_v1(self, payload):
        """Return a receipt or seal an absent operation against a late write."""
        self._validate_reconcile_payload(payload)
        config, auth_failure = self._authenticate_and_lock(
            payload,
            operation='reconcile',
        )
        if auth_failure:
            return self._unpersisted_result(payload, 'refused', auth_failure)

        existing = self._find_operation(config, payload['operation_id'])
        if existing:
            return self._existing_result(existing, payload['request_hash'])
        committed_result = self._find_committed_operation_result(
            config.id,
            payload['operation_id'],
            payload['request_hash'],
        )
        if committed_result:
            return committed_result

        operation = self._create_operation(
            config,
            payload,
            'sealed_without_write',
            'native_text_operation_sealed_without_write',
        )
        return self._operation_result(operation, idempotent=False)

    def _validate_apply_payload(self, payload):
        if not isinstance(payload, dict) or set(payload) != APPLY_FIELDS:
            raise AccessDenied()
        if (
            payload.get('contract') != NATIVE_TEXT_CONTRACT
            or payload.get('source_hash_algorithm')
            != NATIVE_TEXT_SOURCE_HASH_ALGORITHM
            or not self._is_canonical_uuid(payload.get('module_uuid'))
            or not self._is_canonical_uuid(payload.get('link_attempt_id'))
            or not self._is_canonical_uuid(payload.get('operation_id'))
            or not self._is_digest(payload.get('request_hash'))
            or not self._is_digest(payload.get('expected_source_hash'))
            or not self._is_digest(payload.get('translation_hash'))
            or not self._is_identifier(payload.get('model_name'))
            or not self._is_identifier(payload.get('field_name'))
            or type(payload.get('record_id')) is not int
            or payload['record_id'] <= 0
            or not self._is_language(payload.get('source_lang'))
            or not self._is_language(payload.get('target_lang'))
            or payload['source_lang'] == payload['target_lang']
            or not isinstance(payload.get('translation_value'), str)
            or payload['translation_value'] == ''
        ):
            raise AccessDenied()

        try:
            actual_translation_hash = native_text_value_hash(
                payload['translation_value'],
            )
            actual_request_hash = native_text_request_hash(payload)
        except (UnicodeEncodeError, ValueError):
            raise AccessDenied() from None

        if (
            actual_translation_hash != payload['translation_hash']
            or actual_request_hash != payload['request_hash']
        ):
            raise AccessDenied()

    def _validate_reconcile_payload(self, payload):
        if not isinstance(payload, dict) or set(payload) != RECONCILE_FIELDS:
            raise AccessDenied()
        if (
            payload.get('contract') != NATIVE_TEXT_CONTRACT
            or not self._is_canonical_uuid(payload.get('module_uuid'))
            or not self._is_canonical_uuid(payload.get('link_attempt_id'))
            or not self._is_canonical_uuid(payload.get('operation_id'))
            or not self._is_digest(payload.get('request_hash'))
        ):
            raise AccessDenied()

    def _authenticate_and_lock(self, payload, operation):
        config = self.env['odoo_translate.config'].sudo().search([
            ('module_uuid', '=', payload['module_uuid']),
        ], limit=1)
        if not config:
            raise AccessDenied()

        config.flush_recordset([
            'connection_status',
            'link_attempt_id',
            'shared_secret',
        ])
        self.env.cr.execute(
            'SELECT id FROM odoo_translate_config WHERE id = %s FOR UPDATE',
            [config.id],
        )
        config.invalidate_recordset([
            'connection_status',
            'link_attempt_id',
            'shared_secret',
        ])

        if (
            config.connection_status != 'connected'
            or not config.shared_secret
            or config.link_attempt_id != payload['link_attempt_id']
        ):
            return config, 'stale_link_generation'

        if not verify_native_text_operation_signature(
            operation,
            payload['request_hash'],
            config.shared_secret,
            payload['signature'],
        ):
            raise AccessDenied()

        return config, False

    def _apply_business_write(self, payload):
        try:
            model = self.env[payload['model_name']]
        except KeyError:
            raise NativeTextRefusal('native_text_record_not_found') from None

        record = model.browse(payload['record_id'])
        if not record.exists():
            raise NativeTextRefusal('native_text_record_not_found')

        record.check_access('read')
        record.check_access('write')
        record.check_field_access_rights('read', [payload['field_name']])
        record.check_field_access_rights('write', [payload['field_name']])

        field = record._fields.get(payload['field_name'])
        if (
            not field
            or field.translate is not True
            or not field.store
            or field.type not in ('char', 'text')
        ):
            raise NativeTextRefusal('native_text_field_not_supported')

        if not self._language_is_active(payload['source_lang']):
            raise NativeTextRefusal('native_source_language_not_stored')
        if not self._language_is_active(payload['target_lang']):
            raise NativeTextRefusal('target_language_not_installed')

        record.flush_recordset([payload['field_name']])
        self.env.cr.execute(SQL(
            'SELECT id FROM %s WHERE id = %s FOR UPDATE',
            SQL.identifier(record._table),
            record.id,
        ))
        if self.env.cr.fetchone() is None:
            raise NativeTextRefusal('native_text_record_not_found')

        record.invalidate_recordset([payload['field_name']])
        stored_translations = field._get_stored_translations(record) or {}
        source_value = stored_translations.get(payload['source_lang'])
        if not isinstance(source_value, str) or source_value == '':
            raise NativeTextRefusal('native_source_language_not_stored')
        if native_text_value_hash(source_value) != payload['expected_source_hash']:
            raise NativeTextRefusal('native_source_changed')

        target_value = stored_translations.get(payload['target_lang'])
        if (
            isinstance(target_value, str)
            and native_text_value_hash(target_value)
            == payload['translation_hash']
        ):
            raise NativeTextRefusal('native_text_already_translated')

        written = record.with_context(
            lang=payload['target_lang'],
            odootranslate_operation_id=payload['operation_id'],
            skip_ai_translation=True,
            tracking_disable=True,
        ).write({payload['field_name']: payload['translation_value']})
        if written is not True:
            raise NativeTextRefusal('native_translation_write_not_confirmed')

        record.flush_recordset([payload['field_name']])
        record.invalidate_recordset([payload['field_name']])
        stored_after_write = field._get_stored_translations(record) or {}
        translated_value = stored_after_write.get(payload['target_lang'])
        if (
            not isinstance(translated_value, str)
            or native_text_value_hash(translated_value)
            != payload['translation_hash']
        ):
            raise NativeTextRefusal('native_translation_readback_mismatch')

    def _create_operation(self, config, payload, status, reason_code):
        values = {
            'config_id': config.id,
            'link_attempt_id': payload['link_attempt_id'],
            'operation_id': payload['operation_id'],
            'request_hash': payload['request_hash'],
            'receipt_id': str(uuid.uuid4()),
            'status': status,
            'reason_code': reason_code,
            'completed_at': fields.Datetime.now(),
        }
        if 'model_name' in payload:
            values.update({
                'model_name': payload['model_name'],
                'record_id': payload['record_id'],
                'field_name': payload['field_name'],
                'source_lang': payload['source_lang'],
                'target_lang': payload['target_lang'],
                'source_hash_algorithm': payload['source_hash_algorithm'],
                'source_hash': payload['expected_source_hash'],
                'translation_hash': payload['translation_hash'],
            })

        return self.env['odoo_translate.native_text_operation'].sudo().create(
            values,
        )

    def _find_operation(self, config, operation_id):
        return self.env['odoo_translate.native_text_operation'].sudo().search([
            ('config_id', '=', config.id),
            ('operation_id', '=', operation_id),
        ], limit=1)

    def _find_committed_operation_result(
        self,
        config_id,
        operation_id,
        request_hash,
    ):
        """Read a receipt committed while this Odoo snapshot waited."""
        with self.env.registry.cursor() as cursor:
            committed_env = api.Environment(cursor, self.env.uid, {})
            operation = committed_env[
                'odoo_translate.native_text_operation'
            ].sudo().search([
                ('config_id', '=', config_id),
                ('operation_id', '=', operation_id),
            ], limit=1)
            if not operation:
                return False
            return committed_env[
                'odoo_translate.translation_gateway'
            ]._existing_result(operation, request_hash)

    def _existing_result(self, operation, request_hash):
        if operation.request_hash != request_hash:
            return {
                'contract': NATIVE_TEXT_CONTRACT,
                'operation_id': operation.operation_id,
                'request_hash': request_hash,
                'disposition': 'conflict',
                'write_confirmed': False,
                'idempotent': True,
                'reason_code': 'native_text_operation_conflict',
                'receipt': False,
            }
        return self._operation_result(operation, idempotent=True)

    @staticmethod
    def _operation_result(operation, idempotent):
        return {
            'contract': NATIVE_TEXT_CONTRACT,
            'operation_id': operation.operation_id,
            'request_hash': operation.request_hash,
            'disposition': operation.status,
            'write_confirmed': operation.status == 'applied',
            'idempotent': idempotent,
            'reason_code': operation.reason_code or False,
            'receipt': {
                'receipt_id': operation.receipt_id,
                'source_hash_algorithm': (
                    operation.source_hash_algorithm or False
                ),
                'source_hash': operation.source_hash or False,
                'translation_hash': operation.translation_hash or False,
                'completed_at': fields.Datetime.to_string(
                    operation.completed_at,
                ),
            },
        }

    @staticmethod
    def _unpersisted_result(payload, disposition, reason_code):
        return {
            'contract': NATIVE_TEXT_CONTRACT,
            'operation_id': payload['operation_id'],
            'request_hash': payload['request_hash'],
            'disposition': disposition,
            'write_confirmed': False,
            'idempotent': False,
            'reason_code': reason_code,
            'receipt': False,
        }

    def _language_is_active(self, language):
        return bool(self.env['res.lang'].sudo().search_count([
            ('code', '=', language),
            ('active', '=', True),
        ]))

    @staticmethod
    def _is_canonical_uuid(value):
        if not isinstance(value, str):
            return False
        try:
            return str(uuid.UUID(value)) == value
        except (AttributeError, ValueError):
            return False

    @staticmethod
    def _is_digest(value):
        return isinstance(value, str) and bool(DIGEST_PATTERN.fullmatch(value))

    @staticmethod
    def _is_identifier(value):
        return (
            isinstance(value, str)
            and len(value) <= 128
            and bool(IDENTIFIER_PATTERN.fullmatch(value))
        )

    @staticmethod
    def _is_language(value):
        return (
            isinstance(value, str)
            and 1 <= len(value) <= 64
            and '\n' not in value
            and '\r' not in value
        )
