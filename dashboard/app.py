"""
TfL Nexus - Real-time Delay Visualization Dashboard
A lightweight Flask app for monitoring current TfL delays
"""

from flask import Flask, render_template, jsonify
from flask_cors import CORS
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)
CORS(app)

# Database configuration
DB_USER = os.getenv('POSTGRES_USER', 'sa')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')
DB_HOST = os.getenv('POSTGRES_HOST', 'localhost')
DB_PORT = os.getenv('POSTGRES_PORT', '5433')
DB_NAME = os.getenv('POSTGRES_DB', 'tflnexus')

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')


@app.route('/api/delays/current')
def get_current_delays():
    """Get current live disruptions"""
    session = SessionLocal()
    try:
        query = text("""
            SELECT 
                s.line_name,
                s.mode,
                ld.severity_level,
                ld.category_description,
                ld.disruption_type,
                ld.summary,
                ld.additional_info,
                ld.is_full_suspension,
                ld.is_partial_suspension,
                ld.affected_section_start_naptan,
                ld.affected_section_end_naptan,
                ld.created,
                ld.last_update,
                ld.valid_from,
                ld.valid_to,
                ld.tfl_disruption_id,
                sl.estimated_delay_minutes,
                sl.confidence_score
            FROM live_disruptions ld
            JOIN services s ON ld.service_id = s.service_id
            LEFT JOIN severity_levels sl ON ld.severity_level = sl.severity_level AND s.mode = sl.mode_name
            WHERE ld.valid_to IS NULL OR ld.valid_to > NOW()
            ORDER BY ld.created DESC
            LIMIT 100
        """)
        
        result = session.execute(query)
        
        delays = []
        for row in result:
            severity_labels = [
                'Good Service', 'Minor Delays', 'Minor Delays', 'Moderate Delays',
                'Moderate Delays', 'Severe Delays', 'Severe Delays', 'Part Suspended',
                'Part Suspended', 'Suspended', 'Suspended'
            ]
            severity_text = severity_labels[min(row.severity_level, 10)] if row.severity_level is not None else 'Unknown'
            
            if row.is_full_suspension:
                severity_text = 'Suspended'
            elif row.is_partial_suspension:
                severity_text = 'Part Suspended'
            
            delay_minutes = row.estimated_delay_minutes if row.estimated_delay_minutes else row.severity_level * 2.5
            
            section_info = None
            if row.affected_section_start_naptan or row.affected_section_end_naptan:
                section_info = {
                    'start': row.affected_section_start_naptan,
                    'end': row.affected_section_end_naptan
                }
            
            delays.append({
                'line_name': row.line_name,
                'mode': row.mode,
                'delay_minutes': round(delay_minutes, 1),
                'severity': severity_text,
                'severity_level': row.severity_level,
                'description': row.summary or row.category_description,
                'additional_info': row.additional_info,
                'category': row.category_description,
                'disruption_type': row.disruption_type,
                'is_full_suspension': row.is_full_suspension,
                'is_partial_suspension': row.is_partial_suspension,
                'affected_section': section_info,
                'timestamp': row.created.isoformat() if row.created else None,
                'last_update': row.last_update.isoformat() if row.last_update else None,
                'data_source': 'TfL Disruption API',
                'confidence_level': 'high' if row.confidence_score and row.confidence_score > 0.75 else 'medium',
                'confidence_score': round(row.confidence_score, 2) if row.confidence_score else 0.3,
                'tfl_disruption_id': row.tfl_disruption_id
            })
        
        return jsonify({
            'success': True,
            'count': len(delays),
            'delays': delays,
            'last_updated': datetime.utcnow().isoformat()
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
    finally:
        session.close()


@app.route('/api/delays/summary')
def get_delay_summary():
    """Get summary statistics of active disruptions"""
    session = SessionLocal()
    try:
        query = text("""
            SELECT 
                s.line_name,
                s.mode,
                COUNT(*) as delay_count,
                AVG(COALESCE(sl.estimated_delay_minutes, ld.severity_level * 2.5)) as avg_delay,
                MAX(COALESCE(sl.estimated_delay_minutes, ld.severity_level * 2.5)) as max_delay,
                MAX(ld.last_update) as latest_update,
                AVG(sl.confidence_score) as avg_confidence
            FROM live_disruptions ld
            JOIN services s ON ld.service_id = s.service_id
            LEFT JOIN severity_levels sl ON ld.severity_level = sl.severity_level AND s.mode = sl.mode_name
            WHERE ld.valid_to IS NULL OR ld.valid_to > NOW()
            GROUP BY s.line_name, s.mode
            ORDER BY delay_count DESC
        """)
        
        result = session.execute(query)
        
        summary = []
        for row in result:
            summary.append({
                'line_name': row.line_name,
                'mode': row.mode,
                'delay_count': row.delay_count,
                'avg_delay': round(row.avg_delay, 1) if row.avg_delay else 0,
                'max_delay': round(row.max_delay, 1) if row.max_delay else 0,
                'latest_update': row.latest_update.isoformat() if row.latest_update else None,
                'confidence': round(row.avg_confidence, 2) if row.avg_confidence else 0.3
            })
        
        return jsonify({
            'success': True,
            'summary': summary,
            'last_updated': datetime.utcnow().isoformat()
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
    finally:
        session.close()


@app.route('/api/delays/severity-breakdown')
def get_severity_breakdown():
    """Get breakdown of active disruptions by severity"""
    session = SessionLocal()
    try:
        query = text("""
            SELECT 
                CASE
                    WHEN ld.is_full_suspension THEN 'Suspended'
                    WHEN ld.is_partial_suspension THEN 'Part Suspended'
                    WHEN ld.severity_level >= 8 THEN 'Part Suspended'
                    WHEN ld.severity_level >= 5 THEN 'Severe Delays'
                    WHEN ld.severity_level >= 3 THEN 'Moderate Delays'
                    WHEN ld.severity_level >= 1 THEN 'Minor Delays'
                    ELSE 'Good Service'
                END as severity,
                COUNT(*) as count,
                AVG(COALESCE(sl.estimated_delay_minutes, ld.severity_level * 2.5)) as avg_delay,
                AVG(sl.confidence_score) as avg_confidence
            FROM live_disruptions ld
            JOIN services s ON ld.service_id = s.service_id
            LEFT JOIN severity_levels sl ON ld.severity_level = sl.severity_level AND s.mode = sl.mode_name
            WHERE ld.valid_to IS NULL OR ld.valid_to > NOW()
            GROUP BY 
                ld.is_full_suspension,
                ld.is_partial_suspension,
                ld.severity_level
            ORDER BY count DESC
        """)
        
        result = session.execute(query)
        
        breakdown = []
        for row in result:
            breakdown.append({
                'severity': row.severity,
                'count': row.count,
                'avg_delay': round(row.avg_delay, 1) if row.avg_delay else 0,
                'confidence': round(row.avg_confidence, 2) if row.avg_confidence else 0.3
            })
        
        return jsonify({
            'success': True,
            'breakdown': breakdown
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
    finally:
        session.close()


@app.route('/api/phase2b/stats')
def get_phase2b_stats():
    """Get Phase 2B-specific statistics"""
    session = SessionLocal()
    try:
        query = text("""
            SELECT 
                COUNT(*) FILTER (WHERE is_full_suspension) as full_suspensions,
                COUNT(*) FILTER (WHERE is_partial_suspension) as partial_suspensions,
                COUNT(*) FILTER (WHERE affected_section_start_naptan IS NOT NULL) as with_section_info,
                AVG(sl.confidence_score) as avg_confidence,
                COUNT(DISTINCT sl.severity_level) as severity_levels_in_use,
                (SELECT COUNT(*) FROM severity_levels WHERE confidence_score > 0.75) as high_confidence_levels,
                (SELECT COUNT(*) FROM realtime_delay_samples) as total_samples
            FROM live_disruptions ld
            JOIN services s ON ld.service_id = s.service_id
            LEFT JOIN severity_levels sl ON ld.severity_level = sl.severity_level AND s.mode = sl.mode_name
            WHERE ld.valid_to IS NULL OR ld.valid_to > NOW()
        """)
        
        result = session.execute(query).fetchone()
        
        return jsonify({
            'success': True,
            'stats': {
                'full_suspensions': result.full_suspensions or 0,
                'partial_suspensions': result.partial_suspensions or 0,
                'with_section_info': result.with_section_info or 0,
                'avg_confidence': round(result.avg_confidence, 2) if result.avg_confidence else 0.3,
                'severity_levels_in_use': result.severity_levels_in_use or 0,
                'high_confidence_levels': result.high_confidence_levels or 0,
                'total_delay_samples': result.total_samples or 0
            }
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
    finally:
        session.close()


@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    session = SessionLocal()
    try:
        result = session.execute(text("SELECT COUNT(*) FROM services"))
        service_count = result.scalar()
        
        result = session.execute(text("SELECT COUNT(*) FROM live_disruptions WHERE valid_to IS NULL OR valid_to > NOW()"))
        active_disruptions = result.scalar()
        
        result = session.execute(text("SELECT COUNT(*) FROM live_disruptions"))
        total_disruptions = result.scalar()
        
        result = session.execute(text("SELECT COUNT(*) FROM severity_levels"))
        severity_levels = result.scalar()
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'phase': '2B',
            'services_count': service_count,
            'active_disruptions': active_disruptions,
            'total_disruptions': total_disruptions,
            'severity_levels': severity_levels
        })
    
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500
    
    finally:
        session.close()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
