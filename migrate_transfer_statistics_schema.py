"""
Migration: Update transfer_statistics table to Phase 2 schema.

Changes:
- Replace from_stop_id/to_stop_id with stop_id + from_service_id/to_service_id
- Replace avg/min/max_transfer_time with mean_delay, delay_variance, delay_std_dev
- Add: success_rate, last_computed
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
    """Migrate transfer_statistics table to Phase 2 schema."""
    with ConnectionBroker.get_session() as session:
        try:
            # Drop old columns
            old_columns = ['from_stop_id', 'to_stop_id', 'avg_transfer_time', 'min_transfer_time', 'max_transfer_time', 'updated_at']
            for col in old_columns:
                result = session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='transfer_statistics' 
                    AND column_name=:col_name
                """), {'col_name': col})
                
                if result.fetchone():
                    session.execute(text(f"ALTER TABLE transfer_statistics DROP COLUMN {col}"))
                    logger.info(f"Dropped column {col}")
            
            # Add new columns
            new_columns = [
                ('stop_id', 'INTEGER NOT NULL REFERENCES stops(stop_id)'),
                ('from_service_id', 'INTEGER NOT NULL REFERENCES services(service_id)'),
                ('to_service_id', 'INTEGER NOT NULL REFERENCES services(service_id)'),
                ('mean_delay', 'DOUBLE PRECISION'),
                ('delay_variance', 'DOUBLE PRECISION'),
                ('delay_std_dev', 'DOUBLE PRECISION'),
                ('success_rate', 'DOUBLE PRECISION'),
                ('last_computed', 'TIMESTAMP WITHOUT TIME ZONE')
            ]
            
            for col_name, col_type in new_columns:
                result = session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='transfer_statistics' 
                    AND column_name=:col_name
                """), {'col_name': col_name})
                
                if result.fetchone():
                    logger.info(f"Column {col_name} already exists")
                else:
                    session.execute(text(f"ALTER TABLE transfer_statistics ADD COLUMN {col_name} {col_type}"))
                    logger.info(f"Added column {col_name}")
            
            # Add indexes
            indexes = [
                'CREATE INDEX IF NOT EXISTS idx_transfer_stats_stop ON transfer_statistics(stop_id)',
                'CREATE INDEX IF NOT EXISTS idx_transfer_stats_services ON transfer_statistics(from_service_id, to_service_id)'
            ]
            
            for idx in indexes:
                session.execute(text(idx))
                logger.info(f"Created index: {idx[:60]}...")
            
            session.commit()
            logger.info("Transfer statistics schema migration completed")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Migration failed: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    main()
