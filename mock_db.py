import hashlib
from datetime import date

from config import CARD_HASH_SALT


def _hash_card(card_number: str) -> str:
    """Returns a salted SHA256 hash of the full card number."""
    return hashlib.sha256(
        (CARD_HASH_SALT + card_number).encode()
    ).hexdigest()


# ---------------------------------------------------------------------------
# Simulated visit history per card
# ---------------------------------------------------------------------------

CARD_USAGE: dict[str, list[str]] = {
    # NEXUS_INFINITE allows 2 visits/month — this card has already used both
    _hash_card("4000000000009999"): ["2026-06-01", "2026-06-10"],

    # ATLAS_PREMIUM allows 1 visit/month — this card has already used it
    _hash_card("4000000000008888"): ["2026-06-05"],

    # NEXUS_INFINITE allows 2 visits/month — this card has used 1, 1 remaining
    _hash_card("4000000000007777"): ["2026-06-08"],
}


# ---------------------------------------------------------------------------
# Simulated used booking references
#
# Keys are booking references (uppercased).
# Values are the date on which the reference was used (YYYY-MM-DD string).
# ---------------------------------------------------------------------------

USED_REFERENCES: dict[str, str] = {
    "BK-20260613-4421A": str(date.today()),
    "BK-20260613-8875C": str(date.today()),
}
