from src.data.db_broker import ConnectionBroker
from sqlalchemy import text

with ConnectionBroker.get_session() as session:
    result = session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'live_disruptions' "
        "ORDER BY ordinal_position"
    ))
    columns = [r[0] for r in result.fetchall()]
    print("live_disruptions columns:")
    for col in columns:
        print(f"  - {col}")
    
    result = session.execute(text("SELECT COUNT(*) FROM severity_levels"))
    count = result.scalar()
    print(f"\nSeverity levels loaded: {count}")
    
    result = session.execute(text("SELECT COUNT(*) FROM disruption_categories"))
    count = result.scalar()
    print(f"Disruption categories loaded: {count}")
    
    result = session.execute(text("SELECT COUNT(*) FROM live_disruptions"))
    count = result.scalar()
    print(f"Live disruptions count: {count}")
