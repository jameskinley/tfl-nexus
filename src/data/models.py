"""
SQLAlchemy models for TfL Nexus database.

Phase 1: Stop, Service, Edge models (fully implemented)
Future phases: Historical delays, fragility scores, etc. (schema only)
"""

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from datetime import datetime

from .db_broker import Base


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
# FUTURE PHASE MODELS (Schema only - DO NOT populate in Phase 1)
# ============================================================================

class HistoricalDelay(Base):
    """Historical delay records for transit services (Phase 2)."""
    
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
    """Transfer delay statistics between services at interchange stops (Phase 2)."""
    
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


class FragilityScore(Base):
    """Network fragility metrics for stops and edges (Phase 3)."""
    
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


class ArrivalRecord(Base):
    """Raw arrival predictions for delay calculation (Phase 2)."""
    
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


class LiveDisruption(Base):
    """Real-time disruption data (Phase 2B - Enhanced)."""
    
    __tablename__ = 'live_disruptions'

    disruption_id = Column(Integer, primary_key=True, autoincrement=True)
    tfl_disruption_id = Column(String(100), unique=True, nullable=False, index=True)
    service_id = Column(Integer, ForeignKey('services.service_id'), nullable=False, index=True)
    
    category = Column(String(50), nullable=False, index=True)
    category_description = Column(Text, nullable=True)
    disruption_type = Column(String(100), nullable=True)
    description = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    additional_info = Column(Text, nullable=True)
    closure_text = Column(Text, nullable=True)
    
    severity = Column(String(50), nullable=True, index=True)
    severity_level = Column(Integer, nullable=True)
    severity_description = Column(Text, nullable=True)
    
    is_full_suspension = Column(Boolean, default=False, index=True)
    is_partial_suspension = Column(Boolean, default=False, index=True)
    affected_section_start_naptan = Column(String(100), nullable=True)
    affected_section_end_naptan = Column(String(100), nullable=True)
    
    affected_stops_json = Column(JSON, nullable=True)
    affected_routes_json = Column(JSON, nullable=True)
    
    created = Column(DateTime, nullable=True)
    last_update = Column(DateTime, nullable=True, index=True)
    valid_from = Column(DateTime, nullable=True, index=True)
    valid_to = Column(DateTime, nullable=True)
    
    start_time = Column(DateTime, nullable=False, index=True)
    expected_end_time = Column(DateTime, nullable=True)
    actual_end_time = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index('idx_service_start', 'service_id', 'start_time'),
        Index('idx_suspension_flags', 'is_full_suspension', 'is_partial_suspension'),
        Index('idx_category_type', 'category', 'disruption_type'),
    )

    def __repr__(self):
        return f"<LiveDisruption(id={self.disruption_id}, type='{self.disruption_type}', suspension={self.is_full_suspension}, resolved={self.actual_end_time is not None})>"

class SeverityLevel(Base):
    """Severity level definitions with adaptive learning (Phase 2B)."""
    
    __tablename__ = 'severity_levels'

    severity_id = Column(Integer, primary_key=True, autoincrement=True)
    mode_name = Column(String(50), nullable=False)
    severity_level = Column(Integer, nullable=False)
    description = Column(String(255), nullable=False)
    
    estimated_delay_minutes = Column(Float, nullable=True)
    is_suspension = Column(Boolean, default=False, nullable=False)
    
    sample_count = Column(Integer, default=0, nullable=False)
    confidence_score = Column(Float, default=0.3, nullable=False)
    
    last_updated = Column(DateTime, server_default=func.now(), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('mode_name', 'severity_level', name='uq_mode_severity'),
        Index('idx_severity_mode_level', 'mode_name', 'severity_level'),
    )

    def __repr__(self):
        return f"<SeverityLevel(mode='{self.mode_name}', level={self.severity_level}, delay={self.estimated_delay_minutes}m, conf={self.confidence_score:.2f})>"


class DisruptionCategory(Base):
    """Valid disruption category reference data (Phase 2B)."""
    
    __tablename__ = 'disruption_categories'

    category_id = Column(Integer, primary_key=True, autoincrement=True)
    category_name = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<DisruptionCategory(name='{self.category_name}')>"


class RealtimeDelaySample(Base):
    """Sampled arrival delays for severity learning (Phase 2B)."""
    
    __tablename__ = 'realtime_delay_samples'

    sample_id = Column(Integer, primary_key=True, autoincrement=True)
    service_id = Column(Integer, ForeignKey('services.service_id'), nullable=False, index=True)
    stop_id = Column(Integer, ForeignKey('stops.stop_id'), nullable=False, index=True)
    
    severity_at_time = Column(String(50), nullable=False)
    disruption_id = Column(Integer, ForeignKey('live_disruptions.disruption_id'), nullable=True, index=True)
    
    vehicle_id = Column(String(50), nullable=True)
    expected_arrival = Column(DateTime, nullable=False)
    measured_delay_seconds = Column(Integer, nullable=False)
    
    timestamp = Column(DateTime, nullable=False, index=True)
    platform_name = Column(String(100), nullable=True)
    direction = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('idx_sample_service_time', 'service_id', 'timestamp'),
        Index('idx_sample_severity', 'severity_at_time', 'timestamp'),
    )

    def __repr__(self):
        return f"<RealtimeDelaySample(id={self.sample_id}, service={self.service_id}, delay={self.measured_delay_seconds}s, severity='{self.severity_at_time}')>"

class User(Base):
    """User accounts for route planning (Phase 4)."""
    
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
    """User-saved routes (Phase 4)."""
    
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
