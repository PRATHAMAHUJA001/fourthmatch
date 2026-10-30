"""DB engine/session. SQLite now; swap DATABASE_URL to move to Postgres."""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "fourthmatch.db"


class Base(DeclarativeBase):
    pass


def database_url(db_path: Path | None = None) -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    path = db_path or DEFAULT_DB_PATH
    return f"sqlite:///{path}"


def make_engine(db_path: Path | None = None) -> Engine:
    url = database_url(db_path)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_all(engine: Engine) -> None:
    # Import models so every table is registered on Base.metadata.
    from app.infra.db import models as _models  # noqa: F401

    Base.metadata.create_all(engine)
    _migrate_tracks_sam_run_id(engine)
    _migrate_model_calls_cache_hit(engine)


def _migrate_tracks_sam_run_id(engine: Engine) -> None:
    """Additive SQLite migration: legacy tracks tables predate sam_runs.

    Tracks are never seeded (SAM-only), so the legacy table is empty and a
    nullable ADD COLUMN is safe. Fresh DBs already have the column (no-op).
    """
    inspector = inspect(engine)
    if "tracks" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("tracks")}
    if "sam_run_id" in columns:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tracks ADD COLUMN sam_run_id INTEGER REFERENCES sam_runs(id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tracks_sam_run_id ON tracks (sam_run_id)"))


def _migrate_model_calls_cache_hit(engine: Engine) -> None:
    """Additive SQLite migration: legacy model_calls tables predate cache_hit."""
    inspector = inspect(engine)
    if "model_calls" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("model_calls")}
    if "cache_hit" in columns:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE model_calls ADD COLUMN cache_hit BOOLEAN NOT NULL DEFAULT 0"))


def get_session() -> Iterator[Session]:
    """FastAPI session dependency (wired in api/deps.py)."""
    factory = make_session_factory(make_engine())
    session = factory()
    try:
        yield session
    finally:
        session.close()
