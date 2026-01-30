"""
TfL Nexus Unified Ingestion Module

Single source of truth for all data ingestion operations.
Consolidates Phase 1 (static network) and Phase 2 (temporal data) pipelines.

Entry Point:
    python -m src.ingest --reset-db --start-monitor

Components:
    - schema: Database models and atomic initialization
    - static_network: Stops, Services, Edges ingestion (Phase 1)
    - temporal_data: Historical delays, statistics computation (Phase 2)
    - orchestrator: Main entry point coordinating all ingestion steps
"""

from .schema import initialize_database, Base
from .orchestrator import run_full_ingestion

__all__ = ['initialize_database', 'Base', 'run_full_ingestion']
