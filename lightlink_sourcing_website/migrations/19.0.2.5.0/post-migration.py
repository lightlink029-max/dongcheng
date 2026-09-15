from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    websites = env["website"].search([])
    websites.filtered(lambda website: not website.ll_business_type).write({
        "ll_business_type": "general",
    })
    sourcing_website = env.ref(
        "lightlink_sourcing_website.website_global_sourcing",
        raise_if_not_found=False,
    )
    if sourcing_website:
        sourcing_website.write({
            "ll_business_type": "sourcing_agency",
            "sourcing_enabled": True,
        })
