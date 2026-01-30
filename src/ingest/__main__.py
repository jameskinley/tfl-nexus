"""
TfL Nexus Ingestion Module Entry Point

Allows running the ingestion pipeline via:
    python -m src.ingest [args]
"""

from .orchestrator import main

if __name__ == "__main__":
    main()
