from __future__ import annotations

import phonenumbers

# Used only when a number has no explicit country code (no leading '+') — the
# consultancy's primary market. Existing Lead.phone values in this codebase
# are stored exactly this way (e.g. "9800000000", no '+977' prefix).
DEFAULT_REGION = "NP"


def normalize_phone(raw: str | None, default_region: str = DEFAULT_REGION) -> str | None:
    """Best-effort E.164 normalization (e.g. "9800000000" -> "+9779800000000").

    Returns None if `raw` is empty or can't be parsed as a valid number,
    rather than raising — callers (contact matching, outbound sends) should
    treat that as "no usable phone number", not crash. Phone number is the
    primary WhatsApp contact-matching mechanism, so this must be reused
    identically everywhere a phone is compared, never re-implemented ad hoc.
    """
    if not raw or not raw.strip():
        return None
    try:
        parsed = phonenumbers.parse(raw.strip(), default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
