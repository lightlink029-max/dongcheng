# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DynamicTranslatableFieldConfig(models.Model):
    _name = 'dynamic.translatable.field.config'
    _description = 'Configuration des Champs Traductibles Dynamiques'
    _rec_name = 'display_name'

    model_id = fields.Many2one(
        'ir.model',
        string='Modèle',
        required=True,
        ondelete='cascade',
        help='Sélectionnez le modèle contenant le champ'
    )

    model_name = fields.Char(
        related='model_id.model',
        string='Nom Technique du Modèle',
        store=True,
        readonly=True
    )

    field_id = fields.Many2one(
        'ir.model.fields',
        string='Champ',
        required=True,
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['char', 'text', 'html'])]",
        ondelete='cascade',
        help='Sélectionnez le champ à rendre traductible'
    )

    field_name = fields.Char(
        related='field_id.name',
        string='Nom Technique du Champ',
        store=True,
        readonly=True
    )

    field_description = fields.Char(
        related='field_id.field_description',
        string='Description du Champ',
        readonly=True
    )

    field_type = fields.Selection(
        related='field_id.ttype',
        string='Type de Champ',
        readonly=True
    )

    is_translatable = fields.Boolean(
        string='Est Traductible',
        default=False,
        help='Active/Désactive la traduction pour ce champ'
    )

    display_name = fields.Char(
        string='Nom Complet',
        compute='_compute_display_name',
        store=True
    )

    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('applied', 'Appliqué'),
        ('error', 'Erreur')
    ], string='État', default='draft', readonly=True)

    error_message = fields.Text(
        string='Message d\'Erreur',
        readonly=True,
        help='Détails de l\'erreur si l\'application a échoué'
    )

    active = fields.Boolean(
        string='Actif',
        default=True,
        help='Permet d\'archiver/désarchiver cette configuration'
    )

    _sql_constraints = [
        ('model_field_unique', 'unique(model_id, field_id)',
         'Cette configuration existe déjà pour ce modèle et ce champ!')
    ]

    @api.depends('model_id.name', 'field_id.field_description', 'field_id.name')
    def _compute_display_name(self):
        for record in self:
            if record.model_id and record.field_id:
                record.display_name = f"{record.model_id.name} - {record.field_id.field_description} ({record.field_id.name})"
            else:
                record.display_name = _('Nouvelle Configuration')

    def _apply_patch_for_model(self):
        """Applique le patch read() pour le modèle de cet enregistrement"""
        try:
            from . import translation_patch
            if self.model_name:
                field_names = self.search([
                    ('model_name', '=', self.model_name),
                    ('is_translatable', '=', True),
                    ('state', '=', 'applied')
                ]).mapped('field_name')
                translation_patch.apply_translation_patch(self.env, self.model_name, field_names)
        except Exception as e:
            _logger.error(f"[OdooTranslate] Erreur lors de l'application du patch: {e}")

    def _remove_patch_for_model(self):
        """Retire le patch read() si plus aucun champ n'est configuré pour ce modèle"""
        try:
            from . import translation_patch
            if self.model_name:
                # Vérifier s'il reste des configs actives pour ce modèle
                remaining = self.search([
                    ('model_name', '=', self.model_name),
                    ('is_translatable', '=', True),
                    ('state', '=', 'applied'),
                    ('id', '!=', self.id)
                ])
                if not remaining:
                    translation_patch.remove_translation_patch(self.env, self.model_name)
        except Exception as e:
            _logger.error(f"[OdooTranslate] Erreur lors du retrait du patch: {e}")

    def action_apply_translation(self):
        """Active la traduction pour le champ configuré"""
        for record in self:
            try:
                if not record.model_name or not record.field_name:
                    raise ValidationError(_("Modèle et champ requis"))
                
                # Vérifier que le modèle existe
                if record.model_name not in self.env:
                    raise ValidationError(_("Le modèle '%s' n'existe pas") % record.model_name)
                
                # Appliquer le patch sur le modèle
                record._apply_patch_for_model()
                
                record.is_translatable = True
                record.state = 'applied'
                record.error_message = False
                
            except Exception as e:
                record.state = 'error'
                record.error_message = str(e)
                _logger.error(f"[OdooTranslate] Erreur activation: {e}")
        
        return True

    def action_remove_translation(self):
        """Désactive la traduction pour le champ configuré"""
        for record in self:
            try:
                record.is_translatable = False
                record.state = 'draft'
                record.error_message = False
                
                # Vérifier s'il faut retirer le patch du modèle
                record._remove_patch_for_model()
                
            except Exception as e:
                record.state = 'error'
                record.error_message = str(e)
                _logger.error(f"[OdooTranslate] Erreur désactivation: {e}")
        
        return True

    def toggle_translation(self):
        """Bascule l'état de traduction du champ"""
        for record in self:
            if record.is_translatable:
                record.action_remove_translation()
            else:
                record.action_apply_translation()
        return True

    def toggle_active(self):
        """Bascule l'état actif/archivé de l'enregistrement"""
        for record in self:
            record.active = not record.active
        return True

    def unlink(self):
        """Surcharge pour nettoyer les patchs si nécessaire"""
        for record in self:
            if record.is_translatable and record.state == 'applied':
                try:
                    record._remove_patch_for_model()
                except Exception as e:
                    _logger.warning(f"[OdooTranslate] Erreur lors du nettoyage avant suppression: {e}")
        return super().unlink()

    # ==================== API METHODS ====================
    
    @api.model
    def enable_translation(self, model_name, field_name):
        """
        Active la traduction pour un champ via API.
        Crée la config si elle n'existe pas, sinon l'active.
        
        Args:
            model_name: Nom technique du modèle (ex: 'mail.message')
            field_name: Nom technique du champ (ex: 'body')
        
        Returns:
            dict: {'success': bool, 'config_id': int, 'message': str}
        
        Exemple d'appel XML-RPC:
            models.execute_kw(db, uid, password, 
                'dynamic.translatable.field.config', 'enable_translation',
                ['mail.message', 'body'])
        """
        try:
            # Vérifier que le modèle existe
            model = self.env['ir.model'].search([('model', '=', model_name)], limit=1)
            if not model:
                return {'success': False, 'config_id': None, 'message': f"Modèle '{model_name}' non trouvé"}
            
            # Vérifier que le champ existe
            field = self.env['ir.model.fields'].search([
                ('model_id', '=', model.id),
                ('name', '=', field_name),
                ('ttype', 'in', ['char', 'text', 'html'])
            ], limit=1)
            if not field:
                return {'success': False, 'config_id': None, 'message': f"Champ '{field_name}' non trouvé ou type non supporté"}
            
            # Chercher config existante (inclure les archivées pour éviter le duplicate key)
            config = self.with_context(active_test=False).search([
                ('model_id', '=', model.id),
                ('field_id', '=', field.id)
            ], limit=1)
            
            if config:
                # Réactiver si archivé
                if not config.active:
                    config.active = True
                # Appliquer si pas déjà actif
                if config.state != 'applied':
                    config.action_apply_translation()
                return {'success': True, 'config_id': config.id, 'message': 'Traduction activée'}
            else:
                # Créer et activer
                config = self.create({
                    'model_id': model.id,
                    'field_id': field.id,
                })
                config.action_apply_translation()
                return {'success': True, 'config_id': config.id, 'message': 'Configuration créée et traduction activée'}
                
        except Exception as e:
            _logger.error(f"[OdooTranslate] Erreur enable_translation: {e}")
            return {'success': False, 'config_id': None, 'message': str(e)}

    @api.model
    def disable_translation(self, model_name, field_name):
        """
        Désactive la traduction pour un champ via API.
        
        Args:
            model_name: Nom technique du modèle
            field_name: Nom technique du champ
        
        Returns:
            dict: {'success': bool, 'message': str}
        """
        try:
            config = self.search([
                ('model_name', '=', model_name),
                ('field_name', '=', field_name)
            ], limit=1)
            
            if not config:
                return {'success': False, 'message': 'Configuration non trouvée'}
            
            config.action_remove_translation()
            return {'success': True, 'message': 'Traduction désactivée'}
            
        except Exception as e:
            _logger.error(f"[OdooTranslate] Erreur disable_translation: {e}")
            return {'success': False, 'message': str(e)}

    @api.model
    def is_translation_enabled(self, model_name, field_name):
        """
        Vérifie si la traduction est activée pour un champ.
        
        Args:
            model_name: Nom technique du modèle
            field_name: Nom technique du champ
        
        Returns:
            dict: {'enabled': bool, 'config_id': int or None}
        """
        config = self.search([
            ('model_name', '=', model_name),
            ('field_name', '=', field_name),
            ('state', '=', 'applied'),
            ('is_translatable', '=', True)
        ], limit=1)
        
        return {
            'enabled': bool(config),
            'config_id': config.id if config else None
        }

