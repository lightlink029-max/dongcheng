# -*- coding: utf-8 -*-

import logging
import re

from odoo.tools.translate import get_translation

_logger = logging.getLogger(__name__)

MANAGED_FIELD = 'odootranslate_managed'
RULE_KEY_FIELD = 'odootranslate_rule_key'
ACTION_RULE_KEY_PREFIX = 'webhook:'
AUTOMATION_RULE_KEY_PREFIX = 'automation:'
MAIL_ACTION_RULE_KEY = 'webhook:mail.mail'
MAIL_AUTOMATION_RULE_KEY = 'automation:mail.mail'
ODOO18_AUTOMATIC_WEBHOOK_SOURCE = 'Send Webhook Notification'

_WATCHED_MODEL_OVERRIDES = {
    'website.page': 'ir.ui.view',
}

_MODEL_PATTERN = r'[A-Za-z_][A-Za-z0-9_.]*'
_LEGACY_ACTION_PATTERN = re.compile(
    r'^\[(?:OdooTranslate|NODIE)\] Translation - '
    rf'(?P<model>{_MODEL_PATTERN}) - send webhook$',
)
_LEGACY_AUTOMATION_PATTERNS = (
    re.compile(
        r'^\[(?:OdooTranslate|NODIE)\] Auto-Translation - '
        rf'(?P<model>{_MODEL_PATTERN})$',
    ),
    re.compile(
        rf'^\[NODIE\] Auto-translate (?P<model>{_MODEL_PATTERN})$',
    ),
)


def action_rule_key(logical_model):
    return f'{ACTION_RULE_KEY_PREFIX}{logical_model}'


def automation_rule_key(watched_model):
    return f'{AUTOMATION_RULE_KEY_PREFIX}{watched_model}'


def _legacy_action_model(name):
    match = _LEGACY_ACTION_PATTERN.fullmatch(name or '')
    return match.group('model') if match else None


def _legacy_automation_model(name):
    for pattern in _LEGACY_AUTOMATION_PATTERNS:
        match = pattern.fullmatch(name or '')
        if match:
            return match.group('model')
    return None


def _logical_model_from_action(action):
    key = action.odootranslate_rule_key or ''
    if not key.startswith(ACTION_RULE_KEY_PREFIX):
        return None
    return key[len(ACTION_RULE_KEY_PREFIX):] or None


def _is_legacy_automatic_webhook_name(action):
    """Detect the automatic action name used by Odoo 18 automations."""
    if 'automated_name' in action._fields or action.state != 'webhook':
        return False

    languages = action.env['res.lang'].sudo().with_context(
        active_test=False,
    ).search([]).mapped('code')
    automatic_names = {
        get_translation(
            'base_automation',
            language,
            ODOO18_AUTOMATIC_WEBHOOK_SOURCE,
            (),
        )
        for language in {'en_US', *languages}
    }

    return action.name in automatic_names


def _recover_legacy_action_candidates(automation_model):
    """Recover Odoo 18 actions whose custom name was overwritten by Odoo."""
    recovered_candidates = []
    legacy_automations = automation_model.search([
        (MANAGED_FIELD, '=', False),
        '|',
        ('name', '=like', '[OdooTranslate] Auto-Translation - %'),
        '|',
        ('name', '=like', '[NODIE] Auto-Translation - %'),
        ('name', '=like', '[NODIE] Auto-translate %'),
    ])
    for automation in legacy_automations:
        historical_model = _legacy_automation_model(automation.name)
        if not historical_model or not automation.model_id.model:
            continue

        expected_watched_model = _WATCHED_MODEL_OVERRIDES.get(
            historical_model,
            historical_model,
        )
        linked_actions = automation.action_server_ids
        if (
            automation.model_id.model != expected_watched_model
            or len(linked_actions) != 1
        ):
            continue

        action = linked_actions
        if (
            action.odootranslate_managed
            or action.model_id != automation.model_id
            or not _is_legacy_automatic_webhook_name(action)
        ):
            continue

        recovered_candidates.append((
            action_rule_key(historical_model),
            action,
        ))

    return recovered_candidates


