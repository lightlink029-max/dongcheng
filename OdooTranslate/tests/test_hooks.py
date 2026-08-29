# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.modules.module import get_manifest
from odoo.tests.common import TransactionCase, tagged

from .. import hooks
from ..models import ir_http, translation_patch


@tagged('post_install', '-at_install')
class TestHooks(TransactionCase):

    def test_asset_paths_use_the_installed_technical_module_name(self):
        manifest = get_manifest('OdooTranslate')
        asset_paths = [
            path
            for paths in manifest['assets'].values()
            for path in paths
            if isinstance(path, str)
        ]

        self.assertTrue(asset_paths)
        self.assertTrue(all(
            path.startswith('OdooTranslate/')
            for path in asset_paths
        ))

    def test_post_init_hook_uses_the_installed_technical_module_path(self):
        with patch.object(
            translation_patch,
            'apply_all_configured_patches',
            autospec=True,
        ) as apply_patches, patch.object(
            translation_patch,
            'apply_knowledge_write_patch',
            autospec=True,
        ) as apply_knowledge_patch, patch.object(
            ir_http,
            'apply_sidebar_patch',
            autospec=True,
        ) as apply_sidebar_patch:
            hooks.post_init_hook(self.env)

        apply_patches.assert_called_once_with(self.env)
        apply_knowledge_patch.assert_called_once_with()
        apply_sidebar_patch.assert_called_once_with()
