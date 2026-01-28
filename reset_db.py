"""
Drop all tables and recreate them fresh.
Use this to reset the database.
"""

from src.data.db_broker import ConnectionBroker, Base
from sqlalchemy import text

def drop_all_tables():
    """Drop all tables in the database."""
    print("Dropping all tables...")
    
    with ConnectionBroker.get_session() as session:
        # Drop tables in correct order (respecting foreign keys)
        tables = [
            'saved_routes',
            'live_disruptions',
            'fragility_scores',
            'transfer_statistics',
            'historical_delays',
            'edges',
            'services',
            'stops',
            'users'
        ]
        
        for table in tables:
            try:
                session.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
                print(f"  Dropped table: {table}")
            except Exception as e:
                print(f"  Could not drop {table}: {e}")
        
        session.commit()
    
    print("✓ All tables dropped\n")

def create_all_tables():
    """Create all tables fresh."""
    print("Creating all tables...")
    ConnectionBroker.create_tables()
    print("✓ All tables created\n")

def main():
    """Reset the database."""
    print("="*60)
    print("DATABASE RESET")
    print("="*60 + "\n")
    
    response = input("This will DROP all tables and data. Continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Cancelled.")
        return
    
    drop_all_tables()
    create_all_tables()
    
    print("="*60)
    print("Database reset complete!")
    print("="*60)

if __name__ == "__main__":
    main()
