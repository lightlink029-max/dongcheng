# -*- coding: utf-8 -*-
"""
Pre-migration script for version 1.7
Creates the odoo_translate_config table before views are loaded.

This is necessary because the model is new in this version, and Odoo tries
to load XML views before registering new models during an upgrade.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration: Create odoo_translate_config table if it doesn't exist.
    This ensures the model exists before the XML views try to reference it.
    """
    if not version:
        return

    _logger.info("[OdooTranslate] Running pre-migration for version 1.7")

    # Check if table already exists
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'odoo_translate_config'
        )
    """)
    table_exists = cr.fetchone()[0]

    if table_exists:
        _logger.info("[OdooTranslate] Table odoo_translate_config already exists, checking for new columns")
        # Check if shared_secret column exists (new in 1.7)
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = 'odoo_translate_config' AND column_name = 'shared_secret'
            )
        """)
        if not cr.fetchone()[0]:
            cr.execute("""
                ALTER TABLE odoo_translate_config 
                ADD COLUMN shared_secret VARCHAR
            """)
            _logger.info("[OdooTranslate] Added shared_secret column")
        return

    _logger.info("[OdooTranslate] Creating odoo_translate_config table")

    # Create the table with all required columns
    cr.execute("""
        CREATE TABLE odoo_translate_config (
            id SERIAL PRIMARY KEY,
            module_uuid VARCHAR,
            shared_secret VARCHAR,
            link_token VARCHAR,
            link_token_created_at TIMESTAMP,
            connection_status VARCHAR DEFAULT 'disconnected',
            has_api_key BOOLEAN DEFAULT FALSE,
            linked_email VARCHAR,
            connected_at TIMESTAMP,
            last_status_check TIMESTAMP,
            display_name VARCHAR,
            create_uid INTEGER,
            create_date TIMESTAMP,
            write_uid INTEGER,
            write_date TIMESTAMP
        )
    """)

    _logger.info("[OdooTranslate] Table odoo_translate_config created successfully")
