"""Tests for the Step-2 hardening fixes."""
import io

from conftest import make_person

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
SVG = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"


def _upload(client, url, field, filename, data, content_type):
    return client.post(
        url,
        data={field: (io.BytesIO(data), filename, content_type)},
        content_type="multipart/form-data",
    )


# ── F1: CSRF / origin guard ──────────────────────────────────────────────────
def test_cross_origin_post_blocked(auth_client):
    r = auth_client.post("/api/person", json={"name": "Mallory"},
                         headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert "cross-origin" in r.get_json()["error"]


def test_same_origin_post_allowed(auth_client):
    # test client Host is "localhost"; matching Origin passes
    r = auth_client.post("/api/person", json={"name": "Trusty"},
                         headers={"Origin": "http://localhost"})
    assert r.status_code == 200


def test_no_origin_header_allowed(auth_client):
    # non-browser tooling sends no Origin/Referer — still allowed
    assert make_person(auth_client, "Toolbot")


def test_safe_get_not_blocked_by_origin(auth_client):
    r = auth_client.get("/api/tree", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200


def test_nosniff_header_present(auth_client):
    r = auth_client.get("/api/tree")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


# ── F2: image mimetype hardening ─────────────────────────────────────────────
def test_photo_html_mimetype_is_coerced_not_reflected(auth_client):
    pid = make_person(auth_client)
    # attacker sets text/html but the extension is .jpg → served as image/jpeg
    assert _upload(auth_client, f"/api/photo/{pid}", "photo",
                   "x.jpg", PNG, "text/html").status_code == 200
    r = auth_client.get(f"/api/photo/{pid}")
    assert r.status_code == 200
    assert r.mimetype == "image/jpeg"
    assert "html" not in r.headers["Content-Type"]


def test_photo_svg_rejected(auth_client):
    pid = make_person(auth_client)
    r = _upload(auth_client, f"/api/photo/{pid}", "photo",
                "evil.svg", SVG, "image/svg+xml")
    assert r.status_code == 415


def test_picture_svg_rejected(auth_client):
    pid = make_person(auth_client)
    r = _upload(auth_client, f"/api/picture/{pid}", "file",
                "evil.svg", SVG, "image/svg+xml")
    assert r.status_code == 415


def test_picture_pasted_png_without_ext_allowed(auth_client):
    pid = make_person(auth_client)
    # a pasted screenshot: no extension but a trustworthy raster mimetype
    r = _upload(auth_client, f"/api/picture/{pid}", "file",
                "", PNG, "image/png")
    assert r.status_code == 200


# ── F3: upload size limit ────────────────────────────────────────────────────
def test_upload_over_limit_rejected(auth_client):
    pid = make_person(auth_client)
    auth_client.application.config["MAX_CONTENT_LENGTH"] = 100
    r = _upload(auth_client, f"/api/photo/{pid}", "photo",
                "big.jpg", b"x" * 500, "image/jpeg")
    assert r.status_code == 413


# ── F4: unlock brute-force cooldown ──────────────────────────────────────────
def test_unlock_cooldown_after_repeated_failures(auth_client, appmod):
    auth_client.post("/api/lock")  # lock first
    # five wrong PINs trip the cooldown
    for _ in range(5):
        auth_client.post("/lock", data={"pin": "0000"})
    # even the correct PIN is now refused during the cooldown window
    r = auth_client.post("/lock", data={"pin": "1234"})
    assert r.status_code == 429
    assert b"Too many attempts" in r.data
