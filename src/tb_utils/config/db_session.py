"""Database Session Maker.

The engine and session factory are lazily initialized on first use so that
importing this library does not require an active database connection.
"""

import logging
from typing import Generator, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from .database import db_settings

logger = logging.getLogger(__name__)

# Module-level singletons — populated on first access via get_engine() / get_session()
_engine: Optional[Engine] = None
_SessionLocal: Optional[scoped_session] = None


def get_engine() -> Engine:
    """Return (and lazily create) the shared SQLAlchemy engine.

    The engine is created once and reused for all subsequent calls.

    Returns:
        A configured SQLAlchemy Engine

    Raises:
        RuntimeError: If the engine could not be created (e.g. bad DB URL)
    """
    global _engine
    if _engine is None:
        try:
            _engine = create_engine(
                db_settings.get_database_url,
                pool_pre_ping=True,  # Test connections before using them
                pool_size=10,  # Max connections to keep open
                max_overflow=20,  # Max connections beyond pool_size
                echo=False,  # Set True to log all SQL queries
            )
            logger.debug("SQLAlchemy engine created: %s", db_settings.DB_HOST)
        except Exception as exc:
            logger.error("Failed to create SQLAlchemy engine: %s", exc, exc_info=True)
            raise RuntimeError(f"Could not create database engine: {exc}") from exc
    return _engine


def get_session_factory() -> scoped_session:
    """Return (and lazily create) the shared scoped session factory.

    Returns:
        A SQLAlchemy scoped_session factory
    """
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = scoped_session(
            sessionmaker(autocommit=False, autoflush=False, bind=engine)
        )
    return _SessionLocal


# Convenience alias — retains backward-compatible name for consumers already
# using `from tb_utils.config.db_session import SessionLocal`.
# Accessing this attribute triggers lazy initialization.
class _LazySessionLocal:
    """Proxy that initialises the session factory on first attribute access."""

    def __getattr__(self, name):
        return getattr(get_session_factory(), name)

    def __call__(self, *args, **kwargs):
        return get_session_factory()(*args, **kwargs)


SessionLocal = _LazySessionLocal()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for injecting a database session.

    Usage::

        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...

    Yields:
        An active SQLAlchemy Session
    """
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
