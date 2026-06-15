# Automated Test Suite

The test suite is in `tests/test_rules.py` and contains **50 tests across 15 test classes**. Run it with:

```bash
pytest tests/ -v
```

Tests are split into two layers: unit tests that call one rule function at a time, and integration tests that run the full service pipeline end-to-end.

---

## How Unit Tests Are Structured

Four builder functions create a fully valid baseline transaction that passes every rule by default:

| Builder | Entitlement type | What it creates |
|---|---|---|
| `_bp(hours=2)` | — | Boarding pass with departure `hours` hours from now |
| `_booking()` | `BOOKING` | Valid booking using reference `BKREF12345` |
| `_card()` | `CREDIT_CARD` | SKYCARD_ELITE card, expiry 12/28, Alice Johnson |
| `_airline()` | `AIRLINE_STATUS` | Membership `FF-987654321` (STAR_GOLD) |

Each unit test overrides exactly one field on the baseline to trigger a specific failure. Everything else remains valid so the test isolates only one rule at a time.

---

## Unit Test Classes

### Boarding Pass Validity (5 tests)

| Condition | Expected |
|---|---|
| All fields present and non-empty | Passed |
| `passenger_name` is empty | Failed — `INVALID_BOARDING_PASS` |
| `flight_number` is empty | Failed — `INVALID_BOARDING_PASS` |
| `departure_airport` is empty | Failed — `INVALID_BOARDING_PASS` |
| `flight_pnr` is empty | Failed — `INVALID_BOARDING_PASS` |

### Access Window (3 tests)

| Condition | Expected |
|---|---|
| Departure 2 hours away | Passed |
| Departure 5 hours away (too early) | Failed — `ACCESS_WINDOW_VIOLATION` |
| Departure 1 hour in the past (already departed) | Failed — `ACCESS_WINDOW_VIOLATION` |

### Guest Name Match (3 tests)

| Condition | Expected |
|---|---|
| Guest name exactly matches boarding pass | Passed |
| Completely different name ("Bob Williams" vs "Alice Johnson") | Failed — `GUEST_NAME_MISMATCH` |
| Similar but not identical ("Alice Johnston" vs "Alice Johnson", ~0.96) | Inconclusive — `GUEST_NAME_MISMATCH` |

### Card Eligibility (2 tests)

| Condition | Expected |
|---|---|
| SKYCARD_ELITE at GTX-T1-VL (eligible) | Passed |
| CREST_PLUS at GTX-T1-VL (not eligible for this lounge) | Failed — `CARD_NOT_ELIGIBLE_FOR_LOUNGE` |

### Card Expiry (3 tests)

| Condition | Expected |
|---|---|
| Expiry `12/28` (valid future date) | Passed |
| Expiry `01/23` (past date) | Failed — `CARD_EXPIRED` |
| Expiry `1228` (wrong format, no slash) | Failed — `CARD_EXPIRY_FORMAT_INVALID` |

### Card Holder Name Match (3 tests)

| Condition | Expected |
|---|---|
| Card holder name exactly matches boarding pass | Passed |
| Completely different name ("Bob Williams" on card) | Failed — `CARD_HOLDER_NAME_MISMATCH` |
| Similar but not identical ("Alice Johnson" card vs "Alice Johnston" on boarding pass, ~0.96) | Inconclusive — `CARD_HOLDER_NAME_MISMATCH` |

### Visit Limits (2 tests)

| Condition | Expected |
|---|---|
| NEXUS_INFINITE card — limit 2/month, 1 visit used | Passed |
| ATLAS_PREMIUM card — limit 1/month, 1 visit used (limit reached) | Failed — `CARD_VISIT_LIMIT_EXCEEDED` |

### Booking Reference Match (4 tests)

| Condition | Expected |
|---|---|
| Reference `BKREF12345` exists in DB | Passed |
| Reference `WRONG-REF` not in DB | Failed — `BOOKING_REFERENCE_MISMATCH` |
| QR payload `BKREF12345` exists in DB | Passed |
| QR payload `BK-INVALID-9999Z` not in DB | Failed — `BOOKING_REFERENCE_MISMATCH` |

### Booking Expiry (2 tests)

| Condition | Expected |
|---|---|
| `BKREF12345` — expiry `2027-12-31` | Passed |
| `BKREF-EXPIRED-001` — expiry `2025-01-01` | Failed — `BOOKING_EXPIRED` |

### Duplicate Booking Reference (2 tests)

| Condition | Expected |
|---|---|
| `BKREF12345` — not in used references | Passed |
| `BK-20260613-4421A` — already used today | Failed — `BOOKING_REFERENCE_ALREADY_USED` |

### Airline Status Eligibility (5 tests)

| Condition | Expected |
|---|---|
| `FF-987654321` → STAR_GOLD | Passed |
| `FF-111222333` → SKYTEAM_ELITE_PLUS | Passed |
| `FF-444555666` → ONEWORLD_EMERALD | Passed |
| `FF-000000000` → SILVER_BASIC (non-qualifying tier) | Failed — `AIRLINE_STATUS_INVALID` |
| `FF-UNKNOWN-999` — ID not in DB | Failed — `AIRLINE_STATUS_INVALID` |

---

## Boundary Test Classes

These pin exact threshold behaviour — where a value sitting right at the edge of a rule's condition could go either way.

| Condition | Expected | Why |
|---|---|---|
| Departure exactly 3 hours away | Passed | Window check is `window_open <= now`; boundary is inclusive |
| Card expiry set to current month and year | Passed | Expiry check is `month >= today.month`; card is valid through end of month |
| "JOHN SMITH" vs "JOHN SMYTH" — similarity exactly 0.90 | Inconclusive | Threshold is `>= 0.90`; exactly 0.90 is inconclusive, not failed |
| "ALICIA JOHNSON" vs "ALICE JOHNSON" — similarity ≈ 0.889 | Failed | Below threshold is a definitive mismatch |

---

## Integration Test Class (12 tests)

`TestAnalyseTransaction` calls `analyse_transaction()` end-to-end — all rules, masking, and LLM fallback run together as a single pipeline. A `monkeypatch` fixture removes the Gemini API key before every test so the fallback always fires, keeping tests deterministic and independent of external APIs.

| What is tested | Expected |
|---|---|
| Valid booking, all rules pass | `status: inconclusive`, `confidence: low` (UNCERTAIN case) |
| Wrong booking reference | `status: failed`, `BOOKING_REFERENCE_MISMATCH` in categories |
| Expired booking | `status: failed`, `BOOKING_EXPIRED` in categories |
| Access too early (5 hours before departure) | `status: failed`, `ACCESS_WINDOW_VIOLATION` in categories |
| Ineligible card type for lounge | `status: failed`, `ENTITLEMENT_NOT_VALID` in categories |
| Non-qualifying airline tier | `status: failed`, `ENTITLEMENT_NOT_VALID` in categories |
| Short-circuit: wrong booking reference | Exactly 1 finding returned, rule is `BOOKING_REFERENCE_MISMATCH` |
| No API key set | `fallback_used: true`; both `staff_guidance` and `guest_explanation` are non-empty |
| All three entitlement types submitted | `masked_guest_data` always has exactly 10 keys |
| Booking transaction (no card or airline data) | Card fields and `airline_status_id` are `null` in masked output |
| Booking transaction name masking | Masked `guest_name` does not contain the real surname |
| Wrong booking reference (full response check) | Response contains all 10 required top-level fields |
