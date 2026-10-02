from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ShopifyPublishWizard(models.TransientModel):
    _name = "ll.shopify.publish.wizard"
    _description = "Shopify 发布预览"

    product_ids = fields.Many2many("product.template", string="Odoo 产品", required=True)
    store_ids = fields.Many2many(
        "ll.shopify.store",
        string="目标店铺",
        required=True,
        domain="[('state', '=', 'connected'), ('active', '=', True)]",
    )
    update_price = fields.Boolean(default=True, string="使用各店价格表更新价格")
    include_images = fields.Boolean(default=True, string="首次创建时复制产品主图")
    include_collections = fields.Boolean(default=True, string="关联已配置的分类集合")
    sync_inventory = fields.Boolean(default=True, string="发布后同步库存")
    preview_html = fields.Html(compute="_compute_preview_html", sanitize=False)
    validation_error_count = fields.Integer(compute="_compute_preview_html")

    @api.depends(
        "product_ids",
        "store_ids",
        "update_price",
        "include_images",
        "include_collections",
        "sync_inventory",
    )
    def _compute_preview_html(self):
        for wizard in self:
            rows, errors = wizard._preview_rows()
            body = []
            for row in rows:
                issues = "；".join(row["errors"]) if row["errors"] else "检查通过"
                issue_class = "text-danger" if row["errors"] else "text-success"
                body.append(
                    Markup(
                        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{:.2f} {}</td>"
                        '<td class="{}">{}</td></tr>'
                    ).format(
                        escape(row["product"]),
                        escape(row["store"]),
                        escape(row["mode"]),
                        row["price"],
                        escape(row["currency"]),
                        issue_class,
                        escape(issues),
                    )
                )
            wizard.preview_html = Markup(
                '<div class="alert alert-info mb-3">确认后，每个“产品 × 店铺”会生成独立、可重试的后台任务；单店失败不会阻塞其他店铺。</div>'
                '<table class="table table-sm table-striped"><thead><tr>'
                "<th>产品</th><th>店铺</th><th>操作</th><th>价格</th><th>检查</th>"
                "</tr></thead><tbody>{}</tbody></table>"
            ).format(Markup("\n").join(body))
            wizard.validation_error_count = errors

    def _preview_rows(self):
        self.ensure_one()
        rows = []
        error_count = 0
        channel_model = self.env["ll.shopify.channel.product"]
        for store in self.store_ids:
            for product in self.product_ids:
                errors = []
                if store.state != "connected":
                    errors.append("店铺未连接")
                if product.company_id and product.company_id != store.company_id:
                    errors.append("产品与店铺公司不一致")
                if store.pricelist_id.currency_id != store.currency_id:
                    errors.append("币种与价格表不一致")
                if not product.product_variant_ids:
                    errors.append("没有可发布变体")
                price = store.pricelist_id._get_product_price(product.product_variant_id, 1.0)
                channel = channel_model.search(
                    [("store_id", "=", store.id), ("product_tmpl_id", "=", product.id)],
                    limit=1,
                )
                rows.append(
                    {
                        "product": product.display_name,
                        "store": store.display_name,
                        "mode": "更新并发布" if channel else "新建并发布",
                        "price": price,
                        "currency": store.currency_id.name,
                        "errors": errors,
                    }
                )
                error_count += len(errors)
        if not self.product_ids:
            error_count += 1
        if not self.store_ids:
            error_count += 1
        return rows, error_count

    def action_confirm_publish(self):
        self.ensure_one()
        rows, errors = self._preview_rows()
        if errors:
            details = [
                f"{row['store']} / {row['product']}：{'；'.join(row['errors'])}"
                for row in rows
                if row["errors"]
            ]
            raise UserError("发布预览存在问题，请先修复：\n" + "\n".join(details))
        channel_model = self.env["ll.shopify.channel.product"]
        created_channels = channel_model
        for store in self.store_ids:
            for product in self.product_ids:
                channel = channel_model.search(
                    [("store_id", "=", store.id), ("product_tmpl_id", "=", product.id)],
                    limit=1,
                )
                price = store.pricelist_id._get_product_price(product.product_variant_id, 1.0)
                if not channel:
                    channel = channel_model.create(
                        {
                            "store_id": store.id,
                            "product_tmpl_id": product.id,
                            "title": product.name,
                            "description_html": product.description_sale or "",
                            "vendor": product.company_id.name or store.company_id.name,
                            "price": price,
                            "shopify_status": "DRAFT",
                        }
                    )
                elif self.update_price:
                    channel.price = price
                if self.include_images and product.image_1920 and not channel.image_ids:
                    self.env["ll.shopify.channel.image"].create(
                        {
                            "channel_product_id": channel.id,
                            "image": product.image_1920,
                            "filename": f"product-{product.id}.jpg",
                            "alt_text": product.name,
                        }
                    )
                if self.include_collections:
                    collections = self.env["ll.shopify.collection"].search(
                        [
                            ("store_id", "=", store.id),
                            ("category_id", "parent_of", product.categ_id.id),
                            ("active", "=", True),
                        ]
                    )
                    channel.collection_ids = [(6, 0, collections.ids)]
                created_channels |= channel
        created_channels.action_queue_publish()
        return {
            "type": "ir.actions.act_window",
            "name": _("Shopify 渠道商品"),
            "res_model": "ll.shopify.channel.product",
            "views": [[False, "list"], [False, "form"]],
            "domain": [("id", "in", created_channels.ids)],
            "target": "current",
        }
