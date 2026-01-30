"""
Migration: Fix live_disruptions schema to match new design.
Removes: stop_id, end_time, is_active
Keeps: All new columns (affected_stops, expected_end_time, actual_end_time)
"""

import logging
from src.data.db_broker import ConnectionBroker
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Fix live_disruptions table schema."""
    with ConnectionBroker.get_session() as session:
        try:
            #  Drop old columns that are no longer in the model
            columns_to_drop = ['stop_id', 'end_time', 'is_active']
            
            for col in columns_to_drop:
                # Check if column exists before dropping
                result = session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='live_disruptions' 
                    AND column_name=:col_name
                """), {'col_name': col})
                
                if result.fetchone():
                    session.execute(text(
                        f"ALTER TABLE live_disruptions DROP COLUMN {col}"
                    ))
                    logger.info(f"Dropped column {col}")
                else:
                    logger.info(f"Column {col} does not exist (already removed)")
            
            session.commit()
            logger.info("Schema migration completed successfully")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Migration failed: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    main()
