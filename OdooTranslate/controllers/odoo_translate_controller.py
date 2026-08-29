# -*- coding: utf-8 -*-
"""HTTP endpoints used by the OdooTranslate application."""

import hashlib
import hmac
import json
import logging
import uuid

from odoo import http, release as odoo_release
from odoo.http import Response, request

from ..module_api import (
    MODULE_CAPABILITIES,
    NONCE_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    json_body,
    verify_signed_request,
)
from ..release_metadata import (
    BUILD_ID,
    COMMIT_SHA,
    MODULE_VERSION,
    ODOO_MAJOR,
    PROTOCOL_VERSION,
    SOURCE_TREE,
)


_logger = logging.getLogger(__name__)

CALLBACK_FIELDS = {
    'email',
    'has_api_key',
    'link_attempt_id',
    'shared_secret',
    'token',
    'unlink_operation_id',
    'uuid',
}
REQUEST_ID_HEADER = 'X-OdooTranslate-Request-Id'
UPDATE_STATUS_FIELDS = {'has_api_key', 'operation_id', 'uuid'}
UPDATE_STATUS_PATH = '/module/v2/update-status'


def _new_request_id():
    return str(uuid.uuid4())


def _json_response(
    request_id,
    status,
    success,
    data=None,
    error_code=None,
    error_message=None,
):
    payload = {
        'request_id': request_id,
        'success': success,
    }
    if data is not None:
        payload['data'] = data
    if error_code is not None:
        payload['error'] = {
            'code': error_code,
            'message': error_message or 'The module request could not be completed.',
        }

    response = Response(
        json.dumps(payload, sort_keys=True, separators=(',', ':')),
        status=status,
        content_type='application/json',
    )
    response.headers[REQUEST_ID_HEADER] = request_id

    return response


def _canonical_uuid(value):
    if not isinstance(value, str):
        return None

    try:
        canonical = str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return None

    return canonical if value == canonical else None


