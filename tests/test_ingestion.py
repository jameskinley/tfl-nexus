"""
Test data ingestion pipeline.
"""

import pytest
from src.ingest.static_network import ingest_stops, ingest_services, ingest_edges
from src.data.tfl.tfl_client import TflClient
from src.config.config_main import tfl_config
from src.data.db_broker import ConnectionBroker
from src.ingest.schema import Stop, Service, Edge, initialize_database
from sqlalchemy import func


class TestIngestionPipeline:
    """Test the data ingestion pipeline."""
    
    @pytest.fixture(scope="class")
    def tfl_client(self):
        """Create TfL client instance."""
        return TflClient(tfl_config)
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_database(self):
        """Ensure tables exist."""
        engine = ConnectionBroker.get_engine()
        initialize_database(engine, drop_existing=False)
        yield
    
    def test_client_initialization(self, tfl_client):
        """Test that TfL client initializes correctly."""
        assert tfl_client is not None
    
    def test_ingest_stops_single_mode(self, tfl_client):
        """Test ingesting stops for a single mode (DLR - smallest dataset)."""
        from sqlalchemy import text
        with ConnectionBroker.get_session() as session:
            # Clear any existing DLR stops for clean test
            session.execute(text("DELETE FROM edges WHERE service_id IN (SELECT service_id FROM services WHERE mode = 'dlr');"))
            session.execute(text("DELETE FROM services WHERE mode = 'dlr';"))
            session.execute(text("DELETE FROM stops WHERE mode = 'dlr';"))
            session.commit()
            
            # Ingest DLR stops
            stop_mapping = ingest_stops(session, tfl_client, ['dlr'])
            
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
