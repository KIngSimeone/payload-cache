from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from payload_cache.service.db import create_db_engine, init_db


class SpyTransformer:
    """Upper-cases like the real transformer, but records every call."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, value: str) -> str:
        self.calls.append(value)
        return value.upper()


@pytest.fixture
def transformer() -> SpyTransformer:
    return SpyTransformer()


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    # A file-backed database behaves like production SQLite (real connections,
    # real constraints) while staying isolated per test.
    engine = create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


class FakeClock:
    """Controllable time source, so TTL tests advance time instead of sleeping."""

    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
