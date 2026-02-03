#!/usr/bin/env python3
"""
Phase 2B Migration Runner

Runs the Alembic migration to upgrade the database schema for Phase 2B.
"""

import sys
import logging
from alembic.config import Config
from alembic import command

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    logger.info("Starting Phase 2B migration")
    
    alembic_cfg = Config("alembic.ini")
    
    try:
        logger.info("Running upgrade to phase2b_001...")
        command.upgrade(alembic_cfg, "phase2b_001")
        logger.info("Migration completed successfully")
        return 0
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return 1


def show_current_revision():
    alembic_cfg = Config("alembic.ini")
    try:
        command.current(alembic_cfg)
    except Exception as e:
        logger.error(f"Failed to show current revision: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "current":
        show_current_revision()
    else:
        sys.exit(run_migration())
