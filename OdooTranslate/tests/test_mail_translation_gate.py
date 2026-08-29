# -*- coding: utf-8 -*-

import hashlib
from datetime import timedelta
from unittest.mock import patch

from psycopg2 import errors

from odoo import api, fields, release
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.base.models import ir_actions as base_ir_actions
from odoo.addons.mail.models import mail_mail as base_mail_mail
from odoo.addons.mail.models import mail_template as base_mail_template

from ..models import (
    auth_mail_policy,
    base_automation,
    ir_actions_server,
    mail_mail,
)


@tagged('post_install', '-at_install')
class TestMailTranslationGate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.lang']._activate_lang('fr_FR')
        cls.auth_user = new_test_user(
            cls.env,
            context={'no_reset_password': True},
            login='odootranslate_auth_mail_user',
            name='Auth mail user',
            email='auth-mail-user@example.test',
        )

    def setUp(self):
        super().setUp()
        mail_model_id = self.env['ir.model']._get_id('mail.mail')
        self.webhook_action = self.env['ir.actions.server'].create({
            'name': '[OdooTranslate] Translation - mail.mail - send webhook',
            'model_id': mail_model_id,
            'state': 'webhook',
            'webhook_url': 'https://app.example.test/webhook',
            'odootranslate_managed': True,
            'odootranslate_rule_key': 'webhook:mail.mail',
        })
        self.mail_automation = self.env['base.automation'].create({
            'name': '[OdooTranslate] Auto-Translation - mail.mail',
            'model_id': mail_model_id,
            'trigger': 'on_create',
            'filter_domain': '[["needs_translation","=",True]]',
            'action_server_ids': [(6, 0, self.webhook_action.ids)],
            'active': True,
            'odootranslate_managed': True,
            'odootranslate_rule_key': 'automation:mail.mail',
        })
        self.addCleanup(self.webhook_action.unlink)
        self.addCleanup(self.mail_automation.unlink)
        self.default_recipient = self._create_recipient(
            'recipient@example.com',
        )

    def _create_waiting_mail(self, scheduled_date=None, **overrides):
        values = {
            'subject': 'Source subject',
            'body_html': '<p>Source body</p>',
            'email_to': 'recipient@example.com',
            'needs_translation': True,
            'scheduled_date': scheduled_date or (
                fields.Datetime.now() - timedelta(minutes=1)
            ),
            'translation_source_subject': 'Source subject',
            'translation_source_body_html': '<p>Source body</p>',
            'auto_delete': False,
        }
        values.update(overrides)
        with patch.object(
            base_ir_actions.IrActionsServer,
            '_run_action_webhook',
            autospec=True,
            return_value=None,
        ):
            mail = self.env['mail.mail'].with_context(**{
                'skip_ai_translation': True,
                auth_mail_policy.SKIP_REASON_CONTEXT_KEY:
                    auth_mail_policy.AUTH_TRANSACTIONAL_REASON,
            }).create(values)
        return mail.with_context({})

    def _create_recipient(self, email, lang='fr_FR', name='Mail recipient'):
        return self.env['res.partner'].create({
            'name': name,
            'email': email,
            'lang': lang,
        })

    def _create_dynamic_translation(
            self, mail, field_name, language, source, value):
        return self.env['dynamic.translation'].create({
            'model_name': 'mail.mail',
            'field_name': field_name,
            'res_id': mail.id,
            'lang': language,
            'source': source,
            'value': value,
            'is_author_view': False,
        })

    def _create_committed_waiting_mail(self, subject):
        with self.env.registry.cursor() as cursor:
            env = api.Environment(
                cursor,
                self.env.uid,
                {'skip_ai_translation': True},
            )
            mail = env['mail.mail'].create({
                'subject': subject,
                'body_html': '<p>Concurrent source body</p>',
                'email_to': 'concurrent-recipient@example.test',
                'needs_translation': True,
                'scheduled_date': (
                    fields.Datetime.now() + timedelta(minutes=4)
                ),
                'translation_source_subject': subject,
                'translation_source_body_html': (
                    '<p>Concurrent source body</p>'
                ),
                'auto_delete': False,
            })
            mail_id = mail.id
            cursor.commit()

        return mail_id

    def _delete_committed_mail(self, mail_id):
        with self.env.registry.cursor() as cursor:
            env = api.Environment(
                cursor,
                self.env.uid,
                {'skip_ai_translation': True},
            )
            env['dynamic.translation'].search([
                ('model_name', '=', 'mail.mail'),
                ('res_id', '=', mail_id),
            ]).unlink()
            mail = env['mail.mail'].browse(mail_id)
            if mail.exists():
                mail.write({'needs_translation': False})
                mail.unlink()
            cursor.commit()

    def _create_native_auth_mail(self):
        return self.env['mail.mail'].with_context(**{
            'skip_ai_translation': True,
            auth_mail_policy.SKIP_REASON_CONTEXT_KEY:
                auth_mail_policy.AUTH_TRANSACTIONAL_REASON,
        }).create({
            'subject': 'Native auth subject',
            'body_html': '<p>Native auth body</p>',
            'email_to': 'recipient@example.test',
            'auto_delete': False,
        })

    def test_source_values_complete_each_missing_field_from_mail_message(self):
        message = self.env['mail.message'].create({
            'subject': 'Message subject',
            'body': '<p>Message body</p>',
            'message_type': 'comment',
        })

        subject, body_html = self.env[
            'mail.mail'
        ]._translation_source_values({
            'mail_message_id': message.id,
            'subject': 'Explicit subject',
        })
        fallback_subject, explicit_body = self.env[
            'mail.mail'
        ]._translation_source_values({
            'mail_message_id': message.id,
            'body_html': '<p>Explicit body</p>',
        })

        self.assertEqual('Explicit subject', subject)
        self.assertEqual('<p>Message body</p>', str(body_html))
        self.assertEqual('Message subject', fallback_subject)
        self.assertEqual('<p>Explicit body</p>', explicit_body)

    def test_expired_wait_sends_original_with_an_explicit_release_reason(self):
        mail = self._create_waiting_mail()
        mail.recipient_ids = self.default_recipient
        self.env['dynamic.translation'].create({
            'model_name': 'mail.mail',
            'field_name': 'body_html',
            'res_id': mail.id,
            'lang': 'fr_FR',
            'value': '<p>Corps traduit</p>',
        })
        mail.with_context(lang='fr_FR').write({
            'subject': 'Sujet natif traduit',
            'body_html': '<p>Corps natif traduit</p>',
        })
        french_mail = mail.with_context(lang='fr_FR')

        with self.assertLogs(mail_mail._logger.name, level='WARNING') as logs, \
                patch.object(
                    base_mail_mail.MailMail,
                    'send',
                    autospec=True,
                    return_value=True,
                ) as native_send:
            self.assertTrue(french_mail.send())
            self.assertTrue(french_mail.send())

        self.assertTrue(mail.exists())
        self.assertFalse(mail.needs_translation)
        self.assertFalse(mail.scheduled_date)
        self.assertEqual(
            mail_mail.RELEASE_REASON_DEADLINE_EXCEEDED,
            mail.translation_release_reason,
        )
        self.assertTrue(mail.translation_released_at)
        self.assertEqual(2, native_send.call_count)
        for call in native_send.call_args_list:
            outgoing_mail = call.args[0]
            self.assertEqual('Source subject', outgoing_mail.subject)
            self.assertEqual('<p>Source body</p>', str(outgoing_mail.body_html))
        self.assertIn('reason=released_untranslated', '\n'.join(logs.output))

    def test_waiting_mail_keeps_its_original_deadline_before_timeout(self):
        deadline = fields.Datetime.now() + timedelta(minutes=4)
        mail = self._create_waiting_mail(scheduled_date=deadline)

        with patch.object(
            base_mail_mail.MailMail,
            'send',
            autospec=True,
            return_value=True,
        ) as native_send:
            self.assertTrue(mail.send())

        native_send.assert_not_called()
        self.assertTrue(mail.needs_translation)
        self.assertEqual(deadline, mail.scheduled_date)
        self.assertFalse(mail.translation_release_reason)

    def test_gate_check_releases_an_expired_mail_with_an_explicit_reason(self):
        mail = self._create_waiting_mail()

        result = mail.odootranslate_check_translation_gate('request:gate-check')

        self.assertFalse(result['success'])
        self.assertEqual(
            'mail_translation_deadline_exceeded',
            result['failure_code'],
        )
        self.assertFalse(mail.needs_translation)
        self.assertFalse(mail.scheduled_date)
        self.assertEqual(
            mail_mail.RELEASE_REASON_DEADLINE_EXCEEDED,
            mail.translation_release_reason,
        )
        self.assertTrue(mail.translation_released_at)

    def test_atomic_native_write_refuses_a_non_translatable_mail_field(self):
        deadline = fields.Datetime.now() + timedelta(minutes=4)
        mail = self._create_waiting_mail(scheduled_date=deadline)

        result = mail.odootranslate_apply_translation_if_waiting(
            'native_write',
            {
                'field_name': 'subject',
                'source_lang': 'en_US',
                'lang': 'fr_FR',
                'value': 'Sujet traduit',
                'expected_source_hash': hashlib.sha256(
                    b'Source subject'
                ).hexdigest(),
            },
            'request:native-write',
        )

        self.assertFalse(result['success'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_INVALID_PAYLOAD,
            result['failure_code'],
        )
        self.assertTrue(mail.needs_translation)
        self.assertEqual(deadline, mail.scheduled_date)

    def test_atomic_dynamic_write_is_refused_after_the_deadline(self):
        mail = self._create_waiting_mail()

        result = mail.odootranslate_apply_translation_if_waiting(
            'dynamic_upsert',
            {
                'field_name': 'subject',
                'source_lang': 'en_US',
                'lang': 'fr_FR',
                'source': 'Source subject',
                'value': 'Sujet traduit',
                'is_author_view': False,
            },
            'request:expired-dynamic-write',
        )

        self.assertFalse(result['success'])
        self.assertEqual(
            'mail_translation_deadline_exceeded',
            result['failure_code'],
        )
        self.assertFalse(self.env['dynamic.translation'].search([
            ('model_name', '=', 'mail.mail'),
            ('field_name', '=', 'subject'),
            ('res_id', '=', mail.id),
            ('lang', '=', 'fr_FR'),
        ]))
        self.assertEqual(
            mail_mail.RELEASE_REASON_DEADLINE_EXCEEDED,
            mail.translation_release_reason,
        )

    def test_atomic_dynamic_write_is_applied_only_while_the_gate_is_open(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )

        result = mail.odootranslate_apply_translation_if_waiting(
            'dynamic_upsert',
            {
                'field_name': 'subject',
                'source_lang': 'en_US',
                'lang': 'fr_FR',
                'source': 'Source subject',
                'value': 'Sujet traduit',
                'is_author_view': False,
                'expected_source_hash': hashlib.sha256(
                    b'Source subject'
                ).hexdigest(),
            },
            'request:dynamic-write',
        )

        self.assertTrue(result['success'])
        translation = self.env['dynamic.translation'].search([
            ('model_name', '=', 'mail.mail'),
            ('field_name', '=', 'subject'),
            ('res_id', '=', mail.id),
            ('lang', '=', 'fr_FR'),
            ('is_author_view', '=', False),
        ])
        self.assertEqual('Source subject', translation.source)
        self.assertEqual('Sujet traduit', translation.value)

    def test_atomic_write_requires_a_source_language(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )

        result = mail.odootranslate_apply_translation_if_waiting(
            'dynamic_upsert',
            {
                'field_name': 'subject',
                'lang': 'fr_FR',
                'source': 'Source subject',
                'value': 'Sujet traduit',
                'expected_source_hash': hashlib.sha256(
                    b'Source subject'
                ).hexdigest(),
            },
            'request:missing-source-language',
        )

        self.assertFalse(result['success'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_INVALID_PAYLOAD,
            result['failure_code'],
        )

    def test_atomic_native_terms_refuse_a_non_callable_mail_field(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )

        result = mail.odootranslate_apply_translation_if_waiting(
            'native_terms',
            {
                'field_name': 'body_html',
                'source_lang': 'en_US',
                'translations': {'fr_FR': '<p>Corps traduit</p>'},
                'expected_source_hash': hashlib.sha256(
                    b'<p>Source body</p>'
                ).hexdigest(),
            },
            'request:native-terms',
        )

        self.assertFalse(result['success'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_INVALID_PAYLOAD,
            result['failure_code'],
        )

    def test_atomic_write_reports_an_invalid_operation_payload(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )

        result = mail.odootranslate_apply_translation_if_waiting(
            'native_write',
            {
                'field_name': 'subject',
                'source_lang': 'en_US',
                'lang': 'fr_FR',
                'expected_source_hash': hashlib.sha256(
                    b'Source subject'
                ).hexdigest(),
            },
            'request:invalid-payload',
        )

        self.assertFalse(result['success'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_INVALID_PAYLOAD,
            result['failure_code'],
        )

    def test_upgrade_backfill_preserves_pending_mail_source_and_deadline(self):
        deadline = fields.Datetime.now() + timedelta(minutes=4)
        mail = self._create_waiting_mail(scheduled_date=deadline)
        mail.write({
            'translation_source_subject': False,
            'translation_source_body_html': False,
        })

        mail_mail.backfill_pending_mail_translation_sources(self.env)

        self.assertEqual('Source subject', mail.translation_source_subject)
        self.assertEqual(
            '<p>Source body</p>',
            str(mail.translation_source_body_html),
        )
        self.assertTrue(mail.needs_translation)
        self.assertEqual(deadline, mail.scheduled_date)

    def test_translation_attempt_cannot_be_replaced_while_gate_is_open(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )

        first_result = mail.odootranslate_check_translation_gate('request:first')
        second_result = mail.odootranslate_check_translation_gate('request:second')

        self.assertTrue(first_result['success'])
        self.assertFalse(second_result['success'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_ATTEMPT_CONFLICT,
            second_result['failure_code'],
        )
        self.assertEqual('request:first', mail.translation_attempt_id)
        self.assertFalse(mail.release_for_sending('request:second'))
        self.assertTrue(mail.needs_translation)

    def test_gate_check_returns_the_single_recipient_language(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )

        result = mail.odootranslate_check_translation_gate(
            'request:recipient-language',
        )

        self.assertTrue(result['success'])
        self.assertEqual('fr_FR', result['recipient_lang'])

    def test_gate_check_refuses_an_unknown_recipient_language(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
            email_to='unknown-recipient@example.test',
        )

        result = mail.odootranslate_check_translation_gate(
            'request:unknown-recipient-gate',
        )

        self.assertFalse(result['success'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_RECIPIENT_LANGUAGE_UNRESOLVED,
            result['failure_code'],
        )
        self.assertFalse(result['recipient_lang'])
        self.assertFalse(mail.translation_attempt_id)

    def test_gate_check_refuses_mixed_recipient_languages(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
            email_to=False,
        )
        english_recipient = self._create_recipient(
            'english-recipient@example.test',
            lang='en_US',
        )
        mail.recipient_ids = self.default_recipient | english_recipient

        result = mail.odootranslate_check_translation_gate(
            'request:mixed-recipient-gate',
        )

        self.assertFalse(result['success'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_RECIPIENT_LANGUAGES_AMBIGUOUS,
            result['failure_code'],
        )
        self.assertFalse(result['recipient_lang'])
        self.assertFalse(mail.translation_attempt_id)

    def test_legacy_release_cannot_bypass_the_structured_release_rpc(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        self.assertTrue(
            mail.odootranslate_check_translation_gate(
                'request:legacy-release',
            )['success'],
        )

        result = mail.release_for_sending('request:legacy-release')

        self.assertFalse(result)
        self.assertTrue(mail.needs_translation)
        self.assertFalse(mail.translation_release_reason)

    def test_legacy_release_refuses_a_non_outgoing_mail(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
            translation_attempt_id='request:legacy-non-outgoing',
        )
        mail.state = 'exception'

        result = mail.release_for_sending(
            'request:legacy-non-outgoing',
        )

        self.assertFalse(result)
        self.assertTrue(mail.needs_translation)

    def test_non_outgoing_mail_cannot_claim_the_translation_gate(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        mail.state = 'exception'

        result = mail.odootranslate_check_translation_gate(
            'request:not-outgoing',
        )

        self.assertFalse(result['success'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_CLOSED,
            result['failure_code'],
        )
        self.assertFalse(mail.translation_attempt_id)

    def test_atomic_write_refuses_stale_source_and_refreshes_the_snapshot(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        mail.with_context(lang='en_US').write({'subject': 'Edited subject'})

        result = mail.odootranslate_apply_translation_if_waiting(
            'dynamic_upsert',
            {
                'field_name': 'subject',
                'source_lang': 'en_US',
                'lang': 'fr_FR',
                'source': 'Source subject',
                'value': 'Sujet traduit obsolète',
                'expected_source_hash': hashlib.sha256(
                    b'Source subject'
                ).hexdigest(),
            },
            'request:stale-source',
        )

        self.assertFalse(result['success'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_SOURCE_CHANGED,
            result['failure_code'],
        )
        self.assertEqual('Edited subject', mail.translation_source_subject)
        self.assertNotEqual(
            'Sujet traduit obsolète',
            mail.with_context(lang='fr_FR').subject,
        )

    def test_atomic_write_refreshes_a_stale_snapshot_for_a_fresh_read(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        mail.with_context(lang='en_US').write({'subject': 'Edited subject'})

        result = mail.odootranslate_apply_translation_if_waiting(
            'dynamic_upsert',
            {
                'field_name': 'subject',
                'source_lang': 'en_US',
                'lang': 'fr_FR',
                'source': 'Edited subject',
                'value': 'Sujet traduit à jour',
                'expected_source_hash': hashlib.sha256(
                    b'Edited subject'
                ).hexdigest(),
            },
            'request:fresh-source',
        )

        self.assertTrue(result['success'])
        self.assertEqual('Edited subject', mail.translation_source_subject)
        translation = self.env['dynamic.translation'].search([
            ('model_name', '=', 'mail.mail'),
            ('field_name', '=', 'subject'),
            ('res_id', '=', mail.id),
            ('lang', '=', 'fr_FR'),
        ])
        self.assertEqual('Edited subject', translation.source)

    def test_deadline_transition_and_atomic_write_serialize_across_cursors(self):
        registry = self.env.registry
        mail_id = None
        lock_cursor = None

        try:
            with registry.cursor() as setup_cursor:
                setup_env = api.Environment(
                    setup_cursor,
                    self.env.uid,
                    {'skip_ai_translation': True},
                )
                mail = setup_env['mail.mail'].create({
                    'subject': 'Concurrent source subject',
                    'body_html': '<p>Concurrent source body</p>',
                    'email_to': 'recipient@example.test',
                    'needs_translation': True,
                    'scheduled_date': (
                        fields.Datetime.now() + timedelta(minutes=4)
                    ),
                    'translation_source_subject': 'Concurrent source subject',
                    'translation_source_body_html': (
                        '<p>Concurrent source body</p>'
                    ),
                    'auto_delete': False,
                })
                mail_id = mail.id
                setup_cursor.commit()

            lock_cursor = registry.cursor()
            lock_cursor.execute(
                'SELECT id FROM mail_mail WHERE id = %s FOR UPDATE',
                [mail_id],
            )

            with registry.cursor() as blocked_cursor:
                blocked_cursor.execute("SET LOCAL lock_timeout = '250ms'")
                blocked_env = api.Environment(
                    blocked_cursor,
                    self.env.uid,
                    {'skip_ai_translation': True},
                )
                with self.assertRaises(errors.LockNotAvailable):
                    blocked_env['mail.mail'].browse(
                        mail_id
                    ).odootranslate_apply_translation_if_waiting(
                        'native_write',
                        {
                            'field_name': 'subject',
                            'source_lang': 'en_US',
                            'lang': 'fr_FR',
                            'value': 'Concurrent translated subject',
                            'expected_source_hash': hashlib.sha256(
                                b'Concurrent source subject'
                            ).hexdigest(),
                        },
                        'request:blocked-writer',
                    )
                blocked_cursor.rollback()

            lock_cursor.execute(
                """
                UPDATE mail_mail
                   SET needs_translation = FALSE,
                       scheduled_date = NULL,
                       translation_release_reason = %s,
                       translation_released_at = NOW()
                 WHERE id = %s
                """,
                [mail_mail.RELEASE_REASON_DEADLINE_EXCEEDED, mail_id],
            )
            lock_cursor.commit()

            with registry.cursor() as writer_cursor:
                writer_env = api.Environment(
                    writer_cursor,
                    self.env.uid,
                    {'skip_ai_translation': True},
                )
                writer_result = writer_env['mail.mail'].browse(
                    mail_id
                ).odootranslate_apply_translation_if_waiting(
                    'native_write',
                    {
                        'field_name': 'subject',
                        'source_lang': 'en_US',
                        'lang': 'fr_FR',
                        'value': 'Concurrent translated subject',
                        'expected_source_hash': hashlib.sha256(
                            b'Concurrent source subject'
                        ).hexdigest(),
                    },
                    'request:serialized-writer',
                )
                writer_cursor.commit()

            self.assertFalse(writer_result['success'])
            self.assertEqual(
                mail_mail.GATE_FAILURE_DEADLINE_EXCEEDED,
                writer_result['failure_code'],
            )

            with registry.cursor() as verify_cursor:
                verify_env = api.Environment(
                    verify_cursor,
                    self.env.uid,
                    {'lang': 'fr_FR'},
                )
                verified_mail = verify_env['mail.mail'].browse(mail_id)
                self.assertEqual(
                    'Concurrent source subject',
                    verified_mail.subject,
                )
        finally:
            if lock_cursor is not None:
                lock_cursor.rollback()
                lock_cursor.close()
            if mail_id is not None:
                with registry.cursor() as cleanup_cursor:
                    cleanup_env = api.Environment(
                        cleanup_cursor,
                        self.env.uid,
                        {'skip_ai_translation': True},
                    )
                    cleanup_env['dynamic.translation'].search([
                        ('model_name', '=', 'mail.mail'),
                        ('res_id', '=', mail_id),
                    ]).unlink()
                    cleanup_mail = cleanup_env['mail.mail'].browse(mail_id)
                    if cleanup_mail.exists():
                        cleanup_mail.write({'needs_translation': False})
                        cleanup_mail.unlink()
                    cleanup_cursor.commit()

    def test_gate_lock_invalidates_a_stale_attempt_cache_across_cursors(self):
        registry = self.env.registry
        mail_id = self._create_committed_waiting_mail(
            'Attempt cache source',
        )
        stale_cursor = registry.cursor()

        try:
            stale_cursor.execute(
                'SET TRANSACTION ISOLATION LEVEL READ COMMITTED',
            )
            stale_env = api.Environment(
                stale_cursor,
                self.env.uid,
                {'skip_ai_translation': True},
            )
            stale_mail = stale_env['mail.mail'].browse(mail_id)
            self.assertFalse(stale_mail.translation_attempt_id)

            with registry.cursor() as writer_cursor:
                writer_env = api.Environment(
                    writer_cursor,
                    self.env.uid,
                    {'skip_ai_translation': True},
                )
                writer_env['mail.mail'].browse(mail_id).write({
                    'translation_attempt_id': 'request:fresh-owner',
                })
                writer_cursor.commit()

            result = stale_mail.odootranslate_check_translation_gate(
                'request:stale-owner',
            )

            self.assertFalse(result['success'])
            self.assertEqual(
                mail_mail.GATE_FAILURE_ATTEMPT_CONFLICT,
                result['failure_code'],
            )
            self.assertEqual(
                'request:fresh-owner',
                stale_mail.translation_attempt_id,
            )
        finally:
            stale_cursor.rollback()
            stale_cursor.close()
            self._delete_committed_mail(mail_id)

    def test_atomic_write_invalidates_a_stale_source_cache_across_cursors(self):
        registry = self.env.registry
        original_source = 'Cross-cursor source'
        updated_source = 'Cross-cursor source edited'
        mail_id = self._create_committed_waiting_mail(original_source)
        stale_cursor = registry.cursor()

        try:
            stale_cursor.execute(
                'SET TRANSACTION ISOLATION LEVEL READ COMMITTED',
            )
            stale_env = api.Environment(
                stale_cursor,
                self.env.uid,
                {'skip_ai_translation': True},
            )
            stale_mail = stale_env['mail.mail'].browse(mail_id)
            self.assertEqual(original_source, stale_mail.subject)
            self.assertEqual(
                original_source,
                stale_mail.translation_source_subject,
            )

            with registry.cursor() as writer_cursor:
                writer_env = api.Environment(
                    writer_cursor,
                    self.env.uid,
                    {'skip_ai_translation': True, 'lang': 'en_US'},
                )
                writer_env['mail.mail'].browse(mail_id).write({
                    'subject': updated_source,
                })
                writer_cursor.commit()

            result = stale_mail.odootranslate_apply_translation_if_waiting(
                'dynamic_upsert',
                {
                    'field_name': 'subject',
                    'source_lang': 'en_US',
                    'lang': 'fr_FR',
                    'source': original_source,
                    'value': 'Traduction obsolète',
                    'expected_source_hash': hashlib.sha256(
                        original_source.encode('utf-8')
                    ).hexdigest(),
                },
                'request:stale-source-cache',
            )

            self.assertFalse(result['success'])
            self.assertEqual(
                mail_mail.GATE_FAILURE_SOURCE_CHANGED,
                result['failure_code'],
            )
            self.assertEqual(
                updated_source,
                stale_mail.translation_source_subject,
            )
            stale_cursor.commit()
        finally:
            stale_cursor.rollback()
            stale_cursor.close()
            self._delete_committed_mail(mail_id)

    def test_release_rpc_injects_required_sidecars_and_sends_with_context(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        mail.recipient_ids = self.default_recipient
        gate_result = mail.odootranslate_check_translation_gate(
            'request:release',
        )
        self._create_dynamic_translation(
            mail,
            'subject',
            'fr_FR',
            'Source subject',
            'Sujet traduit',
        )
        self._create_dynamic_translation(
            mail,
            'body_html',
            'fr_FR',
            '<p>Source body</p>',
            '<p>Corps traduit</p>',
        )

        self.assertTrue(gate_result['success'])
        with patch.object(
            base_mail_mail.MailMail,
            'send',
            autospec=True,
            return_value=True,
        ) as native_send:
            result = mail.odootranslate_release_translated_and_send(
                'request:release',
                ['subject', 'body_html'],
                'en_US',
            )

        self.assertEqual({
            'success': True,
            'release_confirmed': True,
            'send_confirmed': True,
            'mail_state': 'outgoing',
            'failure_code': False,
        }, result)
        self.assertFalse(mail.needs_translation)
        self.assertFalse(mail.scheduled_date)
        self.assertEqual(
            mail_mail.RELEASE_REASON_TRANSLATED,
            mail.translation_release_reason,
        )
        self.assertTrue(mail.translation_released_at)
        self.assertEqual('en_US', mail.translation_source_lang)
        self.assertEqual(
            ['subject', 'body_html'],
            mail.translation_required_fields,
        )
        native_send.assert_called_once()
        outgoing_mail = native_send.call_args.args[0]
        self.assertTrue(outgoing_mail.env.context['skip_ai_translation'])
        self.assertEqual('Sujet traduit', outgoing_mail.subject)
        self.assertEqual('<p>Corps traduit</p>', str(outgoing_mail.body_html))

    def test_release_rpc_reports_an_unconfirmed_immediate_send(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        self.default_recipient.lang = 'en_US'
        mail.recipient_ids = self.default_recipient
        self.assertTrue(
            mail.odootranslate_check_translation_gate(
                'request:send-not-confirmed',
            )['success'],
        )

        with patch.object(
            base_mail_mail.MailMail,
            'send',
            autospec=True,
            return_value=False,
        ):
            result = mail.odootranslate_release_translated_and_send(
                'request:send-not-confirmed',
                ['subject', 'body_html'],
                'en_US',
            )

        self.assertEqual({
            'success': False,
            'release_confirmed': True,
            'send_confirmed': False,
            'mail_state': 'outgoing',
            'failure_code': mail_mail.GATE_FAILURE_SEND_NOT_CONFIRMED,
        }, result)
        self.assertFalse(mail.needs_translation)
        self.assertEqual(
            mail_mail.RELEASE_REASON_TRANSLATED,
            mail.translation_release_reason,
        )

    def test_release_rpc_allows_a_same_language_mail_without_sidecars(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        self.default_recipient.lang = 'en_US'
        mail.recipient_ids = self.default_recipient
        self.assertTrue(
            mail.odootranslate_check_translation_gate(
                'request:same-language',
            )['success'],
        )

        with patch.object(
            base_mail_mail.MailMail,
            'send',
            autospec=True,
            return_value=True,
        ):
            result = mail.odootranslate_release_translated_and_send(
                'request:same-language',
                ['subject', 'body_html'],
                'en_US',
            )

        self.assertTrue(result['success'])
        self.assertTrue(result['release_confirmed'])
        self.assertTrue(result['send_confirmed'])

    def test_release_rpc_allows_an_empty_live_required_source(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        mail.recipient_ids = self.default_recipient
        self.assertTrue(
            mail.odootranslate_check_translation_gate(
                'request:empty-live-source',
            )['success'],
        )
        mail.with_context(lang='en_US').write({'subject': False})

        with patch.object(
            base_mail_mail.MailMail,
            'send',
            autospec=True,
            return_value=True,
        ):
            result = mail.odootranslate_release_translated_and_send(
                'request:empty-live-source',
                ['subject'],
                'en_US',
            )

        self.assertTrue(result['success'])
        self.assertTrue(result['release_confirmed'])
        self.assertFalse(mail.translation_source_subject)

    def test_release_rpc_refuses_an_attempt_conflict(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        self.assertTrue(
            mail.odootranslate_check_translation_gate(
                'request:release-owner',
            )['success'],
        )

        result = mail.odootranslate_release_translated_and_send(
            'request:release-other',
            ['subject'],
            'en_US',
        )

        self.assertEqual({
            'success': False,
            'release_confirmed': False,
            'send_confirmed': False,
            'mail_state': 'outgoing',
            'failure_code': mail_mail.GATE_FAILURE_ATTEMPT_CONFLICT,
        }, result)
        self.assertTrue(mail.needs_translation)

    def test_release_rpc_refuses_invalid_required_fields(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        self.assertTrue(
            mail.odootranslate_check_translation_gate(
                'request:invalid-required-fields',
            )['success'],
        )

        result = mail.odootranslate_release_translated_and_send(
            'request:invalid-required-fields',
            ['email_to'],
            'en_US',
        )

        self.assertEqual(
            mail_mail.GATE_FAILURE_INVALID_PAYLOAD,
            result['failure_code'],
        )
        self.assertFalse(result['release_confirmed'])
        self.assertTrue(mail.needs_translation)

    def test_release_rpc_reports_an_unconfirmed_release_write(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        self.default_recipient.lang = 'en_US'
        mail.recipient_ids = self.default_recipient
        self.assertTrue(
            mail.odootranslate_check_translation_gate(
                'request:release-not-confirmed',
            )['success'],
        )

        with patch.object(
            mail_mail.MailMail,
            'write',
            autospec=True,
            return_value=False,
        ):
            result = mail.odootranslate_release_translated_and_send(
                'request:release-not-confirmed',
                ['subject'],
                'en_US',
            )

        self.assertEqual({
            'success': False,
            'release_confirmed': False,
            'send_confirmed': False,
            'mail_state': 'outgoing',
            'failure_code': mail_mail.GATE_FAILURE_RELEASE_NOT_CONFIRMED,
        }, result)
        self.assertTrue(mail.needs_translation)

    def test_release_rpc_persists_the_deadline_fallback_when_too_late(self):
        mail = self._create_waiting_mail(
            translation_attempt_id='request:late-release',
        )

        result = mail.odootranslate_release_translated_and_send(
            'request:late-release',
            ['subject'],
            'en_US',
        )

        self.assertEqual({
            'success': False,
            'release_confirmed': False,
            'send_confirmed': False,
            'mail_state': 'outgoing',
            'failure_code': mail_mail.GATE_FAILURE_DEADLINE_EXCEEDED,
        }, result)
        self.assertFalse(mail.needs_translation)
        self.assertEqual(
            mail_mail.RELEASE_REASON_DEADLINE_EXCEEDED,
            mail.translation_release_reason,
        )

    def test_release_rpc_refuses_an_unknown_recipient_language(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        self.assertTrue(
            mail.odootranslate_check_translation_gate(
                'request:unknown-recipient',
            )['success'],
        )
        mail.write({
            'email_to': 'unknown-recipient@example.test',
            'recipient_ids': [(5, 0, 0)],
        })

        result = mail.odootranslate_release_translated_and_send(
            'request:unknown-recipient',
            ['subject', 'body_html'],
            'en_US',
        )

        self.assertFalse(result['success'])
        self.assertFalse(result['release_confirmed'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_RECIPIENT_LANGUAGE_UNRESOLVED,
            result['failure_code'],
        )
        self.assertTrue(mail.needs_translation)

    def test_release_rpc_refuses_mixed_recipient_languages(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        self.assertTrue(
            mail.odootranslate_check_translation_gate(
                'request:mixed-recipients',
            )['success'],
        )
        french_recipient = self._create_recipient(
            'french-recipient@example.test',
            lang='fr_FR',
            name='French recipient',
        )
        english_recipient = self._create_recipient(
            'english-recipient@example.test',
            lang='en_US',
            name='English recipient',
        )
        mail.write({
            'email_to': False,
            'recipient_ids': [
                (6, 0, (french_recipient | english_recipient).ids),
            ],
        })

        result = mail.odootranslate_release_translated_and_send(
            'request:mixed-recipients',
            ['subject'],
            'en_US',
        )

        self.assertFalse(result['success'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_RECIPIENT_LANGUAGES_AMBIGUOUS,
            result['failure_code'],
        )
        self.assertTrue(mail.needs_translation)

    def test_release_rpc_includes_additional_cc_recipient_languages(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        mail.recipient_ids = self.default_recipient
        self.assertTrue(
            mail.odootranslate_check_translation_gate(
                'request:mixed-cc',
            )['success'],
        )
        self._create_recipient(
            'english-cc@example.test',
            lang='en_US',
            name='English CC recipient',
        )
        mail.email_cc = 'english-cc@example.test'

        result = mail.odootranslate_release_translated_and_send(
            'request:mixed-cc',
            ['subject'],
            'en_US',
        )

        self.assertFalse(result['success'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_RECIPIENT_LANGUAGES_AMBIGUOUS,
            result['failure_code'],
        )
        self.assertTrue(mail.needs_translation)

    def test_release_rpc_refuses_a_missing_required_sidecar(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        mail.recipient_ids = self.default_recipient
        self.assertTrue(
            mail.odootranslate_check_translation_gate(
                'request:missing-sidecar',
            )['success'],
        )

        result = mail.odootranslate_release_translated_and_send(
            'request:missing-sidecar',
            ['subject'],
            'en_US',
        )

        self.assertFalse(result['success'])
        self.assertFalse(result['release_confirmed'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_RECIPIENT_TRANSLATION_MISSING,
            result['failure_code'],
        )
        self.assertTrue(mail.needs_translation)

    def test_release_rpc_refuses_a_sidecar_for_an_obsolete_source(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        mail.recipient_ids = self.default_recipient
        self.assertTrue(
            mail.odootranslate_check_translation_gate(
                'request:obsolete-sidecar',
            )['success'],
        )
        self._create_dynamic_translation(
            mail,
            'subject',
            'fr_FR',
            'Source subject',
            'Sujet traduit',
        )
        mail.with_context(lang='en_US').write({
            'subject': 'Edited source subject',
        })

        result = mail.odootranslate_release_translated_and_send(
            'request:obsolete-sidecar',
            ['subject'],
            'en_US',
        )

        self.assertFalse(result['success'])
        self.assertEqual(
            mail_mail.GATE_FAILURE_SOURCE_CHANGED,
            result['failure_code'],
        )
        self.assertEqual(
            'Edited source subject',
            mail.translation_source_subject,
        )
        self.assertTrue(mail.needs_translation)

    def test_release_rpc_refuses_a_non_outgoing_mail(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        mail.translation_attempt_id = 'request:non-outgoing-release'
        mail.state = 'exception'

        result = mail.odootranslate_release_translated_and_send(
            'request:non-outgoing-release',
            ['subject'],
            'en_US',
        )

        self.assertEqual({
            'success': False,
            'release_confirmed': False,
            'send_confirmed': False,
            'mail_state': 'exception',
            'failure_code': mail_mail.GATE_FAILURE_CLOSED,
        }, result)
        self.assertTrue(mail.needs_translation)

    def test_release_rpc_always_returns_a_structured_missing_mail_result(self):
        result = self.env['mail.mail'].browse(
            2_147_483_647,
        ).odootranslate_release_translated_and_send(
            'request:missing-mail',
            ['subject'],
            'en_US',
        )

        self.assertEqual({
            'success': False,
            'release_confirmed': False,
            'send_confirmed': False,
            'mail_state': False,
            'failure_code': mail_mail.GATE_FAILURE_NOT_FOUND,
        }, result)

    def test_translated_mail_is_not_sent_when_a_required_sidecar_disappears(self):
        mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )
        mail.recipient_ids = self.default_recipient
        mail.write({
            'needs_translation': False,
            'scheduled_date': False,
            'translation_release_reason': mail_mail.RELEASE_REASON_TRANSLATED,
            'translation_released_at': fields.Datetime.now(),
            'translation_source_lang': 'en_US',
            'translation_required_fields': ['subject'],
        })

        with self.assertLogs(
                mail_mail._logger.name,
                level='WARNING') as logs, patch.object(
                    base_mail_mail.MailMail,
                    'send',
                    autospec=True,
                    return_value=True,
                ) as native_send:
            result = mail.send()

        self.assertFalse(result)
        native_send.assert_not_called()
        self.assertEqual('outgoing', mail.state)
        self.assertIn(
            mail_mail.GATE_FAILURE_RECIPIENT_TRANSLATION_MISSING,
            '\n'.join(logs.output),
        )

    def test_late_translation_cannot_overwrite_a_deadline_release(self):
        mail = self._create_waiting_mail()

        with patch.object(
            base_mail_mail.MailMail,
            'send',
            autospec=True,
            return_value=True,
        ):
            self.assertTrue(mail.send())

        self.assertFalse(mail.release_for_sending())
        self.assertEqual(
            mail_mail.RELEASE_REASON_DEADLINE_EXCEEDED,
            mail.translation_release_reason,
        )

    def test_normal_mail_runs_through_real_automation_and_translation_gate(self):
        self.webhook_action.name = 'Renamed mail webhook'
        self.mail_automation.name = 'Renamed mail automation'

        with patch.object(
            base_ir_actions.IrActionsServer,
            '_run_action_webhook',
            autospec=True,
            return_value=None,
        ) as native_webhook:
            mail = self.env['mail.mail'].create({
                'subject': 'Source subject',
                'body_html': '<p>Source body</p>',
                'email_to': 'recipient@example.test',
                'auto_delete': False,
            })

        self.assertTrue(mail.needs_translation)
        self.assertTrue(mail.scheduled_date)
        self.assertEqual(mail.scheduled_date, mail.translation_deadline_at)
        self.assertEqual('Source subject', mail.translation_source_subject)
        self.assertEqual(
            '<p>Source body</p>',
            str(mail.translation_source_body_html),
        )
        native_webhook.assert_called_once()

    def test_translation_deadline_is_immutable_and_survives_release(self):
        with patch.object(
            base_ir_actions.IrActionsServer,
            '_run_action_webhook',
            autospec=True,
            return_value=None,
        ):
            mail = self.env['mail.mail'].create({
                'subject': 'Source subject',
                'body_html': '<p>Source body</p>',
                'email_to': 'recipient@example.test',
                'auto_delete': False,
            })

        deadline = mail.translation_deadline_at
        open_proof = mail.odootranslate_inspect_translation_deadline()
        self.assertEqual({
            'contract',
            'gate_state',
            'deadline_at',
            'observed_at',
            'release_reason',
            'failure_code',
        }, set(open_proof))
        self.assertEqual('open', open_proof['gate_state'])
        self.assertEqual(
            fields.Datetime.to_string(deadline),
            open_proof['deadline_at'],
        )
        self.assertFalse(open_proof['failure_code'])
        with self.assertRaises(ValidationError):
            mail.write({
                'translation_deadline_at': deadline + timedelta(minutes=1),
            })
        with self.assertRaises(ValidationError):
            mail.write({'translation_deadline_at': False})

        mail.write({
            'needs_translation': False,
            'scheduled_date': False,
            'translation_release_reason': mail_mail.RELEASE_REASON_TRANSLATED,
        })

        self.assertEqual(deadline, mail.translation_deadline_at)
        released_proof = mail.odootranslate_inspect_translation_deadline()
        self.assertEqual('released', released_proof['gate_state'])
        self.assertEqual(
            mail_mail.RELEASE_REASON_TRANSLATED,
            released_proof['release_reason'],
        )
        self.assertEqual(
            fields.Datetime.to_string(deadline),
            released_proof['deadline_at'],
        )

    def test_deadline_inspection_distinguishes_expired_and_desynchronized(self):
        with patch.object(
            base_ir_actions.IrActionsServer,
            '_run_action_webhook',
            autospec=True,
            return_value=None,
        ):
            mail = self.env['mail.mail'].create({
                'subject': 'Source subject',
                'body_html': '<p>Source body</p>',
                'email_to': 'recipient@example.test',
                'auto_delete': False,
            })

        expired_at = fields.Datetime.now() - timedelta(seconds=1)
        self.env.cr.execute(
            """
            UPDATE mail_mail
               SET translation_deadline_at = %s, scheduled_date = %s
             WHERE id = %s
            """,
            [expired_at, expired_at, mail.id],
        )
        mail.invalidate_recordset([
            'translation_deadline_at',
            'scheduled_date',
        ])
        expired = mail.odootranslate_inspect_translation_deadline()
        self.assertEqual('expired', expired['gate_state'])
        self.assertFalse(expired['failure_code'])

        self.env.cr.execute(
            'UPDATE mail_mail SET scheduled_date = %s WHERE id = %s',
            [expired_at + timedelta(minutes=1), mail.id],
        )
        mail.invalidate_recordset(['scheduled_date'])
        unverifiable = mail.odootranslate_inspect_translation_deadline()
        self.assertEqual('unverifiable', unverifiable['gate_state'])
        self.assertFalse(unverifiable['deadline_at'])
        self.assertEqual(
            'mail_translation_deadline_unverifiable',
            unverifiable['failure_code'],
        )

    def test_deadline_inspection_is_redacted_pure_and_fail_closed_for_legacy(self):
        deadline = fields.Datetime.now() + timedelta(minutes=4)
        legacy_mail = self._create_waiting_mail(scheduled_date=deadline)
        before_write_date = legacy_mail.write_date

        result = legacy_mail.odootranslate_inspect_translation_deadline()

        self.assertEqual('mail_translation_deadline_v1', result['contract'])
        self.assertEqual('unverifiable', result['gate_state'])
        self.assertFalse(result['deadline_at'])
        self.assertTrue(result['observed_at'])
        self.assertFalse(result['release_reason'])
        self.assertEqual(
            'mail_translation_deadline_unverifiable',
            result['failure_code'],
        )
        self.assertEqual(before_write_date, legacy_mail.write_date)
        self.assertTrue(legacy_mail.needs_translation)
        self.assertEqual(deadline, legacy_mail.scheduled_date)

        missing = self.env['mail.mail'].browse(
            legacy_mail.id + 1000000
        ).odootranslate_inspect_translation_deadline()
        self.assertEqual('mail_translation_deadline_v1', missing['contract'])
        self.assertEqual('unverifiable', missing['gate_state'])
        self.assertFalse(missing['deadline_at'])
        self.assertTrue(missing['observed_at'])
        self.assertFalse(missing['release_reason'])
        self.assertEqual(mail_mail.GATE_FAILURE_NOT_FOUND, missing['failure_code'])

    def test_auth_context_skips_real_automation_and_translation_gate(self):
        with patch.object(
            base_ir_actions.IrActionsServer,
            '_run_action_webhook',
            autospec=True,
            return_value=None,
        ) as native_webhook:
            mail = self._create_native_auth_mail()

        self.assertFalse(mail.needs_translation)
        self.assertFalse(mail.scheduled_date)
        native_webhook.assert_not_called()

    def test_password_reset_flow_is_sent_as_auth_transactional(self):
        with patch.object(
            base_ir_actions.IrActionsServer,
            '_run_action_webhook',
            autospec=True,
            return_value=None,
        ) as native_webhook, patch.object(
            base_mail_mail.MailMail,
            'send',
            autospec=True,
            return_value=True,
        ) as native_send:
            result = self.auth_user._action_reset_password(signup_type='reset')

        native_send.assert_called_once()
        reset_mail = native_send.call_args.args[0]
        self.assertTrue(reset_mail.env.context['skip_ai_translation'])
        self.assertEqual(
            reset_mail.env.context[auth_mail_policy.SKIP_REASON_CONTEXT_KEY],
            auth_mail_policy.AUTH_TRANSACTIONAL_REASON,
        )
        self.assertFalse(native_send.call_args.kwargs['raise_exception'])
        self.assertEqual(result['type'], 'ir.actions.client')
        native_webhook.assert_not_called()

    def test_signup_invitation_flow_is_sent_as_auth_transactional(self):
        users = self.auth_user.with_context(create_user=True)

        with patch.object(
            base_ir_actions.IrActionsServer,
            '_run_action_webhook',
            autospec=True,
            return_value=None,
        ) as native_webhook, patch.object(
            base_mail_mail.MailMail,
            'send',
            autospec=True,
            return_value=True,
        ) as native_send:
            result = users._action_reset_password(signup_type='signup')

        native_send.assert_called_once()
        invitation_mail = native_send.call_args.args[0]
        self.assertTrue(invitation_mail.env.context['create_user'])
        self.assertTrue(invitation_mail.env.context['skip_ai_translation'])
        self.assertEqual(
            invitation_mail.env.context[
                auth_mail_policy.SKIP_REASON_CONTEXT_KEY
            ],
            auth_mail_policy.AUTH_TRANSACTIONAL_REASON,
        )
        self.assertTrue(native_send.call_args.kwargs['raise_exception'])
        self.assertEqual(result['type'], 'ir.actions.client')
        native_webhook.assert_not_called()

    def test_all_installed_auth_templates_propagate_the_auth_marker(self):
        installed_template_count = 0

        for xmlid in sorted(auth_mail_policy.AUTH_TEMPLATE_XMLIDS):
            template = self.env.ref(xmlid, raise_if_not_found=False)
            if not template or template._name != 'mail.template':
                continue

            installed_template_count += 1
            with self.subTest(xmlid=xmlid), patch.object(
                base_mail_template.MailTemplate,
                'send_mail_batch',
                autospec=True,
                return_value=self.env['mail.mail'],
            ) as native_send_batch:
                template.send_mail_batch([self.auth_user.id])

            classified_template = native_send_batch.call_args.args[0]
            self.assertTrue(
                classified_template.env.context['skip_ai_translation'],
            )
            self.assertEqual(
                classified_template.env.context[
                    auth_mail_policy.SKIP_REASON_CONTEXT_KEY
                ],
                auth_mail_policy.AUTH_TRANSACTIONAL_REASON,
            )

        self.assertGreaterEqual(installed_template_count, 4)

    def test_security_update_mail_does_not_reach_translation_automation(self):
        with patch.object(
            base_ir_actions.IrActionsServer,
            '_run_action_webhook',
            autospec=True,
            return_value=None,
        ) as native_webhook, patch.object(
            base_mail_mail.MailMail,
            'send',
            autospec=True,
            return_value=True,
        ) as native_send:
            result = self.auth_user._notify_security_setting_update(
                'Security update',
                'A security setting changed',
            )

        native_webhook.assert_not_called()
        if native_send.called:
            security_mail = native_send.call_args.args[0]
            self.assertEqual(
                security_mail.env.context[
                    auth_mail_policy.SKIP_REASON_CONTEXT_KEY
                ],
                auth_mail_policy.AUTH_TRANSACTIONAL_REASON,
            )
        if result:
            self.assertFalse(result.filtered('needs_translation'))

    def test_new_device_mail_does_not_reach_translation_automation(self):
        if release.version_info[0] >= 19:
            self.skipTest('Odoo version uses security notifications instead')

        with patch.object(
            base_ir_actions.IrActionsServer,
            '_run_action_webhook',
            autospec=True,
            return_value=None,
        ) as native_webhook, patch.object(
            base_mail_mail.MailMail,
            'send',
            autospec=True,
            return_value=True,
        ) as native_send:
            self.auth_user._alert_new_device()

        native_webhook.assert_not_called()
        native_send.assert_called_once()
        new_device_mail = native_send.call_args.args[0]
        self.assertEqual(
            new_device_mail.env.context[
                auth_mail_policy.SKIP_REASON_CONTEXT_KEY
            ],
            auth_mail_policy.AUTH_TRANSACTIONAL_REASON,
        )

    def test_email_totp_code_uses_auth_marker_when_addon_is_installed(self):
        if not hasattr(self.auth_user, '_send_totp_mail_code'):
            self.skipTest('Email TOTP addon is not installed')

        native_mail = self._create_native_auth_mail()
        user_model_class = type(self.auth_user)
        with patch.object(
            user_model_class,
            '_totp_rate_limit',
            autospec=True,
            return_value=None,
        ), patch.object(
            base_mail_template.MailTemplate,
            'send_mail_batch',
            autospec=True,
            return_value=native_mail,
        ) as native_send_batch:
            self.auth_user._send_totp_mail_code()

        classified_template = native_send_batch.call_args.args[0]
        self.assertEqual(
            classified_template.env.context[
                auth_mail_policy.SKIP_REASON_CONTEXT_KEY
            ],
            auth_mail_policy.AUTH_TRANSACTIONAL_REASON,
        )

    def test_totp_invitation_uses_auth_marker(self):
        native_mail = self._create_native_auth_mail()
        with patch.object(
            base_mail_template.MailTemplate,
            'send_mail_batch',
            autospec=True,
            return_value=native_mail,
        ) as native_send_batch:
            self.auth_user.action_totp_invite()

        classified_template = native_send_batch.call_args.args[0]
        self.assertEqual(
            classified_template.env.context[
                auth_mail_policy.SKIP_REASON_CONTEXT_KEY
            ],
            auth_mail_policy.AUTH_TRANSACTIONAL_REASON,
        )

    def test_historical_mail_automation_filter_is_reconciled(self):
        other_automation = self.env['base.automation'].create({
            'name': 'Unrelated mail automation',
            'model_id': self.env['ir.model']._get_id('mail.mail'),
            'trigger': 'on_create',
            'filter_domain': '[]',
            'active': False,
        })
        self.addCleanup(other_automation.unlink)
        self.mail_automation.name = 'Renamed mail automation'
        self.mail_automation.filter_domain = '[]'

        updated_count = self.env[
            'base.automation'
        ]._odootranslate_reconcile_mail_filters()

        self.assertGreaterEqual(updated_count, 1)
        self.assertEqual(
            self.mail_automation.filter_domain,
            base_automation.MAIL_TRANSLATION_FILTER,
        )
        self.assertEqual(other_automation.filter_domain, '[]')

    def test_password_reset_fallback_is_sent_without_waiting_for_translation(self):
        mail = self._create_waiting_mail().with_context(
            skip_ai_translation=True,
            **{
                auth_mail_policy.SKIP_REASON_CONTEXT_KEY:
                    auth_mail_policy.AUTH_TRANSACTIONAL_REASON,
            },
        )

        with patch.object(
            base_mail_mail.MailMail,
            'send',
            autospec=True,
            return_value=True,
        ) as native_send:
            result = mail_mail.MailMail.send(
                mail,
                auto_commit=False,
                raise_exception=False,
            )

        self.assertTrue(result)
        native_send.assert_called_once()
        self.assertFalse(mail.needs_translation)
        self.assertFalse(mail.scheduled_date)

    def test_signup_invitation_is_not_classified_only_by_raise_exception(self):
        normal_mail = self._create_waiting_mail(
            scheduled_date=fields.Datetime.now() + timedelta(minutes=4),
        )

        with patch.object(
            base_mail_mail.MailMail,
            'send',
            autospec=True,
            return_value=True,
        ) as native_send:
            result = mail_mail.MailMail.send(
                normal_mail,
                auto_commit=False,
                raise_exception=True,
            )

        self.assertTrue(result)
        native_send.assert_not_called()
        self.assertTrue(normal_mail.needs_translation)
        self.assertTrue(normal_mail.scheduled_date)

    def test_renamed_managed_webhook_is_suppressed_for_auth_mail(self):
        self.webhook_action.name = 'Renamed OdooTranslate mail webhook'
        action = self.webhook_action.with_context(**{
            auth_mail_policy.SKIP_REASON_CONTEXT_KEY:
                auth_mail_policy.AUTH_TRANSACTIONAL_REASON,
        })

        with patch.object(
            base_ir_actions.IrActionsServer,
            '_run_action_webhook',
            autospec=True,
            return_value=None,
        ) as native_webhook:
            result = ir_actions_server.IrActionsServer._run_action_webhook(action)

        self.assertIsNone(result)
        native_webhook.assert_not_called()

    def test_unmanaged_prefix_webhook_is_not_suppressed_for_auth_mail(self):
        action = self.env['ir.actions.server'].create({
            'name': '[OdooTranslate] Translation - mail.mail - send webhook',
            'model_id': self.env['ir.model']._get_id('mail.mail'),
            'state': 'webhook',
            'webhook_url': 'https://app.example.test/webhook',
        }).with_context(**{
            auth_mail_policy.SKIP_REASON_CONTEXT_KEY:
                auth_mail_policy.AUTH_TRANSACTIONAL_REASON,
        })

        with patch.object(
            base_ir_actions.IrActionsServer,
            '_run_action_webhook',
            autospec=True,
            return_value='native-result',
        ) as native_webhook:
            result = ir_actions_server.IrActionsServer._run_action_webhook(
                action,
            )

        self.assertEqual(result, 'native-result')
        native_webhook.assert_called_once()

    def test_unmanaged_prefix_automation_does_not_enable_mail_translation(self):
        self.mail_automation.active = False
        unmanaged_automation = self.env['base.automation'].create({
            'name': '[OdooTranslate] Auto-Translation - mail.mail',
            'model_id': self.env['ir.model']._get_id('mail.mail'),
            'trigger': 'on_create',
            'active': True,
        })
        self.addCleanup(unmanaged_automation.unlink)

        should_translate = self.env['mail.mail']._should_translate_mail({
            'subject': 'Source subject',
        })

        self.assertFalse(should_translate)

    def test_normal_odootranslate_webhook_is_not_suppressed(self):
        action = self.env['ir.actions.server'].create({
            'name': '[OdooTranslate] Translation - mail.mail - send webhook',
            'model_id': self.env['ir.model']._get_id('mail.mail'),
            'state': 'webhook',
            'webhook_url': 'https://app.example.test/webhook',
        })

        with patch.object(
            base_ir_actions.IrActionsServer,
            '_run_action_webhook',
            autospec=True,
            return_value='native-result',
        ) as native_webhook:
            result = ir_actions_server.IrActionsServer._run_action_webhook(action)

        self.assertEqual(result, 'native-result')
        native_webhook.assert_called_once()
