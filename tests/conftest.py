"""Shared pytest fixtures.

Each test gets a freshly-imported ``app`` module pointed at a throwaway
temp directory, so DB_PATH / PIN_CONFIG / the persistent secret key never
touch the real data volume. Because every data route is gated behind
``require_unlock`` and the encrypted (SQLCipher) path is used once a PIN
exists, the ``auth_client`` fixture drives the real setup→unlock flow.
"""
import importlib
import sys

import pytest

PIN = "1234"


@pytest.fixture
def appmod(tmp_path, monkeypatch):
    """Import the Flask app fresh against a temp data dir.

    ``peoplecrm.config`` resolves DB_PATH / PIN_CONFIG from the environment at
    import time, so drop the app and all package submodules first to force a
    clean re-read per test.
    """
    monkeypatch.setenv("DB_PATH", str(tmp_path / "people.db"))
    monkeypatch.setenv("PIN_CONFIG", str(tmp_path / "pin.json"))
    for name in list(sys.modules):
        if name == "app" or name == "peoplecrm" or name.startswith("peoplecrm."):
            sys.modules.pop(name, None)
    mod = importlib.import_module("app")
    mod.app.config.update(TESTING=True)
    return mod


@pytest.fixture
def client(appmod):
    """Anonymous client — no PIN configured yet."""
    return appmod.app.test_client()


@pytest.fixture
def auth_client(appmod):
    """Client that has completed setup and holds an unlocked session."""
    c = appmod.app.test_client()
    resp = c.post(
        "/setup",
        data={"pin": PIN, "confirm": PIN, "timeout": "15"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    return c


def make_person(client, name="Alice Smith", category="Friends"):
    """Create a person and return its person_id."""
    r = client.post("/api/person", json={"name": name, "category": category})
    assert r.status_code == 200
    return r.get_json()["person_id"]
