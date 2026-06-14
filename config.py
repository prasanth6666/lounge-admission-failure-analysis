# Mapping of card type to the specific lounges it is eligible to access
CARD_LOUNGE_ELIGIBILITY = {
    "SKYCARD_ELITE":  {"GTX-T1-VL", "GTX-T3-VL", "NZP-T2-VL", "WQR-T1-VL", "PRV-T5-VL"},
    "NEXUS_INFINITE": {"GTX-T1-VL", "GTX-T3-VL", "NZP-T2-VL", "WQR-T1-VL", "PRV-T5-VL"},
    "ATLAS_PREMIUM":  {"GTX-T1-VL", "GTX-T3-VL", "NZP-T2-VL"},
    "ZEPHYR_WORLD":   {"GTX-T1-VL", "NZP-T2-VL", "WQR-T1-VL"},
    "CREST_PLUS":     {"GTX-T3-VL", "PRV-T5-VL"},
}

# Number of hours before departure that lounge access is permitted
LOUNGE_ACCESS_WINDOW_HOURS = 3

# Visit limits per card type
# period: "monthly" or "quarterly"
# limit: maximum number of lounge visits allowed in that period
CARD_VISIT_LIMITS = {
    "SKYCARD_ELITE":  {"period": "quarterly", "limit": 4},
    "NEXUS_INFINITE": {"period": "monthly",   "limit": 2},
    "ATLAS_PREMIUM":  {"period": "monthly",   "limit": 1},
    "ZEPHYR_WORLD":   {"period": "quarterly", "limit": 2},
    "CREST_PLUS":     {"period": "monthly",   "limit": 1},
}

# Salt for card number hashing — in production move this to .env
CARD_HASH_SALT = "lounge-system-2026-xK9mP2"

# Name similarity threshold for inconclusive flagging.
# Scores at or above this value are treated as "similar but not identical" → inconclusive.
# Scores below this value are treated as a definitive mismatch → failed.
NAME_SIMILARITY_THRESHOLD = 0.90

# Valid entitlement types
ENTITLEMENT_TYPES = {"CREDIT_CARD", "BOOKING", "AIRLINE_STATUS"}

# Airline alliance statuses that qualify for complimentary lounge access
VALID_AIRLINE_STATUSES = {
    "STAR_GOLD",
    "SKYTEAM_ELITE_PLUS",
    "ONEWORLD_EMERALD",
}
