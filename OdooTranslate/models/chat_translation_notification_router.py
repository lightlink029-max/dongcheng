# -*- coding: utf-8 -*-

import logging

from odoo import models


_logger = logging.getLogger(__name__)


class ChatTranslationNotificationRouter(models.AbstractModel):
    _name = 'odoo_translate.chat.notification.router'
    _description = 'OdooTranslate Private Chat Notification Router'

    def notify(self, translations):
        result = {
            'failed': 0,
            'queued': 0,
            'skipped': 0,
        }

        for translation in translations:
            try:
                translation_result = self._notify_translation(translation)
            except Exception as error:
                _logger.error(
                    '[OdooTranslate] event=chat_translation_notification_failed '
                    'stage=routing translation_id=%s message_id=%s lang=%s '
                    'error_type=%s',
                    translation.id,
                    translation.res_id,
                    translation.lang,
                    type(error).__name__,
                )
                translation_result = {
                    'failed': 1,
                    'queued': 0,
                    'skipped': 0,
                }

            for key in result:
                result[key] += translation_result[key]

        return result

    def _notify_translation(self, translation):
        result = {
            'failed': 0,
            'queued': 0,
            'skipped': 0,
        }
        message = self.env['mail.message'].sudo().browse(translation.res_id).exists()

        if not message:
            self._log_skipped(translation, 'missing_message')
            result['skipped'] += 1
            return result

        if translation.field_name != 'body':
            self._log_skipped(translation, 'unsupported_message_field')
            result['skipped'] += 1
            return result

        if message.model != 'discuss.channel' or not message.res_id:
            self._log_skipped(translation, 'unsupported_message_scope')
            result['skipped'] += 1
            return result

        channel = self.env['discuss.channel'].sudo().browse(message.res_id).exists()
        if not channel:
            self._log_skipped(translation, 'missing_conversation')
            result['skipped'] += 1
            return result

        payload = {
            'mail.message': [{
                'id': message.id,
                translation.field_name: translation.value,
            }],
        }

        if translation.is_author_view:
            targets, skipped_reason = self._author_targets(
                message,
                translation,
                channel,
            )
            if skipped_reason:
                self._log_skipped(translation, skipped_reason)
                result['skipped'] += 1
                return result

            for target in targets:
                if not target.lang:
                    self._log_skipped(
                        translation,
                        'missing_author_language',
                        recipient=target,
                    )
                    result['skipped'] += 1
                    continue

                if target.lang != translation.lang:
                    self._log_skipped(
                        translation,
                        'author_language_changed',
                        recipient=target,
                    )
                    result['skipped'] += 1
                    continue

                self._queue(translation, target, target, payload, result)

            self._log_completed(translation, result)
            return result

        author_keys = self._author_identity_keys(message)
        delivered_keys = set()

        for member in channel.channel_member_ids:
            target = member.partner_id or member.guest_id
            if not target:
                self._log_skipped(
                    translation,
                    'missing_recipient_identity',
                    member_id=member.id,
                )
                result['skipped'] += 1
                continue

            target_key = self._identity_key(target)
            if target_key in author_keys or target_key in delivered_keys:
                continue

            if not target.lang:
                self._log_skipped(
                    translation,
                    'missing_recipient_language',
                    recipient=target,
                )
                result['skipped'] += 1
                continue

            if target.lang != translation.lang:
                continue

            delivered_keys.add(target_key)
            self._queue(translation, member, target, payload, result)

        self._log_completed(translation, result)
        return result

    def _author_targets(self, message, translation, channel):
        targets = self._message_author_identities(message)
        if not targets:
            return [], 'missing_author_identity'

        declared_targets = self._unique_identities((
            translation.author_partner_id,
            translation.author_guest_id,
        ))
        if declared_targets and {
            self._identity_key(target)
            for target in declared_targets
        } != {
            self._identity_key(target)
            for target in targets
        }:
            return [], 'author_identity_mismatch'

        current_member_keys = {
            self._identity_key(identity)
            for member in channel.channel_member_ids
            for identity in (member.partner_id or member.guest_id,)
            if identity
        }
        if any(
            self._identity_key(target) not in current_member_keys
            for target in targets
        ):
            return [], 'author_not_current_member'

        return targets, None

    def _author_identity_keys(self, message):
        return {
            self._identity_key(identity)
            for identity in self._message_author_identities(message)
        }

    def _message_author_identities(self, message):
        if message.author_guest_id:
            return [message.author_guest_id]

        if message.author_id:
            return [message.author_id]

        return []

    def _unique_identities(self, identities):
        targets = []
        seen = set()

        for identity in identities:
            if not identity:
                continue

            identity_key = self._identity_key(identity)
            if identity_key in seen:
                continue

            seen.add(identity_key)
            targets.append(identity)

        return targets

    def _queue(self, translation, bus_target, recipient, payload, result):
        try:
            if self._send_notification(bus_target, payload):
                result['queued'] += 1
            else:
                result['skipped'] += 1
                self._log_skipped(
                    translation,
                    'unroutable_recipient',
                    recipient=recipient,
                )
        except Exception as error:
            result['failed'] += 1
            _logger.error(
                '[OdooTranslate] event=chat_translation_notification_failed '
                'stage=delivery translation_id=%s message_id=%s lang=%s '
                'recipient_model=%s recipient_id=%s error_type=%s',
                translation.id,
                translation.res_id,
                translation.lang,
                recipient._name,
                recipient.id,
                type(error).__name__,
            )

    def _send_notification(self, bus_target, payload):
        if not bus_target._bus_channel():
            return False

        bus_target._bus_send('mail.record/insert', payload)

        return True

    def _identity_key(self, identity):
        return (identity._name, identity.id)

    def _log_skipped(
        self,
        translation,
        reason,
        recipient=None,
        member_id=None,
    ):
        _logger.warning(
            '[OdooTranslate] event=chat_translation_notification_skipped '
            'reason=%s translation_id=%s message_id=%s lang=%s '
            'recipient_model=%s recipient_id=%s member_id=%s',
            reason,
            translation.id,
            translation.res_id,
            translation.lang,
            recipient._name if recipient else None,
            recipient.id if recipient else None,
            member_id,
        )

    def _log_completed(self, translation, result):
        _logger.info(
            '[OdooTranslate] event=chat_translation_notification_completed '
            'translation_id=%s message_id=%s lang=%s queued=%s failed=%s skipped=%s',
            translation.id,
            translation.res_id,
            translation.lang,
            result['queued'],
            result['failed'],
            result['skipped'],
        )
