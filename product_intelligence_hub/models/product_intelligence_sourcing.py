from urllib.parse import quote_from_bytes

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


class ProductIntelligenceSourcingOffer(models.Model):
    _name = "product.intelligence.sourcing.offer"
    _description = "国内货源报价"
    _order = "is_preferred desc, is_backup desc, estimated_margin_percent desc, purchase_price asc, id desc"
    _check_company_auto = True

    candidate_id = fields.Many2one(
        "product.intelligence.candidate", string="产品机会", required=True,
        ondelete="cascade", index=True, check_company=True,
    )
    company_id = fields.Many2one(related="candidate_id.company_id", store=True, index=True)
    platform = fields.Selection([("1688", "1688")], required=True, default="1688", index=True)
    external_id = fields.Char(string="货源商品 ID", required=True, index=True)
    name = fields.Char(string="货源商品", required=True)
    product_url = fields.Char(string="商品链接")
    image_url = fields.Char(string="货源主图")
    image_512 = fields.Image(
        string="主图", max_width=512, max_height=512, attachment=True, copy=False,
    )
    supplier_name = fields.Char(string="供应商", index=True)
    merchant_features = fields.Char(string="商家特色", index=True)
    merchant_join_time = fields.Char(string="商家入驻时间")
    supplier_url = fields.Char(string="供应商主页")
    contact_name = fields.Char(string="联系人")
    contact_phone = fields.Char(string="联系电话")
    contact_details = fields.Text(string="联系方式/备注")
    supplier_location = fields.Char(string="所在地")
    price_text = fields.Char(string="页面价格")
    currency_id = fields.Many2one(
        "res.currency", string="币种", required=True,
        default=lambda self: self.env.ref("base.CNY", raise_if_not_found=False) or self.env.company.currency_id,
    )
    purchase_price = fields.Monetary(string="采购单价", currency_field="currency_id")
    opportunity_price = fields.Monetary(
        string="机会商品价格", currency_field="currency_id",
        related="candidate_id.supplier_price", store=True, readonly=True,
    )
    price_difference = fields.Monetary(
        string="价格优势", currency_field="currency_id",
        compute="_compute_price_comparison", store=True,
        help="机会商品价格减去1688采购价格。正数表示1688价格更低。",
    )
    is_cheaper_than_opportunity = fields.Boolean(
        string="1688价格更低", compute="_compute_price_comparison", store=True, index=True,
    )
    minimum_order_qty = fields.Float(string="最小起订量", default=1.0)
    sales_text = fields.Char(string="销量/成交")
    ai_business_opportunity = fields.Text(string="AI商机识别", copy=False, readonly=True)
    ai_opportunity_snapshot = fields.Text(string="AI商机识别快照", copy=False, readonly=True)
    delivery_days = fields.Integer(string="预计交期（天）")
    domestic_freight = fields.Monetary(string="国内运费/件", currency_field="currency_id")
    estimated_total_cost = fields.Monetary(
        string="预计总成本/件", currency_field="currency_id",
        compute="_compute_profit", store=True,
    )
    estimated_profit = fields.Monetary(
        string="预计利润/件", currency_field="currency_id",
        compute="_compute_profit", store=True,
    )
    estimated_margin_percent = fields.Float(
        string="预计利润率 %", compute="_compute_profit", store=True, digits=(16, 2),
    )
    is_preferred = fields.Boolean(string="主推荐货源", index=True, copy=False)
    is_backup = fields.Boolean(string="备选货源", index=True, copy=False)
    captured_at = fields.Datetime(string="采集时间", default=fields.Datetime.now)
    supplier_partner_id = fields.Many2one("res.partner", string="Odoo 供应商", readonly=True, copy=False)
    supplierinfo_id = fields.Many2one("product.supplierinfo", string="产品供应商价目", readonly=True, copy=False)

    _candidate_platform_external_unique = models.Constraint(
        "UNIQUE(candidate_id, platform, external_id)",
        "同一产品机会下不能重复保存相同货源商品。",
    )

    @api.depends(
        "purchase_price", "domestic_freight", "candidate_id.logistics_cost",
        "candidate_id.other_cost", "candidate_id.target_sale_price",
    )
    def _compute_profit(self):
        for offer in self:
            candidate = offer.candidate_id
            total = (
                offer.purchase_price + offer.domestic_freight
                + candidate.logistics_cost + candidate.other_cost
            )
            sale_price = candidate.target_sale_price
            offer.estimated_total_cost = total
            offer.estimated_profit = sale_price - total if sale_price else 0.0
            offer.estimated_margin_percent = (
                (sale_price - total) / sale_price * 100.0 if sale_price else 0.0
            )

    @api.depends("purchase_price", "candidate_id.supplier_price")
    def _compute_price_comparison(self):
        for offer in self:
            opportunity_price = offer.candidate_id.supplier_price or 0.0
            offer.price_difference = opportunity_price - offer.purchase_price
            offer.is_cheaper_than_opportunity = bool(
                opportunity_price > 0 and offer.purchase_price > 0
                and opportunity_price > offer.purchase_price
            )

    def action_bulk_delete(self):
        self.unlink()
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model
    def _prepare_ai_opportunity_snapshot(self, candidate):
        recommendation = dict(candidate._fields["recommendation"].selection).get(
            candidate.recommendation, candidate.recommendation or "-"
        )
        lines = [
            _("综合评分：%(score).2f", score=candidate.total_score),
            _("系统建议：%(recommendation)s", recommendation=recommendation),
            _("需求：%(value).2f", value=candidate.demand_score),
            _("增长：%(value).2f", value=candidate.growth_score),
            _("利润：%(value).2f", value=candidate.margin_score),
            _("竞争：%(value).2f", value=candidate.competition_score),
            _("物流：%(value).2f", value=candidate.logistics_score),
            _("合规：%(value).2f", value=candidate.compliance_score),
            _("内容：%(value).2f", value=candidate.content_score),
        ]
        brief = html2plaintext(candidate.description or "").strip()
        decision = html2plaintext(candidate.decision_notes or "").strip()
        if brief:
            lines.extend(["", _("产品简报："), brief])
        if decision:
            lines.extend(["", _("决策说明："), decision])
        return "\n".join(lines)

    def action_set_preferred(self):
        self.ensure_one()
        self.candidate_id.sourcing_offer_ids.filtered(
            lambda item: item != self and item.is_preferred
        ).write({"is_preferred": False})
        self.write({"is_preferred": True, "is_backup": False})
        self.candidate_id.preferred_sourcing_offer_id = self.id
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_toggle_backup(self):
        self.ensure_one()
        if self.is_preferred:
            raise UserError(_("主推荐货源不能同时设为备选货源。"))
        self.is_backup = not self.is_backup
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_clear_sourcing_role(self):
        self.ensure_one()
        if self.candidate_id.preferred_sourcing_offer_id == self:
            self.candidate_id.preferred_sourcing_offer_id = False
        self.write({"is_preferred": False, "is_backup": False})
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_open_source(self):
        self.ensure_one()
        if not self.product_url:
            raise UserError(_("该货源没有商品链接。"))
        return {"type": "ir.actions.act_url", "url": self.product_url, "target": "new"}


