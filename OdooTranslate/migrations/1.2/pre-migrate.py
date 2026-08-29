# -*- coding: utf-8 -*-
"""
Pre-migration script for version 1.2
Adds is_author_view column and updates the unique constraint.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration: 
    1. Add is_author_view column if not exists
    2. Set default value for existing records
    3. Drop old unique constraint
    4. Create new unique constraint including is_author_view
    """
    if not version:
        return
    
    _logger.info("[OdooTranslate] Running pre-migration for version 1.2")
    
    # Check if table exists
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'dynamic_translation'
        )
    """)
    if not cr.fetchone()[0]:
        _logger.info("[OdooTranslate] Table dynamic_translation does not exist yet, skipping migration")
        return
    
    # 1. Check if column already exists
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'dynamic_translation' AND column_name = 'is_author_view'
        )
    """)
    column_exists = cr.fetchone()[0]
    
    if not column_exists:
        # Add is_author_view column with default False
        cr.execute("""
            ALTER TABLE dynamic_translation 
            ADD COLUMN is_author_view BOOLEAN DEFAULT FALSE
        """)
        _logger.info("[OdooTranslate] Added is_author_view column")
        
        # Set all existing records to False (recipient view)
        cr.execute("""
            UPDATE dynamic_translation SET is_author_view = FALSE WHERE is_author_view IS NULL
        """)
        _logger.info("[OdooTranslate] Set existing records to is_author_view=False")
    
    # 2. Create index on is_author_view (if not exists)
    cr.execute("""
        CREATE INDEX IF NOT EXISTS dynamic_translation_is_author_view_index 
        ON dynamic_translation (is_author_view)
    """)
    _logger.info("[OdooTranslate] Created/verified index on is_author_view")
    
    # 3. Drop old unique constraint (if exists) - handle both possible names
    cr.execute("""
        ALTER TABLE dynamic_translation 
        DROP CONSTRAINT IF EXISTS dynamic_translation_unique_translation
    """)
    _logger.info("[OdooTranslate] Dropped old unique constraint (if existed)")
    
    # 4. Create new unique constraint including is_author_view
    cr.execute("""
        ALTER TABLE dynamic_translation 
        ADD CONSTRAINT dynamic_translation_unique_translation 
        UNIQUE (model_name, field_name, res_id, lang, is_author_view)
    """)
    _logger.info("[OdooTranslate] Created new unique constraint with is_author_view")
    
    _logger.info("[OdooTranslate] Pre-migration for version 1.2 completed successfully")
