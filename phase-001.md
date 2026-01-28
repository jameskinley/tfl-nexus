# Phase 1 Data Ingestion Pipeline - Implementation Plan

## Context & Objectives

### What Phase 1 IS
Phase 1 is **static data foundation building**. The goal is to prove you can:
- Ingest, store, and query real transport data correctly
- Build a spatial database with proper schemas
- Establish the network topology (stops, services, edges)

### What Phase 1 IS NOT
Phase 1 does NOT include:
- ❌ Real-time disruption monitoring
- ❌ Historical delay analysis
- ❌ Graph analytics (fragility, propagation, robustness)
- ❌ API endpoint implementation
- ❌ Route planning algorithms
- ❌ Probability calculations

**Stay in scope.** Phase 1 is about data persistence, not analytics.

---

## Critical Requirements

### 1. Respect Established Patterns
You are working in an **existing codebase** with:
- ✅ Established file structure
- ✅ Working, tested TfL client
- ✅ Existing code conventions

**DO NOT:**
- Create new files without justification
- Refactor existing working code
- Change naming conventions
- Duplicate functionality that already exists

**DO:**
- Follow existing patterns exactly
- Use the established TfL client
- Match code style and structure
- Extend, don't replace

### 2. Use the Provided TfL API Specification
A **TFL_API_SPEC.yaml** file is provided containing:
- Complete endpoint documentation
- Request/response schemas
- Field descriptions
- Example responses

**MANDATORY:** Refer to TFL_API_SPEC.yaml for ALL API interactions.
- ❌ DO NOT guess endpoint structures
- ❌ DO NOT provide example API responses from memory
- ❌ DO NOT assume field names
- ✅ READ the spec file first
- ✅ VERIFY endpoints exist in the spec
- ✅ USE the exact field names documented

### 3. PostgreSQL + PostGIS Focus
- All data must be stored in PostgreSQL
- Spatial data MUST use PostGIS geometry types
- Use SQLAlchemy ORM (not raw SQL strings)
- Proper foreign keys and indexes required

---

## Database Schema Requirements

### Tables to Implement

#### 1. `stops` table
**Purpose:** Store all transport stops across all modes

Required columns:
- `stop_id` - Primary key (serial)
- `tfl_stop_id` - TfL's identifier (unique, indexed)
- `name` - Stop name
- `mode` - Transport mode (tube, bus, dlr, etc.)
- `latitude` - Latitude (float)
- `longitude` - Longitude (float)
- `location` - PostGIS geometry (POINT, SRID 4326)
- `zone` - TfL fare zone (optional)
- `hub_naptanid` - Hub/parent station ID (optional)
- `stop_type` - Stop type classification (optional)
- `created_at` - Timestamp
- `updated_at` - Timestamp

**Indexes required:**
- Unique index on `tfl_stop_id`
- Index on `mode`
- GIST spatial index on `location`

#### 2. `services` table
**Purpose:** Store transport lines/services

Required columns:
- `service_id` - Primary key (serial)
- `tfl_line_id` - TfL's line identifier (unique, indexed)
- `line_name` - Display name
- `mode` - Transport mode
- `operator` - Operating company (optional)
- `created_at` - Timestamp
- `updated_at` - Timestamp

**Indexes required:**
- Unique index on `tfl_line_id`
- Index on `mode`

#### 3. `edges` table
**Purpose:** Directional connections between stops

Required columns:
- `edge_id` - Primary key (serial)
- `from_stop_id` - Foreign key to stops.stop_id (indexed)
- `to_stop_id` - Foreign key to stops.stop_id (indexed)
- `service_id` - Foreign key to services.service_id (indexed)
- `scheduled_travel_time` - Travel time in seconds (optional for Phase 1)
- `sequence_order` - Position in route sequence
- `created_at` - Timestamp

**Indexes required:**
- Composite index on `(from_stop_id, service_id)`
- Composite index on `(to_stop_id, service_id)`

