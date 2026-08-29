# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _


_logger = logging.getLogger(__name__)


class DynamicTranslation(models.Model):
    _name = 'dynamic.translation'
    _description = 'Traductions Dynamiques'
    _rec_name = 'display_name'

    model_name = fields.Char(
        string='Modèle',
        required=True,
        index=True,
        help='Nom technique du modèle (ex: mail.message)'
    )

    field_name = fields.Char(
        string='Champ',
        required=True,
        index=True,
        help='Nom technique du champ (ex: body)'
    )

    res_id = fields.Integer(
        string='ID Enregistrement',
        required=True,
        index=True,
        help='ID de l\'enregistrement traduit'
    )

    lang = fields.Selection(
        selection='_get_languages',
        string='Langue',
        required=True,
        index=True,
        help='Code de la langue (ex: fr_FR, en_US)'
    )

    source = fields.Text(
        string='Source',
        help='Texte original (optionnel, pour référence)'
    )

    value = fields.Text(
        string='Traduction',
        required=True,
        help='Texte traduit'
    )

    # Author tracking fields - to differentiate author view from recipient view
    author_partner_id = fields.Many2one(
        'res.partner',
        string='Auteur (Partner)',
        index=True,
        help='Partenaire auteur du message original (pour mail.message)'
    )

    author_guest_id = fields.Many2one(
        'mail.guest',
        string='Auteur (Guest)',
        index=True,
        help='Visiteur auteur du message original (pour livechat)'
    )

    is_author_view = fields.Boolean(
        string='Vue Auteur',
        default=False,
        index=True,
        help='True si cette traduction est pour la vue auteur (original visible par défaut)'
    )

    display_name = fields.Char(
        string='Nom',
        compute='_compute_display_name',
        store=True
    )

    @api.model
    def _get_languages(self):
        """Récupère les langues installées"""
        langs = self.env['res.lang'].search([('active', '=', True)])
        return [(lang.code, lang.name) for lang in langs]

    @api.depends('model_name', 'field_name', 'res_id', 'lang')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.model_name}.{record.field_name} [{record.res_id}] ({record.lang})"

    _sql_constraints = [
        ('unique_translation', 'unique(model_name, field_name, res_id, lang, is_author_view)',
         'Une traduction existe déjà pour cet enregistrement, ce champ, cette langue et ce type de vue!')
    ]

    @api.model
    def get_translation(self, model_name, field_name, res_id, lang):
        """
        Récupère une traduction.
        
        Args:
            model_name: Nom du modèle
            field_name: Nom du champ
            res_id: ID de l'enregistrement
            lang: Code langue
        
        Returns:
            str ou None: La traduction si trouvée
        """
        translation = self.sudo().search([
            ('model_name', '=', model_name),
            ('field_name', '=', field_name),
            ('res_id', '=', res_id),
            ('lang', '=', lang),
        ], limit=1)
        return translation.value if translation else None

    @api.model
    def get_translations_batch(self, model_name, field_names, res_ids, lang, partner_id=None, guest_id=None):
        """
        Récupère plusieurs traductions en une seule requête.
        
        Pour mail.message, on vérifie si l'utilisateur est l'auteur du message.
        Si oui, on retourne la traduction "author view" (is_author_view=True).
        Sinon, on retourne la traduction "recipient view" (is_author_view=False).
        
        Args:
            model_name: Nom du modèle
            field_names: Liste des noms de champs
            res_ids: Liste des IDs d'enregistrements
            lang: Code langue
            partner_id: ID du partner actuel (optionnel, pour détection auteur)
            guest_id: ID du guest actuel (optionnel, pour détection auteur livechat)
        
        Returns:
            dict: {res_id: {field_name: value}}
        """
        result = {}
        
        if model_name == 'mail.message' and (partner_id or guest_id):
            # Pour mail.message, on doit vérifier message par message si l'utilisateur est l'auteur
            for res_id in res_ids:
                # Vérifier si le message a été écrit par cet utilisateur
                message = self.env['mail.message'].sudo().browse(res_id)
                if not message.exists():
                    continue
                
                is_author = False
                # mail.message.author_id est un Many2one vers res.partner
                if partner_id and message.author_id and message.author_id.id == partner_id:
                    is_author = True
                # mail.message.author_guest_id est un Many2one vers mail.guest (pour livechat)
                elif guest_id and message.author_guest_id and message.author_guest_id.id == guest_id:
                    is_author = True
                
                # Rechercher TOUTES les traductions appropriées (pas limit=1)
                translations = self.sudo().search([
                    ('model_name', '=', model_name),
                    ('field_name', 'in', field_names),
                    ('res_id', '=', res_id),
                    ('lang', '=', lang),
                    ('is_author_view', '=', is_author),
                ])
                
                for trans in translations:
                    if res_id not in result:
                        result[res_id] = {}
                    result[res_id][trans.field_name] = trans.value
        else:
            # Comportement standard pour les autres modèles (recipient view uniquement)
            translations = self.sudo().search([
                ('model_name', '=', model_name),
                ('field_name', 'in', field_names),
                ('res_id', 'in', res_ids),
                ('lang', '=', lang),
                ('is_author_view', '=', False),
            ])
            
            for trans in translations:
                if trans.res_id not in result:
                    result[trans.res_id] = {}
                result[trans.res_id][trans.field_name] = trans.value
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Override create pour notifier via le bus"""
        records = super().create(vals_list)
        self._notify_translations(records)
        return records

    def write(self, vals):
        """Override write pour notifier via le bus si la valeur change"""
        result = super().write(vals)
        if 'value' in vals:
            self._notify_translations(self)
        return result

    def _notify_translations(self, records):
        """
        Route les mises à jour mail.message vers les identités privées autorisées.

        Une panne du bus ne doit jamais annuler la traduction déjà persistée.
        """
        for record in records:
            if record.model_name != 'mail.message':
                continue

            try:
                self.env['odoo_translate.chat.notification.router'].notify(record)
            except Exception as error:
                _logger.error(
                    '[OdooTranslate] event=chat_translation_notification_failed '
                    'stage=router_invocation translation_id=%s message_id=%s lang=%s '
                    'error_type=%s',
                    record.id,
                    record.res_id,
                    record.lang,
                    type(error).__name__,
                )

    @api.model
    def set_translation(self, model_name, field_name, res_id, lang, value, source=None):
        """
        Crée ou met à jour une traduction.
        
        Args:
            model_name: Nom du modèle
            field_name: Nom du champ
            res_id: ID de l'enregistrement
            lang: Code langue
            value: Traduction
            source: Texte source (optionnel)
        
        Returns:
            dynamic.translation: L'enregistrement créé/mis à jour
        """
        existing = self.sudo().search([
            ('model_name', '=', model_name),
            ('field_name', '=', field_name),
            ('res_id', '=', res_id),
            ('lang', '=', lang),
        ], limit=1)
        
        vals = {'value': value}
        if source:
            vals['source'] = source
        
        if existing:
            existing.write(vals)
            return existing
        else:
            vals.update({
                'model_name': model_name,
                'field_name': field_name,
                'res_id': res_id,
                'lang': lang,
            })
            return self.sudo().create(vals)
