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
- Only failed transactions are submitted as input. Successful lounge admissions are not processed by this service.
- All data stores (`VALID_BOOKINGS`, `VALID_AIRLINE_MEMBERSHIPS`, `CARD_USAGE`, `USED_REFERENCES`) are simulated in-memory in `mock_db.py`. No external database is used.

**Boarding Pass**

- The passenger is expected to provide a boarding pass containing: passenger name, flight number, flight date, departure airport, destination airport, and flight PNR.
- If any of these fields are missing or empty, the boarding pass is considered invalid and access is denied.

**Entitlement Types**

- Lounge access can be obtained through one of three entitlement types: Credit Card, Lounge Booking, or Airline Membership Status.
- The request payload always includes all optional entitlement fields (`credit_card`, `booking_reference`, `qr_code_payload`, `airline_status_id`). Fields not applicable to the submitted entitlement type are set to `null` at the top level. Sending a partial `credit_card` object with null inner fields is not supported — the `CreditCard` model requires all four fields to be non-null strings when the object is provided.

**Request Validation**

The following errors are caught by Pydantic before any rule runs and return a `422 Unprocessable Entity`:

- `entitlement_type` must be one of `CREDIT_CARD`, `BOOKING`, or `AIRLINE_STATUS`. Any other value is rejected.
- If `entitlement_type` is `CREDIT_CARD`, the `credit_card` object must be present with all four fields (`card_number`, `card_type`, `expiry_date`, `card_holder_name`) as non-null strings.
- If `entitlement_type` is `BOOKING`, at least one of `booking_reference` or `qr_code_payload` must be provided. Both being `null` is rejected.
- If `entitlement_type` is `AIRLINE_STATUS`, `airline_status_id` must be present.

If all three entitlement fields are populated but only one `entitlement_type` is declared, the extra fields are accepted but ignored — the rule engine only evaluates rules for the declared type.

**Credit Card**

- Not all card types provide lounge access — only specific card types are eligible.
- A card type may only be eligible for specific lounges, not all lounges system-wide.
- Cards must not be expired at the time of the access attempt. Expiry dates are expected in `MM/YY` format — an unrecognisable format is treated as a data error, distinct from a genuinely expired card.
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

Rules are grouped into common rules (executed for every entitlement type) and entitlement-specific rules.

### Rule Outcomes

Each rule can return one of the following outcomes:

- **Passed** — Validation succeeded.
- **Failed** — A deterministic rejection reason was identified.
- **Inconclusive** — The validation could not be completed with sufficient confidence and may require manual review.

### Rule Evaluation Strategy

Rules are evaluated in priority order. The engine returns the first deterministic failure encountered. If no rule fails but one or more rules are inconclusive, the transaction is flagged for manual review.

### Name Matching Rules

Name matching rules use a similarity threshold of 0.90 after normalisation (case-insensitive comparison, whitespace normalisation, and accent removal).

- Exact match → Passed
- Similarity ≥ 0.90 but not identical → Inconclusive
- Similarity < 0.90 → Failed

### Common Rules

| Rule ID | What it checks |
|---|---|
| `INVALID_BOARDING_PASS` | Passenger name, flight number, departure airport, destination airport, and flight PNR are present and non-empty. |
| `ACCESS_WINDOW_VIOLATION` | The access attempt falls within the configured lounge access window before flight departure. Attempts made too early or after departure fail validation. |
| `GUEST_NAME_MISMATCH` | The submitted guest name matches the passenger name on the boarding pass. |

### Credit Card Entitlement

| Rule ID | What it checks |
|---|---|
| `CARD_NOT_ELIGIBLE_FOR_LOUNGE` | The submitted card type is eligible for the requested lounge. |
| `CARD_EXPIRY_FORMAT_INVALID` | The card expiry date is in valid MM/YY format and contains a valid month value (01–12). |
| `CARD_EXPIRED` | The card has not expired. |
| `CARD_HOLDER_NAME_MISMATCH` | The card holder name matches the passenger name on the boarding pass. |
| `CARD_VISIT_LIMIT_EXCEEDED` | The card has not exceeded its permitted complimentary lounge visit limit for the current entitlement period. |

### Booking Entitlement

