"""Runs the CLI against the real application in-process.

FastAPI's TestClient is an ``httpx2.Client``, so the CLI's request code is
exercised end to end without starting a server.
"""

import io
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from payload_cache.cli.main import EXIT_REQUEST_FAILED, EXIT_USAGE, main, run
from payload_cache.cli.settings import parse_args
from payload_cache.service.config import Settings
from payload_cache.service.main import create_app
from tests.conftest import SpyTransformer

REQUEST = {"list_1": ["first string", "second string"], "list_2": ["other string", "last string"]}
EXPECTED_OUTPUT = "FIRST STRING, OTHER STRING, SECOND STRING, LAST STRING"


@pytest.fixture
def client(tmp_path: Path, transformer: SpyTransformer) -> Iterator[TestClient]:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'cli.db'}")
    with TestClient(create_app(settings, transformer)) as client:
        yield client


def run_cli(argv: list[str], client: TestClient, stdin: str = "") -> list[dict[str, object]]:
    stdout = io.StringIO()
    run(parse_args(argv), client, io.StringIO(stdin), stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def test_repeated_runs_reuse_the_payload(client: TestClient, transformer: SpyTransformer) -> None:
    results = run_cli(["--json", json.dumps(REQUEST), "--repeat", "3"], client)

    assert [r["iteration"] for r in results] == [1, 2, 3]
    assert [r["created"] for r in results] == [True, False, False]
    assert len({r["id"] for r in results}) == 1
    assert all(r["output"] == EXPECTED_OUTPUT for r in results)
    assert len(transformer.calls) == 4


def test_reads_request_from_stdin(client: TestClient) -> None:
    results = run_cli(["--input", "-"], client, stdin=json.dumps(REQUEST))

    assert results[0]["output"] == EXPECTED_OUTPUT


def test_reads_request_from_file_and_writes_output_file(client: TestClient, tmp_path: Path) -> None:
    input_file = tmp_path / "request.json"
    input_file.write_text(json.dumps(REQUEST))
    output_file = tmp_path / "results.jsonl"

    assert run_cli(["-i", str(input_file), "-o", str(output_file)], client) == []
    result = json.loads(output_file.read_text())
    assert result["output"] == EXPECTED_OUTPUT


def test_main_reports_invalid_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repeat", "0", "--input", "-"]) == EXIT_USAGE
    assert "--repeat" in capsys.readouterr().err


def test_main_reports_invalid_input_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_file = tmp_path / "request.json"
    input_file.write_text('{"list_1": ["a"]}')

    assert main(["--input", str(input_file)]) == EXIT_USAGE
    assert "invalid input" in capsys.readouterr().err


def test_main_reports_unreachable_server(capsys: pytest.CaptureFixture[str]) -> None:
    # Port 9 (discard) is essentially never listening on a dev machine or CI runner.
    exit_code = main(["--host", "http://127.0.0.1:9", "--json", json.dumps(REQUEST)])

    assert exit_code == EXIT_REQUEST_FAILED
    assert "could not reach" in capsys.readouterr().err
