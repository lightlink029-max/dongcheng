import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .shopify_api import ShopifyAPIError, graphql_request, normalize_shop_domain


class ShopifyStore(models.Model):
    _name = "ll.shopify.store"
    _description = "Shopify 店铺"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name, id"

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    shop_domain = fields.Char(required=True, tracking=True, index=True)
    public_domain = fields.Char(help="可选：面向客户的自定义域名，仅用于后台识别。")
    allowed_origins = fields.Text(
        help="公开询盘接口允许的完整来源地址，每行一个，例如 https://shop.example.com。"
    )
    state = fields.Selection(
        [
            ("draft", "未连接"),
            ("connected", "已连接"),
            ("paused", "已暂停"),
            ("error", "异常"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    api_version = fields.Selection(
        [("2026-07", "2026-07")], default="2026-07", required=True
    )
    client_id = fields.Char(groups="base.group_system", copy=False)
    client_secret = fields.Char(groups="base.group_system", copy=False)
    access_token = fields.Char(groups="base.group_system", copy=False)
    granted_scopes = fields.Char(readonly=True, copy=False)
    requested_scopes = fields.Char(
        default=(
            "read_products,write_products,read_inventory,write_inventory,"
            "read_locations,read_orders,write_orders,read_fulfillments,"
            "write_fulfillments,read_customers"
        )
    )
    webhook_secret = fields.Char(groups="base.group_system", copy=False)
    public_inquiry_token = fields.Char(readonly=True, copy=False, index=True)
    oauth_callback_url = fields.Char(compute="_compute_endpoint_urls")
    webhook_callback_url = fields.Char(compute="_compute_endpoint_urls", groups="base.group_system")
    inquiry_endpoint_url = fields.Char(compute="_compute_endpoint_urls")
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id
    )
    pricelist_id = fields.Many2one(
        "product.pricelist", required=True, domain="[('currency_id', '=', currency_id)]"
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse", required=True, domain="[('company_id', '=', company_id)]"
    )
    sales_team_id = fields.Many2one("crm.team", string="销售团队")
    salesperson_id = fields.Many2one("res.users", string="默认销售员")
    shipping_product_id = fields.Many2one(
        "product.product", domain="[('detailed_type', '=', 'service')]"
    )
    unmapped_product_id = fields.Many2one("product.product", string="未映射商品占位产品")
    auto_confirm_orders = fields.Boolean()
    sync_products = fields.Boolean(default=True)
    sync_inventory = fields.Boolean(default=True)
    sync_orders = fields.Boolean(default=True)
    sync_fulfillments = fields.Boolean(default=True)
    safety_stock = fields.Float(default=0.0)
    last_connection_at = fields.Datetime(readonly=True)
    last_product_sync_at = fields.Datetime(readonly=True)
    last_inventory_sync_at = fields.Datetime(readonly=True)
    last_order_sync_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)
    pending_job_count = fields.Integer(compute="_compute_counts")
    failed_job_count = fields.Integer(compute="_compute_counts")
    channel_product_count = fields.Integer(compute="_compute_counts")
    order_count = fields.Integer(compute="_compute_counts")

    _sql_constraints = [
        ("shop_domain_unique", "unique(shop_domain)", "同一个 Shopify 店铺只能配置一次。"),
        (
            "public_inquiry_token_unique",
            "unique(public_inquiry_token)",
            "询盘访问令牌必须唯一。",
        ),
        ("safety_stock_nonnegative", "check(safety_stock >= 0)", "安全库存不能为负数。"),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("shop_domain"):
                try:
                    vals["shop_domain"] = normalize_shop_domain(vals["shop_domain"])
                except ValueError as error:
                    raise ValidationError(str(error)) from error
            vals.setdefault("webhook_secret", secrets.token_urlsafe(32))
            vals.setdefault("public_inquiry_token", secrets.token_urlsafe(32))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("shop_domain"):
            try:
                vals["shop_domain"] = normalize_shop_domain(vals["shop_domain"])
            except ValueError as error:
                raise ValidationError(str(error)) from error
        if "company_id" in vals and any(
            store.company_id.id != vals["company_id"]
            and (store.channel_product_count or store.order_count)
            for store in self
        ):
            raise ValidationError("已有商品或订单历史的店铺不能更换公司。")
        return super().write(vals)

    @api.constrains("currency_id", "pricelist_id")
    def _check_pricelist_currency(self):
        for store in self:
            if store.pricelist_id and store.pricelist_id.currency_id != store.currency_id:
                raise ValidationError("店铺币种必须与价格表币种一致。")

    @api.constrains("warehouse_id", "company_id")
    def _check_warehouse_company(self):
        for store in self:
            if store.warehouse_id.company_id != store.company_id:
                raise ValidationError("仓库必须属于店铺所在公司。")

    def _compute_counts(self):
        job_model = self.env["ll.shopify.job"]
        channel_model = self.env["ll.shopify.channel.product"]
        order_model = self.env["ll.shopify.order.binding"]
        for store in self:
            store.pending_job_count = job_model.search_count(
                [("store_id", "=", store.id), ("state", "in", ["queued", "running", "retry"])]
            )
            store.failed_job_count = job_model.search_count(
                [("store_id", "=", store.id), ("state", "=", "failed")]
            )
            store.channel_product_count = channel_model.search_count(
                [("store_id", "=", store.id)]
            )
            store.order_count = order_model.search_count([("store_id", "=", store.id)])

    def _compute_endpoint_urls(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url").rstrip("/")
        for store in self:
            store.oauth_callback_url = f"{base_url}/lightlink/shopify/oauth/callback"
            store.webhook_callback_url = (
                f"{base_url}/lightlink/shopify/webhook/{store.webhook_secret}"
                if store.webhook_secret
                else ""
            )
            store.inquiry_endpoint_url = (
                f"{base_url}/lightlink/shopify/inquiry/{store.public_inquiry_token}"
                if store.public_inquiry_token
                else ""
            )

    def _graphql(self, query, variables=None):
        self.ensure_one()
        if self.state not in {"connected", "error"} or not self.access_token:
            raise UserError("该店铺尚未完成 Shopify 连接。")
        return graphql_request(
            self.shop_domain, self.api_version, self.access_token, query, variables
        )

    def action_start_oauth(self):
        self.ensure_one()
        if not self.client_id or not self.client_secret:
            raise UserError("请先由系统管理员填写 Shopify Client ID 和 Client Secret。")
        state = self.env["ll.shopify.oauth.state"].create({"store_id": self.id})
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url").rstrip("/")
        redirect_uri = f"{base_url}/lightlink/shopify/oauth/callback"
        query = {
            "client_id": self.client_id,
            "scope": self.requested_scopes,
            "redirect_uri": redirect_uri,
            "state": state.token,
        }
        from urllib.parse import urlencode

        return {
            "type": "ir.actions.act_url",
            "url": f"https://{self.shop_domain}/admin/oauth/authorize?{urlencode(query)}",
            "target": "self",
        }

    def action_test_connection(self):
        for store in self:
            try:
                data = store._graphql("query { shop { name myshopifyDomain currencyCode } }")
                shop = data.get("shop") or {}
                if normalize_shop_domain(shop.get("myshopifyDomain")) != store.shop_domain:
                    raise UserError("Shopify 返回的店铺域名与当前配置不一致。")
                store.write(
                    {
                        "state": "connected",
                        "last_connection_at": fields.Datetime.now(),
                        "last_error": False,
                    }
                )
            except (ShopifyAPIError, ValueError, UserError) as error:
                store.write({"state": "error", "last_error": str(error)})
                raise UserError(_("连接测试失败：%s") % error) from error
        return self._notify("连接测试成功", "Shopify API 已正常响应。")

    def action_pause(self):
        self.write({"state": "paused"})

    def action_resume(self):
        for store in self:
            if not store.access_token:
                raise UserError("没有访问令牌，请重新连接 Shopify。")
        self.write({"state": "connected", "last_error": False})

    def action_sync_now(self):
        run_token = fields.Datetime.to_string(fields.Datetime.now())
        for store in self:
            if store.state != "connected":
                raise UserError(_("店铺 %s 不是已连接状态。") % store.display_name)
            if store.sync_orders:
                self.env["ll.shopify.job"].enqueue(
                    store, "import_orders", store, payload={"manual_run": run_token}
                )
            if store.sync_inventory:
                channels = self.env["ll.shopify.channel.product"].search(
                    [("store_id", "=", store.id), ("active", "=", True)]
                )
                for channel in channels:
                    self.env["ll.shopify.job"].enqueue(
                        store, "sync_inventory", channel, payload=channel._inventory_marker()
                    )
        return self._notify("同步任务已创建", "系统会在后台逐店执行，失败不会影响其他店铺。")

    @api.model
    def _cron_schedule_sync(self):
        now = fields.Datetime.now()
        order_bucket = now.strftime("%Y-%m-%dT%H:%M")
        inventory_bucket = now.replace(
            minute=(now.minute // 15) * 15, second=0, microsecond=0
        ).strftime("%Y-%m-%dT%H:%M")
        stores = self.search([("state", "=", "connected"), ("active", "=", True)])
        jobs = self.env["ll.shopify.job"]
        for store in stores:
            if store.sync_orders:
                jobs.enqueue(store, "import_orders", store, payload={"scheduled": order_bucket})
            if store.sync_inventory:
                channels = self.env["ll.shopify.channel.product"].search(
                    [
                        ("store_id", "=", store.id),
                        ("active", "=", True),
                        ("shopify_product_gid", "!=", False),
                    ]
                )
                for channel in channels:
                    jobs.enqueue(
                        store,
                        "sync_inventory",
                        channel,
                        payload={"scheduled": inventory_bucket},
                    )
        return True

    def action_open_jobs(self):
        self.ensure_one()
        action = self.env.ref("lightlink_shopify_multistore.action_shopify_job").read()[0]
        action["domain"] = [("store_id", "=", self.id)]
        action["context"] = {"default_store_id": self.id}
        return action

    def action_open_channels(self):
        self.ensure_one()
        action = self.env.ref(
            "lightlink_shopify_multistore.action_shopify_channel_product"
        ).read()[0]
        action["domain"] = [("store_id", "=", self.id)]
        action["context"] = {"default_store_id": self.id}
        return action

    @api.model
    def _notify(self, title, message, notification_type="success"):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": notification_type,
                "sticky": False,
            },
        }


class ShopifyOAuthState(models.Model):
    _name = "ll.shopify.oauth.state"
    _description = "Shopify OAuth 临时状态"
    _order = "create_date desc"

    token = fields.Char(required=True, default=lambda self: secrets.token_urlsafe(32), index=True)
    store_id = fields.Many2one("ll.shopify.store", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    expires_at = fields.Datetime(
        required=True, default=lambda self: fields.Datetime.now() + timedelta(minutes=10)
    )
    used = fields.Boolean(default=False)

    _sql_constraints = [("oauth_state_token_unique", "unique(token)", "OAuth状态必须唯一。")]

    @api.autovacuum
    def _gc_oauth_states(self):
        cutoff = fields.Datetime.now() - timedelta(days=1)
        self.sudo().search(["|", ("used", "=", True), ("expires_at", "<", cutoff)]).unlink()
