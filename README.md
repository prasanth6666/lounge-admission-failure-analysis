# Lounge Admission Failure Analysis Service

## How to Run the Service

**1. Install dependencies**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Configure the API key (optional)**

Create a `.env` file in the project root:
```
GEMINI_API_KEY=your_api_key_here
```

If this file is absent or the key is not set, the service runs in fallback mode (see below).

**3. Start the server**
```bash
uvicorn main:app --reload
```

The service will be available at `http://localhost:8000`.

**4. Submit a transaction**
```bash
POST http://localhost:8000/analyse
Content-Type: application/json
```

**5. Run tests**
```bash
pytest tests/ -v
```

---

## Assumptions Made

- The service analyses transactions that have **already been denied** — it is a post-hoc failure analysis tool, not an admission gate that makes the access decision.
- All data stores (`VALID_BOOKINGS`, `VALID_AIRLINE_MEMBERSHIPS`, `CARD_USAGE`, `USED_REFERENCES`) are simulated in-memory in `mock_db.py`. No external database is used.

**Boarding Pass**

- The passenger is expected to provide a boarding pass containing: passenger name, flight number, flight date, departure airport, destination airport, and flight PNR.
- If any of these fields are missing or empty, the boarding pass is considered invalid and access is denied.

**Entitlement Types**

- Lounge access can be obtained through one of three entitlement types: Credit Card, Lounge Booking, or Airline Membership Status.

**Credit Card**

- Not all card types provide lounge access — only specific card types are eligible.
- A card type may only be eligible for specific lounges, not all lounges system-wide.
- Cards must not be expired at the time of the access attempt.
- The cardholder name on the card must match the passenger name on the boarding pass.
- Cards may have visit limits per monthly or quarterly period, beyond which access is denied.

**Lounge Booking**

- Lounge bookings are stored in the booking database and can be looked up by booking reference.
- Booking references are unique.
- Bookings have an expiry date, retrieved from the database — not submitted by the guest.
- Each booking reference is valid for **single use per day**. References already used today are tracked in `USED_REFERENCES`.

**Airline Membership**

- Airline membership IDs are stored in the airline membership database and can be looked up to retrieve the member's tier.
- Only specific membership tiers qualify for complimentary lounge access (`STAR_GOLD`, `SKYTEAM_ELITE_PLUS`, `ONEWORLD_EMERALD`).
- Airline status tiers are retrieved from the database by looking up the submitted membership ID in `VALID_AIRLINE_MEMBERSHIPS`.

**Name Matching**

- Names may contain different capitalisations, extra spaces, or accented characters. Names are normalised before comparison.
- Name matching uses Python's `difflib.SequenceMatcher` to handle spelling variations. A similarity score of 0.90 or above is treated as inconclusive (similar but not identical); below 0.90 is a definitive mismatch.

**Access Window**

- The lounge access window is **3 hours before departure**. Access attempts before or after this window are denied.
- Flights are assumed to depart on time. The access window is calculated against the scheduled departure time on the boarding pass. Flight delays are not accounted for — a delayed flight could cause the system to incorrectly report the flight as already departed.

**Manual Review**

- Failed rules indicate a deterministic rejection reason with high confidence.
- Inconclusive rules indicate that the check could not be completed with sufficient confidence to determine the rejection reason.
- Manual review is required when one or more rules return an inconclusive result and no deterministic failure has been identified.
- If all rules pass but the admission attempt is still reported as failed, the transaction is classified as `UNCERTAIN` and flagged for manual review, as no deterministic rule was able to identify the cause.
- The rule engine **short-circuits on the first failed rule**, returning that result immediately without running subsequent rules.

---

## Rules Implemented

Rules are grouped into common rules (run for every entitlement type) and entitlement-specific rules.

### Common Rules

| Rule ID | What it checks |
|---|---|
| `INVALID_BOARDING_PASS` | Passenger name, flight number, departure and destination airports, and flight PNR are all present and non-empty. |
| `ACCESS_WINDOW_VIOLATION` | The access attempt falls within the 3-hour window before the flight departure time. Attempts too early or after departure fail. |
| `GUEST_NAME_MISMATCH` | The submitted guest name matches the passenger name on the boarding pass. Scores below 0.90 similarity fail; scores between 0.90 and 1.0 are inconclusive. |

