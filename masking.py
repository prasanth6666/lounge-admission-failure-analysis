import re


def mask_name(name: str) -> str:
    """Masks each part of a name keeping only the first character.
    Example: John Michael Smith → J*** M****** S****
    """
    if not name:
        return ""
    parts = name.split()
    masked = []
    for part in parts:
        if len(part) <= 1:
            masked.append(part)
        else:
            masked.append(part[0] + "*" * (len(part) - 1))
    return " ".join(masked)


def mask_card_number(number: str) -> str:
    """Keeps only last 4 digits, masks the rest.
    Example: 4111111111111234 → ************1234
    """
    if not number:
        return ""
    digits = re.sub(r"\D", "", number)
    if len(digits) < 4:
        return "****"
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_booking_reference(ref: str) -> str:
    """Keeps first 2 and last 2 characters, masks the middle.
    Example: BK123489 → BK****89
    """
    if not ref:
        return ""
    if len(ref) <= 4:
        return "*" * len(ref)
    return ref[:2] + "*" * (len(ref) - 4) + ref[-2:]


def mask_card_expiry(expiry: str) -> str:
    """Masks the month, keeps only the year.
    Example: 08/28 → **/28
    """
    if not expiry:
        return ""
    parts = expiry.split("/")
    if len(parts) != 2:
        return "**/**"
    return f"**/{parts[1]}"


def mask_qr_payload(payload: str) -> str:
    """Masks QR code payload entirely — too sensitive to show any part."""
    if not payload:
        return ""
    return "****"


def mask_airline_status_id(status_id: str) -> str:
    """Keeps first 2 and last 2 characters.
    Example: FF-987654321 → FF-*******21
    """
    if not status_id:
        return ""
    if len(status_id) <= 4:
        return "*" * len(status_id)
    return status_id[:2] + "*" * (len(status_id) - 4) + status_id[-2:]


def mask_transaction(transaction) -> dict:
    """Returns a dict with all sensitive fields masked.
    All fields are always present — null when not applicable to the entitlement type.
    """
    cc = transaction.credit_card
    return {
        "guest_name":              mask_name(transaction.guest_name),
        "card_number":             mask_card_number(cc.card_number) if cc else None,
        "card_holder":             mask_name(cc.card_holder_name) if cc else None,
        "card_type":               cc.card_type if cc else None,
        "card_expiry":             mask_card_expiry(cc.expiry_date) if cc else None,
        "booking_reference":       mask_booking_reference(transaction.booking_reference) if transaction.booking_reference else None,
        "qr_code_payload":         mask_qr_payload(transaction.qr_code_payload) if transaction.qr_code_payload else None,
        "airline_status_id":       mask_airline_status_id(transaction.airline_status_id) if transaction.airline_status_id else None,
        "boarding_pass_reference": mask_booking_reference(transaction.boarding_pass.flight_pnr),
        "passenger_name":          mask_name(transaction.boarding_pass.passenger_name),
    }
