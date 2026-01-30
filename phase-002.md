# TfL Nexus - Phase 2 Data Pipeline - Implementation Plan

## Context & Objectives

### What Phase 2 IS
Phase 2 is **temporal data integration and live monitoring**. The goal is to:
- Ingest and store real-time disruption data from TfL
- Collect historical delay/performance data
- Build the temporal foundation for analytics
- Enable time-series queries on network reliability

### What Phase 2 IS NOT
Phase 2 does NOT include:
- ❌ Graph analytics (fragility scores, cascade analysis)
- ❌ Propagation simulation
- ❌ Robust routing algorithms
- ❌ Probability calculations
- ❌ Network centrality metrics
- ❌ User-facing API endpoints

**Stay in scope.** Phase 2 is about temporal data collection, not advanced analytics.

---

## CRITICAL: Start by Analyzing the TfL API Specification

**BEFORE writing any code, you MUST:**

1. **Read the entire TFL_API_SPEC.yaml file**
   - Understand all available endpoints
   - Study response structures
   - Note severity enum values
   - Check timestamp formats
   - Identify historical data availability

2. **Document your findings**
   - Which endpoints will you use for live status?
   - Which endpoints (if any) provide historical data?
   - What are the exact field names in responses?
   - What are the valid severity values?
   - How are disruptions identified (ID field name)?

3. **Create a mapping document**
   - API endpoint → Your use case
   - Response fields → Database columns
   - TfL terminology → Your database terminology

**DO NOT proceed to implementation until you have:**
- ✅ Read TFL_API_SPEC.yaml completely
- ✅ Identified all endpoints needed for Phase 2
- ✅ Verified field names and response structures
- ✅ Documented any limitations or gaps

---

## Critical Requirements

### 1. Respect Established Patterns
You are working in an **existing codebase** with:
- ✅ Established file structure from Phase 1
- ✅ Working database models (stops, services, edges)
- ✅ Working, tested TfL client
- ✅ Existing code conventions

**DO NOT:**
- Refactor Phase 1 code
- Change existing database schemas (only ADD tables)
- Duplicate functionality
- Break existing ingestion pipelines

**DO:**
- Follow existing patterns exactly
- Extend the established TfL client
- Match code style and structure
- Build on Phase 1 foundation

### 2. Use the Provided TfL API Specification
A **TFL_API_SPEC.yaml** file is provided containing:
- Line status endpoints
- Disruption feed structures
- Historical performance data (if available)
- Field descriptions and enums

**MANDATORY:** Refer to TFL_API_SPEC.yaml for ALL API interactions.
- ❌ DO NOT guess endpoint structures
- ❌ DO NOT assume status severity values
- ❌ DO NOT invent field names
- ✅ READ the spec file first for status/disruption endpoints
- ✅ VERIFY field names and enum values
- ✅ USE documented response structures

### 3. Time-Series Data Focus
- All temporal data stored in PostgreSQL
- Proper timestamp handling (UTC)
- Efficient time-range queries
- Partitioning for large datasets (if needed)
- Indexes on timestamp columns

---

## Database Schema Requirements

### New Tables to Implement

#### 1. `live_disruptions` table
**Purpose:** Store current and recent disruptions

Required columns:
- `disruption_id` - Primary key (serial)
- `tfl_disruption_id` - TfL's disruption identifier (unique, indexed)
- `service_id` - Foreign key to services.service_id (indexed)
- `severity` - Disruption severity level (e.g., "Severe", "Moderate", "Minor")
- `category` - Disruption category (e.g., "RealTime", "PlannedWork")
- `description` - Human-readable description (text)
- `affected_stops` - JSON or array of affected stop IDs (optional)
- `start_time` - When disruption started (timestamp, indexed)
- `expected_end_time` - Expected resolution (timestamp, nullable)
- `actual_end_time` - When actually resolved (timestamp, nullable)
- `created_at` - When record was created (timestamp)
- `updated_at` - Last update timestamp

**Indexes required:**
- Unique index on `tfl_disruption_id`
- Index on `service_id`
- Index on `start_time`
- Index on `severity`
- Composite index on `(service_id, start_time)` for time-range queries

