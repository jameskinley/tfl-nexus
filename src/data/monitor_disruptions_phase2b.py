import logging
import time
import signal
import sys
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.data.models import LiveDisruption, Service, DisruptionCategory
from src.data.tfl.tfl_client import TflClient
from src.data.db_broker import ConnectionBroker
from src.data.severity_learner import SeverityLearner
from src.config.config_main import tfl_config, phase2_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DisruptionAnalyzer:

    @staticmethod
    def analyze_disruption(disruption_data: Dict) -> Dict:
        description = disruption_data.get('description', '').lower()
        summary = disruption_data.get('summary', '').lower()
        closure_text = disruption_data.get('closureText', '').lower()
        
        combined_text = f"{description} {summary} {closure_text}"
        
        suspension_keywords = [
            'suspended', 'no service', 'closed', 'not running',
            'not stopping', 'service suspended'
        ]
        partial_keywords = [
            'part suspended', 'partially suspended', 'section closed',
            'between', 'part closure', 'partial closure'
        ]
        
        has_suspension = any(keyword in combined_text for keyword in suspension_keywords)
        has_partial = any(keyword in combined_text for keyword in partial_keywords)
        
        is_full_suspension = has_suspension and not has_partial
        is_partial_suspension = has_suspension and has_partial
        
        start_naptan = None
        end_naptan = None
        
        if is_partial_suspension:
            start_naptan, end_naptan = DisruptionAnalyzer._extract_section_naptans(
                disruption_data.get('affectedRoutes', [])
            )
        
        return {
            'is_full_suspension': is_full_suspension,
            'is_partial_suspension': is_partial_suspension,
            'start_naptan': start_naptan,
            'end_naptan': end_naptan
        }
    
    @staticmethod
    def _extract_section_naptans(affected_routes: List[Dict]) -> tuple:
        if not affected_routes:
            return None, None
        
        for route in affected_routes:
            sequence = route.get('routeSectionNaptanEntrySequence', [])
            if sequence:
                sorted_sequence = sorted(sequence, key=lambda x: x.get('ordinal', 0))
                
                if sorted_sequence:
                    first_stop = sorted_sequence[0].get('stopPoint', {})
                    last_stop = sorted_sequence[-1].get('stopPoint', {})
                    
                    start_naptan = first_stop.get('naptanId')
                    end_naptan = last_stop.get('naptanId')
                    
                    if start_naptan and end_naptan:
                        return start_naptan, end_naptan
        
        return None, None
    
    @staticmethod
    def extract_line_ids(affected_routes: List[Dict]) -> List[str]:
        line_ids = set()
        for route in affected_routes:
            line_id = route.get('lineId')
            if line_id:
                line_ids.add(line_id)
        return list(line_ids)


