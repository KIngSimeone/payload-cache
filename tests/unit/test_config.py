from datetime import timedelta

import pytest

from payload_cache.service.config import Settings


def test_ttl_defaults_to_one_day() -> None:
    assert Settings().ttl == timedelta(days=1)


def test_ttl_is_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CACHE_TTL_SECONDS", "90")

    assert Settings().ttl == timedelta(seconds=90)


def test_ttl_can_be_disabled_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CACHE_TTL_SECONDS", "none")

    assert Settings().ttl is None
