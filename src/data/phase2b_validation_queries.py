"""
Phase 2B Validation Queries

Run these queries after the monitor has been running for 24-48 hours
to validate data quality and Phase 2B implementation.
"""

VALIDATION_QUERIES = {
    "disruption_category_distribution": """
        SELECT 
            category,
            disruption_type,
            COUNT(*) as count,
            COUNT(CASE WHEN is_full_suspension THEN 1 END) as full_suspensions,
            COUNT(CASE WHEN is_partial_suspension THEN 1 END) as partial_suspensions
        FROM live_disruptions
        WHERE created_at > NOW() - INTERVAL '24 hours'
        GROUP BY category, disruption_type
        ORDER BY count DESC;
    """,
    
    "json_field_population": """
        SELECT 
            COUNT(*) as total_disruptions,
            COUNT(affected_routes_json) as has_routes_json,
            COUNT(affected_stops_json) as has_stops_json,
            ROUND(100.0 * COUNT(affected_routes_json) / COUNT(*), 2) as routes_pct,
            ROUND(100.0 * COUNT(affected_stops_json) / COUNT(*), 2) as stops_pct
        FROM live_disruptions
        WHERE actual_end_time IS NULL;
    """,
    
    "severity_levels_loaded": """
        SELECT 
            mode_name,
            severity_level,
            description,
            estimated_delay_minutes,
            is_suspension,
            confidence_score,
            sample_count
        FROM severity_levels
        ORDER BY mode_name, severity_level;
    """,
    
    "partial_suspension_details": """
        SELECT 
            s.line_name,
            ld.disruption_type,
            ld.is_partial_suspension,
            ld.affected_section_start_naptan,
            ld.affected_section_end_naptan,
            ld.closure_text,
            ld.description
        FROM live_disruptions ld
        JOIN services s ON ld.service_id = s.service_id
        WHERE is_partial_suspension = true
          AND actual_end_time IS NULL
        ORDER BY ld.created_at DESC;
    """,
    
    "full_suspension_status": """
        SELECT 
            s.line_name,
            s.mode,
            ld.category,
            ld.is_full_suspension,
            ld.start_time,
            ld.valid_to,
            ld.description
        FROM live_disruptions ld
        JOIN services s ON ld.service_id = s.service_id
        WHERE is_full_suspension = true
          AND actual_end_time IS NULL
        ORDER BY start_time DESC;
    """,
    
    "delay_samples_collected": """
        SELECT 
            s.line_name,
            st.name as stop_name,
            COUNT(*) as sample_count,
            AVG(measured_delay_seconds) as avg_delay_seconds,
            MIN(measured_delay_seconds) as min_delay,
            MAX(measured_delay_seconds) as max_delay
        FROM realtime_delay_samples rd
        JOIN services s ON rd.service_id = s.service_id
        JOIN stops st ON rd.stop_id = st.stop_id
        WHERE timestamp > NOW() - INTERVAL '6 hours'
        GROUP BY s.line_name, st.name
        ORDER BY sample_count DESC
        LIMIT 20;
    """,
    
    "severity_learning_progress": """
        SELECT 
            mode_name,
            severity_level,
            description,
            estimated_delay_minutes,
            confidence_score,
            sample_count,
            last_updated
        FROM severity_levels
        WHERE is_suspension = false
        ORDER BY mode_name, severity_level;
    """,
    
    "active_disruptions_summary": """
        SELECT 
            s.line_name,
            s.mode,
            ld.category,
            ld.disruption_type,
            ld.is_full_suspension,
            ld.is_partial_suspension,
            EXTRACT(EPOCH FROM (NOW() - ld.start_time))/3600 as hours_active,
            ld.description
        FROM live_disruptions ld
        JOIN services s ON ld.service_id = s.service_id
        WHERE actual_end_time IS NULL
        ORDER BY ld.start_time DESC;
    """,
    
    "disruption_resolution_patterns": """
        SELECT 
            DATE_TRUNC('day', start_time) as day,
            COUNT(*) as total_disruptions,
            COUNT(CASE WHEN actual_end_time IS NOT NULL THEN 1 END) as resolved,
            COUNT(CASE WHEN is_full_suspension THEN 1 END) as full_suspensions,
            COUNT(CASE WHEN is_partial_suspension THEN 1 END) as partial_suspensions,
            AVG(EXTRACT(EPOCH FROM (COALESCE(actual_end_time, NOW()) - start_time))/3600) as avg_duration_hours
        FROM live_disruptions
        WHERE start_time > NOW() - INTERVAL '7 days'
        GROUP BY DATE_TRUNC('day', start_time)
        ORDER BY day DESC;
    """,
    
    "affected_routes_structure_check": """
        SELECT 
            disruption_id,
            tfl_disruption_id,
            jsonb_array_length(affected_routes_json::jsonb) as route_count,
            affected_routes_json::jsonb -> 0 -> 'lineId' as first_line_id,
            affected_routes_json::jsonb -> 0 -> 'direction' as first_direction,
            jsonb_array_length(
                (affected_routes_json::jsonb -> 0 -> 'routeSectionNaptanEntrySequence')::jsonb
            ) as sequence_length
        FROM live_disruptions
        WHERE affected_routes_json IS NOT NULL
          AND actual_end_time IS NULL
        LIMIT 10;
    """,
}


def print_query(name: str):
    print(f"\n{'='*80}")
    print(f"Query: {name}")
    print(f"{'='*80}")
    print(VALIDATION_QUERIES[name])
    print()


def print_all_queries():
    for name in VALIDATION_QUERIES:
        print_query(name)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        query_name = sys.argv[1]
        if query_name in VALIDATION_QUERIES:
            print_query(query_name)
        else:
            print(f"Unknown query: {query_name}")
            print(f"Available queries: {', '.join(VALIDATION_QUERIES.keys())}")
    else:
        print_all_queries()