def migrate_legacy_rules(env):
    """Attach durable identities only to unambiguous historical rules."""
    action_model = env['ir.actions.server'].sudo().with_context(
        active_test=False,
    )
    automation_model = env['base.automation'].sudo().with_context(
        active_test=False,
    )

    action_candidates_by_key = {}
    legacy_actions = action_model.search([
        (MANAGED_FIELD, '=', False),
        ('state', '=', 'webhook'),
        '|',
        ('name', '=like', '[OdooTranslate] Translation - % - send webhook'),
        ('name', '=like', '[NODIE] Translation - % - send webhook'),
    ])
    for action in legacy_actions:
        logical_model = _legacy_action_model(action.name)
        if not logical_model:
            continue
        expected_watched_model = _WATCHED_MODEL_OVERRIDES.get(
            logical_model,
            logical_model,
        )
        if action.model_id.model != expected_watched_model:
            continue
        key = action_rule_key(logical_model)
        action_candidates_by_key.setdefault(key, action_model.browse())
        action_candidates_by_key[key] |= action

    for key, action in _recover_legacy_action_candidates(automation_model):
        action_candidates_by_key.setdefault(key, action_model.browse())
        action_candidates_by_key[key] |= action

    migrated_actions = action_model.browse()
    existing_action_keys = set(action_model.search([
        (MANAGED_FIELD, '=', True),
        (RULE_KEY_FIELD, '!=', False),
    ]).mapped(RULE_KEY_FIELD))
    for key, candidates in action_candidates_by_key.items():
        if len(candidates) != 1 or key in existing_action_keys:
            _logger.warning(
                '[OdooTranslate] legacy action migration skipped: '
                'rule_key=%s candidate_count=%s already_managed=%s',
                key,
                len(candidates),
                key in existing_action_keys,
            )
            continue
        candidates.write({
            MANAGED_FIELD: True,
            RULE_KEY_FIELD: key,
        })
        migrated_actions |= candidates
        existing_action_keys.add(key)

    managed_actions = action_model.search([
        (MANAGED_FIELD, '=', True),
        (RULE_KEY_FIELD, '=like', f'{ACTION_RULE_KEY_PREFIX}%'),
        ('state', '=', 'webhook'),
    ])
    automation_candidates_by_key = {}
    if managed_actions:
        legacy_automations = automation_model.search([
            (MANAGED_FIELD, '=', False),
            ('action_server_ids', 'in', managed_actions.ids),
        ])
        for automation in legacy_automations:
            historical_model = _legacy_automation_model(automation.name)
            if not historical_model or not automation.model_id.model:
                continue

            linked_actions = automation.action_server_ids
            valid_linked_actions = linked_actions.filtered(
                lambda action: (
                    action.odootranslate_managed
                    and action.state == 'webhook'
                    and _logical_model_from_action(action)
                )
            )
            if (
                not linked_actions
                or set(valid_linked_actions.ids) != set(linked_actions.ids)
                or any(
                    action.model_id != automation.model_id
                    for action in valid_linked_actions
                )
            ):
                continue

            valid_name_models = {
                automation.model_id.model,
                *valid_linked_actions.mapped(
                    lambda action: _logical_model_from_action(action),
                ),
            }
            if historical_model not in valid_name_models:
                continue

            key = automation_rule_key(automation.model_id.model)
            automation_candidates_by_key.setdefault(
                key,
                automation_model.browse(),
            )
            automation_candidates_by_key[key] |= automation

    migrated_automations = automation_model.browse()
    existing_automation_keys = set(automation_model.search([
        (MANAGED_FIELD, '=', True),
        (RULE_KEY_FIELD, '!=', False),
    ]).mapped(RULE_KEY_FIELD))
    for key, candidates in automation_candidates_by_key.items():
        if len(candidates) != 1 or key in existing_automation_keys:
            _logger.warning(
                '[OdooTranslate] legacy automation migration skipped: '
                'rule_key=%s candidate_count=%s already_managed=%s',
                key,
                len(candidates),
                key in existing_automation_keys,
            )
            continue
        candidates.write({
            MANAGED_FIELD: True,
            RULE_KEY_FIELD: key,
        })
        migrated_automations |= candidates
        existing_automation_keys.add(key)

    result = {
        'actions': len(migrated_actions),
        'automations': len(migrated_automations),
    }
    automation_model._odootranslate_reconcile_mail_filters()
    _logger.info(
        '[OdooTranslate] legacy rule identity migration completed: '
        'actions=%s automations=%s',
        result['actions'],
        result['automations'],
    )
    return result
