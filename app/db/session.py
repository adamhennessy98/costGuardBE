from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_db_url = settings.effective_database_url

engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}

if _db_url.startswith("sqlite"):
    # SQLite does not support connection pooling or multi-threaded access
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL (Supabase) connection-pool settings
    engine_kwargs.update(
        {
            "pool_size": 5,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_recycle": 1800,  # recycle connections every 30 min
        }
    )

engine = create_engine(_db_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session per request."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
