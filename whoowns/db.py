"""Database engine and session factory.

DATABASE_URL env var overrides the default local SQLite file, so the same
code runs against Supabase/Neon Postgres unchanged (spec §7).
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "app.db"

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create all tables if they don't exist."""
    from whoowns import models

    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    models.Base.metadata.create_all(engine)
