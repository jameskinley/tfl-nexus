# Phase 2B: Enhanced Disruption Tracking Implementation Guide

## Overview

Phase 2B enhances disruption tracking by:
- Switching from `/Line/Mode/{modes}/Status` to dedicated `/Line/Mode/{modes}/Disruption` endpoint
- Capturing granular affected infrastructure data (routes, stops, sections)
- Implementing adaptive severity-to-delay mapping using Bayesian learning
- Detecting full vs partial suspensions with section boundaries
- Sampling real-time delays to refine severity estimates over time

## What Changed

### Database Schema
- **live_disruptions table**: Added 15+ new columns for enhanced tracking
  - `disruption_type`, `category_description`, `summary`, `additional_info`, `closure_text`
  - `affected_stops_json`, `affected_routes_json` (full TfL API objects)
  - `is_full_suspension`, `is_partial_suspension`, suspension section NaPTAN IDs
  - Timestamps: `created`, `last_update`, `valid_from`, `valid_to`

- **New tables**:
  - `severity_levels`: Severity definitions with adaptive delay estimates
  - `disruption_categories`: Valid disruption category reference
  - `realtime_delay_samples`: Collected arrival delays for learning

### Code Architecture
- `src/data/models.py`: Enhanced models with Phase 2B fields
- `src/data/monitor_disruptions_phase2b.py`: Rewritten monitor using Disruption endpoint
- `src/data/severity_learner.py`: Adaptive learning system
- `src/data/tfl/tfl_client.py`: Added `get_disruptions_by_mode()` and `get_arrivals()`
- `src/config/config_main.py`: Phase 2B configuration options

## Installation & Setup

### 1. Install Dependencies

```bash
cd /path/to/tfl-nexus
source .venv/Scripts/activate
pip install -r requirements.txt
```

### 2. Run Migration

```bash
python run_phase2b_migration.py
```

This will:
- Truncate the `live_disruptions` table (clean start)
- Add new columns to `live_disruptions`
- Create `severity_levels`, `disruption_categories`, `realtime_delay_samples` tables

### 3. Configure Environment

Add to `.env` (optional overrides):

```env
ENABLE_SEVERITY_LEARNING=true
LEARNING_SAMPLE_INTERVAL=300
CONFIDENCE_THRESHOLD=0.75
HIGH_CONFIDENCE_THRESHOLD=0.9
MIN_SAMPLES_FOR_UPDATE=20
MAJOR_STOP_THRESHOLD=3
DISRUPTION_POLL_INTERVAL=120
```

### 4. Start Phase 2B Monitor

