"""Characterization tests for the setup / lock / unlock flow."""
import pytest

import sqlcipher3.dbapi2 as _sqlcipher

# The pinned production lib (sqlcipher3==0.5.3) exposes Connection.iterdump,
# which change-pin's re-key relies on. The local prebuilt test wheel
# (sqlcipher3-binary) may not, so skip the re-key test there rather than
# assert a behaviour the runtime can't provide.
_HAS_ITERDUMP = hasattr(_sqlcipher.connect(":memory:"), "iterdump")


def test_index_without_pin_redirects_to_setup(client):
    r = client.get("/")
    assert r.status_code == 302
    assert "/setup" in r.headers["Location"]


def test_api_without_pin_returns_setup_required(client):
    r = client.get("/api/tree")
    assert r.status_code == 403
    assert r.get_json()["error"] == "setup required"


def test_setup_rejects_short_pin(client):
    r = client.post("/setup", data={"pin": "12", "confirm": "12"})
    assert r.status_code == 200
    assert b"4" in r.data  # error message about length shown


def test_setup_rejects_mismatched_pins(client):
    r = client.post("/setup", data={"pin": "1234", "confirm": "9999"})
    assert r.status_code == 200
    assert b"do not match" in r.data


def test_setup_creates_config_and_unlocks(client, appmod):
    r = client.post("/setup", data={"pin": "1234", "confirm": "1234", "timeout": "30"})
    assert r.status_code == 302
    cfg = appmod._load_pin_config()
    assert cfg is not None
    assert cfg["timeout_minutes"] == 30
    assert "pin_hash" in cfg and "salt" in cfg
    # session is now active
    assert client.get("/").status_code == 200


def test_setup_second_time_redirects_to_index(auth_client):
    r = auth_client.get("/setup")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/")


def test_lock_then_wrong_pin(auth_client):
    assert auth_client.post("/api/lock").status_code == 200
    # now locked: index redirects to lock screen
    r = auth_client.get("/")
    assert r.status_code == 302 and "/lock" in r.headers["Location"]
    # wrong PIN stays on lock screen with error
    r = auth_client.post("/lock", data={"pin": "0000"})
    assert r.status_code == 200 and b"Incorrect" in r.data


def test_lock_then_correct_pin_unlocks(auth_client):
    auth_client.post("/api/lock")
    r = auth_client.post("/lock", data={"pin": "1234"})
    assert r.status_code == 302
    assert auth_client.get("/").status_code == 200


def test_ping_heartbeat(auth_client):
    assert auth_client.post("/api/ping").get_json()["ok"] is True


@pytest.mark.skipif(not _HAS_ITERDUMP,
                    reason="local sqlcipher wheel lacks Connection.iterdump")
def test_change_pin_rekeys_and_reencrypts(auth_client, appmod):
    # seed some data so re-key exercises a non-empty DB
    auth_client.post("/api/person", json={"name": "Carol", "category": "Work"})
    r = auth_client.post("/api/change-pin", json={"old_pin": "1234", "new_pin": "5678"})
    assert r.status_code == 200
    # lock and unlock with the new PIN; data survives
    auth_client.post("/api/lock")
    assert auth_client.post("/lock", data={"pin": "5678"}).status_code == 302
    tree = auth_client.get("/api/tree").get_json()
    names = [p["name"] for cat in tree for p in cat["people"]]
    assert "Carol" in names


def test_change_pin_wrong_old_pin(auth_client):
    r = auth_client.post("/api/change-pin", json={"old_pin": "0000", "new_pin": "5678"})
    assert r.status_code == 403


def test_update_timeout(auth_client, appmod):
    r = auth_client.post("/api/settings/timeout", json={"minutes": 60})
    assert r.status_code == 200
    assert appmod._load_pin_config()["timeout_minutes"] == 60
    # invalid value rejected
    assert auth_client.post("/api/settings/timeout", json={"minutes": 7}).status_code == 400


def test_reset_wipes_config_and_db(auth_client, appmod):
    assert appmod._PIN_CONFIG.exists()
    r = auth_client.post("/reset", data={"confirm": "RESET"})
    assert r.status_code == 302
    assert not appmod._PIN_CONFIG.exists()
    assert not appmod.DB_PATH.exists()
