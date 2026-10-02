import base64
import hashlib
import hmac

from odoo.tests.common import TransactionCase

from ..models.shopify_api import (
    canonical_json,
    normalize_shop_domain,
    payload_hash,
    verify_oauth_hmac,
    verify_webhook_hmac,
)


class TestShopifyAPIHelpers(TransactionCase):
    def test_store_constraints(self):
        self.assertEqual(normalize_shop_domain("Demo-Store"), "demo-store.myshopify.com")
        self.assertEqual(
            normalize_shop_domain("https://demo-store.myshopify.com/admin"),
            "demo-store.myshopify.com",
        )
        with self.assertRaises(ValueError):
            normalize_shop_domain("example.com")

    def test_oauth_hmac(self):
        params = {"shop": "demo.myshopify.com", "code": "abc", "timestamp": "1"}
        message = b"code=abc&shop=demo.myshopify.com&timestamp=1"
        params["hmac"] = hmac.new(b"secret", message, hashlib.sha256).hexdigest()
        self.assertTrue(verify_oauth_hmac("secret", params))
        params["code"] = "tampered"
        self.assertFalse(verify_oauth_hmac("secret", params))

    def test_webhook_hmac_and_deduplication(self):
        body = b'{"id": 42}'
        signature = base64.b64encode(hmac.new(b"secret", body, hashlib.sha256).digest()).decode()
        self.assertTrue(verify_webhook_hmac("secret", body, signature))
        self.assertFalse(verify_webhook_hmac("secret", body + b"x", signature))

    def test_canonical_payload_hash(self):
        self.assertEqual(canonical_json({"b": 2, "a": 1}), '{"a":1,"b":2}')
        self.assertEqual(payload_hash({"a": 1}), payload_hash({"a": 1}))
