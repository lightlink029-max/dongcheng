import base64
import hashlib
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .shopify_api import payload_hash


CHANNEL_STATES = [
    ("draft", "草稿"),
    ("queued", "待处理"),
    ("synced", "已同步"),
    ("warning", "需检查"),
    ("error", "失败"),
    ("archived", "已归档"),
]


class ShopifyChannelProduct(models.Model):
    _name = "ll.shopify.channel.product"
    _description = "Shopify 渠道商品"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "store_id, product_tmpl_id"

    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(related="store_id.company_id", store=True, index=True)
    store_id = fields.Many2one(
        "ll.shopify.store", required=True, ondelete="restrict", index=True, tracking=True
    )
    product_tmpl_id = fields.Many2one(
        "product.template", required=True, ondelete="restrict", index=True, tracking=True
    )
    title = fields.Char(required=True, translate=True, tracking=True)
    description_html = fields.Html(translate=True, sanitize=True)
    handle = fields.Char(tracking=True)
    seo_title = fields.Char(translate=True)
    seo_description = fields.Text(translate=True)
    vendor = fields.Char()
    product_type = fields.Char()
    tags = fields.Char(help="以逗号分隔的 Shopify 标签。")
    price = fields.Monetary(currency_field="currency_id")
    compare_at_price = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(related="store_id.currency_id", store=True)
    shopify_status = fields.Selection(
        [("DRAFT", "草稿"), ("ACTIVE", "已发布"), ("ARCHIVED", "已归档")],
        default="DRAFT",
        required=True,
        tracking=True,
    )
    sync_state = fields.Selection(CHANNEL_STATES, default="draft", required=True, tracking=True)
    shopify_product_gid = fields.Char(readonly=True, copy=False, index=True)
    shopify_handle = fields.Char(readonly=True, copy=False)
    last_payload_hash = fields.Char(readonly=True, copy=False)
    last_synced_at = fields.Datetime(readonly=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)
    collection_ids = fields.Many2many(
        "ll.shopify.collection", "ll_shopify_channel_collection_rel", string="分类集合"
    )
    image_ids = fields.One2many(
        "ll.shopify.channel.image", "channel_product_id", string="店铺图片", copy=True
    )
    variant_ids = fields.One2many(
        "ll.shopify.channel.variant", "channel_product_id", string="变体映射", copy=True
    )
    pending_job_count = fields.Integer(compute="_compute_pending_job_count")

    _sql_constraints = [
        (
            "store_product_unique",
            "unique(store_id, product_tmpl_id)",
            "同一产品在同一店铺只能有一个渠道配置。",
        ),
        (
            "store_shopify_gid_unique",
            "unique(store_id, shopify_product_gid)",
            "同一 Shopify 商品不能重复绑定。",
        ),
        ("channel_price_nonnegative", "check(price >= 0)", "销售价不能为负数。"),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_variant_bindings()
        return records

    @api.onchange("product_tmpl_id", "store_id")
    def _onchange_product_store(self):
        for channel in self:
            product = channel.product_tmpl_id
            if not product:
                continue
            if not channel.title:
                channel.title = product.name
            if not channel.description_html:
                channel.description_html = product.description_sale
            if not channel.vendor:
                channel.vendor = product.company_id.name or channel.store_id.company_id.name
            if channel.store_id.pricelist_id:
                channel.price = channel.store_id.pricelist_id._get_product_price(
                    product.product_variant_id, 1.0
                )

    @api.constrains("collection_ids", "store_id")
    def _check_collection_store(self):
        for channel in self:
            if any(collection.store_id != channel.store_id for collection in channel.collection_ids):
                raise ValidationError("渠道商品只能选择同一店铺的分类集合。")

    def _compute_pending_job_count(self):
        for channel in self:
            channel.pending_job_count = self.env["ll.shopify.job"].search_count(
                [
                    ("model_name", "=", channel._name),
                    ("res_id", "=", channel.id),
                    ("state", "in", ["queued", "running", "retry"]),
                ]
            )

    def _ensure_variant_bindings(self):
        variant_model = self.env["ll.shopify.channel.variant"]
        for channel in self:
            existing = set(channel.variant_ids.product_id.ids)
            for product in channel.product_tmpl_id.product_variant_ids:
                if product.id not in existing:
                    variant_model.create(
                        {"channel_product_id": channel.id, "product_id": product.id}
                    )

    def _validate_publish(self):
        errors = []
        for channel in self:
            current = []
            if channel.store_id.state != "connected":
                current.append("店铺未连接")
            if not channel.title.strip():
                current.append("标题为空")
            if channel.price < 0:
                current.append("价格小于0")
            if channel.store_id.currency_id != channel.store_id.pricelist_id.currency_id:
                current.append("币种与价格表不一致")
            if not channel.variant_ids:
                current.append("没有可发布的产品变体")
            if len(channel.variant_ids) > 100:
                current.append("单个商品最多支持同步发布100个变体，请先拆分商品")
            if len(channel.variant_ids) > 1 and any(not item.sku for item in channel.variant_ids):
                current.append("多变体商品的每个变体必须有唯一SKU")
            if channel.collection_ids.filtered(lambda collection: not collection.shopify_collection_gid):
                current.append("所选分类集合尚未同步到Shopify")
            duplicate_skus = [
                sku
                for sku in set(channel.variant_ids.mapped("sku")) - {False, ""}
                if len(channel.variant_ids.filtered(lambda item, value=sku: item.sku == value)) > 1
            ]
            if duplicate_skus:
                current.append("店铺内变体SKU重复")
            if current:
                errors.append(f"{channel.display_name}: {'；'.join(current)}")
        return errors

    def _build_product_payload(self):
        self.ensure_one()
        self._ensure_variant_bindings()
        option_lines = self.product_tmpl_id.attribute_line_ids.filtered(
            lambda line: line.value_ids
        ).sorted(lambda line: (line.attribute_id.sequence, line.attribute_id.id))
        product_options = [
            {
                "name": line.attribute_id.name,
                "position": position,
                "values": [{"name": value.name} for value in line.value_ids],
            }
            for position, line in enumerate(option_lines, start=1)
        ]
        variants = []
        for binding in self.variant_ids.sorted("id"):
            selected = {
                value.attribute_id.id: value
                for value in binding.product_id.product_template_attribute_value_ids
            }
            variant = {
                "sku": binding.sku or None,
                "barcode": binding.barcode or None,
                "price": str(binding.effective_price),
                "optionValues": [
                    {
                        "optionName": line.attribute_id.name,
                        "name": selected[line.attribute_id.id].name,
                    }
                    for line in option_lines
                    if line.attribute_id.id in selected
                ],
            }
            if self.compare_at_price:
                variant["compareAtPrice"] = str(self.compare_at_price)
            if binding.shopify_variant_gid:
                variant["id"] = binding.shopify_variant_gid
            variants.append(variant)
        product = {
            "title": self.title,
            "descriptionHtml": self.description_html or "",
            "handle": self.handle or None,
            "status": self.shopify_status,
            "vendor": self.vendor or None,
            "productType": self.product_type or None,
            "tags": [tag.strip() for tag in (self.tags or "").split(",") if tag.strip()],
            "seo": {
                "title": self.seo_title or self.title,
                "description": self.seo_description or "",
            },
            "productOptions": product_options,
            "variants": variants,
            "collections": [
                collection.shopify_collection_gid
                for collection in self.collection_ids
                if collection.shopify_collection_gid
            ],
        }
        return {
            "synchronous": True,
            "input": product,
            "identifier": {"id": self.shopify_product_gid} if self.shopify_product_gid else None,
        }

    def action_queue_publish(self):
        errors = self._validate_publish()
        if errors:
            raise UserError("发布前检查未通过：\n" + "\n".join(errors))
        for channel in self:
            self.env["ll.shopify.job"].enqueue(
                channel.store_id,
                "publish_product",
                channel,
                payload=channel._build_product_payload(),
            )
            channel.sync_state = "queued"
        return self.env["ll.shopify.store"]._notify(
            "已进入后台队列", f"已创建 {len(self)} 个独立发布任务。"
        )

    def _inventory_marker(self):
        self.ensure_one()
        mappings = self.env["ll.shopify.location.map"].search(
            [("store_id", "=", self.store_id.id), ("active", "=", True)]
        )
        return {
            "quantities": [
                {
                    "product": binding.product_id.id,
                    "inventory_item": binding.shopify_inventory_item_gid,
                    "locations": [
                        {
                            "gid": mapping.shopify_location_gid,
                            "quantity": mapping.available_quantity(binding.product_id),
                        }
                        for mapping in mappings
                    ],
                }
                for binding in self.variant_ids
                if binding.shopify_inventory_item_gid
            ]
        }

    def action_open_jobs(self):
        self.ensure_one()
        action = self.env.ref("lightlink_shopify_multistore.action_shopify_job").read()[0]
        action["domain"] = [("model_name", "=", self._name), ("res_id", "=", self.id)]
        return action

    def action_archive_remote(self):
        for channel in self:
            channel.write({"shopify_status": "ARCHIVED", "sync_state": "queued"})
        return self.action_queue_publish()

    def name_get(self):
        return [(record.id, f"{record.store_id.name} / {record.title}") for record in self]


class ShopifyChannelVariant(models.Model):
    _name = "ll.shopify.channel.variant"
    _description = "Shopify 渠道变体"
    _order = "channel_product_id, product_id"

    channel_product_id = fields.Many2one(
        "ll.shopify.channel.product", required=True, ondelete="cascade", index=True
    )
    store_id = fields.Many2one(related="channel_product_id.store_id", store=True, index=True)
    product_id = fields.Many2one("product.product", required=True, ondelete="restrict")
    sku = fields.Char(related="product_id.default_code", readonly=True)
    barcode = fields.Char(related="product_id.barcode", readonly=True)
    price_override = fields.Monetary(currency_field="currency_id")
    effective_price = fields.Monetary(compute="_compute_effective_price", currency_field="currency_id")
    currency_id = fields.Many2one(related="store_id.currency_id", store=True)
    shopify_variant_gid = fields.Char(readonly=True, copy=False)
    shopify_inventory_item_gid = fields.Char(readonly=True, copy=False)

    _sql_constraints = [
        (
            "channel_product_variant_unique",
            "unique(channel_product_id, product_id)",
            "产品变体不能重复绑定。",
        )
    ]

    @api.depends("price_override", "channel_product_id.price")
    def _compute_effective_price(self):
        for variant in self:
            variant.effective_price = variant.price_override or variant.channel_product_id.price


class ShopifyChannelImage(models.Model):
    _name = "ll.shopify.channel.image"
    _description = "Shopify 渠道图片"
    _order = "sequence, id"

    channel_product_id = fields.Many2one(
        "ll.shopify.channel.product", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10)
    image = fields.Image(required=True, max_width=2048, max_height=2048, attachment=True)
    filename = fields.Char()
    mimetype = fields.Char(default="image/jpeg")
    alt_text = fields.Char(translate=True)
    checksum = fields.Char(compute="_compute_checksum", store=True, index=True)
    public_token = fields.Char(default=lambda self: secrets.token_urlsafe(24), copy=False, index=True)
    shopify_media_gid = fields.Char(readonly=True, copy=False)
    media_status = fields.Selection(
        [("new", "待上传"), ("ready", "已同步"), ("error", "失败")], default="new"
    )
    last_error = fields.Text(readonly=True)

    _sql_constraints = [
        ("image_token_unique", "unique(public_token)", "图片访问令牌必须唯一。"),
        (
            "channel_checksum_unique",
            "unique(channel_product_id, checksum)",
            "同一店铺商品不能重复添加相同图片。",
        ),
    ]

    @api.depends("image")
    def _compute_checksum(self):
        for image in self:
            image.checksum = (
                hashlib.sha256(base64.b64decode(image.image)).hexdigest() if image.image else False
            )

    def public_url(self):
        self.ensure_one()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url").rstrip("/")
        return f"{base_url}/lightlink/shopify/media/{self.public_token}"

    def unlink(self):
        if not self.env.context.get("allow_shopify_media_unlink") and self.filtered("shopify_media_gid"):
            raise ValidationError("已同步图片必须使用“从店铺移除”，以便保留确认和后台任务记录。")
        return super().unlink()

    def action_remove_remote(self):
        for image in self:
            channel = image.channel_product_id
            if image.shopify_media_gid and channel.shopify_product_gid:
                self.env["ll.shopify.job"].enqueue(
                    channel.store_id,
                    "delete_media",
                    channel,
                    payload={
                        "product_id": channel.shopify_product_gid,
                        "media_ids": [image.shopify_media_gid],
                    },
                )
        return self.with_context(allow_shopify_media_unlink=True).unlink()


class ShopifyCollection(models.Model):
    _name = "ll.shopify.collection"
    _description = "Shopify 分类与集合映射"
    _inherit = ["mail.thread"]
    _order = "store_id, sequence, title"

    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related="store_id.company_id", store=True, index=True)
    store_id = fields.Many2one("ll.shopify.store", required=True, ondelete="restrict", index=True)
    category_id = fields.Many2one("product.category", required=True, ondelete="restrict")
    title = fields.Char(required=True, translate=True)
    description_html = fields.Html(translate=True, sanitize=True)
    handle = fields.Char()
    image = fields.Image(max_width=2048, max_height=2048, attachment=True)
    image_alt = fields.Char(translate=True)
    image_public_token = fields.Char(
        default=lambda self: secrets.token_urlsafe(24), copy=False, index=True
    )
    shopify_collection_gid = fields.Char(readonly=True, copy=False)
    sync_state = fields.Selection(CHANNEL_STATES, default="draft", required=True)
    last_synced_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)

    _sql_constraints = [
        (
            "store_category_unique",
            "unique(store_id, category_id)",
            "同一店铺的产品分类只能映射一个集合。",
        ),
        (
            "store_collection_gid_unique",
            "unique(store_id, shopify_collection_gid)",
            "同一 Shopify 集合不能重复绑定。",
        ),
        (
            "collection_image_token_unique",
            "unique(image_public_token)",
            "分类图片访问令牌必须唯一。",
        ),
    ]

    @api.onchange("category_id")
    def _onchange_category(self):
        if self.category_id and not self.title:
            self.title = self.category_id.name

    def _build_collection_payload(self):
        self.ensure_one()
        result = {
            "title": self.title,
            "descriptionHtml": self.description_html or "",
            "handle": self.handle or None,
        }
        if self.image:
            base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url").rstrip("/")
            result["image"] = {
                "src": f"{base_url}/lightlink/shopify/collection-media/{self.image_public_token}",
                "altText": self.image_alt or self.title,
            }
        if self.shopify_collection_gid:
            result["id"] = self.shopify_collection_gid
        return {"input": result}

    def action_queue_sync(self):
        for collection in self:
            self.env["ll.shopify.job"].enqueue(
                collection.store_id,
                "sync_collection",
                collection,
                payload=collection._build_collection_payload(),
            )
            collection.sync_state = "queued"
        return self.env["ll.shopify.store"]._notify("已进入后台队列", "分类集合将在后台同步。")