**Important:**
- Track disruption lifecycle: created → active → resolved
- Update existing records when status changes
- Archive old disruptions (beyond 30 days) or partition by time

#### 2. `historical_delays` table
**Purpose:** Time-series delay data for services

Required columns:
- `delay_id` - Primary key (serial)
- `service_id` - Foreign key to services.service_id (indexed)
- `timestamp` - When delay was recorded (timestamp, indexed)
- `delay_minutes` - Delay amount in minutes (integer)
- `severity` - Categorical severity if available (optional)
- `hour_of_day` - Hour 0-23 (for time-of-day analysis)
- `day_of_week` - Day 0-6, Monday=0 (for day-of-week analysis)
- `is_peak_hour` - Boolean flag for peak/off-peak (optional)
- `created_at` - Record creation timestamp

**Indexes required:**
- Index on `service_id`
- Index on `timestamp` (critical for time-series queries)
- Composite index on `(service_id, timestamp)`
- Index on `hour_of_day`
- Index on `day_of_week`

**Important:**
- This table will grow large (consider partitioning by month)
- Derive `hour_of_day` and `day_of_week` from timestamp on insert
- Consider aggregation tables for performance (Phase 3)

#### 3. `transfer_statistics` table
**Purpose:** Pre-computed transfer reliability metrics

Required columns:
- `transfer_id` - Primary key (serial)
- `from_service_id` - Foreign key to services.service_id
- `to_service_id` - Foreign key to services.service_id
- `stop_id` - Foreign key to stops.stop_id (indexed)
- `mean_delay` - Average delay in minutes (float)
- `delay_variance` - Statistical variance (float)
- `delay_std_dev` - Standard deviation (float)
- `sample_count` - Number of observations (integer)
- `success_rate` - Proportion of successful transfers (float, 0-1)
- `last_computed` - When statistics were computed (timestamp)
- `created_at` - Record creation timestamp

**Indexes required:**
- Composite index on `(stop_id, from_service_id, to_service_id)` (unique)
- Index on `stop_id`
- Index on `last_computed`

**Important:**
- This is derived/computed data, not raw ingestion
- Recompute periodically (e.g., weekly) from historical_delays
- Used in Phase 3 for probability calculations

#### 4. `disruption_snapshots` table (optional but recommended)
**Purpose:** Historical snapshots of network-wide status

Required columns:
- `snapshot_id` - Primary key (serial)
- `snapshot_time` - When snapshot was taken (timestamp, indexed)
- `network_status` - JSON blob of all line statuses
- `total_disruptions` - Count of active disruptions
- `severity_breakdown` - JSON map of severity counts
- `created_at` - Record creation timestamp

**Indexes required:**
- Index on `snapshot_time`

**Rationale:** 
- Enables historical "what was the network status at time X" queries
- Foundation for cascade analysis in Phase 3
- Small table, one record per polling interval

---

## TfL Client Extension Requirements

The TfL client exists from Phase 1. You need to **ADD** methods for:

### Required New Methods

Refer to TFL_API_SPEC.yaml for exact endpoint specifications.

1. **Get line status (all lines)**
   - Purpose: Fetch current status of all lines
   - Check spec for: endpoint path, response structure, severity enum values
   - Returns: List of line statuses with disruption info

2. **Get line status (specific lines)**
   - Purpose: Fetch status for subset of lines
   - Check spec for: how to specify line IDs, response format
   - Returns: Status for requested lines only

3. **Get disruptions for a line**
   - Purpose: Detailed disruption information for a specific line
   - Check spec for: endpoint path, disruption object structure
   - Returns: List of active disruptions with details

4. **Get arrivals for a stop** (if available in spec)
   - Purpose: Real-time arrival predictions
   - Check spec for: endpoint path, response structure
   - Optional: Can derive delay from scheduled vs predicted times

5. **Get historical performance** (if available in spec)
   - Purpose: Historical reliability metrics
   - Check spec for: availability, endpoint, time range parameters
   - May not exist: TfL's historical API access is limited

### Client Method Pattern
Follow the **existing pattern** from Phase 1:
- Consistent method signature style
- Same error handling approach
- Caching for historical data (NOT for live status)
- Rate limiting
- Logging format

