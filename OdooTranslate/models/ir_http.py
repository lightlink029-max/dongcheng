# -*- coding: utf-8 -*-
"""
Module ir_http pour OdooTranslate.
Intercepte les réponses HTTP pour traduire la sidebar Knowledge.
"""
import os
import re
from markupsafe import Markup

# Workers déjà patchés (évite de re-patcher)
_patched_workers = set()

# Mapping codes langue courts -> codes Odoo
LANG_MAPPING = {
    'de': 'de_DE', 'fr': 'fr_FR', 'en': 'en_US', 'es': 'es_ES',
    'it': 'it_IT', 'nl': 'nl_NL', 'pt': 'pt_PT', 'pl': 'pl_PL',
    'ru': 'ru_RU', 'zh': 'zh_CN', 'ja': 'ja_JP', 'ko': 'ko_KR',
    'ar': 'ar_001', 'he': 'he_IL', 'tr': 'tr_TR', 'vi': 'vi_VN',
    'th': 'th_TH', 'uk': 'uk_UA', 'cs': 'cs_CZ', 'ro': 'ro_RO',
    'hu': 'hu_HU', 'sv': 'sv_SE', 'da': 'da_DK', 'fi': 'fi_FI',
    'no': 'nb_NO', 'el': 'el_GR', 'bg': 'bg_BG', 'hr': 'hr_HR',
    'sk': 'sk_SK', 'sl': 'sl_SI', 'et': 'et_EE', 'lv': 'lv_LV',
    'lt': 'lt_LT',
}


def _get_lang_from_referer(request):
    """Récupère la langue depuis l'URL Referer (prioritaire pour la sidebar)."""
    try:
        referer = request.httprequest.headers.get('Referer', '')
        # Match both short codes (en, fr) and full codes (zh_CN, en_US)
        match = re.search(r'/([a-z]{2}(?:_[A-Z]{2})?)/knowledge/', referer)
        if match:
            lang_code = match.group(1)
            # If it's already a full code (zh_CN), return it directly
            if '_' in lang_code:
                return lang_code
            # Otherwise, convert short code to full code
            return LANG_MAPPING.get(lang_code)
    except Exception:
        pass
    
    # Fallback: contexte Odoo
    env = getattr(request, 'env', None)
    if env:
        if env.lang:
            return env.lang
        if env.context.get('lang'):
            return env.context.get('lang')
    return None


def _get_lang_code_from_odoo_lang(odoo_lang, env=None):
    """Convertit un code Odoo (en_US) en code URL (ce qu'Odoo utilise dans les URLs)."""
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
    
    # Fallback: use short code from mapping or first 2 chars
    for short_code, full_code in LANG_MAPPING.items():
        if full_code == odoo_lang:
            return short_code
    return odoo_lang[:2].lower() if len(odoo_lang) >= 2 else None


def _translate_sidebar_html(html_str, env, lang):
    """
    Traduit les noms d'articles dans le HTML de la sidebar Knowledge.
    Aussi: ajoute le préfixe de langue aux liens pour maintenir le contexte.
    """
    # Extraire les IDs d'articles
    article_ids = [int(m) for m in re.findall(r'data-article-id="(\d+)"', html_str)]
    if not article_ids:
        return html_str
    
    # Obtenir le code langue pour les URLs (récupère url_code depuis res.lang)
    lang_code = _get_lang_code_from_odoo_lang(lang, env)
    
    try:
        # Récupérer les traductions
        env.cr.execute("""
            SELECT res_id, value FROM dynamic_translation 
            WHERE model_name = 'knowledge.article' 
            AND field_name = 'name'
            AND res_id = ANY(%s) AND lang = %s
        """, (article_ids, lang))
        translations = {row[0]: row[1] for row in env.cr.fetchall()}
        
        # 1. Remplacer les noms d'articles dans la sidebar
        # Pattern simplifié: on capture tout le contenu de o_article_name et on le remplace
        for article_id, translated_name in translations.items():
            # Pattern: dans le bloc data-article-id="XX", capturer le contenu de o_article_name
            # et le remplacer entièrement par la traduction
            pattern = rf'(data-article-id="{article_id}"[^>]*>.*?<(?:a|span)[^>]*class="[^"]*o_article_name[^"]*"[^>]*>)(.*?)(</(?:a|span)>)'
            
            def make_replace_fn(trans_name):
                def replace_fn(m):
                    return m.group(1) + trans_name + m.group(3)
                return replace_fn
            
            html_str = re.sub(pattern, make_replace_fn(translated_name), html_str, flags=re.DOTALL)
        
        # 2. Ajouter le préfixe de langue aux liens /knowledge/article/XX
        if lang_code:
            # Pattern: href="/knowledge/article/XX" sans préfixe de langue
            def add_lang_prefix(m):
                return f'href="/{lang_code}{m.group(1)}"'
            
            html_str = re.sub(
                r'href="(/knowledge/article/\d+[^"]*)"',
                add_lang_prefix,
                html_str
            )
        
        return html_str
        
    except Exception:
        return html_str


