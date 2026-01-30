"""
Database Schema Module

Consolidates all SQLAlchemy models and provides atomic database initialization.
Eliminates incremental migration scripts in favor of drop+recreate approach.

Phase Coverage:
    - Phase 1: Stop, Service, Edge (static network topology)
    - Phase 2: HistoricalDelay, TransferStatistic, LiveDisruption, ArrivalRecord
    - Phase 3: FragilityScore
    - Phase 4: User, SavedRoute
"""

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Index
)
from sqlalchemy.orm import relationship, declarative_base
from geoalchemy2 import Geometry
from datetime import datetime

# Base class for all models
Base = declarative_base()


# ============================================================================
# PHASE 1: STATIC NETWORK TOPOLOGY
# ============================================================================

class Stop(Base):
    """Transport stops across all modes (tube, bus, DLR, etc.)."""
    
    __tablename__ = 'stops'

    stop_id = Column(Integer, primary_key=True, autoincrement=True)
    tfl_stop_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    mode = Column(String(50), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location = Column(Geometry('POINT', srid=4326), nullable=False)
    zone = Column(String(10), nullable=True)
    hub_naptanid = Column(String(50), nullable=True)
    stop_type = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    outgoing_edges = relationship('Edge', foreign_keys='Edge.from_stop_id', back_populates='from_stop')
    incoming_edges = relationship('Edge', foreign_keys='Edge.to_stop_id', back_populates='to_stop')

    def __repr__(self):
        return f"<Stop(id={self.stop_id}, tfl_id='{self.tfl_stop_id}', name='{self.name}', mode='{self.mode}')>"


class Service(Base):
    """Transport lines/services (tube lines, bus routes, etc.)."""
    
    __tablename__ = 'services'

    service_id = Column(Integer, primary_key=True, autoincrement=True)
    tfl_line_id = Column(String(50), unique=True, nullable=False, index=True)
    line_name = Column(String(100), nullable=False)
    mode = Column(String(50), nullable=False, index=True)
    operator = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    edges = relationship('Edge', back_populates='service')

    def __repr__(self):
        return f"<Service(id={self.service_id}, tfl_id='{self.tfl_line_id}', name='{self.line_name}', mode='{self.mode}')>"


class Edge(Base):
    """Directional connections between stops on a service."""
    
    __tablename__ = 'edges'

    edge_id = Column(Integer, primary_key=True, autoincrement=True)
    from_stop_id = Column(Integer, ForeignKey('stops.stop_id'), nullable=False, index=True)
    to_stop_id = Column(Integer, ForeignKey('stops.stop_id'), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey('services.service_id'), nullable=False, index=True)
    scheduled_travel_time = Column(Integer, nullable=True)  # seconds
    sequence_order = Column(Integer, nullable=False)
    branch_id = Column(Integer, nullable=True)  # For lines with multiple branches
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    from_stop = relationship('Stop', foreign_keys=[from_stop_id], back_populates='outgoing_edges')
    to_stop = relationship('Stop', foreign_keys=[to_stop_id], back_populates='incoming_edges')
    service = relationship('Service', back_populates='edges')

    def __repr__(self):
        return f"<Edge(id={self.edge_id}, from={self.from_stop_id}, to={self.to_stop_id}, service={self.service_id}, order={self.sequence_order})>"


# ============================================================================
# PHASE 2: TEMPORAL DATA INTEGRATION
# ============================================================================

class HistoricalDelay(Base):
    """Historical delay records for transit services."""
    
    __tablename__ = 'historical_delays'

    delay_id = Column(Integer, primary_key=True, autoincrement=True)
    service_id = Column(Integer, ForeignKey('services.service_id'), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    delay_minutes = Column(Integer, nullable=False)
    severity = Column(String(50), nullable=True)
    hour_of_day = Column(Integer, nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False, index=True)
    is_peak_hour = Column(Boolean, nullable=True)
    data_source = Column(String(30), nullable=False, index=True)
    confidence_level = Column(String(10), nullable=False)
    timetable_version = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    service = relationship('Service')

    __table_args__ = (
        Index('idx_service_timestamp', 'service_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<HistoricalDelay(id={self.delay_id}, service={self.service_id}, delay={self.delay_minutes}m, source={self.data_source})>"


class TransferStatistic(Base):
    """Transfer delay statistics between services at interchange stops."""
    
    __tablename__ = 'transfer_statistics'

    transfer_id = Column(Integer, primary_key=True, autoincrement=True)
    stop_id = Column(Integer, ForeignKey('stops.stop_id'), nullable=False, index=True)
    from_service_id = Column(Integer, ForeignKey('services.service_id'), nullable=False)
    to_service_id = Column(Integer, ForeignKey('services.service_id'), nullable=False)
    mean_delay = Column(Float, nullable=False)
    delay_variance = Column(Float, nullable=False)
    delay_std_dev = Column(Float, nullable=False)
    sample_count = Column(Integer, nullable=False)
    success_rate = Column(Float, nullable=True)
    last_computed = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_transfer_unique', 'stop_id', 'from_service_id', 'to_service_id', unique=True),
    )

    def __repr__(self):
        return f"<TransferStatistic(id={self.transfer_id}, stop={self.stop_id}, from_svc={self.from_service_id}, to_svc={self.to_service_id})>"


class LiveDisruption(Base):
    """Real-time disruption data."""
    
    __tablename__ = 'live_disruptions'

    disruption_id = Column(Integer, primary_key=True, autoincrement=True)
    tfl_disruption_id = Column(String(100), unique=True, nullable=False, index=True)
    service_id = Column(Integer, ForeignKey('services.service_id'), nullable=False, index=True)
    severity = Column(String(50), nullable=False, index=True)
    category = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    affected_stops = Column(Text, nullable=True)
    start_time = Column(DateTime, nullable=False, index=True)
    expected_end_time = Column(DateTime, nullable=True)
    actual_end_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_service_start', 'service_id', 'start_time'),
    )

    def __repr__(self):
        return f"<LiveDisruption(id={self.disruption_id}, tfl_id='{self.tfl_disruption_id}', severity='{self.severity}', resolved={self.actual_end_time is not None})>"


class ArrivalRecord(Base):
    """Raw arrival predictions for delay calculation."""
    
    __tablename__ = 'arrival_records'

    record_id = Column(Integer, primary_key=True, autoincrement=True)
    stop_id = Column(Integer, ForeignKey('stops.stop_id'), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey('services.service_id'), nullable=False, index=True)
    vehicle_id = Column(String(50), nullable=True)
    expected_arrival = Column(DateTime, nullable=False)
    time_to_station = Column(Integer, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    timetable_version = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_stop_service_timestamp', 'stop_id', 'service_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<ArrivalRecord(id={self.record_id}, stop={self.stop_id}, service={self.service_id}, arrival={self.expected_arrival})>"


# ============================================================================
# PHASE 3: NETWORK FRAGILITY ANALYSIS
# ============================================================================

class FragilityScore(Base):
    """Network fragility metrics for stops and edges."""
    
    __tablename__ = 'fragility_scores'

    score_id = Column(Integer, primary_key=True, autoincrement=True)
    stop_id = Column(Integer, ForeignKey('stops.stop_id'), nullable=True, index=True)
    edge_id = Column(Integer, ForeignKey('edges.edge_id'), nullable=True, index=True)
    fragility_score = Column(Float, nullable=False)
    centrality_score = Column(Float, nullable=True)
    betweenness_score = Column(Float, nullable=True)
    impact_radius = Column(Integer, nullable=True)  # meters
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<FragilityScore(id={self.score_id}, stop={self.stop_id}, edge={self.edge_id}, score={self.fragility_score})>"


# ============================================================================
# PHASE 4: USER FEATURES
# ============================================================================

class User(Base):
    """User accounts for route planning."""
    
    __tablename__ = 'users'

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)

    # Relationships
    saved_routes = relationship('SavedRoute', back_populates='user')

    def __repr__(self):
        return f"<User(id={self.user_id}, username='{self.username}')>"


class SavedRoute(Base):
    """User-saved routes."""
    
    __tablename__ = 'saved_routes'

    route_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False, index=True)
    route_name = Column(String(100), nullable=False)
    origin_stop_id = Column(Integer, ForeignKey('stops.stop_id'), nullable=False)
    destination_stop_id = Column(Integer, ForeignKey('stops.stop_id'), nullable=False)
    route_data = Column(Text, nullable=False)  # JSON-encoded route
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used = Column(DateTime, nullable=True)

    # Relationships
    user = relationship('User', back_populates='saved_routes')

    def __repr__(self):
        return f"<SavedRoute(id={self.route_id}, user={self.user_id}, name='{self.route_name}')>"


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def initialize_database(engine, drop_existing=False):
    """
    Initialize database schema atomically.
    
    Args:
        engine: SQLAlchemy engine instance
        drop_existing: If True, drops all existing tables before creation
        
    Returns:
        None
        
    Note:
        This function replaces all incremental migration scripts.
        Use drop_existing=True for fresh setup or schema changes.
    """
    if drop_existing:
        print("⚠️  Dropping all existing tables...")
        Base.metadata.drop_all(bind=engine)
        print("✓ Tables dropped")
    
    print("Creating database schema...")
    Base.metadata.create_all(bind=engine)
    print("✓ Database schema initialized")
    
    # Verify PostGIS extension (required for Stop.location)
    from sqlalchemy import text
    with engine.connect() as conn:
        result = conn.execute(text("SELECT PostGIS_version();"))
        version = result.scalar()
        print(f"✓ PostGIS extension verified: {version}")
