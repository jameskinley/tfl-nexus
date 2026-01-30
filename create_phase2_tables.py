"""
Create/update database tables for Phase 2.

Run this after updating models to ensure database schema matches.
"""

import logging
from src.data.db_broker import ConnectionBroker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Create all tables including Phase 2 additions."""
    logger.info("Creating/updating database tables")
    
    try:
        ConnectionBroker.create_tables()
        logger.info("Database tables created successfully")
        logger.info("Phase 2 tables: live_disruptions, historical_delays, transfer_statistics, arrival_records")
    except Exception as e:
        logger.error(f"Error creating tables: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
