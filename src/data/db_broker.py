from src.config.config_main import db_config

import psycopg2

class ConnectionBroker:

    @staticmethod
    def connect():
        try:
            with psycopg2.connect(
                host=db_config.host,
                port=db_config.port,
                user=db_config.user,
                password=db_config.password,
                database=db_config.database
            ) as connection:
                #TODO: add logging
                return connection
        except (psycopg2.DatabaseError, Exception) as error:
            #TODO: add logging
            raise