**CRITICAL:** Do NOT cache live disruption data.
- Use `cache_key=None` for real-time endpoints
- Cache historical data if available

---

## Data Collection Architecture

### Two Distinct Pipelines

#### Pipeline A: Real-Time Disruption Monitoring
**Mode:** Continuous polling (e.g., every 2-5 minutes)

**Flow:**
```
1. Poll TfL line status endpoint
   ↓
2. Parse response for each service
   ↓
3. For each service:
   a. Check if disruption is NEW (not in DB)
      → INSERT new disruption record
   b. Check if disruption is UPDATED (status changed)
      → UPDATE existing disruption record
   c. Check if disruption is RESOLVED (no longer in API)
      → UPDATE actual_end_time, mark resolved
   ↓
4. Log statistics (new/updated/resolved counts)
   ↓
5. Optional: Store network-wide snapshot
   ↓
6. Sleep until next poll interval
```

**Implementation details:**
- Run as background daemon/worker
- Graceful shutdown handling
- Error recovery (API down, DB connection lost)
- Monitoring/health checks
- Configurable poll interval

#### Pipeline B: Historical Delay Ingestion
**Mode:** Periodic batch (e.g., daily or weekly)

**Flow:**
```
1. IF historical API exists (check TFL_API_SPEC.yaml):
   a. Fetch historical delay data for date range
   b. Parse response
   c. INSERT into historical_delays
   ELSE:
   a. Derive delays from disruption duration
   b. Approximate based on severity
   c. INSERT synthetic delay records

2. After ingestion:
   a. Recompute transfer_statistics
   b. Aggregate by hour/day patterns
   c. Update last_computed timestamps
```

**Important:**
- TfL may not have comprehensive historical API
- May need to derive data from disruption records
- Acceptable to approximate in Phase 2
- Phase 3 will use this for analytics

---

## Real-Time Disruption Ingestion Details

### Disruption Lifecycle Tracking

A disruption goes through states:
1. **NEW** - First time seen from API
2. **ACTIVE** - Ongoing, may have updates
3. **RESOLVED** - No longer in API response

**Implementation:**
```python
def process_line_status(service_id: int, status_data: dict):
    """
    Process status for a single service
    Check TFL_API_SPEC.yaml for exact status_data structure
    """
    # Extract disruptions from status_data (field name in spec)
    disruptions = status_data.get('lineStatuses')  # VERIFY in spec
    
    if not disruptions or status_data.get('severity') == 'Good Service':
        # No disruptions - check if we need to resolve existing ones
        resolve_disruptions_for_service(service_id)
        return
    
    for disruption in disruptions:
        tfl_id = disruption.get('id')  # VERIFY in spec
        
        existing = db.query(LiveDisruption).filter_by(
            tfl_disruption_id=tfl_id
        ).first()
        
        if existing:
            # UPDATE existing disruption
            existing.severity = disruption.get('severity')
            existing.description = disruption.get('reason')
            existing.updated_at = datetime.utcnow()
        else:
            # INSERT new disruption
            new_disruption = LiveDisruption(
                tfl_disruption_id=tfl_id,
                service_id=service_id,
                severity=disruption.get('severity'),
                description=disruption.get('reason'),
                category=disruption.get('category'),
                start_time=parse_tfl_timestamp(...),  # Check spec
                # ...
            )
            db.add(new_disruption)

def resolve_disruptions_for_service(service_id: int):
    """Mark all active disruptions as resolved"""
    active = db.query(LiveDisruption).filter_by(
        service_id=service_id,
        actual_end_time=None
    ).all()
    
    for disruption in active:
        disruption.actual_end_time = datetime.utcnow()
        disruption.updated_at = datetime.utcnow()
```

### Severity Mapping
TfL uses specific severity values. Check TFL_API_SPEC.yaml for exact enum.

Expected values (verify in spec):
- "Good Service"
- "Minor Delays"
- "Severe Delays"
- "Part Suspended"
- "Suspended"
- "Planned Closure"
- "Part Closure"
- "Service Closed"

**Store exactly as TfL provides** - don't normalize/remap in Phase 2.