### Empty Tables for Future Phases
These tables should be **defined in models** but **NOT populated** in Phase 1:
- `historical_delays` (Phase 2)
- `transfer_statistics` (Phase 2)
- `fragility_scores` (Phase 3)
- `live_disruptions` (Phase 2)
- `users` (Phase 4)
- `saved_routes` (Phase 4)

**Define the schemas, but do not write ingestion code for them.**

---

## TfL Client Extension Requirements

The TfL client already exists and is working. You need to **ADD** methods for:

### Required New Methods

Refer to TFL_API_SPEC.yaml for exact endpoint specifications.

1. **Get stops by mode**
   - Purpose: Fetch all stops for given transport modes
   - Check spec for: endpoint path, query parameters, response structure

2. **Get lines by mode**
   - Purpose: Fetch all lines/services for given transport modes
   - Check spec for: endpoint path, mode values, response structure

3. **Get route sequence**
   - Purpose: Get ordered list of stops for a line
   - Check spec for: endpoint path, direction parameter, sequence structure
   - This is CRITICAL for building edges

4. **Get line details** (optional, if needed)
   - Purpose: Get additional metadata about a line
   - Check spec for: endpoint path, response structure

### Client Method Pattern
Follow the **existing pattern** in the TfL client:
- Method signature style
- Error handling approach
- Caching mechanism
- Rate limiting
- Logging format

**DO NOT** rewrite the client. **EXTEND** it.

---

## Ingestion Pipeline Architecture

### High-Level Flow

```
1. Initialize database (create tables if not exist)
   ↓
2. Ingest STOPS (from TfL API)
   - Fetch stops for all modes
   - Parse response
   - Create Stop records
   - Build tfl_stop_id → internal stop_id mapping
   ↓
3. Ingest SERVICES (from TfL API)
   - Fetch lines for all modes
   - Parse response
   - Create Service records
   - Build tfl_line_id → internal service_id mapping
   ↓
4. Ingest EDGES (from TfL route sequences)
   - For each service:
     - Fetch route sequence
     - Parse stop sequence
     - Create Edge records between consecutive stops
     - Use internal stop_id and service_id
   ↓
5. Verify data integrity
```

### Critical Implementation Details

#### Stop Ingestion
- **API endpoint:** Check TFL_API_SPEC.yaml for `/StopPoint/Mode/{modes}`
- **Response parsing:** 
  - Extract stop identifier (check spec for exact field name)
  - Extract name, lat, lon, mode
  - Handle stops that appear in multiple modes
- **Spatial data:**
  - Create PostGIS POINT geometry from lat/lon
  - SRID must be 4326 (WGS84)
  - Use: `WKTElement(f'POINT({lon} {lat})', srid=4326)`
- **Deduplication:**
  - Check if stop already exists by tfl_stop_id
  - Skip if exists, don't overwrite

#### Service Ingestion
- **API endpoint:** Check TFL_API_SPEC.yaml for `/Line/Mode/{modes}`
- **Response parsing:**
  - Extract line identifier (check spec for exact field name)
  - Extract line name, mode
  - Handle line metadata variations
- **Deduplication:**
  - Check if service already exists by tfl_line_id
  - Skip if exists, don't overwrite

#### Edge Ingestion (MOST COMPLEX)
- **API endpoint:** Check TFL_API_SPEC.yaml for route sequence endpoint
- **Challenge:** TfL doesn't give you edges directly. You must:
  1. Get route sequence for each line
  2. Parse the nested structure (check spec carefully)
  3. Extract ordered list of stop IDs
  4. Create edges between consecutive stops

**Route sequence parsing:**
- Structure is nested and complex (refer to spec)
- Multiple route branches may exist (inbound/outbound)
- Stop IDs in sequence may use different identifier than StopPoint API
- Handle both station IDs and stop IDs (check spec)

**Edge creation:**
```
For each service:
  For each route direction/branch:
    stops = [stop1, stop2, stop3, ..., stopN]
    For i in range(len(stops) - 1):
      Create Edge:
        from_stop_id = stops[i] (mapped to internal ID)
        to_stop_id = stops[i+1] (mapped to internal ID)
        service_id = current service (mapped to internal ID)
        sequence_order = i
```

