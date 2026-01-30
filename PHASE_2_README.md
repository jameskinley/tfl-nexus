# Phase 2: Temporal Data Integration - Implementation Guide

## Overview

Phase 2 implements real-time disruption monitoring and hybrid historical delay tracking for TfL services.

## Components Implemented

### 1. Database Models (`src/data/models.py`)
- **LiveDisruption**: Tracks real-time service disruptions with lifecycle management
- **HistoricalDelay**: Stores delay records with hybrid data sources (disruption-derived + arrival-measured)
- **TransferStatistic**: Pre-computed transfer reliability metrics at interchange stops
- **ArrivalRecord**: Raw arrival predictions for delay calculation

### 2. TfL Client Extensions (`src/data/tfl/tfl_client.py`)
New methods:
- `get_all_line_statuses(modes, detail)`: Fetch status for all lines in one request
- `get_line_status(line_ids, detail)`: Fetch status for specific lines
- `get_severity_codes()`: Get valid severity code mappings
- `get_disruption_categories()`: Get disruption category enums
- `get_stop_arrivals(stop_id)`: Get real-time arrival predictions

### 3. Real-Time Disruption Monitor (`src/data/monitor_disruptions.py`)
Background daemon that:
- Polls TfL every 2 minutes (configurable)
- Tracks disruption lifecycle: NEW → UPDATED → RESOLVED
- Stores disruptions in `live_disruptions` table
- Handles graceful shutdown (SIGINT/SIGTERM)

### 4. Historical Data Ingestion (`src/data/ingest_historical.py`)
Hybrid approach with two pipelines:

**Pipeline A: Disruption-Derived Delays**
- Processes resolved disruptions using severity-to-delay mapping
- Creates hourly `HistoricalDelay` records
- Data source: `disruption_derived`, confidence: `low`

**Pipeline B: Arrival Collection**
- Collects real-time arrival predictions for top 20 interchange stops
- Stores raw data in `arrival_records` table
- TODO: Implement arrival-to-delay calculator comparing with timetables

### 5. Transfer Statistics Computation (`src/data/compute_statistics.py`)
- Identifies interchange stops (served by 2+ services)
- Calculates delay statistics for each service pair
- Stores mean, variance, std_dev in `transfer_statistics`
- Requires minimum 10 samples (configurable)

## Configuration (`src/config/config_main.py`)

Environment variables:
```bash
DISRUPTION_POLL_INTERVAL=120          # Seconds between disruption polls
ARRIVAL_POLL_INTERVAL=60              # Seconds between arrival collections
HISTORICAL_BACKFILL_DAYS=90           # Days to backfill on initial run
TRANSFER_MIN_SAMPLES=10               # Minimum samples for valid statistics
```

Hardcoded config (Phase2Config):
- `severity_delay_mapping`: Maps TfL severity descriptions to delay minutes
- `top_interchange_stops`: 20 major interchange stations for arrival collection

## Setup Instructions

### 1. Create Database Tables
```bash
python create_phase2_tables.py
```

### 2. Run Initial Historical Backfill
```bash
# Backfill delays from existing disruptions (all time)
python -m src.data.ingest_historical --mode backfill

# Or backfill last N days only
python -m src.data.ingest_historical --mode backfill --days 30
```

### 3. Start Real-Time Disruption Monitor
```bash
# Run in foreground (development)
python -m src.data.monitor_disruptions

# Run in background (production)
nohup python -m src.data.monitor_disruptions > logs/monitor.log 2>&1 &

# Check if running
ps aux | grep monitor_disruptions

# Stop
pkill -f monitor_disruptions
```

### 4. Collect Arrival Data (Optional)
```bash
# One-time collection
python -m src.data.ingest_historical --mode collect

# Schedule via cron (every minute)
* * * * * cd /path/to/tfl-nexus && python -m src.data.ingest_historical --mode collect
```

### 5. Compute Transfer Statistics
```bash
# Run weekly or after significant data accumulation
python -m src.data.compute_statistics
```

## Testing

Run Phase 2 tests:
```bash
# All Phase 2 tests
pytest tests/test_monitor.py tests/test_historical.py tests/test_statistics.py -v

# Specific test file
pytest tests/test_monitor.py -v

# With coverage
pytest tests/test_monitor.py --cov=src.data.monitor_disruptions --cov-report=html
```

## Data Quality

### Data Source Types
- **disruption_derived**: Approximate delays from disruption severity (confidence: low)
- **arrival_measured**: Precise delays from arrival predictions vs timetables (confidence: high)

### Current Implementation Status
✅ Disruption-derived delays (fully implemented)
🚧 Arrival-measured delays (collection implemented, calculator TODO)

### Validation Queries

Check disruption capture:
```sql
SELECT 
    DATE_TRUNC('hour', created_at) as hour,
    COUNT(*) as disruption_count,
    COUNT(DISTINCT service_id) as affected_lines
FROM live_disruptions
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;
```

Check historical delay distribution:
```sql
SELECT 
    data_source,
    confidence_level,
    COUNT(*) as records,
    AVG(delay_minutes) as avg_delay
FROM historical_delays
GROUP BY data_source, confidence_level;
```

Check transfer statistics coverage:
```sql
SELECT 
    COUNT(*) as transfer_pairs,
    AVG(sample_count) as avg_samples,
    MIN(last_computed) as oldest_computation
FROM transfer_statistics;
```

## Monitoring & Logs

Monitor logs are written to stdout. Key log patterns:

**Normal operation:**
```
INFO - Poll cycle complete: 3 new, 5 updated, 2 resolved, 0 errors (1.23s)
```

**Errors to watch:**
```
ERROR - Poll cycle failed: <exception>
ERROR - Error processing line <id>: <exception>
```

## TODO Items

### High Priority
- [ ] Implement arrival-to-delay calculator (compare arrivals with cached timetables)
- [ ] Add timetable caching mechanism
- [ ] Implement data quality validation script

### Medium Priority
- [ ] Table partitioning for `historical_delays` (after 6 months of data)
- [ ] Automatic severity mapping refinement based on measured data
- [ ] Add health check endpoint for monitor daemon

### Low Priority
- [ ] Expand arrival collection to 50+ stops based on usage analysis
- [ ] Implement gap detection and backfill for monitor downtime
- [ ] Add Prometheus metrics export

## Architecture Notes

### Request Volume
- Disruption monitor: 1 request per cycle = 30 requests/hour
- Arrival collector (20 stops): 20 requests per cycle = 1,200 requests/hour
- **Total: ~1,230 requests/hour** (well under TfL's 5,000/hour limit)

### Data Growth Estimates
- `live_disruptions`: ~100-200 active records, ~500/month archived
- `historical_delays`: ~24 records/service/day = ~720/month/service
- `arrival_records`: ~20 stops × 60/min = 28,800/hour (consider retention policy)
- `transfer_statistics`: ~200 interchange pairs (relatively static)

### Scaling Considerations
- Consider archiving disruptions older than 90 days
- Implement `arrival_records` retention (keep only last 7 days?)
- Monitor database size and add partitioning if `historical_delays` exceeds 1M records

## Integration with Future Phases

**Phase 3 (Analytics):**
- Uses `historical_delays` for fragility score computation
- Uses `transfer_statistics` for connection probability calculations
- Builds on disruption patterns for cascade prediction

**Phase 4 (API):**
- Exposes `live_disruptions` via `/disruptions/live` endpoint
- Uses `transfer_statistics` for route robustness scoring
- Provides data quality indicators (source + confidence) in responses