```bash
python -m src.data.monitor_disruptions_phase2b
```

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_SEVERITY_LEARNING` | `true` | Enable adaptive delay learning |
| `LEARNING_SAMPLE_INTERVAL` | `300` | Seconds between delay sampling (5 min) |
| `CONFIDENCE_THRESHOLD` | `0.75` | Confidence to reduce sampling frequency |
| `HIGH_CONFIDENCE_THRESHOLD` | `0.9` | Confidence to stop sampling |
| `MIN_SAMPLES_FOR_UPDATE` | `20` | Minimum samples before updating estimates |
| `MAJOR_STOP_THRESHOLD` | `3` | Minimum lines to be "major interchange" |

## How It Works

### Disruption Monitoring
1. Every 2 minutes, polls `/Line/Mode/{modes}/Disruption`
2. Extracts `affectedRoutes[]` and `affectedStops[]` (stores as JSON)
3. Analyzes description/closureText for suspension keywords
4. Parses `routeSectionNaptanEntrySequence` for partial suspension boundaries
5. Generates unique ID from category + type + created timestamp
6. Updates if `lastUpdate` timestamp changes

### Suspension Detection
- **Full suspension**: Keywords like "suspended", "no service" without "part/partial"
- **Partial suspension**: "part suspended", "section closed", "between X and Y"
- **Section extraction**: Sorts `routeSectionNaptanEntrySequence` by ordinal, extracts first/last NaPTAN IDs

### Adaptive Learning
1. Every 10th poll cycle, samples arrivals at major interchange stops
2. Compares arrival intervals to expected frequency (detects bunching)
3. Computes excess delay, attributes to current severity level
4. After 20+ samples, updates severity estimate using Bayesian formula:
   ```
   new_estimate = (old * old_conf + sample * sample_weight) / (old_conf + sample_weight)
   ```
5. Increases confidence score gradually (caps at 0.95)
6. Reduces sampling frequency once confidence > 0.75

## Validation

### After 24 Hours
Run validation queries:

```bash
python src/data/phase2b_validation_queries.py
```

Or run specific query:
```bash
python src/data/phase2b_validation_queries.py disruption_category_distribution
```

### Key Checks
1. **JSON population**: `affected_routes_json` and `affected_stops_json` should be populated
2. **Suspension detection**: Verify `is_full_suspension` and `is_partial_suspension` flags match TfL website
3. **Section boundaries**: Check partial suspensions have `affected_section_start_naptan` and `affected_section_end_naptan`
4. **Severity learning**: Query `severity_levels` to see confidence scores increasing
5. **Delay samples**: Verify `realtime_delay_samples` table collecting data

### Compare with TfL Website
Visit https://tfl.gov.uk/tube-dlr-overground/status and verify:
- Same disruptions captured
- Suspension types correct
- Affected stops match

## Troubleshooting

### Migration Fails
```bash
alembic current
```
Check current revision. If stuck, manually verify table structure matches migration.

### No Severity Data Loaded
Check logs for severity initialization errors. Manually trigger:
```python
from src.data.severity_learner import SeverityLearner
from src.data.tfl.tfl_client import TflClient
from src.config.config_main import tfl_config

client = TflClient(tfl_config)
learner = SeverityLearner(client, {})
learner.initialize_severity_data()
```

### Learning Not Converging
- Check `realtime_delay_samples` table for data
- Verify major stops identified: Query `stops` with high edge counts
- Increase `LEARNING_SAMPLE_INTERVAL` if hitting rate limits
- Check logs for arrival API errors

### Suspensions Not Detected
- Query disruptions with `is_full_suspension=false` and manually check descriptions
- Add suspension keywords to `DisruptionAnalyzer` if TfL uses new terms
- Check `affectedRoutes[].routeSectionNaptanEntrySequence` structure in database

## Phase 3 Preparation

Phase 2B data enables Phase 3 analytics:

### For Disruption Propagation
```sql
SELECT 
    affected_routes_json,
    affected_stops_json,
    is_full_suspension,
    affected_section_start_naptan,
    affected_section_end_naptan
FROM live_disruptions
WHERE actual_end_time IS NULL;
```

### For Severity-Based Routing
```sql
SELECT 
    mode_name,
    severity_level,
    estimated_delay_minutes,
    confidence_score
FROM severity_levels
WHERE is_suspension = false
ORDER BY mode_name, severity_level;
```

### For Edge Removal
Parse `affected_routes_json` to identify:
- `lineId`: Which service
- `routeSectionNaptanEntrySequence`: Ordered stops in closed section
- Match to `edges` table to disable specific edges

## Performance Notes

- Disruption endpoint response: ~50-200 KB (depends on active disruptions)
- Arrivals endpoint: ~5-20 KB per stop
- Sampling overhead: ~10-30 API calls per learning cycle (every 10 polls)
- Database writes: ~5-50 rows per poll (disruptions + samples)
- Learning converges in ~48-72 hours with typical disruption frequency

## Rollback

If Phase 2B causes issues:

```bash
python -m alembic downgrade -1
```

This will:
- Drop new tables
- Remove new columns
- Restore `live_disruptions` to Phase 2 schema

**Note**: Truncated data cannot be recovered. Use backup if needed.

## Next Steps

After Phase 2B is stable:
1. Let learning run for 1 week to collect diverse severity samples
2. Monitor confidence scores approaching 0.9
3. Verify suspension detection accuracy
4. Begin Phase 3: Graph-based disruption analytics
