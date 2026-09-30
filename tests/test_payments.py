from app.config import WEBHOOK_SECRET
from app.models import Payment, WebhookEvent
from tests.conftest import future_time, signup_and_login

WEBHOOK_HEADERS = {"X-Webhook-Secret": WEBHOOK_SECRET}


def get_status(client, headers, booking_id):
    return client.get(f"/bookings/{booking_id}", headers=headers).json()["status"]


# ---------- POST /payments/ ----------

def test_successful_payment_confirms_booking(client, user_headers, booking):
    res = client.post("/payments/", json={"booking_id": booking["id"]}, headers=user_headers)
    assert res.status_code == 201
    assert res.json()["status"] == "SUCCESS"
    assert res.json()["reference"].startswith("pay_")
    assert get_status(client, user_headers, booking["id"]) == "CONFIRMED"


def test_failed_payment_marks_booking_failed(client, user_headers, booking):
    res = client.post("/payments/", json={"booking_id": booking["id"], "simulate": "failed"}, headers=user_headers)
    assert res.status_code == 201
    assert res.json()["status"] == "FAILED"
    assert get_status(client, user_headers, booking["id"]) == "FAILED"


def test_can_retry_after_failed_payment(client, user_headers, booking):
    client.post("/payments/", json={"booking_id": booking["id"], "simulate": "failed"}, headers=user_headers)
    res = client.post("/payments/", json={"booking_id": booking["id"]}, headers=user_headers)
    assert res.status_code == 201
    assert get_status(client, user_headers, booking["id"]) == "CONFIRMED"


def test_cannot_pay_twice(client, user_headers, booking, db):
    client.post("/payments/", json={"booking_id": booking["id"]}, headers=user_headers)
    res = client.post("/payments/", json={"booking_id": booking["id"]}, headers=user_headers)
    assert res.status_code == 409
    assert db.query(Payment).filter_by(booking_id=booking["id"], status="SUCCESS").count() == 1


def test_cannot_pay_cancelled_booking(client, user_headers, booking):
    client.post(f"/bookings/{booking['id']}/cancel", headers=user_headers)
    res = client.post("/payments/", json={"booking_id": booking["id"]}, headers=user_headers)
    assert res.status_code == 409


def test_cannot_pay_for_someone_elses_booking(client, booking):
    other = signup_and_login(client, email="other@example.com")
    res = client.post("/payments/", json={"booking_id": booking["id"]}, headers=other)
    assert res.status_code == 404


def test_payment_invalid_booking_id(client, user_headers):
    res = client.post("/payments/", json={"booking_id": 999}, headers=user_headers)
    assert res.status_code == 404


def test_payment_invalid_simulate_value(client, user_headers, booking):
    res = client.post("/payments/", json={"booking_id": booking["id"], "simulate": "maybe"}, headers=user_headers)
    assert res.status_code == 422


# ---------- POST /payments/webhook/ ----------

def test_webhook_confirms_booking(client, user_headers, booking):
    payload = {"event_id": "evt_1", "booking_id": booking["id"], "status": "SUCCESS"}
    res = client.post("/payments/webhook/", json=payload, headers=WEBHOOK_HEADERS)
    assert res.status_code == 200
    assert res.json()["booking_status"] == "CONFIRMED"
    assert get_status(client, user_headers, booking["id"]) == "CONFIRMED"


def test_webhook_same_event_is_idempotent(client, user_headers, booking, db):
    payload = {"event_id": "evt_dup", "booking_id": booking["id"], "status": "SUCCESS"}

    for _ in range(3):
        res = client.post("/payments/webhook/", json=payload, headers=WEBHOOK_HEADERS)
        assert res.status_code == 200

    assert res.json()["message"] == "Event already processed"
    assert db.query(WebhookEvent).filter_by(event_id="evt_dup").count() == 1
    assert db.query(Payment).filter_by(booking_id=booking["id"]).count() == 1
    assert get_status(client, user_headers, booking["id"]) == "CONFIRMED"


def test_webhook_updates_existing_payment_instead_of_creating_new(client, user_headers, booking, db):
    res = client.post("/payments/", json={"booking_id": booking["id"], "simulate": "failed"}, headers=user_headers)
    reference = res.json()["reference"]

    payload = {"event_id": "evt_2", "booking_id": booking["id"], "status": "SUCCESS", "payment_reference": reference}
    client.post("/payments/webhook/", json=payload, headers=WEBHOOK_HEADERS)

    payments = db.query(Payment).filter_by(booking_id=booking["id"]).all()
    assert len(payments) == 1
    assert payments[0].status.value == "SUCCESS"
    assert get_status(client, user_headers, booking["id"]) == "CONFIRMED"


def test_late_failed_webhook_does_not_undo_confirmed_booking(client, user_headers, booking):
    client.post("/payments/", json={"booking_id": booking["id"]}, headers=user_headers)

    payload = {"event_id": "evt_late", "booking_id": booking["id"], "status": "FAILED"}
    res = client.post("/payments/webhook/", json=payload, headers=WEBHOOK_HEADERS)
    assert res.status_code == 200
    assert get_status(client, user_headers, booking["id"]) == "CONFIRMED"


def test_webhook_does_not_touch_cancelled_booking(client, user_headers, booking):
    client.post(f"/bookings/{booking['id']}/cancel", headers=user_headers)
    payload = {"event_id": "evt_3", "booking_id": booking["id"], "status": "SUCCESS"}
    client.post("/payments/webhook/", json=payload, headers=WEBHOOK_HEADERS)
    assert get_status(client, user_headers, booking["id"]) == "CANCELLED"


def test_webhook_wrong_secret(client, booking):
    payload = {"event_id": "evt_4", "booking_id": booking["id"], "status": "SUCCESS"}
    assert client.post("/payments/webhook/", json=payload).status_code == 401
    res = client.post("/payments/webhook/", json=payload, headers={"X-Webhook-Secret": "wrong"})
    assert res.status_code == 401


def test_webhook_unknown_booking(client):
    payload = {"event_id": "evt_5", "booking_id": 999, "status": "SUCCESS"}
    res = client.post("/payments/webhook/", json=payload, headers=WEBHOOK_HEADERS)
    assert res.status_code == 404


def test_webhook_reference_of_another_booking(client, user_headers, booking, centre_with_test):
    res = client.post("/payments/", json={"booking_id": booking["id"], "simulate": "failed"}, headers=user_headers)
    reference = res.json()["reference"]

    second = client.post(
        "/bookings", json={**centre_with_test, "appointment_at": future_time(5)}, headers=user_headers
    ).json()

    payload = {"event_id": "evt_6", "booking_id": second["id"], "status": "SUCCESS", "payment_reference": reference}
    res = client.post("/payments/webhook/", json=payload, headers=WEBHOOK_HEADERS)
    assert res.status_code == 400


def test_webhook_invalid_status(client, booking):
    payload = {"event_id": "evt_7", "booking_id": booking["id"], "status": "DONE"}
    res = client.post("/payments/webhook/", json=payload, headers=WEBHOOK_HEADERS)
    assert res.status_code == 422
