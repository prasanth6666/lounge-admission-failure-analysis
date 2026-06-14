import unicodedata
import re
import hashlib
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

from config import (
    CARD_LOUNGE_ELIGIBILITY,
    LOUNGE_ACCESS_WINDOW_HOURS,
    CARD_VISIT_LIMITS,
    CARD_HASH_SALT,
    NAME_SIMILARITY_THRESHOLD,
    VALID_AIRLINE_STATUSES,
)
from mock_db import CARD_USAGE, USED_REFERENCES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_card(card_number: str) -> str:
    return hashlib.sha256(
        (CARD_HASH_SALT + card_number).encode()
    ).hexdigest()


def _get_period_start(period: str) -> date:
    today = date.today()
    if period == "monthly":
        return date(today.year, today.month, 1)
    elif period == "quarterly":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        return date(today.year, quarter_start_month, 1)
    return date(today.year, today.month, 1)


def _normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", name.upper().strip())


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _bp_failed(details: str) -> dict:
    return {"rule_id": "INVALID_BOARDING_PASS", "result": "failed", "details": details}


# ---------------------------------------------------------------------------
# Rule functions
# ---------------------------------------------------------------------------

def check_boarding_pass_validity(transaction) -> dict:
    try:
        bp = transaction.boarding_pass

        if not bp.passenger_name.strip():
            return _bp_failed("Boarding pass passenger name is missing.")
        if not bp.flight_number.strip():
            return _bp_failed("Boarding pass flight number is missing.")
        if not bp.flight_date:
            return _bp_failed("Boarding pass flight date is missing.")
        if not bp.departure_airport.strip():
            return _bp_failed("Boarding pass departure airport is missing.")
        if not bp.destination_airport.strip():
            return _bp_failed("Boarding pass destination airport is missing.")
        if not bp.booking_reference.strip():
            return _bp_failed("Boarding pass booking reference is missing.")

        return {"rule_id": "INVALID_BOARDING_PASS", "result": "passed", "details": "Boarding pass is valid."}
    except Exception:
        return {
            "rule_id": "INVALID_BOARDING_PASS",
            "result":  "inconclusive",
            "details": "Boarding pass validation could not be completed.",
        }


def check_access_window(transaction) -> dict:
    try:
        bp          = transaction.boarding_pass
        departure   = datetime.combine(bp.flight_date, bp.departure_time)
        now         = datetime.now()
        window_open = departure - timedelta(hours=LOUNGE_ACCESS_WINDOW_HOURS)

        if window_open <= now <= departure:
            return {
                "rule_id": "ACCESS_WINDOW_VIOLATION",
                "result":  "passed",
                "details": "Access attempt is within the permitted window before departure.",
            }

        if now > departure:
            return {
                "rule_id": "ACCESS_WINDOW_VIOLATION",
                "result":  "failed",
                "details": "Flight has already departed. Lounge access is no longer valid for this boarding pass.",
            }

        return {
            "rule_id": "ACCESS_WINDOW_VIOLATION",
            "result":  "failed",
            "details": f"Access attempt is too early. Lounge access is only permitted within {LOUNGE_ACCESS_WINDOW_HOURS} hours before departure.",
        }

    except Exception:
        return {
            "rule_id": "ACCESS_WINDOW_VIOLATION",
            "result":  "inconclusive",
            "details": "Flight date check could not be completed.",
        }


def check_card_eligibility(transaction) -> dict:
    try:
        card_type        = transaction.credit_card.card_type.upper().replace(" ", "_")
        eligible_lounges = CARD_LOUNGE_ELIGIBILITY.get(card_type, set())
        passed           = transaction.lounge_id in eligible_lounges

        return {
            "rule_id": "CARD_NOT_ELIGIBLE_FOR_LOUNGE",
            "result":  "passed" if passed else "failed",
            "details": (
                "Card is eligible for this lounge."
                if passed else
                "Card is not eligible for access to this specific lounge."
            ),
        }
    except Exception:
        return {
            "rule_id": "CARD_NOT_ELIGIBLE_FOR_LOUNGE",
            "result":  "inconclusive",
            "details": "Card eligibility check could not be completed.",
        }


def check_card_expiry(transaction) -> dict:
    try:
        expiry = transaction.credit_card.expiry_date.strip()
        parts  = expiry.split("/")

        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            return {
                "rule_id": "CARD_EXPIRED",
                "result":  "failed",
                "details": "Card expiry date is not in a valid MM/YY format.",
            }

        month = int(parts[0])
        year  = 2000 + int(parts[1])

        if month < 1 or month > 12:
            return {
                "rule_id": "CARD_EXPIRED",
                "result":  "failed",
                "details": "Card expiry month is invalid. Month must be between 01 and 12.",
            }

        today  = date.today()
        passed = (year > today.year) or (year == today.year and month >= today.month)

        return {
            "rule_id": "CARD_EXPIRED",
            "result":  "passed" if passed else "failed",
            "details": (
                "Card expiry date is valid."
                if passed else
                "Card has expired and is no longer valid for lounge access."
            ),
        }
    except Exception:
        return {
            "rule_id": "CARD_EXPIRED",
            "result":  "inconclusive",
            "details": "Card expiry check could not be completed.",
        }



