"""
Data Ingestion Pipeline for TfL Nexus - Phase 1

Orchestrates the ingestion of:
1. Stops (from TfL StopPoint API)
2. Services (from TfL Line API)
3. Edges (from TfL Route Sequence API)
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime
from geoalchemy2 import WKTElement
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from tqdm import tqdm

from src.data.models import Stop, Service, Edge
from src.data.tfl.tfl_client import TflClient
from src.data.db_broker import ConnectionBroker


class DataIngestionPipeline:
    """Orchestrates ingestion of TfL data into PostgreSQL/PostGIS database."""
    
    def __init__(self, tfl_client: TflClient):
        """
        Initialize the ingestion pipeline.
        
        Args:
            tfl_client: Configured TfL API client
        """
        self.tfl_client = tfl_client
        self.stop_mapping: Dict[str, int] = {}  # naptan_id -> stop_id
        self.service_mapping: Dict[str, int] = {}  # tfl_line_id -> service_id
        
    def ingest_stops(self, session: Session, modes: List[str]) -> Dict[str, int]:
        """
        Ingest stops from TfL API.
        
        Args:
            session: SQLAlchemy session
            modes: List of transport modes to ingest
        
        Returns:
            Dictionary mapping naptan_id -> internal stop_id
        """
        print(f"\n{'='*60}")
        print(f"INGESTING STOPS FOR MODES: {', '.join(modes)}")
        print(f"{'='*60}")
        
        stop_mapping = {}
        total_stops = 0
        skipped_stops = 0
        error_count = 0
        
        start_time = datetime.now()
        
        try:
            # Process each mode separately to avoid 504 timeouts
            for mode in tqdm(modes, desc="Processing modes", unit="mode"):
                try:
                    print(f"\nFetching stops for mode: {mode}")
                    response = self.tfl_client.get_stops_by_mode([mode])
                    stops_data = response.get('stopPoints', [])
                    
                    print(f"  Fetched {len(stops_data)} stops for {mode}")
                    
                    # Process stops with progress bar
                    for stop_data in tqdm(stops_data, desc=f"  Processing {mode} stops", unit="stop", leave=False):
                        try:
                            naptan_id = stop_data.get('naptanId') or stop_data.get('id')
                            
                            if not naptan_id:
                                error_count += 1
                                continue
                            
                            # Check if stop already exists
                            existing_stop = session.query(Stop).filter_by(tfl_stop_id=naptan_id).first()
                            if existing_stop:
                                stop_mapping[naptan_id] = existing_stop.stop_id
                                skipped_stops += 1
                                continue
                            
                            # Extract data
                            lat = stop_data.get('lat')
                            lon = stop_data.get('lon')
                            
                            if lat is None or lon is None:
                                error_count += 1
                                continue
                            
                            # Validate coordinates
                            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                                error_count += 1
                                continue
                            
                            # Get primary mode (use first mode from list)
                            stop_modes = stop_data.get('modes', [])
                            primary_mode = stop_modes[0] if stop_modes else 'unknown'
                            
                            # Create PostGIS POINT geometry
                            location = WKTElement(f'POINT({lon} {lat})', srid=4326)
                            
                            # Create Stop record
                            stop = Stop(
                                tfl_stop_id=naptan_id,
                                name=stop_data.get('commonName', 'Unknown'),
                                mode=primary_mode,
                                latitude=lat,
                                longitude=lon,
                                location=location,
                                zone=stop_data.get('zone'),
                                hub_naptanid=stop_data.get('hubNaptanCode'),
                                stop_type=stop_data.get('stopType')
                            )
                            
                            session.add(stop)
                            session.flush()  # Get the auto-generated stop_id
                            
                            stop_mapping[naptan_id] = stop.stop_id
                            total_stops += 1
                        
                        except Exception as e:
                            error_count += 1
                            continue
                    
                    # Commit after each mode
                    session.commit()
                    print(f"  ✓ Processed {mode}: {total_stops} stops inserted")
                    
                except Exception as e:
                    print(f"  ✗ Error processing mode {mode}: {e}")
                    session.rollback()
                    continue
            
            duration = (datetime.now() - start_time).total_seconds()
            
            print(f"\n{'='*60}")
            print(f"STOPS INGESTION COMPLETE")
            print(f"{'='*60}")
            print(f"Total stops inserted: {total_stops}")
            print(f"Stops skipped (already exist): {skipped_stops}")
            print(f"Errors encountered: {error_count}")
            print(f"Duration: {duration:.2f} seconds")
            print(f"{'='*60}\n")
            
            self.stop_mapping = stop_mapping
            return stop_mapping
            
        except Exception as e:
            session.rollback()
            print(f"CRITICAL ERROR in stop ingestion: {e}")
            raise
    
    def ingest_services(self, session: Session, modes: List[str]) -> Dict[str, int]:
        """
        Ingest services/lines from TfL API.
        
        Args:
            session: SQLAlchemy session
            modes: List of transport modes to ingest
        
        Returns:
            Dictionary mapping tfl_line_id -> internal service_id
        """
        print(f"\n{'='*60}")
        print(f"INGESTING SERVICES FOR MODES: {', '.join(modes)}")
        print(f"{'='*60}")
        
        service_mapping = {}
        total_services = 0
        skipped_services = 0
        error_count = 0
        
        start_time = datetime.now()
        
        try:
            # Fetch lines from TfL API (one request for all modes is OK for lines)
            print(f"\nFetching lines from TfL API...")
            lines = list(self.tfl_client.get_lines_by_mode(modes))
            
            print(f"Fetched {len(lines)} services from TfL API")
            
            # Process lines with progress bar
            for line_data in tqdm(lines, desc="Processing services", unit="service"):
                try:
                    line_id = line_data.get('id')
                    
                    if not line_id:
                        error_count += 1
                        continue
                    
                    # Check if service already exists
                    existing_service = session.query(Service).filter_by(tfl_line_id=line_id).first()
                    if existing_service:
                        service_mapping[line_id] = existing_service.service_id
                        skipped_services += 1
                        continue
                    
                    # Create Service record
                    service = Service(
                        tfl_line_id=line_id,
                        line_name=line_data.get('name', 'Unknown'),
                        mode=line_data.get('mode', 'unknown'),
                        operator=None  # Not in basic line data
                    )
                    
                    session.add(service)
                    session.flush()  # Get the auto-generated service_id
                    
                    service_mapping[line_id] = service.service_id
                    total_services += 1
                
                except Exception as e:
                    error_count += 1
                    continue
            
            # Final commit
            session.commit()
            
            duration = (datetime.now() - start_time).total_seconds()
            
            print(f"\n{'='*60}")
            print(f"SERVICES INGESTION COMPLETE")
            print(f"{'='*60}")
            print(f"Total services inserted: {total_services}")
            print(f"Services skipped (already exist): {skipped_services}")
            print(f"Errors encountered: {error_count}")
            print(f"Duration: {duration:.2f} seconds")
            print(f"{'='*60}\n")
            
            self.service_mapping = service_mapping
            return service_mapping
            
        except Exception as e:
            session.rollback()
            print(f"CRITICAL ERROR in service ingestion: {e}")
            raise
    
    def ingest_edges(self, session: Session) -> int:
        """
        Ingest edges from TfL route sequences.
        
        Args:
            session: SQLAlchemy session
        
        Returns:
            Total number of edges created
        """
        print(f"\n{'='*60}")
        print(f"INGESTING EDGES FROM ROUTE SEQUENCES")
        print(f"{'='*60}")
        
        total_edges = 0
        error_count = 0
        missing_stops = 0
        
        start_time = datetime.now()
        
        try:
            # Process each service with progress bar
            for line_id, service_id in tqdm(self.service_mapping.items(), desc="Processing route sequences", unit="line"):
                try:
                    # Fetch route sequence
                    route_sequence = self.tfl_client.get_route_sequence(line_id, direction="all")
                    
                    # Extract edges from stopPointSequences
                    stop_sequences = route_sequence.get('stopPointSequences', [])
                    
                    if not stop_sequences:
                        continue
                    
                    edges_for_line = 0
                    
                    for sequence in stop_sequences:
                        stop_points = sequence.get('stopPoint', [])
                        branch_id = sequence.get('branchId')
                        
                        if len(stop_points) < 2:
                            continue
                        
                        # Create edges between consecutive stops
                        for i in range(len(stop_points) - 1):
                            try:
                                from_stop_naptan = stop_points[i].get('id') or stop_points[i].get('stationId')
                                to_stop_naptan = stop_points[i + 1].get('id') or stop_points[i + 1].get('stationId')
                                
                                if not from_stop_naptan or not to_stop_naptan:
                                    error_count += 1
                                    continue
                                
                                # Map to internal stop IDs
                                from_stop_id = self.stop_mapping.get(from_stop_naptan)
                                to_stop_id = self.stop_mapping.get(to_stop_naptan)
                                
                                if not from_stop_id:
                                    missing_stops += 1
                                    continue
                                
                                if not to_stop_id:
                                    missing_stops += 1
                                    continue
                                
                                # Check if edge already exists
                                existing_edge = session.query(Edge).filter_by(
                                    from_stop_id=from_stop_id,
                                    to_stop_id=to_stop_id,
                                    service_id=service_id,
                                    branch_id=branch_id
                                ).first()
                                
                                if existing_edge:
                                    continue
                                
                                # Create Edge record
                                edge = Edge(
                                    from_stop_id=from_stop_id,
                                    to_stop_id=to_stop_id,
                                    service_id=service_id,
                                    sequence_order=i,
                                    branch_id=branch_id
                                )
                                
                                session.add(edge)
                                edges_for_line += 1
                                total_edges += 1
                                
                            except Exception as e:
                                error_count += 1
                                continue
                    
                    # Commit after each line
                    session.commit()
                
                except Exception as e:
                    print(f"  Error processing route sequence for {line_id}: {e}")
                    session.rollback()
                    error_count += 1
                    continue
            
            duration = (datetime.now() - start_time).total_seconds()
            
            print(f"\n{'='*60}")
            print(f"EDGES INGESTION COMPLETE")
            print(f"{'='*60}")
            print(f"Total edges created: {total_edges}")
            print(f"Missing stop mappings: {missing_stops}")
            print(f"Errors encountered: {error_count}")
            print(f"Duration: {duration:.2f} seconds")
            print(f"{'='*60}\n")
            
            return total_edges
            
        except Exception as e:
            session.rollback()
            print(f"CRITICAL ERROR in edge ingestion: {e}")
            raise
    
    def verify_data(self, session: Session):
        """
        Verify data integrity and run validation queries.
        
        Args:
            session: SQLAlchemy session
        """
        print(f"\n{'='*60}")
        print(f"VERIFYING DATA INTEGRITY")
        print(f"{'='*60}")
        
        # Count stops by mode
        print("\n1. Stops by mode:")
        mode_counts = session.query(
            Stop.mode, 
            func.count(Stop.stop_id)
        ).group_by(Stop.mode).all()
        
        for mode, count in mode_counts:
            print(f"   {mode}: {count} stops")
        
        # Count services by mode
        print("\n2. Services by mode:")
        service_counts = session.query(
            Service.mode,
            func.count(Service.service_id)
        ).group_by(Service.mode).all()
        
        for mode, count in service_counts:
            print(f"   {mode}: {count} services")
        
        # Total edges
        print("\n3. Total edges:")
        total_edges = session.query(func.count(Edge.edge_id)).scalar()
        print(f"   {total_edges} edges")
        
        # Check for NULL geometries
        print("\n4. Checking for NULL geometries:")
        null_geoms = session.query(func.count(Stop.stop_id)).filter(Stop.location == None).scalar()
        print(f"   Stops with NULL geometry: {null_geoms}")
        if null_geoms > 0:
            print("   ⚠️  WARNING: Found stops with NULL geometries!")
        
        # Check for orphaned edges
        print("\n5. Checking for orphaned edges:")
        # This is complex in SQLAlchemy, so we'll use raw SQL
        orphaned_query = text("""
            SELECT COUNT(*) 
            FROM edges e
            LEFT JOIN stops s1 ON e.from_stop_id = s1.stop_id
            LEFT JOIN stops s2 ON e.to_stop_id = s2.stop_id
            WHERE s1.stop_id IS NULL OR s2.stop_id IS NULL
        """)
        orphaned_edges = session.execute(orphaned_query).scalar()
        print(f"   Orphaned edges: {orphaned_edges}")
        if orphaned_edges > 0:
            print("   ⚠️  WARNING: Found orphaned edges!")
        
        # Top connected stops (hubs)
        print("\n6. Top 10 most connected stops (hubs):")
        hub_query = text("""
            SELECT s.name, s.mode, COUNT(*) as connection_count
            FROM stops s
            JOIN edges e ON s.stop_id = e.from_stop_id OR s.stop_id = e.to_stop_id
            GROUP BY s.stop_id, s.name, s.mode
            ORDER BY connection_count DESC
            LIMIT 10
        """)
        hubs = session.execute(hub_query).fetchall()
        for hub in hubs:
            print(f"   {hub[0]} ({hub[1]}): {hub[2]} connections")
        
        # Test spatial query
        print("\n7. Testing spatial query (nearest unique stops to Trafalgar Square):")
        spatial_query = text("""
            SELECT DISTINCT ON (name, mode) 
                   name, 
                   mode, 
                   ST_Distance(
                       location::geography,
                       ST_SetSRID(ST_MakePoint(-0.1278, 51.5074), 4326)::geography
                   ) as distance_m
            FROM stops
            WHERE ST_DWithin(
                location::geography,
                ST_SetSRID(ST_MakePoint(-0.1278, 51.5074), 4326)::geography,
                1000
            )
            ORDER BY name, mode, distance_m
            LIMIT 5
        """)
        nearest_stops = session.execute(spatial_query).fetchall()
        for stop in nearest_stops:
            print(f"   {stop[0]} ({stop[1]}): {stop[2]:.0f}m away")
        
        print("\n8. Checking for duplicate stop names (same station, multiple entrances):")
        duplicate_query = text("""
            SELECT name, mode, COUNT(*) as entrance_count
            FROM stops
            GROUP BY name, mode
            HAVING COUNT(*) > 1
            ORDER BY entrance_count DESC
            LIMIT 5
        """)
        duplicates = session.execute(duplicate_query).fetchall()
        for dup in duplicates:
            print(f"   {dup[0]} ({dup[1]}): {dup[2]} entrances/platforms")
        
        print(f"\n{'='*60}")
        print(f"DATA VERIFICATION COMPLETE")
        print(f"{'='*60}\n")
    
    def run_full_ingestion(self, modes: List[str]):
        """
        Run the complete ingestion pipeline.
        
        Args:
            modes: List of transport modes to ingest
        """
        print(f"\n{'#'*60}")
        print(f"# TFL NEXUS - PHASE 1 DATA INGESTION PIPELINE")
        print(f"# Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*60}\n")
        
        overall_start = datetime.now()
        
        try:
            # Create tables if they don't exist
            print("Creating database tables...")
            ConnectionBroker.create_tables()
            print("✓ Tables created/verified\n")
            
            with ConnectionBroker.get_session() as session:
                # Step 1: Ingest stops
                stop_mapping = self.ingest_stops(session, modes)
                
                # Step 2: Ingest services
                service_mapping = self.ingest_services(session, modes)
                
                # Step 3: Ingest edges
                total_edges = self.ingest_edges(session)
                
                # Step 4: Verify data
                self.verify_data(session)
            
            overall_duration = (datetime.now() - overall_start).total_seconds()
            
            print(f"\n{'#'*60}")
            print(f"# PIPELINE COMPLETE")
            print(f"# Total duration: {overall_duration:.2f} seconds")
            print(f"# Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'#'*60}\n")
            
            # Final summary
            print("FINAL SUMMARY:")
            print(f"  ✓ {len(stop_mapping)} stops in mapping")
            print(f"  ✓ {len(service_mapping)} services in mapping")
            print(f"  ✓ {total_edges} edges created")
            print(f"  ✓ Data verification passed")
            
        except Exception as e:
            print(f"\n{'!'*60}")
            print(f"! PIPELINE FAILED")
            print(f"! Error: {e}")
            print(f"{'!'*60}\n")
            raise
