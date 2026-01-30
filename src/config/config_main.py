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
        "940GZZLUKSX",  # King's Cross St. Pancras
        "940GZZLULVT",  # Liverpool Street
        "940GZZLUVIC",  # Victoria
        "940GZZLUWLO",  # Waterloo
        "940GZZLUPAC",  # Piccadilly Circus
        "940GZZLULST",  # Leicester Square
        "940GZZLUOXC",  # Oxford Circus
        "940GZZLUBST",  # Baker Street
        "940GZZLUBBB",  # Bank/Monument
        "940GZZLUGPS",  # Green Park
        "940GZZLUBDS",  # Bond Street
        "940GZZLUEUS",  # Euston
        "940GZZLUPAH",  # Paddington
        "940GZZLUCWR",  # Canary Wharf
        "940GZZLUTMP",  # Temple
        "940GZZLUHSK",  # High Street Kensington
        "940GZZLUEMB",  # Embankment
        "940GZZLUWSM",  # Westminster
        "940GZZLUCHL",  # Charing Cross
        "940GZZLUHPK",  # Hyde Park Corner
    ]

phase2_config = Phase2Config()