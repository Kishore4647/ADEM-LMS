from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()


def build_database_url(raw_url: str):
    """Normalize Supabase pooler URLs for psycopg/SQLAlchemy.

    Supabase's copied pooler URI can include ``pgbouncer=true``. That flag is
    understood by some Supabase clients but not psycopg, so it must not be
    passed to the database driver.
    """
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    query = {key: value for key, value in url.query.items() if key != "pgbouncer"}
    return url.set(query=query)


database_url = build_database_url(settings.database_url)
connect_args = (
    {"prepare_threshold": None, "connect_timeout": 10}
    if database_url.drivername.startswith("postgresql")
    else {}
)
if database_url.drivername.startswith("postgresql") and database_url.host not in {
    "localhost",
    "127.0.0.1",
    "::1",
}:
    connect_args["sslmode"] = "require"
engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
