from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import email_normalize


class ShopifyOrderBinding(models.Model):
    _name = "ll.shopify.order.binding"
    _description = "Shopify 订单绑定"
    _inherit = ["mail.thread"]
    _order = "shopify_updated_at desc, id desc"

    company_id = fields.Many2one(related="store_id.company_id", store=True, index=True)
    store_id = fields.Many2one("ll.shopify.store", required=True, ondelete="restrict", index=True)
    sale_order_id = fields.Many2one("sale.order", required=True, ondelete="restrict", index=True)
    shopify_order_gid = fields.Char(required=True, index=True)
    shopify_order_name = fields.Char(required=True, index=True)
    shopify_customer_gid = fields.Char()
    financial_status = fields.Char(readonly=True)
    fulfillment_status = fields.Char(readonly=True)
    shopify_updated_at = fields.Datetime(readonly=True)
    last_import_at = fields.Datetime(readonly=True)
    last_fulfillment_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)

    _sql_constraints = [
        (
            "store_shopify_order_unique",
            "unique(store_id, shopify_order_gid)",
            "同一店铺订单不能重复导入。",
        ),
        ("sale_order_binding_unique", "unique(sale_order_id)", "销售订单已经绑定 Shopify 订单。"),
    ]

    @api.model
    def _import_shopify_order(self, store, payload):
        store.ensure_one()
        order_gid = payload.get("id")
        order_name = payload.get("name") or order_gid
        if not order_gid:
            raise ValidationError("Shopify 订单缺少全局ID。")
        existing = self.search(
            [("store_id", "=", store.id), ("shopify_order_gid", "=", order_gid)], limit=1
        )
        remote_updated = self._parse_datetime(payload.get("updatedAt"))
        status_values = {
            "financial_status": payload.get("displayFinancialStatus") or "",
            "fulfillment_status": payload.get("displayFulfillmentStatus") or "",
            "shopify_updated_at": remote_updated,
            "last_import_at": fields.Datetime.now(),
            "last_error": False,
        }
        if existing:
            if (
                remote_updated
                and existing.shopify_updated_at
                and remote_updated <= existing.shopify_updated_at
            ):
                return existing
            if existing.sale_order_id.state in {"draft", "sent"}:
                existing.sale_order_id.write(
                    {"note": payload.get("note") or existing.sale_order_id.note}
                )
                existing._replace_draft_lines(payload)
            existing.write(status_values)
            return existing

        partner = self._find_or_create_partner(store, payload)
        sale = self.env["sale.order"].with_company(store.company_id).create(
            {
                "company_id": store.company_id.id,
                "partner_id": partner.id,
                "partner_invoice_id": partner.id,
                "partner_shipping_id": partner.id,
                "pricelist_id": store.pricelist_id.id,
                "warehouse_id": store.warehouse_id.id,
                "team_id": store.sales_team_id.id or False,
                "user_id": store.salesperson_id.id or False,
                "client_order_ref": order_name,
                "note": payload.get("note") or "",
                "ll_shopify_store_id": store.id,
                "ll_shopify_order_gid": order_gid,
                "ll_shopify_order_name": order_name,
            }
        )
        binding = self.create(
            {
                "store_id": store.id,
                "sale_order_id": sale.id,
                "shopify_order_gid": order_gid,
                "shopify_order_name": order_name,
                "shopify_customer_gid": (payload.get("customer") or {}).get("id"),
                **status_values,
            }
        )
        binding._replace_draft_lines(payload)
        if store.auto_confirm_orders:
            sale.action_confirm()
        return binding

    @api.model
    def _find_or_create_partner(self, store, payload):
        customer = payload.get("customer") or {}
        address = payload.get("shippingAddress") or {}
        email = email_normalize(customer.get("email") or payload.get("email") or "") or False
        phone = customer.get("phone") or payload.get("phone") or address.get("phone") or False
        domain = [("company_id", "in", [False, store.company_id.id])]
        if email and phone:
            domain += ["|", ("email_normalized", "=", email), ("phone", "=", phone)]
        elif email:
            domain.append(("email_normalized", "=", email))
        elif phone:
            domain.append(("phone", "=", phone))
        else:
            domain.append(("id", "=", 0))
        partner = self.env["res.partner"].search(domain, limit=1)
        if partner:
            return partner
        name = " ".join(
            filter(
                None,
                [
                    customer.get("firstName") or address.get("firstName"),
                    customer.get("lastName") or address.get("lastName"),
                ],
            )
        ).strip()
        return self.env["res.partner"].create(
            {
                "name": name or payload.get("name") or _("Shopify 客户"),
                "company_id": store.company_id.id,
                "email": email,
                "phone": phone,
                "street": address.get("address1"),
                "street2": address.get("address2"),
                "city": address.get("city"),
                "zip": address.get("zip"),
                "comment": _("来源：Shopify 店铺 %s") % store.name,
            }
        )

    def _replace_draft_lines(self, payload):
        self.ensure_one()
        sale = self.sale_order_id
        if sale.state not in {"draft", "sent"}:
            return
        commands = [(5, 0, 0)]
        line_nodes = ((payload.get("lineItems") or {}).get("nodes") or [])
        for line in line_nodes:
            product = self._match_product(line)
            if not product:
                product = self.store_id.unmapped_product_id
            if not product:
                raise ValidationError(
                    _("订单 %s 中 SKU %s 未映射，且店铺未配置占位产品。")
                    % (self.shopify_order_name, line.get("sku") or "-")
                )
            self._assert_money_currency(line.get("originalUnitPriceSet"))
            price = self._money_amount(line.get("originalUnitPriceSet"))
            commands.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "name": line.get("name") or product.display_name,
                        "product_uom_qty": line.get("currentQuantity") or line.get("quantity") or 1,
                        "price_unit": price,
                        "ll_shopify_line_gid": line.get("id"),
                    },
                )
            )
        for shipping in ((payload.get("shippingLines") or {}).get("nodes") or []):
            if not self.store_id.shipping_product_id:
                continue
            self._assert_money_currency(shipping.get("originalPriceSet"))
            commands.append(
                (
                    0,
                    0,
                    {
                        "product_id": self.store_id.shipping_product_id.id,
                        "name": shipping.get("title") or _("Shopify 运费"),
                        "product_uom_qty": 1,
                        "price_unit": self._money_amount(shipping.get("originalPriceSet")),
                    },
                )
            )
        sale.write({"order_line": commands})

    def _match_product(self, line):
        variant_gid = (line.get("variant") or {}).get("id")
        if variant_gid:
            variant = self.env["ll.shopify.channel.variant"].search(
                [
                    ("store_id", "=", self.store_id.id),
                    ("shopify_variant_gid", "=", variant_gid),
                ],
                limit=1,
            )
            if variant:
                return variant.product_id
        sku = line.get("sku")
        if sku:
            variant = self.env["ll.shopify.channel.variant"].search(
                [("store_id", "=", self.store_id.id), ("sku", "=", sku)], limit=1
            )
            if variant:
                return variant.product_id
            return self.env["product.product"].search(
                [
                    ("default_code", "=", sku),
                    ("company_id", "in", [False, self.store_id.company_id.id]),
                ],
                limit=1,
            )
        return self.env["product.product"]

    @api.model
    def _money_amount(self, value):
        raw = (((value or {}).get("shopMoney") or {}).get("amount")) or 0
        try:
            return float(Decimal(str(raw)))
        except (InvalidOperation, ValueError):
            return 0.0

    def _assert_money_currency(self, value):
        self.ensure_one()
        currency = ((value or {}).get("shopMoney") or {}).get("currencyCode")
        if currency and currency != self.store_id.currency_id.name:
            raise ValidationError(
                _("订单币种 %s 与店铺价格表币种 %s 不一致。")
                % (currency, self.store_id.currency_id.name)
            )

    @api.model
    def _parse_datetime(self, value):
        if not value:
            return False
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed


