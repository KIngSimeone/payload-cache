"""Command-line parsing for ``cache-cli``, built on Pydantic Settings.

Parsing and validation live in one model so that every argument is checked
(URL shape, positive repeat count, well-formed payload JSON) before any request
is sent.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Self

from pydantic import AliasChoices, Field, HttpUrl, PositiveInt, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    CliSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from payload_cache.schemas import PayloadRequest

STDIO = "-"


class CliSettings(BaseSettings):
    model_config = SettingsConfigDict(cli_prog_name="cache-cli")

    host: HttpUrl = Field(
        default=HttpUrl("http://localhost:8000"),
        validation_alias=AliasChoices("host", "h"),
        description="Base URL of the payload cache service.",
    )
    repeat: PositiveInt = Field(
        default=1,
        validation_alias=AliasChoices("repeat", "r"),
        description="Number of times to send the request.",
    )
    input: str | None = Field(
        default=None,
        validation_alias=AliasChoices("input", "i"),
        description=f'JSON file with "list_1" and "list_2" ("{STDIO}" for stdin).',
    )
    # Kept as a string: typed as a model, pydantic-settings would expand it into
    # --json.list_1/--json.list_2 flags instead of one JSON argument.
    json_payload: str | None = Field(
        default=None,
        validation_alias=AliasChoices("json", "j"),
        description="The request as an inline JSON string.",
    )
    output: str = Field(
        default=STDIO,
        validation_alias=AliasChoices("output", "o"),
        description=f'File to write results to ("{STDIO}" for stdout).',
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Only explicit arguments count: otherwise an unrelated HOST or INPUT
        # environment variable would silently change what the tool does.
        return (init_settings,)

    @field_validator("input")
    @classmethod
    def _input_file_exists(cls, value: str | None) -> str | None:
        if value not in (None, STDIO) and not Path(value).is_file():
            raise ValueError(f"input file not found: {value}")
        return value

    @field_validator("json_payload")
    @classmethod
    def _json_is_valid_request(cls, value: str | None) -> str | None:
        if value is not None:
            PayloadRequest.model_validate_json(value)
        return value

    @model_validator(mode="after")
    def _exactly_one_input(self) -> Self:
        if (self.input is None) == (self.json_payload is None):
            raise ValueError("provide exactly one of --input or --json")
        return self


def _build_parser() -> argparse.ArgumentParser:
    # The spec assigns -h to --host, so argparse's default -h/--help is
    # replaced by a long-only --help.
    parser = argparse.ArgumentParser(
        prog="cache-cli",
        description="Send payload requests to the cache service and print the results.",
        add_help=False,
    )
    parser.add_argument("--help", action="help", help="Show this help message and exit.")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> CliSettings:
    """Parse and validate ``argv`` (defaults to ``sys.argv[1:]``)."""
    source: CliSettingsSource[CliSettings] = CliSettingsSource(
        CliSettings, root_parser=_build_parser()
    )
    args = list(sys.argv[1:] if argv is None else argv)
    return CliSettings(_cli_settings_source=source(args=args))
