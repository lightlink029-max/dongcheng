import hashlib
import html
import logging
import base64
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProductIntelligenceCandidate(models.Model):
    _name = "product.intelligence.candidate"
    _description = "产品机会候选"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "total_score desc, write_date desc"
    _check_company_auto = True

    name = fields.Char(string="产品名称", required=True, tracking=True)
    reference = fields.Char(string="编号", copy=False, readonly=True, default=lambda self: _("新建"))
    active = fields.Boolean(default=True)
    stage = fields.Selection(
        [
            ("observe", "观察"),
            ("orient", "研判"),
            ("review", "决策审核"),
            ("approved", "已批准"),
            ("rejected", "已淘汰"),
            ("executed", "已执行"),
        ],
        default="observe",
        required=True,
        tracking=True,
        string="OODA 阶段",
        group_expand="_group_expand_stage",
    )
    source_id = fields.Many2one(
        "product.intelligence.source", string="数据来源", required=True, tracking=True, check_company=True
    )
    external_id = fields.Char(string="外部产品 ID", index=True)
    external_url = fields.Char(string="产品链接")
    image_url = fields.Char(string="主图链接")
    original_image_url = fields.Char(string="原始主图链接", copy=False)
    oss_object_key = fields.Char(string="OSS 对象 Key", copy=False, readonly=True)
    image_storage_state = fields.Selection(
        [("external", "外部链接"), ("stored", "已存入 OSS"), ("failed", "OSS 上传失败")],
        string="图片存储状态", default="external", copy=False, readonly=True,
    )
    image_storage_error = fields.Char(string="图片存储错误", copy=False, readonly=True)
    image_preview = fields.Html(string="主图", compute="_compute_image_preview", sanitize=False)
    supplier_name = fields.Char(string="供应商", index=True)
    keyword_text = fields.Text(string="关键词")
    inquiry_count = fields.Integer(string="询盘数")
    transaction_count = fields.Integer(string="交易数")
    heat_score = fields.Float(string="热度", digits=(16, 2))
    sales_7d = fields.Integer(string="近7天销量")
    sales_30d = fields.Integer(string="近30天销量")
    sales_180d = fields.Integer(string="近半年销量")
    displayed_sales = fields.Integer(string="页面展示销量")
    sales_amount = fields.Monetary(string="销售金额", currency_field="currency_id")
    price_text = fields.Char(string="价格区间")
    repeat_purchase_rate = fields.Float(string="复购率 %", digits=(16, 2))
    supplier_rating = fields.Float(string="供应商评分", digits=(4, 2))
    review_count = fields.Integer(string="评价数")
    search_rank = fields.Integer(string="搜索排名")
    source_payload = fields.Json(copy=False)
    category = fields.Char(string="产品分类", index=True)
    target_country_id = fields.Many2one("res.country", string="目标国家/地区")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id
    )
    owner_id = fields.Many2one(
        "res.users", string="负责人", default=lambda self: self.env.user, tracking=True
    )
    data_date = fields.Date(string="数据日期", default=fields.Date.context_today)
    detail_state = fields.Selection(
        [("pending", "未补充"), ("queued", "等待补充"), ("done", "详情已补充"), ("failed", "补充失败")],
        string="详情状态", default="pending", copy=False, index=True,
    )
    core_industry_attributes = fields.Text(string="核心行业属性", copy=False)
    important_attributes = fields.Text(string="重要属性", copy=False)
    packaging_information = fields.Text(string="包装信息", copy=False)
    shipping_information = fields.Text(string="发货信息", copy=False)
    detail_error = fields.Char(string="详情错误", copy=False)
    detail_updated_at = fields.Datetime(string="详情更新时间", copy=False)

    supplier_price = fields.Monetary(string="供应商价格", currency_field="currency_id")
    target_sale_price = fields.Monetary(string="目标售价", currency_field="currency_id")
    logistics_cost = fields.Monetary(currency_field="currency_id")
    other_cost = fields.Monetary(currency_field="currency_id")
    estimated_margin_percent = fields.Float(
        string="预计利润率 %", compute="_compute_estimated_margin", store=True, digits=(16, 2)
    )
    supplier_count = fields.Integer()
    minimum_order_qty = fields.Float()
    lead_time_days = fields.Integer()
    monthly_search_volume = fields.Integer()
    trend_growth_percent = fields.Float(digits=(16, 2))
    competitor_count = fields.Integer()

    demand_score = fields.Float(default=50.0, digits=(5, 2))
    growth_score = fields.Float(default=50.0, digits=(5, 2))
    margin_score = fields.Float(default=50.0, digits=(5, 2))
    competition_score = fields.Float(
        default=50.0,
        digits=(5, 2),
        help="A higher score means a more attractive competitive landscape.",
    )
    logistics_score = fields.Float(
        default=50.0,
        digits=(5, 2),
        help="A higher score means easier and lower-risk logistics.",
    )
    compliance_score = fields.Float(
        default=50.0,
        digits=(5, 2),
        help="A higher score means lower compliance and intellectual-property risk.",
    )
    content_score = fields.Float(default=50.0, digits=(5, 2))
    total_score = fields.Float(
        string="综合评分", compute="_compute_total_score", store=True, digits=(5, 2), tracking=True
    )
    recommendation = fields.Selection(
        [("reject", "淘汰"), ("review", "复核"), ("approve", "批准")],
        compute="_compute_recommendation",
        store=True,
        string="建议",
    )

    description = fields.Html()
    decision_notes = fields.Html()
    rejection_reason = fields.Text()
    product_tmpl_id = fields.Many2one("product.template", readonly=True, copy=False)

    _external_source_unique = models.Constraint(
        "UNIQUE(source_id, external_id)",
        "The external product identifier must be unique for each data source.",
    )

    @api.depends("image_url")
    def _compute_image_preview(self):
        for record in self:
            url = html.escape(record.image_url or "", quote=True)
            record.image_preview = (
                f'<img src="{url}" alt="产品主图" style="width:300px;height:300px;max-width:100%;object-fit:contain;border-radius:6px"/>'
                if url else ""
            )

    @api.model
    def prepare_ingest_values(self, item, source):
        """Normalize common Shunxi/marketplace field names into candidate values."""
        def first(*keys, default=None):
            for key in keys:
                value = item.get(key)
                if value not in (None, ""):
                    return value
            return default

        def number(value, integer=False):
            try:
                cleaned = str(value or 0).replace(",", "").replace("%", "").strip()
                return int(float(cleaned)) if integer else float(cleaned)
            except (TypeError, ValueError):
                return 0

        name = first("name", "title", "product_title", "产品标题")
        external_url = first("external_url", "url", "product_url", "产品链接")
        external_id = first("external_id", "product_id", "item_id", "产品ID")
        if not external_id and external_url:
            external_id = hashlib.sha256(external_url.encode()).hexdigest()[:32]
        if not name or not external_id:
            return False
        return {
            "name": str(name)[:512],
            "source_id": source.id,
            "company_id": source.company_id.id,
            "external_id": str(external_id)[:128],
            "external_url": external_url,
            "image_url": first("image_url", "image", "main_image", "主图"),
            "original_image_url": first("image_url", "image", "main_image", "主图"),
            "category": first("category", "category_name", "类目"),
            "supplier_name": first("supplier_name", "supplier", "company_name", "供应商"),
            "keyword_text": first("keywords", "keyword_text", "关键词"),
            "supplier_price": number(first("supplier_price", "price", "min_price", "最低价格")),
            "minimum_order_qty": number(first("minimum_order_qty", "moq", "最小起订量")),
            "inquiry_count": number(first("inquiry_count", "inquiries", "询盘数"), integer=True),
            "transaction_count": number(first("transaction_count", "transactions", "交易数"), integer=True),
            "heat_score": number(first("heat_score", "heat", "热度")),
            "sales_7d": number(first("sales_7d", "seven_day_sales", "近7天销量"), integer=True),
            "sales_30d": number(first("sales_30d", "thirty_day_sales", "近30天销量"), integer=True),
            "sales_180d": number(first("sales_180d", "half_year_sales", "近半年销量"), integer=True),
            "displayed_sales": number(first("displayed_sales", "sold", "已售"), integer=True),
            "sales_amount": number(first("sales_amount", "gmv", "销售金额")),
            "price_text": first("price_text", "display_price", "页面价格"),
            "repeat_purchase_rate": number(first("repeat_purchase_rate", "repurchase_rate", "复购率")),
            "supplier_rating": number(first("supplier_rating", "rating", "供应商评分")),
            "review_count": number(first("review_count", "reviews", "评价数"), integer=True),
            "search_rank": number(first("search_rank", "rank", "排名"), integer=True),
            "source_payload": item,
            "data_date": fields.Date.context_today(self),
        }

    @api.model
    def _group_expand_stage(self, stages, domain):
        return [key for key, _label in self._fields["stage"].selection]

    @api.model_create_multi
    def create(self, values_list):
        sequence = self.env["ir.sequence"]
        for values in values_list:
            if values.get("reference", _("新建")) == _("新建"):
                values["reference"] = sequence.next_by_code(
                    "product.intelligence.candidate"
                ) or _("新建")
        records = super().create(values_list)
        records._store_images_if_enabled()
        return records

    def _store_images_if_enabled(self):
        storage = self.env["product.image.storage.oss"]
        if not storage._config()["enabled"]:
            return
        for record in self:
            source_url = record.original_image_url or record.image_url
            if not source_url or record.oss_object_key:
                continue
            try:
                key, public_url = storage.store_url(source_url, record.external_id or str(record.id))
                record.with_context(skip_oss_storage=True).write({
                    "image_url": public_url,
                    "oss_object_key": key,
                    "image_storage_state": "stored",
                    "image_storage_error": False,
                })
            except Exception as exc:
                _logger.exception("OSS image upload failed for candidate %s", record.id)
                record.with_context(skip_oss_storage=True).write({
                    "image_storage_state": "failed", "image_storage_error": str(exc)[:512],
                })

    def action_store_image_oss(self):
        self._store_images_if_enabled()
        return {"type": "ir.actions.client", "tag": "reload"}

    def unlink(self):
        storage = self.env["product.image.storage.oss"]
        config = storage._config()
        keys = list(filter(None, self.mapped("oss_object_key"))) if config["delete_on_unlink"] else []
        result = super().unlink()
        for key in keys:
            try:
                storage.delete_object(key)
            except Exception:
                _logger.exception("Unable to delete OSS object %s", key)
        return result

    @api.depends("supplier_price", "target_sale_price", "logistics_cost", "other_cost")
    def _compute_estimated_margin(self):
        for record in self:
            if record.target_sale_price:
                cost = record.supplier_price + record.logistics_cost + record.other_cost
                record.estimated_margin_percent = (
                    (record.target_sale_price - cost) / record.target_sale_price * 100.0
                )
            else:
                record.estimated_margin_percent = 0.0

    @api.depends(
        "demand_score",
        "growth_score",
        "margin_score",
        "competition_score",
        "logistics_score",
        "compliance_score",
        "content_score",
        "company_id",
    )
    def _compute_total_score(self):
        for record in self:
            company = record.company_id
            record.total_score = (
                record.demand_score * company.pi_weight_demand
                + record.growth_score * company.pi_weight_growth
                + record.margin_score * company.pi_weight_margin
                + record.competition_score * company.pi_weight_competition
                + record.logistics_score * company.pi_weight_logistics
                + record.compliance_score * company.pi_weight_compliance
                + record.content_score * company.pi_weight_content
            ) / 100.0

    @api.depends("total_score", "company_id")
    def _compute_recommendation(self):
        for record in self:
            if record.total_score >= record.company_id.pi_approval_threshold:
                record.recommendation = "approve"
            elif record.total_score >= record.company_id.pi_review_threshold:
                record.recommendation = "review"
            else:
                record.recommendation = "reject"

    @api.constrains(
        "demand_score",
        "growth_score",
        "margin_score",
        "competition_score",
        "logistics_score",
        "compliance_score",
        "content_score",
    )
    def _check_score_range(self):
        score_fields = [
            "demand_score",
            "growth_score",
            "margin_score",
            "competition_score",
            "logistics_score",
            "compliance_score",
            "content_score",
        ]
        for record in self:
            if any(not 0.0 <= record[field_name] <= 100.0 for field_name in score_fields):
                raise ValidationError(_("每项评分必须在 0 到 100 之间。"))

    def action_orient(self):
        self.write({"stage": "orient"})

    def action_submit_review(self):
        self.write({"stage": "review"})

    def action_approve(self):
        self.write({"stage": "approved", "rejection_reason": False})

    def action_reject(self):
        self.write({"stage": "rejected"})

    def action_create_product(self):
        self.ensure_one()
        if self.stage != "approved":
            raise UserError(_("创建 Odoo 产品前，请先批准该候选产品。"))
        if self.product_tmpl_id:
            self.product_tmpl_id.write(self._prepare_product_values(self.product_tmpl_id))
            self._sync_standard_product_attributes(self.product_tmpl_id)
            return self.action_open_product()
        product = self.env["product.template"].create(self._prepare_product_values())
        self._sync_standard_product_attributes(product)
        source_image = self.image_url or self.original_image_url
        if source_image:
            try:
                image_data, _content_type = self.env["product.image.storage.oss"].download_image(source_image)
                product.write({"image_1920": base64.b64encode(image_data)})
            except Exception as exc:
                _logger.exception("Unable to download candidate image for product %s", product.id)
                self.message_post(body=_("正式产品已创建，但主图下载失败：%s") % str(exc)[:512])
        self.write({"product_tmpl_id": product.id, "stage": "executed"})
        return self.action_open_product()

    def _prepare_ecommerce_description(self, existing_description=None):
        self.ensure_one()
        start_marker = "<!-- product-intelligence-details:start -->"
        end_marker = "<!-- product-intelligence-details:end -->"
        existing = existing_description or ""
        marker_pattern = re.compile(
            re.escape(start_marker) + ".*?" + re.escape(end_marker),
            flags=re.DOTALL,
        )
        existing = marker_pattern.sub("", existing).strip()
        sections = [
            ("核心行业属性", self.core_industry_attributes),
            ("重要属性", self.important_attributes),
            ("包装信息", self.packaging_information),
            ("发货及交货时间", self.shipping_information),
        ]
        cards = []
        for title, content in sections:
            rows = []
            for raw_line in (content or "").splitlines():
                line = raw_line.strip().lstrip("-•").strip()
                if not line:
                    continue
                parts = re.split(r"\s*[:：]\s*", line, maxsplit=1)
                if len(parts) == 2 and parts[0] and parts[1]:
                    rows.append(
                        '<div class="d-flex flex-column flex-sm-row gap-1 gap-sm-3 py-2 border-bottom">'
                        f'<strong class="text-body-emphasis" style="min-width: 9rem;">{html.escape(parts[0].strip())}</strong>'
                        f'<span class="text-break">{html.escape(parts[1].strip())}</span></div>'
                    )
                else:
                    rows.append(f'<div class="py-2 border-bottom text-break">{html.escape(line)}</div>')
            if rows:
                cards.append(
                    '<div class="col-12 col-lg-6">'
                    '<section class="card h-100 border-0 shadow-sm">'
                    f'<div class="card-header bg-light"><h3 class="h5 mb-0">{html.escape(title)}</h3></div>'
                    f'<div class="card-body py-1">{"".join(rows)}</div>'
                    '</section></div>'
                )
        managed_block = ""
        if cards:
            managed_block = (
                f'{start_marker}<section class="product-intelligence-details my-4">'
                '<h2 class="h3 mb-3">产品规格与交付信息</h2>'
                f'<div class="row g-3">{"".join(cards)}</div>'
                f'</section>{end_marker}'
            )
        return "\n".join(part for part in (existing, managed_block) if part)

    def _prepare_translation_source_text(self):
        """Build plain product-detail text for Odoo's native translated field."""
        self.ensure_one()
        sections = [
            (_("核心行业属性"), self.core_industry_attributes),
            (_("重要属性"), self.important_attributes),
            (_("包装信息"), self.packaging_information),
            (_("发货及交货时间"), self.shipping_information),
        ]
        blocks = []
        for title, content in sections:
            lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
            if lines:
                blocks.append("%s\n%s" % (title, "\n".join(lines)))
        return "\n\n".join(blocks)

    @api.model
    def _parse_standard_attribute_lines(self, section, content):
        result = []
        for raw_line in (content or "").splitlines():
            line = raw_line.strip().lstrip("-•").strip()
            if not line:
                continue
            parts = re.split(r"\s*[:：]\s*", line, maxsplit=1)
            if len(parts) == 2 and parts[0] and parts[1]:
                result.append((f"{section} · {parts[0].strip()}", parts[1].strip()))
            else:
                result.append((section, line))
        return result

    def _standard_attribute_pairs(self):
        self.ensure_one()
        pairs = [
            ("来源概览 · 数据来源", self.source_id.display_name),
            ("来源概览 · 供应商", self.supplier_name),
            ("来源概览 · 产品分类", self.category),
            ("来源概览 · 产品链接", self.external_url),
        ]
        pairs += self._parse_standard_attribute_lines("核心属性", self.core_industry_attributes)
        pairs += self._parse_standard_attribute_lines("重要属性", self.important_attributes)
        pairs += self._parse_standard_attribute_lines("包装信息", self.packaging_information)
        pairs += self._parse_standard_attribute_lines("发货信息", self.shipping_information)
        return [(name, value) for name, value in pairs if name and value]

    def _sync_standard_product_attributes(self, product):
        self.ensure_one()
        # Details are presented in the standard eCommerce description. Remove
        # attributes created by the previous representation to keep the page tidy.
        managed_lines = product.attribute_line_ids.filtered("attribute_id.pi_managed")
        managed_lines.unlink()
        return True

    def _prepare_product_values(self, product=None):
        self.ensure_one()
        return {
            "name": self.name,
            "default_code": self.reference,
            "standard_price": self.supplier_price,
            "list_price": self.target_sale_price,
            "sale_ok": True,
            "purchase_ok": True,
            "company_id": self.company_id.id,
            "description_sale": self.description,
            "description_ecommerce": self._prepare_ecommerce_description(
                product.description_ecommerce if product else None
            ),
            "pi_candidate_id": self.id,
            "pi_source_name": self.source_id.display_name,
            "pi_external_url": self.external_url,
            "pi_supplier_name": self.supplier_name,
            "pi_source_category": self.category,
            "pi_core_industry_attributes": self.core_industry_attributes,
            "pi_important_attributes": self.important_attributes,
            "pi_packaging_information": self.packaging_information,
            "pi_shipping_information": self.shipping_information,
            "pi_detail_updated_at": fields.Datetime.now(),
        }

    def action_sync_product_details(self):
        candidates = self.filtered("product_tmpl_id")
        if not candidates:
            raise UserError(_("请先将产品机会创建为 Odoo 产品。"))
        for candidate in candidates:
            candidate.product_tmpl_id.write(
                candidate._prepare_product_values(candidate.product_tmpl_id)
            )
            candidate._sync_standard_product_attributes(candidate.product_tmpl_id)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("产品详情同步完成"),
                "message": _("已将 %(count)s 个产品机会的最新详情同步到 Odoo 产品。")
                % {"count": len(candidates)},
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_product(self):
        self.ensure_one()
        if not self.product_tmpl_id:
            raise UserError(_("尚未创建 Odoo 产品。"))
        return {
            "type": "ir.actions.act_window",
            "name": self.product_tmpl_id.display_name,
            "res_model": "product.template",
            "view_mode": "form",
            "res_id": self.product_tmpl_id.id,
        }

    def action_bulk_delete(self):
        if not self.env.user.has_group("product_intelligence_hub.group_product_intelligence_manager"):
            raise UserError(_("只有产品智能管理员可以批量删除候选产品。"))
        self.unlink()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_queue_detail_enrichment(self):
        candidates = self.filtered(lambda record: record.external_url)
        candidates.write({"detail_state": "queued", "detail_error": False})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("详情补充队列"),
                "message": _("已将 %(count)s 个产品加入详情补充队列，请在 Alibaba 页面打开选品情报助手执行。") % {"count": len(candidates)},
                "type": "success",
                "sticky": False,
            },
        }
