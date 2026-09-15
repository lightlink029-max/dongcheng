from odoo import _, api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    psc_procurement_keywords = fields.Char(
        string="采购关键词",
        help="用于采购检索的同义词、材质、用途、市场叫法等；多个关键词可用逗号分隔。",
    )
    psc_category_attribute_template_ids = fields.Many2many(
        "product.attribute",
        string="分类推荐属性",
        compute="_compute_psc_category_attribute_template_ids",
    )

    @api.depends("categ_id", "categ_id.psc_attribute_template_ids")
    def _compute_psc_category_attribute_template_ids(self):
        for product in self:
            product.psc_category_attribute_template_ids = (
                product.categ_id.psc_attribute_template_ids
            )


class ProductCategory(models.Model):
    _inherit = "product.category"

    psc_attribute_template_ids = fields.Many2many(
        "product.attribute",
        "psc_product_category_attribute_rel",
        "category_id",
        "attribute_id",
        string="推荐属性模板",
        help="新建本分类产品时应优先维护的产品属性。这里只提供录入指引，不会自动创建产品变体。",
    )


class BusinessHubProductWorkspace(models.Model):
    _inherit = "psc.business.hub"

    product_workspace_widget = fields.Char(default="ready")

    @api.model
    def get_product_workspace(self, filters=None, offset=0, limit=24):
        filters = filters if isinstance(filters, dict) else {}
        offset = max(int(offset or 0), 0)
        limit = min(max(int(limit or 24), 1), 60)

        keyword = str(filters.get("keyword") or "").strip()[:120]
        category_filter = filters.get("category_id")
        category_id = self._workspace_filter_id(category_filter)
        attribute_value_id = self._workspace_filter_id(
            filters.get("attribute_value_id")
        )
        tag_id = self._workspace_filter_id(filters.get("tag_id"))
        image_status = filters.get("image_status")
        active_status = filters.get("active_status") or "active"

        domain = []
        product_model = self.env["product.template"].with_context(active_test=False)
        if active_status == "archived":
            domain.append(("active", "=", False))
        elif active_status != "all":
            domain.append(("active", "=", True))
        if category_filter == "uncategorized":
            domain.append(("categ_id", "=", False))
        elif category_id:
            domain.append(("categ_id", "child_of", category_id))
        if attribute_value_id:
            domain.append(("attribute_line_ids.value_ids", "in", [attribute_value_id]))
        if tag_id:
            domain.append(("product_tag_ids", "in", [tag_id]))
        if image_status == "with_image":
            domain.append(("image_1920", "!=", False))
        elif image_status == "without_image":
            domain.append(("image_1920", "=", False))
        if keyword:
            keyword_terms = [
                ("name", "ilike", keyword),
                ("default_code", "ilike", keyword),
                ("product_variant_ids.default_code", "ilike", keyword),
                ("barcode", "ilike", keyword),
                ("psc_procurement_keywords", "ilike", keyword),
                ("product_tag_ids.name", "ilike", keyword),
                ("attribute_line_ids.value_ids.name", "ilike", keyword),
                ("description_purchase", "ilike", keyword),
                ("description_sale", "ilike", keyword),
            ]
            domain.extend(["|"] * (len(keyword_terms) - 1) + keyword_terms)

        total = product_model.search_count(domain)
        products = product_model.search(
            domain,
            offset=offset,
            limit=limit,
            order="write_date desc, name, id",
        )
        product_rows = []
        for product in products:
            attribute_summary = []
            for line in product.attribute_line_ids[:4]:
                value_names = line.value_ids.mapped("name")[:4]
                if value_names:
                    attribute_summary.append(
                        f"{line.attribute_id.name}: {', '.join(value_names)}"
                    )
            local_write_date = (
                fields.Datetime.context_timestamp(self, product.write_date)
                if product.write_date
                else False
            )
            product_rows.append({
                "id": product.id,
                "name": product.name,
                "default_code": product.default_code or "",
                "barcode": product.barcode or "",
                "category": (
                    product.categ_id.complete_name
                    or product.categ_id.name
                    or _("未分类")
                ),
                "attributes": attribute_summary,
                "tags": product.product_tag_ids.mapped("name")[:6],
                "keywords": product.psc_procurement_keywords or "",
                "has_image": bool(product.image_128),
                "image_url": f"/web/image/product.template/{product.id}/image_256",
                "active": product.active,
                "write_date": (
                    local_write_date.strftime("%Y-%m-%d %H:%M")
                    if local_write_date
                    else ""
                ),
            })

        categories = self.env["product.category"].search([], order="complete_name, id")
        attribute_values = self.env["product.attribute.value"].search(
            [], limit=300, order="attribute_id, sequence, name, id"
        )
        tags = self.env["product.tag"].search([], limit=200, order="name, id")
        return {
            "products": product_rows,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(product_rows) < total,
            "filters": {
                "categories": [{
                    "id": category.id,
                    "name": category.complete_name or category.name,
                } for category in categories],
                "attribute_values": [{
                    "id": value.id,
                    "name": f"{value.attribute_id.name}: {value.name}",
                } for value in attribute_values],
                "tags": [{"id": tag.id, "name": tag.name} for tag in tags],
            },
        }

    @api.model
    def _workspace_filter_id(self, value):
        try:
            value = int(value or 0)
        except (TypeError, ValueError):
            return False
        return value if value > 0 else False
