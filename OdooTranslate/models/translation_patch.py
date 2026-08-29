# -*- coding: utf-8 -*-
import re
import json
import threading
from markupsafe import Markup

# Flag pour savoir si BaseModel est déjà patché
_basemodel_patched = False
_original_read = None
_original_read_format = None

# Flag pour le patch write() de knowledge.article
_knowledge_write_patched = False
_original_knowledge_write = None

# Flag pour éviter la récursion (thread-local)
_translation_check_local = threading.local()

# Champs à intercepter pour le write back-office
BACKOFFICE_TRANSLATED_FIELDS = {'body', 'name'}


def _get_current_lang(env, guest_id=None):
    """
    Récupère la langue courante depuis plusieurs sources possibles :
    0. mail.guest.lang (si guest_id fourni - PRIORITAIRE pour livechat)
    1. env.user.lang (utilisateur connecté non-public - PRIORITAIRE)
    2. website.visitor.lang_id (visiteur anonyme)
    3. env.lang / env.context.get('lang') (contexte Odoo)
    4. request.env.lang (contexte HTTP/web)
    5. request.httprequest (URL comme /de/...)
    """
    # 0. Guest livechat - PRIORITAIRE pour les visiteurs livechat
    if guest_id:
        try:
            if 'mail.guest' in env:
                guest = env['mail.guest'].sudo().browse(guest_id)
                if guest.exists() and guest.lang:
                    return guest.lang
        except Exception:
            pass
    
    # 1. Utilisateur connecté (non-public) - PRIORITAIRE
    try:
        if env.user and not env.user._is_public() and env.user.lang:
            return env.user.lang
    except Exception:
        pass
    
    # 2. Visiteur anonyme - récupérer la langue depuis le contexte ou la session
    # IMPORTANT: On n'appelle PAS _get_visitor_from_request() ici car cela peut
    # interférer avec le processus de création de visiteur et causer des problèmes
    # de performance. On utilise plutôt les sources de langue déjà disponibles.
    try:
        from odoo.http import request
        
        # Essayer de récupérer la langue depuis la session du visiteur
        if request and hasattr(request, 'session'):
            visitor_lang = request.session.get('visitor_lang')
            if visitor_lang:
                return visitor_lang
    except Exception:
        pass
    
    # 3. Source standard: env.lang
    if env.lang:
        return env.lang
    
    # 4. Contexte explicite
    if env.context.get('lang'):
        return env.context.get('lang')
    
    # 5. Essayer via la requête HTTP (site web)
    try:
        from odoo.http import request
        
        # 5a. Contexte HTTP standard
        if request and hasattr(request, 'env') and request.env.lang:
            return request.env.lang
        
        # 5b. Récupérer depuis l'URL (ex: /de/knowledge/...)
        if request and hasattr(request, 'httprequest'):
            path = request.httprequest.path or ''
            # Format: /lang_code/... (ex: /de/, /fr/, /en/)
            parts = path.split('/')
            if len(parts) > 1 and parts[1]:
                lang_code = parts[1]
                # Vérifier si c'est un code langue valide (2 lettres ou xx_XX)
                if len(lang_code) == 2:
                    # Convertir code court en code Odoo (de -> de_DE)
                    lang_mapping = {
                        'de': 'de_DE',
                        'fr': 'fr_FR',
                        'en': 'en_US',
                        'es': 'es_ES',
                        'it': 'it_IT',
                        'nl': 'nl_NL',
                        'pt': 'pt_PT',
                        'pl': 'pl_PL',
                        'ru': 'ru_RU',
                        'zh': 'zh_CN',
                        'ja': 'ja_JP',
                        'ko': 'ko_KR',
                        'ar': 'ar_001',
                        'he': 'he_IL',
                        'tr': 'tr_TR',
                        'vi': 'vi_VN',
                        'th': 'th_TH',
                        'uk': 'uk_UA',
                        'cs': 'cs_CZ',
                        'ro': 'ro_RO',
                        'hu': 'hu_HU',
                        'sv': 'sv_SE',
                        'da': 'da_DK',
                        'fi': 'fi_FI',
                        'no': 'nb_NO',
                        'el': 'el_GR',
                        'bg': 'bg_BG',
                        'hr': 'hr_HR',
                        'sk': 'sk_SK',
                        'sl': 'sl_SI',
                        'et': 'et_EE',
                        'lv': 'lv_LV',
                        'lt': 'lt_LT',
                    }
                    if lang_code in lang_mapping:
                        return lang_mapping[lang_code]
                elif '_' in lang_code and len(lang_code) == 5:
                    # Déjà au format xx_XX
                    return lang_code
    except Exception:
        pass
    
    return None


