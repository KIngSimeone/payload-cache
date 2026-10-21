"""Pure helpers for building payloads, kept free of I/O so they are trivial to test."""

import hashlib
import json
from collections.abc import Sequence
from itertools import chain

OUTPUT_SEPARATOR = ", "


def interleave(first: Sequence[str], second: Sequence[str]) -> list[str]:
    """Return ``[first[0], second[0], first[1], second[1], ...]``."""
    if len(first) != len(second):
        raise ValueError("sequences must have the same length")
    return list(chain.from_iterable(zip(first, second, strict=True)))


def render_output(items: Sequence[str]) -> str:
    return OUTPUT_SEPARATOR.join(items)


def fingerprint(list_1: Sequence[str], list_2: Sequence[str]) -> str:
    """Stable key for a pair of input lists, used to reuse payload identifiers.

    The key is derived from the *input*, not the output: two different inputs can
    render the same output string (e.g. ``["a"]`` vs ``["A"]``) yet are distinct
    requests. JSON encoding keeps list boundaries unambiguous, which a plain join
    would not.
    """
    canonical = json.dumps([list(list_1), list(list_2)], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
