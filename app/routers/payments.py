import hmac
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import WEBHOOK_SECRET
from app.database import get_db
from app.models import Booking, BookingStatus, Payment, PaymentStatus, User, WebhookEvent
from app.routers.bookings import get_user_booking
from app.schemas import PaymentOut, PaymentRequest, WebhookPayload
from app.security import get_current_user

router = APIRouter(prefix="/payments", tags=["Payments"])
logger = logging.getLogger(__name__)

# a failed booking can be paid again, confirmed/cancelled ones can't
PAYABLE_STATUSES = (BookingStatus.PENDING, BookingStatus.FAILED)


def new_payment_reference() -> str:
    return f"pay_{uuid.uuid4().hex[:16]}"


def booking_status_for(payment_status: PaymentStatus) -> BookingStatus:
    if payment_status == PaymentStatus.SUCCESS:
        return BookingStatus.CONFIRMED
    return BookingStatus.FAILED


@router.post("/", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def make_payment(
    data: PaymentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # lock the booking row so two payment requests for the same booking can't both go through
    booking = get_user_booking(db, data.booking_id, user, lock=True)

    if booking.status not in PAYABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot pay for a booking that is {booking.status.value}",
        )

    payment_status = PaymentStatus.SUCCESS if data.simulate == "success" else PaymentStatus.FAILED
    payment = Payment(
        booking_id=booking.id,
        amount=booking.amount,
        status=payment_status,
        reference=new_payment_reference(),
    )
    db.add(payment)
    booking.status = booking_status_for(payment_status)
    db.commit()
    db.refresh(payment)

    logger.info("Payment %s for booking %s: %s", payment.reference, booking.id, payment_status.value)
    return payment


@router.post("/webhook/")
def payment_webhook(
    payload: WebhookPayload,
    x_webhook_secret: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # idempotency: if we've seen this event before just say ok and do nothing
    if db.query(WebhookEvent).filter_by(event_id=payload.event_id).first():
        logger.info("Duplicate webhook event %s ignored", payload.event_id)
        return {"message": "Event already processed", "event_id": payload.event_id}

    booking = db.query(Booking).filter(Booking.id == payload.booking_id).with_for_update().first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    payment = None
    if payload.payment_reference:
        payment = db.query(Payment).filter_by(reference=payload.payment_reference).first()
        if payment and payment.booking_id != booking.id:
            raise HTTPException(status_code=400, detail="Payment reference does not belong to this booking")

    db.add(WebhookEvent(event_id=payload.event_id, booking_id=booking.id, status=payload.status))

    if booking.status in (BookingStatus.CONFIRMED, BookingStatus.CANCELLED):
        # final states - we still record the event but don't touch the booking
        message = f"Booking is already {booking.status.value}, no changes made"
    else:
        if payment:
            payment.status = payload.status
        else:
            db.add(
                Payment(
                    booking_id=booking.id,
                    amount=booking.amount,
                    status=payload.status,
                    reference=payload.payment_reference or new_payment_reference(),
                )
            )
        booking.status = booking_status_for(payload.status)
        message = "Booking updated"

    try:
        db.commit()
    except IntegrityError:
        # same event came in at the same time from another request and won the insert
        db.rollback()
        logger.info("Webhook event %s already processed (race)", payload.event_id)
        return {"message": "Event already processed", "event_id": payload.event_id}

    logger.info("Webhook event %s for booking %s: %s", payload.event_id, booking.id, message)
    return {"message": message, "event_id": payload.event_id, "booking_status": booking.status.value}
