import logging
import traceback
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .catalog import channel_idempotency
from .shopify_api import ShopifyAPIError, payload_hash


_logger = logging.getLogger(__name__)


JOB_OPERATIONS = [
    ("fetch_locations", "读取店铺库位"),
    ("register_webhooks", "注册Webhook"),
    ("publish_product", "发布商品"),
    ("delete_media", "删除商品图片"),
    ("sync_collection", "同步分类集合"),
    ("sync_inventory", "同步库存"),
    ("import_orders", "读取订单"),
    ("import_order", "导入订单"),
    ("push_fulfillment", "回传履约"),
]


class ShopifyJob(models.Model):
    _name = "ll.shopify.job"
    _description = "Shopify 后台任务"
    _order = "priority, create_date, id"
    _rec_name = "display_name"

    display_name = fields.Char(compute="_compute_display_name", store=True)
    company_id = fields.Many2one(related="store_id.company_id", store=True, index=True)
    store_id = fields.Many2one("ll.shopify.store", required=True, ondelete="cascade", index=True)
    operation = fields.Selection(JOB_OPERATIONS, required=True, index=True)
    model_name = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    state = fields.Selection(
        [
            ("queued", "待执行"),
            ("running", "执行中"),
            ("retry", "等待重试"),
            ("done", "完成"),
            ("failed", "失败"),
            ("cancelled", "已取消"),
        ],
        default="queued",
        required=True,
        index=True,
    )
    priority = fields.Integer(default=10, index=True)
    idempotency_key = fields.Char(required=True, index=True)
    payload_json = fields.Json(default=dict)
    result_json = fields.Json(readonly=True)
    attempt_count = fields.Integer(default=0, readonly=True)
    max_attempts = fields.Integer(default=5)
    next_run_at = fields.Datetime(default=fields.Datetime.now, index=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)
    retryable = fields.Boolean(readonly=True)

    _sql_constraints = [
        (
            "job_idempotency_unique",
            "unique(idempotency_key)",
            "相同任务已经存在，不会重复创建。",
        )
    ]

    @api.depends("store_id", "operation", "res_id")
    def _compute_display_name(self):
        labels = dict(JOB_OPERATIONS)
        for job in self:
            job.display_name = f"{job.store_id.name or '-'} / {labels.get(job.operation, job.operation)} #{job.res_id}"

    @api.model
    def enqueue(self, store, operation, record, payload=None, *, priority=10, force=False):
        store.ensure_one()
        record.ensure_one()
        payload = payload or {}
        if operation in {"publish_product", "sync_inventory"} and record._name == "ll.shopify.channel.product":
            key = channel_idempotency(record, operation, payload)
        else:
            key = payload_hash(
                {
                    "store": store.id,
                    "operation": operation,
                    "record": f"{record._name}:{record.id}",
                    "payload": payload,
                }
            )
        existing = self.search([("idempotency_key", "=", key)], limit=1)
        if existing:
            if force and existing.state in {"failed", "cancelled"}:
                existing.write(
                    {
                        "state": "queued",
                        "next_run_at": fields.Datetime.now(),
                        "last_error": False,
                        "retryable": False,
                    }
                )
            return existing
        return self.create(
            {
                "store_id": store.id,
                "operation": operation,
                "model_name": record._name,
                "res_id": record.id,
                "payload_json": payload,
                "idempotency_key": key,
                "priority": priority,
            }
        )

    def action_retry(self):
        for job in self:
            if job.state not in {"failed", "cancelled", "retry"}:
                raise UserError(_("任务 %s 当前不能重试。") % job.display_name)
            job.write(
                {
                    "state": "queued",
                    "next_run_at": fields.Datetime.now(),
                    "last_error": False,
                    "retryable": False,
                }
            )

    def action_cancel(self):
        invalid = self.filtered(lambda job: job.state not in {"queued", "retry", "failed"})
        if invalid:
            raise UserError("只能取消待执行、待重试或失败的任务。")
        self.write({"state": "cancelled", "finished_at": fields.Datetime.now()})

    def action_open_record(self):
        self.ensure_one()
        record = self.env[self.model_name].browse(self.res_id).exists()
        if not record:
            raise UserError("关联记录已不存在。")
        return {
            "type": "ir.actions.act_window",
            "name": record.display_name,
            "res_model": record._name,
            "res_id": record.id,
            "views": [[False, "form"]],
            "target": "current",
        }

    @api.model
    def _cron_process_jobs(self, batch_size=20):
        jobs = self.search(
            [
                ("state", "in", ["queued", "retry"]),
                ("next_run_at", "<=", fields.Datetime.now()),
                ("store_id.state", "=", "connected"),
            ],
            order="priority, create_date, id",
            limit=batch_size,
        )
        for job in jobs:
            with self.env.cr.savepoint():
                job._execute_one()
        return len(jobs)

    def _execute_one(self):
        self.ensure_one()
        if self.state not in {"queued", "retry"}:
            return
        self.write(
            {
                "state": "running",
                "started_at": fields.Datetime.now(),
                "attempt_count": self.attempt_count + 1,
                "last_error": False,
            }
        )
        try:
            result = getattr(self, f"_run_{self.operation}")()
            self.write(
                {
                    "state": "done",
                    "finished_at": fields.Datetime.now(),
                    "result_json": result or {},
                    "retryable": False,
                }
            )
        except Exception as error:  # a task failure must not abort another store's task
            retryable = isinstance(error, ShopifyAPIError) and error.retryable
            attempts_left = self.attempt_count < self.max_attempts
            next_state = "retry" if retryable and attempts_left else "failed"
            delay_minutes = min(2 ** max(self.attempt_count - 1, 0), 60)
            message = str(error)[:4000]
            self.write(
                {
                    "state": next_state,
                    "next_run_at": fields.Datetime.now() + timedelta(minutes=delay_minutes),
                    "finished_at": fields.Datetime.now() if next_state == "failed" else False,
                    "last_error": message,
                    "retryable": retryable,
                    "result_json": {},
                }
            )
            self._mark_record_error(message)
            if (self.payload_json or {}).get("webhook_id"):
                self.env["ll.shopify.webhook.event"].search(
                    [
                        ("store_id", "=", self.store_id.id),
                        ("webhook_id", "=", self.payload_json["webhook_id"]),
                    ],
                    limit=1,
                ).write({"state": "error", "last_error": message})
            _logger.warning(
                "Shopify job failed store=%s operation=%s record=%s:%s retryable=%s\n%s",
                self.store_id.id,
                self.operation,
                self.model_name,
                self.res_id,
                retryable,
                traceback.format_exc(limit=5),
            )

    def _record(self):
        return self.env[self.model_name].browse(self.res_id).exists()

    def _mark_record_error(self, message):
        record = self._record()
        if not record:
            return
        values = {}
        if "last_error" in record._fields:
            values["last_error"] = message
        if "sync_state" in record._fields:
            values["sync_state"] = "error"
        if values:
            record.write(values)

    @staticmethod
    def _raise_user_errors(container):
        errors = (container or {}).get("userErrors") or []
        if errors:
            messages = [error.get("message") or "Shopify 校验失败" for error in errors]
            raise ShopifyAPIError("；".join(messages))

    def _run_fetch_locations(self):
        data = self.store_id._graphql("query { locations(first: 100) { nodes { id name isActive } } }")
        nodes = (data.get("locations") or {}).get("nodes") or []
        maps = self.env["ll.shopify.location.map"]
        created = 0
        for node in nodes:
            if not node.get("isActive") or maps.search_count(
                [("store_id", "=", self.store_id.id), ("shopify_location_gid", "=", node["id"])]
            ):
                continue
            location = self.env["stock.location"].search(
                [
                    ("id", "child_of", self.store_id.warehouse_id.view_location_id.id),
                    ("usage", "=", "internal"),
                    ("name", "=", node["name"]),
                ],
                limit=1,
            )
            if not location and not maps.search_count([("store_id", "=", self.store_id.id)]):
                location = self.store_id.warehouse_id.lot_stock_id
            if location:
                maps.create(
                    {
                        "name": node["name"],
                        "store_id": self.store_id.id,
                        "location_id": location.id,
                        "shopify_location_gid": node["id"],
                    }
                )
                created += 1
        return {"locations_seen": len(nodes), "mappings_created": created}

    def _run_register_webhooks(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url").rstrip("/")
        callback = f"{base_url}/lightlink/shopify/webhook/{self.store_id.webhook_secret}"
        mutation = """
            mutation CreateWebhook($topic: WebhookSubscriptionTopic!, $subscription: WebhookSubscriptionInput!) {
              webhookSubscriptionCreate(topic: $topic, webhookSubscription: $subscription) {
                webhookSubscription { id topic uri }
                userErrors { field message }
              }
            }
        """
        created = []
        for topic in ["APP_UNINSTALLED", "ORDERS_CREATE", "ORDERS_UPDATED"]:
            data = self.store_id._graphql(
                mutation,
                {"topic": topic, "subscription": {"callbackUrl": callback, "format": "JSON"}},
            )
            container = data.get("webhookSubscriptionCreate") or {}
            self._raise_user_errors(container)
            created.append((container.get("webhookSubscription") or {}).get("id"))
        return {"subscriptions": [item for item in created if item]}

    def _run_publish_product(self):
        channel = self._record()
        if not channel:
            raise UserError("渠道商品已不存在。")
        payload = channel._build_product_payload()
        mutation = """
            mutation SetProduct($input: ProductSetInput!, $synchronous: Boolean!, $identifier: ProductSetIdentifiers) {
              productSet(input: $input, synchronous: $synchronous, identifier: $identifier) {
                product { id handle variants(first: 250) { nodes { id sku inventoryItem { id } } } }
                userErrors { field message code }
              }
            }
        """
        data = self.store_id._graphql(mutation, payload)
        container = data.get("productSet") or {}
        self._raise_user_errors(container)
        product = container.get("product") or {}
        if not product.get("id"):
            raise ShopifyAPIError("Shopify 没有返回已发布商品。", retryable=True)
        by_sku = {
            (node.get("sku") or ""): node
            for node in ((product.get("variants") or {}).get("nodes") or [])
        }
        for binding in channel.variant_ids:
            node = by_sku.get(binding.sku or "")
            if node:
                binding.write(
                    {
                        "shopify_variant_gid": node.get("id"),
                        "shopify_inventory_item_gid": (node.get("inventoryItem") or {}).get("id"),
                    }
                )
        channel.write(
            {
                "shopify_product_gid": product["id"],
                "shopify_handle": product.get("handle"),
                "last_payload_hash": payload_hash(payload),
                "last_synced_at": fields.Datetime.now(),
                "last_error": False,
                "sync_state": "archived" if channel.shopify_status == "ARCHIVED" else "synced",
            }
        )
        self._sync_product_media(channel)
        self.store_id.last_product_sync_at = fields.Datetime.now()
        if self.store_id.sync_inventory:
            self.enqueue(
                self.store_id,
                "sync_inventory",
                channel,
                payload=channel._inventory_marker(),
                force=True,
            )
        return {"shopify_product_gid": product["id"], "handle": product.get("handle")}

    def _sync_product_media(self, channel):
        pending = channel.image_ids.filtered(lambda image: not image.shopify_media_gid)
        if pending:
            media = [
                {
                    "mediaContentType": "IMAGE",
                    "originalSource": image.public_url(),
                    "alt": image.alt_text or channel.title,
                }
                for image in pending
            ]
            mutation = """
                mutation UpdateProductMedia($product: ProductUpdateInput!, $media: [CreateMediaInput!]) {
                  productUpdate(product: $product, media: $media) {
                    product { id media(first: 100) { nodes { id alt status } } }
                    userErrors { field message }
                  }
                }
            """
            data = self.store_id._graphql(
                mutation, {"product": {"id": channel.shopify_product_gid}, "media": media}
            )
            container = data.get("productUpdate") or {}
            self._raise_user_errors(container)
            nodes = ((container.get("product") or {}).get("media") or {}).get("nodes") or []
            unbound = [node for node in nodes if node.get("id")]
            for image, node in zip(pending, unbound[-len(pending) :]):
                image.write({"shopify_media_gid": node["id"], "media_status": "ready", "last_error": False})
        existing = channel.image_ids.filtered("shopify_media_gid").sorted("sequence")
        if existing:
            update_mutation = """
                mutation UpdateMedia($productId: ID!, $media: [UpdateMediaInput!]!) {
                  productUpdateMedia(productId: $productId, media: $media) {
                    mediaUserErrors { field message }
                  }
                }
            """
            response = self.store_id._graphql(
                update_mutation,
                {
                    "productId": channel.shopify_product_gid,
                    "media": [
                        {"id": image.shopify_media_gid, "alt": image.alt_text or channel.title}
                        for image in existing
                    ],
                },
            )
            errors = (response.get("productUpdateMedia") or {}).get("mediaUserErrors") or []
            if errors:
                raise ShopifyAPIError("；".join(error.get("message") or "图片更新失败" for error in errors))
            reorder_mutation = """
                mutation ReorderMedia($id: ID!, $moves: [MoveInput!]!) {
                  productReorderMedia(id: $id, moves: $moves) {
                    job { id }
                    mediaUserErrors { field message }
                  }
                }
            """
            response = self.store_id._graphql(
                reorder_mutation,
                {
                    "id": channel.shopify_product_gid,
                    "moves": [
                        {"id": image.shopify_media_gid, "newPosition": str(position)}
                        for position, image in enumerate(existing)
                    ],
                },
            )
            errors = (response.get("productReorderMedia") or {}).get("mediaUserErrors") or []
            if errors:
                raise ShopifyAPIError("；".join(error.get("message") or "图片排序失败" for error in errors))

    def _run_delete_media(self):
        payload = self.payload_json or {}
        product_id = payload.get("product_id")
        media_ids = payload.get("media_ids") or []
        if not product_id or not media_ids:
            return {"deleted": 0}
        mutation = """
            mutation DeleteMedia($productId: ID!, $mediaIds: [ID!]!) {
              productDeleteMedia(productId: $productId, mediaIds: $mediaIds) {
                deletedMediaIds
                mediaUserErrors { field message }
              }
            }
        """
        response = self.store_id._graphql(
            mutation, {"productId": product_id, "mediaIds": media_ids}
        )
        container = response.get("productDeleteMedia") or {}
        errors = container.get("mediaUserErrors") or []
        if errors:
            raise ShopifyAPIError("；".join(error.get("message") or "图片删除失败" for error in errors))
        return {"deleted": len(container.get("deletedMediaIds") or [])}

    def _run_sync_collection(self):
        collection = self._record()
        if not collection:
            raise UserError("分类集合已不存在。")
        values = collection._build_collection_payload()["input"]
        if collection.shopify_collection_gid:
            mutation = """
                mutation UpdateCollection($input: CollectionInput!) {
                  collectionUpdate(input: $input) {
                    collection { id handle }
                    userErrors { field message }
                  }
                }
            """
            key = "collectionUpdate"
        else:
            mutation = """
                mutation CreateCollection($input: CollectionInput!) {
                  collectionCreate(input: $input) {
                    collection { id handle }
                    userErrors { field message }
                  }
                }
            """
            key = "collectionCreate"
        data = self.store_id._graphql(mutation, {"input": values})
        container = data.get(key) or {}
        self._raise_user_errors(container)
        remote = container.get("collection") or {}
        collection.write(
            {
                "shopify_collection_gid": remote.get("id"),
                "handle": remote.get("handle") or collection.handle,
                "sync_state": "synced",
                "last_synced_at": fields.Datetime.now(),
                "last_error": False,
            }
        )
        return {"shopify_collection_gid": remote.get("id")}

    def _run_sync_inventory(self):
        channel = self._record()
        if not channel:
            raise UserError("渠道商品已不存在。")
        mappings = self.env["ll.shopify.location.map"].search(
            [("store_id", "=", self.store_id.id), ("active", "=", True)]
        )
        if not mappings:
            raise UserError("请先配置 Shopify Location 与 Odoo 库位映射。")
        mutation = """
            mutation SetInventory($input: InventorySetQuantitiesInput!, $idempotencyKey: String!) {
              inventorySetQuantities(input: $input) @idempotent(key: $idempotencyKey) {
                inventoryAdjustmentGroup { createdAt reason referenceDocumentUri }
                userErrors { field message code }
              }
            }
        """
        changed = 0
        for binding in channel.variant_ids:
            if not binding.shopify_inventory_item_gid:
                continue
            quantities = [
                {
                    "inventoryItemId": binding.shopify_inventory_item_gid,
                    "locationId": mapping.shopify_location_gid,
                    "quantity": mapping.available_quantity(binding.product_id),
                }
                for mapping in mappings
            ]
            input_values = {
                "name": "available",
                "reason": "correction",
                "ignoreCompareQuantity": True,
                "referenceDocumentUri": f"odoo://ll.shopify.channel.product/{channel.id}",
                "quantities": quantities,
            }
            data = self.store_id._graphql(
                mutation,
                {"input": input_values, "idempotencyKey": payload_hash(input_values)},
            )
            self._raise_user_errors(data.get("inventorySetQuantities") or {})
            changed += len(quantities)
        self.store_id.last_inventory_sync_at = fields.Datetime.now()
        return {"quantities_updated": changed}

    def _run_import_orders(self):
        query_filter = ""
        if self.store_id.last_order_sync_at:
            query_filter = "updated_at:>=" + fields.Datetime.to_string(
                self.store_id.last_order_sync_at - timedelta(minutes=5)
            ).replace(" ", "T") + "Z"
        query = """
            query Orders($query: String, $cursor: String) {
              orders(first: 100, after: $cursor, sortKey: UPDATED_AT, query: $query) {
                nodes {
                  id name createdAt updatedAt displayFinancialStatus displayFulfillmentStatus
                  email phone note tags
                  customer { id email phone firstName lastName }
                  shippingAddress { firstName lastName company address1 address2 city province zip country countryCodeV2 phone }
                  lineItems(first: 250) {
                    nodes { id name sku quantity currentQuantity variant { id } originalUnitPriceSet { shopMoney { amount currencyCode } } }
                    pageInfo { hasNextPage endCursor }
                  }
                  shippingLines(first: 250) {
                    nodes { title originalPriceSet { shopMoney { amount currencyCode } } }
                    pageInfo { hasNextPage endCursor }
                  }
                }
                pageInfo { hasNextPage endCursor }
              }
            }
        """
        cursor = None
        seen = 0
        while True:
            data = self.store_id._graphql(
                query, {"query": query_filter or None, "cursor": cursor}
            )
            connection = data.get("orders") or {}
            nodes = connection.get("nodes") or []
            for order in nodes:
                self._complete_order_connections(order)
                self.env["ll.shopify.order.binding"]._import_shopify_order(self.store_id, order)
            seen += len(nodes)
            page_info = connection.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor:
                raise ShopifyAPIError("Shopify 订单分页缺少游标。", retryable=True)
        self.store_id.last_order_sync_at = fields.Datetime.now()
        if (self.payload_json or {}).get("webhook_id"):
            self.env["ll.shopify.webhook.event"].search(
                [
                    ("store_id", "=", self.store_id.id),
                    ("webhook_id", "=", self.payload_json["webhook_id"]),
                ],
                limit=1,
            ).write({"state": "done", "last_error": False})
        return {"orders_seen": seen}

    def _complete_order_connections(self, order):
        """Load all nested order rows instead of silently truncating at Shopify's page limit."""
        queries = {
            "lineItems": """
                query OrderLineItems($id: ID!, $cursor: String) {
                  order(id: $id) {
                    lineItems(first: 250, after: $cursor) {
                      nodes { id name sku quantity currentQuantity variant { id } originalUnitPriceSet { shopMoney { amount currencyCode } } }
                      pageInfo { hasNextPage endCursor }
                    }
                  }
                }
            """,
            "shippingLines": """
                query OrderShippingLines($id: ID!, $cursor: String) {
                  order(id: $id) {
                    shippingLines(first: 250, after: $cursor) {
                      nodes { title originalPriceSet { shopMoney { amount currencyCode } } }
                      pageInfo { hasNextPage endCursor }
                    }
                  }
                }
            """,
        }
        for field_name, query in queries.items():
            connection = order.get(field_name) or {"nodes": []}
            page_info = connection.get("pageInfo") or {}
            while page_info.get("hasNextPage"):
                cursor = page_info.get("endCursor")
                if not cursor:
                    raise ShopifyAPIError(
                        f"Shopify 订单 {order.get('name') or order.get('id')} 的 {field_name} 分页缺少游标。",
                        retryable=True,
                    )
                data = self.store_id._graphql(
                    query, {"id": order.get("id"), "cursor": cursor}
                )
                page = ((data.get("order") or {}).get(field_name) or {})
                connection.setdefault("nodes", []).extend(page.get("nodes") or [])
                page_info = page.get("pageInfo") or {}
            order[field_name] = connection

    def _run_import_order(self):
        payload = self.payload_json or {}
        remote = payload.get("order") or payload
        binding = self.env["ll.shopify.order.binding"]._import_shopify_order(
            self.store_id, remote
        )
        return {"binding_id": binding.id, "sale_order_id": binding.sale_order_id.id}

    def _run_push_fulfillment(self):
        picking = self._record()
        if not picking:
            raise UserError("库存调拨已不存在。")
        return picking._shopify_push_fulfillment(self.store_id)
