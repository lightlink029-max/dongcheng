# -*- coding: utf-8 -*-
"""
Override mail.mail to block immediate sending for translation.

When a mail.mail is created:
1. We set scheduled_date = now + 5 minutes to prevent immediate sending
2. A webhook is triggered to translate the mail via OdooTranslate
3. After translation, OdooTranslate releases the mail explicitly
4. The Odoo cron (process_email_queue) sends the mail

After five minutes, a still-pending mail is released with its original content.
That product fail-open is persisted and logged explicitly; the deadline is never
silently extended by a retry.

IMPORTANT: The native send() method does NOT respect scheduled_date.
Only process_email_queue() (cron) checks it. We must override send() to enforce it.
"""
import hashlib
import logging
from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools import email_split

from .auth_mail_policy import (
    AUTH_TRANSACTIONAL_REASON,
    is_auth_transactional_context,
)
from .rule_identity import MAIL_AUTOMATION_RULE_KEY

_logger = logging.getLogger(__name__)

# Delay between queue checks while a mail is waiting for translation.
TRANSLATION_WAIT_MINUTES = 5
RELEASE_REASON_TRANSLATED = 'translated'
RELEASE_REASON_DEADLINE_EXCEEDED = 'deadline_exceeded'
RELEASE_REASON_AUTH_TRANSACTIONAL = 'auth_transactional'
GATE_FAILURE_CLOSED = 'mail_translation_gate_closed'
GATE_FAILURE_DEADLINE_EXCEEDED = 'mail_translation_deadline_exceeded'
GATE_FAILURE_NOT_FOUND = 'mail_not_found'
GATE_FAILURE_INVALID_PAYLOAD = 'mail_translation_payload_invalid'
GATE_FAILURE_WRITE_NOT_CONFIRMED = 'mail_translation_write_not_confirmed'
GATE_FAILURE_ATTEMPT_CONFLICT = 'mail_translation_attempt_conflict'
GATE_FAILURE_SOURCE_CHANGED = 'mail_translation_source_changed'
GATE_FAILURE_RECIPIENT_LANGUAGE_UNRESOLVED = (
    'mail_recipient_language_unresolved'
)
GATE_FAILURE_RECIPIENT_LANGUAGES_AMBIGUOUS = (
    'mail_recipient_languages_ambiguous'
)
GATE_FAILURE_RECIPIENT_TRANSLATION_MISSING = (
    'mail_recipient_translation_missing'
)
GATE_FAILURE_RELEASE_NOT_CONFIRMED = 'mail_release_not_confirmed'
GATE_FAILURE_SEND_NOT_CONFIRMED = 'mail_send_not_confirmed'
TRANSLATION_OPERATION_NATIVE_WRITE = 'native_write'
TRANSLATION_OPERATION_NATIVE_TERMS = 'native_terms'
TRANSLATION_OPERATION_DYNAMIC_UPSERT = 'dynamic_upsert'
TRANSLATABLE_MAIL_FIELDS = ('subject', 'body_html')


def backfill_pending_mail_translation_sources(env):
    """Preserve source payloads for Store mails already waiting at upgrade."""
    pending_mails = env['mail.mail'].sudo().search([
        ('needs_translation', '=', True),
        '|',
        ('translation_source_subject', '=', False),
        ('translation_source_body_html', '=', False),
    ])
    defaulted_language_count = 0

    for mail in pending_mails:
        source_language = False
        if mail.mail_message_id and mail.mail_message_id.author_id:
            source_language = mail.mail_message_id.author_id.lang

        if not source_language and mail.email_from:
            sender_emails = email_split(mail.email_from)
            if sender_emails:
                sender_partner = env['res.partner'].sudo().search([
                    ('email', '=ilike', sender_emails[0]),
                ], limit=1)
                source_language = sender_partner.lang if sender_partner else False

        if not source_language:
            source_language = 'en_US'
            defaulted_language_count += 1

        source_mail = mail.with_context(lang=source_language)
        mail.with_context(skip_ai_translation=True).write({
            'translation_source_subject': source_mail.subject or False,
            'translation_source_body_html': source_mail.body_html or False,
        })

    if pending_mails:
        _logger.warning(
            '[OdooTranslate] event=mail_translation_source_backfill_completed '
            'pending_mail_count=%s defaulted_language_count=%s',
            len(pending_mails),
            defaulted_language_count,
        )


def backfill_pending_mail_translation_deadlines(env):
    """Persist the existing deadline only for mails still waiting at upgrade."""
    env.cr.execute(
        """
        UPDATE mail_mail
           SET translation_deadline_at = scheduled_date
         WHERE needs_translation IS TRUE
           AND translation_deadline_at IS NULL
           AND scheduled_date IS NOT NULL
        """
    )

    if env.cr.rowcount:
        _logger.warning(
            '[OdooTranslate] event=mail_translation_deadline_backfill_completed '
            'pending_mail_count=%s',
            env.cr.rowcount,
        )


