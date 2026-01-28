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