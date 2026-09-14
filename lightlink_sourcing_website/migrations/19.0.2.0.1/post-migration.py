from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["website"].initialize_lightlink_sourcing_site()
    env["website"]._cleanup_lightlink_sourcing_bootstrap_menus()
