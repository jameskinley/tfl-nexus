"""
Migration: Update historical_delays table to Phase 2 schema.

Changes:
- Replace edge_id with service_id
- Replace delay_seconds with delay_minutes
- Add: hour_of_day, day_of_week, is_peak_hour, data_source, confidence_level, timetable_version
- Remove: cause_category
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
    """Migrate historical_delays table to Phase 2 schema."""
    with ConnectionBroker.get_session() as session:
        try:
            # Drop old columns
            old_columns = ['edge_id', 'delay_seconds', 'cause_category']
            for col in old_columns:
                result = session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='historical_delays' 
                    AND column_name=:col_name
                """), {'col_name': col})
                
                if result.fetchone():
                    session.execute(text(f"ALTER TABLE historical_delays DROP COLUMN {col}"))
                    logger.info(f"Dropped column {col}")
            
            # Add new columns
            new_columns = [
                ('service_id', 'INTEGER NOT NULL REFERENCES services(service_id)'),
                ('delay_minutes', 'INTEGER NOT NULL'),
                ('hour_of_day', 'INTEGER'),
                ('day_of_week', 'INTEGER'),
                ('is_peak_hour', 'BOOLEAN'),
                ('data_source', 'VARCHAR(50)'),
                ('confidence_level', 'VARCHAR(20)'),
                ('timetable_version', 'VARCHAR(50)')
            ]
            
            for col_name, col_type in new_columns:
                result = session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='historical_delays' 
                    AND column_name=:col_name
                """), {'col_name': col_name})
                
                if result.fetchone():
                    logger.info(f"Column {col_name} already exists")
                else:
                    session.execute(text(f"ALTER TABLE historical_delays ADD COLUMN {col_name} {col_type}"))
                    logger.info(f"Added column {col_name}")
            
            # Add indexes
            indexes = [
                'CREATE INDEX IF NOT EXISTS ix_historical_delays_service_id ON historical_delays(service_id)',
                'CREATE INDEX IF NOT EXISTS ix_historical_delays_timestamp ON historical_delays(timestamp)',
                'CREATE INDEX IF NOT EXISTS ix_historical_delays_hour_day ON historical_delays(hour_of_day, day_of_week)'
            ]
            
            for idx in indexes:
                session.execute(text(idx))
                logger.info(f"Created index: {idx[:60]}...")
            
            session.commit()
            logger.info("Historical delays schema migration completed")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Migration failed: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    main()
