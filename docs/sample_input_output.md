# Sample Input and Output

All requests are submitted as `POST /analyse` with a JSON body. The service only processes transactions that were already denied at the lounge — it analyses the cause, it does not make the admission decision.

---

## Example 1 — Clear failure: booking reference not found

**Input**

```json
{
  "transaction_id": "TXN-TC-001",
  "lounge_id": "GTX-T1-VL",
  "attempt_timestamp": "2026-06-15T11:50:00",
  "guest_name": "Alice Johnson",
  "boarding_pass": {
    "passenger_name": "Alice Johnson",
    "flight_number": "EK202",
    "flight_date": "2026-06-15",
    "departure_time": "14:00:00",
    "departure_airport": "DXB",
    "destination_airport": "LHR",
    "flight_pnr": "PNR-EK202-001"
  },
  "entitlement_type": "BOOKING",
  "credit_card": null,
  "booking_reference": "WRONG-REF-001",
  "qr_code_payload": null,
  "airline_status_id": null
}
```

**Output**

```json
{
  "transaction_id": "TXN-TC-001",
  "status": "failed",
  "failure_categories": [
    "BOOKING_REFERENCE_MISMATCH"
  ],
  "confidence": "high",
  "deterministic_findings": [
    {
      "rule_id": "BOOKING_REFERENCE_MISMATCH",
      "result": "failed",
      "details": "Submitted booking reference does not match any booking in the system."
    }
  ],
  "masked_guest_data": {
    "guest_name": "A**** J******",
    "card_number": null,
    "card_holder": null,
    "card_type": null,
    "card_expiry": null,
    "booking_reference": "WR*********01",
    "qr_code_payload": null,
    "airline_status_id": null,
    "boarding_pass_reference": "PN*********01",
    "passenger_name": "A**** J******"
  },
  "staff_guidance": "The booking reference provided does not match any entry in our system. Please politely ask the guest to reconfirm their booking reference or provide alternative details such as their full name and flight number for a manual search. If no valid booking can be located, advise the guest that we cannot proceed with admission.",
  "guest_explanation": "It appears the booking reference you provided could not be found in our system. Could you please double-check your reference number and provide it again, or share your full name and flight details so we can attempt to locate your reservation? We're happy to help once we can verify your booking.",
  "requires_manual_review": false,
  "fallback_used": false
}
```

**Key points**

- `status` is `failed` and `confidence` is `high` because a deterministic rule identified the cause.
- `requires_manual_review` is `false` — no human review is needed when a clear reason is found.
- The rule engine short-circuits on the first failed rule; subsequent rules are not evaluated.
- `masked_guest_data` contains masked versions of all sensitive fields;
---

## Example 2 — Multiple inconclusive findings: name mismatches on both guest and card

This case demonstrates the engine collecting multiple inconclusive results. Unlike a `failed` result, inconclusive findings do not cause short-circuiting — all rules run and every inconclusive result is collected.

**Input**

```json
{
  "transaction_id": "TXN-MULTI-INC-001",
  "lounge_id": "GTX-T1-VL",
  "attempt_timestamp": "2026-06-15T11:50:00",
  "guest_name": "Jon Smith",
  "boarding_pass": {
    "passenger_name": "John Smith",
    "flight_number": "EK202",
    "flight_date": "2026-06-15",
    "departure_time": "14:00:00",
    "departure_airport": "DXB",
    "destination_airport": "LHR",
    "flight_pnr": "PNR-EK202-001"
  },
  "entitlement_type": "CREDIT_CARD",
  "credit_card": {
    "card_number": "4111111111111111",
    "card_type": "SKYCARD_ELITE",
    "expiry_date": "12/28",
    "card_holder_name": "Jon Smith"
  },
  "booking_reference": null,
  "qr_code_payload": null,
  "airline_status_id": null
}
```

**Output**

