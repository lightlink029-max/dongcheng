from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    ll_shopify_channel_ids = fields.One2many(
        "ll.shopify.channel.product", "product_tmpl_id", string="Shopify 渠道"
    )
    ll_shopify_channel_count = fields.Integer(compute="_compute_shopify_channel_count")
    ll_shopify_synced_count = fields.Integer(compute="_compute_shopify_channel_count")

    def _compute_shopify_channel_count(self):
        for product in self:
            product.ll_shopify_channel_count = len(product.ll_shopify_channel_ids)
            product.ll_shopify_synced_count = len(
                product.ll_shopify_channel_ids.filtered(lambda channel: channel.sync_state == "synced")
            )

    def action_open_shopify_channels(self):
        self.ensure_one()
        action = self.env.ref(
            "lightlink_shopify_multistore.action_shopify_channel_product"
        ).read()[0]
        action["domain"] = [("product_tmpl_id", "=", self.id)]
        action["context"] = {"default_product_tmpl_id": self.id}
        return action

    def action_shopify_publish_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": "发布到 Shopify",
            "res_model": "ll.shopify.publish.wizard",
            "views": [[False, "form"]],
            "target": "new",
            "context": {"default_product_ids": [(6, 0, self.ids)]},
        }


class BusinessHubProductWorkspace(models.Model):
    _inherit = "psc.business.hub"

    @api.model
    def get_product_workspace(self, filters=None, offset=0, limit=24):
        result = super().get_product_workspace(filters=filters, offset=offset, limit=limit)
        rows_by_id = {row["id"]: row for row in result.get("products", [])}
        if not rows_by_id:
            return result
        channels = self.env["ll.shopify.channel.product"].search(
            [("product_tmpl_id", "in", list(rows_by_id)), ("active", "=", True)],
            order="store_id, id",
        )
        by_product = {}
        for channel in channels:
            by_product.setdefault(channel.product_tmpl_id.id, []).append(
                {
                    "id": channel.id,
                    "store": channel.store_id.name,
                    "sync_state": channel.sync_state,
                    "status": channel.shopify_status,
                    "has_error": bool(channel.last_error),
                }
            )
        for product_id, row in rows_by_id.items():
            product_channels = by_product.get(product_id, [])
            row["shopify"] = {
                "channels": product_channels,
                "count": len(product_channels),
                "synced": sum(item["sync_state"] == "synced" for item in product_channels),
                "has_error": any(item["has_error"] for item in product_channels),
            }
        return result


class ProductCategory(models.Model):
    _inherit = "product.category"

    ll_shopify_collection_ids = fields.One2many(
        "ll.shopify.collection", "category_id", string="Shopify 集合映射"
    )
