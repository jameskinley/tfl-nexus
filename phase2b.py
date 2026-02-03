#!/usr/bin/env python3
"""
Phase 2B Management Script

Quick commands for managing Phase 2B disruption monitoring
"""

import sys
import subprocess
from pathlib import Path

VENV_PYTHON = Path(".venv/Scripts/python.exe")


def run_migration():
    print("Running Phase 2B migration...")
    subprocess.run([str(VENV_PYTHON), "run_phase2b_migration.py"])


def check_migration():
    print("Checking migration status...")
    subprocess.run([str(VENV_PYTHON), "check_phase2b_migration.py"])


def run_tests():
    print("Running Phase 2B tests...")
    subprocess.run([str(VENV_PYTHON), "test_phase2b.py"])


def start_monitor():
    print("Starting Phase 2B monitor...")
    print("Press Ctrl+C to stop")
    subprocess.run([str(VENV_PYTHON), "-m", "src.data.monitor_disruptions_phase2b"])


def show_validation_queries():
    print("Available validation queries:")
    subprocess.run([str(VENV_PYTHON), "src/data/phase2b_validation_queries.py"])


def run_validation_query(query_name):
    subprocess.run([str(VENV_PYTHON), "src/data/phase2b_validation_queries.py", query_name])


def show_help():
    print("""
Phase 2B Management Script
==========================

Usage: python phase2b.py <command>

Commands:
  migrate       - Run Phase 2B database migration
  check         - Check migration status and table counts
  test          - Run test suite
  monitor       - Start disruption monitor (Ctrl+C to stop)
  validate      - Show available validation queries
  query <name>  - Run specific validation query

Examples:
  python phase2b.py migrate
  python phase2b.py test
  python phase2b.py monitor
  python phase2b.py query disruption_category_distribution
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_help()
        sys.exit(0)
    
    command = sys.argv[1].lower()
    
    commands = {
        "migrate": run_migration,
        "check": check_migration,
        "test": run_tests,
        "monitor": start_monitor,
        "validate": show_validation_queries,
        "help": show_help,
    }
    
    if command == "query" and len(sys.argv) > 2:
        run_validation_query(sys.argv[2])
    elif command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")
        show_help()
        sys.exit(1)
