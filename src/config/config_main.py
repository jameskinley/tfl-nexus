from dotenv import load_dotenv
import os

load_dotenv()

class DBConfig():
    host: str = os.getenv("POSTGRES_HOST", "localhost")
    port: int = int(os.getenv("POSTGRES_PORT", 5432))
    user: str = os.getenv("POSTGRES_USER", "sa")
    password: str = os.getenv("POSTGRES_PASSWORD", "password")
    database: str = os.getenv("POSTGRES_DB", "tflnexus")

db_config = DBConfig()

class TflConfig():
    primary_key: str = os.getenv("TFL_PRIMARY_KEY", "")
    secondary_key: str = os.getenv("TFL_SECONDARY_KEY", "")
    base_url: str = os.getenv("TFL_BASE_URL", "https://api.tfl.gov.uk")
    use_cache: bool = os.getenv("TFL_USE_CACHE", "true").lower() == "true"

tfl_config = TflConfig()

class IngestionConfig():
    """Configuration for data ingestion process."""
    modes: list = os.getenv("INGESTION_MODES", "tube,dlr,elizabeth-line,overground,tram").split(",")

ingestion_config = IngestionConfig()

class Phase2Config():
    disruption_poll_interval: int = int(os.getenv("DISRUPTION_POLL_INTERVAL", "120"))
    arrival_poll_interval: int = int(os.getenv("ARRIVAL_POLL_INTERVAL", "60"))
    historical_backfill_days: int = int(os.getenv("HISTORICAL_BACKFILL_DAYS", "90"))
    min_sample_size: int = int(os.getenv("TRANSFER_MIN_SAMPLES", "10"))
    
    enable_severity_learning: bool = os.getenv("ENABLE_SEVERITY_LEARNING", "true").lower() == "true"
    learning_sample_interval: int = int(os.getenv("LEARNING_SAMPLE_INTERVAL", "300"))
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))
    high_confidence_threshold: float = float(os.getenv("HIGH_CONFIDENCE_THRESHOLD", "0.9"))
    min_samples_for_update: int = int(os.getenv("MIN_SAMPLES_FOR_UPDATE", "20"))
    major_stop_threshold: int = int(os.getenv("MAJOR_STOP_THRESHOLD", "3"))
    
    default_frequency_seconds = {
        "tube": 180,
        "dlr": 240,
        "overground": 300,
        "elizabeth-line": 300,
        "tram": 360,
    }
    
    severity_delay_mapping = {
        "Good Service": 0,
        "Minor Delays": 5,
        "Severe Delays": 15,
        "Part Suspended": 30,
        "Suspended": 60,
        "Part Closure": 45,
        "Planned Closure": 60,
        "Service Closed": 60,
        "Reduced Service": 10,
        "Special Service": 0,
    }
    
    top_interchange_stops = [
        "940GZZLUKSX",
        "940GZZLULVT",
        "940GZZLUVIC",
        "940GZZLUWLO",
        "940GZZLUPAC",
        "940GZZLULST",
        "940GZZLUOXC",
        "940GZZLUBST",
        "940GZZLUBBB",
        "940GZZLUGPS",
        "940GZZLUBDS",
        "940GZZLUEUS",
        "940GZZLUPAH",
        "940GZZLUCWR",
        "940GZZLUTMP",
        "940GZZLUHSK",
        "940GZZLUEMB",
        "940GZZLUWSM",
        "940GZZLUCHL",
        "940GZZLUHPK",
    ]

phase2_config = Phase2Config()