| Rule ID | What it checks |
|---|---|
| `BOOKING_REFERENCE_MISMATCH` | The submitted booking reference or QR code payload exists in the booking repository. |
| `BOOKING_EXPIRED` | The booking has not expired. |
| `BOOKING_REFERENCE_ALREADY_USED` | The booking reference has not already been used for lounge access on the current day. |

### Airline Status Entitlement

| Rule ID | What it checks |
|---|---|
| `AIRLINE_STATUS_INVALID` | The airline membership ID exists in the membership repository and the associated tier qualifies for complimentary lounge access. |

---




## How Test Data Was Generated

See [docs/test_suite.md](docs/test_suite.md) for the full list of all 50 automated tests, what each one covers, and how the integration tests work.

### Mock Datasets

Mock datasets were created in `mock_db.py` to simulate the external systems the service depends on:

- **Card entitlement repository** — card types and the specific lounges each is eligible to access, defined in `config.py` under `CARD_LOUNGE_ELIGIBILITY`.
- **Booking repository** (`VALID_BOOKINGS`) — booking references with their expiry dates, covering valid, expired, and already-used scenarios.
- **Airline membership repository** (`VALID_AIRLINE_MEMBERSHIPS`) — membership IDs mapped to their tier, including both qualifying and non-qualifying tiers.
- **Card usage history** (`CARD_USAGE`) — per-card visit records used to enforce monthly and quarterly visit limits.
- **Previously used booking references** (`USED_REFERENCES`) — references already consumed today, used to detect duplicate access attempts.

### Positive Test Cases

Positive scenarios were created to verify that valid transactions are not incorrectly rejected:

- Valid boarding pass with all required fields present
- Eligible credit card with a valid expiry date and matching cardholder name
- Active booking reference that exists, has not expired, and has not been used today
- Valid airline membership with a qualifying tier
- Access attempt within the permitted time window before departure

In `tests/test_rules.py`, four builder functions produce valid baseline transactions that pass all rules by default — `_bp()`, `_card()`, `_booking()`, and `_airline()`. Each unit test then overrides one or more fields on the baseline to isolate a specific failure.

### Negative Test Cases

Negative test cases were created for each validation rule to verify that the correct failure is identified and reported:

- Missing or empty boarding pass fields
- Access attempt outside the permitted time window
- Card type not eligible for the requested lounge
- Card expiry date in an unrecognised format
- Expired card
- Booking reference not found in the system
- Expired booking
- Booking reference already used today
- Card visit limit exceeded for the current period
- Airline membership tier that does not qualify for lounge access
- Guest name or card holder name that does not match the boarding pass

### Boundary Test Cases

Boundary conditions were included to verify behaviour at the edges of each rule's threshold:

| Condition | Expected result | Reason |
|---|---|---|
| Access attempt exactly at window opening time (departure 3 hours away) | Passes | Window check is `window_open <= now`, boundary is inclusive |
| Card expiry set to the current month | Passes | Expiry check is `month >= today.month`, card is valid through end of month |
| Name similarity exactly at 0.90 (`JOHN SMITH` vs `JOHN SMYTH`) | Inconclusive | Threshold check is `similarity >= 0.90`, so exactly 0.90 is inconclusive not failed |
| Name similarity just below 0.90 (`ALICIA JOHNSON` vs `ALICE JOHNSON` ≈ 0.889) | Failed | Below threshold is a definitive mismatch |
| Card visit count equal to the configured limit | Failed | Limit check is `visits >= limit`, equal to limit means exceeded |

### Manual Review Scenarios

Inconclusive outcomes were created to verify that the service correctly flags transactions for manual review rather than issuing a deterministic rejection:

- Guest name or card holder name that is similar but not identical to the boarding pass name — `difflib` similarity ≥ 0.90 but not an exact match
- A transaction where all rules pass but the admission was still denied — the `UNCERTAIN` case — which produces a synthetic `UNKNOWN_FAILURE_REASON` finding and triggers a manual review flag

### Synthetic Data

All names, card numbers, booking references, and membership identifiers used in test data are artificially generated and do not represent real customer data.

### API Test Payloads (`test_data/`)

The `test_data/` directory contains 14 hand-crafted JSON payloads for live API testing against the running service. Each file can be submitted directly to `POST /analyse` and targets a specific rule or outcome.

