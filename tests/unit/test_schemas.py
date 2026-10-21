import pytest
from pydantic import ValidationError

from payload_cache.schemas import MAX_ITEMS_PER_LIST, PayloadRequest


def test_accepts_lists_of_equal_length() -> None:
    request = PayloadRequest(list_1=["a", "b"], list_2=["c", "d"])
    assert request.list_1 == ["a", "b"]


@pytest.mark.parametrize(
    "data",
    [
        {"list_1": ["a", "b"], "list_2": ["c"]},
        {"list_1": [], "list_2": []},
        {"list_1": ["a"]},
        {"list_1": ["a"], "list_2": [1]},
        {"list_1": ["a"], "list_2": ["b"], "unexpected": True},
        {"list_1": ["a"] * (MAX_ITEMS_PER_LIST + 1), "list_2": ["b"] * (MAX_ITEMS_PER_LIST + 1)},
    ],
    ids=["unequal-length", "empty", "missing-list", "non-string", "extra-field", "too-long"],
)
def test_rejects_invalid_requests(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PayloadRequest.model_validate(data)