def _get_lang_code_short(odoo_lang, env=None):
    """Convertit un code Odoo (en_US) en code URL (récupère url_code depuis res.lang)."""
    if not odoo_lang:
        return None
    
    # Try to get the actual url_code from Odoo's res.lang
    if env:
        try:
            env.cr.execute("""
                SELECT url_code FROM res_lang WHERE code = %s AND active = true LIMIT 1
            """, (odoo_lang,))
            result = env.cr.fetchone()
            if result and result[0]:
                return result[0]
        except Exception:
            pass
    
    # Fallback: use mapping
    lang_mapping = {
        'de_DE': 'de', 'fr_FR': 'fr', 'en_US': 'en', 'es_ES': 'es',
        'it_IT': 'it', 'nl_NL': 'nl', 'pt_PT': 'pt', 'pl_PL': 'pl',
        'ru_RU': 'ru', 'zh_CN': 'zh', 'ja_JP': 'ja', 'ko_KR': 'ko',
        'ar_001': 'ar', 'he_IL': 'he', 'tr_TR': 'tr', 'vi_VN': 'vi',
        'th_TH': 'th', 'uk_UA': 'uk', 'cs_CZ': 'cs', 'ro_RO': 'ro',
        'hu_HU': 'hu', 'sv_SE': 'sv', 'da_DK': 'da', 'fi_FI': 'fi',
        'nb_NO': 'no', 'el_GR': 'el', 'bg_BG': 'bg', 'hr_HR': 'hr',
        'sk_SK': 'sk', 'sl_SI': 'sl', 'et_EE': 'et', 'lv_LV': 'lv',
        'lt_LT': 'lt',
    }
    return lang_mapping.get(odoo_lang, odoo_lang[:2].lower() if len(odoo_lang) >= 2 else None)


