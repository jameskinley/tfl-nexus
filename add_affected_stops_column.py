"""
Migration: Add missing columns to live_disruptions table.
"""

import logging
from src.data.db_broker import ConnectionBroker
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def add_column_if_missing(session, column_name, column_type):
    """Add column if it doesn't exist."""
    result = session.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='live_disruptions' 
        AND column_name=:col_name
    """), {'col_name': column_name})
    
    if result.fetchone():
        logger.info(f"Column {column_name} already exists")
        return False
    
    session.execute(text(
        f"ALTER TABLE live_disruptions ADD COLUMN {column_name} {column_type}"
    ))
    logger.info(f"Added column {column_name}")
    return True


def main():
    """Add missing columns to live_disruptions table."""
    with ConnectionBroker.get_session() as session:
        try:
            changes_made = False
            changes_made |= add_column_if_missing(session, 'affected_stops', 'JSONB')
            changes_made |= add_column_if_missing(session, 'expected_end_time', 'TIMESTAMP WITH TIME ZONE')
            changes_made |= add_column_if_missing(session, 'actual_end_time', 'TIMESTAMP WITH TIME ZONE')
            
            if changes_made:
                session.commit()
                logger.info("Migration completed successfully")
            else:
                logger.info("No changes needed")
                
        except Exception as e:
            session.rollback()
            logger.error(f"Migration failed: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    main()
