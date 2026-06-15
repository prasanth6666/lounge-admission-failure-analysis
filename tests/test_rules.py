"""
Automated test suite for the Lounge Admission Failure Analysis service.

Covers every deterministic rule function with both positive (pass) and
negative (fail / inconclusive) cases, plus end-to-end integration tests
through analyse_transaction().

Run:
    pytest tests/ -v
"""

import pytest
from datetime import datetime, timedelta

from models import AdmissionTransaction, CreditCard
from rules import (
    check_boarding_pass_validity,
    check_access_window,
    check_guest_name_against_boarding_pass,
    check_card_eligibility,
    check_card_expiry,
    check_card_holder_name,
    check_card_visit_limit,
    check_booking_reference_match,
    check_booking_expiry,
    check_booking_reference_duplicate,
    check_airline_status_eligibility,
)
from service import analyse_transaction


# ---------------------------------------------------------------------------
# Transaction builder helpers
# ---------------------------------------------------------------------------

def _bp(hours: float = 2, **overrides) -> dict:
    """Boarding pass dict with departure `hours` hours from now."""
    dt = (datetime.now() + timedelta(hours=hours)).replace(microsecond=0)
    defaults = {
        "passenger_name":      "Alice Johnson",
        "flight_number":       "AB1234",
        "flight_date":         str(dt.date()),
        "departure_time":      dt.strftime("%H:%M:%S"),
        "departure_airport":   "GTX",
        "destination_airport": "NZP",
        "flight_pnr":          "PNR-AB1234",
    }
    defaults.update(overrides)
    return defaults


def _booking(**overrides) -> AdmissionTransaction:
    """Valid BOOKING transaction. Any field can be overridden."""
    defaults = {
        "transaction_id":      "TXN-B001",
        "lounge_id":           "GTX-T1-VL",
        "attempt_timestamp":   datetime.now().isoformat(timespec="seconds"),
        "guest_name":          "Alice Johnson",
        "entitlement_type":    "BOOKING",
        "boarding_pass":       _bp(),
        "booking_reference":   "BKREF12345",
    }
    defaults.update(overrides)
    return AdmissionTransaction(**defaults)


def _card(**overrides) -> AdmissionTransaction:
    """Valid CREDIT_CARD transaction. Any field can be overridden."""
    defaults = {
        "transaction_id":    "TXN-C001",
        "lounge_id":         "GTX-T1-VL",
        "attempt_timestamp": datetime.now().isoformat(timespec="seconds"),
        "guest_name":        "Alice Johnson",
        "entitlement_type":  "CREDIT_CARD",
        "boarding_pass":     _bp(),
        "credit_card":       CreditCard(
            card_number      = "4111111111111111",
            card_type        = "SKYCARD_ELITE",
            expiry_date      = "12/28",
            card_holder_name = "Alice Johnson",
        ),
    }
    defaults.update(overrides)
    return AdmissionTransaction(**defaults)


def _airline(**overrides) -> AdmissionTransaction:
    """Valid AIRLINE_STATUS transaction. Any field can be overridden."""
    defaults = {
        "transaction_id":    "TXN-A001",
        "lounge_id":         "GTX-T1-VL",
        "attempt_timestamp": datetime.now().isoformat(timespec="seconds"),
        "guest_name":        "Alice Johnson",
        "entitlement_type":  "AIRLINE_STATUS",
        "boarding_pass":     _bp(),
        "airline_status_id": "FF-987654321",
    }
    defaults.update(overrides)
    return AdmissionTransaction(**defaults)


# ---------------------------------------------------------------------------
# Common Rule: Boarding Pass Validity
# ---------------------------------------------------------------------------

