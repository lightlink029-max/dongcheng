# -*- coding: utf-8 -*-

from psycopg2 import IntegrityError

from odoo.tests.common import TransactionCase, tagged

from ..models import base_automation, rule_identity


@tagged('post_install', '-at_install')
class TestRuleIdentity(TransactionCase):

    def test_managed_rule_fields_are_persistent_indexed_and_not_copied(self):
        for model_name in ('ir.actions.server', 'base.automation'):
            model = self.env[model_name]

            managed_field = model._fields['odootranslate_managed']
            key_field = model._fields['odootranslate_rule_key']

            self.assertTrue(managed_field.store)
            self.assertTrue(managed_field.index)
            self.assertFalse(managed_field.copy)
            self.assertTrue(key_field.store)
            self.assertTrue(key_field.index)
            self.assertFalse(key_field.copy)

    def test_rule_keys_are_unique_when_present(self):
        model_id = self.env['ir.model']._get_id('mail.mail')
        action_model = self.env['ir.actions.server']
        action_values = {
            'name': 'Managed mail webhook',
            'model_id': model_id,
            'state': 'webhook',
            'webhook_url': 'https://app.example.test/webhook',
            'odootranslate_managed': True,
            'odootranslate_rule_key': 'webhook:mail.mail',
        }
        action = action_model.create(action_values)
        self.addCleanup(action.unlink)
        second_action = action_model.create({
            **action_values,
            'name': 'Second managed mail webhook',
            'odootranslate_rule_key': False,
        })
        self.addCleanup(second_action.unlink)

        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env.cr.execute(
                f'UPDATE "{action_model._table}" '
                'SET odootranslate_rule_key = %s WHERE id = %s',
                ('webhook:mail.mail', second_action.id),
            )

        automation_model = self.env['base.automation']
        automation_values = {
            'name': 'Managed mail automation',
            'model_id': model_id,
            'trigger': 'on_create',
            'action_server_ids': [(6, 0, action.ids)],
            'active': True,
            'odootranslate_managed': True,
            'odootranslate_rule_key': 'automation:mail.mail',
        }
        automation = automation_model.create(automation_values)
        self.addCleanup(automation.unlink)
        second_automation = automation_model.create({
            **automation_values,
            'name': 'Second managed mail automation',
            'action_server_ids': [(6, 0, second_action.ids)],
            'odootranslate_rule_key': False,
        })
        self.addCleanup(second_automation.unlink)

        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env.cr.execute(
                f'UPDATE "{automation_model._table}" '
                'SET odootranslate_rule_key = %s WHERE id = %s',
                ('automation:mail.mail', second_automation.id),
            )

    def test_legacy_rules_are_migrated_once_and_keep_identity_after_rename(self):
        model_id = self.env['ir.model']._get_id('mail.mail')
        action = self.env['ir.actions.server'].create({
            'name': '[OdooTranslate] Translation - mail.mail - send webhook',
            'model_id': model_id,
            'state': 'webhook',
            'webhook_url': 'https://app.example.test/webhook',
        })
        automation = self.env['base.automation'].create({
            'name': '[OdooTranslate] Auto-Translation - mail.mail',
            'model_id': model_id,
            'trigger': 'on_create',
            'action_server_ids': [(6, 0, action.ids)],
            'active': True,
        })
        self.addCleanup(action.unlink)
        self.addCleanup(automation.unlink)

        if 'automated_name' not in action._fields:
            state_labels = dict(
                action._fields['state']._description_selection(self.env),
            )
            self.assertEqual(action.name, state_labels['webhook'])

        migrated = rule_identity.migrate_legacy_rules(self.env)

        self.assertEqual(migrated, {'actions': 1, 'automations': 1})
        self.assertTrue(action.odootranslate_managed)
        self.assertEqual(
            action.odootranslate_rule_key,
            'webhook:mail.mail',
        )
        self.assertTrue(automation.odootranslate_managed)
        self.assertEqual(
            automation.odootranslate_rule_key,
            'automation:mail.mail',
        )
        self.assertEqual(
            automation.filter_domain,
            base_automation.MAIL_TRANSLATION_FILTER,
        )

        action.name = 'Webhook renamed by an administrator'
        automation.name = 'Automation renamed by an administrator'

        self.assertEqual(
            rule_identity.migrate_legacy_rules(self.env),
            {'actions': 0, 'automations': 0},
        )
        self.assertEqual(action.odootranslate_rule_key, 'webhook:mail.mail')
        self.assertEqual(
            automation.odootranslate_rule_key,
            'automation:mail.mail',
        )

    def test_odoo18_automatic_webhook_name_migration_is_language_independent(self):
        model_id = self.env['ir.model']._get_id('res.partner')
        action = self.env['ir.actions.server'].create({
            'name': '[OdooTranslate] Translation - res.partner - send webhook',
            'model_id': model_id,
            'state': 'webhook',
            'webhook_url': 'https://app.example.test/webhook',
        })
        automation = self.env['base.automation'].create({
            'name': '[OdooTranslate] Auto-Translation - res.partner',
            'model_id': model_id,
            'trigger': 'on_create',
            'action_server_ids': [(6, 0, action.ids)],
            'active': True,
        })
        self.addCleanup(action.unlink)
        self.addCleanup(automation.unlink)

        migration_env = self.env
        if 'automated_name' not in action._fields:
            language = self.env['res.lang']._activate_lang('fr_FR')
            self.env['base.language.install'].create({
                'lang_ids': [(6, 0, language.ids)],
                'overwrite': True,
            }).lang_install()
            expected_localized_name = rule_identity.get_translation(
                'base_automation',
                'fr_FR',
                rule_identity.ODOO18_AUTOMATIC_WEBHOOK_SOURCE,
                (),
            )
            self.assertNotEqual(
                expected_localized_name,
                rule_identity.ODOO18_AUTOMATIC_WEBHOOK_SOURCE,
            )
            localized_action = action.with_context(lang='fr_FR')
            localized_action._compute_name()
            localized_action.flush_recordset(['name'])
            localized_action.invalidate_recordset(['name'])
            self.assertEqual(localized_action.name, expected_localized_name)
            migration_env = localized_action.env

        self.assertEqual(
            rule_identity.migrate_legacy_rules(migration_env),
            {'actions': 1, 'automations': 1},
        )
        self.assertEqual(
            action.odootranslate_rule_key,
            'webhook:res.partner',
        )
        self.assertEqual(
            automation.odootranslate_rule_key,
            'automation:res.partner',
        )

    def test_strict_migration_ignores_false_prefix_and_unrelated_automation(self):
        model_id = self.env['ir.model']._get_id('mail.mail')
        false_prefix_action = self.env['ir.actions.server'].create({
            'name': (
                '[OdooTranslate] Translation - mail.mail - send webhook copy'
            ),
            'model_id': model_id,
            'state': 'webhook',
            'webhook_url': 'https://app.example.test/webhook',
        })
        unrelated_action = self.env['ir.actions.server'].create({
            'name': 'Unrelated webhook',
            'model_id': model_id,
            'state': 'webhook',
            'webhook_url': 'https://app.example.test/webhook',
        })
        wrong_state_action = self.env['ir.actions.server'].create({
            'name': '[OdooTranslate] Translation - res.partner - send webhook',
            'model_id': self.env['ir.model']._get_id('res.partner'),
            'state': 'code',
            'code': 'action = None',
        })
        wrong_model_action = self.env['ir.actions.server'].create({
            'name': (
                '[OdooTranslate] Translation - product.product - '
                'send webhook'
            ),
            'model_id': self.env['ir.model']._get_id('res.partner'),
            'state': 'webhook',
            'webhook_url': 'https://app.example.test/webhook',
        })
        false_prefix_automation = self.env['base.automation'].create({
            'name': '[OdooTranslate] Auto-Translation - mail.mail copy',
            'model_id': model_id,
            'trigger': 'on_create',
            'action_server_ids': [(6, 0, false_prefix_action.ids)],
            'active': True,
        })
        exact_but_unrelated_automation = self.env['base.automation'].create({
            'name': '[OdooTranslate] Auto-Translation - mail.mail',
            'model_id': model_id,
            'trigger': 'on_create',
            'action_server_ids': [(6, 0, unrelated_action.ids)],
            'active': True,
        })
        unrelated_action.name = 'Unrelated webhook'
        self.addCleanup(false_prefix_action.unlink)
        self.addCleanup(unrelated_action.unlink)
        self.addCleanup(wrong_state_action.unlink)
        self.addCleanup(wrong_model_action.unlink)
        self.addCleanup(false_prefix_automation.unlink)
        self.addCleanup(exact_but_unrelated_automation.unlink)

        self.assertEqual(
            rule_identity.migrate_legacy_rules(self.env),
            {'actions': 0, 'automations': 0},
        )
        self.assertFalse(false_prefix_action.odootranslate_managed)
        self.assertFalse(wrong_state_action.odootranslate_managed)
        self.assertFalse(wrong_model_action.odootranslate_managed)
        self.assertFalse(false_prefix_automation.odootranslate_managed)
        self.assertFalse(exact_but_unrelated_automation.odootranslate_managed)

    def test_previous_branding_exact_names_are_migrated(self):
        model_id = self.env['ir.model']._get_id('res.partner')
        action = self.env['ir.actions.server'].create({
            'name': '[NODIE] Translation - res.partner - send webhook',
            'model_id': model_id,
            'state': 'webhook',
            'webhook_url': 'https://app.example.test/webhook',
        })
        automation = self.env['base.automation'].create({
            'name': '[NODIE] Auto-translate res.partner',
            'model_id': model_id,
            'trigger': 'on_create',
            'action_server_ids': [(6, 0, action.ids)],
            'active': True,
        })
        self.addCleanup(action.unlink)
        self.addCleanup(automation.unlink)

        self.assertEqual(
            rule_identity.migrate_legacy_rules(self.env),
            {'actions': 1, 'automations': 1},
        )
        self.assertEqual(
            action.odootranslate_rule_key,
            'webhook:res.partner',
        )
        self.assertEqual(
            automation.odootranslate_rule_key,
            'automation:res.partner',
        )

    def test_ambiguous_legacy_action_key_is_left_unmanaged(self):
        model_id = self.env['ir.model']._get_id('res.partner')
        actions = self.env['ir.actions.server'].browse()
        for _index in range(2):
            actions |= self.env['ir.actions.server'].create({
                'name': (
                    '[OdooTranslate] Translation - res.partner - '
                    'send webhook'
                ),
                'model_id': model_id,
                'state': 'webhook',
                'webhook_url': 'https://app.example.test/webhook',
            })
        self.addCleanup(actions.unlink)

        self.assertEqual(
            rule_identity.migrate_legacy_rules(self.env),
            {'actions': 0, 'automations': 0},
        )
        self.assertFalse(any(actions.mapped('odootranslate_managed')))
