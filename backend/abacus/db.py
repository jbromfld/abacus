from threading import Lock

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .advisor_access import (
    ADVISOR_UNAVAILABLE,
    AdvisorAccessError,
    verify_advisor_access,
)
from .config import advisor_database_url, database_url

DATABASE_URL = database_url()
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def session():
    with Session() as db:
        yield db


_advisor_lock = Lock()
_advisor_engine = None
_advisor_factory = None


def dispose_advisor_engine():
    global _advisor_engine, _advisor_factory
    with _advisor_lock:
        if _advisor_engine is not None:
            _advisor_engine.dispose()
        _advisor_engine, _advisor_factory = None, None


def advisor_session_factory():
    global _advisor_engine, _advisor_factory
    url = advisor_database_url()
    with _advisor_lock:
        if _advisor_engine is None or _advisor_engine.url != url:
            if _advisor_engine is not None:
                _advisor_engine.dispose()
            _advisor_engine = create_engine(
                url,
                pool_pre_ping=True,
                hide_parameters=True,
                connect_args={"connect_timeout": 5},
            )
            _advisor_factory = sessionmaker(_advisor_engine, expire_on_commit=False)
        return _advisor_factory, url.username


def read_only_session():
    """Fail closed: a separate restricted login plus an enforced read-only snapshot."""
    try:
        factory, role = advisor_session_factory()
        with factory() as db:
            db.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            verify_advisor_access(db, role)
            yield db
    except (ValueError, AdvisorAccessError, SQLAlchemyError):
        raise HTTPException(503, ADVISOR_UNAVAILABLE) from None
