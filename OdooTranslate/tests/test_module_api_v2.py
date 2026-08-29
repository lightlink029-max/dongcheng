# -*- coding: utf-8 -*-

import json
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, TransactionCase, tagged

from .. import module_api, release_metadata
from ..controllers import odoo_translate_controller
from ..models import odoo_translate_config
from ..module_api import (
    build_signed_request,
    legacy_unlink_operation_id,
    verify_signed_request,
)


@tagged('post_install', '-at_install')
class TestModuleApiV2(TransactionCase):

    MODULE_UUID = '123e4567-e89b-12d3-a456-426614174000'
    LINK_ATTEMPT_ID = '123e4567-e89b-12d3-a456-426614174333'
    UNLINK_OPERATION_ID = '123e4567-e89b-12d3-a456-426614174111'
    STATUS_OPERATION_ID = '123e4567-e89b-12d3-a456-426614174222'
    SECRET = 'a' * 64

    def setUp(self):
        super().setUp()
        self.config = self.env['odoo_translate.config'].create({
            'module_uuid': self.MODULE_UUID,
            'shared_secret': self.SECRET,
            'link_attempt_id': self.LINK_ATTEMPT_ID,
            'unlink_operation_id': self.UNLINK_OPERATION_ID,
            'connection_status': 'connected',
            'has_api_key': True,
            'linked_email': 'owner@example.test',
            'connected_at': '2026-07-16 00:00:00',
            'last_status_check': '2026-07-16 00:00:00',
        })
        self.env['ir.config_parameter'].sudo().set_param(
            'odoo_translate.app_url',
            'https://saas.example.test',
        )

    def test_signatures_match_the_shared_php_vectors(self):
        status_body, status_headers = build_signed_request(
            self.MODULE_UUID,
            self.SECRET,
            '/api/module/v2/status',
            timestamp='1750000000',
            nonce='00112233445566778899aabbccddeeff',
        )
        unlink_body, unlink_headers = build_signed_request(
            self.MODULE_UUID,
            self.SECRET,
            '/api/module/v2/unlink',
            payload={
                'operation_id': self.UNLINK_OPERATION_ID,
                'uuid': self.MODULE_UUID,
            },
            timestamp='1750000000',
            nonce='00112233445566778899aabbccddeeff',
        )
        update_body, update_headers = build_signed_request(
            self.MODULE_UUID,
            self.SECRET,
            '/module/v2/update-status',
            payload={
                'has_api_key': True,
                'operation_id': self.STATUS_OPERATION_ID,
                'uuid': self.MODULE_UUID,
            },
            timestamp='1750000000',
            nonce='00112233445566778899aabbccddeeff',
        )

        self.assertEqual(
            status_body,
            b'{"uuid":"123e4567-e89b-12d3-a456-426614174000"}',
        )
        self.assertEqual(
            status_headers['X-OdooTranslate-Signature'],
            'v1=84b5a73f720a5eb801c1e9fde5154ad70734f554323378caec9d7ccf3da57298',
        )
        self.assertEqual(
            unlink_body,
            b'{"operation_id":"123e4567-e89b-12d3-a456-426614174111",'
            b'"uuid":"123e4567-e89b-12d3-a456-426614174000"}',
        )
        self.assertEqual(
            unlink_headers['X-OdooTranslate-Signature'],
            'v1=8f589dfc4ecc1e833778413ac3b4d4a0b20908c4404a526064203b8836729e6c',
        )
        self.assertEqual(
            update_body,
            b'{"has_api_key":true,'
            b'"operation_id":"123e4567-e89b-12d3-a456-426614174222",'
            b'"uuid":"123e4567-e89b-12d3-a456-426614174000"}',
        )
        self.assertEqual(
            update_headers['X-OdooTranslate-Signature'],
            'v1=0ad28e53ccf51932aaf6f2410f05d4af5f9c032a6807e19ccae6f02338364bf4',
        )

    def test_ping_exposes_normalized_module_and_protocol_identity(self):
        response = odoo_translate_controller.OdooTranslateController().ping()
        payload = json.loads(response.get_data(as_text=True))

        self.assertEqual(payload['version'], '1.16.0')
        self.assertEqual(payload['module_version'], '1.16.0')
        self.assertEqual(payload['protocol_version'], '1.1.0')
        self.assertEqual(
            payload['capabilities'],
            ['native_text_atomic_write_v1'],
        )
        self.assertEqual(module_api.PROTOCOL, 'odootranslate-module:v1')
        self.assertIn(payload['odoo_major'], (18, 19))
        self.assertEqual(payload['commit_sha'], release_metadata.COMMIT_SHA)
        self.assertEqual(payload['source_tree'], release_metadata.SOURCE_TREE)
        self.assertEqual(payload['build_id'], release_metadata.BUILD_ID)

        if release_metadata.COMMIT_SHA is None:
            self.assertIsNone(release_metadata.SOURCE_TREE)
            self.assertIsNone(release_metadata.BUILD_ID)
        else:
            self.assertEqual(payload['odoo_major'], release_metadata.ODOO_MAJOR)
            self.assertRegex(release_metadata.COMMIT_SHA, r'^[0-9a-f]{40}(?:[0-9a-f]{24})?$')
            self.assertRegex(release_metadata.SOURCE_TREE, r'^[0-9a-f]{40}(?:[0-9a-f]{24})?$')
            self.assertEqual(
                release_metadata.BUILD_ID,
                f'odoo{payload["odoo_major"]}-{payload["module_version"]}-'
                f'{release_metadata.COMMIT_SHA[:12]}',
            )

    def test_inbound_signature_binds_every_canonical_component(self):
        body, headers = build_signed_request(
            self.MODULE_UUID,
            self.SECRET,
            '/module/v2/update-status',
            payload={
                'has_api_key': True,
                'operation_id': self.STATUS_OPERATION_ID,
                'uuid': self.MODULE_UUID,
            },
            timestamp='1750000000',
            nonce='00112233445566778899aabbccddeeff',
        )
        verify = lambda **overrides: verify_signed_request(
            overrides.get('method', 'POST'),
            overrides.get('path', '/module/v2/update-status'),
            overrides.get('timestamp', '1750000000'),
            overrides.get('nonce', '00112233445566778899aabbccddeeff'),
            overrides.get('body', body),
            self.SECRET,
            overrides.get('signature', headers['X-OdooTranslate-Signature']),
            now=overrides.get('now', 1750000000),
        )

        self.assertTrue(verify())
        self.assertFalse(verify(method='PUT'))
        self.assertFalse(verify(path='/module/update-status'))
        self.assertFalse(verify(timestamp='1750000001'))
        self.assertFalse(verify(nonce='10112233445566778899aabbccddeeff'))
        self.assertFalse(verify(body=body + b' '))
        self.assertFalse(verify(now=1750000301))
        self.assertFalse(verify(signature=headers['X-OdooTranslate-Signature'].upper()))

    def test_legacy_unlink_operation_id_is_stable_and_secret_scoped(self):
        first = legacy_unlink_operation_id(self.MODULE_UUID, self.SECRET)

        self.assertEqual(first, '1367af2d-85c9-5ba0-a42f-09d7bfcf0295')
        self.assertEqual(
            first,
            legacy_unlink_operation_id(self.MODULE_UUID, self.SECRET),
        )
        self.assertNotEqual(
            first,
            legacy_unlink_operation_id(self.MODULE_UUID, 'b' * 64),
        )

    def test_connect_does_not_log_the_temporary_link_token(self):
        self.config.write({
            'connection_status': 'disconnected',
            'shared_secret': False,
            'link_attempt_id': False,
            'unlink_operation_id': False,
        })

        with patch.object(odoo_translate_config._logger, 'info') as info:
            action = self.config.action_connect()

        self.assertIn(self.config.link_token, action['url'])
        info.assert_called_once_with(
            '[OdooTranslate] Secure connection flow initiated'
        )

    def test_disconnect_uses_stable_operation_and_clears_after_generation_fence(self):
        response = self._response({
            'success': True,
            'data': {
                'link_attempt_id': self.LINK_ATTEMPT_ID,
                'status': 'unlinked',
            },
            'request_id': 'request-1',
        })

        with patch.object(
            odoo_translate_config.requests,
            'post',
            return_value=response,
        ) as post:
            self.config.action_disconnect()

        self.assertEqual(post.call_count, 1)
        sent = post.call_args
        self.assertEqual(
            sent.args[0],
            'https://saas.example.test/api/module/v2/unlink',
        )
        self.assertEqual(
            sent.kwargs['data'],
            b'{"operation_id":"123e4567-e89b-12d3-a456-426614174111",'
            b'"uuid":"123e4567-e89b-12d3-a456-426614174000"}',
        )
        self.assertEqual(self.config.connection_status, 'disconnected')
        self.assertFalse(self.config.shared_secret)
        self.assertFalse(self.config.link_attempt_id)
        self.assertFalse(self.config.unlink_operation_id)
        self.assertEqual(self.config.module_uuid, self.MODULE_UUID)

    def test_disconnect_rejects_a_success_for_another_link_generation(self):
        response = self._response({
            'success': True,
            'data': {
                'link_attempt_id': '123e4567-e89b-12d3-a456-426614174999',
                'status': 'unlinked',
            },
            'request_id': 'request-2',
        })

        with patch.object(odoo_translate_config.requests, 'post', return_value=response):
            with self.assertRaises(UserError):
                self.config.action_disconnect()

        self.assertEqual(self.config.connection_status, 'connected')
        self.assertEqual(self.config.shared_secret, self.SECRET)
        self.assertEqual(self.config.link_attempt_id, self.LINK_ATTEMPT_ID)
        self.assertTrue(self.config.has_api_key)

    def test_disconnect_network_retry_keeps_body_and_refreshes_envelope(self):
        response = self._response({
            'success': True,
            'data': {
                'link_attempt_id': self.LINK_ATTEMPT_ID,
                'status': 'unlinked',
            },
            'request_id': 'request-3',
        })
        network_error = odoo_translate_config.requests.exceptions.ConnectionError(
            'offline'
        )

        with patch.object(
            module_api.secrets,
            'token_hex',
            side_effect=['0' * 32, '1' * 32],
        ), patch.object(
            odoo_translate_config.requests,
            'post',
            side_effect=[network_error, response],
        ) as post:
            self.config.action_disconnect()

        self.assertEqual(post.call_count, 2)
        first = post.call_args_list[0].kwargs
        second = post.call_args_list[1].kwargs
        self.assertEqual(first['data'], second['data'])
        self.assertNotEqual(
            first['headers']['X-OdooTranslate-Nonce'],
            second['headers']['X-OdooTranslate-Nonce'],
        )
        self.assertNotEqual(
            first['headers']['X-OdooTranslate-Signature'],
            second['headers']['X-OdooTranslate-Signature'],
        )
        self.assertEqual(self.config.connection_status, 'disconnected')

    def test_disconnect_network_exhaustion_preserves_connection_state(self):
        network_error = odoo_translate_config.requests.exceptions.ConnectionError(
            'offline'
        )

        with patch.object(
            odoo_translate_config.requests,
            'post',
            side_effect=network_error,
        ) as post:
            with self.assertRaises(UserError):
                self.config.action_disconnect()

        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            post.call_args_list[0].kwargs['data'],
            post.call_args_list[1].kwargs['data'],
        )
        self.assertNotEqual(
            post.call_args_list[0].kwargs['headers']['X-OdooTranslate-Nonce'],
            post.call_args_list[1].kwargs['headers']['X-OdooTranslate-Nonce'],
        )
        self.assertEqual(self.config.connection_status, 'connected')
        self.assertEqual(self.config.shared_secret, self.SECRET)
        self.assertEqual(self.config.link_attempt_id, self.LINK_ATTEMPT_ID)

    def test_disconnect_retries_only_operation_in_progress_conflicts(self):
        processing = self._response({
            'success': False,
            'error': {'code': 'module_operation_in_progress'},
            'request_id': 'request-4',
        }, status=409)
        success = self._response({
            'success': True,
            'data': {
                'link_attempt_id': self.LINK_ATTEMPT_ID,
                'status': 'unlinked',
            },
            'request_id': 'request-5',
        })

        with patch.object(
            odoo_translate_config.requests,
            'post',
            side_effect=[processing, success],
        ) as post:
            self.config.action_disconnect()

        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            post.call_args_list[0].kwargs['data'],
            post.call_args_list[1].kwargs['data'],
        )
        self.assertNotEqual(
            post.call_args_list[0].kwargs['headers']['X-OdooTranslate-Nonce'],
            post.call_args_list[1].kwargs['headers']['X-OdooTranslate-Nonce'],
        )

    def test_disconnect_does_not_retry_another_conflict(self):
        conflict = self._response({
            'success': False,
            'error': {'code': 'module_operation_conflict'},
            'request_id': 'request-6',
        }, status=409)

        with patch.object(
            odoo_translate_config.requests,
            'post',
            return_value=conflict,
        ) as post:
            with self.assertRaises(UserError):
                self.config.action_disconnect()

        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.config.connection_status, 'connected')

    def test_legacy_disconnect_recovers_generation_from_unlink_receipt(self):
        self.config.write({
            'link_attempt_id': False,
            'unlink_operation_id': False,
        })
        unlinked = self._response({
            'success': True,
            'data': {
                'link_attempt_id': self.LINK_ATTEMPT_ID,
                'status': 'unlinked',
            },
            'request_id': 'request-8',
        })

        with patch.object(
            odoo_translate_config.requests,
            'post',
            return_value=unlinked,
        ) as post:
            self.config.action_disconnect()

        self.assertEqual(post.call_count, 1)
        self.assertEqual(
            post.call_args_list[0].args[0],
            'https://saas.example.test/api/module/v2/unlink',
        )
        self.assertEqual(
            post.call_args_list[0].kwargs['data'],
            (
                '{"operation_id":"%s","uuid":"%s"}'
                % (
                    legacy_unlink_operation_id(self.MODULE_UUID, self.SECRET),
                    self.MODULE_UUID,
                )
            ).encode('utf-8'),
        )
        self.assertEqual(self.config.connection_status, 'disconnected')

    def test_legacy_disconnect_retries_receipt_after_all_responses_were_lost(self):
        self.config.write({
            'link_attempt_id': False,
            'unlink_operation_id': False,
        })
        network_error = odoo_translate_config.requests.exceptions.ConnectionError(
            'response lost'
        )
        receipt = self._response({
            'success': True,
            'data': {
                'link_attempt_id': self.LINK_ATTEMPT_ID,
                'status': 'unlinked',
            },
            'request_id': 'request-9',
        })

        with patch.object(
            odoo_translate_config.requests,
            'post',
            side_effect=[network_error, network_error],
        ) as first_attempt:
            with self.assertRaises(UserError):
                self.config.action_disconnect()

        first_body = first_attempt.call_args_list[0].kwargs['data']
        self.assertEqual(first_attempt.call_count, 2)
        self.assertFalse(self.config.link_attempt_id)
        self.assertEqual(self.config.connection_status, 'connected')

        with patch.object(
            odoo_translate_config.requests,
            'post',
            return_value=receipt,
        ) as retry:
            self.config.action_disconnect()

        self.assertEqual(retry.call_count, 1)
        self.assertEqual(retry.call_args.kwargs['data'], first_body)
        self.assertEqual(self.config.connection_status, 'disconnected')

    def test_disconnect_detects_a_connection_started_during_remote_unlink(self):
        response = self._response({
            'success': True,
            'data': {
                'link_attempt_id': self.LINK_ATTEMPT_ID,
                'status': 'unlinked',
            },
            'request_id': 'request-10',
        })

        def start_connection(*args, **kwargs):
            self.config.write({
                'connection_status': 'pending',
                'link_token': 'new-link-token',
                'link_token_created_at': fields.Datetime.now(),
            })
            return response

        with patch.object(
            odoo_translate_config.requests,
            'post',
            side_effect=start_connection,
        ):
            with self.assertRaisesRegex(
                UserError,
                'link changed while disconnecting',
            ):
                self.config.action_disconnect()

    def test_refresh_bootstraps_generation_without_replacing_link_identity(self):
        self.config.link_attempt_id = False
        response = self._response({
            'success': True,
            'data': {
                'connected': True,
                'has_api_key': False,
                'link_attempt_id': self.LINK_ATTEMPT_ID,
            },
            'request_id': 'request-11',
        })
        original_connected_at = self.config.connected_at

        with patch.object(odoo_translate_config.requests, 'post', return_value=response):
            self.config.action_refresh_status()

        self.assertEqual(self.config.connection_status, 'connected')
        self.assertFalse(self.config.has_api_key)
        self.assertEqual(self.config.link_attempt_id, self.LINK_ATTEMPT_ID)
        self.assertEqual(self.config.shared_secret, self.SECRET)
        self.assertEqual(self.config.linked_email, 'owner@example.test')
        self.assertEqual(self.config.connected_at, original_connected_at)

    def test_refresh_rejects_another_link_generation(self):
        response = self._response({
            'success': True,
            'data': {
                'connected': True,
                'has_api_key': False,
                'link_attempt_id': '123e4567-e89b-12d3-a456-426614174999',
            },
            'request_id': 'request-12',
        })

        with patch.object(odoo_translate_config.requests, 'post', return_value=response):
            with self.assertRaises(UserError):
                self.config.action_refresh_status()

        self.assertTrue(self.config.has_api_key)
        self.assertEqual(self.config.link_attempt_id, self.LINK_ATTEMPT_ID)

    def test_callback_is_idempotent_after_the_token_is_consumed(self):
        self.config.write({
            'connection_status': 'pending',
            'has_api_key': False,
            'shared_secret': False,
            'link_attempt_id': False,
            'unlink_operation_id': False,
            'link_token': 'link-token',
            'link_token_created_at': fields.Datetime.now(),
        })
        callback = {
            'email': 'owner@example.test',
            'has_api_key': True,
            'link_attempt_id': self.LINK_ATTEMPT_ID,
            'shared_secret': self.SECRET,
            'token': 'link-token',
            'unlink_operation_id': self.UNLINK_OPERATION_ID,
            'uuid': self.MODULE_UUID,
        }

        first = self._controller_call('callback', callback)
        second = self._controller_call('callback', callback)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(self._payload(first)['data']['idempotent'])
        self.assertTrue(self._payload(second)['data']['idempotent'])
        self.assertFalse(self.config.link_token)
        self.assertEqual(self.config.connection_status, 'connected')
        self.assertEqual(self.config.shared_secret, self.SECRET)
        self.assertEqual(self.config.link_attempt_id, self.LINK_ATTEMPT_ID)
        self.assertEqual(self.config.unlink_operation_id, self.UNLINK_OPERATION_ID)

    def test_callback_rejects_a_different_operation_after_token_consumption(self):
        self.config.write({
            'link_token': False,
            'link_token_created_at': False,
        })
        callback = {
            'email': 'owner@example.test',
            'has_api_key': True,
            'link_attempt_id': self.LINK_ATTEMPT_ID,
            'shared_secret': self.SECRET,
            'token': 'consumed-token',
            'unlink_operation_id': '123e4567-e89b-12d3-a456-426614174999',
            'uuid': self.MODULE_UUID,
        }

        response = self._controller_call('callback', callback)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            self._payload(response)['error']['code'],
            'module_callback_auth_failed',
        )
        self.assertEqual(self.config.unlink_operation_id, self.UNLINK_OPERATION_ID)

    def test_callback_retry_must_match_email_and_api_key_status(self):
        self.config.write({
            'link_token': False,
            'link_token_created_at': False,
        })
        callback = {
            'email': 'changed@example.test',
            'has_api_key': False,
            'link_attempt_id': self.LINK_ATTEMPT_ID,
            'shared_secret': self.SECRET,
            'token': 'consumed-token',
            'unlink_operation_id': self.UNLINK_OPERATION_ID,
            'uuid': self.MODULE_UUID,
        }

        response = self._controller_call('callback', callback)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            self._payload(response)['error']['code'],
            'module_callback_auth_failed',
        )
        self.assertEqual(self.config.linked_email, 'owner@example.test')
        self.assertTrue(self.config.has_api_key)

    def test_update_status_journals_exact_idempotence_and_rejects_replay(self):
        operation = {
            'has_api_key': False,
            'operation_id': self.STATUS_OPERATION_ID,
            'uuid': self.MODULE_UUID,
        }
        body, headers = self._signed_update(operation, nonce='0' * 32)

        first = self._controller_call_raw('update_status', body, headers)
        replay = self._controller_call_raw('update_status', body, headers)
        retry_body, retry_headers = self._signed_update(
            operation,
            nonce='1' * 32,
        )
        retry = self._controller_call_raw(
            'update_status',
            retry_body,
            retry_headers,
        )

        self.assertEqual(first.status_code, 200)
        self.assertFalse(self._payload(first)['data']['idempotent'])
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(
            self._payload(replay)['error']['code'],
            'module_replay_detected',
        )
        self.assertEqual(retry.status_code, 200)
        self.assertTrue(self._payload(retry)['data']['idempotent'])
        self.assertFalse(self.config.has_api_key)

        journal = self.env['odoo_translate.module_api_operation'].sudo().search([
            ('config_id', '=', self.config.id),
            ('operation_id', '=', self.STATUS_OPERATION_ID),
        ])
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal.link_attempt_id, self.LINK_ATTEMPT_ID)
        self.assertEqual(journal.status, 'succeeded')
        self.assertEqual(journal.attempt_count, 2)

    def test_update_status_rejects_operation_id_reuse_with_another_payload(self):
        first_operation = {
            'has_api_key': False,
            'operation_id': self.STATUS_OPERATION_ID,
            'uuid': self.MODULE_UUID,
        }
        body, headers = self._signed_update(first_operation, nonce='2' * 32)
        self.assertEqual(
            self._controller_call_raw('update_status', body, headers).status_code,
            200,
        )

        conflicting_operation = dict(first_operation, has_api_key=True)
        conflict_body, conflict_headers = self._signed_update(
            conflicting_operation,
            nonce='3' * 32,
        )
        conflict = self._controller_call_raw(
            'update_status',
            conflict_body,
            conflict_headers,
        )

        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(
            self._payload(conflict)['error']['code'],
            'module_operation_conflict',
        )
        self.assertFalse(self.config.has_api_key)

    def test_update_status_requires_the_exact_canonical_body(self):
        operation = {
            'has_api_key': False,
            'operation_id': self.STATUS_OPERATION_ID,
            'uuid': self.MODULE_UUID,
        }
        body, headers = self._signed_update(operation, nonce='4' * 32)

        response = self._controller_call_raw(
            'update_status',
            body + b' ',
            headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self._payload(response)['error']['code'],
            'module_request_invalid',
        )
        self.assertTrue(self.config.has_api_key)

    def test_update_status_rejects_query_parameters(self):
        operation = {
            'has_api_key': False,
            'operation_id': self.STATUS_OPERATION_ID,
            'uuid': self.MODULE_UUID,
        }
        body, headers = self._signed_update(operation, nonce='5' * 32)

        response = self._controller_call_raw(
            'update_status',
            body,
            headers,
            query_string=b'debug=1',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self._payload(response)['error']['code'],
            'module_request_invalid',
        )
        self.assertTrue(self.config.has_api_key)

    def test_update_status_failure_is_journalled_and_recoverable(self):
        operation = {
            'has_api_key': False,
            'operation_id': self.STATUS_OPERATION_ID,
            'uuid': self.MODULE_UUID,
        }
        body, headers = self._signed_update(operation, nonce='6' * 32)

        with patch.object(
            odoo_translate_config.OdooTranslateConfig,
            'write',
            side_effect=RuntimeError('status write failed'),
        ):
            failed = self._controller_call_raw('update_status', body, headers)

        self.assertEqual(failed.status_code, 500)
        journal = self.env['odoo_translate.module_api_operation'].sudo().search([
            ('config_id', '=', self.config.id),
            ('operation_id', '=', self.STATUS_OPERATION_ID),
        ])
        self.assertEqual(journal.status, 'failed')
        self.assertEqual(journal.last_error_code, 'module_request_failed')
        self.assertEqual(journal.attempt_count, 1)
        self.assertTrue(self.config.has_api_key)

        retry_body, retry_headers = self._signed_update(
            operation,
            nonce='7' * 32,
        )
        recovered = self._controller_call_raw(
            'update_status',
            retry_body,
            retry_headers,
        )

        self.assertEqual(recovered.status_code, 200)
        self.assertFalse(self._payload(recovered)['data']['idempotent'])
        journal.invalidate_recordset()
        self.assertEqual(journal.status, 'succeeded')
        self.assertFalse(journal.last_error_code)
        self.assertEqual(journal.attempt_count, 2)
        self.assertFalse(self.config.has_api_key)

    def test_legacy_update_status_returns_426_with_request_id(self):
        response = self._controller_call('legacy_update_status', {})
        payload = self._payload(response)

        self.assertEqual(response.status_code, 426)
        self.assertEqual(
            payload['error']['code'],
            'module_protocol_upgrade_required',
        )
        self.assertEqual(
            response.headers['X-OdooTranslate-Request-Id'],
            payload['request_id'],
        )

    def _signed_update(self, payload, nonce):
        return build_signed_request(
            self.MODULE_UUID,
            self.SECRET,
            '/module/v2/update-status',
            payload=payload,
            timestamp=str(int(time.time())),
            nonce=nonce,
        )

    def _controller_call(self, method, payload):
        return self._controller_call_raw(
            method,
            json.dumps(payload).encode('utf-8'),
            {},
        )

    def _controller_call_raw(self, method, body, headers, query_string=b''):
        fake_request = SimpleNamespace(
            env=self.env,
            httprequest=SimpleNamespace(
                data=body,
                headers=headers,
                query_string=query_string,
            ),
        )
        controller = odoo_translate_controller.OdooTranslateController()

        with patch.object(odoo_translate_controller, 'request', fake_request):
            return getattr(controller, method)()

    @staticmethod
    def _payload(response):
        return json.loads(response.get_data(as_text=True))

    @staticmethod
    def _response(payload, status=200):
        response = Mock()
        response.status_code = status
        response.ok = 200 <= status < 300
        response.headers = {
            'X-OdooTranslate-Request-Id': payload.get('request_id', 'request')
        }
        response.json.return_value = payload

        return response


