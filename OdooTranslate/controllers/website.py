# -*- coding: utf-8 -*-
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Vérifier si le module website est installé
try:
    from odoo.addons.website.controllers.main import Website
    _WEBSITE_INSTALLED = True
except ImportError:
    _WEBSITE_INSTALLED = False
    _logger.info("[OdooTranslate] Module website non installé, controller website ignoré")


def _update_visitor_language(env, visitor, lang_code):
    """
    Met à jour la langue d'un visiteur existant.
    Met aussi à jour le mail.guest associé aux canaux livechat actifs.
    
    Args:
        env: Odoo environment
        visitor: recordset website.visitor
        lang_code: Code de la nouvelle langue (ex: 'fr_FR', 'en_US')
        
    Returns:
        bool: True si la mise à jour a réussi, False sinon
    """
    try:
        if not visitor or not visitor.id:
            return False
        
        # Vérifier que la langue existe et est active
        lang = env['res.lang'].sudo().search([
            ('code', '=', lang_code),
            ('active', '=', True)
        ], limit=1)
        
        if not lang:
            _logger.warning(f"[OdooTranslate] Langue {lang_code} non trouvée ou inactive")
            return False
        
        # Mettre à jour la langue du visiteur
        old_lang = visitor.lang_id.code if visitor.lang_id else 'None'
        visitor.sudo().write({'lang_id': lang.id})
        
        _logger.info(
            f"[OdooTranslate] Langue du visiteur {visitor.id} mise à jour: "
            f"{old_lang} -> {lang_code}"
        )
        
        # Si le visiteur a un partenaire associé, mettre à jour aussi sa langue
        if visitor.partner_id:
            visitor.partner_id.sudo().write({'lang': lang_code})
            _logger.info(
                f"[OdooTranslate] Langue du partenaire {visitor.partner_id.id} "
                f"({visitor.partner_id.name}) mise à jour: {lang_code}"
            )
        
        # Mettre à jour la langue des mail.guest dans les canaux livechat actifs
        # Le guest est créé pour les visiteurs non-connectés dans les livechats
        try:
            guest = env['mail.guest']._get_guest_from_context()
            if guest:
                guest.sudo().write({'lang': lang_code})
                _logger.info(
                    f"[OdooTranslate] Langue du guest {guest.id} mise à jour: {lang_code}"
                )
            else:
                # Chercher les guests liés aux livechats du visiteur
                if hasattr(visitor, 'discuss_channel_ids'):
                    for channel in visitor.sudo().discuss_channel_ids:
                        if channel.channel_type == 'livechat' and not channel.livechat_end_dt:
                            for member in channel.channel_member_ids:
                                if member.guest_id:
                                    member.guest_id.sudo().write({'lang': lang_code})
                                    _logger.info(
                                        f"[OdooTranslate] Langue du guest {member.guest_id.id} "
                                        f"(canal {channel.id}) mise à jour: {lang_code}"
                                    )
        except Exception as e:
            _logger.warning(f"[OdooTranslate] Erreur mise à jour langue guest: {e}")
        
        return True
        
    except Exception as e:
        _logger.error(f"[OdooTranslate] Erreur lors de la mise à jour de la langue: {e}")
        return False


if _WEBSITE_INSTALLED:
    class WebsiteLanguageSync(Website):
        """
        Override du controller Website pour synchroniser la langue du visiteur
        quand il change la langue du site.
        """

        @http.route()
        def change_lang(self, lang, r='/', **kwargs):
            """
            Override de la méthode de changement de langue.
            Met à jour la langue du visiteur ANONYME avant de rediriger.
            
            Les utilisateurs connectés gèrent leur propre préférence de langue,
            on ne la modifie pas automatiquement.
            
            :param lang: supposed to be value of `url_code` field
            """
            # Récupérer le code langue complet depuis url_code
            lang_code = request.env['res.lang']._get_data(url_code=lang).code or lang
            
            _logger.info(f"[OdooTranslate] Changement de langue détecté: {lang} -> {lang_code}")
            
            # Ne mettre à jour que pour les visiteurs ANONYMES (non connectés)
            try:
                # Vérifier si l'utilisateur est connecté (non-public)
                if request.env.user and not request.env.user._is_public():
                    _logger.debug(
                        f"[OdooTranslate] Utilisateur connecté ({request.env.user.login}), "
                        "pas de mise à jour automatique de la langue"
                    )
                elif 'website.visitor' in request.env:
                    # Utilisateur anonyme - mettre à jour la langue du visiteur
                    visitor = request.env['website.visitor']._get_visitor_from_request()
                    
                    if visitor and visitor.id:
                        _logger.info(
                            f"[OdooTranslate] Visiteur anonyme détecté: {visitor.id}, "
                            f"mise à jour de la langue vers {lang_code}"
                        )
                        _update_visitor_language(request.env, visitor, lang_code)
                    else:
                        _logger.debug("[OdooTranslate] Aucun visiteur existant à mettre à jour")
                else:
                    _logger.debug("[OdooTranslate] Modèle website.visitor non disponible")
                    
            except Exception as e:
                _logger.warning(f"[OdooTranslate] Erreur lors de la mise à jour de la langue du visiteur: {e}")
            
            # Appeler la méthode parente pour effectuer le changement de langue standard
            return super().change_lang(lang, r=r, **kwargs)
