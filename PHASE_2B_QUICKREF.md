# Phase 2B Quick Reference

## Start Monitor
```bash
python phase2b.py monitor
```

## Check Status
```bash
python phase2b.py check
```

## Run Tests
```bash
python phase2b.py test
```

## Validation Queries
```bash
python phase2b.py validate                            # List all queries
python phase2b.py query active_disruptions_summary    # Run specific query
```

## Common Queries

### Active Disruptions
```sql
SELECT s.line_name, ld.category, ld.is_full_suspension, ld.is_partial_suspension
FROM live_disruptions ld
JOIN services s ON ld.service_id = s.service_id
WHERE actual_end_time IS NULL;
```

### Severity Learning Progress
```sql
SELECT mode_name, severity_level, description, 
       estimated_delay_minutes, confidence_score, sample_count
FROM severity_levels
WHERE is_suspension = false
ORDER BY mode_name, severity_level;
```

### Partial Suspensions with Sections
```sql
SELECT s.line_name, 
       ld.affected_section_start_naptan,
       ld.affected_section_end_naptan,
       ld.closure_text
FROM live_disruptions ld
JOIN services s ON ld.service_id = s.service_id
WHERE is_partial_suspension = true AND actual_end_time IS NULL;
```

## Configuration (.env)

```env
ENABLE_SEVERITY_LEARNING=true
LEARNING_SAMPLE_INTERVAL=300
CONFIDENCE_THRESHOLD=0.75
HIGH_CONFIDENCE_THRESHOLD=0.9
DISRUPTION_POLL_INTERVAL=120
```

## Key Features

✅ **Dedicated Disruption Endpoint** - More complete data than Status endpoint  
✅ **Intelligent Suspension Detection** - Distinguishes full vs partial  
✅ **Section Boundary Extraction** - Exact NaPTAN IDs for closed sections  
✅ **JSON Infrastructure Storage** - Complete affectedRoutes and affectedStops  
✅ **Adaptive Delay Learning** - Bayesian refinement from real-time samples  
✅ **Confidence-Based Sampling** - Reduces overhead as learning stabilizes

## Implementation Files

| File | Purpose |
|------|---------|
| `monitor_disruptions_phase2b.py` | Main monitor using Disruption endpoint |
| `severity_learner.py` | Adaptive severity→delay learning system |
| `phase2b_validation_queries.py` | SQL queries for data quality checks |
| `models.py` | Enhanced LiveDisruption + 3 new models |
| `tfl_client.py` | Extended with disruption/arrivals endpoints |

## Data Flow

1. **Poll** `/Line/Mode/{modes}/Disruption` every 2 minutes
2. **Analyze** description/closureText for suspension keywords
3. **Parse** routeSectionNaptanEntrySequence for section boundaries
4. **Store** complete JSON structures in database
5. **Sample** arrivals at major stops every 10th cycle
6. **Update** severity estimates using Bayesian formula
7. **Reduce** sampling as confidence increases

## Validation Checklist

After 24 hours of running:
- [ ] Disruptions captured match TfL website
- [ ] Suspension flags correctly set
- [ ] Section NaPTAN IDs populated for partial suspensions
- [ ] affected_routes_json and affected_stops_json contain data
- [ ] severity_levels confidence scores increasing
- [ ] realtime_delay_samples table collecting data

## Troubleshooting

**No disruptions captured**: Check TfL API status, verify modes configured  
**Learning not working**: Check realtime_delay_samples table, verify major stops identified  
**Suspensions not detected**: Review keyword list in DisruptionAnalyzer  
**High API load**: Increase LEARNING_SAMPLE_INTERVAL or reduce major_stop_threshold

## Phase 3 Preparation

Phase 2B provides:
- `affected_routes_json`: Exact edges to remove from graph
- `is_full_suspension`/`is_partial_suspension`: Algorithm selection
- `affected_section_start/end_naptan`: Precise closures
- `estimated_delay_minutes`: Edge weight adjustments
- Complete stop/route metadata for propagation analysis
