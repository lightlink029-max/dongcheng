# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api

from odoo.addons.OdooTranslate.models.rule_identity import (
    migrate_legacy_rules,
)
from odoo.addons.OdooTranslate.models.mail_mail import (
    backfill_pending_mail_translation_sources,
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    migrate_legacy_rules(env)
    backfill_pending_mail_translation_sources(env)
