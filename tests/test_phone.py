"""normalize_phone is the primary WhatsApp contact-matching mechanism (spec
section 13: "phone number should be the primary matching mechanism, do not
rely only on name matching") — it must be correct and pure, no DB dependency.
"""

from app.utils.phone import normalize_phone


def test_bare_nepali_number_gets_country_code():
    assert normalize_phone("9800000000") == "+9779800000000"


def test_already_e164_is_unchanged():
    assert normalize_phone("+9779800000000") == "+9779800000000"


def test_country_code_without_plus():
    assert normalize_phone("9779812345678") == "+9779812345678"


def test_formatting_characters_are_stripped():
    assert normalize_phone("98123 45678") == "+9779812345678"
    assert normalize_phone("+977 981-234-5678") == "+9779812345678"


def test_empty_and_none_return_none():
    assert normalize_phone("") is None
    assert normalize_phone(None) is None
    assert normalize_phone("   ") is None


def test_unparseable_input_returns_none_not_an_exception():
    assert normalize_phone("not-a-phone-number") is None


def test_respects_explicit_default_region():
    # A bare 10-digit US-shaped number defaults to Nepal today; passing a
    # different region should change the result rather than being ignored.
    assert normalize_phone("2025551234", default_region="US") == "+12025551234"
