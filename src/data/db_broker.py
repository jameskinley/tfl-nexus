from src.config.config_main import db_config

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from contextlib import contextmanager

# Base class for SQLAlchemy models
Base = declarative_base()

class ConnectionBroker:

    _engine = None
    _SessionLocal = None

    @staticmethod
    def connect():
        """Legacy psycopg2 connection for backward compatibility."""
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

    @staticmethod
    def get_engine():
        """Get or create SQLAlchemy engine."""
        if ConnectionBroker._engine is None:
            connection_string = (
                f"postgresql+psycopg2://{db_config.user}:{db_config.password}"
                f"@{db_config.host}:{db_config.port}/{db_config.database}"
            )
            ConnectionBroker._engine = create_engine(
                connection_string,
                pool_pre_ping=True,  # Verify connections before using
                echo=False  # Set to True for SQL debug logging
            )
        return ConnectionBroker._engine

    @staticmethod
    def get_session_factory():
        """Get or create SQLAlchemy session factory."""
        if ConnectionBroker._SessionLocal is None:
            engine = ConnectionBroker.get_engine()
            ConnectionBroker._SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=engine
            )
        return ConnectionBroker._SessionLocal

    @staticmethod
    @contextmanager
    def get_session():
        """
        Get a SQLAlchemy session with automatic cleanup.
        
        Usage:
            with ConnectionBroker.get_session() as session:
                session.query(Model).all()
        """
        SessionLocal = ConnectionBroker.get_session_factory()
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def create_tables():
        """Create all tables defined in models."""
        engine = ConnectionBroker.get_engine()
        Base.metadata.create_all(bind=engine)