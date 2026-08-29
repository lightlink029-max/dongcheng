# -*- coding: utf-8 -*-
import logging

from .models import ir_http, translation_patch

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Apply every configured ORM and Knowledge patch after installation."""
    _logger.info('[OdooTranslate] post-init hook started')

    try:
        translation_patch.apply_all_configured_patches(env)
        translation_patch.apply_knowledge_write_patch()
        ir_http.apply_sidebar_patch()
    except Exception:
        _logger.exception('[OdooTranslate] post-init hook failed')
        raise