### Error Handling
- **API failure:** Log error, skip this poll cycle, continue
- **Parse error:** Log bad data, skip record, continue
- **DB error:** Rollback transaction, log, retry once, then skip
- **Network timeout:** Retry with exponential backoff

### Logging Requirements
Each poll cycle should log:
- Timestamp
- Lines checked
- New disruptions found
- Updated disruptions
- Resolved disruptions
- Errors encountered
- API response time

---

## Historical Delay Ingestion Details

### If TfL Provides Historical API

Check TFL_API_SPEC.yaml for historical performance endpoints.

**If available:**
```python
def ingest_historical_delays(start_date: date, end_date: date):
    """
    Ingest historical delay data for date range
    Check TFL_API_SPEC.yaml for endpoint and parameters
    """
    for service in all_services:
        # Fetch historical data (endpoint in spec)
        data = tfl_client.get_historical_performance(
            service.tfl_line_id,
            start_date,
            end_date
        )
        
        for record in data:
            # Parse timestamp (format in spec)
            timestamp = parse_timestamp(record['timestamp'])
            
            # Extract delay (field name in spec)
            delay_minutes = record.get('delay')
            
            # Derive time-based fields
            hour_of_day = timestamp.hour
            day_of_week = timestamp.weekday()
            
            # Check for duplicates
            existing = db.query(HistoricalDelay).filter_by(
                service_id=service.service_id,
                timestamp=timestamp
            ).first()
            
            if not existing:
                db.add(HistoricalDelay(
                    service_id=service.service_id,
                    timestamp=timestamp,
                    delay_minutes=delay_minutes,
                    hour_of_day=hour_of_day,
                    day_of_week=day_of_week
                ))
```

### If TfL Does NOT Provide Historical API

**Fallback approach:** Derive from disruption records

```python
def derive_delays_from_disruptions():
    """
    Approximate historical delays from disruption records
    This is a fallback if TfL doesn't have historical API
    """
    disruptions = db.query(LiveDisruption).filter(
        LiveDisruption.actual_end_time.isnot(None)  # Only resolved
    ).all()
    
    for disruption in disruptions:
        # Duration in minutes
        duration = (disruption.actual_end_time - disruption.start_time).total_seconds() / 60
        
        # Map severity to approximate delay
        severity_to_delay = {
            'Minor Delays': 5,
            'Severe Delays': 15,
            'Part Suspended': 30,
            'Suspended': 60,
        }
        
        delay = severity_to_delay.get(disruption.severity, 10)
        
        # Create hourly delay records for disruption duration
        current_time = disruption.start_time
        while current_time < disruption.actual_end_time:
            db.add(HistoricalDelay(
                service_id=disruption.service_id,
                timestamp=current_time,
                delay_minutes=delay,
                hour_of_day=current_time.hour,
                day_of_week=current_time.weekday()
            ))
            current_time += timedelta(hours=1)
```

**Document which approach you're using in comments.**

---

## Transfer Statistics Computation

This is **derived data**, computed from historical_delays.

**When to compute:**
- After initial historical data ingestion
- Periodically (e.g., weekly) to incorporate new data
- On-demand for specific transfers

