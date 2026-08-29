# -*- coding: utf-8 -*-

from types import SimpleNamespace
from unittest.mock import patch

from odoo import Command
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.bus.models import ir_websocket as bus_ir_websocket
from odoo.addons.mail.models.discuss import mail_guest as mail_guest_model

from ..models import chat_translation_notification_router


@tagged('post_install', '-at_install')
class TestPrivateChatNotifications(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.lang']._activate_lang('fr_FR')
        cls.env['res.lang']._activate_lang('de_DE')

        cls.author = cls.env['res.partner'].create({
            'name': 'Chat author',
            'lang': 'fr_FR',
        })
        cls.recipient_fr_user = new_test_user(
            cls.env,
            context={'no_reset_password': True},
            login='odootranslate_french_member',
            name='French member',
        )
        cls.recipient_fr = cls.recipient_fr_user.partner_id
        cls.recipient_fr.lang = 'fr_FR'
        cls.recipient_de = cls.env['res.partner'].create({
            'name': 'German member',
            'lang': 'de_DE',
        })
        cls.outsider_fr = cls.env['res.partner'].create({
            'name': 'French outsider',
            'lang': 'fr_FR',
        })
        cls.guest_fr = cls.env['mail.guest'].create({
            'name': 'French guest',
            'lang': 'fr_FR',
        })
        cls.channel = cls._create_channel(
            cls.author,
            cls.recipient_fr,
            cls.recipient_de,
            cls.guest_fr,
        )
        cls.message = cls.env['mail.message'].sudo().create({
            'author_id': cls.author.id,
            'body': 'Private source message',
            'message_type': 'comment',
            'model': 'discuss.channel',
            'res_id': cls.channel.id,
        })

    @classmethod
    def _create_channel(cls, *identities):
        member_commands = []
        for identity in identities:
            field_name = 'guest_id' if identity._name == 'mail.guest' else 'partner_id'
            member_commands.append(Command.create({field_name: identity.id}))

        return cls.env['discuss.channel'].with_context(install_mode=True).create({
            'channel_member_ids': member_commands,
            'channel_type': 'group',
            'group_public_id': False,
            'name': 'Private translated chat',
        })

    def _create_translation(self, **overrides):
        values = {
            'field_name': 'body',
            'is_author_view': False,
            'lang': 'fr_FR',
            'model_name': 'mail.message',
            'res_id': self.message.id,
            'source': 'Private source message',
            'value': 'Message traduit prive',
        }
        values.update(overrides)

        return self.env['dynamic.translation'].create(values)

    @staticmethod
    def _rendered_logs(logger_mock):
        return '\n'.join(
            call.args[0] % tuple(call.args[1:])
            for call in logger_mock.call_args_list
        )

    def test_recipient_view_targets_only_current_members_with_matching_language(self):
        router_class = chat_translation_notification_router.ChatTranslationNotificationRouter

        with patch.object(router_class, '_send_notification', autospec=True) as send:
            self._create_translation()

        targets = {
            (
                (call.args[1].partner_id or call.args[1].guest_id)._name,
                (call.args[1].partner_id or call.args[1].guest_id).id,
            )
            for call in send.call_args_list
        }

        self.assertEqual(targets, {
            ('mail.guest', self.guest_fr.id),
            ('res.partner', self.recipient_fr.id),
        })
        self.assertNotIn(('res.partner', self.author.id), targets)
        self.assertNotIn(('res.partner', self.recipient_de.id), targets)
        self.assertNotIn(('res.partner', self.outsider_fr.id), targets)

    def test_author_view_targets_only_the_declared_author(self):
        router_class = chat_translation_notification_router.ChatTranslationNotificationRouter

        with patch.object(router_class, '_send_notification', autospec=True) as send:
            self._create_translation(
                author_partner_id=self.author.id,
                is_author_view=True,
                lang='fr_FR',
                value='Original with translated variants',
            )

        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1], self.author)

    def test_author_view_is_skipped_when_the_author_language_changed(self):
        router_class = chat_translation_notification_router.ChatTranslationNotificationRouter

        with (
            patch.object(router_class, '_send_notification', autospec=True) as send,
            patch.object(chat_translation_notification_router._logger, 'warning') as warning,
        ):
            translation = self._create_translation(
                author_partner_id=self.author.id,
                is_author_view=True,
                lang='en_US',
                value='Stale author language view',
            )

        send.assert_not_called()
        self.assertTrue(translation.exists())
        warning_text = self._rendered_logs(warning)
        self.assertIn('reason=author_language_changed', warning_text)
        self.assertNotIn('Stale author language view', warning_text)

    def test_author_view_rejects_spoofed_author_metadata(self):
        router_class = chat_translation_notification_router.ChatTranslationNotificationRouter

        with (
            patch.object(router_class, '_send_notification', autospec=True) as send,
            patch.object(chat_translation_notification_router._logger, 'warning') as warning,
        ):
            translation = self._create_translation(
                author_partner_id=self.outsider_fr.id,
                is_author_view=True,
                lang='fr_FR',
                value='Spoofed private author view',
            )

        send.assert_not_called()
        self.assertTrue(translation.exists())
        warning_text = self._rendered_logs(warning)
        self.assertIn('reason=author_identity_mismatch', warning_text)
        self.assertNotIn('Spoofed private author view', warning_text)

    def test_author_view_requires_current_channel_membership(self):
        author = self.env['res.partner'].create({
            'name': 'Former channel author',
            'lang': 'fr_FR',
        })
        channel = self._create_channel(author, self.recipient_fr)
        message = self.env['mail.message'].sudo().create({
            'author_id': author.id,
            'body': 'Former member source',
            'message_type': 'comment',
            'model': 'discuss.channel',
            'res_id': channel.id,
        })
        channel.channel_member_ids.filtered(
            lambda member: member.partner_id == author
        ).unlink()
        router_class = chat_translation_notification_router.ChatTranslationNotificationRouter

        with (
            patch.object(router_class, '_send_notification', autospec=True) as send,
            patch.object(chat_translation_notification_router._logger, 'warning') as warning,
        ):
            translation = self._create_translation(
                author_partner_id=author.id,
                is_author_view=True,
                lang='fr_FR',
                res_id=message.id,
                value='Former member private view',
            )

        send.assert_not_called()
        self.assertTrue(translation.exists())
        warning_text = self._rendered_logs(warning)
        self.assertIn('reason=author_not_current_member', warning_text)
        self.assertNotIn('Former member private view', warning_text)

    def test_author_guest_view_targets_only_the_declared_guest(self):
        author_guest = self.env['mail.guest'].create({
            'name': 'Guest author',
            'lang': 'fr_FR',
        })
        channel = self._create_channel(author_guest, self.recipient_fr)
        message = self.env['mail.message'].sudo().create({
            'author_guest_id': author_guest.id,
            'body': 'Guest private source',
            'message_type': 'comment',
            'model': 'discuss.channel',
            'res_id': channel.id,
        })
        router_class = chat_translation_notification_router.ChatTranslationNotificationRouter

        with patch.object(router_class, '_send_notification', autospec=True) as send:
            self._create_translation(
                lang='fr_FR',
                res_id=message.id,
                value='Guest recipient view',
            )

        self.assertEqual(send.call_count, 1)
        recipient_member = send.call_args.args[1]
        self.assertEqual(recipient_member.partner_id, self.recipient_fr)
        self.assertFalse(recipient_member.guest_id)

        with patch.object(router_class, '_send_notification', autospec=True) as send:
            self._create_translation(
                author_guest_id=author_guest.id,
                is_author_view=True,
                lang='fr_FR',
                res_id=message.id,
                value='Guest original with translated variants',
            )

        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1], author_guest)

    def test_member_without_language_is_skipped_without_fallback(self):
        guest_without_lang = self.env['mail.guest'].create({
            'name': 'Guest without language',
            'lang': False,
        })
        channel = self._create_channel(self.author, guest_without_lang)
        message = self.env['mail.message'].sudo().create({
            'author_id': self.author.id,
            'body': 'Source without recipient language',
            'message_type': 'comment',
            'model': 'discuss.channel',
            'res_id': channel.id,
        })
        router_class = chat_translation_notification_router.ChatTranslationNotificationRouter

        with (
            patch.object(router_class, '_send_notification', autospec=True) as send,
            patch.object(chat_translation_notification_router._logger, 'warning') as warning,
        ):
            translation = self._create_translation(
                res_id=message.id,
                value='Must not be logged or sent',
            )

        send.assert_not_called()
        warning_text = self._rendered_logs(warning)
        self.assertIn('reason=missing_recipient_language', warning_text)
        self.assertIn(str(translation.id), warning_text)
        self.assertNotIn('Must not be logged or sent', warning_text)

    def test_non_discuss_message_is_persisted_without_recipient_push(self):
        message = self.env['mail.message'].sudo().create({
            'author_id': self.author.id,
            'body': 'Helpdesk source',
            'message_type': 'comment',
            'model': 'res.partner',
            'res_id': self.recipient_fr.id,
        })
        router_class = chat_translation_notification_router.ChatTranslationNotificationRouter

        with (
            patch.object(router_class, '_send_notification', autospec=True) as send,
            patch.object(chat_translation_notification_router._logger, 'warning') as warning,
        ):
            translation = self._create_translation(
                res_id=message.id,
                value='Persisted helpdesk translation',
            )

        send.assert_not_called()
        self.assertTrue(translation.exists())
        warning_text = self._rendered_logs(warning)
        self.assertIn('reason=unsupported_message_scope', warning_text)
        self.assertIn(str(translation.id), warning_text)
        self.assertNotIn('Persisted helpdesk translation', warning_text)

    def test_non_discuss_author_view_is_persisted_without_private_push(self):
        message = self.env['mail.message'].sudo().create({
            'author_id': self.author.id,
            'body': 'Helpdesk author source',
            'message_type': 'comment',
            'model': 'res.partner',
            'res_id': self.recipient_fr.id,
        })
        router_class = chat_translation_notification_router.ChatTranslationNotificationRouter

        with (
            patch.object(router_class, '_send_notification', autospec=True) as send,
            patch.object(chat_translation_notification_router._logger, 'warning') as warning,
        ):
            translation = self._create_translation(
                author_partner_id=self.author.id,
                is_author_view=True,
                res_id=message.id,
                value='Persisted helpdesk author view',
            )

        send.assert_not_called()
        self.assertTrue(translation.exists())
        warning_text = self._rendered_logs(warning)
        self.assertIn('reason=unsupported_message_scope', warning_text)
        self.assertNotIn('Persisted helpdesk author view', warning_text)

    def test_unsupported_message_field_is_persisted_without_store_push(self):
        router_class = chat_translation_notification_router.ChatTranslationNotificationRouter

        with (
            patch.object(router_class, '_send_notification', autospec=True) as send,
            patch.object(chat_translation_notification_router._logger, 'warning') as warning,
        ):
            translation = self._create_translation(
                field_name='subject',
                value='Must not become an arbitrary store property',
            )

        send.assert_not_called()
        self.assertTrue(translation.exists())
        warning_text = self._rendered_logs(warning)
        self.assertIn('reason=unsupported_message_field', warning_text)
        self.assertNotIn('Must not become an arbitrary store property', warning_text)

    def test_notification_failure_does_not_rollback_translation_and_is_logged(self):
        recipient = self.env['res.partner'].create({
            'name': 'Only French recipient',
            'lang': 'fr_FR',
        })
        channel = self._create_channel(self.author, recipient)
        message = self.env['mail.message'].sudo().create({
            'author_id': self.author.id,
            'body': 'Failure source',
            'message_type': 'comment',
            'model': 'discuss.channel',
            'res_id': channel.id,
        })
        router_class = chat_translation_notification_router.ChatTranslationNotificationRouter

        with (
            patch.object(
                router_class,
                '_send_notification',
                autospec=True,
                side_effect=RuntimeError('simulated bus failure'),
            ),
            patch.object(chat_translation_notification_router._logger, 'error') as error,
        ):
            translation = self._create_translation(
                res_id=message.id,
                value='Persisted despite notification failure',
            )

        self.assertTrue(translation.exists())
        self.assertEqual(
            self.env['dynamic.translation'].search_count([('id', '=', translation.id)]),
            1,
        )
        error.assert_called_once()
        error_text = self._rendered_logs(error)
        self.assertIn('event=chat_translation_notification_failed', error_text)
        self.assertIn('error_type=RuntimeError', error_text)
        self.assertNotIn('simulated bus failure', error_text)
        self.assertNotIn('Persisted despite notification failure', error_text)

    def test_author_sender_uses_native_private_identity_channel(self):
        router = self.env['odoo_translate.chat.notification.router']
        payload = {'mail.message': [{'id': self.message.id, 'body': 'Translated'}]}

        with patch.object(type(self.recipient_fr), '_bus_send', autospec=True) as bus_send:
            queued = router._send_notification(self.recipient_fr, payload)

        self.assertTrue(queued)
        bus_send.assert_called_once_with(
            self.recipient_fr,
            'mail.record/insert',
            payload,
        )

    def test_recipient_sender_uses_native_private_member_channels(self):
        router = self.env['odoo_translate.chat.notification.router']
        payload = {'mail.message': [{'id': self.message.id, 'body': 'Translated'}]}
        partner_member = self.channel.channel_member_ids.filtered(
            lambda member: member.partner_id == self.recipient_fr
        )
        guest_member = self.channel.channel_member_ids.filtered(
            lambda member: member.guest_id == self.guest_fr
        )

        with patch.object(type(partner_member), '_bus_send', autospec=True) as bus_send:
            partner_queued = router._send_notification(partner_member, payload)
            guest_queued = router._send_notification(guest_member, payload)

        self.assertTrue(partner_queued)
        self.assertTrue(guest_queued)
        self.assertEqual(bus_send.call_count, 2)
        bus_send.assert_any_call(
            partner_member,
            'mail.record/insert',
            payload,
        )
        bus_send.assert_any_call(
            guest_member,
            'mail.record/insert',
            payload,
        )

    def test_unroutable_member_is_skipped_without_bus_write(self):
        router = self.env['odoo_translate.chat.notification.router']
        payload = {'mail.message': [{'id': self.message.id, 'body': 'Translated'}]}
        partner_member = self.channel.channel_member_ids.filtered(
            lambda member: member.partner_id == self.recipient_fr
        )
        empty_channel = self.env['res.partner']

        with (
            patch.object(
                type(partner_member),
                '_bus_channel',
                autospec=True,
                return_value=empty_channel,
            ),
            patch.object(type(partner_member), '_bus_send', autospec=True) as bus_send,
        ):
            queued = router._send_notification(partner_member, payload)

        self.assertFalse(queued)
        bus_send.assert_not_called()

    def test_websocket_has_no_global_translation_language_channel(self):
        fake_request = SimpleNamespace(
            cookies={},
            env=self.env,
            session=SimpleNamespace(uid=self.env.uid),
        )

        with (
            patch.object(bus_ir_websocket, 'request', fake_request),
            patch.object(mail_guest_model, 'request', fake_request),
        ):
            channels = self.env['ir.websocket']._build_bus_channel_list([])

        global_translation_channels = [
            channel
            for channel in channels
            if isinstance(channel, str) and channel.startswith('odoo_translate_')
        ]
        self.assertEqual(global_translation_channels, [])
