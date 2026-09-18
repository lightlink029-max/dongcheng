from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["website"].seed_lightlink_sourcing_legal_pages()
    env["website"].seed_lightlink_sourcing_logo()