class TestBoardingPassValidity:

    def test_valid_boarding_pass_passes(self):
        assert check_boarding_pass_validity(_booking())["result"] == "passed"

    def test_empty_passenger_name_fails(self):
        r = check_boarding_pass_validity(_booking(boarding_pass=_bp(passenger_name="")))
        assert r["result"] == "failed"
        assert r["rule_id"] == "INVALID_BOARDING_PASS"

    def test_empty_flight_number_fails(self):
        r = check_boarding_pass_validity(_booking(boarding_pass=_bp(flight_number="")))
        assert r["result"] == "failed"

    def test_empty_departure_airport_fails(self):
        r = check_boarding_pass_validity(_booking(boarding_pass=_bp(departure_airport="")))
        assert r["result"] == "failed"

    def test_empty_flight_pnr_fails(self):
        r = check_boarding_pass_validity(_booking(boarding_pass=_bp(flight_pnr="")))
        assert r["result"] == "failed"


# ---------------------------------------------------------------------------
# Common Rule: Access Window
# ---------------------------------------------------------------------------

class TestAccessWindow:

    def test_within_window_passes(self):
        # Departure 2 hours away — inside the 3-hour access window
        r = check_access_window(_booking(boarding_pass=_bp(hours=2)))
        assert r["result"] == "passed"
        assert r["rule_id"] == "ACCESS_WINDOW_VIOLATION"

    def test_too_early_fails(self):
        # Departure 5 hours away — outside the 3-hour window
        r = check_access_window(_booking(boarding_pass=_bp(hours=5)))
        assert r["result"] == "failed"
        assert "too early" in r["details"].lower()

    def test_after_departure_fails(self):
        # Departure was 1 hour ago
        r = check_access_window(_booking(boarding_pass=_bp(hours=-1)))
        assert r["result"] == "failed"
        assert "departed" in r["details"].lower()


# ---------------------------------------------------------------------------
# Common Rule: Guest Name vs Boarding Pass
# ---------------------------------------------------------------------------

class TestGuestName:

    def test_exact_name_match_passes(self):
        # guest_name and boarding_pass.passenger_name are both "Alice Johnson"
        r = check_guest_name_against_boarding_pass(_booking())
        assert r["result"] == "passed"

    def test_completely_different_name_fails(self):
        r = check_guest_name_against_boarding_pass(_booking(guest_name="Bob Williams"))
        assert r["result"] == "failed"
        assert r["rule_id"] == "GUEST_NAME_MISMATCH"

    def test_similar_name_is_inconclusive(self):
        # "Alice Johnson" vs "Alice Johnston" — similarity ≈ 0.96, above threshold
        txn = _booking(boarding_pass=_bp(passenger_name="Alice Johnston"))
        r = check_guest_name_against_boarding_pass(txn)
        assert r["result"] == "inconclusive"


# ---------------------------------------------------------------------------
# CREDIT_CARD Rule: Card Eligibility
# ---------------------------------------------------------------------------

class TestCardEligibility:

    def test_eligible_card_for_lounge_passes(self):
        # SKYCARD_ELITE is eligible for GTX-T1-VL
        r = check_card_eligibility(_card(lounge_id="GTX-T1-VL"))
        assert r["result"] == "passed"

    def test_ineligible_card_for_lounge_fails(self):
        # CREST_PLUS is only eligible for GTX-T3-VL and PRV-T5-VL, not GTX-T1-VL
        txn = _card(
            lounge_id   = "GTX-T1-VL",
            credit_card = CreditCard(
                card_number      = "4222222222222222",
                card_type        = "CREST_PLUS",
                expiry_date      = "12/28",
                card_holder_name = "Alice Johnson",
            ),
        )
        r = check_card_eligibility(txn)
        assert r["result"] == "failed"
        assert r["rule_id"] == "CARD_NOT_ELIGIBLE_FOR_LOUNGE"


# ---------------------------------------------------------------------------
# CREDIT_CARD Rule: Card Expiry
# ---------------------------------------------------------------------------

class TestCardExpiry:

    def test_valid_future_expiry_passes(self):
        assert check_card_expiry(_card())["result"] == "passed"

    def test_expired_card_fails(self):
        txn = _card(credit_card=CreditCard(
            card_number      = "4111111111111111",
            card_type        = "SKYCARD_ELITE",
            expiry_date      = "01/23",
            card_holder_name = "Alice Johnson",
        ))
        r = check_card_expiry(txn)
        assert r["result"] == "failed"
        assert r["rule_id"] == "CARD_EXPIRED"

    def test_invalid_expiry_format_fails(self):
        txn = _card(credit_card=CreditCard(
            card_number      = "4111111111111111",
            card_type        = "SKYCARD_ELITE",
            expiry_date      = "1228",
            card_holder_name = "Alice Johnson",
        ))
        assert check_card_expiry(txn)["result"] == "failed"


