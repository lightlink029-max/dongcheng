# -*- coding: utf-8 -*-
"""
OdooTranslate Configuration Model

Stores the connection state between the Odoo module and the OdooTranslate Laravel app.
This model handles:
1. Module UUID (unique identifier for this Odoo instance)
2. Link token (temporary token for OAuth-like linking flow)
3. Connection status (disconnected, pending, connected)
4. API key status from the Laravel app
"""
import hmac
import logging
import uuid
from urllib.parse import urlencode

import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..module_api import build_signed_request, legacy_unlink_operation_id

_logger = logging.getLogger(__name__)

# OdooTranslate app base URL - can be overridden in system parameters
ODOO_TRANSLATE_APP_URL = 'https://app.odootranslate.com'

class OdooTranslateConfig(models.Model):
    _name = 'odoo_translate.config'
    _description = 'OdooTranslate Connection Configuration'
    _rec_name = 'display_name'

    # Unique identifier for this Odoo instance
    module_uuid = fields.Char(
        string='Module UUID',
        readonly=True,
        copy=False,
        help='Unique identifier for this Odoo instance'
    )

    # Shared secret for HMAC signatures (unique per client, set during linking)
    shared_secret = fields.Char(
        string='Shared Secret',
        readonly=True,
        copy=False,
        groups='base.group_no_one',
        help='Secret key for secure communication with OdooTranslate app'
    )

    link_attempt_id = fields.Char(
        string='Link Attempt ID',
        readonly=True,
        copy=False,
        groups='base.group_no_one',
        help='Durable identifier of the active OdooTranslate link generation',
    )

    unlink_operation_id = fields.Char(
        string='Unlink Operation ID',
        readonly=True,
        copy=False,
        groups='base.group_no_one',
        help='Stable identifier used to make disconnect retries idempotent',
    )

    # Temporary token used during the linking flow
    link_token = fields.Char(
        string='Link Token',
        readonly=True,
        copy=False,
        help='Temporary token used during the connection flow'
    )

    # When the link token was generated
    link_token_created_at = fields.Datetime(
        string='Link Token Created',
        readonly=True,
    )

    # Connection status
    connection_status = fields.Selection([
        ('disconnected', 'Not Connected'),
        ('pending', 'Connection Pending'),
        ('connected', 'Connected'),
    ], string='Connection Status', default='disconnected', readonly=True)

    # Whether the Odoo API key is configured on OdooTranslate app
    has_api_key = fields.Boolean(
        string='API Key Configured',
        default=False,
        readonly=True,
        help='True if the user has configured their Odoo API key on the OdooTranslate app'
    )

    # Linked user email (from OdooTranslate app)
    linked_email = fields.Char(
        string='Linked Account Email',
        readonly=True,
    )

    # When the module was connected
    connected_at = fields.Datetime(
        string='Connected At',
        readonly=True,
    )

    # Last status check
    last_status_check = fields.Datetime(
        string='Last Status Check',
        readonly=True,
    )

    # Computed display name
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )

    # Status emoji for UI
    status_emoji = fields.Char(
        string='Status',
        compute='_compute_status_emoji',
    )

    # Status label for UI
    status_label = fields.Char(
        string='Status Label',
        compute='_compute_status_label',
    )

    @api.depends('connection_status', 'has_api_key', 'linked_email')
    def _compute_display_name(self):
        for record in self:
            if record.connection_status == 'disconnected':
                record.display_name = _('OdooTranslate - Not Connected')
            elif record.connection_status == 'pending':
                record.display_name = _('OdooTranslate - Connection Pending')
            elif record.has_api_key:
                record.display_name = _('OdooTranslate - Connected (%s)') % (record.linked_email or 'Unknown')
            else:
                record.display_name = _('OdooTranslate - API Key Missing')

    @api.depends('connection_status', 'has_api_key')
    def _compute_status_emoji(self):
        for record in self:
            if record.connection_status == 'disconnected':
                record.status_emoji = '🔴'
            elif record.connection_status == 'pending':
                record.status_emoji = '🔴'
            elif not record.has_api_key:
                record.status_emoji = '🟠'
            else:
                record.status_emoji = '🟢'

    @api.depends('connection_status', 'has_api_key')
    def _compute_status_label(self):
        for record in self:
            if record.connection_status == 'disconnected':
                record.status_label = _('Not connected to OdooTranslate')
            elif record.connection_status == 'pending':
                record.status_label = _('Connection pending - complete the registration')
            elif not record.has_api_key:
                record.status_label = _('Connected but Odoo API key not configured')
            else:
                record.status_label = _('Connected and ready to translate')

    @api.model
    def get_config(self):
        """Get or create the singleton configuration record."""
        config = self.sudo().search([], limit=1)
        if not config:
            config = self.sudo().create({
                'module_uuid': str(uuid.uuid4()),
            })
        return config

    def _get_app_url(self):
        """Get the OdooTranslate app URL from system parameters or default."""
        param = self.env['ir.config_parameter'].sudo().get_param('odoo_translate.app_url')
        return (param or ODOO_TRANSLATE_APP_URL).rstrip('/')

    def action_connect(self):
        """
        Initiate the connection flow.
        Generates a link token and returns the URL to open.
        """
        self.ensure_one()

        self.flush_recordset()
        self.env.cr.execute(
            'SELECT id FROM odoo_translate_config WHERE id = %s FOR UPDATE',
            [self.id],
        )
        self.invalidate_recordset()
        if self.connection_status == 'connected':
            raise UserError(_(
                'OdooTranslate is already connected. Disconnect it before '
                'starting a new connection.'
            ))

        # Generate a new link token
        link_token = str(uuid.uuid4())

        self.write({
            'link_token': link_token,
            'link_token_created_at': fields.Datetime.now(),
            'connection_status': 'pending',
        })

        app_url = self._get_app_url()
        odoo_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        odoo_db = self.env.cr.dbname
        odoo_login = self.env.user.login
        query = urlencode({
            'uuid': self.module_uuid,
            'token': link_token,
            'odoo_url': odoo_url,
            'odoo_db': odoo_db,
            'odoo_login': odoo_login,
        })
        register_url = f"{app_url}/module/link?{query}"

        _logger.info('[OdooTranslate] Secure connection flow initiated')

        return {
            'type': 'ir.actions.act_url',
            'url': register_url,
            'target': 'new',
        }

    def action_configure_api_key(self):
        """
        Redirect to the OdooTranslate settings page to configure the Odoo API key.
        """
        self.ensure_one()

        app_url = self._get_app_url()
        settings_url = f"{app_url}/settings/odoo"

        return {
            'type': 'ir.actions.act_url',
            'url': settings_url,
            'target': 'new',
        }

    def action_disconnect(self):
        """
        Disconnect the module from OdooTranslate.
        Resets the connection status and clears credentials.
        """
        self.ensure_one()

        if not self.module_uuid or not self.shared_secret:
            raise UserError(_(
                'The secure module credentials are missing. Update or relink '
                'OdooTranslate before disconnecting.'
            ))

        module_uuid = self.module_uuid.lower()
        shared_secret = self.shared_secret
        configured_connection_status = self.connection_status
        configured_link_attempt_id = self.link_attempt_id or False
        configured_unlink_operation_id = self.unlink_operation_id or False
        configured_link_token = self.link_token or False
        configured_link_token_created_at = self.link_token_created_at or False

        if configured_connection_status != 'connected':
            raise UserError(_(
                'OdooTranslate is not in a connected state. Refresh the page '
                'before disconnecting.'
            ))

        with self.env.cr.savepoint():
            operation_id = configured_unlink_operation_id or legacy_unlink_operation_id(
                module_uuid,
                shared_secret,
            )
            data = self._post_module_api(
                '/api/module/v2/unlink',
                timeout=5,
                retry_network=True,
                retry_error_codes={'module_operation_in_progress'},
                payload={
                    'operation_id': operation_id,
                    'uuid': module_uuid,
                },
                module_uuid=module_uuid,
                shared_secret=shared_secret,
            )
            response_link_attempt_id = self._validated_link_attempt_id(data)

            if (
                data.get('status') != 'unlinked'
                or not response_link_attempt_id
                or (
                    configured_link_attempt_id
                    and response_link_attempt_id != configured_link_attempt_id
                )
            ):
                raise UserError(_(
                    'OdooTranslate returned an invalid unlink confirmation. '
                    'No local connection data was changed.'
                ))

            self.flush_recordset()
            self.env.cr.execute(
                'SELECT id FROM odoo_translate_config WHERE id = %s FOR UPDATE',
                [self.id],
            )
            self.invalidate_recordset()
            if (
                self.module_uuid.lower() != module_uuid
                or self.shared_secret != shared_secret
                or self.connection_status != configured_connection_status
                or (self.link_attempt_id or False) != configured_link_attempt_id
                or (self.unlink_operation_id or False) != configured_unlink_operation_id
                or (self.link_token or False) != configured_link_token
                or (
                    self.link_token_created_at or False
                ) != configured_link_token_created_at
            ):
                raise UserError(_(
                    'The OdooTranslate link changed while disconnecting. '
                    'The new connection was preserved.'
                ))

            self.write({
                'connection_status': 'disconnected',
                'has_api_key': False,
                'linked_email': False,
                'connected_at': False,
                'link_token': False,
                'link_token_created_at': False,
                'last_status_check': False,
                'shared_secret': False,
                'link_attempt_id': False,
                'unlink_operation_id': False,
            })

        # Return action to reload the form view
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'odoo_translate.config',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'main',
        }

    def action_refresh_status(self):
        """
        Check the current connection status with the OdooTranslate app.
        """
        self.ensure_one()

        if not self.module_uuid or not self.shared_secret:
            raise UserError(_(
                'The secure module credentials are missing. Update or relink '
                'OdooTranslate before refreshing the status.'
            ))

        module_uuid = self.module_uuid.lower()
        shared_secret = self.shared_secret
        current_link_attempt_id = self.link_attempt_id or False
        data = self._post_module_api(
            '/api/module/v2/status',
            timeout=10,
            module_uuid=module_uuid,
            shared_secret=shared_secret,
        )
        link_attempt_id = self._validated_link_attempt_id(data)

        if (
            data.get('connected') is not True
            or not link_attempt_id
            or (
                current_link_attempt_id
                and current_link_attempt_id != link_attempt_id
            )
        ):
            raise UserError(_(
                'OdooTranslate returned an invalid connection status. '
                'No local connection data was changed.'
            ))

        with self.env.cr.savepoint():
            self.flush_recordset()
            self.env.cr.execute(
                'SELECT id FROM odoo_translate_config WHERE id = %s FOR UPDATE',
                [self.id],
            )
            self.invalidate_recordset()
            if (
                self.module_uuid.lower() != module_uuid
                or self.shared_secret != shared_secret
                or (
                    self.link_attempt_id
                    and self.link_attempt_id != link_attempt_id
                )
            ):
                raise UserError(_(
                    'The OdooTranslate link changed while refreshing. '
                    'No connection data was changed.'
                ))

            self.write({
                'last_status_check': fields.Datetime.now(),
                'connection_status': 'connected',
                'has_api_key': data.get('has_api_key') is True,
                'link_attempt_id': link_attempt_id,
            })

        _logger.info('[OdooTranslate] Secure module status refreshed')

        # Return action to reload the form view with updated data
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'odoo_translate.config',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'main',
            'context': {
                'form_view_initial_mode': 'edit',
            },
        }

    def _post_module_api(
        self,
        path,
        timeout,
        retry_network=False,
        retry_error_codes=None,
        payload=None,
        module_uuid=None,
        shared_secret=None,
    ):
        """Call a signed module API v2 endpoint without exposing credentials."""
        self.ensure_one()

        retryable_codes = retry_error_codes or set()
        attempts = 2 if retry_network or retryable_codes else 1
        response = None
        response_payload = None
        request_module_uuid = module_uuid or self.module_uuid
        request_shared_secret = shared_secret or self.shared_secret

        for attempt in range(attempts):
            body, headers = build_signed_request(
                request_module_uuid,
                request_shared_secret,
                path,
                payload=payload,
            )
            try:
                response = requests.post(
                    f"{self._get_app_url()}{path}",
                    data=body,
                    headers=headers,
                    timeout=timeout,
                )
            except requests.exceptions.RequestException as error:
                if retry_network and attempt + 1 < attempts:
                    continue

                _logger.warning(
                    '[OdooTranslate] Module API unavailable operation=%s exception=%s',
                    path.rsplit('/', 1)[-1],
                    error.__class__.__name__,
                )
                raise UserError(_(
                    'Could not connect to OdooTranslate. '
                    'No local connection data was changed.'
                )) from error

            try:
                response_payload = response.json()
            except ValueError as error:
                _logger.warning(
                    '[OdooTranslate] Invalid module API response operation=%s status=%s request_id=%s',
                    path.rsplit('/', 1)[-1],
                    response.status_code,
                    response.headers.get('X-OdooTranslate-Request-Id') or 'missing',
                )
                raise UserError(_(
                    'OdooTranslate returned an invalid response. '
                    'No local connection data was changed.'
                )) from error

            error = response_payload.get('error') if isinstance(response_payload, dict) else None
            error_code = error.get('code') if isinstance(error, dict) else None
            if (
                response.status_code == 409
                and error_code in retryable_codes
                and attempt + 1 < attempts
            ):
                continue

            break

        if response is None:
            raise UserError(_(
                'Could not connect to OdooTranslate. '
                'No local connection data was changed.'
            ))

        request_id = response.headers.get('X-OdooTranslate-Request-Id')

        if not isinstance(response_payload, dict):
            raise UserError(_(
                'OdooTranslate returned an invalid response. '
                'No local connection data was changed.'
            ))

        if not response.ok or response_payload.get('success') is not True:
            request_id = response_payload.get('request_id') or request_id
            _logger.warning(
                '[OdooTranslate] Module API rejected operation=%s status=%s request_id=%s',
                path.rsplit('/', 1)[-1],
                response.status_code,
                request_id or 'missing',
            )
            message = _(
                'OdooTranslate rejected the secure module request. '
                'Update or relink the module. No local connection data was changed.'
            )
            if request_id:
                message = _('%s Support request ID: %s') % (message, request_id)
            raise UserError(message)

        data = response_payload.get('data')
        if not isinstance(data, dict):
            raise UserError(_(
                'OdooTranslate returned an invalid response. '
                'No local connection data was changed.'
            ))

        return data

    @staticmethod
    def _validated_link_attempt_id(data):
        link_attempt_id = data.get('link_attempt_id')
        if not isinstance(link_attempt_id, str):
            return False

        try:
            canonical = str(uuid.UUID(link_attempt_id))
        except (ValueError, AttributeError):
            return False

        return canonical if link_attempt_id == canonical else False

    def is_same_link_generation(
        self,
        email,
        has_api_key,
        shared_secret,
        link_attempt_id,
        unlink_operation_id,
    ):
        """Return whether a consumed callback exactly matches the active link."""
        self.ensure_one()

        return (
            self.connection_status == 'connected'
            and self.linked_email == email
            and bool(self.has_api_key) == has_api_key
            and isinstance(self.shared_secret, str)
            and hmac.compare_digest(self.shared_secret, shared_secret)
            and self.link_attempt_id == link_attempt_id
            and self.unlink_operation_id == unlink_operation_id
        )

    def confirm_link(
        self,
        email,
        has_api_key=False,
        shared_secret=None,
        link_attempt_id=None,
        unlink_operation_id=None,
    ):
        """
        Called by the OdooTranslate app callback to confirm the link.
        This is triggered via the controller when user completes registration.
        """
        self.ensure_one()

        if self.connection_status != 'pending':
            _logger.warning('[OdooTranslate] Unexpected confirm_link state')
            return False

        # Check if token has expired (30 minutes max)
        if self.link_token_created_at:
            from datetime import datetime, timedelta
            token_age = fields.Datetime.now() - self.link_token_created_at
            if token_age > timedelta(minutes=30):
                _logger.warning('[OdooTranslate] Link token expired')
                self.write({
                    'connection_status': 'disconnected',
                    'link_token': False,
                    'link_token_created_at': False,
                })
                return False

        self.write({
            'connection_status': 'connected',
            'has_api_key': has_api_key,
            'linked_email': email,
            'connected_at': fields.Datetime.now(),
            'link_token': False,  # Clear the link token after use
            'link_token_created_at': False,
            'shared_secret': shared_secret,  # Store the shared secret for future HMAC verification
            'link_attempt_id': link_attempt_id,
            'unlink_operation_id': unlink_operation_id,
        })

        _logger.info('[OdooTranslate] Module link confirmed')
        return True

    def update_api_key_status(self, has_api_key):
        """
        Update the API key status (called by OdooTranslate app when user configures/removes key).
        """
        self.ensure_one()
        self.write({'has_api_key': has_api_key})
        _logger.info(f"[OdooTranslate] API key status updated: {has_api_key}")

    def action_remove_all_translations(self):
        """
        Remove all translations generated by this module.
        This clears all dynamic.translation records and field configurations.
        WARNING: This action cannot be undone!
        """
        self.ensure_one()
        
        translation_count = 0
        
        # Delete all dynamic translations
        translations = self.env['dynamic.translation'].sudo().search([])
        translation_count = len(translations)
        if translation_count > 0:
            translations.unlink()
            _logger.info(f"[OdooTranslate] Removed {translation_count} translation(s)")
        
        # Delete all field configurations (silently)
        configs = self.env['dynamic.translatable.field.config'].sudo().search([])
        if configs:
            configs.unlink()
            _logger.info(f"[OdooTranslate] Removed {len(configs)} field configuration(s)")
        
        if translation_count == 0:
            raise UserError(_('No translations to remove.'))
        
        # Return notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Translations Removed'),
                'message': _('All translations for non-natively translatable fields have been removed.'),
                'type': 'success',
                'sticky': False,
            }
        }
