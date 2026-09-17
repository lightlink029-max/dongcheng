from odoo import SUPERUSER_ID, api

from odoo.addons.lightlink_sourcing_website.models.content_translations import (
    apply_sourcing_translations,
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["website"].initialize_lightlink_sourcing_site()
    env["website"]._cleanup_lightlink_sourcing_bootstrap_menus()
    env["website"].sync_lightlink_sourcing_mirror()
    apply_sourcing_translations(env)
    for xmlid in (
        "menu_ll_sourcing_offerings",
        "menu_ll_sourcing_product_categories",
        "menu_ll_sourcing_assets",
        "menu_ll_sourcing_metrics",
        "menu_ll_sourcing_testimonials",
        "menu_ll_sourcing_payment_methods",
        "menu_ll_sourcing_footer_columns",
        "menu_ll_site_trust",
    ):
        menu = env.ref("lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False)
        if menu:
            menu.unlink()
