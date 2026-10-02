import hashlib
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize


class ShopifyInquiry(models.Model):
    _name = "ll.shopify.inquiry"
    _description = "Shopify 采购询盘"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    company_id = fields.Many2one(related="store_id.company_id", store=True, index=True)
    store_id = fields.Many2one("ll.shopify.store", required=True, ondelete="restrict", index=True)
    lead_id = fields.Many2one("crm.lead", required=True, ondelete="restrict", index=True)
    name = fields.Char(required=True)
    email = fields.Char(required=True)
    phone = fields.Char()
    company_name = fields.Char()
    message = fields.Text(required=True)
    product_reference = fields.Char()
    page_url = fields.Char()
    utm_source = fields.Char()
    utm_medium = fields.Char()
    utm_campaign = fields.Char()
    consent = fields.Boolean(required=True)
    consent_at = fields.Datetime(required=True)
    ip_hash = fields.Char(index=True)
    user_agent = fields.Char()

    @api.model
    def create_from_public(self, store, values, *, remote_ip="", user_agent=""):
        required = ["name", "email", "message"]
        missing = [key for key in required if not str(values.get(key) or "").strip()]
        if missing:
            raise ValidationError("请填写姓名、电子邮箱和采购需求。")
        if not values.get("consent"):
            raise ValidationError("提交前必须同意隐私政策和联系授权。")
        email = email_normalize(values["email"])
        if not email:
            raise ValidationError("电子邮箱格式不正确。")
        clean = {
            key: str(values.get(key) or "").strip()[:limit]
            for key, limit in {
                "name": 160,
                "phone": 64,
                "company_name": 160,
                "message": 5000,
                "product_reference": 255,
                "page_url": 1000,
                "utm_source": 128,
                "utm_medium": 128,
                "utm_campaign": 128,
            }.items()
        }
        ip_hash = hashlib.sha256(f"{store.id}:{remote_ip}".encode()).hexdigest()
        lead = self.env["crm.lead"].create(
            {
                "name": f"Shopify采购需求 - {clean['name']}",
                "contact_name": clean["name"],
                "partner_name": clean["company_name"],
                "email_from": email,
                "phone": clean["phone"],
                "description": clean["message"],
                "team_id": store.sales_team_id.id or False,
                "user_id": store.salesperson_id.id or False,
                "company_id": store.company_id.id,
                "ll_shopify_store_id": store.id,
                "ll_shopify_page_url": clean["page_url"],
                "ll_shopify_product_reference": clean["product_reference"],
                "ll_shopify_utm_source": clean["utm_source"],
                "ll_shopify_utm_medium": clean["utm_medium"],
                "ll_shopify_utm_campaign": clean["utm_campaign"],
                "ll_shopify_consent_at": fields.Datetime.now(),
            }
        )
        return self.create(
            {
                "store_id": store.id,
                "lead_id": lead.id,
                "email": email,
                "consent": True,
                "consent_at": fields.Datetime.now(),
                "ip_hash": ip_hash,
                "user_agent": user_agent[:500],
                **clean,
            }
        )


class CrmLead(models.Model):
    _inherit = "crm.lead"

    ll_shopify_store_id = fields.Many2one("ll.shopify.store", string="Shopify 来源店铺", index=True)
    ll_shopify_page_url = fields.Char(string="Shopify 来源页面")
    ll_shopify_product_reference = fields.Char(string="Shopify 商品引用")
    ll_shopify_utm_source = fields.Char(string="UTM Source")
    ll_shopify_utm_medium = fields.Char(string="UTM Medium")
    ll_shopify_utm_campaign = fields.Char(string="UTM Campaign")
    ll_shopify_consent_at = fields.Datetime(string="同意时间")


class ShopifyWebhookEvent(models.Model):
    _name = "ll.shopify.webhook.event"
    _description = "Shopify Webhook 事件"
    _order = "received_at desc, id desc"

    store_id = fields.Many2one("ll.shopify.store", required=True, ondelete="cascade", index=True)
    webhook_id = fields.Char(required=True, index=True)
    topic = fields.Char(required=True, index=True)
    shop_domain = fields.Char(required=True)
    payload_json = fields.Json(required=True)
    state = fields.Selection(
        [("received", "已接收"), ("queued", "已入队"), ("done", "已完成"), ("error", "失败")],
        default="received",
        required=True,
    )
    received_at = fields.Datetime(default=fields.Datetime.now, required=True)
    last_error = fields.Text()

    _sql_constraints = [
        (
            "store_webhook_unique",
            "unique(store_id, webhook_id)",
            "相同Webhook事件已经接收，不会重复处理。",
        )
    ]

    @api.autovacuum
    def _scrub_old_webhook_payloads(self):
        cutoff = fields.Datetime.now() - timedelta(days=30)
        self.sudo().search(
            [("received_at", "<", cutoff), ("payload_json", "!=", False)]
        ).write({"payload_json": {"scrubbed": True}, "last_error": False})
