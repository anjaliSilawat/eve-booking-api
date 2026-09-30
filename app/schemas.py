from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import BookingStatus, PaymentStatus


# ---------- auth ----------

class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    # bcrypt only uses the first 72 bytes
    password: str = Field(min_length=6, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    is_admin: bool


# ---------- centres & tests ----------

class DiagnosticTestCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: Optional[str] = Field(default=None, max_length=500)


class DiagnosticTestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None


class CentreCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    location: str = Field(min_length=2, max_length=150)


class CentreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str


class CentreTestCreate(BaseModel):
    test_id: int
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class CentreTestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    test: DiagnosticTestOut
    price: Decimal


class CentreDetail(CentreOut):
    tests: list[CentreTestOut] = []


# ---------- bookings ----------

class BookingCreate(BaseModel):
    centre_id: int
    test_id: int
    appointment_at: datetime

    @field_validator("appointment_at")
    @classmethod
    def must_be_in_future(cls, value: datetime):
        # if no timezone is sent, treat it as UTC
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value <= datetime.now(timezone.utc):
            raise ValueError("appointment time must be in the future")
        return value


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    centre_id: int
    test_id: int
    appointment_at: datetime
    amount: Decimal
    status: BookingStatus
    created_at: datetime


# ---------- payments ----------

class PaymentRequest(BaseModel):
    booking_id: int
    # lets the client decide the outcome of the fake payment
    simulate: Literal["success", "failed"] = "success"


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    amount: Decimal
    status: PaymentStatus
    reference: str
    created_at: datetime


class WebhookPayload(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    booking_id: int
    status: PaymentStatus
    payment_reference: Optional[str] = Field(default=None, max_length=64)
