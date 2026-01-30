"""
Tests for Phase 2 transfer statistics computation.
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from src.ingest.temporal_data import compute_transfer_statistics
from src.ingest.schema import TransferStatistic, HistoricalDelay, Service, Stop, Edge, initialize_database
from src.data.db_broker import ConnectionBroker


class TestTransferStatisticsComputer:
    """Test transfer statistics computation."""
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_database(self):
        """Ensure tables exist."""
        engine = ConnectionBroker.get_engine()
        initialize_database(engine, drop_existing=False)
        yield
    
    @pytest.fixture(autouse=True)
    def cleanup_data(self):
        """Clean up test data between tests."""
        yield
        with ConnectionBroker.get_session() as session:
            session.execute(text('TRUNCATE TABLE transfer_statistics, historical_delays, edges, services, stops CASCADE'))
            session.commit()
    
    @pytest.fixture(autouse=True)
    def cleanup_data(self):
        """Clean up test data between tests."""
        yield
        with ConnectionBroker.get_session() as session:
            session.execute(text('TRUNCATE TABLE transfer_statistics, historical_delays, edges, services, stops CASCADE'))
            session.commit()
    
    @pytest.fixture
    def interchange_setup(self):
        """Create interchange stop with multiple services and delay data."""
        with ConnectionBroker.get_session() as session:
            stop = Stop(
                tfl_stop_id='test-interchange-stop',
                name='Test Interchange',
                mode='tube',
                latitude=51.5,
                longitude=-0.1,
                location='SRID=4326;POINT(-0.1 51.5)'
            )
            session.add(stop)
            session.flush()
            
            service1 = Service(
                tfl_line_id='test-service-1',
                line_name='Test Service 1',
                mode='tube'
            )
            service2 = Service(
                tfl_line_id='test-service-2',
                line_name='Test Service 2',
                mode='tube'
            )
            session.add_all([service1, service2])
            session.flush()
            
            edge1 = Edge(
                from_stop_id=stop.stop_id,
                to_stop_id=stop.stop_id,
                service_id=service1.service_id,
                sequence_order=1
            )
            edge2 = Edge(
                from_stop_id=stop.stop_id,
                to_stop_id=stop.stop_id,
                service_id=service2.service_id,
                sequence_order=1
            )
            session.add_all([edge1, edge2])
            
            base_time = datetime.now(timezone.utc) - timedelta(days=7)
            for i in range(20):
                ts = base_time + timedelta(hours=i)
                
                delay1 = HistoricalDelay(
                    service_id=service1.service_id,
                    timestamp=ts,
                    delay_minutes=5 + i % 10,
                    hour_of_day=ts.hour,
                    day_of_week=ts.weekday(),
                    data_source='disruption_derived',
                    confidence_level='low'
                )
                delay2 = HistoricalDelay(
                    service_id=service2.service_id,
                    timestamp=ts,
                    delay_minutes=3 + i % 8,
                    hour_of_day=ts.hour,
                    day_of_week=ts.weekday(),
                    data_source='disruption_derived',
                    confidence_level='low'
                )
                session.add_all([delay1, delay2])
            
            session.commit()
            
            return {
                'stop_id': stop.stop_id,
                'service1_id': service1.service_id,
                'service2_id': service2.service_id
            }
    
    def test_computer_initialization(self):
        """Test computer initializes correctly."""
        with ConnectionBroker.get_session() as session:
            computer = TransferStatisticsComputer(session)
            assert computer is not None
            assert computer.min_samples > 0
    
    def test_find_interchange_stops(self, interchange_setup):
        """Test interchange stop detection."""
        with ConnectionBroker.get_session() as session:
            computer = TransferStatisticsComputer(session)
            interchanges = computer._find_interchange_stops()
            
            assert len(interchanges) > 0
            assert interchange_setup['stop_id'] in interchanges
    
    def test_get_services_at_stop(self, interchange_setup):
        """Test service enumeration at stop."""
        with ConnectionBroker.get_session() as session:
            computer = TransferStatisticsComputer(session)
            services = computer._get_services_at_stop(interchange_setup['stop_id'])
            
            assert len(services) >= 2
            assert interchange_setup['service1_id'] in services
            assert interchange_setup['service2_id'] in services
    
    def test_compute_transfer_stat(self, interchange_setup):
        """Test transfer statistic computation."""
        with ConnectionBroker.get_session() as session:
            computer = TransferStatisticsComputer(session)
            
            success = computer._compute_transfer_stat(
                interchange_setup['stop_id'],
                interchange_setup['service1_id'],
                interchange_setup['service2_id']
            )
            session.commit()
            
            assert success == True
            
            stat = session.query(TransferStatistic).filter_by(
                stop_id=interchange_setup['stop_id'],
                from_service_id=interchange_setup['service1_id'],
                to_service_id=interchange_setup['service2_id']
            ).first()
            
            assert stat is not None
            assert stat.mean_delay >= 0
            assert stat.delay_variance >= 0
            assert stat.sample_count >= computer.min_samples
            assert stat.success_rate is not None
    
    def test_compute_all_transfers(self, interchange_setup):
        """Test full transfer computation."""
        with ConnectionBroker.get_session() as session:
            computer = TransferStatisticsComputer(session)
            stats = computer.compute_all_transfers()
            
            assert stats['computed'] + stats['updated'] > 0
