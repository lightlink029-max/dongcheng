from odoo import api, fields, models


class ShopifyDashboard(models.Model):
    _name = "ll.shopify.dashboard"
    _description = "Shopify 多站点运营总览"

    name = fields.Char(default="Shopify 多站点运营总览", required=True)
    dashboard_widget = fields.Char(default="ready")

    @api.model
    def get_dashboard(self):
        store_model = self.env["ll.shopify.store"]
        channel_model = self.env["ll.shopify.channel.product"]
        job_model = self.env["ll.shopify.job"]
        order_model = self.env["ll.shopify.order.binding"]
        stores = store_model.search([], order="sequence, name")
        return {
            "summary": {
                "stores": len(stores),
                "connected": len(stores.filtered(lambda store: store.state == "connected")),
                "products": channel_model.search_count([( "active", "=", True)]),
                "orders": order_model.search_count([]),
                "pending_jobs": job_model.search_count(
                    [("state", "in", ["queued", "running", "retry"])]
                ),
                "failed_jobs": job_model.search_count([("state", "=", "failed")]),
            },
            "stores": [
                {
                    "id": store.id,
                    "name": store.name,
                    "domain": store.shop_domain,
                    "state": store.state,
                    "products": store.channel_product_count,
                    "orders": store.order_count,
                    "pending": store.pending_job_count,
                    "failed": store.failed_job_count,
                    "last_connection_at": fields.Datetime.to_string(store.last_connection_at)
                    if store.last_connection_at
                    else "",
                    "last_error": store.last_error or "",
                }
                for store in stores
            ],
        }