@tagged('post_install', '-at_install')
class TestModuleApiV2Http(HttpCase):

    def setUp(self):
        super().setUp()
        self.config = self.env['odoo_translate.config'].create({
            'module_uuid': TestModuleApiV2.MODULE_UUID,
            'shared_secret': TestModuleApiV2.SECRET,
            'link_attempt_id': TestModuleApiV2.LINK_ATTEMPT_ID,
            'unlink_operation_id': TestModuleApiV2.UNLINK_OPERATION_ID,
            'connection_status': 'connected',
            'has_api_key': True,
            'linked_email': 'owner@example.test',
        })

    def test_signed_status_update_crosses_the_real_http_route(self):
        body, headers = build_signed_request(
            TestModuleApiV2.MODULE_UUID,
            TestModuleApiV2.SECRET,
            '/module/v2/update-status',
            payload={
                'has_api_key': False,
                'operation_id': TestModuleApiV2.STATUS_OPERATION_ID,
                'uuid': TestModuleApiV2.MODULE_UUID,
            },
            nonce='8' * 32,
        )

        response = self.url_open(
            '/module/v2/update-status',
            data=body,
            headers=headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['data']['status'], 'updated')
        self.config.invalidate_recordset()
        self.assertFalse(self.config.has_api_key)

    def test_link_callback_crosses_the_real_http_route(self):
        self.config.write({
            'connection_status': 'pending',
            'has_api_key': False,
            'shared_secret': False,
            'link_attempt_id': False,
            'unlink_operation_id': False,
            'link_token': 'http-link-token',
            'link_token_created_at': fields.Datetime.now(),
        })
        callback = {
            'email': 'owner@example.test',
            'has_api_key': True,
            'link_attempt_id': TestModuleApiV2.LINK_ATTEMPT_ID,
            'shared_secret': TestModuleApiV2.SECRET,
            'token': 'http-link-token',
            'unlink_operation_id': TestModuleApiV2.UNLINK_OPERATION_ID,
            'uuid': TestModuleApiV2.MODULE_UUID,
        }

        response = self.url_open(
            '/module/callback',
            data=json.dumps(callback).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.config.invalidate_recordset()
        self.assertEqual(self.config.connection_status, 'connected')
        self.assertEqual(self.config.link_attempt_id, TestModuleApiV2.LINK_ATTEMPT_ID)
