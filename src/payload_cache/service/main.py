from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from payload_cache.service.api import router
from payload_cache.service.config import Settings
from payload_cache.service.db import create_db_engine, init_db
from payload_cache.service.transformer import Transformer, make_transformer


def create_app(settings: Settings | None = None, transformer: Transformer | None = None) -> FastAPI:
    """Build the application.

    A factory (rather than a module-level app) means importing the module has no
    side effects, and tests can inject their own database and transformer.
    Run with ``uvicorn --factory payload_cache.service.main:create_app``.
    """
    settings = settings or Settings()
    engine = create_db_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        init_db(engine)
        yield
        engine.dispose()

    app = FastAPI(title="Payload cache", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.transformer = transformer or make_transformer(settings.transformer_delay_seconds)
    app.state.cache_ttl = settings.ttl
    app.include_router(router)
    return app
