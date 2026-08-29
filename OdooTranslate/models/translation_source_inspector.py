# -*- coding: utf-8 -*-

from odoo import models
from odoo.exceptions import UserError


class Base(models.AbstractModel):
    _inherit = 'base'

    def odootranslate_get_stored_field_translation_source(self, field_name, lang):
        self.ensure_one()
        self.check_access('read')
        self.check_field_access_rights('read', [field_name])

        field = self._fields.get(field_name)
        if not field or not field.translate or not field.store:
            raise UserError('The requested field does not have stored native translations.')

        stored_translations = field._get_stored_translations(self) or {}
        source_value = stored_translations.get(lang)
        is_stored = isinstance(source_value, str) and bool(source_value.strip())
        result = {
            'is_stored': is_stored,
            'translation_show_source': callable(field.translate),
            'value': source_value if is_stored else False,
            'blocks': [],
            'mapping_complete': is_stored,
        }

        if not is_stored:
            return result

        english_value = stored_translations.get('en_US')
        if not isinstance(english_value, str):
            result['mapping_complete'] = False
            return result

        if field.translate is True:
            result['blocks'] = [{
                'source': english_value,
                'value': source_value,
            }]
            return result

        english_terms = list(field.get_trans_terms(english_value))
        source_terms = list(field.get_trans_terms(source_value))
        if len(english_terms) != len(source_terms):
            result['mapping_complete'] = False
            return result

        result['blocks'] = [
            {'source': english_term, 'value': source_term}
            for english_term, source_term in zip(english_terms, source_terms)
        ]
        return result
