import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ProductIntelligenceCandidate(models.Model):
    _name = "product.intelligence.candidate"
    _description = "产品机会候选"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "total_score desc, write_date desc"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
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
        group_expand="_group_expand_stage",
    )
    source_id = fields.Many2one(
        "product.intelligence.source", required=True, tracking=True, check_company=True
    )
    external_id = fields.Char(index=True)
    external_url = fields.Char()
    image_url = fields.Char()
    supplier_name = fields.Char(index=True)
    keyword_text = fields.Text()
    inquiry_count = fields.Integer()
    transaction_count = fields.Integer()
    heat_score = fields.Float(string="热度", digits=(16, 2))
    sales_7d = fields.Integer(string="近7天销量")
    sales_30d = fields.Integer(string="近30天销量")
    sales_180d = fields.Integer(string="近半年销量")
    displayed_sales = fields.Integer(string="页面展示销量")
    sales_amount = fields.Monetary(string="销售金额", currency_field="currency_id")
    price_text = fields.Char(string="页面价格")
    repeat_purchase_rate = fields.Float(string="复购率 %", digits=(16, 2))
    supplier_rating = fields.Float(string="供应商评分", digits=(4, 2))
    review_count = fields.Integer(string="评价数")
    search_rank = fields.Integer()
    source_payload = fields.Json(copy=False)
    category = fields.Char(index=True)
    target_country_id = fields.Many2one("res.country")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id
    )
    owner_id = fields.Many2one(
        "res.users", default=lambda self: self.env.user, tracking=True
    )
    data_date = fields.Date(default=fields.Date.context_today)

    supplier_price = fields.Monetary(currency_field="currency_id")
    target_sale_price = fields.Monetary(currency_field="currency_id")
    logistics_cost = fields.Monetary(currency_field="currency_id")
    other_cost = fields.Monetary(currency_field="currency_id")
    estimated_margin_percent = fields.Float(
        compute="_compute_estimated_margin", store=True, digits=(16, 2)
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
        compute="_compute_total_score", store=True, digits=(5, 2), tracking=True
    )
    recommendation = fields.Selection(
        [("reject", "淘汰"), ("review", "复核"), ("approve", "批准")],
        compute="_compute_recommendation",
        store=True,
    )

    description = fields.Html()
    decision_notes = fields.Html()
    rejection_reason = fields.Text()
    product_tmpl_id = fields.Many2one("product.template", readonly=True, copy=False)

    _external_source_unique = models.Constraint(
        "UNIQUE(source_id, external_id)",
        "The external product identifier must be unique for each data source.",
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
        return super().create(values_list)

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
            return self.action_open_product()
        product = self.env["product.template"].create(
            {
                "name": self.name,
                "default_code": self.reference,
                "standard_price": self.supplier_price,
                "list_price": self.target_sale_price,
                "sale_ok": True,
                "purchase_ok": True,
                "company_id": self.company_id.id,
                "description_sale": self.description,
            }
        )
        self.write({"product_tmpl_id": product.id, "stage": "executed"})
        return self.action_open_product()

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
