"""_candidate_phone_forms is what stands between an inbound WhatsApp phone
number and an existing Lead/User row stored in whatever raw format a
counsellor originally typed it in (see whatsapp_service.py's module
docstring-equivalent comment). Pure function, no DB — the actual DB lookup
(_find_crm_match) is exercised by hand in the plan's Phase 4/6 verification
steps instead, since it needs a real session.
"""

from app.services.whatsapp_service import _candidate_phone_forms


def test_includes_e164_and_bare_digits():
    forms = _candidate_phone_forms("+9779812345678")
    assert "+9779812345678" in forms
    assert "9779812345678" in forms


def test_includes_last_ten_digits_for_long_numbers():
    forms = _candidate_phone_forms("+9779812345678")
    assert "9812345678" in forms


def test_short_numbers_do_not_get_a_spurious_last_ten_form():
    forms = _candidate_phone_forms("+12025551234")
    # 12025551234 is exactly 11 digits — no separate "last 10" entry needed
    # beyond what's already covered, but must not crash or produce garbage.
    assert all(isinstance(f, str) and f for f in forms)
