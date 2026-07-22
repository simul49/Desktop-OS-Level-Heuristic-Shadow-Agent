"""
Heuristic Shadow Agent - Database Manager
Handles MySQL/SQLite connection, session management, and schema initialization.
"""

import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from config import Config
from src.db.models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Singleton database manager with MySQL primary and SQLite fallback."""

    _instance = None
    _engine = None
    _SessionLocal = None
    _using_fallback = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self) -> bool:
        """Initialize database connection. Tries MySQL first, falls back to SQLite."""
        # Try MySQL
        try:
            mysql_url = Config.get_db_url()
            logger.info(f"Connecting to MySQL: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
            self._engine = create_engine(
                mysql_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False,
            )
            # Test connection
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            self._using_fallback = False
            logger.info("MySQL connection established successfully.")
        except (OperationalError, Exception) as e:
            logger.warning(f"MySQL unavailable ({e}), falling back to SQLite.")
            sqlite_url = f"sqlite:///{Config.SQLITE_FALLBACK_PATH}"
            self._engine = create_engine(sqlite_url, echo=False)
            self._using_fallback = True
            logger.info(f"SQLite fallback activated: {Config.SQLITE_FALLBACK_PATH}")

        self._SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self._engine
        )
        self._create_tables()
        return True

    def _create_tables(self) -> None:
        """Create all tables if they don't exist."""
        try:
            Base.metadata.create_all(bind=self._engine)
            # MySQL-specific: create the database if it doesn't exist (attempted via URL)
            logger.info("Database tables verified/created successfully.")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise

    @property
    def is_using_fallback(self) -> bool:
        return self._using_fallback

    @contextmanager
    def get_session(self):
        """Context manager for database sessions."""
        if self._SessionLocal is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_raw_session(self) -> Session:
        """Get a raw session (caller must close)."""
        if self._SessionLocal is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._SessionLocal()

    def health_check(self) -> bool:
        """Check if database connection is alive."""
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def get_engine(self):
        return self._engine


# Global instance
db_manager = DatabaseManager()
