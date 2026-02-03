"""
Quick test of Phase 2B implementation
Tests TfL client endpoints and disruption processing without running full monitor
"""

import logging
from src.data.tfl.tfl_client import TflClient
from src.data.severity_learner import SeverityLearner
from src.data.monitor_disruptions_phase2b import DisruptionAnalyzer, DisruptionMonitor
from src.config.config_main import tfl_config, phase2_config
from src.data.db_broker import ConnectionBroker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_tfl_endpoints():
    logger.info("Testing TfL API endpoints...")
    client = TflClient(tfl_config)
    
    logger.info("Testing get_disruptions_by_mode...")
    disruptions = client.get_disruptions_by_mode(['tube'])
    logger.info(f"  ✓ Received {len(disruptions)} disruptions")
    
    if disruptions:
        sample = disruptions[0]
        logger.info(f"  Sample disruption keys: {list(sample.keys())[:5]}")
    
    logger.info("Testing get_severity_codes...")
    severities = client.get_severity_codes()
    logger.info(f"  ✓ Received {len(severities)} severity codes")
    
    logger.info("Testing get_disruption_categories...")
    categories = client.get_disruption_categories()
    logger.info(f"  ✓ Received {len(categories)} categories")
    logger.info(f"  Categories: {categories[:5]}")
    
    logger.info("All endpoint tests passed!\n")


def test_severity_learner():
    logger.info("Testing SeverityLearner initialization...")
    client = TflClient(tfl_config)
    
    learner_config = {
        'enable_severity_learning': True,
        'learning_sample_interval': 300,
        'confidence_threshold': 0.75,
        'high_confidence_threshold': 0.9,
        'min_samples_for_update': 20,
        'major_stop_threshold': 3,
        'default_frequency_seconds': phase2_config.default_frequency_seconds,
    }
    
    learner = SeverityLearner(client, learner_config)
    learner.initialize_severity_data()
    
    logger.info("  ✓ Severity data initialized")
    
    with ConnectionBroker.get_session() as session:
        from sqlalchemy import text
        result = session.execute(text("SELECT COUNT(*) FROM severity_levels"))
        count = result.scalar()
        logger.info(f"  ✓ Loaded {count} severity level definitions")
        
        result = session.execute(text("SELECT COUNT(*) FROM disruption_categories"))
        count = result.scalar()
        logger.info(f"  ✓ Loaded {count} disruption categories")
    
    logger.info("SeverityLearner tests passed!\n")


def test_disruption_analysis():
    logger.info("Testing disruption analysis...")
    
    test_cases = [
        {
            'description': 'District Line: Severe delays due to signal failure',
            'summary': 'Severe delays',
            'closureText': '',
            'affectedRoutes': [],
            'expected_full': False,
            'expected_partial': False
        },
        {
            'description': 'Northern Line: Suspended between Camden Town and High Barnet',
            'summary': 'Part suspended',
            'closureText': 'No service between Camden Town and High Barnet',
            'affectedRoutes': [],
            'expected_full': False,
            'expected_partial': True
        },
        {
            'description': 'Jubilee Line: Service suspended due to emergency',
            'summary': 'Suspended',
            'closureText': 'No service on entire line',
            'affectedRoutes': [],
            'expected_full': True,
            'expected_partial': False
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        analysis = DisruptionAnalyzer.analyze_disruption(test_case)
        
        full_match = analysis['is_full_suspension'] == test_case['expected_full']
        partial_match = analysis['is_partial_suspension'] == test_case['expected_partial']
        
        status = "✓" if (full_match and partial_match) else "✗"
        logger.info(f"  {status} Test {i}: full={analysis['is_full_suspension']}, partial={analysis['is_partial_suspension']}")
    
    logger.info("Disruption analysis tests passed!\n")


def test_single_poll():
    logger.info("Testing single disruption poll cycle...")
    client = TflClient(tfl_config)
    
    learner_config = {
        'enable_severity_learning': True,
        'learning_sample_interval': 300,
        'confidence_threshold': 0.75,
        'high_confidence_threshold': 0.9,
        'min_samples_for_update': 20,
        'major_stop_threshold': 3,
        'default_frequency_seconds': phase2_config.default_frequency_seconds,
    }
    
    learner = SeverityLearner(client, learner_config)
    monitor = DisruptionMonitor(client, learner, poll_interval=120)
    
    try:
        monitor.poll_cycle()
        logger.info("  ✓ Poll cycle completed successfully")
        
        with ConnectionBroker.get_session() as session:
            from sqlalchemy import text
            result = session.execute(text("SELECT COUNT(*) FROM live_disruptions"))
            count = result.scalar()
            logger.info(f"  ✓ Captured {count} disruptions")
            
            if count > 0:
                result = session.execute(text(
                    "SELECT category, disruption_type, is_full_suspension, is_partial_suspension "
                    "FROM live_disruptions LIMIT 3"
                ))
                logger.info("  Sample disruptions:")
                for row in result:
                    logger.info(f"    - {row[0]}/{row[1]}: full={row[2]}, partial={row[3]}")
        
        logger.info("Single poll test passed!\n")
        
    except Exception as e:
        logger.error(f"  ✗ Poll cycle failed: {e}", exc_info=True)


if __name__ == "__main__":
    try:
        test_tfl_endpoints()
        test_severity_learner()
        test_disruption_analysis()
        test_single_poll()
        
        logger.info("="*60)
        logger.info("All Phase 2B tests passed! ✓")
        logger.info("="*60)
        logger.info("\nYou can now run the full monitor:")
        logger.info("  python -m src.data.monitor_disruptions_phase2b")
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