class MailMail(models.Model):
    _inherit = 'mail.mail'

    # Flag to track if this mail needs translation
    needs_translation = fields.Boolean(
        string='Needs Translation',
        default=False,
        help='True if this mail is waiting for translation before sending'
    )

    translation_release_reason = fields.Selection(
        selection=[
            (RELEASE_REASON_TRANSLATED, 'Translated'),
            (RELEASE_REASON_DEADLINE_EXCEEDED, 'Translation deadline exceeded'),
            (RELEASE_REASON_AUTH_TRANSACTIONAL, 'Authentication transaction'),
        ],
        string='Translation Release Reason',
        copy=False,
        readonly=True,
        index=True,
        help='Why the OdooTranslate delivery gate was released',
    )

    translation_released_at = fields.Datetime(
        string='Translation Released At',
        copy=False,
        readonly=True,
        help='When the OdooTranslate delivery gate was released',
    )

    translation_deadline_at = fields.Datetime(
        string='Translation Deadline At',
        copy=False,
        readonly=True,
        index=True,
        help='Immutable OdooTranslate delivery deadline fixed at mail creation',
    )

    translation_source_subject = fields.Text(
        string='Translation Source Subject',
        copy=False,
        readonly=True,
        help='Original subject preserved for the five-minute fail-open',
    )

    translation_source_body_html = fields.Text(
        string='Translation Source Body',
        copy=False,
        readonly=True,
        help='Original body preserved for the five-minute fail-open',
    )

    translation_attempt_id = fields.Char(
        string='Translation Attempt ID',
        copy=False,
        readonly=True,
        index=True,
        help='Stable OdooTranslate request identity holding the mail translation gate',
    )

    translation_source_lang = fields.Char(
        string='Translation Source Language',
        copy=False,
        readonly=True,
        help='Source language revalidated before the translated release',
    )

    translation_required_fields = fields.Json(
        string='Translation Required Fields',
        copy=False,
        readonly=True,
        help='Mail fields whose recipient translations gate every send retry',
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to block immediate sending for mails that need translation.

        Sets scheduled_date = now + 5 minutes so the mail won't be sent immediately.
        The webhook will notify OdooTranslate, which will translate and then release the mail
        by setting scheduled_date = False.
        """
        for vals in vals_list:
            vals.pop('translation_deadline_at', None)
            # Check if this mail should be translated
            # Skip system mails, mails already scheduled, or mails with skip flag
            should_translate = self._should_translate_mail(vals)
            _logger.info(
                '[OdooTranslate] create() translation gate evaluated: should_translate=%s',
                should_translate,
            )
            
            if should_translate:
                source_subject, source_body_html = self._translation_source_values(vals)
                # Block immediate sending by setting scheduled_date
                delay = timedelta(minutes=TRANSLATION_WAIT_MINUTES)
                translation_deadline = fields.Datetime.now() + delay
                vals['scheduled_date'] = translation_deadline
                vals['translation_deadline_at'] = translation_deadline
                vals['needs_translation'] = True
                vals['translation_source_subject'] = source_subject or False
                vals['translation_source_body_html'] = source_body_html or False
                # CRITICAL: Disable auto_delete so the mail isn't deleted before being sent
                vals['auto_delete'] = False
                _logger.info('[OdooTranslate] create() - BLOCKING mail: scheduled_date=%s, needs_translation=True, auto_delete=False',
                             vals['scheduled_date'])

        records = super().create(vals_list)
        _logger.info('[OdooTranslate] create() - Created mail IDs: %s', records.ids)
        
        return records

    def write(self, vals):
        """Keep the delivery deadline immutable after record creation."""
        if 'translation_deadline_at' in vals:
            requested_deadline = (
                fields.Datetime.to_datetime(vals['translation_deadline_at'])
                if vals['translation_deadline_at']
                else False
            )
            if any(
                mail.translation_deadline_at != requested_deadline
                for mail in self
            ):
                raise ValidationError(
                    'The OdooTranslate mail translation deadline is immutable.'
                )

            vals = dict(vals)
            vals.pop('translation_deadline_at')

        return super().write(vals)

    def _should_translate_mail(self, vals):
        """
        Determine if a mail should be translated based on various criteria.
        
        Returns False for:
        - Mails with skip_ai_translation in context
        - Mails already scheduled (scheduled_date already set)
        - Mails without body_html (nothing to translate)
        - No OdooTranslate automation rule configured for mail.mail
        """
        if is_auth_transactional_context(self.env.context):
            _logger.info(
                '[OdooTranslate] mail translation gate skipped: reason=%s',
                AUTH_TRANSACTIONAL_REASON,
            )

            return False

        # Check context flags
        if self.env.context.get('skip_ai_translation'):
            return False

        # Already scheduled - don't interfere
        if vals.get('scheduled_date'):
            return False

        subject, body_html = self._translation_source_values(vals)

        # No body to translate - check both vals and linked mail_message
        if not body_html and not subject:
            return False

        # Check if OdooTranslate is configured for mail.mail.
        if 'base.automation' not in self.env:
            return False

        automation = self.env['base.automation'].sudo().search([
            ('odootranslate_managed', '=', True),
            ('odootranslate_rule_key', '=', MAIL_AUTOMATION_RULE_KEY),
            ('model_id.model', '=', 'mail.mail'),
            ('active', '=', True)
        ], limit=1)
        if not automation:
            return False

        return True

    def _translation_source_values(self, vals):
        """Resolve the exact rendered source stored before translation writes."""
        body_html = vals.get('body_html', '')
        subject = vals.get('subject', '')

        mail_message_id = vals.get('mail_message_id')
        if mail_message_id and (not subject or not body_html):
            mail_message = self.env['mail.message'].sudo().browse(mail_message_id)
            if mail_message.exists():
                if not subject:
                    subject = mail_message.subject or ''
                if not body_html:
                    body_html = mail_message.body or ''

        return subject, body_html

    def send(self, auto_commit=False, raise_exception=False, **kwargs):
        """
        Override send() to:
        1. Respect scheduled_date (block mails waiting for translation)
        2. Inject translation from dynamic.translation into body_content at send time
        
        CRITICAL: The native send() method ignores scheduled_date!
        Only process_email_queue() (cron) checks it.
        
        Auth reset/signup/invitation mails are identified by an explicit context
        marker because Odoo always rolls back the savepoint containing their
        transient ``mail.mail`` row. ``raise_exception`` and ``auto_delete`` are
        not reliable classifiers for this flow.

        For mails NOT needing translation (needs_translation=False), send immediately.
        For mails needing translation but not ready, block them.
        """
        _logger.info('[OdooTranslate] send() called for mail IDs: %s, raise_exception=%s', self.ids, raise_exception)
        
        if is_auth_transactional_context(self.env.context):
            _logger.info(
                '[OdooTranslate] send() bypassing AI translation: reason=%s '
                'mail_count=%s',
                AUTH_TRANSACTIONAL_REASON,
                len(self),
            )
            auth_mails = self.filtered(lambda mail: mail.needs_translation)
            if auth_mails:
                auth_mails._lock_translation_delivery()
                auth_mails.write({
                    'needs_translation': False,
                    'scheduled_date': False,
                    'translation_release_reason': RELEASE_REASON_AUTH_TRANSACTIONAL,
                    'translation_released_at': fields.Datetime.now(),
                })

            return super(MailMail, self).send(
                auto_commit=auto_commit,
                raise_exception=raise_exception,
                **kwargs
            )
        
        self._lock_translation_delivery()

        mails_already_sent = self.filtered(lambda mail: mail.state == 'sent')
        mails_to_process = self - mails_already_sent

        # Mails that don't need translation should be sent immediately.
        mails_not_needing_translation = mails_to_process.filtered(
            lambda mail: not mail.needs_translation
        )
        
        mails_needing_translation = mails_to_process - mails_not_needing_translation
        now = fields.Datetime.now()
        mails_released_untranslated = mails_needing_translation.filtered(
            lambda mail: not mail._odootranslate_translation_deadline()
            or mail._odootranslate_translation_deadline() <= now
        )
        mails_blocked = mails_needing_translation - mails_released_untranslated
        
        _logger.info('[OdooTranslate] send() - not_needing=%s, needing=%s, ready=%s, blocked=%s',
                     mails_not_needing_translation.ids, mails_needing_translation.ids,
                     mails_released_untranslated.ids, mails_blocked.ids)
        
        # Keep the original deadline stable. A retry must never postpone fallback.
        if mails_blocked:
            mails_blocked.write({'auto_delete': False})
            _logger.info(
                '[OdooTranslate] send() - BLOCKED mails %s pending confirmed translations',
                mails_blocked.ids,
            )

        if mails_released_untranslated:
            mails_released_untranslated._release_untranslated_after_deadline(now)

        mails_to_send = mails_not_needing_translation | mails_released_untranslated
        mails_released_by_deadline = mails_to_send.filtered(
            lambda mail: mail.translation_release_reason
            == RELEASE_REASON_DEADLINE_EXCEEDED
        )
        mails_released_as_translated = mails_not_needing_translation.filtered(
            lambda mail: mail.translation_release_reason
            == RELEASE_REASON_TRANSLATED
        )
        ordinary_mails = mails_not_needing_translation.filtered(
            lambda mail: mail.translation_release_reason
            not in (RELEASE_REASON_DEADLINE_EXCEEDED, RELEASE_REASON_TRANSLATED)
        )

        # Deadline releases always keep the original source, including send retries.
        if mails_to_send:
            for mail in mails_released_by_deadline:
                self._inject_original_source(mail)

            for mail in ordinary_mails:
                self._inject_translation_for_recipient(mail)

            translated_mails_refused = self.browse()
            for mail in mails_released_as_translated:
                if not self._inject_translation_for_recipient(mail):
                    translated_mails_refused |= mail

            mails_to_send -= translated_mails_refused

            if not mails_to_send:
                _logger.warning(
                    '[OdooTranslate] event=translated_mail_send_refused '
                    'reason_code=%s mail_ids=%s mail_count=%s',
                    GATE_FAILURE_RECIPIENT_TRANSLATION_MISSING,
                    translated_mails_refused.ids,
                    len(translated_mails_refused),
                )

                return False
            
            _logger.info('[OdooTranslate] send() - SENDING mails %s', mails_to_send.ids)
            send_result = super(MailMail, mails_to_send).send(
                auto_commit=auto_commit,
                raise_exception=raise_exception,
                **kwargs
            )

            return send_result is True and not translated_mails_refused
        
        _logger.info('[OdooTranslate] send() - NO mails to send, returning True')
        return True

    def _inject_original_source(self, mail):
        """Force the exact pre-translation source into the outgoing payload."""
        mail._update_cache({
            'subject': mail.translation_source_subject or False,
            'body_html': mail.translation_source_body_html or False,
        })

    def _inject_translation_for_recipient(self, mail):
        """
        Inject the translated body_html and subject from dynamic.translation based on recipient's language.
        
        OdooTranslate translates the full body_html and stores it in dynamic.translation.
        At send time, we inject the translated body_html directly.
        """
        if 'dynamic.translation' not in self.env:
            return self._mail_injection_refused(
                mail,
                GATE_FAILURE_RECIPIENT_TRANSLATION_MISSING,
            )

        if mail.translation_release_reason == RELEASE_REASON_TRANSLATED:
            required_fields = self._normalize_required_fields(
                mail.translation_required_fields,
            )
            source_lang = mail.translation_source_lang
            if not required_fields or not self._valid_language_code(source_lang):
                return self._mail_injection_refused(
                    mail,
                    GATE_FAILURE_INVALID_PAYLOAD,
                )

            recipient_lang, failure_code = self._resolve_recipient_language(mail)
            if failure_code:
                return self._mail_injection_refused(mail, failure_code)

            source_values = self._live_translation_source_values(
                mail,
                required_fields,
                source_lang,
            )
            values, failure_code = self._required_recipient_values(
                mail,
                required_fields,
                source_values,
                source_lang,
                recipient_lang,
            )
            if failure_code:
                return self._mail_injection_refused(mail, failure_code)

            if values:
                mail._update_cache(values)

            return True

        recipient_lang = self._get_recipient_lang(mail)
        if not recipient_lang:
            return False

        translations = self.env['dynamic.translation'].sudo().search([
            ('model_name', '=', 'mail.mail'),
            ('field_name', 'in', list(TRANSLATABLE_MAIL_FIELDS)),
            ('res_id', '=', mail.id),
            ('lang', '=', recipient_lang),
            ('is_author_view', '=', False),
        ])
        values = {
            translation.field_name: translation.value
            for translation in translations
            if translation.value
        }
        if values:
            mail._update_cache(values)

        return bool(values)

    def _get_recipient_lang(self, mail):
        """
        Get the language of the mail recipient.
        Checks partner_ids first, then tries to find partner by email.
        """
        recipient_lang, failure_code = self._resolve_recipient_language(mail)

        return recipient_lang if not failure_code else None

    def _resolve_recipient_language(self, mail):
        """Resolve every effective recipient to one language without content."""
        mail.invalidate_recordset(['recipient_ids', 'email_to', 'email_cc'])
        languages_by_address = {}
        unresolved = False

        def add_recipient(address, language):
            normalized_address = address.strip().lower()
            if not normalized_address or not language:
                return False

            languages_by_address.setdefault(normalized_address, set()).add(
                language,
            )

            return True

        linked_partners = mail.recipient_ids.sudo()
        linked_partners.invalidate_recordset(['email', 'lang'])
        for partner in linked_partners:
            addresses = email_split(partner.email or '')
            if not addresses or not partner.lang:
                unresolved = True
                continue

            for address in addresses:
                if not add_recipient(address, partner.lang):
                    unresolved = True

        for field_name in ('email_to', 'email_cc'):
            raw_addresses = mail[field_name] or ''
            addresses = email_split(raw_addresses)
            if raw_addresses.strip() and not addresses:
                unresolved = True

            for address in addresses:
                normalized_address = address.strip().lower()
                if normalized_address in languages_by_address:
                    continue

                partners = self.env['res.partner'].sudo().search([
                    ('email_normalized', '=', normalized_address),
                ])
                partners.invalidate_recordset(['email', 'lang'])
                if not partners or any(
                        not partner.lang for partner in partners):
                    unresolved = True
                    continue

                partner_languages = set(partners.mapped('lang'))

                languages_by_address[normalized_address] = partner_languages

        if unresolved or not languages_by_address:
            return None, GATE_FAILURE_RECIPIENT_LANGUAGE_UNRESOLVED

        recipient_languages = set().union(*languages_by_address.values())
        if len(recipient_languages) != 1:
            return None, GATE_FAILURE_RECIPIENT_LANGUAGES_AMBIGUOUS

        return next(iter(recipient_languages)), False

    def _normalize_required_fields(self, required_fields):
        if not isinstance(required_fields, (list, tuple)):
            return None

        if any(
            not isinstance(field_name, str)
            or field_name not in TRANSLATABLE_MAIL_FIELDS
            for field_name in required_fields
        ):
            return None

        normalized_fields = [
            field_name
            for field_name in TRANSLATABLE_MAIL_FIELDS
            if field_name in required_fields
        ]

        return normalized_fields or None

    def _valid_language_code(self, language):
        return (
            isinstance(language, str)
            and bool(language.strip())
            and len(language) <= 64
        )

    def _source_snapshot_field_name(self, field_name):
        if field_name == 'subject':
            return 'translation_source_subject'
        if field_name == 'body_html':
            return 'translation_source_body_html'

        return None

    def _live_translation_source_values(
            self, mail, required_fields, source_lang):
        source_values = {}
        snapshot_updates = {}
        for field_name in required_fields:
            mail.invalidate_recordset([field_name])
            source_mail = mail.with_context(lang=source_lang)
            source_mail.invalidate_recordset([field_name])
            source_value = str(source_mail[field_name] or '')
            source_values[field_name] = source_value

            snapshot_field = self._source_snapshot_field_name(field_name)
            snapshot_value = str(mail[snapshot_field] or '')
            if snapshot_value != source_value:
                snapshot_updates[snapshot_field] = source_value or False

        if snapshot_updates:
            mail.with_context(
                skip_ai_translation=True,
                tracking_disable=True,
            ).write(snapshot_updates)

        return source_values

    def _required_recipient_values(
            self, mail, required_fields, source_values,
            source_lang, recipient_lang):
        if recipient_lang == source_lang:
            return {
                field_name: source_values[field_name] or False
                for field_name in required_fields
            }, False

        translations = self.env['dynamic.translation'].sudo().search([
            ('model_name', '=', 'mail.mail'),
            ('field_name', 'in', required_fields),
            ('res_id', '=', mail.id),
            ('lang', '=', recipient_lang),
            ('is_author_view', '=', False),
        ])
        translations_by_field = {
            translation.field_name: translation
            for translation in translations
        }
        values = {}
        for field_name in required_fields:
            source_value = source_values[field_name]
            if not source_value:
                values[field_name] = False
                continue

            translation = translations_by_field.get(field_name)
            if not translation or not translation.value:
                return None, GATE_FAILURE_RECIPIENT_TRANSLATION_MISSING
            if str(translation.source or '') != source_value:
                return None, GATE_FAILURE_SOURCE_CHANGED

            values[field_name] = translation.value

        return values, False

    def _mail_injection_refused(self, mail, failure_code):
        _logger.warning(
            '[OdooTranslate] event=translated_mail_send_refused '
            'reason_code=%s mail_ids=%s mail_count=%s',
            failure_code,
            mail.ids,
            len(mail),
        )

        return False

    def release_for_sending(self, attempt_id=False):
        """Acknowledge a release already confirmed by the structured RPC."""
        mails = self.exists()
        if len(mails) != len(self) or not mails:
            return False

        mails._lock_translation_delivery()
        if any(mail.state != 'outgoing' for mail in mails):
            _logger.warning(
                '[OdooTranslate] event=translated_mail_release_refused '
                'reason=gate_closed mail_ids=%s mail_count=%s',
                mails.ids,
                len(mails),
            )

            return False

        valid_attempt_id = (
            isinstance(attempt_id, str)
            and bool(attempt_id)
            and len(attempt_id) <= 128
        )
        attempt_conflicts = mails.filtered(
            lambda mail: not valid_attempt_id
            or not mail.translation_attempt_id
            or mail.translation_attempt_id != attempt_id
        )
        if attempt_conflicts:
            _logger.warning(
                '[OdooTranslate] event=translated_mail_release_refused '
                'reason=attempt_conflict mail_ids=%s mail_count=%s',
                attempt_conflicts.ids,
                len(attempt_conflicts),
            )

            return False

        already_released_as_translated = mails.filtered(
            lambda mail: not mail.needs_translation
            and mail.translation_release_reason == RELEASE_REASON_TRANSLATED
        )
        if already_released_as_translated != mails:
            _logger.warning(
                '[OdooTranslate] event=translated_mail_release_refused '
                'reason=structured_rpc_required mail_ids=%s mail_count=%s',
                mails.ids,
                len(mails),
            )

            return False

        return True

    def odootranslate_check_translation_gate(self, attempt_id):
        """Confirm that translation can still start for exactly one mail."""
        mail = self.exists()
        if len(mail) != 1:
            return {
                'success': False,
                'failure_code': GATE_FAILURE_NOT_FOUND,
                'release_reason': False,
            }

        mail._lock_translation_delivery()
        gate_result = mail._translation_gate_result(
            fields.Datetime.now(),
            attempt_id,
            claim_attempt=False,
        )
        if not gate_result['success']:
            return gate_result

        recipient_lang, failure_code = mail._resolve_recipient_language(mail)
        if failure_code:
            return {
                'success': False,
                'failure_code': failure_code,
                'release_reason': False,
                'recipient_lang': False,
            }

        if not mail.translation_attempt_id:
            mail.write({'translation_attempt_id': attempt_id})

        gate_result['recipient_lang'] = recipient_lang

        return gate_result

    def odootranslate_inspect_translation_deadline(self):
        """Return the redacted deadline proof without mutating gate state."""
        observed_at = fields.Datetime.now()
        mail = self.exists()
        if len(mail) != 1:
            return {
                'contract': 'mail_translation_deadline_v1',
                'gate_state': 'unverifiable',
                'deadline_at': False,
                'observed_at': fields.Datetime.to_string(observed_at),
                'release_reason': False,
                'failure_code': GATE_FAILURE_NOT_FOUND,
            }

        deadline = mail.translation_deadline_at
        release_reason = mail.translation_release_reason or False
        known_release_reasons = (
            RELEASE_REASON_TRANSLATED,
            RELEASE_REASON_DEADLINE_EXCEEDED,
            RELEASE_REASON_AUTH_TRANSACTIONAL,
        )

        if not mail.needs_translation and release_reason in known_release_reasons:
            gate_state = 'released'
            failure_code = False
        elif mail.state != 'outgoing' or not mail.needs_translation:
            gate_state = 'closed'
            failure_code = False
        elif (
            not deadline
            or not mail.scheduled_date
            or mail.scheduled_date != deadline
        ):
            gate_state = 'unverifiable'
            failure_code = 'mail_translation_deadline_unverifiable'
            deadline = False
        elif deadline <= observed_at:
            gate_state = 'expired'
            failure_code = False
        else:
            gate_state = 'open'
            failure_code = False

        return {
            'contract': 'mail_translation_deadline_v1',
            'gate_state': gate_state,
            'deadline_at': (
                fields.Datetime.to_string(deadline) if deadline else False
            ),
            'observed_at': fields.Datetime.to_string(observed_at),
            'release_reason': release_reason,
            'failure_code': failure_code,
        }

    def odootranslate_release_translated_and_send(
            self, attempt_id, required_fields, source_lang):
        """Revalidate, release and immediately send one translated mail."""
        mail = self.exists()
        if len(self.ids) != 1 or len(mail) != 1:
            failure_code = (
                GATE_FAILURE_NOT_FOUND
                if not mail
                else GATE_FAILURE_INVALID_PAYLOAD
            )

            return self._translation_delivery_result(
                failure_code=failure_code,
            )

        mail._lock_translation_delivery()
        mail_state = mail.state
        if mail_state != 'outgoing':
            return mail._translation_delivery_result(
                failure_code=GATE_FAILURE_CLOSED,
                mail_state=mail_state,
            )

        now = fields.Datetime.now()
        if not mail.needs_translation:
            failure_code = (
                GATE_FAILURE_DEADLINE_EXCEEDED
                if mail.translation_release_reason
                == RELEASE_REASON_DEADLINE_EXCEEDED
                else GATE_FAILURE_CLOSED
            )

            return mail._translation_delivery_result(
                failure_code=failure_code,
                mail_state=mail_state,
            )

        deadline = mail._odootranslate_translation_deadline()
        if not deadline or deadline <= now:
            mail._release_untranslated_after_deadline(now)

            return mail._translation_delivery_result(
                failure_code=GATE_FAILURE_DEADLINE_EXCEEDED,
                mail_state=mail_state,
            )

        if (
            not isinstance(attempt_id, str)
            or not attempt_id
            or len(attempt_id) > 128
        ):
            return mail._translation_delivery_result(
                failure_code=GATE_FAILURE_INVALID_PAYLOAD,
                mail_state=mail_state,
            )

        if (
            not mail.translation_attempt_id
            or mail.translation_attempt_id != attempt_id
        ):
            return mail._translation_delivery_result(
                failure_code=GATE_FAILURE_ATTEMPT_CONFLICT,
                mail_state=mail_state,
            )

        normalized_fields = mail._normalize_required_fields(required_fields)
        if (
            not normalized_fields
            or not mail._valid_language_code(source_lang)
        ):
            return mail._translation_delivery_result(
                failure_code=GATE_FAILURE_INVALID_PAYLOAD,
                mail_state=mail_state,
            )

        source_values = mail._live_translation_source_values(
            mail,
            normalized_fields,
            source_lang,
        )
        recipient_lang, failure_code = mail._resolve_recipient_language(mail)
        if failure_code:
            return mail._translation_delivery_result(
                failure_code=failure_code,
                mail_state=mail_state,
            )

        _, failure_code = mail._required_recipient_values(
            mail,
            normalized_fields,
            source_values,
            source_lang,
            recipient_lang,
        )
        if failure_code:
            return mail._translation_delivery_result(
                failure_code=failure_code,
                mail_state=mail_state,
            )

        try:
            with self.env.cr.savepoint():
                release_confirmed = mail.with_context(
                    skip_ai_translation=True,
                    tracking_disable=True,
                ).write({
                    'scheduled_date': False,
                    'needs_translation': False,
                    'translation_release_reason': RELEASE_REASON_TRANSLATED,
                    'translation_released_at': now,
                    'translation_source_lang': source_lang,
                    'translation_required_fields': normalized_fields,
                }) is True
        except Exception as exception:
            _logger.warning(
                '[OdooTranslate] event=translated_mail_release_failed '
                'exception_type=%s mail_ids=%s mail_count=%s',
                type(exception).__name__,
                mail.ids,
                len(mail),
            )
            release_confirmed = False

        if not release_confirmed:
            mail.invalidate_recordset([
                'scheduled_date',
                'needs_translation',
                'translation_release_reason',
                'translation_released_at',
                'translation_source_lang',
                'translation_required_fields',
                'state',
            ])

            return mail._translation_delivery_result(
                failure_code=GATE_FAILURE_RELEASE_NOT_CONFIRMED,
                mail_state=mail.state,
            )

        try:
            with self.env.cr.savepoint():
                send_confirmed = mail.with_context(
                    skip_ai_translation=True,
                    tracking_disable=True,
                ).send() is True
        except Exception as exception:
            _logger.warning(
                '[OdooTranslate] event=translated_mail_send_failed '
                'exception_type=%s mail_ids=%s mail_count=%s',
                type(exception).__name__,
                mail.ids,
                len(mail),
            )
            send_confirmed = False

        mail.invalidate_recordset(['state'])
        if not send_confirmed:
            return mail._translation_delivery_result(
                release_confirmed=True,
                failure_code=GATE_FAILURE_SEND_NOT_CONFIRMED,
                mail_state=mail.state,
            )

        return mail._translation_delivery_result(
            success=True,
            release_confirmed=True,
            send_confirmed=True,
            mail_state=mail.state,
        )

    def _translation_delivery_result(
            self, success=False, release_confirmed=False,
            send_confirmed=False, mail_state=False, failure_code=False):
        return {
            'success': success,
            'release_confirmed': release_confirmed,
            'send_confirmed': send_confirmed,
            'mail_state': mail_state,
            'failure_code': failure_code,
        }

    def odootranslate_apply_translation_if_waiting(
            self, operation, payload, attempt_id):
        """Atomically verify the deadline and apply one translation write."""
        mail = self.exists()
        if len(mail) != 1:
            return {
                'success': False,
                'failure_code': GATE_FAILURE_NOT_FOUND,
                'release_reason': False,
            }

        mail._lock_translation_delivery()
        gate_result = mail._translation_gate_result(
            fields.Datetime.now(),
            attempt_id,
        )
        if not gate_result['success']:
            return gate_result

        if not isinstance(payload, dict):
            return mail._invalid_translation_payload(operation)

        if not mail._translation_payload_is_valid(operation, payload):
            return mail._invalid_translation_payload(operation)

        source_failure_code = mail._translation_source_failure_code(payload)
        if source_failure_code:
            return {
                'success': False,
                'failure_code': source_failure_code,
                'release_reason': False,
                'operation': operation,
            }

        if operation == TRANSLATION_OPERATION_NATIVE_WRITE:
            write_succeeded = mail._apply_native_translation(payload)
        elif operation == TRANSLATION_OPERATION_NATIVE_TERMS:
            write_succeeded = mail._apply_native_term_translations(payload)
        elif operation == TRANSLATION_OPERATION_DYNAMIC_UPSERT:
            write_succeeded = mail._upsert_dynamic_translation(payload)
        else:
            return mail._invalid_translation_payload(operation)

        if not write_succeeded:
            return {
                'success': False,
                'failure_code': GATE_FAILURE_WRITE_NOT_CONFIRMED,
                'release_reason': False,
                'operation': operation,
            }

        return {
            'success': True,
            'failure_code': False,
            'release_reason': False,
            'operation': operation,
        }

    def _translation_gate_result(
            self, now, attempt_id, claim_attempt=True):
        """Return a redacted gate result while the mail row is locked."""
        if self.state != 'outgoing':
            return {
                'success': False,
                'failure_code': GATE_FAILURE_CLOSED,
                'release_reason': self.translation_release_reason or False,
            }

        if not self.needs_translation:
            failure_code = (
                GATE_FAILURE_DEADLINE_EXCEEDED
                if self.translation_release_reason
                == RELEASE_REASON_DEADLINE_EXCEEDED
                else GATE_FAILURE_CLOSED
            )
            return {
                'success': False,
                'failure_code': failure_code,
                'release_reason': self.translation_release_reason or False,
            }

        deadline = self._odootranslate_translation_deadline()
        if not deadline or deadline <= now:
            self._release_untranslated_after_deadline(now)
            return {
                'success': False,
                'failure_code': GATE_FAILURE_DEADLINE_EXCEEDED,
                'release_reason': RELEASE_REASON_DEADLINE_EXCEEDED,
            }

        if not isinstance(attempt_id, str) or not attempt_id or len(attempt_id) > 128:
            return self._invalid_translation_payload(False)

        if (
            self.translation_attempt_id
            and self.translation_attempt_id != attempt_id
        ):
            return {
                'success': False,
                'failure_code': GATE_FAILURE_ATTEMPT_CONFLICT,
                'release_reason': False,
            }

        if claim_attempt and not self.translation_attempt_id:
            self.write({'translation_attempt_id': attempt_id})

        return {
            'success': True,
            'failure_code': False,
            'release_reason': False,
        }

    def _odootranslate_translation_deadline(self):
        """Use the durable deadline, with upgrade-safe legacy fallback."""
        self.ensure_one()

        return (
            self.translation_deadline_at
            or (self.scheduled_date if self.needs_translation else False)
        )

    def _release_untranslated_after_deadline(self, released_at):
        """Persist and report the intentional five-minute fail-open."""
        if not self:
            return

        self.write({
            'needs_translation': False,
            'scheduled_date': False,
            'auto_delete': False,
            'translation_release_reason': RELEASE_REASON_DEADLINE_EXCEEDED,
            'translation_released_at': released_at,
        })
        _logger.warning(
            '[OdooTranslate] event=mail_translation_deadline_exceeded '
            'reason=released_untranslated mail_ids=%s mail_count=%s '
            'wait_minutes=%s',
            self.ids,
            len(self),
            TRANSLATION_WAIT_MINUTES,
        )

    def _apply_native_translation(self, payload):
        field_name = payload.get('field_name')
        language = payload.get('lang')
        value = payload.get('value')

        return self.with_context(
            lang=language,
            skip_ai_translation=True,
            tracking_disable=True,
        ).write({field_name: value}) is True

    def _apply_native_term_translations(self, payload):
        field_name = payload.get('field_name')
        translations = payload.get('translations')

        return self.with_context(
            skip_ai_translation=True,
            tracking_disable=True,
        ).update_field_translations(field_name, translations) is True

    def _upsert_dynamic_translation(self, payload):
        field_name = payload.get('field_name')
        language = payload.get('lang')
        source = payload.get('source')
        value = payload.get('value')
        is_author_view = payload.get('is_author_view', False)

        translation_model = self.env['dynamic.translation']
        domain = [
            ('model_name', '=', 'mail.mail'),
            ('field_name', '=', field_name),
            ('res_id', '=', self.id),
            ('lang', '=', language),
            ('is_author_view', '=', is_author_view),
        ]
        translation = translation_model.search(domain, limit=1)
        values = {
            'source': source,
            'value': value,
            'is_author_view': is_author_view,
        }

        if translation:
            return translation.write(values) is True

        values.update({
            'model_name': 'mail.mail',
            'field_name': field_name,
            'res_id': self.id,
            'lang': language,
        })
        return bool(translation_model.create(values))

    def _translation_payload_is_valid(self, operation, payload):
        field_name = payload.get('field_name')
        source_lang = payload.get('source_lang')
        if (
            not isinstance(field_name, str)
            or field_name not in TRANSLATABLE_MAIL_FIELDS
            or field_name not in self._fields
            or not self._valid_language_code(source_lang)
        ):
            return False

        field = self._fields[field_name]
        if operation == TRANSLATION_OPERATION_NATIVE_WRITE:
            return (
                field.translate is True
                and isinstance(payload.get('lang'), str)
                and isinstance(payload.get('value'), str)
            )

        if operation == TRANSLATION_OPERATION_NATIVE_TERMS:
            translations = payload.get('translations')
            return (
                callable(field.translate)
                and isinstance(translations, dict)
                and bool(translations)
                and all(
                    isinstance(language, str)
                    and isinstance(value, (str, dict))
                    for language, value in translations.items()
                )
            )

        if operation == TRANSLATION_OPERATION_DYNAMIC_UPSERT:
            return (
                isinstance(payload.get('lang'), str)
                and isinstance(payload.get('source'), str)
                and isinstance(payload.get('value'), str)
                and isinstance(payload.get('is_author_view', False), bool)
            )

        return False

    def _translation_source_failure_code(self, payload):
        field_name = payload.get('field_name')
        source_lang = payload.get('source_lang')
        expected_hash = payload.get('expected_source_hash')
        if (
            not isinstance(field_name, str)
            or field_name not in TRANSLATABLE_MAIL_FIELDS
            or not self._valid_language_code(source_lang)
            or not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or any(character not in '0123456789abcdef' for character in expected_hash)
        ):
            return GATE_FAILURE_INVALID_PAYLOAD

        source_value = self._live_translation_source_values(
            self,
            [field_name],
            source_lang,
        )[field_name]

        actual_hash = hashlib.sha256(
            str(source_value).encode('utf-8')
        ).hexdigest()
        if actual_hash != expected_hash:
            return GATE_FAILURE_SOURCE_CHANGED

        payload_source = payload.get('source')
        if (
            payload_source is not None
            and str(payload_source) != str(source_value)
        ):
            return GATE_FAILURE_SOURCE_CHANGED

        return False

    def _invalid_translation_payload(self, operation):
        _logger.warning(
            '[OdooTranslate] event=mail_translation_payload_rejected '
            'mail_ids=%s operation=%s',
            self.ids,
            operation if isinstance(operation, str) else 'invalid',
        )
        return {
            'success': False,
            'failure_code': GATE_FAILURE_INVALID_PAYLOAD,
            'release_reason': False,
            'operation': operation if isinstance(operation, str) else False,
        }

    def _lock_translation_delivery(self):
        """Serialize deadline fallback, translated release and delivery retries."""
        if not self.ids:
            return

        self.env.cr.execute(
            'SELECT id, mail_message_id FROM mail_mail '
            'WHERE id IN %s ORDER BY id FOR UPDATE',
            [tuple(self.ids)],
        )
        message_ids = sorted(
            message_id
            for _, message_id in self.env.cr.fetchall()
            if message_id
        )
        if message_ids:
            self.env.cr.execute(
                'SELECT id FROM mail_message '
                'WHERE id IN %s ORDER BY id FOR UPDATE',
                [tuple(message_ids)],
            )
            self.env['mail.message'].browse(message_ids).invalidate_recordset([
                'subject',
                'body',
            ])

        self.invalidate_recordset([
            'needs_translation',
            'scheduled_date',
            'state',
            'subject',
            'body_html',
            'recipient_ids',
            'email_to',
            'email_cc',
            'translation_release_reason',
            'translation_released_at',
            'translation_attempt_id',
            'translation_source_subject',
            'translation_source_body_html',
            'translation_source_lang',
            'translation_required_fields',
        ])

    def unlink(self):
        """
        Override unlink to protect mails waiting for translation.
        
        Some Odoo code (e.g., action_reset_password) explicitly calls unlink()
        after send(), ignoring auto_delete=False. We must prevent this.
        
        Mails with needs_translation=True should NOT be deleted.
        They will be sent later by the cron after translation.
        """
        _logger.info('[OdooTranslate] unlink() called for mail IDs: %s', self.ids)
        
        # Protect mails waiting for translation
        mails_to_protect = self.filtered(lambda m: m.needs_translation)
        mails_to_delete = self - mails_to_protect
        
        if mails_to_protect:
            _logger.info('[OdooTranslate] unlink() - PROTECTING mails %s (needs_translation=True)', mails_to_protect.ids)
        
        if mails_to_delete:
            _logger.info('[OdooTranslate] unlink() - DELETING mails %s', mails_to_delete.ids)
            return super(MailMail, mails_to_delete).unlink()
        
        # If all mails are protected, don't delete anything
        _logger.info('[OdooTranslate] unlink() - All mails protected, returning True')
        return True
