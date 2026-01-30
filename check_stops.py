from src.data.db_broker import ConnectionBroker
from src.data.models import Stop, Service
from sqlalchemy import func

with ConnectionBroker.get_session() as session:
    stop_count = session.query(func.count(Stop.stop_id)).scalar()
    service_count = session.query(func.count(Service.service_id)).scalar()
    
    print(f"Total stops in database: {stop_count}")
    print(f"Total services in database: {service_count}")
    
    if stop_count > 0:
        sample_stops = session.query(Stop).limit(5).all()
        print("\nSample stops:")
        for stop in sample_stops:
            print(f"  - {stop.tfl_stop_id}: {stop.name}")
