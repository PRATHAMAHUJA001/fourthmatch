"""Legacy shim — canonical DB setup is app.infra.db.session. Kept for seed imports."""
from app.infra.db.session import (  # noqa: F401
    DEFAULT_DB_PATH,
    REPO_ROOT,
    Base,
    create_all,
    database_url,
    get_session,
    make_engine,
    make_session_factory,
)
