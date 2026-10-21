"""Payload generation backed by the transformer cache.

The transformer is treated as expensive, so a request only calls it for
strings that have never been seen before (or whose cached result has expired),
and only once per distinct string.
"""

import uuid
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, true, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Mapped
from sqlmodel import Session, col, select

from payload_cache.service.models import Payload, TransformedString, utcnow
from payload_cache.service.payloads import fingerprint, interleave, render_output
from payload_cache.service.transformer import Transformer

Clock = Callable[[], datetime]


class PayloadService:
    def __init__(
        self,
        session: Session,
        transformer: Transformer,
        ttl: timedelta | None = None,
        clock: Clock = utcnow,
    ) -> None:
        """``ttl`` of None means cached results never expire. ``clock`` exists
        so tests can move time forward instead of sleeping."""
        self._session = session
        self._transformer = transformer
        self._ttl = ttl
        self._clock = clock

    def get_payload(self, payload_id: uuid.UUID) -> Payload | None:
        # Returns the last generated output even if it is past the TTL: the
        # input lists are not stored, so only a new POST can regenerate it.
        return self._session.get(Payload, payload_id)

    def create_payload(self, list_1: list[str], list_2: list[str]) -> tuple[Payload, bool]:
        """Return the payload for these inputs and whether it was newly created.

        Identical inputs always map to the same payload, so a repeat request
        within the TTL costs one indexed lookup and no transformer calls at all.
        """
        now = self._clock()
        input_hash = fingerprint(list_1, list_2)
        existing = self._find_by_hash(input_hash, now)
        if existing is not None and existing[1]:
            return existing[0], False

        transformed = self._transform(set(list_1) | set(list_2), now)
        output = render_output(
            interleave([transformed[s] for s in list_1], [transformed[s] for s in list_2])
        )

        if existing is not None:
            # Expired: keep the identifier clients already hold, refresh its content.
            payload = existing[0]
            self._session.execute(
                update(Payload)
                .where(col(Payload.id) == payload.id)
                .values(output=output, generated_at=now)
            )
            self._session.commit()
            self._session.refresh(payload)
            return payload, False

        new_id = uuid.uuid4()
        # A concurrent request with the same input may insert first. Ignoring
        # the conflict and re-reading returns the winner's identifier instead
        # of failing or creating a duplicate.
        self._session.execute(
            insert(Payload)
            .values(
                id=new_id, input_hash=input_hash, output=output, created_at=now, generated_at=now
            )
            .on_conflict_do_nothing(index_elements=["input_hash"])
        )
        self._session.commit()

        payload = self._session.exec(select(Payload).where(Payload.input_hash == input_hash)).one()
        return payload, payload.id == new_id

    def _is_fresh(self, timestamp: Mapped[datetime], now: datetime) -> ColumnElement[bool]:
        # Compared in SQL rather than Python because SQLite returns naive
        # datetimes, which cannot be compared with the aware ``now``.
        if self._ttl is None:
            return true()
        return timestamp >= now - self._ttl

    def _find_by_hash(self, input_hash: str, now: datetime) -> tuple[Payload, bool] | None:
        """Return the payload for ``input_hash`` and whether it is still within the TTL."""
        row = self._session.exec(
            select(Payload, self._is_fresh(col(Payload.generated_at), now)).where(
                Payload.input_hash == input_hash
            )
        ).first()
        return None if row is None else (row[0], bool(row[1]))

    def _transform(self, sources: Iterable[str], now: datetime) -> dict[str, str]:
        """Map each distinct source string to its transformed value, filling cache misses."""
        sources = set(sources)
        cached_rows = self._session.exec(
            select(TransformedString).where(
                col(TransformedString.source).in_(sources),
                self._is_fresh(col(TransformedString.cached_at), now),
            )
        )
        results = {row.source: row.result for row in cached_rows}

        # Misses include both unseen strings and expired entries.
        misses = sorted(sources - results.keys())
        if misses:
            fresh = {source: self._transformer(source) for source in misses}
            statement = insert(TransformedString).values(
                [{"source": s, "result": r, "cached_at": now} for s, r in fresh.items()]
            )
            # Expired rows are overwritten in place. If another request cached
            # the same string meanwhile, the newest result wins, which is what
            # a refresh wants anyway.
            self._session.execute(
                statement.on_conflict_do_update(
                    index_elements=["source"],
                    set_={"result": statement.excluded.result, "cached_at": now},
                )
            )
            results |= fresh
        return results
