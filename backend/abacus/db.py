from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import database_url

DATABASE_URL = database_url()
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def session():
    with Session() as db:
        yield db


def read_only_session():
    """Database-enforced, consistent local advisor snapshot; no write privileges in this transaction."""
    with Session() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        yield db
