from src.data.db_broker import ConnectionBroker

def test_broker_connection():

    connection = ConnectionBroker.connect()

    assert connection is not None
    assert connection.closed == 0