"""
Test database setup and models for Phase 1.
"""

import pytest
from sqlalchemy import text
from src.data.db_broker import ConnectionBroker
from src.ingest.schema import Stop, Service, Edge, initialize_database


class TestDatabaseConnection:
    """Test database connectivity and PostGIS."""
    
    def test_database_connection(self):
        """Test that we can connect to the database."""
        with ConnectionBroker.get_session() as session:
            result = session.execute(text("SELECT version();")).fetchone()
            assert result is not None
            assert "PostgreSQL" in result[0]
    
    def test_postgis_extension(self):
        """Test that PostGIS extension is available."""
        with ConnectionBroker.get_session() as session:
            result = session.execute(text("SELECT PostGIS_version();")).fetchone()
            assert result is not None
            assert len(result[0]) > 0


class TestTableStructure:
    """Test that tables are created correctly."""
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_tables(self):
        """Create tables before running tests."""
        engine = ConnectionBroker.get_engine()
        initialize_database(engine, drop_existing=False)
        yield
    
    def test_stops_table_exists(self):
        """Test that stops table exists with correct columns."""
        with ConnectionBroker.get_session() as session:
            result = session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'stops'
                ORDER BY ordinal_position;
            """)).fetchall()
            
            columns = [row[0] for row in result]
            assert 'stop_id' in columns
            assert 'tfl_stop_id' in columns
            assert 'name' in columns
            assert 'location' in columns
            assert 'latitude' in columns
            assert 'longitude' in columns
    
    def test_services_table_exists(self):
        """Test that services table exists with correct columns."""
        with ConnectionBroker.get_session() as session:
            result = session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'services'
                ORDER BY ordinal_position;
            """)).fetchall()
            
            columns = [row[0] for row in result]
            assert 'service_id' in columns
            assert 'tfl_line_id' in columns
            assert 'line_name' in columns
            assert 'mode' in columns
    
    def test_edges_table_exists(self):
        """Test that edges table exists with correct columns."""
        with ConnectionBroker.get_session() as session:
            result = session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'edges'
                ORDER BY ordinal_position;
            """)).fetchall()
            
            columns = [row[0] for row in result]
            assert 'edge_id' in columns
            assert 'from_stop_id' in columns
            assert 'to_stop_id' in columns
            assert 'service_id' in columns
            assert 'sequence_order' in columns
    
    def test_spatial_index_exists(self):
        """Test that spatial index exists on stops.location."""
        with ConnectionBroker.get_session() as session:
            result = session.execute(text("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'stops' AND indexname LIKE '%location%';
            """)).fetchall()
            
            assert len(result) > 0, "Spatial index not found on stops.location"


class TestModels:
    """Test SQLAlchemy models."""
    
    def test_stop_model_creation(self):
        """Test creating a Stop instance."""
        from geoalchemy2 import WKTElement
        
        stop = Stop(
            tfl_stop_id='TEST001',
            name='Test Stop',
            mode='tube',
            latitude=51.5074,
            longitude=-0.1278,
            location=WKTElement('POINT(-0.1278 51.5074)', srid=4326)
        )
        
        assert stop.tfl_stop_id == 'TEST001'
        assert stop.name == 'Test Stop'
        assert stop.mode == 'tube'
    
    def test_service_model_creation(self):
        """Test creating a Service instance."""
        service = Service(
            tfl_line_id='victoria',
            line_name='Victoria',
            mode='tube'
        )
        
        assert service.tfl_line_id == 'victoria'
        assert service.line_name == 'Victoria'
        assert service.mode == 'tube'
    
    def test_edge_model_creation(self):
        """Test creating an Edge instance."""
        edge = Edge(
            from_stop_id=1,
            to_stop_id=2,
            service_id=1,
            sequence_order=0
        )
        
        assert edge.from_stop_id == 1
        assert edge.to_stop_id == 2
        assert edge.service_id == 1
        assert edge.sequence_order == 0
