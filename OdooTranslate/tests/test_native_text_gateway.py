# -*- coding: utf-8 -*-

import uuid

from odoo.exceptions import AccessDenied, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from .. import module_api


@tagged('post_install', '-at_install')
class TestNativeTextGateway(TransactionCase):

    MODULE_UUID = '123e4567-e89b-12d3-a456-426614174500'
    LINK_ATTEMPT_ID = '123e4567-e89b-12d3-a456-426614174501'
    SECRET = 'b' * 64

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.lang']._activate_lang('fr_FR')
        cls.env['res.lang']._activate_lang('de_DE')

    def setUp(self):
        super().setUp()
        self.config = self.env['odoo_translate.config'].create({
            'module_uuid': self.MODULE_UUID,
            'shared_secret': self.SECRET,
            'link_attempt_id': self.LINK_ATTEMPT_ID,
            'connection_status': 'connected',
            'has_api_key': True,
        })
        self.category = self.env['res.partner.category'].create({
            'name': 'Cafe\u0301\r\nsource ',
        })
        self.gateway = self.env['odoo_translate.translation_gateway']

    def test_apply_atomically_checks_source_writes_target_and_returns_receipt(self):
        payload = self._apply_payload(
            self.category,
            source='Caf\u00e9\nsource ',
            translation='U\u0308bersetzung\r\n ',
        )

        result = self.gateway.apply_native_text_v1(payload)

        self.assertEqual('applied', result['disposition'])
        self.assertTrue(result['write_confirmed'])
        self.assertFalse(result['idempotent'])
        self.assertFalse(result['reason_code'])
        self.assertEqual(payload['operation_id'], result['operation_id'])
        self.assertEqual(payload['request_hash'], result['request_hash'])
        self.assertEqual(
            payload['translation_hash'],
            result['receipt']['translation_hash'],
        )
        self.assertEqual(
            'U\u0308bersetzung\r\n ',
            self.category.with_context(lang='de_DE').name,
        )
        self.assertEqual(
            'Cafe\u0301\r\nsource ',
            self.category.with_context(lang='en_US').name,
        )

        stored = self.category._fields['name']._get_stored_translations(
            self.category,
        )
        self.assertEqual('U\u0308bersetzung\r\n ', stored['de_DE'])

        operation = self.env['odoo_translate.native_text_operation'].search([
            ('operation_id', '=', payload['operation_id']),
        ])
        self.assertEqual('applied', operation.status)
        self.assertEqual(payload['request_hash'], operation.request_hash)
        serialized = repr(operation.read()[0])
        self.assertNotIn('Cafe', serialized)
        self.assertNotIn('bersetzung', serialized)

    def test_request_hash_and_signatures_match_the_shared_protocol_vectors(self):
        payload = {
            'contract': module_api.NATIVE_TEXT_CONTRACT,
            'source_hash_algorithm': module_api.NATIVE_TEXT_SOURCE_HASH_ALGORITHM,
            'module_uuid': self.MODULE_UUID,
            'link_attempt_id': self.LINK_ATTEMPT_ID,
            'operation_id': '123e4567-e89b-12d3-a456-426614174502',
            'model_name': 'res.partner.category',
            'record_id': 42,
            'field_name': 'name',
            'source_lang': 'en_US',
            'target_lang': 'fr_FR',
            'expected_source_hash': 'a' * 64,
            'translation_hash': 'c' * 64,
        }

        request_hash = module_api.native_text_request_hash(payload)

        self.assertEqual(
            '94b2aae70fc18aa1819e08d324e0ee92d3b84600ec58d764940e46889af586e9',
            request_hash,
        )
        self.assertEqual(
            'a14b2c23d5d93009fd972ec43576243e9a5b41a50d383d2f404743479283cd06',
            module_api.sign_native_text_operation(
                'apply',
                request_hash,
                self.SECRET,
            ),
        )
        self.assertEqual(
            'c745c3d6b257655cee8673c293d64a9c0d06bb2856365dca9668970c70a5507c',
            module_api.sign_native_text_operation(
                'reconcile',
                request_hash,
                self.SECRET,
            ),
        )

    def test_exact_replay_returns_the_same_receipt_without_another_write(self):
        payload = self._apply_payload(self.category)
        first = self.gateway.apply_native_text_v1(payload)

        replay = self.gateway.apply_native_text_v1(dict(payload))

        self.assertEqual('applied', replay['disposition'])
        self.assertTrue(replay['idempotent'])
        self.assertEqual(
            first['receipt']['receipt_id'],
            replay['receipt']['receipt_id'],
        )
        self.assertEqual(1, self.env['odoo_translate.native_text_operation'].search_count([
            ('operation_id', '=', payload['operation_id']),
        ]))

    def test_operation_id_cannot_be_reused_for_a_different_request(self):
        payload = self._apply_payload(self.category)
        self.gateway.apply_native_text_v1(payload)
        divergent = self._apply_payload(
            self.category,
            operation_id=payload['operation_id'],
            translation='Andere Uebersetzung',
        )

        result = self.gateway.apply_native_text_v1(divergent)

        self.assertEqual('conflict', result['disposition'])
        self.assertFalse(result['write_confirmed'])
        self.assertEqual('native_text_operation_conflict', result['reason_code'])
        self.assertEqual(
            'Traduction cible',
            self.category.with_context(lang='de_DE').name,
        )

    def test_missing_stored_source_is_refused_without_odoo_fallback(self):
        payload = self._apply_payload(
            self.category,
            source_lang='fr_FR',
            source='Cafe\u0301\r\nsource ',
        )

        result = self.gateway.apply_native_text_v1(payload)

        self.assertEqual('refused', result['disposition'])
        self.assertEqual(
            'native_source_language_not_stored',
            result['reason_code'],
        )
        self.assertFalse(result['write_confirmed'])
        stored = self.category._fields['name']._get_stored_translations(
            self.category,
        )
        self.assertNotIn('de_DE', stored)

    def test_changed_source_is_refused_before_write(self):
        payload = self._apply_payload(self.category)
        self.category.with_context(lang='en_US').write({'name': 'Edited source'})

        result = self.gateway.apply_native_text_v1(payload)

        self.assertEqual('refused', result['disposition'])
        self.assertEqual('native_source_changed', result['reason_code'])
        self.assertFalse(result['write_confirmed'])

    def test_identical_stored_target_is_refused_as_an_already_translated_skip(self):
        self.category.with_context(lang='de_DE').write({
            'name': 'Traduction cible',
        })
        payload = self._apply_payload(self.category)

        result = self.gateway.apply_native_text_v1(payload)

        self.assertEqual('refused', result['disposition'])
        self.assertEqual('native_text_already_translated', result['reason_code'])
        self.assertFalse(result['write_confirmed'])
        operation = self.env['odoo_translate.native_text_operation'].search([
            ('operation_id', '=', payload['operation_id']),
        ])
        self.assertEqual('refused', operation.status)
        self.assertEqual('native_text_already_translated', operation.reason_code)

    def test_reconcile_seals_an_absent_operation_against_a_late_write(self):
        payload = self._apply_payload(self.category)
        reconcile = self._reconcile_payload(payload)

        sealed = self.gateway.reconcile_native_text_v1(reconcile)
        late = self.gateway.apply_native_text_v1(payload)

        self.assertEqual('sealed_without_write', sealed['disposition'])
        self.assertFalse(sealed['idempotent'])
        self.assertEqual('sealed_without_write', late['disposition'])
        self.assertTrue(late['idempotent'])
        self.assertEqual(
            sealed['receipt']['receipt_id'],
            late['receipt']['receipt_id'],
        )
        self.assertEqual(
            'native_text_operation_sealed_without_write',
            late['reason_code'],
        )
        stored = self.category._fields['name']._get_stored_translations(
            self.category,
        )
        self.assertNotIn('de_DE', stored)

    def test_reconcile_returns_an_existing_applied_receipt(self):
        payload = self._apply_payload(self.category)
        applied = self.gateway.apply_native_text_v1(payload)

        reconciled = self.gateway.reconcile_native_text_v1(
            self._reconcile_payload(payload),
        )

        self.assertEqual('applied', reconciled['disposition'])
        self.assertTrue(reconciled['write_confirmed'])
        self.assertTrue(reconciled['idempotent'])
        self.assertEqual(
            applied['receipt']['receipt_id'],
            reconciled['receipt']['receipt_id'],
        )

    def test_signature_and_translation_hash_bind_the_complete_request(self):
        payload = self._apply_payload(self.category)
        payload['translation_value'] = 'Tampered value'

        with self.assertRaises(AccessDenied):
            self.gateway.apply_native_text_v1(payload)

        self.assertFalse(self.env['odoo_translate.native_text_operation'].search([
            ('operation_id', '=', payload['operation_id']),
        ]))

    def test_stale_link_generation_is_refused_without_a_write(self):
        payload = self._apply_payload(self.category)
        self.config.write({'link_attempt_id': str(uuid.uuid4())})

        result = self.gateway.apply_native_text_v1(payload)

        self.assertEqual('refused', result['disposition'])
        self.assertEqual('stale_link_generation', result['reason_code'])
        self.assertFalse(result['write_confirmed'])

    def test_field_access_is_enforced_as_the_rpc_user(self):
        restricted_user = new_test_user(
            self.env,
            login='odootranslate_native_text_user',
            groups='base.group_user',
            context={'no_reset_password': True},
        )
        payload = self._apply_payload(self.category)
        field = self.category._fields['name']
        original_groups = field.groups
        field.groups = 'base.group_system'

        try:
            result = self.gateway.with_user(
                restricted_user,
            ).apply_native_text_v1(payload)
        finally:
            field.groups = original_groups

        self.assertEqual('refused', result['disposition'])
        self.assertEqual('native_text_access_denied', result['reason_code'])
        self.assertFalse(result['write_confirmed'])

    def test_non_native_text_field_is_refused(self):
        payload = self._apply_payload(
            self.category,
            field_name='active',
            source='True',
        )

        result = self.gateway.apply_native_text_v1(payload)

        self.assertEqual('refused', result['disposition'])
        self.assertEqual('native_text_field_not_supported', result['reason_code'])

    def test_journal_is_append_only(self):
        payload = self._apply_payload(self.category)
        self.gateway.apply_native_text_v1(payload)
        operation = self.env['odoo_translate.native_text_operation'].search([
            ('operation_id', '=', payload['operation_id']),
        ])

        with self.assertRaises(UserError):
            operation.write({'reason_code': 'tampered'})
        with self.assertRaises(UserError):
            operation.unlink()

    def _apply_payload(
        self,
        record,
        source='Cafe\u0301\r\nsource ',
        translation='Traduction cible',
        source_lang='en_US',
        target_lang='de_DE',
        field_name='name',
        operation_id=None,
    ):
        payload = {
            'contract': module_api.NATIVE_TEXT_CONTRACT,
            'source_hash_algorithm': module_api.NATIVE_TEXT_SOURCE_HASH_ALGORITHM,
            'module_uuid': self.MODULE_UUID,
            'link_attempt_id': self.LINK_ATTEMPT_ID,
            'operation_id': operation_id or str(uuid.uuid4()),
            'model_name': record._name,
            'record_id': record.id,
            'field_name': field_name,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'expected_source_hash': module_api.native_text_value_hash(source),
            'translation_hash': module_api.native_text_value_hash(translation),
            'translation_value': translation,
        }
        payload['request_hash'] = module_api.native_text_request_hash(payload)
        payload['signature'] = 'v1=%s' % module_api.sign_native_text_operation(
            'apply',
            payload['request_hash'],
            self.SECRET,
        )
        return payload

    def _reconcile_payload(self, apply_payload):
        payload = {
            'contract': module_api.NATIVE_TEXT_CONTRACT,
            'module_uuid': apply_payload['module_uuid'],
            'link_attempt_id': apply_payload['link_attempt_id'],
            'operation_id': apply_payload['operation_id'],
            'request_hash': apply_payload['request_hash'],
        }
        payload['signature'] = 'v1=%s' % module_api.sign_native_text_operation(
            'reconcile',
            payload['request_hash'],
            self.SECRET,
        )
        return payload