# ---------------------------------------------------------------------------
# CREDIT_CARD Rule: Card Holder Name vs Boarding Pass
# ---------------------------------------------------------------------------

class TestCardHolderName:

    def test_exact_name_match_passes(self):
        # card_holder_name and boarding_pass.passenger_name are both "Alice Johnson"
        assert check_card_holder_name(_card())["result"] == "passed"

    def test_different_name_fails(self):
        txn = _card(credit_card=CreditCard(
            card_number      = "4111111111111111",
            card_type        = "SKYCARD_ELITE",
            expiry_date      = "12/28",
            card_holder_name = "Bob Williams",
        ))
        r = check_card_holder_name(txn)
        assert r["result"] == "failed"
        assert r["rule_id"] == "CARD_HOLDER_NAME_MISMATCH"

    def test_similar_name_is_inconclusive(self):
        # bp has "Alice Johnston", card has "Alice Johnson" — similarity ≈ 0.96
        txn = _card(boarding_pass=_bp(passenger_name="Alice Johnston"))
        assert check_card_holder_name(txn)["result"] == "inconclusive"


# ---------------------------------------------------------------------------
# CREDIT_CARD Rule: Visit Limits (via check_card_visit_limit)
# ---------------------------------------------------------------------------

class TestVisitLimits:

    def test_card_within_monthly_limit_passes(self):
        # Card 4000000000007777: NEXUS_INFINITE (2/month), 1 visit used → 1 remaining
        txn = _card(credit_card=CreditCard(
            card_number      = "4000000000007777",
            card_type        = "NEXUS_INFINITE",
            expiry_date      = "12/28",
            card_holder_name = "Alice Johnson",
        ))
        assert check_card_visit_limit(txn)["result"] == "passed"

    def test_card_exceeds_monthly_limit_fails(self):
        # Card 4000000000008888: ATLAS_PREMIUM (1/month), 1 visit used → limit reached
        txn = _card(credit_card=CreditCard(
            card_number      = "4000000000008888",
            card_type        = "ATLAS_PREMIUM",
            expiry_date      = "12/28",
            card_holder_name = "Alice Johnson",
        ))
        r = check_card_visit_limit(txn)
        assert r["result"] == "failed"
        assert r["rule_id"] == "CARD_VISIT_LIMIT_EXCEEDED"


# ---------------------------------------------------------------------------
# BOOKING Rule: Booking Reference Match
# ---------------------------------------------------------------------------

class TestBookingReferenceMatch:

    def test_matching_reference_passes(self):
        # BKREF12345 exists in VALID_BOOKINGS → passes DB lookup
        txn = _booking()
        assert check_booking_reference_match(txn)["result"] == "passed"

    def test_mismatched_reference_fails(self):
        # WRONG-REF does not exist in VALID_BOOKINGS → fails DB lookup
        txn = _booking(booking_reference="WRONG-REF")
        r = check_booking_reference_match(txn)
        assert r["result"] == "failed"
        assert r["rule_id"] == "BOOKING_REFERENCE_MISMATCH"

    def test_matching_qr_payload_passes(self):
        # QR payload BKREF12345 exists in VALID_BOOKINGS → passes
        txn = AdmissionTransaction(
            transaction_id    = "TXN-QR-PASS",
            lounge_id         = "GTX-T1-VL",
            attempt_timestamp = datetime.now().isoformat(timespec="seconds"),
            guest_name        = "Alice Johnson",
            entitlement_type  = "BOOKING",
            boarding_pass     = _bp(),
            qr_code_payload   = "BKREF12345",
        )
        assert check_booking_reference_match(txn)["result"] == "passed"

    def test_mismatched_qr_payload_fails(self):
        # QR payload BK-INVALID-9999Z does not exist in VALID_BOOKINGS → fails
        txn = AdmissionTransaction(
            transaction_id    = "TXN-QR-FAIL",
            lounge_id         = "GTX-T1-VL",
            attempt_timestamp = datetime.now().isoformat(timespec="seconds"),
            guest_name        = "Alice Johnson",
            entitlement_type  = "BOOKING",
            boarding_pass     = _bp(),
            qr_code_payload   = "BK-INVALID-9999Z",
        )
        r = check_booking_reference_match(txn)
        assert r["result"] == "failed"
        assert "QR code payload" in r["details"]


