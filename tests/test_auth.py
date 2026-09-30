def test_signup_and_login(client):
    res = client.post("/auth/signup", json={"name": "Riya", "email": "Riya@Example.com", "password": "secret123"})
    assert res.status_code == 201
    body = res.json()
    assert body["email"] == "riya@example.com"
    assert "password" not in body and "password_hash" not in body

    res = client.post("/auth/login", json={"email": "riya@example.com", "password": "secret123"})
    assert res.status_code == 200
    token = res.json()["access_token"]

    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["name"] == "Riya"


def test_signup_duplicate_email(client):
    data = {"name": "Riya", "email": "riya@example.com", "password": "secret123"}
    client.post("/auth/signup", json=data)
    res = client.post("/auth/signup", json=data)
    assert res.status_code == 409


def test_signup_validation(client):
    res = client.post("/auth/signup", json={"name": "R", "email": "not-an-email", "password": "123"})
    assert res.status_code == 422


def test_login_wrong_password(client):
    client.post("/auth/signup", json={"name": "Riya", "email": "riya@example.com", "password": "secret123"})
    res = client.post("/auth/login", json={"email": "riya@example.com", "password": "wrongpass"})
    assert res.status_code == 401


def test_protected_route_needs_token(client):
    assert client.get("/bookings").status_code in (401, 403)
    res = client.get("/bookings", headers={"Authorization": "Bearer abc.def.ghi"})
    assert res.status_code == 401
