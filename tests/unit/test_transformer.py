from payload_cache.service.transformer import make_transformer


def test_transformer_upper_cases_input() -> None:
    assert make_transformer()("first string") == "FIRST STRING"


def test_transformer_handles_non_ascii() -> None:
    assert make_transformer()("straße é") == "STRASSE É"
