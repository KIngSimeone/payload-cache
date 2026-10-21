"""API contract shared by the service and the CLI.

Keeping one definition means the CLI rejects bad input with the same rules the
service would, before spending a network round trip on it.
"""

import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Bounds the work (and transformer calls) a single request can trigger.
MAX_ITEMS_PER_LIST = 1000


class PayloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    list_1: list[str] = Field(min_length=1, max_length=MAX_ITEMS_PER_LIST)
    list_2: list[str] = Field(min_length=1, max_length=MAX_ITEMS_PER_LIST)

    @model_validator(mode="after")
    def _lists_have_same_length(self) -> Self:
        if len(self.list_1) != len(self.list_2):
            raise ValueError("list_1 and list_2 must have the same length")
        return self


class PayloadCreated(BaseModel):
    id: uuid.UUID
    message: str


class PayloadResponse(BaseModel):
    output: str