def _post_process_body_html(html_str, env, lang):
    """
    Post-traite le body HTML pour traduire les liens d'articles embedded.
    Structure: data-embedded="articleIndex" avec JSON dans data-embedded-props
    Le JS génère les liens à partir du JSON, donc on doit modifier le JSON.
    """
    if not html_str or 'data-embedded="articleIndex"' not in html_str:
        return html_str
    
    try:
        # Extraire les IDs d'articles depuis le JSON data-embedded-props
        # Handle both single and double quote formats separately
        article_ids = []
        
        # Format 1: Single quotes (content can have " inside): data-embedded-props='...'
        for props_match in re.finditer(r"data-embedded-props='([^']+)'", html_str):
            try:
                props_str = props_match.group(1).replace('\\"', '"')
                props = json.loads(props_str)
                if 'articles' in props:
                    for article in props['articles']:
                        if 'id' in article:
                            article_ids.append(article['id'])
            except Exception:
                pass
        
        # Format 2: Double quotes with HTML entities: data-embedded-props="..."
        for props_match in re.finditer(r'data-embedded-props="([^"]+)"', html_str):
            try:
                props_str = props_match.group(1).replace('&quot;', '"')
                props = json.loads(props_str)
                if 'articles' in props:
                    for article in props['articles']:
                        if 'id' in article:
                            article_ids.append(article['id'])
            except Exception:
                pass
        
        if not article_ids:
            return html_str
        
        # Récupérer les traductions des noms
        env.cr.execute("""
            SELECT res_id, value FROM dynamic_translation 
            WHERE model_name = 'knowledge.article' 
            AND field_name = 'name'
            AND res_id = ANY(%s) AND lang = %s
        """, (article_ids, lang))
        translations = {row[0]: row[1] for row in env.cr.fetchall()}
        
        # Helper function to clean technical prefix from article names
        # E.g., "'website.page' | Pages" → "Pages"
        # E.g., "📄 'website.page' | Pages" → "📄 Pages"
        def clean_article_name(name):
            if not name:
                return name
            import re as re_module
            # Pattern: optional prefix (like emoji) + 'technical.name' | Human readable
            match = re_module.match(r"^(.*?)'[a-z_.]+'\s*\|\s*(.+)$", name, re_module.IGNORECASE)
            if match:
                prefix = match.group(1).strip()
                human_part = match.group(2).strip()
                # Keep emoji prefix if present
                if prefix:
                    return prefix + ' ' + human_part
                return human_part
            return name
        
        # Mettre à jour le JSON dans data-embedded-props (double quotes format)
        def update_embedded_props_double(m):
            try:
                props_str = m.group(1).replace('&quot;', '"')
                props = json.loads(props_str)
                modified = False
                if 'articles' in props:
                    for article in props['articles']:
                        article_id = article.get('id')
                        if article_id in translations:
                            article['name'] = translations[article_id]
                            modified = True
                        else:
                            original_name = article.get('name', '')
                            cleaned_name = clean_article_name(original_name)
                            if cleaned_name != original_name:
                                article['name'] = cleaned_name
                                modified = True
                if modified:
                    return 'data-embedded-props="' + json.dumps(props, ensure_ascii=False).replace('"', '&quot;') + '"'
                return m.group(0)
            except Exception:
                return m.group(0)
        
        # Mettre à jour le JSON dans data-embedded-props (single quotes format)
        # In HTML single-quoted attributes, raw " is valid, but ' must be escaped as &#39;
        def update_embedded_props_single(m):
            try:
                props_str = m.group(1).replace('\\"', '"')
                props = json.loads(props_str)
                modified = False
                if 'articles' in props:
                    for article in props['articles']:
                        article_id = article.get('id')
                        if article_id in translations:
                            article['name'] = translations[article_id]
                            modified = True
                        else:
                            original_name = article.get('name', '')
                            cleaned_name = clean_article_name(original_name)
                            if cleaned_name != original_name:
                                article['name'] = cleaned_name
                                modified = True
                if modified:
                    # In single-quoted HTML attrs: " is fine, escape ' as &#39;
                    json_str = json.dumps(props, ensure_ascii=False).replace("'", "&#39;")
                    return "data-embedded-props='" + json_str + "'"
                return m.group(0)
            except Exception:
                return m.group(0)
        
        # Apply both replacements
        html_str = re.sub(r'data-embedded-props="([^"]+)"', update_embedded_props_double, html_str)
        html_str = re.sub(r"data-embedded-props='([^']+)'", update_embedded_props_single, html_str)
        
        return html_str
        
    except Exception:
        return html_str


def _get_current_user_ids(env):
    """
    Récupère le partner_id et guest_id de l'utilisateur/visiteur courant.
    Utilisé pour déterminer si on doit afficher la vue auteur ou destinataire.
    
    Returns:
        tuple: (partner_id, guest_id) - l'un ou l'autre sera None
    """
    partner_id = None
    guest_id = None
    
    try:
        # 1. Utilisateur connecté (non-public)
        if env.user and not env.user._is_public() and env.user.partner_id:
            partner_id = env.user.partner_id.id
            return (partner_id, guest_id)
    except Exception:
        pass
    
    # 2. Visiteur livechat (mail.guest) - utiliser la méthode native Odoo
    try:
        if 'mail.guest' in env:
            guest = env['mail.guest']._get_guest_from_context()
            if guest:
                guest_id = guest.id
                return (partner_id, guest_id)
    except Exception:
        pass
    
    # 3. Fallback: essayer via le contexte request
    try:
        from odoo.http import request
        if request and hasattr(request, 'env'):
            # Essayer de récupérer le guest depuis le contexte ou la session
            guest_id_from_context = request.env.context.get('guest_id')
            if guest_id_from_context:
                guest_id = guest_id_from_context
                return (partner_id, guest_id)
            
            # Ou depuis la session
            if hasattr(request, 'session') and request.session.get('guest_id'):
                guest_id = request.session.get('guest_id')
                return (partner_id, guest_id)
    except Exception:
        pass
    
    return (partner_id, guest_id)


