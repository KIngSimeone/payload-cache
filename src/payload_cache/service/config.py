from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration, read from ``CACHE_*`` environment variables."""

    model_config = SettingsConfigDict(env_prefix="CACHE_")

    database_url: str = "sqlite:///./cache.db"
    # Simulated latency of the external transformer, so cache hits are observable.
    transformer_delay_seconds: float = Field(default=0.2, ge=0)
