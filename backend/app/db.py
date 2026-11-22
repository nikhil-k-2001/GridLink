from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def engine_kwargs(url: str) -> dict:
    """psycopg 3 prepares repeated statements server-side, which breaks behind transaction poolers
    (Supabase/Neon pooled endpoints). Disable it for Postgres; it is a minor optimisation here."""
    return {"connect_args": {"prepare_threshold": None}} if url.startswith("postgresql+psycopg") else {}


def init_engine(url: str | None = None, **kwargs):
    global _engine, _SessionLocal
    url = url or get_settings().database_url
    _engine = create_engine(url, pool_pre_ping=True, future=True, **engine_kwargs(url), **kwargs)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


def session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()
