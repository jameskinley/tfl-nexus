"""
Historical delay data ingestion for TfL Nexus - Phase 2

Hybrid approach:
1. Disruption-derived delays (immediate backfill)
2. Arrival-based delays (progressive improvement)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from tqdm import tqdm

from .models import (
    LiveDisruption, HistoricalDelay, Service, ArrivalRecord, Stop
)
from .tfl.tfl_client import TflClient
from .db_broker import ConnectionBroker
from ..config.config_main import tfl_config, phase2_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DisruptionDelayDeriver:
    """Derives historical delays from resolved disruption records."""
    
    def __init__(self, session: Session):
        self.session = session
        self.severity_mapping = phase2_config.severity_delay_mapping
    
    def derive_delays_from_disruptions(self, since_timestamp: datetime = None) -> Dict:
        """
        Process resolved disruptions into historical delay records.
        
        Args:
            since_timestamp: Only process disruptions resolved after this time
        
        Returns:
            Statistics dictionary
        """
        logger.info("Starting disruption-to-delay derivation")
        stats = {'records_created': 0, 'disruptions_processed': 0, 'skipped': 0}
        
        query = self.session.query(LiveDisruption).filter(
            LiveDisruption.actual_end_time.isnot(None)
        )
        
        if since_timestamp:
            query = query.filter(LiveDisruption.actual_end_time >= since_timestamp)
        
        disruptions = query.all()
        logger.info(f"Found {len(disruptions)} resolved disruptions to process")
        
        for disruption in tqdm(disruptions, desc="Deriving delays", unit="disruption"):
            try:
                records = self._create_delay_records(disruption)
                stats['records_created'] += records
                stats['disruptions_processed'] += 1
            except Exception as e:
                logger.error(f"Error processing disruption {disruption.disruption_id}: {e}")
                stats['skipped'] += 1
        
        self.session.commit()
        logger.info(
            f"Derivation complete: {stats['records_created']} delay records from "
            f"{stats['disruptions_processed']} disruptions ({stats['skipped']} errors)"
        )
        
        return stats
    
    def _create_delay_records(self, disruption: LiveDisruption) -> int:
        """Create hourly delay records for disruption duration."""
        delay_minutes = self.severity_mapping.get(disruption.severity, 10)
        
        if delay_minutes == 0:
            return 0
        
        # Ensure timezone-aware datetimes
        from datetime import timezone
        current = disruption.start_time
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        
        end = disruption.actual_end_time
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        
        records_created = 0
        
        while current < end:
            if not self._record_exists(disruption.service_id, current):
                delay_record = HistoricalDelay(
                    service_id=disruption.service_id,
                    timestamp=current,
                    delay_minutes=delay_minutes,
                    severity=disruption.severity,
                    hour_of_day=current.hour,
                    day_of_week=current.weekday(),
                    is_peak_hour=(7 <= current.hour <= 9) or (17 <= current.hour <= 19),
                    data_source='disruption_derived',
                    confidence_level='low',
                    timetable_version=None
                )
                self.session.add(delay_record)
                records_created += 1
            
            current += timedelta(hours=1)
        
        return records_created
    
    def _record_exists(self, service_id: int, timestamp: datetime) -> bool:
        """Check if delay record already exists."""
        return self.session.query(HistoricalDelay).filter_by(
            service_id=service_id,
            timestamp=timestamp
        ).first() is not None


class ArrivalCollector:
    """Collects real-time arrival predictions for key interchange stops."""
    
    def __init__(self, tfl_client: TflClient, session: Session):
        self.tfl_client = tfl_client
        self.session = session
        self.interchange_stops = phase2_config.top_interchange_stops
    
    def collect_arrivals(self) -> Dict:
        """
        Collect arrival predictions for all configured interchange stops.
        
        Returns:
            Statistics dictionary
        """
        logger.info(f"Collecting arrivals for {len(self.interchange_stops)} stops")
        stats = {'records_created': 0, 'stops_processed': 0, 'errors': 0}
        
        stop_map = self._build_stop_map()
        service_map = self._build_service_map()
        
        for naptan_id in tqdm(self.interchange_stops, desc="Collecting arrivals", unit="stop"):
            try:
                if naptan_id not in stop_map:
                    logger.warning(f"Stop {naptan_id} not in database, skipping")
                    continue
                
                arrivals = self.tfl_client.get_stop_arrivals(naptan_id)
                records = self._process_arrivals(
                    arrivals, stop_map[naptan_id], service_map
                )
                
                stats['records_created'] += records
                stats['stops_processed'] += 1
                
            except Exception as e:
                logger.error(f"Error collecting arrivals for {naptan_id}: {e}")
                stats['errors'] += 1
        
        self.session.commit()
        logger.info(
            f"Arrival collection complete: {stats['records_created']} records from "
            f"{stats['stops_processed']} stops ({stats['errors']} errors)"
        )
        
        return stats
    
    def _build_stop_map(self) -> Dict[str, int]:
        """Build mapping of naptan_id to stop_id."""
        stops = self.session.query(Stop.tfl_stop_id, Stop.stop_id).filter(
            Stop.tfl_stop_id.in_(self.interchange_stops)
        ).all()
        return {naptan: stop_id for naptan, stop_id in stops}
    
    def _build_service_map(self) -> Dict[str, int]:
        """Build mapping of tfl_line_id to service_id."""
        services = self.session.query(Service.tfl_line_id, Service.service_id).all()
        return {tfl_id: svc_id for tfl_id, svc_id in services}
    
    def _process_arrivals(self, arrivals: List[dict], stop_id: int,
                         service_map: Dict[str, int]) -> int:
        """Process arrival predictions into database records."""
        records_created = 0
        timestamp = datetime.utcnow()
        
        for arrival in arrivals:
            line_id = arrival.get('lineId')
            if not line_id or line_id not in service_map:
                continue
            
            try:
                arrival_record = ArrivalRecord(
                    stop_id=stop_id,
                    service_id=service_map[line_id],
                    vehicle_id=arrival.get('vehicleId'),
                    expected_arrival=self._parse_timestamp(arrival.get('expectedArrival')),
                    time_to_station=arrival.get('timeToStation', 0),
                    timestamp=timestamp,
                    timetable_version=None
                )
                self.session.add(arrival_record)
                records_created += 1
            except Exception as e:
                logger.error(f"Error creating arrival record: {e}")
        
        return records_created
    
    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse ISO timestamp from TfL API."""
        if not timestamp_str:
            return datetime.now(timezone.utc)
        
        try:
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return datetime.now(timezone.utc)


