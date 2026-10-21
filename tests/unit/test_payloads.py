import pytest

from payload_cache.service.payloads import fingerprint, interleave, render_output


def test_interleave_alternates_between_lists() -> None:
    assert interleave(["a", "b", "c"], ["x", "y", "z"]) == ["a", "x", "b", "y", "c", "z"]


def test_interleave_rejects_lists_of_different_length() -> None:
    with pytest.raises(ValueError):
        interleave(["a"], ["x", "y"])


def test_render_output_matches_spec_format() -> None:
    assert render_output(["FIRST STRING", "OTHER STRING"]) == "FIRST STRING, OTHER STRING"


def test_fingerprint_is_deterministic() -> None:
    assert fingerprint(["a", "b"], ["c", "d"]) == fingerprint(["a", "b"], ["c", "d"])


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # Same strings, swapped lists.
        ((["a"], ["b"]), (["b"], ["a"])),
        # Same concatenation, different list boundaries.
        ((["a,b"], ["c"]), (["a"], ["b,c"])),
        # Inputs that would render the same output after upper-casing.
        ((["a"], ["b"]), (["A"], ["B"])),
    ],
)
def test_fingerprint_distinguishes_different_inputs(
    left: tuple[list[str], list[str]], right: tuple[list[str], list[str]]
) -> None:
    assert fingerprint(*left) != fingerprint(*right)
