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
        # Get active disruptions (not yet resolved)
        query = text("""
            SELECT 
                s.line_name,
                s.mode,
                ld.severity,
                ld.description,
                ld.category,
                ld.start_time,
                ld.expected_end_time,
                ld.tfl_disruption_id,
                ld.created_at,
                ld.updated_at
            FROM live_disruptions ld
            JOIN services s ON ld.service_id = s.service_id
            WHERE ld.actual_end_time IS NULL
            ORDER BY ld.start_time DESC
            LIMIT 100
        """)
        
        result = session.execute(query)
        
        delays = []
        for row in result:
            # Calculate approximate delay in minutes from severity
            severity_map = {
                'Suspended': 60,
                'Part Suspended': 45,
                'Severe Delays': 30,
                'Reduced Service': 20,
                'Part Closure': 25,
                'Minor Delays': 10,
                'Good Service': 0
            }
            delay_minutes = severity_map.get(row.severity, 15)
            
            delays.append({
                'line_name': row.line_name,
                'mode': row.mode,
                'delay_minutes': delay_minutes,
                'severity': row.severity,
                'description': row.description,
                'category': row.category,
                'timestamp': row.start_time.isoformat() if row.start_time else None,
                'data_source': 'TfL Live',
                'confidence_level': 'high',
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
        # Get summary by line for active disruptions
        query = text("""
            SELECT 
                s.line_name,
                s.mode,
                COUNT(*) as delay_count,
                ld.severity,
                MAX(ld.start_time) as latest_update
            FROM live_disruptions ld
            JOIN services s ON ld.service_id = s.service_id
            WHERE ld.actual_end_time IS NULL
            GROUP BY s.line_name, s.mode, ld.severity
            ORDER BY delay_count DESC
        """)
        
        result = session.execute(query)
        
        # Map severity to approximate delay minutes
        severity_map = {
            'Suspended': 60,
            'Part Suspended': 45,
            'Severe Delays': 30,
            'Reduced Service': 20,
            'Part Closure': 25,
            'Minor Delays': 10,
            'Good Service': 0
        }
        
        summary = []
        for row in result:
            avg_delay = severity_map.get(row.severity, 15)
            summary.append({
                'line_name': row.line_name,
                'mode': row.mode,
                'delay_count': row.delay_count,
                'avg_delay': avg_delay,
                'max_delay': avg_delay,
                'latest_update': row.latest_update.isoformat() if row.latest_update else None
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
                severity,
                COUNT(*) as count
            FROM live_disruptions
            WHERE actual_end_time IS NULL
            GROUP BY severity
            ORDER BY count DESC
        """)
        
        result = session.execute(query)
        
        # Map severity to approximate delay minutes
        severity_map = {
            'Suspended': 60,
            'Part Suspended': 45,
            'Severe Delays': 30,
            'Reduced Service': 20,
            'Part Closure': 25,
            'Minor Delays': 10,
            'Good Service': 0
        }
        
        breakdown = []
        for row in result:
            avg_delay = severity_map.get(row.severity, 15)
            breakdown.append({
                'severity': row.severity,
                'count': row.count,
                'avg_delay': avg_delay
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


@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    session = SessionLocal()
    try:
        # Try to query the database
        result = session.execute(text("SELECT COUNT(*) FROM services"))
        service_count = result.scalar()
        
        result = session.execute(text("SELECT COUNT(*) FROM live_disruptions WHERE actual_end_time IS NULL"))
        active_disruptions = result.scalar()
        
        result = session.execute(text("SELECT COUNT(*) FROM live_disruptions"))
        total_disruptions = result.scalar()
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'services_count': service_count,
            'active_disruptions': active_disruptions,
            'total_disruptions': total_disruptions
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
