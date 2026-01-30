"""
Unified Ingestion Orchestrator

Single entry point for all TfL Nexus ingestion operations.
Coordinates Phase 1 (static network) and Phase 2 (temporal data) pipelines.

Usage:
    python -m src.ingest --reset-db --start-monitor
    python -m src.ingest --skip-verification --modes tube,dlr
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from typing import List

from src.data.db_broker import ConnectionBroker
from src.data.tfl.tfl_client import TflClient
from src.config.config_main import tfl_config, phase2_config, ingestion_config

from .schema import initialize_database
from .static_network import (
    ingest_stops, ingest_services, ingest_edges, verify_network
)
from .temporal_data import (
    derive_delays_from_disruptions,
    collect_arrival_predictions,
    compute_transfer_statistics
)


def run_full_ingestion(
    modes: List[str] = None,
    reset_db: bool = False,
    skip_verification: bool = False,
    backfill_days: int = None,
    start_monitor: bool = False
):
    """
    Execute complete ingestion pipeline.
    
    Args:
        modes: List of transport modes to ingest (default from env)
        reset_db: Drop and recreate all tables before ingestion
        skip_verification: Skip data integrity checks
        backfill_days: Number of days to backfill delays (None = all)
        start_monitor: Start disruption monitor daemon after ingestion
    """
    print(f"\n{'#'*70}")
    print(f"# TFL NEXUS - UNIFIED INGESTION PIPELINE")
    print(f"# Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*70}\n")
    
    overall_start = datetime.now()
    
    # Use configured modes if not specified
    if modes is None:
        modes = ingestion_config.modes
        print(f"Using configured modes from environment: {modes}")
    else:
        print(f"Using modes from command line: {modes}")
    
    # Initialize database
    engine = ConnectionBroker.get_engine()
    initialize_database(engine, drop_existing=reset_db)
    
    # Initialize TfL client
    tfl_client = TflClient(tfl_config)
    
    try:
        with ConnectionBroker.get_session() as session:
            # ================================================================
            # PHASE 1: STATIC NETWORK TOPOLOGY
            # ================================================================
            
            print(f"\n{'='*70}")
            print("PHASE 1: STATIC NETWORK INGESTION")
            print(f"{'='*70}\n")
            
            # Step 1: Ingest stops
            stop_mapping = ingest_stops(session, tfl_client, modes)
            
            # Step 2: Ingest services
            service_mapping = ingest_services(session, tfl_client, modes)
            
            # Step 3: Ingest edges
            total_edges = ingest_edges(session, tfl_client, stop_mapping, service_mapping)
            
            # Step 4: Verify network (unless skipped)
            if not skip_verification:
                verify_network(session)
            else:
                print("\n⚠️  Skipping verification as requested\n")
            
            print(f"\n{'='*70}")
            print("PHASE 1 COMPLETE")
            print(f"{'='*70}")
            print(f"  ✓ {len(stop_mapping)} stops")
            print(f"  ✓ {len(service_mapping)} services")
            print(f"  ✓ {total_edges} edges")
            print(f"{'='*70}\n")
            
            # ================================================================
            # PHASE 2: TEMPORAL DATA INTEGRATION
            # ================================================================
            
            print(f"\n{'='*70}")
            print("PHASE 2: TEMPORAL DATA INGESTION")
            print(f"{'='*70}\n")
            
            # Step 5: Backfill historical delays from disruptions
            since_timestamp = None
            if backfill_days is not None:
                since_timestamp = datetime.now(timezone.utc) - timedelta(days=backfill_days)
                print(f"Backfilling delays from {since_timestamp.strftime('%Y-%m-%d')}")
            else:
                print("Backfilling all historical disruptions")
            
            delay_stats = derive_delays_from_disruptions(session, since_timestamp)
            
            # Step 6: Collect current arrival predictions
            print("\nCollecting arrival predictions for interchange stops...")
            arrival_stats = collect_arrival_predictions(session, tfl_client)
            
            # Step 7: Compute transfer statistics
            print("\nComputing transfer statistics...")
            transfer_stats = compute_transfer_statistics(session)
            
            print(f"\n{'='*70}")
            print("PHASE 2 COMPLETE")
            print(f"{'='*70}")
            print(f"  ✓ {delay_stats['records_created']} historical delay records")
            print(f"  ✓ {arrival_stats['records_created']} arrival predictions")
            print(f"  ✓ {transfer_stats['computed']} new transfer statistics")
            print(f"  ✓ {transfer_stats['updated']} updated transfer statistics")
            print(f"{'='*70}\n")
        
        overall_duration = (datetime.now() - overall_start).total_seconds()
        
        print(f"\n{'#'*70}")
        print(f"# INGESTION PIPELINE COMPLETE")
        print(f"# Total duration: {overall_duration:.2f} seconds ({overall_duration/60:.1f} minutes)")
        print(f"# Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*70}\n")
        
        # Start disruption monitor if requested
        if start_monitor:
            print("\n" + "="*70)
            print("STARTING DISRUPTION MONITOR DAEMON")
            print("="*70 + "\n")
            from src.data.monitor_disruptions import start_monitor_daemon
            start_monitor_daemon()
        else:
            print("\nℹ️  To start disruption monitor, run:")
            print("   python -m src.data.monitor_disruptions")
            print("   OR: python -m src.ingest --start-monitor\n")
        
    except Exception as e:
        print(f"\n{'!'*70}")
        print(f"! PIPELINE FAILED")
        print(f"! Error: {e}")
        print(f"{'!'*70}\n")
        raise


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='TfL Nexus Unified Ingestion Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full ingestion with default modes
  python -m src.ingest
  
  # Reset database and ingest specific modes
  python -m src.ingest --reset-db --modes tube,dlr
  
  # Backfill last 30 days and start monitor
  python -m src.ingest --backfill-days 30 --start-monitor
  
  # Quick ingestion without verification
  python -m src.ingest --skip-verification
        """
    )
    
    parser.add_argument(
        '--modes',
        type=str,
        default=None,
        help='Comma-separated transport modes (default: from INGESTION_MODES env var)'
    )
    
    parser.add_argument(
        '--reset-db',
        action='store_true',
        help='Drop and recreate all tables before ingestion (DESTRUCTIVE)'
    )
    
    parser.add_argument(
        '--skip-verification',
        action='store_true',
        help='Skip data integrity verification step'
    )
    
    parser.add_argument(
        '--backfill-days',
        type=int,
        default=None,
        help='Number of days to backfill historical delays (default: all time)'
    )
    
    parser.add_argument(
        '--start-monitor',
        action='store_true',
        help='Start disruption monitor daemon after ingestion'
    )
    
    args = parser.parse_args()
    
    # Parse modes if provided
    modes = None
    if args.modes:
        modes = [m.strip() for m in args.modes.split(',')]
    
    # Confirm destructive operation
    if args.reset_db:
        print("\n⚠️  WARNING: --reset-db will DELETE ALL EXISTING DATA!")
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)
    
    # Run ingestion
    run_full_ingestion(
        modes=modes,
        reset_db=args.reset_db,
        skip_verification=args.skip_verification,
        backfill_days=args.backfill_days,
        start_monitor=args.start_monitor
    )


if __name__ == "__main__":
    main()
