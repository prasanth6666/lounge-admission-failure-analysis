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

COMMON_RULES = [
    check_boarding_pass_validity,
    check_access_window,
    check_guest_name_against_boarding_pass,
]

ENTITLEMENT_RULES = {
    "CREDIT_CARD":    [check_card_eligibility, check_card_expiry, check_card_holder_name, check_card_visit_limit],
    "BOOKING":        [check_booking_reference_match, check_booking_expiry, check_booking_reference_duplicate],
    "AIRLINE_STATUS": [check_airline_status_eligibility],
}

RULE_TO_CATEGORY = {
    "INVALID_BOARDING_PASS":        "BOARDING_PASS_INVALID",
    "ACCESS_WINDOW_VIOLATION":      "ACCESS_WINDOW_VIOLATION",

    "CARD_NOT_ELIGIBLE_FOR_LOUNGE":  "ENTITLEMENT_NOT_VALID",
    "CARD_EXPIRY_FORMAT_INVALID":    "ENTITLEMENT_NOT_VALID",
    "CARD_EXPIRED":                  "ENTITLEMENT_NOT_VALID",
    "AIRLINE_STATUS_INVALID":        "ENTITLEMENT_NOT_VALID",

    "BOOKING_REFERENCE_MISMATCH":   "BOOKING_REFERENCE_MISMATCH",
    "BOOKING_EXPIRED":              "BOOKING_EXPIRED",

    "BOOKING_REFERENCE_ALREADY_USED": "DUPLICATE_ACCESS",
    "CARD_VISIT_LIMIT_EXCEEDED":      "DUPLICATE_ACCESS",

    "CARD_HOLDER_NAME_MISMATCH":    "CARD_HOLDER_NAME_MISMATCH",
    "GUEST_NAME_MISMATCH":          "GUEST_NAME_MISMATCH",
}


def _collect_categories(findings: list) -> list:
    categories = []
    for finding in findings:
        category = RULE_TO_CATEGORY.get(finding["rule_id"], "UNKNOWN")
        if category not in categories:
            categories.append(category)
    return categories


def run_rules(transaction) -> tuple[list, list, bool]:
    """
    Runs all rules and returns:
      - findings               : all failed + inconclusive findings
      - failure_categories     : unique categories derived from all returned findings
      - requires_manual_review : True only when inconclusive findings exist and no failed findings
    """
    rules_to_run = COMMON_RULES + ENTITLEMENT_RULES.get(transaction.entitlement_type, [])

    inconclusive = []

    for rule_fn in rules_to_run:
        result = rule_fn(transaction)
        if result is None or result["result"] == "passed":
            continue
        if result["result"] == "failed":
            return [result], _collect_categories([result]), False
        if result["result"] == "inconclusive":
            inconclusive.append(result)

    if inconclusive:
        return inconclusive, _collect_categories(inconclusive), True

    return (
        [{
            "rule_id": "UNKNOWN_FAILURE_REASON",
            "result":  "inconclusive",
            "details": (
                "The admission attempt failed but no deterministic rule "
                "was able to identify a likely cause."
            ),
        }],
        ["UNCERTAIN"],
        True,
    )
