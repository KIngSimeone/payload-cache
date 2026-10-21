"""``cache-cli``: send a payload request to the service, optionally repeatedly.

Each iteration posts the request, fetches the resulting payload and writes one
JSON line (identifier, whether it was newly created, latency, output). Running
with ``--repeat`` shows the cache at work: the identifier stays the same and
later iterations are much faster than the first.
"""

import json
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import IO, Any

import httpx2
from pydantic import ValidationError

from payload_cache.cli.settings import STDIO, CliSettings, parse_args
from payload_cache.schemas import PayloadCreated, PayloadRequest, PayloadResponse

EXIT_OK = 0
EXIT_REQUEST_FAILED = 1
EXIT_USAGE = 2  # Matches argparse's exit code for bad arguments.

REQUEST_TIMEOUT_SECONDS = 30.0


def load_request(settings: CliSettings, stdin: IO[str]) -> PayloadRequest:
    if settings.json_payload is not None:
        return PayloadRequest.model_validate_json(settings.json_payload)
    if settings.input == STDIO:
        return PayloadRequest.model_validate_json(stdin.read())
    assert settings.input is not None  # Guaranteed by CliSettings validation.
    with open(settings.input, encoding="utf-8") as file:
        return PayloadRequest.model_validate_json(file.read())


@contextmanager
def open_output(target: str, stdout: IO[str]) -> Iterator[IO[str]]:
    if target == STDIO:
        with nullcontext(stdout) as stream:
            yield stream
    else:
        with open(target, "w", encoding="utf-8") as stream:
            yield stream


def send_once(client: httpx2.Client, request: PayloadRequest) -> dict[str, Any]:
    started = time.perf_counter()
    created_response = client.post("/payload", json=request.model_dump())
    created_response.raise_for_status()
    created = PayloadCreated.model_validate_json(created_response.content)

    payload_response = client.get(f"/payload/{created.id}")
    payload_response.raise_for_status()
    payload = PayloadResponse.model_validate_json(payload_response.content)

    return {
        "id": str(created.id),
        "created": created_response.status_code == httpx2.codes.CREATED,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "output": payload.output,
    }


def run(settings: CliSettings, client: httpx2.Client, stdin: IO[str], stdout: IO[str]) -> None:
    """Execute the CLI against ``client``; separated from ``main`` so tests can
    pass an in-process client instead of a real server."""
    request = load_request(settings, stdin)
    with open_output(settings.output, stdout) as output:
        for iteration in range(1, settings.repeat + 1):
            result = {"iteration": iteration, **send_once(client, request)}
            output.write(json.dumps(result, ensure_ascii=False) + "\n")
            output.flush()


def main(argv: list[str] | None = None) -> int:
    try:
        settings = parse_args(argv)
    except ValidationError as error:
        _print_error(_format_validation_error(error, loc_prefix="--"))
        return EXIT_USAGE

    base_url = str(settings.host)
    try:
        with httpx2.Client(base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS) as client:
            run(settings, client, sys.stdin, sys.stdout)
    except ValidationError as error:
        # Raised when the --input content is not a valid request.
        _print_error(f"invalid input: {_format_validation_error(error)}")
        return EXIT_USAGE
    except OSError as error:
        _print_error(str(error))
        return EXIT_USAGE
    except httpx2.HTTPStatusError as error:
        response = error.response
        _print_error(f"server returned {response.status_code}: {response.text}")
        return EXIT_REQUEST_FAILED
    except httpx2.TransportError as error:
        _print_error(f"could not reach {base_url}: {error}")
        return EXIT_REQUEST_FAILED
    return EXIT_OK


def _format_validation_error(error: ValidationError, loc_prefix: str = "") -> str:
    return "; ".join(
        f"{loc_prefix}{'.'.join(map(str, e['loc']))}: {e['msg']}" if e["loc"] else e["msg"]
        for e in error.errors()
    )


def _print_error(message: str) -> None:
    print(f"cache-cli: error: {message}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