**ID mapping is critical:**
- TfL stop IDs from route sequence may differ from StopPoint API
- Maintain mapping: tfl_stop_id → internal stop_id
- Handle cases where stop doesn't exist in stops table
  - Log warning
  - Skip edge
  - Count misses

#### Error Handling
- API request failures: retry with exponential backoff
- Missing data: log and skip, don't crash
- ID mapping failures: log and skip edge
- Database errors: rollback transaction, log, re-raise

#### Progress Tracking
- Log counts: stops processed, services processed, edges created
- Log percentage complete
- Log errors/warnings with context
- Periodic commits (every N records)

---

## Modes to Ingest

Focus on these London transport modes:
```python
TRANSPORT_MODES = [
    "tube",           # London Underground
    "dlr",            # Docklands Light Railway
    "elizabeth-line", # Elizabeth line
    "overground",     # London Overground
    "tram",           # Tramlink
]
```

**DO NOT** initially include:
- `bus` (too many stops, can add later)
- `river-bus` (limited, can add later)

**Rationale:** Start with rail-based modes for clean validation.

---

## Configuration & Environment

### Environment Variables Required
as is.


### Config Management
- Use existing config module pattern
- Don't hardcode values
- Support env var overrides
- Provide sensible defaults for development

---

## Validation Requirements

After ingestion completes, the pipeline MUST:

1. **Log summary statistics:**
   - Total stops inserted
   - Total services inserted
   - Total edges inserted
   - Processing duration
   - Error count

2. **Verify data integrity:**
   - Check no NULL geometries in stops
   - Check all edges reference valid stops
   - Check all edges reference valid services
   - Count stops per mode
   - Count services per mode

3. **Test spatial queries:**
   - Execute a nearest-neighbor query
   - Verify PostGIS is working
   - Log results

### Success Criteria
- ✅ 2,000+ stops inserted (for rail modes only)
- ✅ 50+ services inserted
- ✅ 5,000+ edges inserted
- ✅ Zero orphaned edges
- ✅ Spatial queries return results
- ✅ No crashes or unhandled exceptions

---

## Code Organization

### File Structure
Follow existing project structure. Expected files:

```
models.py          # SQLAlchemy models (you will MODIFY)
tfl_client.py      # TfL API client (you will EXTEND)
config.py          # Config (reference, don't modify unless needed)
ingest_pipeline.py # NEW: Main ingestion orchestration
utils.py           # NEW (if needed): Helper functions
```

### Ingestion Pipeline Structure
```python
class DataIngestionPipeline:
    def __init__(self, db_session, tfl_client):
        # Initialize with dependencies
        
    def ingest_stops(self, modes: List[str]) -> Dict[str, int]:
        # Return mapping: tfl_stop_id → internal stop_id
        
    def ingest_services(self, modes: List[str]) -> Dict[str, int]:
        # Return mapping: tfl_line_id → internal service_id
        
    def ingest_edges(self, 
                     service_mapping: Dict[str, int],
                     stop_mapping: Dict[str, int]):
        # Create edges using mappings
        
    def run_full_ingestion(self, modes: List[str]):
        # Orchestrate: stops → services → edges → verify
        
    def verify_data(self):
        # Run validation queries
```

---

## Testing Strategy

### Unit Tests (Optional but Recommended)
- Test ID mapping logic
- Test edge creation logic
- Test deduplication

### Integration Tests (REQUIRED)
- Test against real TfL API (with caching)
- Test database insertion
- Test full pipeline run

### Manual Verification (REQUIRED)
Provide SQL queries to verify:
```sql
-- Count stops by mode
SELECT mode, COUNT(*) FROM stops GROUP BY mode;

-- Find major hubs (high connection count)
SELECT s.name, COUNT(*) as connections
FROM stops s
JOIN edges e ON s.stop_id = e.from_stop_id OR s.stop_id = e.to_stop_id
GROUP BY s.stop_id, s.name
ORDER BY connections DESC
LIMIT 10;

-- Verify spatial index works
EXPLAIN ANALYZE
SELECT name FROM stops
WHERE ST_DWithin(
    location::geography,
    ST_MakePoint(-0.1278, 51.5074)::geography,
    1000
);
```