def _inject_translations(env, model_name, result, fields=None):
    """
    Fonction utilitaire pour injecter les traductions dans un résultat.
    Vérifie dynamiquement en DB si le modèle/champ est configuré.
    
    Pour mail.message, détermine si l'utilisateur est l'auteur pour afficher
    la bonne vue (auteur ou destinataire).
    """
    if not result:
        return result
    
    # Skip injection when Nodie reads via XML-RPC (to get original values)
    if env.context.get('skip_ai_translation'):
        return result
    
    # S'assurer que le patch BaseModel est appliqué dans ce worker
    # (nécessaire car Odoo utilise multiprocessing et chaque worker a sa propre mémoire)
    apply_basemodel_patch()
    
    # Récupérer partner_id et guest_id pour détection auteur (mail.message)
    # On le fait EN PREMIER pour pouvoir utiliser guest_id pour la langue
    partner_id, guest_id = _get_current_user_ids(env)
    
    # Récupérer la langue depuis toutes les sources possibles
    # Si on a un guest_id, utiliser la langue du guest en priorité
    lang = _get_current_lang(env, guest_id=guest_id)
    if not lang:
        return result
    
    try:
        # Vérifier que nos modèles existent
        if 'dynamic.translatable.field.config' not in env:
            return result
        
        config_model = env['dynamic.translatable.field.config']
        
        # Vérifier si ce modèle a des traductions configurées
        configs = config_model.sudo().search([
            ('model_name', '=', model_name),
            ('is_translatable', '=', True),
            ('state', '=', 'applied')
        ])
        
        if not configs:
            return result
        
        configured_fields = configs.mapped('field_name')
        
        # Filtrer les champs demandés
        fields_to_translate = configured_fields
        if fields:
            fields_to_translate = [f for f in configured_fields if f in fields]
        
        if not fields_to_translate:
            return result
        
        # Récupérer les IDs
        record_ids = [r['id'] for r in result if 'id' in r]
        if not record_ids:
            return result
        
        # Utiliser notre modèle dynamic.translation
        if 'dynamic.translation' not in env:
            return result
        
        translation_model = env['dynamic.translation']
        
        translations = translation_model.get_translations_batch(
            model_name,
            fields_to_translate,
            record_ids,
            lang,
            partner_id=partner_id,
            guest_id=guest_id
        )
        
        # Injecter les traductions
        for record in result:
            record_id = record.get('id')
            if record_id in translations:
                for field_name, value in translations[record_id].items():
                    if value and field_name in record:
                        record[field_name] = value
                        
    except Exception:
        pass
    
    return result


def _get_source_language(env):
    """
    Récupère la langue source (langue de base des articles originaux).
    Utilise la langue par défaut du website si disponible, sinon fr_FR.
    """
    try:
        if 'website' in env:
            website = env['website'].get_current_website()
            if website and website.default_lang_id:
                return website.default_lang_id.code
    except Exception:
        pass
    
    # Fallback
    return 'fr_FR'


def _is_backoffice_context(env):
    """
    Vérifie si on est dans un contexte back-office (utilisateur connecté non-public).
    """
    try:
        if env.user and not env.user._is_public():
            return True
    except Exception:
        pass
    return False