# ---------------------------------------------------------------------------
# BOOKING Rule: Booking Expiry
# ---------------------------------------------------------------------------

class TestBookingExpiry:

    def test_valid_expiry_passes(self):
        # BKREF12345 has expiry_date 2027-12-31 in VALID_BOOKINGS → passes
        txn = _booking()
        assert check_booking_expiry(txn)["result"] == "passed"

    def test_expired_booking_fails(self):
        # BKREF-EXPIRED-001 has expiry_date 2025-01-01 in VALID_BOOKINGS → fails
        txn = _booking(booking_reference="BKREF-EXPIRED-001")
        r = check_booking_expiry(txn)
        assert r["result"] == "failed"
        assert r["rule_id"] == "BOOKING_EXPIRED"


# ---------------------------------------------------------------------------
# BOOKING Rule: Duplicate Booking Reference
# ---------------------------------------------------------------------------

class TestDuplicateBookingReference:

    def test_unused_reference_passes(self):
        # BKREF12345 is in VALID_BOOKINGS but not in USED_REFERENCES
        txn = _booking()
        assert check_booking_reference_duplicate(txn)["result"] == "passed"

    def test_already_used_reference_fails(self):
        # BK-20260613-4421A is seeded in mock_db.USED_REFERENCES as used today
        txn = _booking(booking_reference="BK-20260613-4421A")
        r = check_booking_reference_duplicate(txn)
        assert r["result"] == "failed"
        assert r["rule_id"] == "BOOKING_REFERENCE_ALREADY_USED"


# ---------------------------------------------------------------------------
# AIRLINE_STATUS Rule: Status Eligibility
# ---------------------------------------------------------------------------

class TestAirlineStatus:

    def test_star_gold_membership_passes(self):
        # FF-987654321 maps to STAR_GOLD in VALID_AIRLINE_MEMBERSHIPS → qualifies
        assert check_airline_status_eligibility(_airline(airline_status_id="FF-987654321"))["result"] == "passed"

    def test_skyteam_elite_plus_membership_passes(self):
        # FF-111222333 maps to SKYTEAM_ELITE_PLUS → qualifies
        assert check_airline_status_eligibility(_airline(airline_status_id="FF-111222333"))["result"] == "passed"

    def test_oneworld_emerald_membership_passes(self):
        # FF-444555666 maps to ONEWORLD_EMERALD → qualifies
        assert check_airline_status_eligibility(_airline(airline_status_id="FF-444555666"))["result"] == "passed"

    def test_ineligible_tier_fails(self):
        # FF-000000000 maps to SILVER_BASIC which is not in VALID_AIRLINE_STATUSES → fails
        r = check_airline_status_eligibility(_airline(airline_status_id="FF-000000000"))
        assert r["result"] == "failed"
        assert r["rule_id"] == "AIRLINE_STATUS_INVALID"

    def test_unrecognised_membership_id_fails(self):
        # Membership ID not in VALID_AIRLINE_MEMBERSHIPS at all → fails
        r = check_airline_status_eligibility(_airline(airline_status_id="FF-UNKNOWN-999"))
        assert r["result"] == "failed"
        assert r["rule_id"] == "AIRLINE_STATUS_INVALID"


# ---------------------------------------------------------------------------
# Integration: analyse_transaction (full service, LLM fallback forced)
# ---------------------------------------------------------------------------

