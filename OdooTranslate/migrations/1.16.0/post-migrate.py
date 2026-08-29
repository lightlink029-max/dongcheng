# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api

from odoo.addons.OdooTranslate.models.mail_mail import (
    backfill_pending_mail_translation_deadlines,
)


def migrate(cr, version):
    """Backfill only mails still waiting on their existing deadline."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    backfill_pending_mail_translation_deadlines(env)