def apply_knowledge_write_patch():
    """
    Applique le patch sur knowledge.article.write() pour rediriger les modifications
    vers dynamic.translation quand l'utilisateur est dans une langue traduite.
    
    Stratégie: Laisser le write() passer normalement (pour ne pas casser la collaboration),
    puis restaurer les valeurs originales et sauvegarder les nouvelles dans dynamic.translation.
    """
    global _knowledge_write_patched, _original_knowledge_write
    
    try:
        from odoo.addons.knowledge.models.knowledge_article import Article as KnowledgeArticle
        
        # Vérifier si déjà patché
        if hasattr(KnowledgeArticle.write, '_odoo_translate_patched'):
            _knowledge_write_patched = True
            return
        
        _original_knowledge_write = KnowledgeArticle.write
        
        def patched_knowledge_write(self, vals):
            """
            Intercepte write() pour sauvegarder dans dynamic.translation
            si l'utilisateur est dans une langue différente de la source.
            """
            # Vérifier si on a des champs à intercepter
            fields_to_intercept = BACKOFFICE_TRANSLATED_FIELDS & set(vals.keys())
            
            if not fields_to_intercept:
                return _original_knowledge_write(self, vals)
            
            # Vérifier si on est en back-office
            if not _is_backoffice_context(self.env):
                return _original_knowledge_write(self, vals)
            
            # Récupérer la langue courante de l'utilisateur
            current_lang = _get_current_lang(self.env)
            source_lang = _get_source_language(self.env)
            
            if not current_lang or current_lang == source_lang:
                return _original_knowledge_write(self, vals)
            
            # Vérifier que le modèle dynamic.translation existe
            if 'dynamic.translation' not in self.env:
                return _original_knowledge_write(self, vals)
            
            # 1. Sauvegarder les nouvelles valeurs dans dynamic.translation
            translation_model = self.env['dynamic.translation']
            for record in self:
                for field_name in fields_to_intercept:
                    if field_name in vals:
                        translation_model.set_translation(
                            model_name='knowledge.article',
                            field_name=field_name,
                            res_id=record.id,
                            lang=current_lang,
                            value=vals[field_name],
                            source=None
                        )
            
            # 2. Retirer body/name des vals pour ne PAS modifier l'original
            filtered_vals = {k: v for k, v in vals.items() if k not in fields_to_intercept}
            
            # 3. Si il reste des vals à écrire (icon, is_published, etc.), les écrire
            if filtered_vals:
                return _original_knowledge_write(self, filtered_vals)
            
            return True
        
        patched_knowledge_write._odoo_translate_patched = True
        KnowledgeArticle.write = patched_knowledge_write
        _knowledge_write_patched = True
        
    except ImportError:
        pass
    except Exception:
        pass