---

## Implementation Checklist

### Step 1: Understand Existing Code
- [ ] Read existing TfL client implementation
- [ ] Understand current code patterns
- [ ] Review existing models (if any)
- [ ] Check database connection setup

### Step 2: Study TfL API Specification
- [ ] Read TFL_API_SPEC.yaml completely
- [ ] Identify endpoints needed for stops, lines, route sequences
- [ ] Understand response structures
- [ ] Note any quirks or nested data

### Step 3: Extend TfL Client
- [ ] Add method for fetching stops by mode
- [ ] Add method for fetching lines by mode
- [ ] Add method for fetching route sequences
- [ ] Test each method independently
- [ ] Verify caching works

### Step 4: Define Database Models
- [ ] Create Stop model with PostGIS geometry
- [ ] Create Service model
- [ ] Create Edge model with foreign keys
- [ ] Add all required indexes
- [ ] Define (but don't populate) future phase tables

### Step 5: Implement Ingestion Pipeline
- [ ] Implement stop ingestion with ID mapping
- [ ] Implement service ingestion with ID mapping
- [ ] Implement edge ingestion with route parsing
- [ ] Add error handling throughout
- [ ] Add progress logging

### Step 6: Testing & Validation
- [ ] Run ingestion against real TfL API
- [ ] Verify data counts
- [ ] Run spatial queries
- [ ] Check for data quality issues
- [ ] Document any limitations discovered

### Step 7: Documentation
- [ ] Document any TfL API quirks discovered
- [ ] Provide example SQL queries for validation
- [ ] Note any data quality issues
- [ ] Document how to run the pipeline

---

## Common Pitfalls to Avoid

### 1. TfL API Gotchas
- Stop IDs may differ between endpoints (station ID vs stop ID)
- Route sequences have complex nested structure
- Not all lines have complete route data
- Bus routes are messy (skip in Phase 1)

### 2. Edge Creation Errors
- Creating edges with missing stops (handle gracefully)
- Creating duplicate edges (add uniqueness check)
- Wrong direction (edges are directional!)
- Missing sequence order (important for future phases)

### 3. Spatial Data Errors
- Wrong SRID (must be 4326)
- Swapping lat/lon (it's lon, lat in PostGIS!)
- NULL geometries (check before insert)
- Missing spatial index (queries will be slow)

### 4. Database Issues
- Foreign key violations (insert stops before edges!)
- Transaction not committed
- Connection pool exhaustion
- Missing indexes (performance degrades)

### 5. Code Quality
- Not following existing patterns
- Hardcoded values
- No error handling
- No progress logging
- Crashing on first error

---

## Success Metrics

Your implementation succeeds when:

✅ **Functional:**
- Pipeline runs without crashes
- Data is correctly inserted
- Spatial queries work
- Foreign keys are valid

✅ **Complete:**
- All required tables created
- All required indexes added
- All three ingestion phases work
- Verification queries pass

✅ **Professional:**
- Follows existing code patterns
- Proper error handling
- Comprehensive logging
- Clear documentation

✅ **Validated:**
- Data counts match expectations
- No orphaned records
- Spatial index is used
- Quality checks pass

---

## Final Notes

**Remember:**
- Phase 1 is about **data foundation**, not analytics
- **Read TFL_API_SPEC.yaml** before writing any API code
- **Follow existing patterns** exactly
- **Don't build what you don't need** in Phase 1
- **Test incrementally** (stops, then services, then edges)
- **Log everything** for debugging

**Always:**
1. Check TFL_API_SPEC.yaml
2. Review existing code patterns

**If stuck:***
1. Test with small data samples first
2. Log intermediate results
3. Validate each step before proceeding

Good luck! Phase 1 is the foundation for everything else.