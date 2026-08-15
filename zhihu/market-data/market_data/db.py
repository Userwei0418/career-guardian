from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class StagingBase(DeclarativeBase):
    pass


class RawBase(DeclarativeBase):
    pass


class CoreBase(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    options: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **options)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)
