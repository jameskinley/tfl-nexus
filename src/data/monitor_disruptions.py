"""
Real-time disruption monitoring daemon for TfL Nexus - Phase 2

Continuously polls TfL API for line status and tracks disruption lifecycle.
"""

import logging
import time
import signal
import sys
from datetime import datetime, timezone
from typing import Dict, List

from src.data.models import LiveDisruption, Service
from src.data.tfl.tfl_client import TflClient
from src.data.db_broker import ConnectionBroker
from src.config.config_main import tfl_config, phase2_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DisruptionMonitor:
    """Background worker for continuous disruption monitoring."""
    
    def __init__(self, tfl_client: TflClient, poll_interval: int = 120):
        self.tfl_client = tfl_client
        self.poll_interval = poll_interval
        self.running = False
        self.modes = ['tube', 'dlr', 'overground', 'elizabeth-line']
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating shutdown")
        self.stop()
    
    def start(self):
        """Start the monitoring loop."""
        self.running = True
        logger.info(f"Disruption monitor started (poll interval: {self.poll_interval}s)")
        logger.info(f"Monitoring modes: {', '.join(self.modes)}")
        
        while self.running:
            try:
                self.poll_cycle()
                time.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Poll cycle failed: {e}", exc_info=True)
                time.sleep(self.poll_interval)
    
    def stop(self):
        """Graceful shutdown."""
        logger.info("Disruption monitor stopping")
        self.running = False
    
    def poll_cycle(self):
        """Execute single poll cycle."""
        start_time = datetime.utcnow()
        stats = {'new': 0, 'updated': 0, 'resolved': 0, 'errors': 0}
        
        try:
            statuses = self.tfl_client.get_all_line_statuses(self.modes, detail=True)
            
            with ConnectionBroker.get_session() as session:
                service_map = self._build_service_map(session)
                active_disruption_ids = set()
                
                for line in statuses:
                    try:
                        result = self._process_line_status(session, line, service_map)
                        stats['new'] += result.get('new', 0)
                        stats['updated'] += result.get('updated', 0)
                        active_disruption_ids.update(result.get('active_ids', []))
                    except Exception as e:
                        logger.error(f"Error processing line {line.get('id', 'unknown')}: {e}")
                        stats['errors'] += 1
                
                stats['resolved'] = self._resolve_missing_disruptions(
                    session, active_disruption_ids
                )
                
                session.commit()
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"Poll cycle complete: {stats['new']} new, {stats['updated']} updated, "
                f"{stats['resolved']} resolved, {stats['errors']} errors ({duration:.2f}s)"
            )
        
        except Exception as e:
            logger.error(f"Fatal error in poll cycle: {e}", exc_info=True)
            raise
    
    def _build_service_map(self, session) -> Dict[str, int]:
        """Build mapping of tfl_line_id to service_id."""
        services = session.query(Service.tfl_line_id, Service.service_id).all()
        return {tfl_id: svc_id for tfl_id, svc_id in services}
    
    def _process_line_status(self, session, line: dict, 
                            service_map: Dict[str, int]) -> Dict:
        """Process status for a single line."""
        result = {'new': 0, 'updated': 0, 'active_ids': []}
        
        line_id = line.get('id')
        if not line_id or line_id not in service_map:
            return result
        
        service_id = service_map[line_id]
        line_statuses = line.get('lineStatuses', [])
        
        if not line_statuses:
            return result
        
        for line_status in line_statuses:
            severity = line_status.get('statusSeverityDescription', '')
            
            if severity == 'Good Service':
                self._resolve_service_disruptions(session, service_id)
                continue
            
            tfl_id = str(line_status.get('id'))
            if not tfl_id:
                continue
            
            result['active_ids'].append(tfl_id)
            
            existing = session.query(LiveDisruption).filter_by(
                tfl_disruption_id=tfl_id
            ).first()
            
            if existing:
                if self._update_disruption(existing, line_status):
                    result['updated'] += 1
            else:
                self._create_disruption(session, tfl_id, service_id, line_status)
                result['new'] += 1
        
        return result
    
    def _create_disruption(self, session, tfl_id: str, 
                          service_id: int, line_status: dict):
        """Create new disruption record."""
        disruption_obj = line_status.get('disruption', {})
        
        disruption = LiveDisruption(
            tfl_disruption_id=tfl_id,
            service_id=service_id,
            severity=line_status.get('statusSeverityDescription', 'Unknown'),
            category=disruption_obj.get('category', 'Unknown'),
            description=line_status.get('reason') or disruption_obj.get('description', 'No description'),
            affected_stops=self._extract_affected_stops(disruption_obj),
            start_time=self._parse_timestamp(
                disruption_obj.get('created') or line_status.get('created')
            ),
            expected_end_time=None
        )
        
        session.add(disruption)
        logger.debug(f"Created disruption {tfl_id} for service {service_id}")
    
    def _update_disruption(self, disruption: LiveDisruption, line_status: dict) -> bool:
        """Update existing disruption if changed."""
        changed = False
        new_severity = line_status.get('statusSeverityDescription', '')
        disruption_obj = line_status.get('disruption', {})
        new_description = line_status.get('reason') or disruption_obj.get('description', '')
        
        if disruption.severity != new_severity:
            disruption.severity = new_severity
            changed = True
        
        if disruption.description != new_description:
            disruption.description = new_description
            changed = True
        
        if changed:
            disruption.updated_at = datetime.now(timezone.utc)
            logger.debug(f"Updated disruption {disruption.tfl_disruption_id}")
        
        return changed
    
    def _resolve_service_disruptions(self, session, service_id: int):
        """Mark all active disruptions for a service as resolved."""
        active = session.query(LiveDisruption).filter_by(
            service_id=service_id,
            actual_end_time=None
        ).all()
        
        for disruption in active:
            disruption.actual_end_time = datetime.now(timezone.utc)
            disruption.updated_at = datetime.now(timezone.utc)
    
    def _resolve_missing_disruptions(self, session, 
                                    active_ids: set) -> int:
        """Resolve disruptions not in current API response."""
        stale = session.query(LiveDisruption).filter(
            LiveDisruption.actual_end_time.is_(None),
            ~LiveDisruption.tfl_disruption_id.in_(active_ids)
        ).all()
        
        for disruption in stale:
            disruption.actual_end_time = datetime.now(timezone.utc)
            disruption.updated_at = datetime.now(timezone.utc)
        
        return len(stale)
    
    def _extract_affected_stops(self, disruption_obj: dict) -> str:
        """Extract affected stop IDs as JSON string."""
        affected = disruption_obj.get('affectedStops', [])
        if not affected:
            return None
        
        stop_ids = [stop.get('id') or stop.get('naptanId') for stop in affected if stop.get('id') or stop.get('naptanId')]
        return ','.join(stop_ids) if stop_ids else None
    
    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse ISO timestamp from TfL API."""
        if not timestamp_str:
            return datetime.now(timezone.utc)
        
        try:
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return datetime.now(timezone.utc)


def main():
    """Entry point for disruption monitor daemon."""
    logger.info("Initializing disruption monitor")
    
    ConnectionBroker.create_tables()
    
    client = TflClient(tfl_config)
    monitor = DisruptionMonitor(
        client,
        poll_interval=phase2_config.disruption_poll_interval
    )
    
    try:
        monitor.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        monitor.stop()
        logger.info("Disruption monitor terminated")


if __name__ == "__main__":
    main()
