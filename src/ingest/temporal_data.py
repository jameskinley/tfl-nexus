"""
Temporal Data Ingestion (Phase 2)

Consolidates historical delay backfilling and transfer statistics computation.
Merges functionality from ingest_historical.py and compute_statistics.py.

Components:
- Disruption-derived delays (backfill from LiveDisruption records)
- Arrival predictions (real-time collection for interchange stops)
- Transfer statistics (service-to-service delay correlations)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from tqdm import tqdm
import statistics

from .schema import (
    LiveDisruption, HistoricalDelay, Service, ArrivalRecord, Stop,
    TransferStatistic, Edge
)
from src.data.tfl.tfl_client import TflClient
from src.config.config_main import phase2_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# HISTORICAL DELAY BACKFILLING
# ============================================================================

def derive_delays_from_disruptions(session: Session, since_timestamp: datetime = None) -> Dict:
    """
    Process resolved disruptions into historical delay records.
    
    Args:
        session: SQLAlchemy session
        since_timestamp: Only process disruptions resolved after this time
    
    Returns:
        Statistics dictionary with counts
    """
    logger.info("Starting disruption-to-delay derivation")
    stats = {'records_created': 0, 'disruptions_processed': 0, 'skipped': 0}
    
    severity_mapping = phase2_config.severity_delay_mapping
    
    query = session.query(LiveDisruption).filter(
        LiveDisruption.actual_end_time.isnot(None)
    )
    
    if since_timestamp:
        query = query.filter(LiveDisruption.actual_end_time >= since_timestamp)
    
    disruptions = query.all()
    logger.info(f"Found {len(disruptions)} resolved disruptions to process")
    
    for disruption in tqdm(disruptions, desc="Deriving delays", unit="disruption"):
        try:
            delay_minutes = severity_mapping.get(disruption.severity, 10)
            
            if delay_minutes == 0:
                continue
            
            # Ensure timezone-aware datetimes
            current = disruption.start_time
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            
            end = disruption.actual_end_time
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            
            # Create hourly delay records for disruption duration
            while current < end:
                # Check if record already exists
                existing = session.query(HistoricalDelay).filter_by(
                    service_id=disruption.service_id,
                    timestamp=current
                ).first()
                
                if not existing:
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
                    session.add(delay_record)
                    stats['records_created'] += 1
                
                current += timedelta(hours=1)
            
            stats['disruptions_processed'] += 1
            
        except Exception as e:
            logger.error(f"Error processing disruption {disruption.disruption_id}: {e}")
            stats['skipped'] += 1
    
    session.commit()
    logger.info(
        f"Derivation complete: {stats['records_created']} delay records from "
        f"{stats['disruptions_processed']} disruptions ({stats['skipped']} errors)"
    )
    
    return stats


def collect_arrival_predictions(session: Session, tfl_client: TflClient) -> Dict:
    """
    Collect real-time arrival predictions for key interchange stops.
    
    Args:
        session: SQLAlchemy session
        tfl_client: Configured TfL API client
    
    Returns:
        Statistics dictionary with counts
    """
    interchange_stops = phase2_config.top_interchange_stops
    logger.info(f"Collecting arrivals for {len(interchange_stops)} stops")
    stats = {'records_created': 0, 'stops_processed': 0, 'errors': 0}
    
    # Build mappings
    stop_map = {}
    stops = session.query(Stop.tfl_stop_id, Stop.stop_id).filter(
        Stop.tfl_stop_id.in_(interchange_stops)
    ).all()
    for naptan, stop_id in stops:
        stop_map[naptan] = stop_id
    
    service_map = {}
    services = session.query(Service.tfl_line_id, Service.service_id).all()
    for tfl_id, svc_id in services:
        service_map[tfl_id] = svc_id
    
    # Collect arrivals
    for naptan_id in tqdm(interchange_stops, desc="Collecting arrivals", unit="stop"):
        try:
            if naptan_id not in stop_map:
                logger.warning(f"Stop {naptan_id} not in database, skipping")
                continue
            
            arrivals = tfl_client.get_stop_arrivals(naptan_id)
            timestamp = datetime.now(timezone.utc)
            
            for arrival in arrivals:
                line_id = arrival.get('lineId')
                if not line_id or line_id not in service_map:
                    continue
                
                try:
                    # Parse timestamp
                    expected_str = arrival.get('expectedArrival')
                    if expected_str:
                        try:
                            expected_arrival = datetime.fromisoformat(
                                expected_str.replace('Z', '+00:00')
                            )
                        except (ValueError, AttributeError):
                            expected_arrival = datetime.now(timezone.utc)
                    else:
                        expected_arrival = datetime.now(timezone.utc)
                    
                    arrival_record = ArrivalRecord(
                        stop_id=stop_map[naptan_id],
                        service_id=service_map[line_id],
                        vehicle_id=arrival.get('vehicleId'),
                        expected_arrival=expected_arrival,
                        time_to_station=arrival.get('timeToStation', 0),
                        timestamp=timestamp,
                        timetable_version=None
                    )
                    session.add(arrival_record)
                    stats['records_created'] += 1
                    
                except Exception as e:
                    logger.error(f"Error creating arrival record: {e}")
            
            stats['stops_processed'] += 1
            
        except Exception as e:
            logger.error(f"Error collecting arrivals for {naptan_id}: {e}")
            stats['errors'] += 1
    
    session.commit()
    logger.info(
        f"Arrival collection complete: {stats['records_created']} records from "
        f"{stats['stops_processed']} stops ({stats['errors']} errors)"
    )
    
    return stats


# ============================================================================
# TRANSFER STATISTICS COMPUTATION
# ============================================================================

def compute_transfer_statistics(session: Session) -> Dict:
    """
    Compute transfer delay statistics for all interchange stops.
    
    Args:
        session: SQLAlchemy session
    
    Returns:
        Statistics dictionary with counts
    """
    logger.info("Computing transfer statistics for all interchanges")
    stats = {'computed': 0, 'updated': 0, 'skipped': 0}
    min_samples = phase2_config.min_sample_size
    
    # Find interchange stops (served by multiple services)
    result = session.query(
        Edge.from_stop_id,
        func.count(func.distinct(Edge.service_id)).label('service_count')
    ).group_by(Edge.from_stop_id).having(
        func.count(func.distinct(Edge.service_id)) > 1
    ).all()
    
    interchange_stops = [stop_id for stop_id, _ in result]
    logger.info(f"Found {len(interchange_stops)} interchange stops")
    
    for stop_id in tqdm(interchange_stops, desc="Computing transfers", unit="stop"):
        try:
            # Get all services at this stop
            services = session.query(func.distinct(Edge.service_id)).filter(
                (Edge.from_stop_id == stop_id) | (Edge.to_stop_id == stop_id)
            ).all()
            service_ids = [svc_id for (svc_id,) in services]
            
            if len(service_ids) < 2:
                continue
            
            # Compute statistics for all service pairs
            for from_service in service_ids:
                for to_service in service_ids:
                    if from_service == to_service:
                        continue
                    
                    try:
                        # Get delays for both services
                        delays_from = session.query(
                            HistoricalDelay.timestamp,
                            HistoricalDelay.delay_minutes,
                            HistoricalDelay.confidence_level
                        ).filter(
                            HistoricalDelay.service_id == from_service
                        ).order_by(
                            HistoricalDelay.timestamp.desc()
                        ).limit(1000).all()
                        
                        delays_to = session.query(
                            HistoricalDelay.timestamp,
                            HistoricalDelay.delay_minutes,
                            HistoricalDelay.confidence_level
                        ).filter(
                            HistoricalDelay.service_id == to_service
                        ).order_by(
                            HistoricalDelay.timestamp.desc()
                        ).limit(1000).all()
                        
                        if not delays_from or not delays_to:
                            stats['skipped'] += 1
                            continue
                        
                        # Calculate delay differentials for overlapping times
                        delay_map_from = {ts: (delay, conf) for ts, delay, conf in delays_from}
                        delay_map_to = {ts: (delay, conf) for ts, delay, conf in delays_to}
                        
                        diffs = []
                        for timestamp in delay_map_from:
                            if timestamp in delay_map_to:
                                delay_f, conf_f = delay_map_from[timestamp]
                                delay_t, conf_t = delay_map_to[timestamp]
                                
                                # Weight by confidence
                                weight_from = 1.0 if conf_f == 'high' else 0.5
                                weight_to = 1.0 if conf_t == 'high' else 0.5
                                weight = (weight_from + weight_to) / 2
                                
                                diff = abs(delay_f - delay_t) * weight
                                diffs.append(diff)
                        
                        if len(diffs) < min_samples:
                            logger.debug(
                                f"Insufficient samples for transfer {from_service}->{to_service} "
                                f"at stop {stop_id}: {len(diffs)} < {min_samples}"
                            )
                            stats['skipped'] += 1
                            continue
                        
                        # Compute statistics
                        mean_delay = statistics.mean(diffs)
                        variance = statistics.variance(diffs) if len(diffs) > 1 else 0
                        std_dev = statistics.stdev(diffs) if len(diffs) > 1 else 0
                        success_rate = sum(1 for d in diffs if d < 5) / len(diffs)
                        
                        # Check if statistic already exists
                        existing = session.query(TransferStatistic).filter_by(
                            stop_id=stop_id,
                            from_service_id=from_service,
                            to_service_id=to_service
                        ).first()
                        
                        if existing:
                            existing.mean_delay = mean_delay
                            existing.delay_variance = variance
                            existing.delay_std_dev = std_dev
                            existing.sample_count = len(diffs)
                            existing.success_rate = success_rate
                            existing.last_computed = datetime.now(timezone.utc)
                            stats['updated'] += 1
                        else:
                            stat = TransferStatistic(
                                stop_id=stop_id,
                                from_service_id=from_service,
                                to_service_id=to_service,
                                mean_delay=mean_delay,
                                delay_variance=variance,
                                delay_std_dev=std_dev,
                                sample_count=len(diffs),
                                success_rate=success_rate,
                                last_computed=datetime.now(timezone.utc)
                            )
                            session.add(stat)
                            stats['computed'] += 1
                        
                    except Exception as e:
                        logger.error(
                            f"Error computing transfer {from_service}->{to_service} "
                            f"at stop {stop_id}: {e}"
                        )
                        stats['skipped'] += 1
                        
        except Exception as e:
            logger.error(f"Error computing transfers for stop {stop_id}: {e}")
            stats['skipped'] += 1
    
    session.commit()
    logger.info(
        f"Computation complete: {stats['computed']} new, {stats['updated']} updated, "
        f"{stats['skipped']} skipped"
    )
    
    return stats
