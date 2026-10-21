import uuid

from sqlmodel import Session, select

from payload_cache.service.cache import PayloadService
from payload_cache.service.models import TransformedString
from tests.conftest import SpyTransformer

SAMPLE_1 = ["first string", "second string", "third string"]
SAMPLE_2 = ["other string", "another string", "last string"]


def test_creates_interleaved_payload(session: Session, transformer: SpyTransformer) -> None:
    payload, created = PayloadService(session, transformer).create_payload(SAMPLE_1, SAMPLE_2)

    assert created
    assert payload.output == (
        "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"
    )


def test_same_input_reuses_identifier_without_transforming(
    session: Session, transformer: SpyTransformer
) -> None:
    service = PayloadService(session, transformer)
    first, _ = service.create_payload(SAMPLE_1, SAMPLE_2)
    transformer.calls.clear()

    second, created = service.create_payload(SAMPLE_1, SAMPLE_2)

    assert not created
    assert second.id == first.id
    assert transformer.calls == []


def test_duplicate_strings_are_transformed_once(
    session: Session, transformer: SpyTransformer
) -> None:
    PayloadService(session, transformer).create_payload(["a", "b", "a"], ["b", "a", "c"])

    assert sorted(transformer.calls) == ["a", "b", "c"]


def test_overlapping_request_only_transforms_new_strings(
    session: Session, transformer: SpyTransformer
) -> None:
    service = PayloadService(session, transformer)
    service.create_payload(["a", "b"], ["c", "d"])
    transformer.calls.clear()

    payload, created = service.create_payload(["d", "c"], ["b", "e"])

    assert created
    assert payload.output == "D, B, C, E"
    assert transformer.calls == ["e"]


def test_transformed_strings_are_persisted(session: Session, transformer: SpyTransformer) -> None:
    PayloadService(session, transformer).create_payload(["a"], ["b"])

    rows = session.exec(select(TransformedString)).all()
    assert {(row.source, row.result) for row in rows} == {("a", "A"), ("b", "B")}


def test_get_payload_returns_none_for_unknown_id(
    session: Session, transformer: SpyTransformer
) -> None:
    assert PayloadService(session, transformer).get_payload(uuid.uuid4()) is None
