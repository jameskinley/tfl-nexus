"""
Tests for Phase 2 historical data ingestion.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from sqlalchemy import text
from src.data.ingest_historical import DisruptionDelayDeriver, ArrivalCollector
from src.data.models import LiveDisruption, HistoricalDelay, Service, Stop
from src.data.db_broker import ConnectionBroker


class TestDisruptionDelayDeriver:
    """Test disruption-to-delay derivation."""
    
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
            session.execute(text('TRUNCATE TABLE historical_delays, live_disruptions CASCADE'))
            session.commit()    
    @pytest.fixture
    def sample_service(self):
        """Create test service."""
        with ConnectionBroker.get_session() as session:
            existing = session.query(Service).filter_by(
                tfl_line_id='test-historical-line'
            ).first()
            if existing:
                return existing.service_id
            
            service = Service(
                tfl_line_id='test-historical-line',
                line_name='Test Historical Line',
                mode='tube'
            )
            session.add(service)
            session.commit()
            return service.service_id
    
    @pytest.fixture
    def resolved_disruption(self, sample_service):
        """Create resolved disruption for testing."""
        with ConnectionBroker.get_session() as session:
            start = datetime.now(timezone.utc) - timedelta(hours=3)
            end = datetime.now(timezone.utc) - timedelta(hours=1)
            
            disruption = LiveDisruption(
                tfl_disruption_id='test-resolved-123',
                service_id=sample_service,
                severity='Severe Delays',
                category='RealTime',
                description='Test disruption',
                start_time=start,
                actual_end_time=end
            )
            session.add(disruption)
            session.commit()
            return disruption.disruption_id
    
    def test_deriver_initialization(self):
        """Test deriver initializes correctly."""
        with ConnectionBroker.get_session() as session:
            deriver = DisruptionDelayDeriver(session)
            assert deriver is not None
            assert len(deriver.severity_mapping) > 0
    
    def test_create_delay_records(self, resolved_disruption):
        """Test delay record creation from disruption."""
        with ConnectionBroker.get_session() as session:
            deriver = DisruptionDelayDeriver(session)
            
            disruption = session.query(LiveDisruption).filter_by(
                disruption_id=resolved_disruption
            ).first()
            
            records = deriver._create_delay_records(disruption)
            session.commit()
            
            assert records > 0
            
            delays = session.query(HistoricalDelay).filter_by(
                service_id=disruption.service_id if disruption else None,
            ).all()
            
            assert len(delays) >= records
            assert all(d.data_source == 'disruption_derived' for d in delays)
            assert all(d.confidence_level == 'low' for d in delays)
    
    def test_derive_delays_from_disruptions(self, resolved_disruption):
        """Test full derivation process."""
        with ConnectionBroker.get_session() as session:
            deriver = DisruptionDelayDeriver(session)
            stats = deriver.derive_delays_from_disruptions()
            
            assert stats['disruptions_processed'] >= 1
            assert stats['records_created'] > 0


class TestArrivalCollector:
    """Test arrival prediction collection."""
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_database(self):
        """Ensure tables exist."""
        ConnectionBroker.create_tables()
        yield
    
    @pytest.fixture
    def mock_tfl_client(self):
        """Create mock TfL client with arrival data."""
        client = Mock()
        client.get_stop_arrivals.return_value = [
            {
                'lineId': 'test-line',
                'vehicleId': 'TEST123',
                'expectedArrival': '2026-01-30T12:00:00Z',
                'timeToStation': 120
            }
        ]
        return client
    
    @pytest.fixture
    def sample_stop(self):
        """Create test stop."""
        with ConnectionBroker.get_session() as session:
            existing = session.query(Stop).filter_by(
                tfl_stop_id='940GZZLUKSX'
            ).first()
            if existing:
                return existing.stop_id
            
            stop = Stop(
                tfl_stop_id='940GZZLUKSX',
                name='Test Interchange',
                mode='tube',
                latitude=51.5,
                longitude=-0.1,
                location='SRID=4326;POINT(-0.1 51.5)'
            )
            session.add(stop)
            session.commit()
            return stop.stop_id
    
    def test_collector_initialization(self, mock_tfl_client):
        """Test collector initializes correctly."""
        with ConnectionBroker.get_session() as session:
            collector = ArrivalCollector(mock_tfl_client, session)
            assert collector is not None
            assert len(collector.interchange_stops) > 0
    
    def test_parse_timestamp(self, mock_tfl_client):
        """Test timestamp parsing."""
        with ConnectionBroker.get_session() as session:
            collector = ArrivalCollector(mock_tfl_client, session)
            
            ts = collector._parse_timestamp('2026-01-30T12:00:00Z')
            assert isinstance(ts, datetime)
            assert ts.year == 2026
            
            ts_fallback = collector._parse_timestamp(None)
            assert isinstance(ts_fallback, datetime)
