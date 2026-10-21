"""Stand-in for the external "transformer" service.

The task treats each transformation as an expensive remote call, so the rest of
the service is built around calling it as rarely as possible. The optional delay
makes that cost visible when exercising the service with ``cache-cli --repeat``.
"""

import time
from collections.abc import Callable

Transformer = Callable[[str], str]


def make_transformer(delay_seconds: float = 0.0) -> Transformer:
    def transform(value: str) -> str:
        if delay_seconds:
            time.sleep(delay_seconds)
        return value.upper()

    return transform