def _translate_article_links_html(html_str, env, lang):
    """
    Traduit les liens d'articles (section "Related articles" en bas de page).
    Ces liens ont la structure: <a href="/knowledge/article/XX">Nom Article</a>
    """
    lang_code = _get_lang_code_from_odoo_lang(lang, env)
    
    # Extraire les IDs d'articles depuis les liens
    article_ids = [int(m) for m in re.findall(r'href="(?:/\w{2})?/knowledge/article/(\d+)', html_str)]
    if not article_ids:
        return html_str
    
    try:
        # Récupérer les traductions
        env.cr.execute("""
            SELECT res_id, value FROM dynamic_translation 
            WHERE model_name = 'knowledge.article' 
            AND field_name = 'name'
            AND res_id = ANY(%s) AND lang = %s
        """, (article_ids, lang))
        translations = {row[0]: row[1] for row in env.cr.fetchall()}
        
        if not translations:
            # Même sans traductions, ajouter les préfixes de langue
            if lang_code:
                html_str = re.sub(
                    r'href="(/knowledge/article/\d+[^"]*)"',
                    lambda m: f'href="/{lang_code}{m.group(1)}"',
                    html_str
                )
            return html_str
        
        # Récupérer les noms originaux pour pouvoir les remplacer
        env.cr.execute("""
            SELECT id, name FROM knowledge_article WHERE id = ANY(%s)
        """, (list(translations.keys()),))
        original_names = {row[0]: row[1] for row in env.cr.fetchall()}
        
        # Remplacer les noms dans les liens
        for article_id, translated_name in translations.items():
            original_name = original_names.get(article_id)
            if original_name and translated_name:
                # Pattern: <a href="...knowledge/article/ID...">NOM</a>
                # Capturer le lien complet et remplacer le contenu
                pattern = rf'(<a[^>]*href="[^"]*knowledge/article/{article_id}[^"]*"[^>]*>)(.*?)(</a>)'
                
                def make_replace_fn(trans_name):
                    def replace_fn(m):
                        return m.group(1) + trans_name + m.group(3)
                    return replace_fn
                
                html_str = re.sub(pattern, make_replace_fn(translated_name), html_str, flags=re.DOTALL | re.IGNORECASE)
        
        # Ajouter le préfixe de langue aux liens
        if lang_code:
            html_str = re.sub(
                r'href="(/knowledge/article/\d+[^"]*)"',
                lambda m: f'href="/{lang_code}{m.group(1)}"',
                html_str
            )
        
        return html_str
        
    except Exception as e:
        pass
        return html_str


def _apply_sidebar_patch():
    """Applique le patch pour intercepter les réponses de la sidebar Knowledge."""
    pid = os.getpid()
    if pid in _patched_workers:
        return
    
    try:
        from odoo.http import JsonRPCDispatcher
        
        if hasattr(JsonRPCDispatcher._response, '_odoo_translate_patched'):
            _patched_workers.add(pid)
            return
        
        _original_response = JsonRPCDispatcher._response
        
        def _patched_response(self, result=None, error=None):
            """Intercepte uniquement /knowledge/public_sidebar."""
            try:
                path = getattr(getattr(self.request, 'httprequest', None), 'path', '')
                
                if '/knowledge/public_sidebar' in path and isinstance(result, (str, Markup)):
                    lang = _get_lang_from_referer(self.request)
                    env = getattr(self.request, 'env', None)
                    
                    if lang and env:
                        translated = _translate_sidebar_html(str(result), env, lang)
                        if translated != str(result):
                            result = Markup(translated)
            except Exception:
                pass
            
            return _original_response(self, result, error)
        
        _patched_response._odoo_translate_patched = True
        JsonRPCDispatcher._response = _patched_response
        _patched_workers.add(pid)
        
    except Exception:
        pass


# Fonction publique pour appel depuis __init__.py
def apply_sidebar_patch():
    """Point d'entrée public pour appliquer le patch sidebar."""
    _apply_sidebar_patch()


# ============================================================
# Hook ir.http pour garantir les patchs dans tous les workers
# ============================================================
from odoo import models

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _dispatch(cls, endpoint):
        """Garantit que les patchs sont appliqués dans chaque worker Odoo."""
        from . import translation_patch
        translation_patch.apply_basemodel_patch()
        translation_patch.apply_knowledge_write_patch()
        _apply_sidebar_patch()
        return super()._dispatch(endpoint)