class DisruptionMonitor:

    def __init__(self, tfl_client: TflClient, severity_learner: SeverityLearner, poll_interval: int = 120):
        self.tfl_client = tfl_client
        self.severity_learner = severity_learner
        self.poll_interval = poll_interval
        self.running = False
        self.modes = ['tube', 'dlr', 'overground', 'elizabeth-line']
        self.poll_count = 0
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown")
        self.stop()
    
    def start(self):
        self.running = True
        logger.info(f"Disruption monitor started (poll interval: {self.poll_interval}s)")
        logger.info(f"Monitoring modes: {', '.join(self.modes)}")
        
        self._initialize_metadata()
        
        while self.running:
            try:
                self.poll_cycle()
                self.poll_count += 1
                
                if self.poll_count % 10 == 0:
                    try:
                        self.severity_learner.sample_delays_during_disruptions()
                    except Exception as e:
                        logger.error(f"Severity learning failed: {e}")
                
                time.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Poll cycle failed: {e}", exc_info=True)
                time.sleep(self.poll_interval)
    
    def stop(self):
        logger.info("Disruption monitor stopping")
        self.running = False
    
    def _initialize_metadata(self):
        try:
            self.severity_learner.initialize_severity_data()
            
            with ConnectionBroker.get_session() as session:
                self._load_disruption_categories(session)
                session.commit()
        except Exception as e:
            logger.error(f"Metadata initialization failed: {e}")
    
    def _load_disruption_categories(self, session):
        existing_count = session.query(DisruptionCategory).count()
        if existing_count > 0:
            logger.info(f"Disruption categories already loaded ({existing_count} entries)")
            return
        
        categories = self.tfl_client.get_disruption_categories()
        
        for category_name in categories:
            category = DisruptionCategory(category_name=category_name)
            session.add(category)
        
        logger.info(f"Loaded {len(categories)} disruption categories")
    
    def poll_cycle(self):
        start_time = datetime.utcnow()
        stats = {'new': 0, 'updated': 0, 'resolved': 0, 'errors': 0}
        
        try:
            disruptions = self.tfl_client.get_disruptions_by_mode(self.modes)
            
            with ConnectionBroker.get_session() as session:
                service_map = self._build_service_map(session)
                active_disruption_ids = set()
                
                for disruption_data in disruptions:
                    try:
                        result = self._process_disruption(session, disruption_data, service_map)
                        stats['new'] += result.get('new', 0)
                        stats['updated'] += result.get('updated', 0)
                        active_disruption_ids.update(result.get('active_ids', []))
                    except Exception as e:
                        logger.error(f"Error processing disruption: {e}")
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
        services = session.query(Service.tfl_line_id, Service.service_id).all()
        return {tfl_id: svc_id for tfl_id, svc_id in services}
    
    def _process_disruption(self, session, disruption_data: Dict, 
                           service_map: Dict[str, int]) -> Dict:
        result = {'new': 0, 'updated': 0, 'active_ids': []}
        
        line_ids = DisruptionAnalyzer.extract_line_ids(
            disruption_data.get('affectedRoutes', [])
        )
        
        if not line_ids:
            return result
        
        analysis = DisruptionAnalyzer.analyze_disruption(disruption_data)
        
        for line_id in line_ids:
            if line_id not in service_map:
                logger.warning(f"Unknown line ID: {line_id}")
                continue
            
            service_id = service_map[line_id]
            
            tfl_id = self._generate_disruption_id(disruption_data, service_id)
            
            existing = session.query(LiveDisruption).filter_by(
                tfl_disruption_id=tfl_id
            ).first()
            
            if existing:
                if self._should_update_disruption(existing, disruption_data):
                    self._update_disruption(existing, disruption_data, analysis)
                    result['updated'] += 1
                result['active_ids'].append(tfl_id)
            else:
                self._create_disruption(
                    session, tfl_id, service_id, disruption_data, analysis
                )
                result['new'] += 1
                result['active_ids'].append(tfl_id)
        
        return result
    
    def _generate_disruption_id(self, disruption_data: Dict, service_id: int) -> str:
        category = disruption_data.get('category', 'Unknown')
        disruption_type = disruption_data.get('type', 'Unknown')
        created_str = disruption_data.get('created', '')
        description = disruption_data.get('description', '')[:50]
        
        base_string = f"{service_id}:{category}:{disruption_type}:{created_str}:{description}"
        hash_suffix = hashlib.md5(base_string.encode()).hexdigest()[:12]
        
        return f"disr-{category.lower()[:4]}-{hash_suffix}"
    
    def _should_update_disruption(self, existing: LiveDisruption, 
                                  disruption_data: Dict) -> bool:
        api_last_update_str = disruption_data.get('lastUpdate')
        if not api_last_update_str:
            return True
        
        try:
            api_last_update = datetime.fromisoformat(
                api_last_update_str.replace('Z', '+00:00')
            )
            
            if not existing.last_update:
                return True
            
            if api_last_update > existing.last_update.replace(tzinfo=timezone.utc):
                return True
        except:
            return True
        
        return False
    
    def _create_disruption(self, session, tfl_id: str, service_id: int,
                          disruption_data: Dict, analysis: Dict):
        created_str = disruption_data.get('created')
        created_dt = self._parse_timestamp(created_str) if created_str else datetime.now(timezone.utc)
        
        disruption = LiveDisruption(
            tfl_disruption_id=tfl_id,
            service_id=service_id,
            category=disruption_data.get('category', 'Unknown'),
            category_description=disruption_data.get('categoryDescription'),
            disruption_type=disruption_data.get('type'),
            description=disruption_data.get('description', 'No description'),
            summary=disruption_data.get('summary'),
            additional_info=disruption_data.get('additionalInfo'),
            closure_text=disruption_data.get('closureText'),
            is_full_suspension=analysis['is_full_suspension'],
            is_partial_suspension=analysis['is_partial_suspension'],
            affected_section_start_naptan=analysis['start_naptan'],
            affected_section_end_naptan=analysis['end_naptan'],
            affected_stops_json=disruption_data.get('affectedStops'),
            affected_routes_json=disruption_data.get('affectedRoutes'),
            created=created_dt,
            last_update=self._parse_timestamp(disruption_data.get('lastUpdate')),
            valid_from=self._parse_timestamp(disruption_data.get('validFrom')),
            valid_to=self._parse_timestamp(disruption_data.get('validTo')),
            start_time=created_dt
        )
        
        session.add(disruption)
        logger.debug(f"Created disruption {tfl_id} for service {service_id}")
    
    def _update_disruption(self, disruption: LiveDisruption, 
                          disruption_data: Dict, analysis: Dict):
        disruption.description = disruption_data.get('description', disruption.description)
        disruption.summary = disruption_data.get('summary')
        disruption.additional_info = disruption_data.get('additionalInfo')
        disruption.closure_text = disruption_data.get('closureText')
        disruption.category_description = disruption_data.get('categoryDescription')
        
        disruption.is_full_suspension = analysis['is_full_suspension']
        disruption.is_partial_suspension = analysis['is_partial_suspension']
        disruption.affected_section_start_naptan = analysis['start_naptan']
        disruption.affected_section_end_naptan = analysis['end_naptan']
        
        disruption.affected_stops_json = disruption_data.get('affectedStops')
        disruption.affected_routes_json = disruption_data.get('affectedRoutes')
        
        disruption.last_update = self._parse_timestamp(disruption_data.get('lastUpdate'))
        disruption.valid_to = self._parse_timestamp(disruption_data.get('validTo'))
        disruption.updated_at = datetime.now(timezone.utc)
        
        logger.debug(f"Updated disruption {disruption.tfl_disruption_id}")
    
    def _resolve_missing_disruptions(self, session, active_ids: set) -> int:
        stale = session.query(LiveDisruption).filter(
            LiveDisruption.actual_end_time.is_(None),
            ~LiveDisruption.tfl_disruption_id.in_(active_ids)
        ).all()
        
        for disruption in stale:
            disruption.actual_end_time = datetime.now(timezone.utc)
            disruption.updated_at = datetime.now(timezone.utc)
        
        return len(stale)
    
    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        if not timestamp_str:
            return None
        
        try:
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None


def start_monitor_daemon():
    logger.info("Initializing Phase 2B disruption monitor")
    
    ConnectionBroker.create_tables()
    
    client = TflClient(tfl_config)
    
    learner_config = {
        'enable_severity_learning': phase2_config.enable_severity_learning,
        'learning_sample_interval': phase2_config.learning_sample_interval,
        'confidence_threshold': phase2_config.confidence_threshold,
        'high_confidence_threshold': phase2_config.high_confidence_threshold,
        'min_samples_for_update': phase2_config.min_samples_for_update,
        'major_stop_threshold': phase2_config.major_stop_threshold,
        'default_frequency_seconds': phase2_config.default_frequency_seconds,
    }
    
    learner = SeverityLearner(client, learner_config)
    
    monitor = DisruptionMonitor(
        client,
        learner,
        poll_interval=phase2_config.disruption_poll_interval
    )
    
    try:
        monitor.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        monitor.stop()
        logger.info("Disruption monitor terminated")


def main():
    start_monitor_daemon()


if __name__ == "__main__":
    main()