def backfill_from_disruptions(days: int = None):
    """
    Backfill historical delays from existing disruption data.
    
    Args:
        days: Number of days to backfill (None = all time)
    """
    logger.info("Starting disruption-based backfill")
    
    since = None
    if days:
        since = datetime.utcnow() - timedelta(days=days)
        logger.info(f"Backfilling from {since}")
    
    with ConnectionBroker.get_session() as session:
        deriver = DisruptionDelayDeriver(session)
        stats = deriver.derive_delays_from_disruptions(since_timestamp=since)
    
    logger.info(f"Backfill complete: {stats}")
    return stats


def collect_interchange_arrivals():
    """Collect current arrival predictions for interchange stops."""
    logger.info("Starting arrival collection")
    
    client = TflClient(tfl_config)
    
    with ConnectionBroker.get_session() as session:
        collector = ArrivalCollector(client, session)
        stats = collector.collect_arrivals()
    
    logger.info(f"Collection complete: {stats}")
    return stats


def main():
    """Entry point for historical data ingestion."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Historical delay data ingestion')
    parser.add_argument(
        '--mode',
        choices=['backfill', 'collect', 'both'],
        default='both',
        help='Operation mode'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=None,
        help='Days to backfill (default: all time)'
    )
    
    args = parser.parse_args()
    
    ConnectionBroker.create_tables()
    
    if args.mode in ['backfill', 'both']:
        backfill_from_disruptions(days=args.days)
    
    if args.mode in ['collect', 'both']:
        collect_interchange_arrivals()
    
    logger.info("Historical ingestion complete")


if __name__ == "__main__":
    main()
