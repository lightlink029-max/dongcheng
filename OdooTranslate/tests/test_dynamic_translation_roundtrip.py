# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestDynamicTranslationRoundtrip(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.lang']._activate_lang('fr_FR')
        cls.french_user = new_test_user(
            cls.env,
            login='odootranslate_dynamic_translation_user',
            groups='base.group_user',
            context={'no_reset_password': True},
            lang='fr_FR',
        )
        cls.partner = cls.env['res.partner'].create({
            'name': 'Dynamic translation fixture',
            'ref': 'Original reference',
        })

        model = cls.env['ir.model']._get('res.partner')
        field = cls.env['ir.model.fields'].search([
            ('model_id', '=', model.id),
            ('name', '=', 'ref'),
        ], limit=1)
        cls.config = cls.env['dynamic.translatable.field.config'].create({
            'model_id': model.id,
            'field_id': field.id,
        })
        cls.config.action_apply_translation()
        cls.env['dynamic.translation'].set_translation(
            model_name='res.partner',
            field_name='ref',
            res_id=cls.partner.id,
            lang='fr_FR',
            value='Reference traduite',
            source='Original reference',
        )

    def test_configured_non_native_field_is_translated_on_read(self):
        result = self.partner.with_user(self.french_user).read(['ref'])

        self.assertEqual('Reference traduite', result[0]['ref'])

    def test_original_value_remains_available_to_the_saas_reader(self):
        result = self.partner.with_user(self.french_user).with_context(
            skip_ai_translation=True,
        ).read(['ref'])

        self.assertEqual('Original reference', result[0]['ref'])

    def test_translation_does_not_overwrite_the_original_field(self):
        self.env.cr.execute(
            'SELECT ref FROM res_partner WHERE id = %s',
            (self.partner.id,),
        )

        self.assertEqual('Original reference', self.env.cr.fetchone()[0])
