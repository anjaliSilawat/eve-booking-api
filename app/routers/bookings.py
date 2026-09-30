import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Booking, BookingStatus, Centre, CentreTest, User
from app.schemas import BookingCreate, BookingOut
from app.security import get_current_user

router = APIRouter(prefix="/bookings", tags=["Bookings"])
logger = logging.getLogger(__name__)


def get_user_booking(db: Session, booking_id: int, user: User, lock: bool = False) -> Booking:
    # returns 404 (not 403) for other users' bookings so we don't leak which ids exist
    query = db.query(Booking).filter(Booking.id == booking_id, Booking.user_id == user.id)
    if lock:
        query = query.with_for_update()
    booking = query.first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    data: BookingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not db.get(Centre, data.centre_id):
        raise HTTPException(status_code=404, detail="Centre not found")

    centre_test = db.query(CentreTest).filter_by(centre_id=data.centre_id, test_id=data.test_id).first()
    if not centre_test:
        raise HTTPException(status_code=400, detail="This test is not available at the selected centre")

    # don't let the same user book the same test at the same slot twice
    duplicate = (
        db.query(Booking)
        .filter(
            Booking.user_id == user.id,
            Booking.centre_id == data.centre_id,
            Booking.test_id == data.test_id,
            Booking.appointment_at == data.appointment_at,
            Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="You already have a booking for this test at this time")

    booking = Booking(
        user_id=user.id,
        centre_id=data.centre_id,
        test_id=data.test_id,
        appointment_at=data.appointment_at,
        amount=centre_test.price,  # amount always comes from our side, never from the client
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    logger.info("Booking %s created by user %s", booking.id, user.id)
    return booking


@router.get("", response_model=list[BookingOut])
def list_my_bookings(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return (
        db.query(Booking)
        .filter(Booking.user_id == user.id)
        .order_by(Booking.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_user_booking(db, booking_id, user)


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    booking = get_user_booking(db, booking_id, user, lock=True)
    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Booking is already cancelled")

    booking.status = BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)
    logger.info("Booking %s cancelled by user %s", booking.id, user.id)
    return booking
