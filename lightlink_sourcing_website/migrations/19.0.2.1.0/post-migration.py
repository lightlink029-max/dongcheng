from odoo import SUPERUSER_ID, api

from odoo.addons.lightlink_sourcing_website.models.content_translations import (
    apply_sourcing_translations,
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["website"].initialize_lightlink_sourcing_site()
    env["website"]._cleanup_lightlink_sourcing_bootstrap_menus()
    apply_sourcing_translations(env)