class ProductIntelligenceSourceInsight(models.Model):
    _name = "product.intelligence.source.insight"
    _description = "产品机会数据源商机记录"
    _order = "captured_at desc, id desc"
    _check_company_auto = True

    candidate_id = fields.Many2one(
        "product.intelligence.candidate", string="产品机会", required=True,
        ondelete="cascade", index=True, check_company=True,
    )
    company_id = fields.Many2one(related="candidate_id.company_id", store=True, index=True)
    source_platform = fields.Char(string="数据源", required=True, index=True)
    external_ref = fields.Char(string="来源记录 ID", required=True, index=True)
    source_product_name = fields.Char(string="关联商品")
    source_url = fields.Char(string="来源链接")
    insight_content = fields.Text(string="AI商机识别", required=True)
    captured_at = fields.Datetime(string="采集时间", default=fields.Datetime.now, required=True)

    _candidate_source_ref_unique = models.Constraint(
        "UNIQUE(candidate_id, source_platform, external_ref)",
        "同一产品机会下不能重复保存相同数据源的商机记录。",
    )


class ProductIntelligenceCandidateSourcing(models.Model):
    _inherit = "product.intelligence.candidate"

    sourcing_keyword = fields.Char(string="1688 检索关键词")
    sourcing_image_url = fields.Char(string="找货参考图片")
    sourcing_offer_ids = fields.One2many(
        "product.intelligence.sourcing.offer", "candidate_id", string="1688 货源报价", copy=False,
    )
    sourcing_offer_count = fields.Integer(string="货源数量", compute="_compute_sourcing_offer_count")
    source_insight_ids = fields.One2many(
        "product.intelligence.source.insight", "candidate_id",
        string="数据源商机记录", copy=False,
    )
    preferred_sourcing_offer_id = fields.Many2one(
        "product.intelligence.sourcing.offer", string="主推荐货源", copy=False,
        domain="[('candidate_id', '=', id)]",
    )

    @api.depends("sourcing_offer_ids")
    def _compute_sourcing_offer_count(self):
        for candidate in self:
            candidate.sourcing_offer_count = len(candidate.sourcing_offer_ids)

    def action_open_1688_search(self):
        self.ensure_one()
        keyword = self.sourcing_keyword or self.keyword_text or self.name
        if not keyword:
            raise UserError(_("请先填写1688检索关键词。"))
        if not self.sourcing_keyword:
            self.sourcing_keyword = keyword
        if not self.sourcing_image_url:
            self.sourcing_image_url = self.image_url or self.original_image_url
        # The desktop 1688 search endpoint still decodes `keywords` as GB18030.
        # Sending the usual UTF-8 query string turns 棕色鞋子 into 妫曡壊闉嬪瓙.
        keyword_query = quote_from_bytes(keyword.encode("gb18030"))
        url = (
            "https://s.1688.com/selloffer/offer_search.htm?keywords=%s"
            "&pih_candidate_id=%s&pih_search_mode=keyword" % (keyword_query, self.id)
        )
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}

    def action_open_1688_image_search(self):
        self.ensure_one()
        image_url = self.sourcing_image_url or self.image_url or self.original_image_url
        if not image_url:
            raise UserError(_("当前产品没有可用于找货的参考图片。"))
        if not self.sourcing_image_url:
            self.sourcing_image_url = image_url
        url = (
            "https://s.1688.com/youyuan/index.htm?tab=imageSearch"
            "&pih_candidate_id=%s&pih_search_mode=image" % self.id
        )
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}

    def action_view_sourcing_offers(self):
        self.ensure_one()
        action = self.env.ref(
            "product_intelligence_hub.action_product_intelligence_sourcing_offer"
        ).read()[0]
        action["domain"] = [("candidate_id", "=", self.id)]
        action["context"] = {"default_candidate_id": self.id}
        return action

    def _selected_sourcing_offers(self):
        self.ensure_one()
        main_offer = self.preferred_sourcing_offer_id
        if not main_offer:
            main_offer = self.sourcing_offer_ids.filtered("is_preferred")[:1]
        backup_offers = self.sourcing_offer_ids.filtered(
            lambda offer: offer.is_backup and offer != main_offer
        )
        return main_offer | backup_offers

    def _sync_selected_supplier(self, product):
        self.ensure_one()
        offers = self._selected_sourcing_offers()
        if not offers:
            return False
        supplierinfos = self.env["product.supplierinfo"]
        for position, offer in enumerate(offers):
            partner = offer.supplier_partner_id
            if not partner:
                domain = [("website", "=", offer.supplier_url)] if offer.supplier_url else []
                if not domain and offer.supplier_name:
                    domain = [("name", "=", offer.supplier_name)]
                partner = self.env["res.partner"].search(domain, limit=1) if domain else False
            partner_values = {
                "name": offer.supplier_name or offer.name,
                "company_type": "company",
                "supplier_rank": 1,
                "website": offer.supplier_url or offer.product_url,
                "phone": offer.contact_phone,
                "comment": _("1688货源商品：%(name)s\n%(url)s\n%(details)s") % {
                    "name": offer.name,
                    "url": offer.product_url or "",
                    "details": offer.contact_details or "",
                },
            }
            if partner:
                partner.write({key: value for key, value in partner_values.items() if value})
            else:
                partner = self.env["res.partner"].create(partner_values)
            supplierinfo = offer.supplierinfo_id
            supplier_values = {
                "partner_id": partner.id,
                "product_tmpl_id": product.id,
                "product_name": offer.name,
                "price": offer.purchase_price,
                "min_qty": offer.minimum_order_qty or 1.0,
                "delay": offer.delivery_days or 1,
                "currency_id": offer.currency_id.id,
                "sequence": 1 if offer.is_preferred else 10 + position,
            }
            if supplierinfo:
                supplierinfo.write(supplier_values)
            else:
                supplierinfo = self.env["product.supplierinfo"].create(supplier_values)
            offer.write({
                "supplier_partner_id": partner.id,
                "supplierinfo_id": supplierinfo.id,
            })
            supplierinfos |= supplierinfo
        return supplierinfos

    def action_create_product(self):
        result = super().action_create_product()
        for candidate in self.filtered("product_tmpl_id"):
            candidate._sync_selected_supplier(candidate.product_tmpl_id)
        return result

    def action_sync_product_details(self):
        result = super().action_sync_product_details()
        for candidate in self.filtered("product_tmpl_id"):
            candidate._sync_selected_supplier(candidate.product_tmpl_id)
        return result
