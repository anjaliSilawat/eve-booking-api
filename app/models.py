import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PaymentStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    bookings = relationship("Booking", back_populates="user")


class Centre(Base):
    __tablename__ = "centres"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    location = Column(String(150), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    # tests offered by this centre along with their price
    tests = relationship("CentreTest", back_populates="centre")


class DiagnosticTest(Base):
    __tablename__ = "diagnostic_tests"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique=True, nullable=False)
    description = Column(String(500))


class CentreTest(Base):
    """Which test is available at which centre, and at what price.
    Price is kept here because the same test can cost differently at different centres."""

    __tablename__ = "centre_tests"
    __table_args__ = (UniqueConstraint("centre_id", "test_id", name="uq_centre_test"),)

    id = Column(Integer, primary_key=True)
    centre_id = Column(Integer, ForeignKey("centres.id", ondelete="CASCADE"), nullable=False)
    test_id = Column(Integer, ForeignKey("diagnostic_tests.id", ondelete="CASCADE"), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)

    centre = relationship("Centre", back_populates="tests")
    test = relationship("DiagnosticTest")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    test_id = Column(Integer, ForeignKey("diagnostic_tests.id"), nullable=False)
    appointment_at = Column(DateTime(timezone=True), nullable=False)
    # copied from centre_tests.price at booking time so later price changes don't affect it
    amount = Column(Numeric(10, 2), nullable=False)
    status = Column(Enum(BookingStatus, native_enum=False), default=BookingStatus.PENDING, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="bookings")
    centre = relationship("Centre")
    test = relationship("DiagnosticTest")
    payments = relationship("Payment", back_populates="booking")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        # a booking can have many failed attempts but only one successful payment
        Index(
            "uq_one_success_payment_per_booking",
            "booking_id",
            unique=True,
            postgresql_where=text("status = 'SUCCESS'"),
            sqlite_where=text("status = 'SUCCESS'"),
        ),
    )

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    status = Column(Enum(PaymentStatus, native_enum=False), nullable=False)
    reference = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    booking = relationship("Booking", back_populates="payments")


class WebhookEvent(Base):
    """Every webhook event we have processed. event_id is unique so the same
    event can never be applied twice."""

    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(100), unique=True, nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    status = Column(Enum(PaymentStatus, native_enum=False), nullable=False)
    received_at = Column(DateTime(timezone=True), default=utc_now)
