"""
Transfer statistics computation for TfL Nexus - Phase 2

Computes delay statistics for service transfers at interchange stops.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from tqdm import tqdm
import statistics

from src.data.models import TransferStatistic, HistoricalDelay, Stop, Edge
from src.data.db_broker import ConnectionBroker
from src.config.config_main import phase2_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TransferStatisticsComputer:
    """Computes transfer reliability metrics from historical delay data."""
    
    def __init__(self, session: Session):
        self.session = session
        self.min_samples = phase2_config.min_sample_size
    
    def compute_all_transfers(self) -> Dict:
        """
        Compute transfer statistics for all interchange stops.
        
        Returns:
            Statistics dictionary
        """
        logger.info("Computing transfer statistics for all interchanges")
        stats = {'computed': 0, 'updated': 0, 'skipped': 0}
        
        interchange_stops = self._find_interchange_stops()
        logger.info(f"Found {len(interchange_stops)} interchange stops")
        
        for stop_id in tqdm(interchange_stops, desc="Computing transfers", unit="stop"):
            try:
                result = self._compute_for_stop(stop_id)
                stats['computed'] += result.get('computed', 0)
                stats['updated'] += result.get('updated', 0)
                stats['skipped'] += result.get('skipped', 0)
            except Exception as e:
                logger.error(f"Error computing transfers for stop {stop_id}: {e}")
                stats['skipped'] += 1
        
        self.session.commit()
        logger.info(
            f"Computation complete: {stats['computed']} new, {stats['updated']} updated, "
            f"{stats['skipped']} skipped"
        )
        
        return stats
    
    def _find_interchange_stops(self) -> List[int]:
        """Find stops served by multiple services."""
        result = self.session.query(
            Edge.from_stop_id,
            func.count(func.distinct(Edge.service_id)).label('service_count')
        ).group_by(Edge.from_stop_id).having(
            func.count(func.distinct(Edge.service_id)) > 1
        ).all()
        
        return [stop_id for stop_id, _ in result]
    
    def _compute_for_stop(self, stop_id: int) -> Dict:
        """Compute transfer statistics for all service pairs at a stop."""
        result = {'computed': 0, 'updated': 0, 'skipped': 0}
        
        services = self._get_services_at_stop(stop_id)
        
        if len(services) < 2:
            return result
        
        for from_service in services:
            for to_service in services:
                if from_service == to_service:
                    continue
                
                try:
                    if self._compute_transfer_stat(stop_id, from_service, to_service):
                        existing = self._get_existing_stat(stop_id, from_service, to_service)
                        if existing:
                            result['updated'] += 1
                        else:
                            result['computed'] += 1
                    else:
                        result['skipped'] += 1
                except Exception as e:
                    logger.error(
                        f"Error computing transfer {from_service}->{to_service} "
                        f"at stop {stop_id}: {e}"
                    )
                    result['skipped'] += 1
        
        return result
    
    def _get_services_at_stop(self, stop_id: int) -> List[int]:
        """Get all services serving a stop."""
        services = self.session.query(func.distinct(Edge.service_id)).filter(
            (Edge.from_stop_id == stop_id) | (Edge.to_stop_id == stop_id)
        ).all()
        
        return [svc_id for (svc_id,) in services]
    
    def _compute_transfer_stat(self, stop_id: int, from_service: int, 
                               to_service: int) -> bool:
        """
        Compute transfer statistics for a service pair.
        
        Returns:
            True if statistics computed, False if insufficient data
        """
        delays_from = self._get_delays_for_service(from_service)
        delays_to = self._get_delays_for_service(to_service)
        
        if not delays_from or not delays_to:
            return False
        
        delay_diffs = self._calculate_delay_differentials(delays_from, delays_to)
        
        if len(delay_diffs) < self.min_samples:
            logger.debug(
                f"Insufficient samples for transfer {from_service}->{to_service} "
                f"at stop {stop_id}: {len(delay_diffs)} < {self.min_samples}"
            )
            return False
        
        mean_delay = statistics.mean(delay_diffs)
        variance = statistics.variance(delay_diffs) if len(delay_diffs) > 1 else 0
        std_dev = statistics.stdev(delay_diffs) if len(delay_diffs) > 1 else 0
        success_rate = sum(1 for d in delay_diffs if d < 5) / len(delay_diffs)
        
        existing = self._get_existing_stat(stop_id, from_service, to_service)
        
        if existing:
            existing.mean_delay = mean_delay
            existing.delay_variance = variance
            existing.delay_std_dev = std_dev
            existing.sample_count = len(delay_diffs)
            existing.success_rate = success_rate
            existing.last_computed = datetime.utcnow()
        else:
            stat = TransferStatistic(
                stop_id=stop_id,
                from_service_id=from_service,
                to_service_id=to_service,
                mean_delay=mean_delay,
                delay_variance=variance,
                delay_std_dev=std_dev,
                sample_count=len(delay_diffs),
                success_rate=success_rate,
                last_computed=datetime.now(timezone.utc)
            )
            self.session.add(stat)
        
        return True
    
    def _get_existing_stat(self, stop_id: int, from_service: int, 
                          to_service: int) -> TransferStatistic:
        """Get existing transfer statistic if it exists."""
        return self.session.query(TransferStatistic).filter_by(
            stop_id=stop_id,
            from_service_id=from_service,
            to_service_id=to_service
        ).first()
    
    def _get_delays_for_service(self, service_id: int) -> List[Dict]:
        """Get historical delays for a service, preferring high-confidence data."""
        delays = self.session.query(
            HistoricalDelay.timestamp,
            HistoricalDelay.delay_minutes,
            HistoricalDelay.confidence_level
        ).filter(
            HistoricalDelay.service_id == service_id
        ).order_by(
            HistoricalDelay.timestamp.desc()
        ).limit(1000).all()
        
        return [
            {'timestamp': ts, 'delay': delay, 'confidence': conf}
            for ts, delay, conf in delays
        ]
    
    def _calculate_delay_differentials(self, delays_from: List[Dict], 
                                       delays_to: List[Dict]) -> List[float]:
        """
        Calculate delay differentials for overlapping time windows.
        
        This represents potential transfer conflicts when both services delayed.
        """
        delay_map_from = {d['timestamp']: d for d in delays_from}
        delay_map_to = {d['timestamp']: d for d in delays_to}
        
        diffs = []
        
        for timestamp in delay_map_from:
            if timestamp in delay_map_to:
                weight_from = 1.0 if delay_map_from[timestamp]['confidence'] == 'high' else 0.5
                weight_to = 1.0 if delay_map_to[timestamp]['confidence'] == 'high' else 0.5
                weight = (weight_from + weight_to) / 2
                
                diff = abs(
                    delay_map_from[timestamp]['delay'] - 
                    delay_map_to[timestamp]['delay']
                ) * weight
                
                diffs.append(diff)
        
        return diffs


def main():
    """Entry point for transfer statistics computation."""
    logger.info("Starting transfer statistics computation")
    
    ConnectionBroker.create_tables()
    
    with ConnectionBroker.get_session() as session:
        computer = TransferStatisticsComputer(session)
        stats = computer.compute_all_transfers()
    
    logger.info(f"Computation complete: {stats}")


if __name__ == "__main__":
    main()