def check_booking_reference_match(transaction) -> dict:
    try:
        submitted_ref = transaction.booking_reference or transaction.qr_code_payload
        submitted     = submitted_ref.strip().upper()
        bp_ref    = transaction.boarding_pass.booking_reference.strip().upper()

        if submitted == bp_ref:
            return {
                "rule_id": "BOOKING_REFERENCE_MISMATCH",
                "result":  "passed",
                "details": "Submitted booking reference matches boarding pass.",
            }

        source = "QR code payload" if transaction.qr_code_payload and not transaction.booking_reference else "Submitted booking reference"
        return {
            "rule_id": "BOOKING_REFERENCE_MISMATCH",
            "result":  "failed",
            "details": f"{source} does not match the booking reference on the boarding pass.",
        }
    except Exception:
        return {
            "rule_id": "BOOKING_REFERENCE_MISMATCH",
            "result":  "inconclusive",
            "details": "Booking reference cross-check could not be completed.",
        }


def check_booking_expiry(transaction) -> dict:
    try:
        expiry = transaction.booking_expiry_date
        today  = date.today()
        passed = expiry >= today

        return {
            "rule_id": "BOOKING_EXPIRED",
            "result":  "passed" if passed else "failed",
            "details": (
                "Booking is within the valid period."
                if passed else
                "Booking has expired and is no longer valid for lounge access."
            ),
        }
    except Exception:
        return {
            "rule_id": "BOOKING_EXPIRED",
            "result":  "inconclusive",
            "details": "Booking expiry check could not be completed.",
        }


def check_duplicate_use(transaction) -> dict:
    try:
        today_str = str(date.today())

        # Check booking reference used today
        ref = transaction.booking_reference or transaction.qr_code_payload
        if ref and ref.strip().upper() in USED_REFERENCES:
            if USED_REFERENCES[ref.strip().upper()] == today_str:
                return {
                    "rule_id": "DUPLICATE_USE",
                    "result":  "failed",
                    "details": "This booking reference has already been used for lounge access today. Each booking reference is valid for a single entry only.",
                }

        # Check card visit limit for the current period
        if transaction.credit_card:
            card_type    = transaction.credit_card.card_type.upper().replace(" ", "_")
            card_hash    = _hash_card(transaction.credit_card.card_number)
            visit_config = CARD_VISIT_LIMITS.get(card_type)

            if visit_config and card_hash in CARD_USAGE:
                period       = visit_config["period"]
                limit        = visit_config["limit"]
                period_start = _get_period_start(period)

                visits_in_period = [
                    d for d in CARD_USAGE[card_hash]
                    if date.fromisoformat(d) >= period_start
                ]

                if len(visits_in_period) >= limit:
                    return {
                        "rule_id": "DUPLICATE_USE",
                        "result":  "failed",
                        "details": (
                            f"This card type ({card_type}) allows {limit} lounge visit(s) "
                            f"per {period} period. This card has already been used "
                            f"{len(visits_in_period)} time(s) since {period_start}. "
                            "Complimentary access limit has been reached"
                        ),
                    }

        return {
            "rule_id": "DUPLICATE_USE",
            "result":  "passed",
            "details": "No duplicate use or visit limit exceeded detected",
        }
    except Exception:
        return {
            "rule_id": "DUPLICATE_USE",
            "result":  "inconclusive",
            "details": "Duplicate use check could not be completed.",
        }


def check_airline_status_eligibility(transaction) -> dict:
    try:
        status_id = transaction.airline_status_id.strip().upper()
        passed    = status_id in VALID_AIRLINE_STATUSES

        return {
            "rule_id": "AIRLINE_STATUS_INVALID",
            "result":  "passed" if passed else "failed",
            "details": (
                "Airline status qualifies for complimentary lounge access."
                if passed else
                "Airline status does not qualify for complimentary lounge access."
            ),
        }
    except Exception:
        return {
            "rule_id": "AIRLINE_STATUS_INVALID",
            "result":  "inconclusive",
            "details": "Airline status check could not be completed.",
        }


def check_card_holder_name(transaction) -> dict:
    try:
        card_name  = _normalize_name(transaction.credit_card.card_holder_name)
        bp_name    = _normalize_name(transaction.boarding_pass.passenger_name)
        similarity = _name_similarity(card_name, bp_name)

        if card_name == bp_name:
            return {
                "rule_id": "CARD_HOLDER_NAME_MISMATCH",
                "result":  "passed",
                "details": "Card holder name matches boarding pass.",
            }

        if similarity >= NAME_SIMILARITY_THRESHOLD:
            return {
                "rule_id": "CARD_HOLDER_NAME_MISMATCH",
                "result":  "inconclusive",
                "details": "Card holder name is similar but not identical to the name on the boarding pass.",
            }

        return {
            "rule_id": "CARD_HOLDER_NAME_MISMATCH",
            "result":  "failed",
            "details": "Card holder name does not match the name on the boarding pass.",
        }
    except Exception:
        return {
            "rule_id": "CARD_HOLDER_NAME_MISMATCH",
            "result":  "inconclusive",
            "details": "Card holder name check could not be completed.",
        }


def check_guest_name_against_boarding_pass(transaction) -> dict:
    try:
        bp_name    = _normalize_name(transaction.boarding_pass.passenger_name)
        guest_name = _normalize_name(transaction.guest_name)
        similarity = _name_similarity(bp_name, guest_name)

        if bp_name == guest_name:
            return {
                "rule_id": "GUEST_NAME_MISMATCH",
                "result":  "passed",
                "details": "Names match.",
            }

        if similarity >= NAME_SIMILARITY_THRESHOLD:
            return {
                "rule_id": "GUEST_NAME_MISMATCH",
                "result":  "inconclusive",
                "details": "Guest name is similar but not identical to the name on the boarding pass.",
            }

        return {
            "rule_id": "GUEST_NAME_MISMATCH",
            "result":  "failed",
            "details": "Name on boarding pass does not match the submitted guest name.",
        }
    except Exception:
        return {
            "rule_id": "GUEST_NAME_MISMATCH",
            "result":  "inconclusive",
            "details": "Name check could not be completed.",
        }