def apply_basemodel_patch():
    """
    Applique le patch sur BaseModel.read(), _read_format() et l'accès direct aux champs.
    Appelé UNE SEULE FOIS au chargement du module Python.
    IMPORTANT: Vérifie si vraiment patché car multiprocessing peut causer des problèmes.
    """
    global _basemodel_patched, _original_read, _original_read_format
    
    try:
        from odoo import models
        from odoo.fields import Field
        
        # Vérifier si VRAIMENT patché en regardant un marqueur sur la méthode
        if hasattr(models.BaseModel.read, '_odoo_translate_patched'):
            _basemodel_patched = True
            return
        
        # Sauvegarder les méthodes originales
        _original_read = models.BaseModel.read
        _original_read_format = models.BaseModel._read_format
        
        # Patch de read()
        def patched_read(self, fields=None, load='_classic_read'):
            result = _original_read(self, fields, load)
            return _inject_translations(self.env, self._name, result, fields)
        
        # Marquer comme patché
        patched_read._odoo_translate_patched = True
        
        # Patch de _read_format()
        def patched_read_format(self, fnames, load='_classic_read'):
            result = _original_read_format(self, fnames, load)
            return _inject_translations(self.env, self._name, result, fnames)
        
        # Patch pour l'accès direct aux champs (article.body)
        _original_field_get = Field.__get__
        
        def patched_field_get(self, record=None, owner=None):
            """Intercepte l'accès direct aux champs pour injecter les traductions."""
            # Appeler l'original d'abord
            value = _original_field_get(self, record, owner)
            
            # Vérifications rapides sans accès ORM
            if record is None:
                return value
            
            # Vérifier si on est déjà en train de checker (éviter récursion)
            if not hasattr(_translation_check_local, 'in_check'):
                _translation_check_local.in_check = False
            
            if _translation_check_local.in_check:
                return value
            
            # Vérification basique sans toucher à l'ORM
            try:
                model_name = object.__getattribute__(record, '_name')
                field_name = self.name
            except Exception:
                return value
            
            # Liste blanche des modèles à traduire (pour éviter les requêtes inutiles)
            # On vérifie uniquement knowledge.article pour l'instant
            if model_name != 'knowledge.article':
                return value
            
            if field_name not in ('body', 'name'):
                return value
            
            try:
                _translation_check_local.in_check = True
                
                # Obtenir l'ID sans passer par __getattr__
                try:
                    ids = object.__getattribute__(record, '_ids')
                    if not ids or len(ids) != 1:
                        return value
                    record_id = ids[0]
                except Exception:
                    return value
                
                # Récupérer la langue
                try:
                    env = object.__getattribute__(record, 'env')
                    lang = _get_current_lang(env)
                except Exception:
                    return value
                
                if not lang:
                    return value
                
                # SQL direct pour la traduction
                try:
                    cr = env.cr
                    cr.execute("""
                        SELECT value FROM dynamic_translation 
                        WHERE model_name = %s 
                        AND field_name = %s 
                        AND res_id = %s 
                        AND lang = %s
                        LIMIT 1
                    """, (model_name, field_name, record_id, lang))
                    
                    result = cr.fetchone()
                    if result and result[0]:
                        # Retourner comme Markup pour le HTML (body), texte simple sinon
                        if field_name == 'body':
                            # Post-traiter pour traduire les liens d'articles embedded
                            translated_body = _post_process_body_html(result[0], env, lang)
                            return Markup(translated_body)
                        return result[0]
                    elif field_name == 'body' and value:
                        # Même sans traduction du body, post-traiter pour les liens embedded
                        html_value = str(value) if not isinstance(value, str) else value
                        processed = _post_process_body_html(html_value, env, lang)
                        if processed != html_value:
                            return Markup(processed)
                except Exception:
                    pass
                    
            except Exception:
                pass
            finally:
                _translation_check_local.in_check = False
            
            return value
        
        # Appliquer les patchs
        models.BaseModel.read = patched_read
        models.BaseModel._read_format = patched_read_format
        Field.__get__ = patched_field_get
        
        _basemodel_patched = True
        
    except Exception:
        pass


def remove_basemodel_patch():
    """
    Retire le patch de BaseModel (pour désinstallation).
    """
    global _basemodel_patched, _original_read, _original_read_format
    
    if not _basemodel_patched:
        return
    
    try:
        from odoo import models
        
        if _original_read:
            models.BaseModel.read = _original_read
        if _original_read_format:
            models.BaseModel._read_format = _original_read_format
        
        _basemodel_patched = False
        _original_read = None
        _original_read_format = None
        
    except Exception:
        pass


# ============================================================
# Fonctions de compatibilité (appelées par field_config.py)
# ============================================================

def apply_translation_patch(env, model_name, field_names):
    """Compatibilité - le patch est maintenant global sur BaseModel"""
    apply_basemodel_patch()
    return True


def remove_translation_patch(env, model_name):
    """Compatibilité - ne fait rien car le patch est global"""
    return True


def remove_all_patches(env):
    """Retire le patch global"""
    remove_basemodel_patch()


def apply_all_configured_patches(env):
    """Applique le patch global (vérifie juste qu'il est actif)"""
    apply_basemodel_patch()

