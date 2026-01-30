# TfL Nexus

TfL Nexus is a data aggregator and analytics API for journey planning within London. It analyzes historical and live data to provide optimal routes, scored on robustness.

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- TfL API Key ([Get one here](https://api-portal.tfl.gov.uk/))

### Setup

1. **Clone and configure environment**
   ```bash
   git clone <repository>
   cd tfl-nexus
   cp .env.example .env
   # Edit .env and add your TFL_PRIMARY_KEY
   ```

2. **Create Python virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Start PostgreSQL + PostGIS**
   ```bash
   cd deployment
   docker-compose up -d postgis
   cd ..
   ```

4. **Run unified ingestion (one command does everything!)**
   ```bash
   # Always activate venv first
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   
   python -m src.ingest --reset-db
   ```

   This single command will:
   - ✓ Initialize database schema (all 12 tables atomically)
   - ✓ Ingest stops, services, and edges from TfL API
   - ✓ Backfill historical delays from disruptions
   - ✓ Collect arrival predictions for key interchanges
   - ✓ Compute transfer statistics
   - ✓ Verify data integrity

5. **Start disruption monitor (optional)**
   ```bash
   # Option 1: Via Docker (recommended for production)
   cd deployment && docker-compose up -d disruption-monitor
   
   # Option 2: Standalone daemon
   python -m src.data.monitor_disruptions
   
   # Option 3: Integrated with ingestion
   python -m src.ingest --start-monitor
   ```

### Ingestion Options

```bash
# Full ingestion with default modes (from .env)
python -m src.ingest

# Ingest specific modes only
python -m src.ingest --modes tube,dlr

# Skip verification step for faster ingestion
python -m src.ingest --skip-verification

# Backfill last 30 days only
python -m src.ingest --backfill-days 30

# Reset database and start fresh (DESTRUCTIVE!)
python -m src.ingest --reset-db

# One-liner: reset DB and start monitor
python -m src.ingest --reset-db --start-monitor
```

### Configuration

All configuration is in `.env` file (see `.env.example` for template):

```bash
# Transport modes to ingest (comma-separated)
INGESTION_MODES=tube,dlr,elizabeth-line,overground,tram

# TfL API credentials
TFL_PRIMARY_KEY=your_key_here

# Database connection
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=tflnexus

# Phase 2 settings
DISRUPTION_POLL_INTERVAL=120  # seconds
HISTORICAL_BACKFILL_DAYS=90   # days
```

## Architecture

### Unified Ingestion Module (`src/ingest/`)

Single source of truth for all data ingestion:

```
src/ingest/
├── __init__.py         # Module exports
├── __main__.py         # CLI entry point
├── orchestrator.py     # Main pipeline coordinator
├── schema.py           # All database models + atomic initialization
├── static_network.py   # Phase 1: Stops/Services/Edges
└── temporal_data.py    # Phase 2: Delays/Statistics
```

**Key Design Decisions:**
- ✅ **Atomic schema initialization**: No incremental migrations, just drop+recreate
- ✅ **Functional API**: Pure functions instead of class-based pipelines
- ✅ **Single entry point**: `python -m src.ingest` does everything
- ✅ **Environment-driven**: Modes configurable via `INGESTION_MODES`

### Database Schema

12 tables across 4 phases:

**Phase 1 (Static Network):**
- `stops` - Transport stops with PostGIS geometry
- `services` - Tube/DLR/tram lines
- `edges` - Directional connections between stops

**Phase 2 (Temporal Data):**
- `live_disruptions` - Real-time disruption tracking
- `historical_delays` - Derived delay records
- `arrival_records` - Arrival predictions
- `transfer_statistics` - Service-to-service transfer metrics

**Phase 3 (Network Analysis):**
- `fragility_scores` - Network fragility metrics

**Phase 4 (User Features):**
- `users` - User accounts
- `saved_routes` - User-saved routes

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test module
pytest tests/test_ingestion.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

All tests use the new `src.ingest.*` module structure.

## Development

### Project Structure

```
tfl-nexus/
├── src/
│   ├── ingest/              # ⭐ Unified ingestion module
│   ├── data/
│   │   ├── db_broker.py     # Database connection
│   │   ├── monitor_disruptions.py  # Disruption monitor daemon
│   │   └── tfl/
│   │       └── tfl_client.py  # TfL API client
│   └── config/
│       └── config_main.py   # Environment configuration
├── tests/                   # Pytest test suite
├── deployment/
│   ├── docker-compose.yml   # PostgreSQL + Disruption Monitor
│   └── Dockerfile.monitor   # Monitor container image
├── .env.example            # Environment template
├── requirements.txt        # Python dependencies
└── README.md
```

### Docker Services

```bash
# Start PostgreSQL only
docker-compose up -d postgis

# Start PostgreSQL + Disruption Monitor
docker-compose up -d

# View logs
docker-compose logs -f disruption-monitor

# Stop all services
docker-compose down
```

## Migration from Old Structure

**Removed files (consolidated into `src/ingest/`):**
- ❌ `run_ingestion.py` → Use `python -m src.ingest`
- ❌ `create_phase2_tables.py` → Schema auto-created
- ❌ `fix_live_disruptions_schema.py` → No migrations needed
- ❌ `migrate_historical_delays_schema.py` → No migrations needed
- ❌ `migrate_transfer_statistics_schema.py` → No migrations needed
- ❌ `add_affected_stops_column.py` → No migrations needed
- ❌ `src/data/ingest_pipeline.py` → See `src/ingest/static_network.py`
- ❌ `src/data/ingest_historical.py` → See `src/ingest/temporal_data.py`
- ❌ `src/data/compute_statistics.py` → See `src/ingest/temporal_data.py`
- ❌ `src/data/models.py` → See `src/ingest/schema.py`

**Import updates:**
```python
# Old
from src.data.models import Stop, Service, Edge
from src.data.ingest_pipeline import DataIngestionPipeline

# New
from src.ingest.schema import Stop, Service, Edge
from src.ingest.static_network import ingest_stops, ingest_services, ingest_edges
```

## Troubleshooting

**PostgreSQL connection refused:**
```bash
# Check container is running
docker ps

# Check port mapping (5433 on host → 5432 in container)
docker-compose ps
```

**TfL API rate limiting:**
```bash
# Reduce modes or use --modes flag
python -m src.ingest --modes tube

# Add TFL_SECONDARY_KEY to .env for higher limits
```

**Database out of sync:**
```bash
# Nuclear option: reset everything
python -m src.ingest --reset-db
```

## License

MIT
