from datetime import timedelta

from sqlmodel import Session

from payload_cache.service.cache import PayloadService
from tests.conftest import FakeClock, SpyTransformer

TTL = timedelta(hours=1)


class VersionedTransformer(SpyTransformer):
    """Simulates an external service whose answers change over time."""

    def __init__(self) -> None:
        super().__init__()
        self.version = 1

    def __call__(self, value: str) -> str:
        super().__call__(value)
        return f"{value.upper()}v{self.version}"


def test_cached_strings_are_reused_within_ttl(
    session: Session, transformer: SpyTransformer, clock: FakeClock
) -> None:
    service = PayloadService(session, transformer, ttl=TTL, clock=clock)
    service.create_payload(["a"], ["b"])
    transformer.calls.clear()
    clock.advance(TTL - timedelta(seconds=1))

    service.create_payload(["b"], ["c"])

    assert transformer.calls == ["c"]


def test_expired_strings_are_transformed_again(
    session: Session, transformer: SpyTransformer, clock: FakeClock
) -> None:
    service = PayloadService(session, transformer, ttl=TTL, clock=clock)
    service.create_payload(["a"], ["b"])
    clock.advance(TTL / 2)
    service.create_payload(["c"], ["d"])
    transformer.calls.clear()
    clock.advance(TTL / 2 + timedelta(seconds=1))

    service.create_payload(["a", "c"], ["b", "d"])

    # Only the strings cached in the first request have expired.
    assert sorted(transformer.calls) == ["a", "b"]


def test_expired_payload_keeps_its_identifier_with_refreshed_output(
    session: Session, clock: FakeClock
) -> None:
    transformer = VersionedTransformer()
    service = PayloadService(session, transformer, ttl=TTL, clock=clock)
    original, _ = service.create_payload(["a"], ["b"])
    original_id = original.id
    transformer.version = 2
    clock.advance(TTL + timedelta(seconds=1))

    refreshed, created = service.create_payload(["a"], ["b"])

    assert not created
    assert refreshed.id == original_id
    assert refreshed.output == "Av2, Bv2"
    stored = service.get_payload(original_id)
    assert stored is not None
    assert stored.output == "Av2, Bv2"


def test_payload_within_ttl_is_not_regenerated(session: Session, clock: FakeClock) -> None:
    transformer = VersionedTransformer()
    service = PayloadService(session, transformer, ttl=TTL, clock=clock)
    service.create_payload(["a"], ["b"])
    transformer.version = 2
    transformer.calls.clear()
    clock.advance(TTL - timedelta(seconds=1))

    payload, _ = service.create_payload(["a"], ["b"])

    assert payload.output == "Av1, Bv1"
    assert transformer.calls == []


def test_without_ttl_cache_never_expires(
    session: Session, transformer: SpyTransformer, clock: FakeClock
) -> None:
    service = PayloadService(session, transformer, ttl=None, clock=clock)
    service.create_payload(["a"], ["b"])
    transformer.calls.clear()
    clock.advance(timedelta(days=3650))

    service.create_payload(["a"], ["b"])
    service.create_payload(["b"], ["a"])

    assert transformer.calls == []
