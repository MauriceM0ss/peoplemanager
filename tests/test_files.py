"""Characterization tests for photo / document / picture upload routes."""
import io

from conftest import make_person

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _upload(client, url, field, filename, data, content_type):
    return client.post(
        url,
        data={field: (io.BytesIO(data), filename, content_type)},
        content_type="multipart/form-data",
    )


# ── photos ─────────────────────────────────────────────────────────────────
def test_photo_upload_get_delete(auth_client):
    pid = make_person(auth_client)
    assert _upload(auth_client, f"/api/photo/{pid}", "photo",
                   "me.jpg", PNG, "image/jpeg").status_code == 200
    r = auth_client.get(f"/api/photo/{pid}")
    assert r.status_code == 200 and r.data == PNG
    assert auth_client.delete(f"/api/photo/{pid}").status_code == 200
    assert auth_client.get(f"/api/photo/{pid}").status_code == 404


def test_photo_missing_file(auth_client):
    pid = make_person(auth_client)
    assert auth_client.post(f"/api/photo/{pid}", data={}).status_code == 400


# ── documents ──────────────────────────────────────────────────────────────
def test_document_upload_download_delete(auth_client):
    pid = make_person(auth_client)
    r = _upload(auth_client, f"/api/document/{pid}", "file",
                "notes.txt", b"hello world", "text/plain")
    assert r.status_code == 200
    doc_id = r.get_json()["id"]
    dl = auth_client.get(f"/api/document/{doc_id}")
    assert dl.status_code == 200 and dl.data == b"hello world"
    prev = auth_client.get(f"/api/document/{doc_id}/preview")
    assert prev.status_code == 200
    assert auth_client.delete(f"/api/document/{doc_id}").status_code == 200


def test_document_rejects_disallowed_ext(auth_client):
    pid = make_person(auth_client)
    r = _upload(auth_client, f"/api/document/{pid}", "file",
                "evil.exe", b"MZ", "application/octet-stream")
    assert r.status_code == 415


# ── pictures ───────────────────────────────────────────────────────────────
def test_picture_upload_get_delete(auth_client):
    pid = make_person(auth_client)
    r = _upload(auth_client, f"/api/picture/{pid}", "file",
                "shot.png", PNG, "image/png")
    assert r.status_code == 200
    pic_id = r.get_json()["id"]
    assert auth_client.get(f"/api/picture/{pic_id}").data == PNG
    assert auth_client.delete(f"/api/picture/{pic_id}").status_code == 200


def test_picture_rejects_non_image(auth_client):
    pid = make_person(auth_client)
    r = _upload(auth_client, f"/api/picture/{pid}", "file",
                "note.txt", b"nope", "text/plain")
    assert r.status_code == 415