```json
{
    "transaction_id": "TXN-MULTI-INC-001",
    "status": "inconclusive",
    "failure_categories": [
        "GUEST_NAME_MISMATCH",
        "CARD_HOLDER_NAME_MISMATCH"
    ],
    "confidence": "low",
    "deterministic_findings": [
        {
            "rule_id": "GUEST_NAME_MISMATCH",
            "result": "inconclusive",
            "details": "Guest name is similar but not identical to the name on the boarding pass."
        },
        {
            "rule_id": "CARD_HOLDER_NAME_MISMATCH",
            "result": "inconclusive",
            "details": "Card holder name is similar but not identical to the name on the boarding pass."
        }
    ],
    "masked_guest_data": {
        "guest_name": "J** S****",
        "card_number": "************1111",
        "card_holder": "J** S****",
        "card_type": "SKYCARD_ELITE",
        "card_expiry": "**/28",
        "booking_reference": null,
        "qr_code_payload": null,
        "airline_status_id": null,
        "boarding_pass_reference": "PN*********01",
        "passenger_name": "J*** S****"
    },
    "staff_guidance": "Please note a slight discrepancy between the guest's name and the boarding pass. You'll also find the card holder's name is similar but not identical to the boarding pass. For both issues, kindly request to see a valid photo ID to verify the guest's identity and, if applicable, the physical card along with an ID matching the card holder's name.",
    "guest_explanation": "Thank you for your patience. To complete your entry, we just need to verify a couple of details. We've noticed a minor difference between the name on your boarding pass and the name provided, as well as a slight variation in the cardholder's name. Could you please present a photo ID for verification, and if you are using a payment card for entry, the physical card itself?",
    "requires_manual_review": true,
    "fallback_used": false
}
```

**Key points**

- Both `GUEST_NAME_MISMATCH` and `CARD_HOLDER_NAME_MISMATCH` are inconclusive because `"JON SMITH"` vs `"JOHN SMITH"` has a similarity score of ~0.95, which is above the 0.90 threshold but not an exact match.
- `deterministic_findings` contains both findings — the engine collects all inconclusive results rather than stopping at the first.
- `failure_categories` includes both rule categories.
- `requires_manual_review` is `true` — a staff member must compare identity documents.

---

## Example 3 — Uncertain: all rules pass but admission was denied

This case occurs when the transaction appears fully valid according to all rules, but the guest was still denied at the lounge. No cause can be identified automatically.

**Input**

```json
{
  "transaction_id": "TXN-TC-007",
  "lounge_id": "GTX-T1-VL",
  "attempt_timestamp": "2026-06-15T11:50:00",
  "guest_name": "Alice Johnson",
  "boarding_pass": {
    "passenger_name": "Alice Johnson",
    "flight_number": "EK202",
    "flight_date": "2026-06-15",
    "departure_time": "14:00:00",
    "departure_airport": "DXB",
    "destination_airport": "LHR",
    "flight_pnr": "PNR-EK202-001"
  },
  "entitlement_type": "BOOKING",
  "credit_card": null,
  "booking_reference": "BKREF12345",
  "qr_code_payload": null,
  "airline_status_id": null
}
```

**Output**

```json
{
    "transaction_id": "TXN-TC-007",
    "status": "inconclusive",
    "failure_categories": [
        "UNCERTAIN"
    ],
    "confidence": "low",
    "deterministic_findings": [
        {
            "rule_id": "UNKNOWN_FAILURE_REASON",
            "result": "inconclusive",
            "details": "The admission attempt failed but no deterministic rule was able to identify a likely cause."
        }
    ],
    "masked_guest_data": {
        "guest_name": "A**** J******",
        "card_number": null,
        "card_holder": null,
        "card_type": null,
        "card_expiry": null,
        "booking_reference": "BK******45",
        "qr_code_payload": null,
        "airline_status_id": null,
        "boarding_pass_reference": "PN*********01",
        "passenger_name": "A**** J******"
    },
    "staff_guidance": "The admission attempt failed, but the system could not determine a specific reason. Please manually verify the guest's lounge access credentials and a valid photo ID to confirm their eligibility for entry.",
    "guest_explanation": "We're sorry, but our system encountered an unexpected issue and was unable to process your admission at this time. To help us resolve this for you, please provide your lounge access credentials and a valid photo ID so we can verify your eligibility manually.",
    "requires_manual_review": true,
    "fallback_used": false
}
```

**Key points**

- `status` is `inconclusive` and `confidence` is `low` — no rule failed or returned inconclusive, so no cause could be determined.
- `failure_categories` contains `UNCERTAIN` — a synthetic category assigned only when all rules pass on a denied transaction.
- A synthetic `UNKNOWN_FAILURE_REASON` finding is injected by the rule engine to signal this state to the LLM.
- `requires_manual_review` is `true` — a staff member must investigate the denial reason manually.
