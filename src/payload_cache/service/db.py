from collections.abc import Iterator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

# Imported for its side effect: registering the tables on SQLModel.metadata.
from payload_cache.service import models  # noqa: F401


def create_db_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        # FastAPI runs sync endpoints in a thread pool, so a connection may be
        # used from a different thread than the one that opened it.
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args)


def init_db(engine: Engine) -> None:
    # Shortcut: create_all instead of migrations (e.g. Alembic). Fine for a
    # schema this small, but it cannot evolve an existing database.
    SQLModel.metadata.create_all(engine)


def session_scope(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
