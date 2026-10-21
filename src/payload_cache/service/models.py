import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class TransformedString(SQLModel, table=True):
    """Cached result of one transformer call, keyed by its input string.

    Caching per string (rather than per request) lets any future request reuse
    work done for earlier ones, even when the lists only partially overlap.
    """

    __tablename__ = "transformed_string"

    source: str = Field(primary_key=True)
    result: str


class Payload(SQLModel, table=True):
    """A generated payload, stored so its identifier can be handed out again."""

    __tablename__ = "payload"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # SHA-256 of the input lists; the unique constraint is what guarantees one
    # identifier per distinct input, even under concurrent requests.
    input_hash: str = Field(unique=True, max_length=64)
    output: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
