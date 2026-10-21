from datetime import timedelta

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration, read from ``CACHE_*`` environment variables."""

    # "none" lets CACHE_TTL_SECONDS=none disable expiry from the environment.
    model_config = SettingsConfigDict(env_prefix="CACHE_", env_parse_none_str="none")

    database_url: str = "sqlite:///./cache.db"
    # Simulated latency of the external transformer, so cache hits are observable.
    transformer_delay_seconds: float = Field(default=0.2, ge=0)
    # How long a transformed string may be reused before the transformer is
    # called again. Set it depending on how long the transformed data stays
    # valid: a deterministic transformer (like the upper-casing stand-in) never
    # goes stale, so None (no expiry) is safe, whereas a service whose answers
    # change over time needs a TTL no longer than it can tolerate stale data.
    # Shorter TTLs trade more transformer calls for fresher payloads.
    ttl_seconds: float | None = Field(default=24 * 60 * 60, gt=0)

    @property
    def ttl(self) -> timedelta | None:
        return None if self.ttl_seconds is None else timedelta(seconds=self.ttl_seconds)
