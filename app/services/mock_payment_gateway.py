from __future__ import annotations

from decimal import Decimal


def charge(card_number: str, amount: Decimal | float) -> tuple[bool, str]:
    """Mock payment gateway — no real card data is ever persisted or transmitted
    anywhere. Declines any card number ending in '0000' (the standard test-card
    decline convention) so the UI has a real failure path to exercise; approves
    everything else. Swap the body of this function for a real provider
    (Stripe, etc.) later — the signature is the integration boundary.
    """
    normalized = card_number.replace(" ", "").strip()
    if normalized.endswith("0000"):
        return False, "Card declined"
    return True, "Payment approved"
