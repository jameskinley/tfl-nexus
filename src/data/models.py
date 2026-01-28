"""
SQLAlchemy models for TfL Nexus database.

Phase 1: Stop, Service, Edge models (fully implemented)
Future phases: Historical delays, fragility scores, etc. (schema only)
"""

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Index
)
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from datetime import datetime

from src.data.db_broker import Base


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
    edge_id = Column(Integer, ForeignKey('edges.edge_id'), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    delay_seconds = Column(Integer, nullable=False)
    cause_category = Column(String(100), nullable=True)
    severity = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    edge = relationship('Edge')

    def __repr__(self):
        return f"<HistoricalDelay(id={self.delay_id}, edge={self.edge_id}, delay={self.delay_seconds}s)>"


class TransferStatistic(Base):
    """Transfer times and probabilities between stops (Phase 2)."""
    
    __tablename__ = 'transfer_statistics'

    transfer_id = Column(Integer, primary_key=True, autoincrement=True)
    from_stop_id = Column(Integer, ForeignKey('stops.stop_id'), nullable=False, index=True)
    to_stop_id = Column(Integer, ForeignKey('stops.stop_id'), nullable=False, index=True)
    avg_transfer_time = Column(Integer, nullable=False)  # seconds
    min_transfer_time = Column(Integer, nullable=False)  # seconds
    max_transfer_time = Column(Integer, nullable=False)  # seconds
    sample_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<TransferStatistic(id={self.transfer_id}, from={self.from_stop_id}, to={self.to_stop_id})>"


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


class LiveDisruption(Base):
    """Real-time disruption data (Phase 2)."""
    
    __tablename__ = 'live_disruptions'

    disruption_id = Column(Integer, primary_key=True, autoincrement=True)
    tfl_disruption_id = Column(String(100), unique=True, nullable=False, index=True)
    service_id = Column(Integer, ForeignKey('services.service_id'), nullable=True, index=True)
    stop_id = Column(Integer, ForeignKey('stops.stop_id'), nullable=True, index=True)
    category = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    description = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<LiveDisruption(id={self.disruption_id}, severity='{self.severity}', active={self.is_active})>"


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
