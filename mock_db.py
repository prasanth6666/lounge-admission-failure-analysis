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


# ---------------------------------------------------------------------------
# Registered lounge bookings
#
# Keys are booking references (uppercased).
# Values are dicts with the booking expiry date.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Registered airline memberships
#
# Keys are membership/frequent-flyer IDs (uppercased).
# Values are the actual status tier held by the member.
# check_airline_status_eligibility looks up the tier here and then verifies
# it against VALID_AIRLINE_STATUSES in config.py.
# ---------------------------------------------------------------------------

VALID_AIRLINE_MEMBERSHIPS: dict[str, str] = {
    "FF-987654321": "STAR_GOLD",
    "FF-111222333": "SKYTEAM_ELITE_PLUS",
    "FF-444555666": "ONEWORLD_EMERALD",
    "FF-000000000": "SILVER_BASIC",      # valid member, but tier does not qualify
}


VALID_BOOKINGS: dict[str, dict] = {
    # Valid, unused — used as the pass scenario in tests
    "BKREF12345":        {"expiry_date": "2027-12-31"},

    # Valid expiry, but already consumed today (also in USED_REFERENCES)
    "BK-20260613-4421A": {"expiry_date": "2026-12-31"},
    "BK-20260613-8875C": {"expiry_date": "2026-12-31"},

    # Expired booking — used to test BOOKING_EXPIRED failure
    "BKREF-EXPIRED-001": {"expiry_date": "2025-01-01"},
}
