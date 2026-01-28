"""
Test data ingestion pipeline.
"""

import pytest
from src.data.ingest_pipeline import DataIngestionPipeline
from src.data.tfl.tfl_client import TflClient
from src.config.config_main import tfl_config
from src.data.db_broker import ConnectionBroker
from src.data.models import Stop, Service, Edge
from sqlalchemy import func


class TestIngestionPipeline:
    """Test the data ingestion pipeline."""
    
    @pytest.fixture(scope="class")
    def pipeline(self):
        """Create pipeline instance."""
        client = TflClient(tfl_config)
        return DataIngestionPipeline(client)
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_database(self):
        """Ensure tables exist."""
        ConnectionBroker.create_tables()
        yield
    
    def test_pipeline_initialization(self, pipeline):
        """Test that pipeline initializes correctly."""
        assert pipeline is not None
        assert pipeline.tfl_client is not None
        assert isinstance(pipeline.stop_mapping, dict)
        assert isinstance(pipeline.service_mapping, dict)
    
    def test_ingest_stops_single_mode(self, pipeline):
        """Test ingesting stops for a single mode (DLR - smallest dataset)."""
        with ConnectionBroker.get_session() as session:
            # Clear any existing DLR stops for clean test
            session.execute("DELETE FROM edges WHERE service_id IN (SELECT service_id FROM services WHERE mode = 'dlr');")
            session.execute("DELETE FROM services WHERE mode = 'dlr';")
            session.execute("DELETE FROM stops WHERE mode = 'dlr';")
            session.commit()
            
            # Ingest DLR stops
            stop_mapping = pipeline.ingest_stops(session, ['dlr'])
            
            # Verify some stops were ingested
            assert len(stop_mapping) > 0
            
            # Verify stops in database
            stop_count = session.query(func.count(Stop.stop_id)).filter(Stop.mode == 'dlr').scalar()
            assert stop_count > 0
    
    def test_ingest_services_single_mode(self, pipeline):
        """Test ingesting services for a single mode."""
        with ConnectionBroker.get_session() as session:
            # Ingest DLR services
            service_mapping = pipeline.ingest_services(session, ['dlr'])
            
            # Verify some services were ingested
            assert len(service_mapping) > 0
            
            # Verify services in database
            service_count = session.query(func.count(Service.service_id)).filter(Service.mode == 'dlr').scalar()
            assert service_count > 0
