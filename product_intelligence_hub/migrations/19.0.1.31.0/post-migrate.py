from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Apply the unified website details layout to existing sourced products."""
    env = api.Environment(cr, SUPERUSER_ID, {"lang": "zh_CN"})
    candidates = env["product.intelligence.candidate"].search([
        ("product_tmpl_id", "!=", False),
    ])
    for candidate in candidates:
        product = candidate.product_tmpl_id.with_context(lang="zh_CN")
        description = candidate.with_context(lang="zh_CN")._prepare_ecommerce_description(
            product.description_ecommerce
        )
        product.write({"description_ecommerce": description})
