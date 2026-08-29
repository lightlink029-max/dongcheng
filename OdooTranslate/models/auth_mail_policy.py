# -*- coding: utf-8 -*-

AUTH_TRANSACTIONAL_REASON = 'auth_transactional'
SKIP_REASON_CONTEXT_KEY = 'odootranslate_skip_reason'

AUTH_TEMPLATE_XMLIDS = frozenset({
    'auth_signup.set_password_email',
    'auth_signup.portal_set_password_email',
    'auth_signup.mail_template_data_unregistered_users',
    'auth_signup.mail_template_user_signup_account_created',
    'auth_totp_mail.mail_template_totp_invite',
    'auth_totp_mail.mail_template_totp_mail_code',
    'auth_totp_mail_enforce.mail_template_totp_mail_code',
})


def auth_transactional_context():
    return {
        'skip_ai_translation': True,
        SKIP_REASON_CONTEXT_KEY: AUTH_TRANSACTIONAL_REASON,
    }


def is_auth_transactional_context(context):
    return context.get(SKIP_REASON_CONTEXT_KEY) == AUTH_TRANSACTIONAL_REASON