**Algorithm:**
```python
def compute_transfer_statistics():
    """
    Compute transfer reliability metrics for all interchange stations
    """
    # Find all interchange stops (served by multiple services)
    interchange_stops = db.query(
        Stop.stop_id,
        func.count(func.distinct(Edge.service_id)).label('service_count')
    ).join(Edge).group_by(Stop.stop_id).having(
        func.count(func.distinct(Edge.service_id)) > 1
    ).all()
    
    for stop_id, _ in interchange_stops:
        # Get all service pairs at this stop
        services = db.query(Edge.service_id).filter(
            Edge.from_stop_id == stop_id
        ).union(
            db.query(Edge.service_id).filter(Edge.to_stop_id == stop_id)
        ).distinct().all()
        
        # For each pair of services
        for from_service in services:
            for to_service in services:
                if from_service == to_service:
                    continue
                
                # Get historical delays for both services at overlapping times
                delays = get_overlapping_delays(
                    stop_id, 
                    from_service.service_id,
                    to_service.service_id
                )
                
                if len(delays) < 10:  # Minimum sample size
                    continue
                
                # Compute statistics
                mean_delay = np.mean(delays)
                variance = np.var(delays)
                std_dev = np.std(delays)
                
                # Update or insert
                existing = db.query(TransferStatistic).filter_by(
                    stop_id=stop_id,
                    from_service_id=from_service.service_id,
                    to_service_id=to_service.service_id
                ).first()
                
                if existing:
                    existing.mean_delay = mean_delay
                    existing.delay_variance = variance
                    existing.delay_std_dev = std_dev
                    existing.sample_count = len(delays)
                    existing.last_computed = datetime.utcnow()
                else:
                    db.add(TransferStatistic(
                        stop_id=stop_id,
                        from_service_id=from_service.service_id,
                        to_service_id=to_service.service_id,
                        mean_delay=mean_delay,
                        delay_variance=variance,
                        delay_std_dev=std_dev,
                        sample_count=len(delays),
                        last_computed=datetime.utcnow()
                    ))

def get_overlapping_delays(stop_id, from_service_id, to_service_id):
    """
    Get delays where both services had delays at similar times
    This represents potential transfer conflicts
    """
    # Implementation depends on your time-window definition
    # Example: delays within 30 minutes of each other
    # Returns list of delay differentials
```

**Important:**
- Phase 2 computes basic statistics only
- Phase 3 will use these for probability calculations
- Document assumptions (time windows, minimum samples)

---

## Background Worker Implementation

### Daemon Process for Live Monitoring

```python
class DisruptionMonitor:
    """
    Background worker for continuous disruption monitoring
    """
    def __init__(self, poll_interval: int = 120):  # 2 minutes default
        self.poll_interval = poll_interval
        self.running = False
        self.tfl_client = TfLAPIClient()
        
    def start(self):
        """Start monitoring loop"""
        self.running = True
        logger.info("Disruption monitor started")
        
        while self.running:
            try:
                self.poll_cycle()
                time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                logger.info("Shutdown requested")
                self.stop()
            except Exception as e:
                logger.error(f"Poll cycle failed: {e}")
                time.sleep(self.poll_interval)  # Continue despite errors
    
    def stop(self):
        """Graceful shutdown"""
        logger.info("Disruption monitor stopping")
        self.running = False
    
    def poll_cycle(self):
        """Single poll cycle"""
        start_time = datetime.utcnow()
        
        # Fetch all line statuses
        statuses = self.tfl_client.get_all_line_statuses()
        
        # Process each line
        stats = {'new': 0, 'updated': 0, 'resolved': 0}
        
        for status in statuses:
            # Map TfL line ID to internal service ID
            service = get_service_by_tfl_id(status['id'])
            if not service:
                continue
            
            result = process_line_status(service.service_id, status)
            stats['new'] += result.get('new', 0)
            stats['updated'] += result.get('updated', 0)
            stats['resolved'] += result.get('resolved', 0)
        
        # Log cycle results
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(
            f"Poll cycle complete: {stats['new']} new, "
            f"{stats['updated']} updated, {stats['resolved']} resolved "
            f"({duration:.2f}s)"
        )
```

### Running as a Service

Provide **two deployment options only:**

**Option 1: Local Python Script**
```bash
# Run directly (for development/testing)
python monitor_disruptions.py

# Run in background with nohup (simple production)
nohup python monitor_disruptions.py > logs/monitor.log 2>&1 &

# Check if running
ps aux | grep monitor_disruptions.py

# Stop
pkill -f monitor_disruptions.py
```

**Option 2: Docker Container**
```dockerfile
FROM python:3.10-slim
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Run monitor
CMD ["python", "monitor_disruptions.py"]
```

**Docker Compose integration:**
```yaml
services:
  # ... existing postgres, redis services ...
  
  disruption_monitor:
    build: .
    container_name: tfl_nexus_monitor
    depends_on:
      - postgres
      - redis
    environment:
      - DB_HOST=postgres
      - DB_PORT=5432
      - DB_NAME=tfl_nexus
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - TFL_APP_KEY=${TFL_APP_KEY}
      - DISRUPTION_POLL_INTERVAL=120
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
    networks:
      - tfl_nexus_network
```

