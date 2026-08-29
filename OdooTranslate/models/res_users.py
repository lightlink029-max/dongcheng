# -*- coding: utf-8 -*-

import logging

from odoo import models

from .auth_mail_policy import (
    AUTH_TRANSACTIONAL_REASON,
    auth_transactional_context,
)

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _action_reset_password(self, signup_type='reset'):
        """Keep auth mails synchronous because Odoo rolls their savepoint back."""
        _logger.info(
            '[OdooTranslate] auth mail excluded from AI translation: reason=%s '
            'signup_type=%s user_count=%s',
            AUTH_TRANSACTIONAL_REASON,
            signup_type,
            len(self),
        )
        users = self.with_context(**auth_transactional_context())

        return super(ResUsers, users)._action_reset_password(
            signup_type=signup_type,
        )

    def _notify_security_setting_update(
        self,
        subject,
        content,
        mail_values=None,
        **kwargs
    ):
        users = self.with_context(**auth_transactional_context())
        _logger.info(
            '[OdooTranslate] security mail excluded from AI translation: '
            'reason=%s user_count=%s',
            AUTH_TRANSACTIONAL_REASON,
            len(self),
        )
        return super(ResUsers, users)._notify_security_setting_update(
            subject,
            content,
            mail_values=mail_values,
            **kwargs
        )

    def _alert_new_device(self):
        users = self.with_context(**auth_transactional_context())
        parent = super(ResUsers, users)
        if not hasattr(parent, '_alert_new_device'):
            return None
        _logger.info(
            '[OdooTranslate] new-device mail excluded from AI translation: '
            'reason=%s user_count=%s',
            AUTH_TRANSACTIONAL_REASON,
            len(self),
        )
        return parent._alert_new_device()