### Credit Card Entitlement

| Rule ID | What it checks |
|---|---|
| `CARD_NOT_ELIGIBLE_FOR_LOUNGE` | The card type is eligible for the specific lounge being accessed. |
| `CARD_EXPIRY_FORMAT_INVALID` | The expiry date is in valid MM/YY format with a valid month (01–12). |
| `CARD_EXPIRED` | The card's expiry date has not passed. |
| `CARD_HOLDER_NAME_MISMATCH` | The card holder name matches the boarding pass passenger name (same similarity threshold as guest name). |
| `CARD_VISIT_LIMIT_EXCEEDED` | The card has not exceeded its permitted number of lounge visits for the current monthly or quarterly period. |

### Booking Entitlement

| Rule ID | What it checks |
|---|---|
| `BOOKING_REFERENCE_MISMATCH` | The submitted booking reference or QR code payload exists in `VALID_BOOKINGS`. |
| `BOOKING_EXPIRED` | The booking's expiry date (from `VALID_BOOKINGS`) has not passed. |
| `BOOKING_REFERENCE_ALREADY_USED` | The booking reference has not already been used for lounge access today. |

### Airline Status Entitlement

| Rule ID | What it checks |
|---|---|
| `AIRLINE_STATUS_INVALID` | The membership ID exists in `VALID_AIRLINE_MEMBERSHIPS` and the resolved tier is in the set of qualifying statuses (`STAR_GOLD`, `SKYTEAM_ELITE_PLUS`, `ONEWORLD_EMERALD`). |

---

## How Test Data Was Generated

Test data is hand-crafted inside `tests/test_rules.py` using four builder functions:

- `_bp(**overrides)` — builds a valid `BoardingPass` dict with a departure 2 hours from now by default.
- `_card(**overrides)` — builds a valid `CREDIT_CARD` `AdmissionTransaction` using a `SKYCARD_ELITE` card eligible for lounge `GTX-T1-VL`.
- `_booking(**overrides)` — builds a valid `BOOKING` `AdmissionTransaction` with booking reference `BKREF12345`.
- `_airline(**overrides)` — builds a valid `AIRLINE_STATUS` `AdmissionTransaction` with membership ID `FF-987654321`.

Each test overrides one or more fields on the default to target a specific failure scenario. The `mock_db.py` is pre-seeded with matching data — expired bookings, used references, cards that have hit their visit limits, and membership IDs with both qualifying and non-qualifying tiers — so tests can exercise real failure paths against the mock store without any external setup.

---

## How LLM Integration Works

The service uses **Google Gemini** (`gemini-2.5-flash`) via the `google-generativeai` package to generate two pieces of human-readable output for each failed transaction:

- **`staff_guidance`** — a brief operational note for lounge staff describing the failure and the steps they should take.
- **`guest_explanation`** — a polite, guest-facing explanation describing the issue and what the guest can do to resolve it.

The prompt sent to Gemini includes the transaction ID, failure categories, and the details of every failed and inconclusive rule finding. Gemini is instructed to address every finding (not just the first), provide specific next steps per failure type, and respond in JSON only.

If Gemini wraps the JSON in markdown code fences, the service strips them before parsing. If the parsed response is missing either required field, the call is treated as a failure and the fallback is used.

---

## How Fallback Works When the LLM Is Unavailable

The fallback is triggered in two situations:

1. **`GEMINI_API_KEY` is not set** — the service skips the API call entirely and uses the fallback immediately.
2. **The API call fails** — any exception during the Gemini call (network error, malformed response, missing fields) is caught and the fallback is used instead.

The fallback (`_build_fallback` in `llm_client.py`) generates deterministic text without any external call:

- Staff guidance is constructed from the first finding's details, with a note to perform manual verification if any findings are inconclusive.
- Guest explanation is built from a lookup table (`_GUEST_MESSAGES`) keyed by `rule_id`, mapping each known failure type to a pre-written guest-facing message.

The response always includes a `fallback_used` field — `true` when the fallback was used, `false` when the LLM responded successfully — so callers can distinguish between LLM-generated and deterministic output.
