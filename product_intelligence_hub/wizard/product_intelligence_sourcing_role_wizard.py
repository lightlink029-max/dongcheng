from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductIntelligenceSourcingRoleWizard(models.TransientModel):
    _name = "product.intelligence.sourcing.role.wizard"
    _description = "批量设置货源角色"

    offer_ids = fields.Many2many(
        "product.intelligence.sourcing.offer", string="已选货源", required=True,
    )
    main_offer_id = fields.Many2one(
        "product.intelligence.sourcing.offer", string="主货源", required=True,
        domain="[('id', 'in', offer_ids)]",
        help="其余已选货源将自动标记为备选货源。",
    )

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        offer_ids = self.env.context.get("active_ids", [])
        if self.env.context.get("active_model") == "product.intelligence.sourcing.offer" and offer_ids:
            offers = self.env["product.intelligence.sourcing.offer"].browse(offer_ids).exists()
            values["offer_ids"] = [(6, 0, offers.ids)]
            preferred = offers.filtered("is_preferred")[:1]
            values["main_offer_id"] = (preferred or offers[:1]).id
        return values

    def action_apply(self):
        self.ensure_one()
        offers = self.offer_ids.exists()
        if not offers:
            raise UserError(_("请至少选择一条货源。"))
        if self.main_offer_id not in offers:
            raise UserError(_("主货源必须是已选货源之一。"))
        candidates = offers.mapped("candidate_id")
        if len(candidates) != 1:
            raise UserError(_("一次只能设置同一个产品机会下的货源。"))

        candidate = candidates.ensure_one()
        candidate.sourcing_offer_ids.write({"is_preferred": False, "is_backup": False})
        backup_offers = offers - self.main_offer_id
        if backup_offers:
            backup_offers.write({"is_backup": True})
        self.main_offer_id.write({"is_preferred": True, "is_backup": False})
        candidate.preferred_sourcing_offer_id = self.main_offer_id.id

        if candidate.product_tmpl_id:
            candidate._sync_selected_supplier(candidate.product_tmpl_id)
        return {"type": "ir.actions.client", "tag": "reload"}
