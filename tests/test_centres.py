def test_admin_can_create_centre_and_add_test(client, admin_headers):
    res = client.post("/centres", json={"name": "EVE Noida", "location": "Noida"}, headers=admin_headers)
    assert res.status_code == 201
    centre_id = res.json()["id"]

    res = client.post("/tests", json={"name": "HbA1c"}, headers=admin_headers)
    assert res.status_code == 201
    test_id = res.json()["id"]

    res = client.post(f"/centres/{centre_id}/tests", json={"test_id": test_id, "price": 450}, headers=admin_headers)
    assert res.status_code == 201

    res = client.get(f"/centres/{centre_id}")
    assert res.status_code == 200
    tests = res.json()["tests"]
    assert len(tests) == 1
    assert tests[0]["test"]["name"] == "HbA1c"
    assert float(tests[0]["price"]) == 450


def test_same_test_cannot_be_added_twice(client, admin_headers, centre_with_test):
    res = client.post(
        f"/centres/{centre_with_test['centre_id']}/tests",
        json={"test_id": centre_with_test["test_id"], "price": 100},
        headers=admin_headers,
    )
    assert res.status_code == 409


def test_normal_user_cannot_create_centre(client, user_headers):
    res = client.post("/centres", json={"name": "Fake", "location": "Delhi"}, headers=user_headers)
    assert res.status_code == 403


def test_invalid_price_rejected(client, admin_headers, centre_with_test):
    res = client.post(
        f"/centres/{centre_with_test['centre_id']}/tests",
        json={"test_id": centre_with_test["test_id"], "price": -10},
        headers=admin_headers,
    )
    assert res.status_code == 422


def test_list_centres_with_location_filter(client, centre_with_test):
    assert len(client.get("/centres?location=delhi").json()) == 1
    assert client.get("/centres?location=mumbai").json() == []


def test_centre_not_found(client):
    assert client.get("/centres/999").status_code == 404
