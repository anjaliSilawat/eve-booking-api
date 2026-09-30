# EVE Diagnostic Bookings API

Backend service for booking diagnostic tests at centres and paying for them through a simulated payment flow, with an idempotent payment webhook.

Built with **FastAPI**, **PostgreSQL**, **SQLAlchemy**, **JWT** auth, **pytest** and **Docker**.

---

## Running the project

### Option 1 - Docker (easiest)

```bash
docker compose up --build
```

In another terminal, load some sample data (an admin user, 5 tests, 3 centres):

```bash
docker compose exec api python -m app.seed
```

The API runs on http://localhost:8000 and Swagger docs are at http://localhost:8000/docs.

If port 8000 is already in use on your machine: `API_PORT=8001 docker compose up --build`

### Option 2 - Locally

Needs Python 3.11+ and a running PostgreSQL.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then update DATABASE_URL if needed
python -m app.seed          # creates tables + sample data
uvicorn app.main:app --reload
```

### Running tests

```bash
pytest
```

Tests use an in-memory SQLite database, so they don't need Postgres or Docker running. There are 37 tests covering auth, centres, bookings, payments and the webhook.

---

## Project structure

```
app/
  main.py          FastAPI app, routers, table creation on startup
  config.py        settings read from env variables
  database.py      engine, session and get_db dependency
  models.py        SQLAlchemy models
  schemas.py       Pydantic request/response models + validation
  security.py      password hashing, JWT, current user / admin dependencies
  seed.py          sample data
  routers/
    auth.py
    centres.py
    bookings.py
    payments.py    payment + webhook
tests/
```

---

## Database design

```
users            id, name, email (unique), password_hash, is_admin, created_at
centres          id, name, location, created_at
diagnostic_tests id, name (unique), description
centre_tests     id, centre_id -> centres, test_id -> diagnostic_tests, price
                 UNIQUE(centre_id, test_id)
bookings         id, user_id -> users, centre_id, test_id, appointment_at,
                 amount, status, created_at, updated_at
payments         id, booking_id -> bookings, amount, status, reference (unique),
                 created_at, updated_at
                 UNIQUE(booking_id) WHERE status = 'SUCCESS'
webhook_events   id, event_id (unique), booking_id, status, received_at
```

Some decisions:

- **Price lives in `centre_tests`**, not in `diagnostic_tests`. The same test (e.g. Lipid Profile) can have a different price at different centres, so price belongs to the centre–test pair.
- **The booking stores its own `amount`**. It is copied from `centre_tests.price` when the booking is created and is never taken from the request body. If the centre changes the price later, old bookings aren't affected.
- **A booking can have many payments**, because a failed payment can be retried. A partial unique index makes sure there is **at most one SUCCESS payment per booking**, so even a bug in the code can't charge someone twice.
- **`webhook_events.event_id` is unique**. This is what makes the webhook idempotent (see below).
- Money uses `NUMERIC(10,2)`, not float.

### Booking status flow

```
PENDING --(payment success)--> CONFIRMED
PENDING --(payment failed)---> FAILED --(retry, success)--> CONFIRMED
any status except CANCELLED --(user cancels)--> CANCELLED
```

CONFIRMED and CANCELLED are treated as final for payments. You can't pay for them again, and webhooks don't change them.

---

## API endpoints

Swagger UI at `/docs` has all endpoints with request/response schemas. Use the **Authorize** button there to paste the JWT.

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/signup` | - | Create account |
| POST | `/auth/login` | - | Get JWT token |
| GET | `/auth/me` | User | Logged in user |
| GET | `/centres?location=&skip=&limit=` | - | List centres (paginated, filter by location) |
| GET | `/centres/{id}` | - | Centre with its tests and prices |
| POST | `/centres` | Admin | Create centre |
| POST | `/centres/{id}/tests` | Admin | Add a test to a centre with price |
| GET | `/tests` | - | List all diagnostic tests |
| POST | `/tests` | Admin | Create a diagnostic test |
| POST | `/bookings` | User | Book a test |
| GET | `/bookings?skip=&limit=` | User | My bookings |
| GET | `/bookings/{id}` | User | One of my bookings |
| POST | `/bookings/{id}/cancel` | User | Cancel my booking |
| POST | `/payments/` | User | Simulated payment for a booking |
| POST | `/payments/webhook/` | Webhook secret | Payment status update from provider |

### Example requests

**Signup and login**

```bash
curl -X POST localhost:8000/auth/signup -H "Content-Type: application/json" \
  -d '{"name": "Anjali", "email": "anjali@test.com", "password": "secret123"}'

curl -X POST localhost:8000/auth/login -H "Content-Type: application/json" \
  -d '{"email": "anjali@test.com", "password": "secret123"}'
# {"access_token": "eyJhbGciOi...", "token_type": "bearer"}

TOKEN=<paste access_token here>
```

