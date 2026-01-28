"""
Main entry point for Phase 1 data ingestion.

Runs the full ingestion pipeline for TfL transport data.
"""

from src.data.ingest_pipeline import DataIngestionPipeline
from src.data.tfl.tfl_client import TflClient
from src.config.config_main import tfl_config

# Transport modes to ingest (Phase 1: Rail modes only)
TRANSPORT_MODES = [
    "tube",           # London Underground
    "dlr",            # Docklands Light Railway
    "elizabeth-line", # Elizabeth line
    "overground",     # London Overground
    "tram",           # Tramlink
]

def main():
    """Run the Phase 1 data ingestion pipeline."""
    
    # Initialize TfL client
    tfl_client = TflClient(tfl_config)
    
    # Initialize pipeline
    pipeline = DataIngestionPipeline(tfl_client)
    
    # Run full ingestion
    pipeline.run_full_ingestion(TRANSPORT_MODES)


if __name__ == "__main__":
    main()