class SaleOrder(models.Model):
    _inherit = "sale.order"

    ll_shopify_store_id = fields.Many2one("ll.shopify.store", string="Shopify 店铺", index=True)
    ll_shopify_order_gid = fields.Char(string="Shopify 订单GID", index=True, copy=False)
    ll_shopify_order_name = fields.Char(string="Shopify 订单号", index=True, copy=False)
    ll_shopify_binding_id = fields.One2many(
        "ll.shopify.order.binding", "sale_order_id", string="Shopify绑定"
    )


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    ll_shopify_line_gid = fields.Char(string="Shopify订单行GID", index=True, copy=False)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        result = super().button_validate()
        self._shopify_enqueue_fulfillment_if_needed()
        return result

    def _shopify_enqueue_fulfillment_if_needed(self):
        for picking in self.filtered(lambda item: item.state == "done" and item.sale_id.ll_shopify_store_id):
            store = picking.sale_id.ll_shopify_store_id
            if store.state == "connected" and store.sync_fulfillments:
                self.env["ll.shopify.job"].enqueue(store, "push_fulfillment", picking)

    @api.model
    def _shopify_allocate_fulfillment_lines(self, nodes, quantities_by_line):
        remaining = dict(quantities_by_line)
        remote_line_gids = {
            (line.get("lineItem") or {}).get("id")
            for node in nodes
            for line in ((node.get("lineItems") or {}).get("nodes") or [])
            if (line.get("lineItem") or {}).get("id")
        }
        fulfillment_orders = []
        for node in nodes:
            if node.get("status") in {"CLOSED", "CANCELLED"}:
                continue
            line_connection = node.get("lineItems") or {}
            if (line_connection.get("pageInfo") or {}).get("hasNextPage"):
                raise UserError("单个履约单的订单行超过250个，系统已停止回传以避免遗漏。")
            line_items = []
            for line in line_connection.get("nodes") or []:
                line_gid = (line.get("lineItem") or {}).get("id")
                if not line_gid:
                    continue
                available = remaining.get(line_gid, 0)
                quantity = min(available, line.get("remainingQuantity") or 0)
                if quantity > 0:
                    line_items.append({"id": line["id"], "quantity": quantity})
                    remaining[line_gid] -= quantity
            if line_items:
                fulfillment_orders.append(
                    {"fulfillmentOrderId": node["id"], "fulfillmentOrderLineItems": line_items}
                )
        return fulfillment_orders, remote_line_gids, remaining

    def _shopify_push_fulfillment(self, store):
        self.ensure_one()
        binding = self.env["ll.shopify.order.binding"].search(
            [("sale_order_id", "=", self.sale_id.id), ("store_id", "=", store.id)], limit=1
        )
        if not binding:
            raise UserError("该发货单没有对应的 Shopify 订单绑定。")
        quantities_by_line = {}
        for move in self.move_ids.filtered(
            lambda item: item.state == "done" and item.sale_line_id.ll_shopify_line_gid
        ):
            quantity = move.product_uom._compute_quantity(
                move.quantity, move.sale_line_id.product_uom_id
            )
            integer_quantity = int(round(quantity))
            if abs(quantity - integer_quantity) > 0.000001:
                raise UserError(
                    _("Shopify 订单行 %s 的本次发货数量必须是整数。")
                    % move.sale_line_id.display_name
                )
            if integer_quantity > 0:
                line_gid = move.sale_line_id.ll_shopify_line_gid
                quantities_by_line[line_gid] = (
                    quantities_by_line.get(line_gid, 0) + integer_quantity
                )
        if not quantities_by_line:
            return {"status": "nothing_to_fulfill"}
        query = """
            query FulfillmentOrders($id: ID!) {
              order(id: $id) {
                fulfillmentOrders(first: 250) {
                  nodes {
                    id status
                    lineItems(first: 250) {
                      nodes { id remainingQuantity lineItem { id } }
                      pageInfo { hasNextPage }
                    }
                  }
                  pageInfo { hasNextPage }
                }
              }
            }
        """
        data = store._graphql(query, {"id": binding.shopify_order_gid})
        fulfillment_connection = (data.get("order") or {}).get("fulfillmentOrders") or {}
        if (fulfillment_connection.get("pageInfo") or {}).get("hasNextPage"):
            raise UserError("该订单的履约单超过250个，系统已停止回传以避免遗漏。")
        nodes = fulfillment_connection.get("nodes") or []
        open_nodes = [node for node in nodes if node.get("status") not in {"CLOSED", "CANCELLED"}]
        if not open_nodes:
            return {"status": "nothing_to_fulfill"}
        tracking = {}
        carrier = getattr(self, "carrier_id", False)
        tracking_ref = getattr(self, "carrier_tracking_ref", False)
        if carrier:
            tracking["company"] = carrier.name
        if tracking_ref:
            tracking["number"] = tracking_ref
        fulfillment_orders, remote_line_gids, remaining = (
            self._shopify_allocate_fulfillment_lines(nodes, quantities_by_line)
        )
        missing = set(remaining) - remote_line_gids
        if missing:
            raise UserError("本次发货包含 Shopify 未返回的订单行，已停止回传以避免错发。")
        if not fulfillment_orders:
            return {"status": "nothing_to_fulfill"}
        mutation = """
            mutation CreateFulfillment($fulfillment: FulfillmentInput!) {
              fulfillmentCreate(fulfillment: $fulfillment) {
                fulfillment { id status }
                userErrors { field message }
              }
            }
        """
        fulfillment_gids = []
        for fulfillment_order in fulfillment_orders:
            variables = {
                "fulfillment": {
                    "lineItemsByFulfillmentOrder": [fulfillment_order],
                    "notifyCustomer": True,
                    **({"trackingInfo": tracking} if tracking else {}),
                }
            }
            response = store._graphql(mutation, variables)
            container = response.get("fulfillmentCreate") or {}
            errors = container.get("userErrors") or []
            if errors:
                raise UserError(
                    "；".join(error.get("message") or "履约失败" for error in errors)
                )
            fulfillment_gid = (container.get("fulfillment") or {}).get("id")
            if fulfillment_gid:
                fulfillment_gids.append(fulfillment_gid)
        binding.last_fulfillment_at = fields.Datetime.now()
        return {"fulfillment_gids": fulfillment_gids}
