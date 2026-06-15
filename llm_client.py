import os
import json


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(failed_findings: list, inconclusive_findings: list) -> str:
    failed_text = "\n".join(
        f"  - {f['details']}" for f in failed_findings
    )
    inconclusive_text = "\n".join(
        f"  - {f['details']}" for f in inconclusive_findings
    )

    return f"""
You are an airport lounge operations assistant helping staff handle a failed admission.

Failed checks:
{failed_text if failed_text else "  None"}

Inconclusive checks (could not be fully verified):
{inconclusive_text if inconclusive_text else "  None"}

Your task:
1. Write a brief staff guidance note (2-3 sentences) covering ALL the issues above, with clear next steps the staff should take for each issue.
2. Write a polite guest-facing explanation (2-3 sentences) covering ALL the issues above, with clear next steps the guest should take to resolve each issue.

Rules:
- Address every failure and inconclusive item — do not focus on just one.
- Next steps must be specific to the failure reason (e.g. for an expired card: advise the guest to use an eligible card; for a name mismatch: ask for a photo ID; for visit limit exceeded: advise the guest to purchase a day pass).
- Staff guidance should be direct and operational.
- Guest explanation should be polite, concise, and professional.
- Do NOT make the admission decision — only explain and guide.
- Do NOT mention technical rule names, category codes, or system identifiers in either response.
- If any item is inconclusive, advise staff to verify manually with a photo ID or physical document.

Respond in JSON only:
{{
  "staff_guidance": "...",
  "guest_explanation": "..."
}}
"""


# ---------------------------------------------------------------------------
# Fallback text — used when LLM is unavailable
# ---------------------------------------------------------------------------

_GUEST_MESSAGES = {
    "INVALID_BOARDING_PASS":        "There appears to be an issue with your boarding pass details.",
    "ACCESS_WINDOW_VIOLATION":      "Your access attempt is outside the permitted window. Lounge access is only allowed within 3 hours before departure.",
    "CARD_NOT_ELIGIBLE_FOR_LOUNGE": "The card you have presented is not eligible for complimentary lounge access.",
    "CARD_EXPIRED":                 "The card you have presented appears to have expired.",
    "BOOKING_REFERENCE_MISMATCH":   "The booking reference you provided does not match the one on your boarding pass.",
    "BOOKING_EXPIRED":              "Your booking has expired and is no longer valid for lounge access.",
    "DUPLICATE_USE":                "It appears this access entitlement has already been used.",
    "AIRLINE_STATUS_INVALID":       "We were unable to verify your airline status.",
    "CARD_HOLDER_NAME_MISMATCH":    "The name on your card does not match the name on your boarding pass.",
    "GUEST_NAME_MISMATCH":                   "The name provided does not match the name on your boarding pass.",
}


def _build_fallback(failed_findings: list, inconclusive_findings: list) -> dict:
    all_findings = failed_findings + inconclusive_findings

    if not all_findings:
        return {
            "staff_guidance":    "The admission could not be validated. Please escalate to a supervisor for manual review.",
            "guest_explanation": "We were unable to process your admission automatically. A staff member will assist you shortly.",
        }

    issues_summary   = all_findings[0]["details"]
    has_inconclusive = len(inconclusive_findings) > 0

    staff_guidance = (
        f"The following issue was identified: {issues_summary}. "
        f"Please address the issue with the guest."
        + (" Manual verification is required." if has_inconclusive else "")
    ).strip()

    if failed_findings:
        guest_message = _GUEST_MESSAGES.get(
            failed_findings[0]["rule_id"],
            "There is an issue with your submitted documents."
        )
        guest_explanation = (
            "We regret that we are unable to process your lounge access at this time. "
            + guest_message
            + " Our staff will be happy to assist you with the next steps."
        )
    else:
        guest_explanation = (
            "There seems to be some issue with your booking. "
            "Please contact one of our staff members who will be happy to assist you."
        )

    return {
        "staff_guidance":    staff_guidance,
        "guest_explanation": guest_explanation,
    }


# ---------------------------------------------------------------------------
# LLM call with fallback
# ---------------------------------------------------------------------------

def get_llm_response(
    failed_findings: list,
    inconclusive_findings: list,
) -> tuple[dict, bool]:
    """
    Calls Gemini to generate staff guidance and guest explanation.
    Returns (result_dict, fallback_used).
    Falls back to deterministic text if API key is missing or call fails.
    """
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return _build_fallback(failed_findings, inconclusive_findings), True

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model  = genai.GenerativeModel("gemini-2.5-flash")
        prompt = _build_prompt(failed_findings, inconclusive_findings)

        response      = model.generate_content(prompt)
        response_text = response.text.strip()

        # Strip markdown code fences if Gemini wraps the JSON in them
        if response_text.startswith("```"):
            lines         = response_text.splitlines()
            response_text = "\n".join(lines[1:-1])

        result = json.loads(response_text)

        if "staff_guidance" not in result or "guest_explanation" not in result:
            raise ValueError("LLM response missing required fields")

        return result, False

    except Exception:
        return _build_fallback(failed_findings, inconclusive_findings), True
