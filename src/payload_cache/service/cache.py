"""Payload generation backed by the transformer cache.

The transformer is treated as expensive, so a request only calls it for
strings that have never been seen before, and only once per distinct string.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, col, select

from payload_cache.service.models import Payload, TransformedString
from payload_cache.service.payloads import fingerprint, interleave, render_output
from payload_cache.service.transformer import Transformer


class PayloadService:
    def __init__(self, session: Session, transformer: Transformer) -> None:
        self._session = session
        self._transformer = transformer

    def get_payload(self, payload_id: uuid.UUID) -> Payload | None:
        return self._session.get(Payload, payload_id)

    def create_payload(self, list_1: list[str], list_2: list[str]) -> tuple[Payload, bool]:
        """Return the payload for these inputs and whether it was newly created.

        Identical inputs always map to the same payload, so a repeat request
        costs one indexed lookup and no transformer calls at all.
        """
        input_hash = fingerprint(list_1, list_2)
        existing = self._find_by_hash(input_hash)
        if existing is not None:
            return existing, False

        transformed = self._transform(set(list_1) | set(list_2))
        output = render_output(
            interleave([transformed[s] for s in list_1], [transformed[s] for s in list_2])
        )

        new_id = uuid.uuid4()
        # A concurrent request with the same input may insert first. Ignoring
        # the conflict and re-reading returns the winner's identifier instead
        # of failing or creating a duplicate.
        self._session.execute(
            insert(Payload)
            .values(id=new_id, input_hash=input_hash, output=output)
            .on_conflict_do_nothing(index_elements=["input_hash"])
        )
        self._session.commit()

        payload = self._find_by_hash(input_hash)
        assert payload is not None  # Inserted above or by a concurrent request.
        return payload, payload.id == new_id

    def _find_by_hash(self, input_hash: str) -> Payload | None:
        return self._session.exec(select(Payload).where(Payload.input_hash == input_hash)).first()

    def _transform(self, sources: Iterable[str]) -> dict[str, str]:
        """Map each distinct source string to its transformed value, filling cache misses."""
        sources = set(sources)
        cached_rows = self._session.exec(
            select(TransformedString).where(col(TransformedString.source).in_(sources))
        )
        results = {row.source: row.result for row in cached_rows}

        misses = sorted(sources - results.keys())
        if misses:
            fresh = {source: self._transformer(source) for source in misses}
            # Another request may cache the same string meanwhile; both computed
            # the same value, so keeping whichever landed first is correct.
            self._session.execute(
                insert(TransformedString)
                .values([{"source": s, "result": r} for s, r in fresh.items()])
                .on_conflict_do_nothing(index_elements=["source"])
            )
            results |= fresh
        return results
