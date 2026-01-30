"""
Tests for Phase 2 disruption monitoring.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from sqlalchemy import text
from src.data.monitor_disruptions import DisruptionMonitor
from src.data.models import LiveDisruption, Service
from src.data.db_broker import ConnectionBroker


class TestDisruptionMonitor:
    """Test disruption monitoring functionality."""
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_database(self):
        """Ensure tables exist."""
        ConnectionBroker.create_tables()
        yield
    
    @pytest.fixture(autouse=True)
    def cleanup_data(self):
        """Clean up test data between tests."""
        yield
        with ConnectionBroker.get_session() as session:
            session.execute(text('TRUNCATE TABLE live_disruptions CASCADE'))
            session.commit()
    
    @pytest.fixture
    def mock_tfl_client(self):
        """Create mock TfL client."""
        client = Mock()
        return client
    
    @pytest.fixture
    def monitor(self, mock_tfl_client):
        """Create monitor instance."""
        return DisruptionMonitor(mock_tfl_client, poll_interval=1)
    
    @pytest.fixture
    def sample_service(self):
        """Create test service."""
        with ConnectionBroker.get_session() as session:
            existing = session.query(Service).filter_by(tfl_line_id='test-line').first()
            if existing:
                return existing.service_id
            
            service = Service(
                tfl_line_id='test-line',
                line_name='Test Line',
                mode='tube'
            )
            session.add(service)
            session.commit()
            return service.service_id
    
    def test_monitor_initialization(self, monitor):
        """Test monitor initializes correctly."""
        assert monitor is not None
        assert monitor.running == False
        assert len(monitor.modes) > 0
    
    def test_service_map_building(self, monitor, sample_service):
        """Test service map is built correctly."""
        with ConnectionBroker.get_session() as session:
            service_map = monitor._build_service_map(session)
            assert 'test-line' in service_map
            assert service_map['test-line'] == sample_service
    
    def test_create_disruption(self, monitor, sample_service):
        """Test disruption creation."""
        line_status = {
            'id': 12345,
            'statusSeverityDescription': 'Severe Delays',
            'reason': 'Signal failure',
            'created': '2026-01-30T10:00:00Z',
            'disruption': {
                'category': 'RealTime',
                'description': 'Signal failure at King Cross'
            }
        }
        
        with ConnectionBroker.get_session() as session:
            monitor._create_disruption(session, '12345', sample_service, line_status)
            session.commit()
            
            disruption = session.query(LiveDisruption).filter_by(
                tfl_disruption_id='12345'
            ).first()
            
            assert disruption is not None
            assert disruption.severity == 'Severe Delays'
            assert disruption.service_id == sample_service
            assert disruption.actual_end_time is None
    
    def test_update_disruption(self, monitor, sample_service):
        """Test disruption updates."""
        line_status = {
            'id': 12345,
            'statusSeverityDescription': 'Severe Delays',
            'reason': 'Signal failure',
            'created': '2026-01-30T10:00:00Z',
            'disruption': {
                'category': 'RealTime',
                'description': 'Signal failure at King Cross'
            }
        }
        
        with ConnectionBroker.get_session() as session:
            # Create initial disruption
            monitor._create_disruption(session, '12345', sample_service, line_status)
            session.commit()
            
            # Fetch it
            disruption = session.query(LiveDisruption).filter_by(
                tfl_disruption_id='12345'
            ).first()
            
            # Update with new status
            update_status = {
                'statusSeverityDescription': 'Minor Delays',
                'reason': 'Delays clearing',
                'disruption': {'description': 'Clearing'}
            }
            
            changed = monitor._update_disruption(disruption, update_status)
            session.commit()
            
            assert changed == True
            assert disruption.severity == 'Minor Delays'
    
    def test_resolve_disruption(self, monitor, sample_service):
        """Test disruption resolution."""
        line_status = {
            'id': 12345,
            'statusSeverityDescription': 'Severe Delays',
            'reason': 'Signal failure',
            'created': '2026-01-30T10:00:00Z',
            'disruption': {
                'category': 'RealTime',
                'description': 'Signal failure'
            }
        }
        
        with ConnectionBroker.get_session() as session:
            # Create disruption
            monitor._create_disruption(session, '12345', sample_service, line_status)
            session.commit()
            
            # Resolve it
            monitor._resolve_service_disruptions(session, sample_service)
            session.commit()
    
    def test_parse_timestamp(self, monitor):
        """Test timestamp parsing."""
        ts = monitor._parse_timestamp('2026-01-30T10:00:00Z')
        assert isinstance(ts, datetime)
        assert ts.year == 2026
        
        ts_fallback = monitor._parse_timestamp(None)
        assert isinstance(ts_fallback, datetime)
    
    def test_extract_affected_stops(self, monitor):
        """Test affected stops extraction."""
        disruption_obj = {
            'affectedStops': [
                {'id': 'stop1'},
                {'naptanId': 'stop2'}
            ]
        }
        
        result = monitor._extract_affected_stops(disruption_obj)
        assert result == 'stop1,stop2'
        
        empty_result = monitor._extract_affected_stops({})
        assert empty_result is None