**Running with Docker Compose:**
```bash
# Start monitor with other services
docker-compose up -d

# View monitor logs
docker-compose logs -f disruption_monitor

# Stop monitor
docker-compose stop disruption_monitor

# Restart monitor
docker-compose restart disruption_monitor
```

**Document both options clearly.** Systemd is NOT required.

---

## Configuration & Environment

### New Environment Variables
```
# Phase 2 specific
DISRUPTION_POLL_INTERVAL=120        # Seconds between polls
HISTORICAL_BACKFILL_DAYS=90         # How far back to fetch
TRANSFER_STATS_MIN_SAMPLES=10       # Minimum for valid statistics
ENABLE_SNAPSHOT_LOGGING=true        # Store network snapshots
SNAPSHOT_INTERVAL=300               # Seconds between snapshots

# Database (should already exist from Phase 1)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=tfl_nexus
DB_USER=dev_user
DB_PASSWORD=dev_password
```

### Config Management
- Add to existing config module (don't create new one)
- Support env var overrides
- Provide defaults for development
- Validate ranges (e.g., poll interval >= 60)

---

## Validation Requirements

After Phase 2 implementation, you MUST verify:

### Real-Time Pipeline Validation
```sql
-- Check disruptions are being captured
SELECT 
    DATE_TRUNC('hour', created_at) as hour,
    COUNT(*) as disruption_count,
    COUNT(DISTINCT service_id) as affected_lines
FROM live_disruptions
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;

-- Check disruption lifecycle tracking
SELECT 
    severity,
    COUNT(*) FILTER (WHERE actual_end_time IS NULL) as active,
    COUNT(*) FILTER (WHERE actual_end_time IS NOT NULL) as resolved
FROM live_disruptions
WHERE start_time > NOW() - INTERVAL '7 days'
GROUP BY severity;

-- Verify updates are happening
SELECT 
    tfl_disruption_id,
    created_at,
    updated_at,
    updated_at - created_at as duration_tracked
FROM live_disruptions
WHERE updated_at > created_at
ORDER BY updated_at DESC
LIMIT 10;
```

### Historical Data Validation
```sql
-- Check historical delay distribution
SELECT 
    s.line_name,
    COUNT(*) as record_count,
    AVG(hd.delay_minutes) as avg_delay,
    MAX(hd.delay_minutes) as max_delay,
    MIN(timestamp) as earliest_record,
    MAX(timestamp) as latest_record
FROM historical_delays hd
JOIN services s ON hd.service_id = s.service_id
GROUP BY s.service_id, s.line_name
ORDER BY record_count DESC;

-- Check time-of-day distribution
SELECT 
    hour_of_day,
    COUNT(*) as records,
    AVG(delay_minutes) as avg_delay
FROM historical_delays
GROUP BY hour_of_day
ORDER BY hour_of_day;

-- Check day-of-week distribution
SELECT 
    day_of_week,
    COUNT(*) as records,
    AVG(delay_minutes) as avg_delay
FROM historical_delays
GROUP BY day_of_week
ORDER BY day_of_week;
```

### Transfer Statistics Validation
```sql
-- Check computed transfer statistics
SELECT 
    s.name as stop_name,
    s1.line_name as from_line,
    s2.line_name as to_line,
    ts.mean_delay,
    ts.delay_std_dev,
    ts.sample_count,
    ts.last_computed
FROM transfer_statistics ts
JOIN stops s ON ts.stop_id = s.stop_id
JOIN services s1 ON ts.from_service_id = s1.service_id
JOIN services s2 ON ts.to_service_id = s2.service_id
ORDER BY ts.mean_delay DESC
LIMIT 20;

-- Check coverage (how many interchanges have statistics)
SELECT 
    COUNT(DISTINCT stop_id) as stops_with_statistics
FROM transfer_statistics;
```

### Success Criteria
- ✅ Disruption monitor runs continuously without crashes
- ✅ New disruptions captured within 5 minutes
- ✅ Disruptions update when status changes
- ✅ Disruptions marked resolved when cleared
- ✅ Historical delays recorded (real or derived)
- ✅ Transfer statistics computed for major interchanges
- ✅ No orphaned records (valid foreign keys)
- ✅ Timestamps are reasonable (not future dates)

---

## Code Organization

### File Structure
Add to existing project:

```
models.py                  # MODIFY: Add new models
tfl_client.py              # MODIFY: Add status/disruption methods
config.py                  # MODIFY: Add Phase 2 config
monitor_disruptions.py     # NEW: Real-time monitoring daemon
ingest_historical.py       # NEW: Historical data ingestion
compute_statistics.py      # NEW: Transfer statistics computation
utils/timestamp_helpers.py # NEW (if needed): Time parsing utilities
```

### Class Structure

```python
# monitor_disruptions.py
class DisruptionMonitor:
    def __init__(self, poll_interval, db_session, tfl_client)
    def start(self)
    def stop(self)
    def poll_cycle(self)
    def process_line_status(self, service_id, status_data)
    def resolve_old_disruptions(self)

# ingest_historical.py  
class HistoricalDataIngestion:
    def __init__(self, db_session, tfl_client)
    def ingest_date_range(self, start_date, end_date)
    def derive_from_disruptions(self)  # Fallback method
    def validate_data_quality(self)

# compute_statistics.py
class TransferStatisticsComputer:
    def __init__(self, db_session)
    def compute_all_transfers(self)
    def compute_for_stop(self, stop_id)
    def get_overlapping_delays(self, ...)
```

---

## Testing Strategy

### Unit Tests
- Test disruption lifecycle state transitions
- Test timestamp parsing
- Test severity mapping
- Test statistics computation math

### Integration Tests
- Test against real TfL status API
- Test database inserts/updates
- Test monitor start/stop
- Test error recovery

### Load Tests
- Run monitor for 24 hours
- Check memory usage stability
- Check database growth rate
- Verify no connection leaks

### Manual Verification
- Observe disruptions appearing in database
- Compare DB records with TfL website
- Verify resolved disruptions marked correctly
- Check historical data makes sense

---

## Implementation Checklist

### Step 0: Analyze TfL API Specification (MANDATORY FIRST STEP)
- [ ] Read TFL_API_SPEC.yaml completely
- [ ] Identify status/disruption endpoints
- [ ] Document response structures
- [ ] Note all field names (exact spelling)
- [ ] Identify severity enum values
- [ ] Check for historical data endpoints
- [ ] Understand timestamp formats
- [ ] Create endpoint-to-use-case mapping
- [ ] Document any API limitations

### Step 1: Understand Existing Code (Phase 1)
- [ ] Review Phase 1 TfL client implementation
- [ ] Understand current code patterns
- [ ] Review existing models (stops, services, edges)
- [ ] Check database connection setup
- [ ] Understand logging patterns

### Step 2: Extend Database Models
- [ ] Add LiveDisruption model with indexes
- [ ] Add HistoricalDelay model with indexes
- [ ] Add TransferStatistic model
- [ ] Add DisruptionSnapshot model (optional)
- [ ] Run migrations to create tables

### Step 3: Extend TfL Client
- [ ] Add get_all_line_statuses() method
- [ ] Add get_line_status(line_ids) method
- [ ] Add get_disruptions(line_id) method (if separate endpoint)
- [ ] Add historical methods if available
- [ ] Test each method independently
- [ ] Ensure no caching on live data

### Step 4: Implement Disruption Monitor
- [ ] Create DisruptionMonitor class
- [ ] Implement poll_cycle logic
- [ ] Implement disruption CRUD operations
- [ ] Add error handling and recovery
- [ ] Add comprehensive logging
- [ ] Test graceful shutdown

### Step 5: Implement Historical Ingestion
- [ ] Check if TfL historical API exists
- [ ] If yes: implement direct ingestion
- [ ] If no: implement derivation from disruptions
- [ ] Add data validation
- [ ] Handle duplicates
- [ ] Test with sample date range

### Step 6: Implement Statistics Computation
- [ ] Identify interchange stations
- [ ] Compute overlapping delays
- [ ] Calculate mean, variance, std dev
- [ ] Update/insert statistics
- [ ] Add minimum sample size check
- [ ] Test with sample data

### Step 7: Deployment & Monitoring
- [ ] Create systemd service file
- [ ] Create Docker configuration
- [ ] Add health check endpoint
- [ ] Set up logging rotation
- [ ] Document deployment steps
- [ ] Test continuous operation

### Step 8: Validation
- [ ] Run monitor for 24+ hours
- [ ] Verify disruptions captured
- [ ] Check historical data quality
- [ ] Validate transfer statistics
- [ ] Run all SQL validation queries
- [ ] Document any limitations

---

## Common Pitfalls to Avoid

### 1. Real-Time Data Pitfalls
- Caching live status (defeats the purpose!)
- Not handling "Good Service" (resolved disruptions)
- Missing status changes (only checking new)
- Polling too frequently (rate limits)
- Not tracking disruption IDs (duplicates)

### 2. Timestamp Issues
- Mixing UTC and local time
- Not handling timezone info from TfL
- Future timestamps (clock skew)
- Parsing errors on different formats
- Missing timezone in database queries

### 3. Database Growth
- historical_delays grows unbounded (needs partitioning)
- Not archiving old disruptions
- No indexes on timestamp columns (slow queries)
- Missing composite indexes (bad performance)
- Large transaction commits (locks)

### 4. Statistics Computation
- Insufficient sample size (unreliable stats)
- Not handling missing data gracefully
- Recomputing too frequently (resource waste)
- Not validating input data quality
- Division by zero in variance

### 5. Error Handling
- Crashing on first API error
- Not recovering from DB disconnects
- No retry logic
- Logging sensitive data
- Silent failures

### 6. Code Quality
- Not following Phase 1 patterns
- Hardcoded poll intervals
- No graceful shutdown
- Missing logging context
- Not handling edge cases

---

## Success Metrics

Your Phase 2 implementation succeeds when:

✅ **Functional:**
- Monitor runs continuously (24+ hours)
- Disruptions captured within 5 minutes
- Historical data growing steadily
- Statistics computed successfully
- No data loss or corruption

✅ **Complete:**
- All new tables created
- All indexes added
- Real-time pipeline working
- Historical pipeline working
- Statistics pipeline working

✅ **Professional:**
- Follows Phase 1 patterns exactly
- Comprehensive error handling
- Detailed logging
- Clear documentation
- Deployment options provided

✅ **Validated:**
- SQL validation queries pass
- Data quality checks pass
- No orphaned records
- Reasonable timestamp ranges
- Statistics make sense

---

## Integration with Future Phases

Phase 2 provides the temporal foundation for:

**Phase 3 - Analytics:**
- Historical delays → fragility computation
- Transfer statistics → connection probability
- Disruption patterns → cascade prediction

**Phase 4 - API:**
- Live disruptions → /disruptions/live endpoint
- Historical patterns → route robustness scoring
- Transfer stats → connection risk estimates

**Keep Phase 2 focused on data collection.** 
Analytics and APIs come later.

---

## Final Notes

**Remember:**
- **START BY READING TFL_API_SPEC.yaml** - This is mandatory before any coding
- Phase 2 is about **temporal data collection**, not analytics
- **Follow Phase 1 patterns** exactly
- **Don't break existing code** from Phase 1
- **Test with real API data** (but handle failures)
- **Log everything** for debugging and monitoring

**Deployment Options:**
- ✅ Local Python script (simple, good for development)
- ✅ Docker container (production-ready, integrates with docker-compose)
- ❌ Systemd service (NOT required for this project)

**When stuck:**
1. **Re-read TFL_API_SPEC.yaml** for endpoint details
2. Review Phase 1 code patterns
3. Test with small time windows first
4. Monitor resource usage (CPU, memory, DB)
5. Validate data quality continuously

**Key difference from Phase 1:**
Phase 1 was one-time ingestion. Phase 2 runs **continuously**.
This requires different thinking about:
- Error recovery
- Resource management
- Graceful shutdown
- Monitoring health

**YAML Analysis is Critical:**
Your implementation will fail if you don't understand:
- Exact endpoint paths
- Response field names
- Severity enum values
- Timestamp formats
- Available vs unavailable features

Good luck! Phase 2 builds the temporal layer that makes Phase 3 analytics possible.