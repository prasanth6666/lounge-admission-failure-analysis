from models import AdmissionTransaction
from rule_engine import run_rules
from masking import mask_transaction
from llm_client import get_llm_response


def analyse_transaction(transaction: AdmissionTransaction) -> dict:
    """
    Analyses a failed lounge admission transaction.
    Runs deterministic rules, masks sensitive data, and generates
    staff guidance and guest explanation via LLM (with fallback).
    """

    # Step 1: Run all rules
    findings, failure_categories, requires_manual = run_rules(transaction)

    # Step 2: Derive overall status and confidence
    failed_findings       = [f for f in findings if f["result"] == "failed"]
    inconclusive_findings = [f for f in findings if f["result"] == "inconclusive"]

    if failed_findings:
        status     = "failed"
        confidence = "high"
    else:
        status     = "inconclusive"
        confidence = "low"

    # Step 3: Mask sensitive guest data
    masked_guest_data = mask_transaction(transaction)

    # Step 4: Get staff guidance and guest explanation from LLM (or fallback)
    llm_result, fallback_used = get_llm_response(
        transaction_id        = transaction.transaction_id,
        failure_categories    = failure_categories,
        failed_findings       = failed_findings,
        inconclusive_findings = inconclusive_findings,
    )

    # Step 5: Build and return structured response
    return {
        "transaction_id":         transaction.transaction_id,
        "status":                 status,
        "failure_category":       failure_categories[0] if failure_categories else None,
        "confidence":             confidence,
        "deterministic_findings": findings,
        "masked_guest_data":      masked_guest_data,
        "staff_guidance":         llm_result["staff_guidance"],
        "guest_explanation":      llm_result["guest_explanation"],
        "requires_manual_review": requires_manual,
        "fallback_used":          fallback_used,
    }
