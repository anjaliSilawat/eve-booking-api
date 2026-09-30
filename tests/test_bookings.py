from datetime import datetime, timedelta, timezone

from tests.conftest import future_time, signup_and_login


def test_create_booking(booking):
    assert booking["status"] == "PENDING"
    # amount is taken from the centre's price, not from the request
    assert float(booking["amount"]) == 600


def test_booking_in_past_rejected(client, user_headers, centre_with_test):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    res = client.post("/bookings", json={**centre_with_test, "appointment_at": past}, headers=user_headers)
    assert res.status_code == 422


def test_booking_test_not_offered_at_centre(client, user_headers, centre_with_test):
    res = client.post(
        "/bookings",
        json={"centre_id": centre_with_test["centre_id"], "test_id": 999, "appointment_at": future_time()},
        headers=user_headers,
    )
    assert res.status_code == 400


def test_booking_invalid_centre(client, user_headers, centre_with_test):
    res = client.post(
        "/bookings",
        json={"centre_id": 999, "test_id": centre_with_test["test_id"], "appointment_at": future_time()},
        headers=user_headers,
    )
    assert res.status_code == 404


def test_duplicate_booking_same_slot(client, user_headers, centre_with_test):
    data = {**centre_with_test, "appointment_at": future_time(3)}
    assert client.post("/bookings", json=data, headers=user_headers).status_code == 201
    assert client.post("/bookings", json=data, headers=user_headers).status_code == 409


def test_list_only_my_bookings(client, booking):
    other = signup_and_login(client, email="other@example.com")
    assert client.get("/bookings", headers=other).json() == []


def test_cannot_view_or_cancel_other_users_booking(client, booking):
    other = signup_and_login(client, email="other@example.com")
    assert client.get(f"/bookings/{booking['id']}", headers=other).status_code == 404
    assert client.post(f"/bookings/{booking['id']}/cancel", headers=other).status_code == 404


def test_cancel_booking(client, user_headers, booking):
    res = client.post(f"/bookings/{booking['id']}/cancel", headers=user_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "CANCELLED"

    res = client.post(f"/bookings/{booking['id']}/cancel", headers=user_headers)
    assert res.status_code == 409


def test_booking_not_found(client, user_headers):
    assert client.get("/bookings/12345", headers=user_headers).status_code == 404
