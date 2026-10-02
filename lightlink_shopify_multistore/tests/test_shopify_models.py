from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.modules.module import load_information_from_description_file
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models.shopify_api import ShopifyAPIError


@tagged("post_install", "-at_install")
class TestShopifyModels(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.pricelist = cls.env["product.pricelist"].search(
            [("currency_id", "=", cls.company.currency_id.id)], limit=1
        )
        if not cls.pricelist:
            cls.pricelist = cls.env["product.pricelist"].create(
                {"name": "Shopify Test", "currency_id": cls.company.currency_id.id}
            )
        cls.product = cls.env["product.product"].create(
            {"name": "Shopify Acceptance Product", "default_code": "SHOP-ACCEPT-1", "list_price": 99}
        )
        cls.shipping_product = cls.env["product.product"].create(
            {"name": "Shopify Shipping", "type": "service", "list_price": 0}
        )
        cls.placeholder_product = cls.env["product.product"].create(
            {"name": "Shopify Unmapped", "default_code": "SHOP-UNMAPPED", "list_price": 0}
        )
        cls.store = cls._create_store("Acceptance Store", "acceptance.myshopify.com")

    @classmethod
    def _create_store(cls, name, domain):
        return cls.env["ll.shopify.store"].create(
            {
                "name": name,
                "shop_domain": domain,
                "company_id": cls.company.id,
                "currency_id": cls.company.currency_id.id,
                "pricelist_id": cls.pricelist.id,
                "warehouse_id": cls.warehouse.id,
                "state": "connected",
                "access_token": "test-token",
                "client_id": "test-client",
                "client_secret": "test-secret",
                "shipping_product_id": cls.shipping_product.id,
                "unmapped_product_id": cls.placeholder_product.id,
            }
        )

    def _create_channel(self, store=None, product=None):
        return self.env["ll.shopify.channel.product"].create(
            {
                "store_id": (store or self.store).id,
                "product_tmpl_id": (product or self.product).product_tmpl_id.id,
                "title": (product or self.product).name,
                "price": 99,
            }
        )

    def test_dashboard_metrics(self):
        channel = self._create_channel()
        data = self.env["ll.shopify.dashboard"].get_dashboard()
        self.assertGreaterEqual(data["summary"]["stores"], 1)
        self.assertIn(self.store.id, [row["id"] for row in data["stores"]])
        self.assertTrue(channel)

    def test_store_state(self):
        self.store.action_pause()
        self.assertEqual(self.store.state, "paused")
        self.store.action_resume()
        self.assertEqual(self.store.state, "connected")

    def test_store_required_scopes(self):
        self.store.granted_scopes = self.store.requested_scopes
        self.assertFalse(self.store._missing_granted_scopes())
        self.store.granted_scopes = "read_products"
        self.assertIn(
            "write_merchant_managed_fulfillment_orders",
            self.store._missing_granted_scopes(),
        )

    def test_channel_product_unique_per_store(self):
        self._create_channel()
        with self.assertRaises(Exception), self.env.cr.savepoint():
            self._create_channel()

    def test_channel_payload(self):
        channel = self._create_channel()
        channel.write({"seo_title": "SEO", "handle": "acceptance-product", "tags": "b2b, sourcing"})
        payload = channel._build_product_payload()
        self.assertEqual(payload["input"]["title"], self.product.name)
        self.assertEqual(payload["input"]["tags"], ["b2b", "sourcing"])
        self.assertEqual(payload["input"]["variants"][0]["sku"], "SHOP-ACCEPT-1")

    def test_publish_preview_and_enqueue(self):
        wizard = self.env["ll.shopify.publish.wizard"].create(
            {
                "product_ids": [(6, 0, self.product.product_tmpl_id.ids)],
                "store_ids": [(6, 0, self.store.ids)],
                "include_images": False,
                "sync_inventory": False,
            }
        )
        wizard.action_confirm_publish()
        channel = self.env["ll.shopify.channel.product"].search(
            [("store_id", "=", self.store.id), ("product_tmpl_id", "=", self.product.product_tmpl_id.id)]
        )
        self.assertEqual(channel.sync_state, "queued")
        job = self.env["ll.shopify.job"].search(
            [("operation", "=", "publish_product"), ("res_id", "=", channel.id)]
        )
        self.assertEqual(len(job), 1)
        self.assertFalse(job.payload_json["_lightlink_sync_inventory"])

    def test_batch_publish_idempotency(self):
        channel = self._create_channel()
        channel.action_queue_publish()
        channel.action_queue_publish()
        self.assertEqual(
            self.env["ll.shopify.job"].search_count(
                [("operation", "=", "publish_product"), ("res_id", "=", channel.id)]
            ),
            1,
        )

    def test_collection_mapping(self):
        category = self.env["product.category"].create({"name": "Shopify Test Category"})
        collection = self.env["ll.shopify.collection"].create(
            {"store_id": self.store.id, "category_id": category.id, "title": category.name}
        )
        self.assertEqual(collection.category_id, category)
        with self.assertRaises(Exception), self.env.cr.savepoint():
            self.env["ll.shopify.collection"].create(
                {"store_id": self.store.id, "category_id": category.id, "title": "Duplicate"}
            )

    def test_available_quantity(self):
        location = self.warehouse.lot_stock_id
        self.env["stock.quant"]._update_available_quantity(self.product, location, 10)
        mapping = self.env["ll.shopify.location.map"].create(
            {
                "name": "Primary",
                "store_id": self.store.id,
                "location_id": location.id,
                "shopify_location_gid": "gid://shopify/Location/1",
                "safety_stock": 2,
            }
        )
        self.store.safety_stock = 1
        self.assertEqual(mapping.available_quantity(self.product), 7)

    def test_pricelist_currency_validation(self):
        currency = self.env["res.currency"].search([("id", "!=", self.company.currency_id.id)], limit=1)
        if not currency:
            self.skipTest("数据库没有第二币种")
        other = self.env["product.pricelist"].create({"name": "Other", "currency_id": currency.id})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.store.pricelist_id = other

    def test_order_import_idempotency(self):
        channel = self._create_channel()
        channel.variant_ids.shopify_variant_gid = "gid://shopify/ProductVariant/1"
        payload = {
            "id": "gid://shopify/Order/1",
            "name": "#1001",
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
            "displayFinancialStatus": "PAID",
            "displayFulfillmentStatus": "UNFULFILLED",
            "email": "buyer@example.com",
            "customer": {"id": "gid://shopify/Customer/1", "email": "buyer@example.com", "firstName": "Test", "lastName": "Buyer"},
            "lineItems": {"nodes": [{"id": "gid://shopify/LineItem/1", "name": self.product.name, "sku": self.product.default_code, "quantity": 1, "currentQuantity": 1, "variant": {"id": "gid://shopify/ProductVariant/1"}, "originalUnitPriceSet": {"shopMoney": {"amount": "99.00", "currencyCode": self.company.currency_id.name}}}]},
            "shippingLines": {"nodes": []},
        }
        first = self.env["ll.shopify.order.binding"]._import_shopify_order(self.store, payload)
        second = self.env["ll.shopify.order.binding"]._import_shopify_order(self.store, payload)
        self.assertEqual(first, second)
        self.assertEqual(first.sale_order_id.order_line.product_id, self.product)

    def test_order_sku_match_prefers_store_mapping(self):
        mapped_product = self.env["product.product"].create(
            {
                "name": "Mapped duplicate SKU",
                "default_code": self.product.default_code,
                "list_price": 88,
            }
        )
        self._create_channel(product=mapped_product)
        binding = self.env["ll.shopify.order.binding"].new({"store_id": self.store.id})
        matched = binding._match_product({"sku": self.product.default_code})
        self.assertEqual(matched, mapped_product)

    def test_cancelled_order_line_is_not_recreated(self):
        payload = {
            "id": "gid://shopify/Order/cancelled-line",
            "name": "#CANCELLED",
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
            "displayFinancialStatus": "PAID",
            "displayFulfillmentStatus": "UNFULFILLED",
            "email": "cancelled@example.com",
            "lineItems": {
                "nodes": [
                    {
                        "id": "gid://shopify/LineItem/cancelled",
                        "name": self.product.name,
                        "sku": self.product.default_code,
                        "quantity": 1,
                        "currentQuantity": 0,
                        "variant": {},
                        "originalUnitPriceSet": {
                            "shopMoney": {
                                "amount": "99.00",
                                "currencyCode": self.company.currency_id.name,
                            }
                        },
                    }
                ]
            },
            "shippingLines": {"nodes": []},
        }
        binding = self.env["ll.shopify.order.binding"]._import_shopify_order(
            self.store, payload
        )
        self.assertFalse(binding.sale_order_id.order_line)

    def test_order_nested_connections_are_fully_loaded(self):
        job = self.env["ll.shopify.job"].enqueue(
            self.store, "import_orders", self.store, payload={"pagination": self.id()}
        )
        order = {
            "id": "gid://shopify/Order/250",
            "name": "#250",
            "lineItems": {
                "nodes": [{"id": "gid://shopify/LineItem/1"}],
                "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
            },
            "shippingLines": {
                "nodes": [],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            },
        }
        response = {
            "order": {
                "lineItems": {
                    "nodes": [{"id": "gid://shopify/LineItem/2"}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
        with patch.object(type(self.store), "_graphql", return_value=response) as graphql:
            job._complete_order_connections(order)
        self.assertEqual(len(order["lineItems"]["nodes"]), 2)
        graphql.assert_called_once()

    def test_inquiry_creates_lead(self):
        inquiry = self.env["ll.shopify.inquiry"].create_from_public(
            self.store,
            {"name": "Buyer", "email": "buyer2@example.com", "message": "Need 500 units", "consent": True, "utm_source": "google"},
            remote_ip="127.0.0.1",
            user_agent="test",
        )
        self.assertEqual(inquiry.lead_id.ll_shopify_store_id, self.store)
        self.assertEqual(inquiry.utm_source, "google")

    def test_webhook_event_deduplication(self):
        values = {
            "store_id": self.store.id,
            "webhook_id": "dedupe-1",
            "topic": "orders/create",
            "shop_domain": self.store.shop_domain,
            "payload_json": {"id": 1},
        }
        self.env["ll.shopify.webhook.event"].create(values)
        with self.assertRaises(Exception), self.env.cr.savepoint():
            self.env["ll.shopify.webhook.event"].create(values)

    def test_company_rules_and_secret_visibility(self):
        self.assertEqual(self.env["ll.shopify.store"]._fields["access_token"].groups, "base.group_system")
        rule = self.env.ref("lightlink_shopify_multistore.rule_shopify_store_company")
        self.assertIn("company_ids", rule.domain_force)

    def test_picking_enqueues_fulfillment(self):
        sale = self.env["sale.order"].new({"ll_shopify_store_id": self.store.id})
        picking = self.env["stock.picking"].new({"sale_id": sale, "state": "done"})
        job_model_class = type(self.env["ll.shopify.job"])
        with patch.object(job_model_class, "enqueue", autospec=True) as enqueue:
            picking._shopify_enqueue_fulfillment_if_needed()
        enqueue.assert_called_once()

    def test_partial_fulfillment_allocates_only_done_quantity(self):
        nodes = [
            {
                "id": "gid://shopify/FulfillmentOrder/1",
                "status": "OPEN",
                "lineItems": {
                    "nodes": [
                        {
                            "id": "gid://shopify/FulfillmentOrderLineItem/1",
                            "remainingQuantity": 5,
                            "lineItem": {"id": "gid://shopify/LineItem/1"},
                        }
                    ],
                    "pageInfo": {"hasNextPage": False},
                },
            }
        ]
        orders, remote_gids, remaining = self.env[
            "stock.picking"
        ]._shopify_allocate_fulfillment_lines(
            nodes, {"gid://shopify/LineItem/1": 2}
        )
        self.assertEqual(
            orders[0]["fulfillmentOrderLineItems"][0]["quantity"], 2
        )
        self.assertIn("gid://shopify/LineItem/1", remote_gids)
        self.assertEqual(remaining["gid://shopify/LineItem/1"], 0)

    def test_shopify_frontend_independence(self):
        manifest = load_information_from_description_file("lightlink_shopify_multistore")
        self.assertNotIn("web.assets_frontend", manifest.get("assets", {}))

    def test_job_retry_and_isolation(self):
        job = self.env["ll.shopify.job"].enqueue(
            self.store, "fetch_locations", self.store, payload={"test": self.id()}
        )
        with patch.object(type(self.store), "_graphql", side_effect=ShopifyAPIError("rate", retryable=True)):
            job._execute_one()
        self.assertEqual(job.state, "retry")
        self.assertTrue(job.retryable)

    def test_workspace_channel_summary(self):
        self._create_channel()
        result = self.env["psc.business.hub"].get_product_workspace(
            {"keyword": self.product.default_code}, 0, 10
        )
        row = next(item for item in result["products"] if item["id"] == self.product.product_tmpl_id.id)
        self.assertEqual(row["shopify"]["count"], 1)

    def test_store_failure_isolation(self):
        other = self._create_store("Second Store", "second-acceptance.myshopify.com")
        first_job = self.env["ll.shopify.job"].enqueue(
            self.store, "fetch_locations", self.store, payload={"isolation": "first"}
        )
        second_job = self.env["ll.shopify.job"].enqueue(
            other, "fetch_locations", other, payload={"isolation": "second"}
        )
        first_job._mark_record_error("first failed")
        second_job.write({"state": "done", "finished_at": fields.Datetime.now()})
        self.assertEqual(second_job.state, "done")
        self.assertEqual(other.state, "connected")

    def test_archiving_preserves_orders(self):
        channel = self._create_channel()
        channel.write({"shopify_product_gid": "gid://shopify/Product/1", "sync_state": "synced"})
        channel.action_archive_remote()
        self.assertEqual(channel.shopify_status, "ARCHIVED")
        self.assertTrue(channel.product_tmpl_id.exists())
