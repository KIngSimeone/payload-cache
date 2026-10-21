from pathlib import Path

import pytest
from pydantic import ValidationError

from payload_cache.cli.settings import parse_args

VALID_JSON = '{"list_1": ["a"], "list_2": ["b"]}'


def test_defaults() -> None:
    settings = parse_args(["--json", VALID_JSON])

    assert str(settings.host) == "http://localhost:8000/"
    assert settings.repeat == 1
    assert settings.output == "-"


def test_short_and_long_flags_are_equivalent(tmp_path: Path) -> None:
    input_file = tmp_path / "in.json"
    input_file.write_text(VALID_JSON)
    path = str(input_file)
    short = parse_args(["-h", "http://svc:9000", "-r", "3", "-i", path, "-o", "out"])
    long = parse_args(
        ["--host", "http://svc:9000", "--repeat", "3", "--input", path, "--output", "out"]
    )

    assert short == long
    assert short.repeat == 3


def test_stdin_input_is_accepted() -> None:
    assert parse_args(["--input", "-"]).input == "-"


def test_environment_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST", "http://elsewhere:1234")

    assert str(parse_args(["--json", VALID_JSON]).host) == "http://localhost:8000/"


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--input", "-", "--json", VALID_JSON],
        ["--json", VALID_JSON, "--repeat", "0"],
        ["--json", VALID_JSON, "--repeat", "many"],
        ["--json", VALID_JSON, "--host", "not a url"],
        ["--json", '{"list_1": ["a", "b"], "list_2": ["c"]}'],
        ["--json", "{not json"],
        ["--input", "/definitely/missing.json"],
    ],
    ids=[
        "no-input",
        "both-inputs",
        "zero-repeat",
        "non-numeric-repeat",
        "bad-host",
        "invalid-request",
        "malformed-json",
        "missing-file",
    ],
)
def test_rejects_invalid_arguments(argv: list[str]) -> None:
    with pytest.raises(ValidationError):
        parse_args(argv)
