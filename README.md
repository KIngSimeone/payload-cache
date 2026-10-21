# Payload cache

A FastAPI microservice that generates payloads from two lists of strings and
caches the results of an (expensive, simulated) external transformer, plus
`cache-cli`, a command-line client for exercising it.

Given

```json
{
  "list_1": ["first string", "second string", "third string"],
  "list_2": ["other string", "another string", "last string"]
}
```

each string is transformed (upper-cased, standing in for an external service)
and the two lists are interleaved:

```json
{"output": "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"}
```

## Quick start

With Docker:

```bash
docker compose up --build
```

Locally (requires [uv](https://docs.astral.sh/uv/)):

```bash
uv sync
uv run uvicorn --factory payload_cache.service.main:create_app --reload
```

The API docs are at <http://localhost:8000/docs>.

## API

| Method | Path            | Description |
|--------|-----------------|-------------|
| POST   | `/payload`      | Generate a payload. Returns `{"id", "message"}`. `201` when new, `200` when an identical payload already existed (same `id`). The `Location` header points at the payload. |
| GET    | `/payload/{id}` | Returns `{"output": "..."}`. `404` if unknown, `422` if `id` is not a UUID. |
| GET    | `/health`       | Liveness probe used by the Docker health check. |

Requests are validated before any work is done: both lists are required,
must have the same length, contain only strings, and hold 1–1000 items.

```bash
curl -s -X POST localhost:8000/payload -H 'Content-Type: application/json' \
  -d '{"list_1": ["first string"], "list_2": ["other string"]}'
# {"id":"3f0c…","message":"Payload created"}

curl -s localhost:8000/payload/3f0c…
# {"output":"FIRST STRING, OTHER STRING"}
```

## How caching works

The transformer is treated as the expensive part, so the service avoids calling it
at three levels:

1. **Identical request**: the input lists are hashed (SHA-256 of their
   canonical JSON). If a payload with that hash exists, its identifier is
   returned straight away. No transformer calls are made.
2. **Strings seen before**: every transformed string is stored in the
   `transformed_string` table, keyed by its input. A new request looks up all
   of its strings in one query and only transforms the misses, so partially
   overlapping requests reuse earlier work.
3. **Duplicates within a request**: strings are de-duplicated before
   transforming, so `["a", "a"]` costs one call.

Cached results expire after a TTL (`CACHE_TTL_SECONDS`, default one day).
Choose it based on how long the transformed data stays valid. A
deterministic transformer never goes stale (`none` disables expiry), while an
external service whose answers change needs a TTL no longer than the
staleness you can accept. Expired strings are transformed again on their next
use. An expired payload keeps its identifier, and its output is regenerated
on the next `POST` with the same input.

Both tables have unique keys (`input_hash`, `source`) and inserts use
`ON CONFLICT DO NOTHING`. If two identical requests race, both get the same
identifier and neither fails.

## CLI

```text
cache-cli [-h|--host URL] [-r|--repeat N] [-i|--input FILE|-] [-j|--json JSON] [-o|--output FILE|-] [--help]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `-h`, `--host`   | `http://localhost:8000` | Service base URL |
| `-r`, `--repeat` | `1`   | Number of iterations (≥ 1) |
| `-i`, `--input`  |       | JSON request file, `-` for stdin |
| `-j`, `--json`   |       | JSON request as an argument |
| `-o`, `--output` | `-`   | Results file, `-` for stdout |

Exactly one of `--input` / `--json` is required. Each iteration POSTs the
request, GETs the payload and writes one JSON line:

```bash
uv run cache-cli -r 3 -j '{"list_1": ["first string", "second string"], "list_2": ["other string", "last string"]}'
# {"iteration": 1, "id": "…", "created": true,  "elapsed_ms": 812.4, "output": "FIRST STRING, OTHER STRING, SECOND STRING, LAST STRING"}
# {"iteration": 2, "id": "…", "created": false, "elapsed_ms": 4.1,   "output": "…"}
# {"iteration": 3, "id": "…", "created": false, "elapsed_ms": 3.8,   "output": "…"}

echo '{"list_1": ["a"], "list_2": ["b"]}' | uv run cache-cli -i -
```

Exit codes: `0` success, `1` request failed (server error or unreachable),
`2` invalid arguments or input.

## Configuration

The service reads environment variables:

| Variable | Default | Meaning |
|----------|---------|---------|
| `CACHE_DATABASE_URL` | `sqlite:///./cache.db` (`/data/cache.db` in Docker) | SQLAlchemy database URL |
| `CACHE_TRANSFORMER_DELAY_SECONDS` | `0.2` | Simulated latency per transformer call |
| `CACHE_TTL_SECONDS` | `86400` | How long cached results stay valid; `none` never expires |

## Project layout

```text
src/payload_cache/
  schemas.py            request/response models shared by service and CLI
  service/
    main.py             app factory and lifespan (DB init)
    api.py              routes and dependency wiring
    cache.py            PayloadService: cache lookups, transformer calls, persistence
    payloads.py         pure helpers: interleave, render, fingerprint
    models.py           SQLModel tables
    db.py               engine/session setup
    transformer.py      simulated external transformer
    config.py           environment settings
  cli/
    settings.py         argument parsing and validation (Pydantic Settings)
    main.py             request loop, I/O and error reporting
tests/
  unit/                 pure functions, schemas, PayloadService on a temp SQLite DB, CLI parsing
  integration/          HTTP API via TestClient, CLI end to end against the in-process app
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests
```

## Design decisions and shortcuts

- **Transformer as an injected callable.** The app factory takes a `transformer`
  argument, so tests can pass a spy that counts calls. That is how the
  "minimise transformer calls" requirement is checked.
- **Payload output is stored, not recomputed.** `GET` is a primary-key lookup.
  The output can be rebuilt from `transformed_string`, but storing it keeps
  reads trivial. The cost is some duplicated text.
- **Identifiers are random UUIDs, with a separate unique input hash.** Using the
  hash itself as the id would also work, but UUIDs keep ids opaque and short to
  validate.
- **The transformer runs while the request's DB transaction is open.** That
  is fine for SQLite and a simulated call. With a real remote service I would
  call it outside the transaction (and probably in batches/concurrently).
- **SQLite only.** The conflict-ignoring inserts use the SQLite dialect. Moving
  to PostgreSQL means switching that import to `sqlalchemy.dialects.postgresql`
  (same `on_conflict_do_nothing` API) and adding a driver.
- **`create_all` instead of migrations.** Acceptable for two tables. A real
  deployment would use Alembic. It also cannot add columns to an existing
  database, so after a schema change, delete `cache.db` or run
  `docker compose down -v`.
- **TTL expiry, not deletion.** Expired rows stay in the database and are
  overwritten when next used. Nothing removes entries that are never
  requested again; a periodic cleanup job would handle that if storage
  mattered.
- **`GET` may return an expired payload.** Only the input hash is stored, not
  the input lists, so the service cannot rebuild a payload on read. It is
  refreshed on the next `POST` with the same input. Storing the inputs would
  allow refreshing on `GET` as well.
- **`-h` means `--host`.** The spec assigns `-h` to both `--host` and `--help`.
  Host wins, and help is available as `--help` only.
- **Output separator.** The output joins with `", "` as specified, so a string
  that itself contains `", "` is ambiguous in the output. Returning a JSON list
  would fix that, but would change the specified response format.
