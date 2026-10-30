"""DB engine/session. SQLite now; swap DATABASE_URL to move to Postgres."""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
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
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}
    engine = create_engine(url, connect_args=connect_args, future=True)
    if is_sqlite:
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001, ANN202
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_all(engine: Engine) -> None:
    # Import models so every table is registered on Base.metadata.
    # One schema mechanism only: create_all. Schema changes = drop + recreate
    # + reseed (python -m app.seed --reset); no ad-hoc additive migrations.
    from app.infra.db import models as _models  # noqa: F401

    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI session dependency (wired in api/deps.py)."""
    factory = make_session_factory(make_engine())
    session = factory()
    try:
        yield session
    finally:
        session.close()
