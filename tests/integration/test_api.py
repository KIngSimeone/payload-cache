import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from payload_cache.service.config import Settings
from payload_cache.service.main import create_app
from tests.conftest import SpyTransformer

SAMPLE_REQUEST = {
    "list_1": ["first string", "second string", "third string"],
    "list_2": ["other string", "another string", "last string"],
}


@pytest.fixture
def client(tmp_path: Path, transformer: SpyTransformer) -> Iterator[TestClient]:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(create_app(settings, transformer)) as client:
        yield client


def test_create_then_read_payload(client: TestClient) -> None:
    created = client.post("/payload", json=SAMPLE_REQUEST)

    assert created.status_code == 201
    payload_id = created.json()["id"]
    assert created.headers["Location"] == f"/payload/{payload_id}"

    fetched = client.get(f"/payload/{payload_id}")

    assert fetched.status_code == 200
    assert fetched.json() == {
        "output": "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, "
        "THIRD STRING, LAST STRING"
    }


def test_repeated_request_reuses_identifier_and_cache(
    client: TestClient, transformer: SpyTransformer
) -> None:
    first = client.post("/payload", json=SAMPLE_REQUEST)
    calls_after_first = len(transformer.calls)

    second = client.post("/payload", json=SAMPLE_REQUEST)

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert len(transformer.calls) == calls_after_first == 6


def test_cache_is_shared_across_different_payloads(
    client: TestClient, transformer: SpyTransformer
) -> None:
    client.post("/payload", json=SAMPLE_REQUEST)
    transformer.calls.clear()

    response = client.post(
        "/payload", json={"list_1": ["first string", "new string"], "list_2": ["last string", "x"]}
    )

    assert response.status_code == 201
    assert sorted(transformer.calls) == ["new string", "x"]


def test_cache_survives_restart(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'restart.db'}")
    with TestClient(create_app(settings, SpyTransformer())) as client:
        payload_id = client.post("/payload", json=SAMPLE_REQUEST).json()["id"]

    restarted_transformer = SpyTransformer()
    with TestClient(create_app(settings, restarted_transformer)) as client:
        response = client.post("/payload", json=SAMPLE_REQUEST)

    assert response.json()["id"] == payload_id
    assert restarted_transformer.calls == []


def test_unknown_payload_returns_404(client: TestClient) -> None:
    response = client.get(f"/payload/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Payload not found"}


def test_malformed_identifier_returns_422(client: TestClient) -> None:
    assert client.get("/payload/not-a-uuid").status_code == 422


def test_lists_of_different_length_are_rejected(
    client: TestClient, transformer: SpyTransformer
) -> None:
    response = client.post("/payload", json={"list_1": ["a", "b"], "list_2": ["c"]})

    assert response.status_code == 422
    assert transformer.calls == []


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