class ShopifyLocationMap(models.Model):
    _name = "ll.shopify.location.map"
    _description = "Shopify 库位映射"
    _order = "store_id, name"

    active = fields.Boolean(default=True)
    name = fields.Char(required=True)
    company_id = fields.Many2one(related="store_id.company_id", store=True, index=True)
    store_id = fields.Many2one("ll.shopify.store", required=True, ondelete="cascade", index=True)
    location_id = fields.Many2one(
        "stock.location", required=True, domain="[('usage', '=', 'internal'), ('company_id', 'in', [False, company_id])]"
    )
    shopify_location_gid = fields.Char(required=True)
    safety_stock = fields.Float(default=0.0)

    _sql_constraints = [
        (
            "store_odoo_location_unique",
            "unique(store_id, location_id)",
            "同一店铺的Odoo库位不能重复映射。",
        ),
        (
            "store_shopify_location_unique",
            "unique(store_id, shopify_location_gid)",
            "同一店铺的Shopify Location不能重复映射。",
        ),
        ("location_safety_nonnegative", "check(safety_stock >= 0)", "安全库存不能为负数。"),
    ]

    def available_quantity(self, product):
        self.ensure_one()
        quantity = self.env["stock.quant"]._get_available_quantity(product, self.location_id)
        return max(int(quantity - self.safety_stock - self.store_id.safety_stock), 0)


def channel_idempotency(channel, operation, payload):
    return payload_hash(
        {
            "operation": operation,
            "store": channel.store_id.id,
            "record": f"{channel._name}:{channel.id}",
            "payload": payload,
        }
    )
