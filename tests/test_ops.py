"""Tests for operational endpoints and error handling."""


def test_healthz_ok_without_pin(client):
    # works while locked / before setup — no auth required
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_healthz_not_blocked_by_origin_guard(auth_client):
    r = auth_client.get("/healthz", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200


def test_http_errors_preserved(auth_client):
    # abort(404) still yields a real 404, not a coerced 500
    assert auth_client.get("/api/photo/nobody").status_code == 404
    assert auth_client.get("/person/does-not-exist").status_code == 404