**Browse centres**

```bash
curl "localhost:8000/centres?location=delhi"
curl localhost:8000/centres/1
```

**Create a booking**

```bash
curl -X POST localhost:8000/bookings -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"centre_id": 1, "test_id": 2, "appointment_at": "2026-12-10T10:30:00+05:30"}'
```

```json
{"id": 1, "centre_id": 1, "test_id": 2, "appointment_at": "2026-12-10T05:00:00Z",
 "amount": "600.00", "status": "PENDING", "created_at": "..."}
```

**Pay for it**

`simulate` can be `"success"` (default) or `"failed"`, so both outcomes can be tested without randomness.

```bash
curl -X POST localhost:8000/payments/ -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"booking_id": 1, "simulate": "failed"}'
```

```json
{"id": 1, "booking_id": 1, "amount": "600.00", "status": "FAILED",
 "reference": "pay_336d3d00c4d14640", "created_at": "..."}
```

**Webhook from payment provider**

```bash
curl -X POST localhost:8000/payments/webhook/ -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: dev-webhook-secret" \
  -d '{"event_id": "evt_100", "booking_id": 1, "status": "SUCCESS", "payment_reference": "pay_336d3d00c4d14640"}'
# first time:  {"message": "Booking updated", "event_id": "evt_100", "booking_status": "CONFIRMED"}
# again:       {"message": "Event already processed", "event_id": "evt_100"}
```

`payment_reference` is optional. If it matches an existing payment, that payment is updated. If not, a new payment row is created.

---

## How the webhook stays idempotent

1. Check the `X-Webhook-Secret` header, else 401.
2. Look up `event_id` in `webhook_events`. If it's already there, return 200 with "Event already processed" and do nothing else. Returning 200 (not an error) matters because a real provider keeps retrying until it gets a 2xx.
3. Lock the booking row (`SELECT ... FOR UPDATE`) so a webhook and a `/payments/` call for the same booking can't update it at the same time.
4. Save the event, update or create the payment, and update the booking status, all in **one transaction**. So either everything is saved or nothing is.
5. If two copies of the same event arrive at exactly the same moment, both pass step 2, but only one can insert the `event_id` because of the unique constraint. The other gets an `IntegrityError`, which I catch and treat as a duplicate.

Also, if a booking is already CONFIRMED or CANCELLED, the event is recorded but the booking isn't changed. For example, a late "FAILED" webhook can't undo a confirmed booking.

---

## Edge cases handled

| Case | Response |
|---|---|
| Invalid body (bad email, short password, negative price, wrong enum) | 422 |
| Appointment time in the past | 422 |
| Centre doesn't exist | 404 |
| Test not offered at that centre | 400 |
| Same user books same test, centre and time twice | 409 |
| Email already registered | 409 |
| Wrong login | 401 (same message for wrong email or password) |
| Missing / invalid / expired token | 401 |
| Normal user calling admin endpoints | 403 |
| Viewing, cancelling or paying for another user's booking | 404 (so booking ids of other users aren't revealed) |
| Paying for a CONFIRMED or CANCELLED booking | 409 |
| Invalid booking id in payment / webhook | 404 |
| Same webhook event sent multiple times | 200, applied only once |
| Webhook with a payment reference of a different booking | 400 |
| Webhook with wrong or missing secret | 401 |

---

## Assumptions

- Only admins can create centres and tests. Signup always creates a normal user, and the admin is created by the seed script (`admin@eve.com` / `admin123`, configurable through env).
- The payment is fake. The client chooses the outcome with `simulate`, and the amount always comes from the booking.
- A FAILED booking can be paid again (retry). The user doesn't need to create a new booking.
- Cancelling doesn't do refunds. That's out of scope for this assignment.
- Webhook authentication uses a simple shared secret header. Real providers usually sign the payload with HMAC instead.
- Times without a timezone are treated as UTC. All times are stored as `timestamptz`.
- I'm not checking centre capacity or slot availability. Many users can book the same slot.
- Tables are created on app startup with `create_all()` to keep setup simple.

## What I would improve with more time

- Use **Alembic** migrations instead of `create_all()`.
- HMAC signature verification for the webhook, plus a timestamp check to reject old replayed events.
- Handle refunds when a paid booking is cancelled, or when a SUCCESS webhook arrives for a cancelled booking.
- Slot and capacity management per centre.
- Run the tests on PostgreSQL too (e.g. in GitHub Actions with a Postgres service), because SQLite ignores `FOR UPDATE`.
- Rate limiting on login and signup, and refresh tokens.
- Move the business logic from routers into a separate service layer as the project grows.
- Structured JSON logs with a request id.
