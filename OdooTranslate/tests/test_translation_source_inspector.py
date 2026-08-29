# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestTranslationSourceInspector(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.lang']._activate_lang('fr_FR')
        cls.category = cls.env['res.partner.category'].create({
            'name': 'English source',
        })

    def test_fallback_value_is_not_reported_as_a_stored_source(self):
        self.assertEqual(
            self.category.with_context(lang='fr_FR').name,
            'English source',
        )

        state = self.category.odootranslate_get_stored_field_translation_source(
            'name',
            'fr_FR',
        )

        self.assertFalse(state['is_stored'])
        self.assertFalse(state['value'])
        self.assertEqual(state['blocks'], [])

    def test_explicit_translate_true_value_is_reported_without_fallback(self):
        self.category.with_context(lang='fr_FR').write({
            'name': 'Source francaise',
        })

        state = self.category.odootranslate_get_stored_field_translation_source(
            'name',
            'fr_FR',
        )

        self.assertTrue(state['is_stored'])
        self.assertFalse(state['translation_show_source'])
        self.assertEqual(state['value'], 'Source francaise')
        self.assertEqual(state['blocks'], [{
            'source': 'English source',
            'value': 'Source francaise',
        }])
        self.assertTrue(state['mapping_complete'])

    def test_stored_english_source_is_reported(self):
        state = self.category.odootranslate_get_stored_field_translation_source(
            'name',
            'en_US',
        )

        self.assertTrue(state['is_stored'])
        self.assertEqual(state['value'], 'English source')
        self.assertEqual(state['blocks'], [{
            'source': 'English source',
            'value': 'English source',
        }])

    def test_callable_html_source_returns_fallback_free_blocks(self):
        view = self.env['ir.ui.view'].create({
            'name': 'OdooTranslate source inspector test',
            'type': 'qweb',
            'key': 'odoo_translate.source_inspector_test',
            'arch_db': '<t t-name="odoo_translate.source_inspector_test"><p>Hello world</p></t>',
        })
        view.update_field_translations('arch_db', {
            'fr_FR': {'Hello world': 'Bonjour monde'},
        })

        state = view.odootranslate_get_stored_field_translation_source(
            'arch_db',
            'fr_FR',
        )

        self.assertTrue(state['is_stored'])
        self.assertTrue(state['translation_show_source'])
        self.assertTrue(state['mapping_complete'])
        self.assertIn(
            {'source': 'Hello world', 'value': 'Bonjour monde'},
            state['blocks'],
        )

    def test_field_group_restrictions_are_enforced(self):
        restricted_user = new_test_user(
            self.env,
            login='odootranslate_source_inspector_user',
            groups='base.group_user',
            context={'no_reset_password': True},
        )
        field = self.category._fields['name']
        original_groups = field.groups
        field.groups = 'base.group_system'

        try:
            with self.assertRaises(AccessError):
                self.category.with_user(
                    restricted_user,
                ).odootranslate_get_stored_field_translation_source(
                    'name',
                    'en_US',
                )
        finally:
            field.groups = original_groups

    def test_non_translatable_field_is_rejected(self):
        with self.assertRaises(UserError):
            self.category.odootranslate_get_stored_field_translation_source(
                'active',
                'fr_FR',
            )