class TestAnalyseTransaction:

    @pytest.fixture(autouse=True)
    def no_llm(self, monkeypatch):
        """Remove GEMINI_API_KEY in all integration tests to use deterministic fallback."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def test_all_rules_pass_returns_inconclusive(self):
        result = analyse_transaction(_booking())
        assert result["status"] == "inconclusive"
        assert result["confidence"] == "low"

    def test_booking_reference_mismatch_returns_failed(self):
        txn = _booking(booking_reference="WRONG-REF")
        result = analyse_transaction(txn)
        assert result["status"] == "failed"
        assert result["confidence"] == "high"
        assert result["failure_category"] == "BOOKING_REFERENCE_MISMATCH"

    def test_expired_booking_returns_failed(self):
        txn = _booking(booking_reference="BKREF-EXPIRED-001")
        result = analyse_transaction(txn)
        assert result["status"] == "failed"
        assert result["failure_category"] == "BOOKING_EXPIRED"

    def test_access_window_violation_returns_failed(self):
        txn = _booking(boarding_pass=_bp(hours=5))
        result = analyse_transaction(txn)
        assert result["status"] == "failed"
        assert result["failure_category"] == "ACCESS_WINDOW_VIOLATION"

    def test_card_not_eligible_for_lounge_returns_failed(self):
        txn = _card(
            lounge_id   = "GTX-T1-VL",
            credit_card = CreditCard(
                card_number      = "4222222222222222",
                card_type        = "CREST_PLUS",
                expiry_date      = "12/28",
                card_holder_name = "Alice Johnson",
            ),
        )
        result = analyse_transaction(txn)
        assert result["status"] == "failed"
        assert result["failure_category"] == "ENTITLEMENT_NOT_VALID"

    def test_airline_status_invalid_returns_failed(self):
        txn = _airline(airline_status_id="FF-000000000")
        result = analyse_transaction(txn)
        assert result["status"] == "failed"
        assert result["failure_category"] == "ENTITLEMENT_NOT_VALID"

    def test_short_circuit_stops_at_first_failure(self):
        """Rule engine returns only the first failing rule, even if later rules also fail."""
        txn = _booking(booking_reference="WRONG-REF")
        result = analyse_transaction(txn)
        assert len(result["deterministic_findings"]) == 1
        assert result["deterministic_findings"][0]["rule_id"] == "BOOKING_REFERENCE_MISMATCH"

    def test_fallback_used_when_no_api_key(self):
        txn = _booking(booking_reference="WRONG-REF")
        result = analyse_transaction(txn)
        assert result["fallback_used"] is True
        assert result["staff_guidance"]
        assert result["guest_explanation"]

    def test_masked_guest_data_always_contains_all_fields(self):
        # All three entitlement types must return the same masked_guest_data keys
        expected_keys = {
            "guest_name", "card_number", "card_holder", "card_type", "card_expiry",
            "booking_reference", "qr_code_payload", "airline_status_id",
            "boarding_pass_reference", "passenger_name",
        }
        for txn in [_booking(), _card(), _airline()]:
            result = analyse_transaction(txn)
            assert expected_keys == set(result["masked_guest_data"].keys())

    def test_masked_guest_data_nulls_non_applicable_fields(self):
        # BOOKING transaction — card fields and airline_status_id must be null
        result = analyse_transaction(_booking())
        masked = result["masked_guest_data"]
        assert masked["card_number"] is None
        assert masked["card_holder"] is None
        assert masked["card_type"] is None
        assert masked["card_expiry"] is None
        assert masked["airline_status_id"] is None

    def test_masked_guest_data_hides_full_name(self):
        result = analyse_transaction(_booking())
        masked = result["masked_guest_data"]
        assert "guest_name" in masked
        assert "Johnson" not in masked["guest_name"]

    def test_response_contains_all_required_fields(self):
        txn = _booking(booking_reference="WRONG-REF")
        result = analyse_transaction(txn)
        required = {
            "transaction_id", "status", "failure_category", "confidence",
            "deterministic_findings", "masked_guest_data", "staff_guidance",
            "guest_explanation", "requires_manual_review", "fallback_used",
        }
        assert required.issubset(result.keys())
