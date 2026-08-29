# -*- coding: utf-8 -*-

import logging

from odoo import models

from .auth_mail_policy import (
    AUTH_TEMPLATE_XMLIDS,
    AUTH_TRANSACTIONAL_REASON,
    auth_transactional_context,
)

_logger = logging.getLogger(__name__)


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    def send_mail_batch(
        self,
        res_ids,
        force_send=False,
        raise_exception=False,
        email_values=None,
        email_layout_xmlid=False,
    ):
        template = self
        template_xmlid = self._odootranslate_auth_template_xmlid()
        if template_xmlid:
            template = self.with_context(**auth_transactional_context())
            _logger.info(
                '[OdooTranslate] auth template excluded from AI translation: '
                'reason=%s template=%s recipient_count=%s',
                AUTH_TRANSACTIONAL_REASON,
                template_xmlid,
                len(res_ids),
            )

        return super(MailTemplate, template).send_mail_batch(
            res_ids,
            force_send=force_send,
            raise_exception=raise_exception,
            email_values=email_values,
            email_layout_xmlid=email_layout_xmlid,
        )

    def _odootranslate_auth_template_xmlid(self):
        self.ensure_one()
        template_xmlid = self.get_external_id().get(self.id)
        if template_xmlid in AUTH_TEMPLATE_XMLIDS:
            return template_xmlid
        return None
