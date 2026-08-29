# -*- coding: utf-8 -*-
"""Signing and validation primitives for OdooTranslate module API v2."""

import hashlib
import hmac
import json
import secrets
import time
import unicodedata
import uuid

from .release_metadata import PROTOCOL_VERSION


NONCE_HEADER = 'X-OdooTranslate-Nonce'
MODULE_CAPABILITIES = ('native_text_atomic_write_v1',)
NATIVE_TEXT_CONTRACT = 'native_text@1'
NATIVE_TEXT_SOURCE_HASH_ALGORITHM = 'native_text_source_sha256_crlf_nfc_v1'
PROTOCOL = 'odootranslate-module:v%s' % PROTOCOL_VERSION.split('.')[0]
SIGNATURE_HEADER = 'X-OdooTranslate-Signature'
TIMESTAMP_HEADER = 'X-OdooTranslate-Timestamp'
TIMESTAMP_TOLERANCE = 300


def canonicalize_native_text(value):
    """Match Laravel's versioned CRLF-to-LF and NFC source contract."""
    if not isinstance(value, str):
        raise ValueError('native text values must be strings')

    canonical = value.replace('\r\n', '\n').replace('\r', '\n')
    return unicodedata.normalize('NFC', canonical)


def native_text_value_hash(value):
    """Hash one native text value without trimming significant whitespace."""
    canonical = canonicalize_native_text(value)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def native_text_request_hash(payload):
    """Bind a native-text operation to its complete non-plaintext identity."""
    canonical = '\n'.join([
        NATIVE_TEXT_CONTRACT,
        NATIVE_TEXT_SOURCE_HASH_ALGORITHM,
        str(payload.get('module_uuid', '')),
        str(payload.get('link_attempt_id', '')),
        str(payload.get('operation_id', '')),
        str(payload.get('model_name', '')),
        str(payload.get('record_id', '')),
        str(payload.get('field_name', '')),
        str(payload.get('source_lang', '')),
        str(payload.get('target_lang', '')),
        str(payload.get('expected_source_hash', '')),
        str(payload.get('translation_hash', '')),
    ])
    return hashlib.sha256(canonical.encode('ascii')).hexdigest()


def sign_native_text_operation(operation, request_hash, shared_secret):
    """Sign an apply or reconcile command for the active link generation."""
    if operation not in ('apply', 'reconcile'):
        raise ValueError('unsupported native text operation')
    if not isinstance(request_hash, str) or len(request_hash) != 64:
        raise ValueError('request_hash must be a SHA-256 digest')

    canonical = '\n'.join([
        PROTOCOL,
        'native_text_%s:v1' % operation,
        request_hash,
    ])
    return hmac.new(
        shared_secret.encode('ascii'),
        canonical.encode('ascii'),
        hashlib.sha256,
    ).hexdigest()


def verify_native_text_operation_signature(
    operation,
    request_hash,
    shared_secret,
    signature,
):
    """Verify a generation-scoped native text command signature."""
    if not isinstance(signature, str) or not signature.startswith('v1='):
        return False

    raw_signature = signature[3:]
    if (
        len(raw_signature) != 64
        or any(character not in '0123456789abcdef' for character in raw_signature)
    ):
        return False

    try:
        expected = sign_native_text_operation(
            operation,
            request_hash,
            shared_secret,
        )
    except (AttributeError, UnicodeEncodeError, ValueError):
        return False

    return hmac.compare_digest(expected, raw_signature)


def canonical_request(method, path, timestamp, nonce, body):
    """Return the byte-exact canonical request shared with the Laravel app."""
    body_hash = hashlib.sha256(body).hexdigest()
    return '\n'.join([
        PROTOCOL,
        method.upper(),
        path,
        str(timestamp),
        nonce,
        body_hash,
    ])


def sign_request(method, path, timestamp, nonce, body, shared_secret):
    """Return the lowercase HMAC-SHA256 signature for a request."""
    canonical = canonical_request(method, path, timestamp, nonce, body)
    return hmac.new(
        shared_secret.encode('ascii'),
        canonical.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def json_body(payload):
    """Serialize a module API payload to the byte-exact canonical JSON form."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')


def build_signed_request(
    module_uuid,
    shared_secret,
    path,
    payload=None,
    timestamp=None,
    nonce=None,
):
    """Build the exact body and headers that must be sent through requests."""
    if not module_uuid or not shared_secret:
        raise ValueError('module_uuid and shared_secret are required')

    request_timestamp = str(int(time.time()) if timestamp is None else timestamp)
    request_nonce = nonce or secrets.token_hex(16)
    request_payload = dict(payload or {'uuid': str(module_uuid).lower()})
    request_payload['uuid'] = str(module_uuid).lower()
    body = json_body(request_payload)
    signature = sign_request(
        'POST',
        path,
        request_timestamp,
        request_nonce,
        body,
        shared_secret,
    )

    return body, {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        NONCE_HEADER: request_nonce,
        SIGNATURE_HEADER: 'v1=%s' % signature,
        TIMESTAMP_HEADER: request_timestamp,
    }


def verify_signed_request(
    method,
    path,
    timestamp,
    nonce,
    body,
    shared_secret,
    signature,
    now=None,
):
    """Verify the complete canonical envelope of an inbound request."""
    if not shared_secret:
        return False

    if not isinstance(timestamp, str) or not timestamp.isdigit():
        return False

    if len(timestamp) not in (10, 11):
        return False

    if not isinstance(nonce, str) or len(nonce) != 32:
        return False

    if any(character not in '0123456789abcdef' for character in nonce):
        return False

    if not isinstance(signature, str) or not signature.startswith('v1='):
        return False

    raw_signature = signature[3:]
    if len(raw_signature) != 64:
        return False

    if any(character not in '0123456789abcdef' for character in raw_signature):
        return False

    current_timestamp = int(time.time()) if now is None else int(now)
    if abs(current_timestamp - int(timestamp)) > TIMESTAMP_TOLERANCE:
        return False

    expected_signature = sign_request(
        method,
        path,
        timestamp,
        nonce,
        body,
        shared_secret,
    )
    return hmac.compare_digest(expected_signature, raw_signature)


def legacy_unlink_operation_id(module_uuid, shared_secret):
    """Derive a stable unlink UUID for link generations created before v1.13."""
    if not module_uuid or not shared_secret:
        raise ValueError('module_uuid and shared_secret are required')

    message = '\n'.join([
        'odootranslate-module:legacy-unlink:v1',
        str(module_uuid).lower(),
    ])
    digest = bytearray(hmac.new(
        shared_secret.encode('ascii'),
        message.encode('utf-8'),
        hashlib.sha256,
    ).digest()[:16])
    digest[6] = (digest[6] & 0x0f) | 0x50
    digest[8] = (digest[8] & 0x3f) | 0x80

    return str(uuid.UUID(bytes=bytes(digest)))
