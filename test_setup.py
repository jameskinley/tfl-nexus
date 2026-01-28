"""
Test script to verify the ingestion pipeline setup.
"""

from src.data.db_broker import ConnectionBroker
from src.data.models import Stop, Service, Edge
from sqlalchemy import text

def test_database_connection():
    """Test that we can connect to the database."""
    print("Testing database connection...")
    try:
        with ConnectionBroker.get_session() as session:
            # Try a simple query
            result = session.execute(text("SELECT version();")).fetchone()
            print(f"✓ Connected to PostgreSQL: {result[0][:50]}...")
        print("✓ Database connection successful\n")
        return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}\n")
        return False

def test_postgis_extension():
    """Test that PostGIS extension is available."""
    print("Testing PostGIS extension...")
    try:
        with ConnectionBroker.get_session() as session:
            result = session.execute(text("SELECT PostGIS_version();")).fetchone()
            print(f"✓ PostGIS version: {result[0]}")
        print("✓ PostGIS extension available\n")
        return True
    except Exception as e:
        print(f"✗ PostGIS extension check failed: {e}\n")
        return False

def test_create_tables():
    """Test that we can create the database tables."""
    print("Testing table creation...")
    try:
        ConnectionBroker.create_tables()
        print("✓ Tables created successfully\n")
        return True
    except Exception as e:
        print(f"✗ Table creation failed: {e}\n")
        return False

def test_table_structure():
    """Verify table structure."""
    print("Verifying table structure...")
    try:
        with ConnectionBroker.get_session() as session:
            # Check stops table
            result = session.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'stops'
                ORDER BY ordinal_position;
            """)).fetchall()
            print(f"✓ Stops table has {len(result)} columns")
            
            # Check services table
            result = session.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'services'
                ORDER BY ordinal_position;
            """)).fetchall()
            print(f"✓ Services table has {len(result)} columns")
            
            # Check edges table
            result = session.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'edges'
                ORDER BY ordinal_position;
            """)).fetchall()
            print(f"✓ Edges table has {len(result)} columns")
            
            # Check for spatial index
            result = session.execute(text("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'stops' AND indexname LIKE '%location%';
            """)).fetchall()
            if result:
                print(f"✓ Spatial index found: {result[0][0]}")
            else:
                print("⚠️  Warning: No spatial index found on stops.location")
        
        print("✓ Table structure verified\n")
        return True
    except Exception as e:
        print(f"✗ Table structure verification failed: {e}\n")
        return False

def main():
    """Run all tests."""
    print("="*60)
    print("PHASE 1 - DATABASE SETUP VERIFICATION")
    print("="*60 + "\n")
    
    tests = [
        ("Database Connection", test_database_connection),
        ("PostGIS Extension", test_postgis_extension),
        ("Table Creation", test_create_tables),
        ("Table Structure", test_table_structure),
    ]
    
    results = []
    for name, test_func in tests:
        results.append(test_func())
    
    print("="*60)
    print("TEST RESULTS")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("✓ All tests passed! Ready to run ingestion pipeline.")
    else:
        print("✗ Some tests failed. Please fix issues before running ingestion.")
    print("="*60)

if __name__ == "__main__":
    main()