| File | Scenario | Rule triggered | Expected outcome |
|---|---|---|---|
| `tc_01_booking_reference_mismatch.json` | Booking reference not found in the system | `BOOKING_REFERENCE_MISMATCH` | Failed |
| `tc_02_booking_expired.json` | Booking reference exists but has expired | `BOOKING_EXPIRED` | Failed |
| `tc_03_booking_already_used.json` | Booking reference already used today | `BOOKING_REFERENCE_ALREADY_USED` | Failed |
| `tc_04_card_not_eligible_for_lounge.json` | Card type not eligible for the requested lounge | `CARD_NOT_ELIGIBLE_FOR_LOUNGE` | Failed |
| `tc_05_airline_status_not_qualifying.json` | Airline membership tier does not qualify | `AIRLINE_STATUS_INVALID` | Failed |
| `tc_06_inconclusive_guest_name_similar.json` | Guest name similar but not identical to boarding pass | `GUEST_NAME_MISMATCH` | Inconclusive |
| `tc_07_uncertain_all_rules_pass.json` | All rules pass but admission was denied | `UNKNOWN_FAILURE_REASON` | Uncertain |
| `tc_08_invalid_boarding_pass.json` | Boarding pass missing a required field (flight PNR is empty) | `INVALID_BOARDING_PASS` | Failed |
| `tc_09_access_window_too_early.json` | Access attempt made more than 3 hours before departure | `ACCESS_WINDOW_VIOLATION` | Failed |
| `tc_10_guest_name_mismatch_failed.json` | Guest name completely different from boarding pass | `GUEST_NAME_MISMATCH` | Failed |
| `tc_11_card_expiry_format_invalid.json` | Card expiry date is not in MM/YY format | `CARD_EXPIRY_FORMAT_INVALID` | Failed |
| `tc_12_card_expired.json` | Card has expired | `CARD_EXPIRED` | Failed |
| `tc_13_card_holder_name_mismatch_failed.json` | Card holder name completely different from boarding pass | `CARD_HOLDER_NAME_MISMATCH` | Failed |
| `tc_14_card_visit_limit_exceeded.json` | Card has already reached its monthly visit limit | `CARD_VISIT_LIMIT_EXCEEDED` | Failed |

**Time sensitivity:** Most payloads use a `departure_time` of `14:00:00`, making the access window valid between `11:00` and `14:00`. Submitting outside that window triggers `ACCESS_WINDOW_VIOLATION` instead of the intended rule. Each file includes a `_note` field explaining its time constraint. The exception is `tc_08` — `INVALID_BOARDING_PASS` fires before the access window check and is unaffected by time.

---


## Design Decisions

See [docs/design_decisions.md](docs/design_decisions.md) for a detailed explanation of the key architectural choices made in this service.

---

## How LLM Integration Works

The service uses a two-stage approach. First, the deterministic rule engine runs all checks and identifies the failure reason(s) — this is the analytical step. **Google Gemini** (`gemini-2.5-flash`) is then used purely as a language layer: it takes the structured rule findings already produced by the engine and converts them into human-readable guidance. The LLM does not determine the failure reason or make any admission decision.

The output Gemini generates for each transaction is:

- **`staff_guidance`** — a brief operational note for lounge staff describing the failure and the steps they should take.
- **`guest_explanation`** — a polite, guest-facing explanation describing the issue and what the guest can do to resolve it.

The prompt sent to Gemini contains only the human-readable details of all failed and inconclusive rule findings — no transaction ID, rule codes, or category identifiers are included. When a deterministic failure is present there is always exactly one finding; when findings are inconclusive there may be several, and Gemini is instructed to address all of them. Gemini is also instructed not to mention technical identifiers in its output, to provide specific next steps per failure type, and to respond in JSON only.

When no rule can identify a cause (the `UNCERTAIN` case), a synthetic inconclusive finding is included in the prompt indicating that no deterministic reason was found. Gemini is expected to advise staff to perform a manual review.

**No sensitive data is sent to Gemini.** Rule finding details are generic descriptions (e.g. "Card holder name does not match the boarding pass") and never include actual card numbers, cardholder names, booking references, or membership IDs. Guest data masking is a separate step that produces `masked_guest_data` in the API response and is not part of the LLM prompt.

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
