from urllib.parse import quote_plus

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductIntelligenceSourcingOffer(models.Model):
    _name = "product.intelligence.sourcing.offer"
    _description = "国内货源报价"
    _order = "is_preferred desc, estimated_margin_percent desc, purchase_price asc, id desc"
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
    supplier_name = fields.Char(string="供应商", index=True)
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
    minimum_order_qty = fields.Float(string="最小起订量", default=1.0)
    sales_text = fields.Char(string="销量/成交")
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
    is_preferred = fields.Boolean(string="推荐货源", index=True, copy=False)
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

    def action_set_preferred(self):
        self.ensure_one()
        self.candidate_id.sourcing_offer_ids.filtered(
            lambda item: item != self and item.is_preferred
        ).write({"is_preferred": False})
        self.write({"is_preferred": True})
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_open_source(self):
        self.ensure_one()
        if not self.product_url:
            raise UserError(_("该货源没有商品链接。"))
        return {"type": "ir.actions.act_url", "url": self.product_url, "target": "new"}


class ProductIntelligenceCandidateSourcing(models.Model):
    _inherit = "product.intelligence.candidate"

    sourcing_keyword = fields.Char(string="1688 检索关键词")
    sourcing_image_url = fields.Char(string="找货参考图片")
    sourcing_offer_ids = fields.One2many(
        "product.intelligence.sourcing.offer", "candidate_id", string="1688 货源报价", copy=False,
    )
    sourcing_offer_count = fields.Integer(string="货源数量", compute="_compute_sourcing_offer_count")
    preferred_sourcing_offer_id = fields.Many2one(
        "product.intelligence.sourcing.offer", string="推荐货源", copy=False,
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
        url = (
            "https://s.1688.com/selloffer/offer_search.htm?keywords=%s"
            "&pih_candidate_id=%s" % (quote_plus(keyword), self.id)
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

    def _selected_sourcing_offer(self):
        self.ensure_one()
        offer = self.preferred_sourcing_offer_id
        if not offer:
            offer = self.sourcing_offer_ids.filtered("is_preferred")[:1]
        return offer

    def _sync_selected_supplier(self, product):
        self.ensure_one()
        offer = self._selected_sourcing_offer()
        if not offer:
            return False
        partner = offer.supplier_partner_id
        if not partner:
            domain = []
            if offer.supplier_url:
                domain = [("website", "=", offer.supplier_url)]
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
        }
        if supplierinfo:
            supplierinfo.write(supplier_values)
        else:
            supplierinfo = self.env["product.supplierinfo"].create(supplier_values)
        offer.write({
            "supplier_partner_id": partner.id,
            "supplierinfo_id": supplierinfo.id,
            "is_preferred": True,
        })
        self.preferred_sourcing_offer_id = offer.id
        return supplierinfo

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
