from pydantic import BaseModel, field_validator, model_validator
from typing import Optional
from datetime import date, time


class BoardingPass(BaseModel):
    passenger_name: str
    flight_number: str
    flight_date: date
    departure_time: time
    departure_airport: str
    destination_airport: str
    flight_pnr: str


class CreditCard(BaseModel):
    card_number: str
    card_type: str
    expiry_date: str        # MM/YY format e.g. 12/27
    card_holder_name: str


class AdmissionTransaction(BaseModel):
    transaction_id: str
    lounge_id: str
    attempt_timestamp: str
    guest_name: str
    boarding_pass: BoardingPass
    credit_card: Optional[CreditCard] = None
    booking_reference: Optional[str] = None
    qr_code_payload: Optional[str] = None
    airline_status_id: Optional[str] = None
    entitlement_type: str

    @field_validator("entitlement_type")
    @classmethod
    def validate_entitlement_type(cls, v):
        from config import ENTITLEMENT_TYPES
        if v not in ENTITLEMENT_TYPES:
            raise ValueError(
                f"Invalid entitlement_type '{v}'. Must be one of {ENTITLEMENT_TYPES}"
            )
        return v

    @model_validator(mode="after")
    def check_required_fields(self):
        if self.entitlement_type == "CREDIT_CARD" and self.credit_card is None:
            raise ValueError(
                "credit_card is required when entitlement_type is CREDIT_CARD"
            )
        if self.entitlement_type == "BOOKING":
            if not self.booking_reference and not self.qr_code_payload:
                raise ValueError(
                    "booking_reference or qr_code_payload is required when entitlement_type is BOOKING"
                )
        if self.entitlement_type == "AIRLINE_STATUS" and self.airline_status_id is None:
            raise ValueError(
                "airline_status_id is required when entitlement_type is AIRLINE_STATUS"
            )
        return self