def _json_object(raw_body):
    try:
        payload = json.loads(raw_body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def _lock_config(config):
    config.flush_recordset()
    config.env.cr.execute(
        'SELECT id FROM odoo_translate_config WHERE id = %s FOR UPDATE',
        [config.id],
    )
    config.invalidate_recordset()


class OdooTranslateController(http.Controller):

    @http.route(
        '/module/callback',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        readonly=False,
    )
    def callback(self, **kwargs):
        """Confirm a link generation, including retries after token consumption."""
        request_id = _new_request_id()
        data = _json_object(request.httprequest.data)

        if data is None or set(data) != CALLBACK_FIELDS:
            return _json_response(
                request_id,
                400,
                False,
                error_code='module_callback_invalid',
            )

        module_uuid = _canonical_uuid(data.get('uuid'))
        link_attempt_id = _canonical_uuid(data.get('link_attempt_id'))
        unlink_operation_id = _canonical_uuid(data.get('unlink_operation_id'))
        token = data.get('token')
        email = data.get('email')
        has_api_key = data.get('has_api_key')
        shared_secret = data.get('shared_secret')

        if (
            module_uuid is None
            or link_attempt_id is None
            or unlink_operation_id is None
            or not isinstance(token, str)
            or not token
            or not isinstance(email, str)
            or not email
            or len(email) > 320
            or type(has_api_key) is not bool
            or not isinstance(shared_secret, str)
            or len(shared_secret) != 64
            or any(character not in '0123456789abcdef' for character in shared_secret)
        ):
            return _json_response(
                request_id,
                400,
                False,
                error_code='module_callback_invalid',
            )

        config = request.env['odoo_translate.config'].sudo().search([
            ('module_uuid', '=', module_uuid),
        ], limit=1)
        if not config:
            _logger.warning(
                '[OdooTranslate] Module callback rejected request_id=%s reason=config_missing',
                request_id,
            )
            return _json_response(
                request_id,
                404,
                False,
                error_code='module_not_found',
            )

        try:
            with config.env.cr.savepoint():
                _lock_config(config)

                if config.is_same_link_generation(
                    email,
                    has_api_key,
                    shared_secret,
                    link_attempt_id,
                    unlink_operation_id,
                ):
                    _logger.info(
                        '[OdooTranslate] Module callback recovered request_id=%s link_attempt_id=%s',
                        request_id,
                        link_attempt_id,
                    )
                    return _json_response(
                        request_id,
                        200,
                        True,
                        data={
                            'has_api_key': config.has_api_key,
                            'idempotent': True,
                            'link_attempt_id': link_attempt_id,
                            'status': 'linked',
                        },
                    )

                if (
                    not isinstance(config.link_token, str)
                    or not hmac.compare_digest(config.link_token, token)
                ):
                    _logger.warning(
                        '[OdooTranslate] Module callback rejected request_id=%s reason=token_invalid',
                        request_id,
                    )
                    return _json_response(
                        request_id,
                        401,
                        False,
                        error_code='module_callback_auth_failed',
                    )

                linked = config.confirm_link(
                    email,
                    has_api_key,
                    shared_secret,
                    link_attempt_id,
                    unlink_operation_id,
                )
                if not linked:
                    return _json_response(
                        request_id,
                        409,
                        False,
                        error_code='module_callback_rejected',
                    )
        except Exception as error:
            _logger.error(
                '[OdooTranslate] Module callback failed request_id=%s exception=%s',
                request_id,
                error.__class__.__name__,
            )
            return _json_response(
                request_id,
                500,
                False,
                error_code='module_request_failed',
            )

        _logger.info(
            '[OdooTranslate] Module callback completed request_id=%s link_attempt_id=%s',
            request_id,
            link_attempt_id,
        )
        return _json_response(
            request_id,
            200,
            True,
            data={
                'has_api_key': has_api_key,
                'idempotent': False,
                'link_attempt_id': link_attempt_id,
                'status': 'linked',
            },
        )

    @http.route('/module/update-status', type='http', auth='none', methods=['POST'], csrf=False)
    def legacy_update_status(self, **kwargs):
        """Reject the unsigned legacy protocol explicitly."""
        request_id = _new_request_id()

        return _json_response(
            request_id,
            426,
            False,
            error_code='module_protocol_upgrade_required',
            error_message='Use POST /module/v2/update-status.',
        )

    @http.route(
        UPDATE_STATUS_PATH,
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        readonly=False,
    )
    def update_status(self, **kwargs):
        """Apply an authenticated and idempotent API-key status operation."""
        request_id = _new_request_id()
        raw_body = request.httprequest.data
        data = _json_object(raw_body)
        content_type = request.httprequest.headers.get('Content-Type', '')
        media_type = content_type.split(';', 1)[0].strip().lower()
        query_string = request.httprequest.query_string

        if (
            data is None
            or set(data) != UPDATE_STATUS_FIELDS
            or raw_body != json_body(data)
            or media_type != 'application/json'
            or bool(query_string)
            or len(raw_body) > 512
        ):
            return _json_response(
                request_id,
                400,
                False,
                error_code='module_request_invalid',
            )

        module_uuid = _canonical_uuid(data.get('uuid'))
        operation_id = _canonical_uuid(data.get('operation_id'))
        has_api_key = data.get('has_api_key')
        if (
            module_uuid is None
            or operation_id is None
            or type(has_api_key) is not bool
        ):
            return _json_response(
                request_id,
                400,
                False,
                error_code='module_request_invalid',
            )

        config = request.env['odoo_translate.config'].sudo().search([
            ('module_uuid', '=', module_uuid),
        ], limit=1)
        if not config:
            return _json_response(
                request_id,
                401,
                False,
                error_code='module_auth_failed',
            )

        if config.connection_status != 'connected' or not config.shared_secret:
            return _json_response(
                request_id,
                401,
                False,
                error_code='module_auth_failed',
            )

        shared_secret = config.shared_secret
        link_attempt_id = config.link_attempt_id or False
        timestamp = request.httprequest.headers.get(TIMESTAMP_HEADER)
        nonce = request.httprequest.headers.get(NONCE_HEADER)
        signature = request.httprequest.headers.get(SIGNATURE_HEADER)
        if not verify_signed_request(
            'POST',
            UPDATE_STATUS_PATH,
            timestamp,
            nonce,
            raw_body,
            shared_secret,
            signature,
        ):
            _logger.warning(
                '[OdooTranslate] Module API authentication rejected request_id=%s',
                request_id,
            )
            return _json_response(
                request_id,
                401,
                False,
                error_code='module_auth_failed',
            )

        try:
            with request.env.cr.savepoint():
                _lock_config(config)
        except Exception as error:
            _logger.error(
                '[OdooTranslate] Module API lock failed request_id=%s exception=%s',
                request_id,
                error.__class__.__name__,
            )
            return _json_response(
                request_id,
                503,
                False,
                error_code='module_journal_unavailable',
            )

        if (
            config.connection_status != 'connected'
            or config.shared_secret != shared_secret
            or (config.link_attempt_id or False) != link_attempt_id
        ):
            return _json_response(
                request_id,
                401,
                False,
                error_code='module_auth_failed',
            )

        try:
            with request.env.cr.savepoint():
                reserved = request.env[
                    'odoo_translate.module_api_nonce'
                ].sudo().reserve(config, nonce, request_id)
        except Exception as error:
            _logger.error(
                '[OdooTranslate] Module nonce journal failed request_id=%s exception=%s',
                request_id,
                error.__class__.__name__,
            )
            return _json_response(
                request_id,
                503,
                False,
                error_code='module_journal_unavailable',
            )

        if not reserved:
            _logger.warning(
                '[OdooTranslate] Module API replay rejected request_id=%s',
                request_id,
            )
            return _json_response(
                request_id,
                409,
                False,
                error_code='module_replay_detected',
            )

        try:
            with request.env.cr.savepoint():
                result = request.env[
                    'odoo_translate.module_api_operation'
                ].sudo().apply_status_update(
                    config,
                    operation_id,
                    hashlib.sha256(raw_body).hexdigest(),
                    has_api_key,
                    request_id,
                )
        except Exception as error:
            _logger.error(
                '[OdooTranslate] Module operation failed request_id=%s exception=%s',
                request_id,
                error.__class__.__name__,
            )
            try:
                with request.env.cr.savepoint():
                    request.env[
                        'odoo_translate.module_api_operation'
                    ].sudo().record_status_failure(
                        config,
                        operation_id,
                        hashlib.sha256(raw_body).hexdigest(),
                        has_api_key,
                        request_id,
                        'module_request_failed',
                    )
            except Exception as journal_error:
                _logger.error(
                    '[OdooTranslate] Module failure journal unavailable request_id=%s exception=%s',
                    request_id,
                    journal_error.__class__.__name__,
                )
                return _json_response(
                    request_id,
                    503,
                    False,
                    error_code='module_journal_unavailable',
                )

            return _json_response(
                request_id,
                500,
                False,
                error_code='module_request_failed',
            )

        if not result['succeeded']:
            return _json_response(
                request_id,
                result['http_status'],
                False,
                error_code=result['code'],
            )

        _logger.info(
            '[OdooTranslate] Module status operation completed request_id=%s operation_id=%s idempotent=%s',
            request_id,
            operation_id,
            result['idempotent'],
        )
        return _json_response(
            request_id,
            200,
            True,
            data={
                'has_api_key': result['has_api_key'],
                'idempotent': result['idempotent'],
                'operation_id': operation_id,
                'status': 'updated',
            },
        )

    @http.route('/module/ping', type='http', auth='none', methods=['GET'], csrf=False)
    def ping(self, **kwargs):
        """Expose the module identity without claiming a self-referential ZIP digest."""
        request_id = _new_request_id()
        runtime_odoo_major = int(odoo_release.version_info[0])
        response = Response(
            json.dumps({
                'build_id': BUILD_ID,
                'capabilities': list(MODULE_CAPABILITIES),
                'commit_sha': COMMIT_SHA,
                'module_installed': True,
                'module_version': MODULE_VERSION,
                'odoo_major': ODOO_MAJOR or runtime_odoo_major,
                'protocol_version': PROTOCOL_VERSION,
                'request_id': request_id,
                'source_tree': SOURCE_TREE,
                'success': True,
                'version': MODULE_VERSION,
            }, sort_keys=True, separators=(',', ':')),
            status=200,
            content_type='application/json',
        )
        response.headers[REQUEST_ID_HEADER] = request_id

        return response
