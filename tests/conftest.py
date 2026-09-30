from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Centre, CentreTest, DiagnosticTest, User
from app.security import hash_password

# tests run on an in-memory sqlite db so they don't need postgres running
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def signup_and_login(client, email="riya@example.com", password="secret123"):
    client.post("/auth/signup", json={"name": "Riya", "email": email, "password": password})
    res = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def user_headers(client):
    return signup_and_login(client)


@pytest.fixture
def admin_headers(client, db):
    db.add(User(name="Admin", email="admin@eve.com", password_hash=hash_password("admin123"), is_admin=True))
    db.commit()
    res = client.post("/auth/login", json={"email": "admin@eve.com", "password": "admin123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def centre_with_test(db):
    centre = Centre(name="EVE Diagnostics Saket", location="New Delhi")
    test = DiagnosticTest(name="Lipid Profile")
    db.add_all([centre, test])
    db.flush()
    db.add(CentreTest(centre_id=centre.id, test_id=test.id, price=Decimal("600.00")))
    db.commit()
    return {"centre_id": centre.id, "test_id": test.id}


def future_time(days=2):
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat()


@pytest.fixture
def booking(client, user_headers, centre_with_test):
    res = client.post(
        "/bookings",
        json={**centre_with_test, "appointment_at": future_time()},
        headers=user_headers,
    )
    assert res.status_code == 201
    return res.json()
