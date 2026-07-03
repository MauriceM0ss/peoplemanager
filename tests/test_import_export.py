"""Characterization tests for the encrypted export / import round-trip."""
import io

from conftest import make_person


def test_export_returns_plain_sqlite(auth_client):
    make_person(auth_client, "Erin", "Work")
    r = auth_client.get("/api/export")
    assert r.status_code == 200
    # export is decrypted to a plain SQLite file
    assert r.data[:16] == b"SQLite format 3\x00"


def test_import_round_trip_preserves_data(auth_client):
    make_person(auth_client, "Frank", "Family")
    blob = auth_client.get("/api/export").data

    # wipe Frank, then re-import the earlier snapshot
    tree = auth_client.get("/api/tree").get_json()
    fam = next(c for c in tree if c["category"] == "Family")
    pid = next(p["id"] for p in fam["people"] if p["name"] == "Frank")
    auth_client.delete(f"/api/person/{pid}")

    r = auth_client.post(
        "/api/import",
        data={"db": (io.BytesIO(blob), "people.db")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    names = [p["name"] for cat in auth_client.get("/api/tree").get_json()
             for p in cat["people"]]
    assert "Frank" in names


def test_import_rejects_non_sqlite(auth_client):
    r = auth_client.post(
        "/api/import",
        data={"db": (io.BytesIO(b"not a database at all"), "bad.db")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
