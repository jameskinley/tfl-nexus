import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from src.data.models import (
    SeverityLevel, RealtimeDelaySample, LiveDisruption, 
    Service, Stop, Edge
)
from src.data.tfl.tfl_client import TflClient
from src.data.db_broker import ConnectionBroker

logger = logging.getLogger(__name__)


class SeverityLearner:

    def __init__(self, tfl_client: TflClient, config: dict):
        self.tfl_client = tfl_client
        self.config = config
        self.major_stops = []
        self.learning_enabled = config.get('enable_severity_learning', True)
        self.sample_interval = config.get('learning_sample_interval', 300)
        self.confidence_threshold = config.get('confidence_threshold', 0.75)
        self.high_confidence_threshold = config.get('high_confidence_threshold', 0.9)
        self.min_samples_for_update = config.get('min_samples_for_update', 20)
        
    def initialize_severity_data(self):
        with ConnectionBroker.get_session() as session:
            self._load_severity_definitions(session)
            self._load_major_stops(session)
            session.commit()
    
    def _load_severity_definitions(self, session: Session):
        existing_count = session.query(SeverityLevel).count()
        if existing_count > 0:
            logger.info(f"Severity definitions already loaded ({existing_count} entries)")
            return
        
        severity_data = self.tfl_client.get_severity_codes()
        
        initial_delay_map = {
            0: 0.0,
            1: 1.0,
            2: 3.0,
            3: 5.0,
            4: 8.0,
            5: 10.0,
            6: 12.0,
            7: 15.0,
            8: 20.0,
            9: 25.0,
            10: None,
        }
        
        suspension_keywords = ['suspend', 'closed', 'closure', 'no service']
        
        for severity in severity_data:
            mode_name = severity.get('modeName', '')
            level = severity.get('severityLevel')
            description = severity.get('description', '')
            
            desc_lower = description.lower()
            is_suspension = any(keyword in desc_lower for keyword in suspension_keywords)
            
            estimated_delay = None if is_suspension else initial_delay_map.get(level, 10.0)
            
            severity_record = SeverityLevel(
                mode_name=mode_name,
                severity_level=level,
                description=description,
                estimated_delay_minutes=estimated_delay,
                is_suspension=is_suspension,
                sample_count=0,
                confidence_score=0.3
            )
            
            session.add(severity_record)
            logger.debug(f"Added severity: {mode_name} L{level} = {description} ({estimated_delay}min)")
        
        logger.info(f"Loaded {len(severity_data)} severity definitions")
    
    def _load_major_stops(self, session: Session):
        major_stop_threshold = self.config.get('major_stop_threshold', 3)
        
        query = session.query(
            Stop.stop_id,
            Stop.tfl_stop_id,
            Stop.name,
            func.count(func.distinct(Edge.service_id)).label('line_count')
        ).join(
            Edge,
            (Stop.stop_id == Edge.from_stop_id) | (Stop.stop_id == Edge.to_stop_id)
        ).filter(
            Stop.mode.in_(['tube', 'dlr', 'overground', 'elizabeth-line'])
        ).group_by(
            Stop.stop_id, Stop.tfl_stop_id, Stop.name
        ).having(
            func.count(func.distinct(Edge.service_id)) >= major_stop_threshold
        ).order_by(
            func.count(func.distinct(Edge.service_id)).desc()
        ).limit(30)
        
        self.major_stops = [
            {
                'stop_id': row.stop_id,
                'naptan_id': row.tfl_stop_id,
                'name': row.name,
                'line_count': row.line_count
            }
            for row in query.all()
        ]
        
        logger.info(f"Identified {len(self.major_stops)} major interchange stops for sampling")
    
    def sample_delays_during_disruptions(self):
        if not self.learning_enabled:
            return
        
        with ConnectionBroker.get_session() as session:
            active_disruptions = session.query(LiveDisruption).filter(
                LiveDisruption.actual_end_time.is_(None)
            ).all()
            
            if not active_disruptions:
                logger.debug("No active disruptions, skipping delay sampling")
                return
            
            samples_collected = 0
            
            for disruption in active_disruptions:
                try:
                    samples = self._sample_disruption_delays(session, disruption)
                    samples_collected += samples
                except Exception as e:
                    logger.error(f"Failed to sample disruption {disruption.disruption_id}: {e}")
            
            if samples_collected > 0:
                session.commit()
                logger.info(f"Collected {samples_collected} delay samples")
                
                self._update_severity_estimates(session)
                session.commit()
    
    def _sample_disruption_delays(self, session: Session, disruption: LiveDisruption) -> int:
        service = session.query(Service).filter_by(
            service_id=disruption.service_id
        ).first()
        
        if not service:
            return 0
        
        severity_record = session.query(SeverityLevel).filter_by(
            mode_name=service.mode,
            severity_level=disruption.severity_level
        ).first()
        
        if not severity_record:
            return 0
        
        if severity_record.confidence_score >= self.high_confidence_threshold:
            if severity_record.sample_count >= 100:
                return 0
        
        relevant_stops = self._find_affected_stops(session, disruption)
        
        if not relevant_stops:
            relevant_stops = [stop for stop in self.major_stops if stop['naptan_id']][:5]
        
        samples_collected = 0
        
        for stop_info in relevant_stops[:3]:
            try:
                arrivals = self.tfl_client.get_arrivals(
                    [service.tfl_line_id],
                    stop_info['naptan_id']
                )
                
                delays = self._compute_delays_from_arrivals(arrivals, service)
                
                for delay_data in delays:
                    sample = RealtimeDelaySample(
                        service_id=service.service_id,
                        stop_id=stop_info['stop_id'],
                        severity_at_time=disruption.severity or f"Level_{disruption.severity_level}",
                        disruption_id=disruption.disruption_id,
                        vehicle_id=delay_data.get('vehicle_id'),
                        expected_arrival=delay_data['expected_arrival'],
                        measured_delay_seconds=delay_data['delay_seconds'],
                        timestamp=datetime.now(timezone.utc),
                        platform_name=delay_data.get('platform_name'),
                        direction=delay_data.get('direction')
                    )
                    session.add(sample)
                    samples_collected += 1
                
            except Exception as e:
                logger.warning(f"Failed to sample arrivals at {stop_info.get('name', 'unknown')}: {e}")
        
        return samples_collected
    
    def _find_affected_stops(self, session: Session, disruption: LiveDisruption) -> List[Dict]:
        affected_stops = []
        
        if disruption.affected_stops_json:
            naptan_ids = [
                stop.get('naptanId') 
                for stop in disruption.affected_stops_json 
                if stop.get('naptanId')
            ][:5]
            
            if naptan_ids:
                stops = session.query(Stop).filter(
                    Stop.tfl_stop_id.in_(naptan_ids)
                ).all()
                
                affected_stops = [
                    {
                        'stop_id': stop.stop_id,
                        'naptan_id': stop.tfl_stop_id,
                        'name': stop.name
                    }
                    for stop in stops
                ]
        
        return affected_stops
    
    def _compute_delays_from_arrivals(self, arrivals: List[Dict], service: Service) -> List[Dict]:
        if not arrivals:
            return []
        
        expected_frequency = self.config.get('default_frequency_seconds', {}).get(
            service.mode, 300
        )
        
        sorted_arrivals = sorted(arrivals, key=lambda x: x.get('timeToStation', 999999))
        
        delays = []
        prev_time = None
        
        for arrival in sorted_arrivals[:10]:
            time_to_station = arrival.get('timeToStation', 0)
            
            if prev_time is not None:
                interval = time_to_station - prev_time
                if interval > expected_frequency * 1.5:
                    excess_delay = int(interval - expected_frequency)
                    
                    expected_arrival_str = arrival.get('expectedArrival')
                    expected_arrival = None
                    if expected_arrival_str:
                        try:
                            expected_arrival = datetime.fromisoformat(
                                expected_arrival_str.replace('Z', '+00:00')
                            )
                        except:
                            expected_arrival = datetime.now(timezone.utc)
                    else:
                        expected_arrival = datetime.now(timezone.utc)
                    
                    delays.append({
                        'vehicle_id': arrival.get('vehicleId'),
                        'expected_arrival': expected_arrival,
                        'delay_seconds': excess_delay,
                        'platform_name': arrival.get('platformName'),
                        'direction': arrival.get('direction')
                    })
            
            prev_time = time_to_station
        
        if delays:
            avg_delay = sum(d['delay_seconds'] for d in delays) / len(delays)
            if avg_delay < 30:
                return []
        
        return delays
    
    def _update_severity_estimates(self, session: Session):
        severity_levels = session.query(SeverityLevel).filter(
            SeverityLevel.is_suspension == False
        ).all()
        
        for severity in severity_levels:
            recent_samples = session.query(RealtimeDelaySample).join(
                Service
            ).filter(
                and_(
                    Service.mode == severity.mode_name,
                    RealtimeDelaySample.timestamp >= datetime.now(timezone.utc) - timedelta(days=7)
                )
            ).join(
                LiveDisruption,
                RealtimeDelaySample.disruption_id == LiveDisruption.disruption_id
            ).filter(
                LiveDisruption.severity_level == severity.severity_level
            ).all()
            
            if len(recent_samples) < self.min_samples_for_update:
                continue
            
            sample_mean_delay = sum(s.measured_delay_seconds for s in recent_samples) / len(recent_samples)
            sample_mean_minutes = sample_mean_delay / 60.0
            
            old_estimate = severity.estimated_delay_minutes or 10.0
            old_confidence = severity.confidence_score
            
            sample_weight = min(len(recent_samples) * 0.1, 5.0)
            
            new_estimate = (old_estimate * old_confidence + sample_mean_minutes * sample_weight) / (old_confidence + sample_weight)
            
            new_confidence = min(old_confidence + 0.05, 0.95)
            
            severity.estimated_delay_minutes = round(new_estimate, 2)
            severity.confidence_score = new_confidence
            severity.sample_count = len(recent_samples)
            severity.last_updated = datetime.now(timezone.utc)
            
            logger.info(
                f"Updated {severity.mode_name} L{severity.severity_level}: "
                f"{old_estimate:.1f}m -> {new_estimate:.1f}m "
                f"(conf: {old_confidence:.2f} -> {new_confidence:.2f}, samples: {len(recent_samples)})"
            )
    
    def get_severity_estimate(self, mode_name: str, severity_level: int) -> Optional[float]:
        with ConnectionBroker.get_session() as session:
            severity = session.query(SeverityLevel).filter_by(
                mode_name=mode_name,
                severity_level=severity_level
            ).first()
            
            if severity:
                return severity.estimated_delay_minutes
            
            return None
    
    def should_reduce_sampling(self) -> bool:
        with ConnectionBroker.get_session() as session:
            avg_confidence = session.query(
                func.avg(SeverityLevel.confidence_score)
            ).filter(
                SeverityLevel.is_suspension == False
            ).scalar()
            
            if avg_confidence and avg_confidence >= self.confidence_threshold:
                return True
            
            return False
