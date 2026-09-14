from odoo import SUPERUSER_ID, api

from odoo.addons.lightlink_sourcing_website.models.content_translations import (
    apply_sourcing_translations,
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    apply_sourcing_translations(env)
