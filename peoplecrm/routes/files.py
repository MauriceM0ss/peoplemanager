"""Upload / download / delete for photos, documents and pictures."""
import io
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file

from ..config import ALLOWED_DOC_EXTS, _TEXT_PREVIEW_EXTS, safe_image_mime
from ..db import get_db
from ..security import require_unlock

bp = Blueprint("files", __name__)


# ── photos ────────────────────────────────────────────────────────────────────
@bp.route("/api/photo/<person_id>")
@require_unlock
def get_photo(person_id):
    conn = get_db()
    row  = conn.execute("SELECT photo_data, mimetype FROM photos WHERE person_id = ?",
                        (person_id,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    return send_file(io.BytesIO(row["photo_data"]), mimetype=row["mimetype"])


@bp.route("/api/photo/<person_id>", methods=["POST"])
@require_unlock
def upload_photo(person_id):
    if "photo" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f    = request.files["photo"]
    # Derive the served Content-Type from the extension allowlist rather than
    # trusting the client mimetype, so the image can't be replayed as active
    # content (stored XSS) when served inline by get_photo.
    mime = safe_image_mime(f.filename, f.mimetype)
    if mime is None:
        return jsonify({"error": "Not an allowed image type"}), 415
    data = f.read()
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO photos (person_id, photo_data, mimetype) VALUES (?,?,?)",
                 (person_id, data, mime))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.route("/api/photo/<person_id>", methods=["DELETE"])
@require_unlock
def delete_photo(person_id):
    conn = get_db()
    conn.execute("DELETE FROM photos WHERE person_id = ?", (person_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── documents ─────────────────────────────────────────────────────────────────
@bp.route("/api/document/<person_id>", methods=["POST"])
@require_unlock
def upload_document(person_id):
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_DOC_EXTS:
        return jsonify({"error": "File type not allowed"}), 415
    data = f.read()
    mime = f.mimetype or "application/octet-stream"
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO documents (person_id, filename, data, mimetype, size) VALUES (?,?,?,?,?)",
        (person_id, f.filename, data, mime, len(data)))
    doc_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "id": doc_id})


@bp.route("/api/document/<int:doc_id>")
@require_unlock
def download_document(doc_id):
    conn = get_db()
    row = conn.execute("SELECT filename, data, mimetype FROM documents WHERE id = ?",
                       (doc_id,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    return send_file(io.BytesIO(row["data"]), mimetype=row["mimetype"],
                     as_attachment=True, download_name=row["filename"])


@bp.route("/api/document/<int:doc_id>/preview")
@require_unlock
def preview_document(doc_id):
    conn = get_db()
    row = conn.execute("SELECT filename, data, mimetype FROM documents WHERE id = ?",
                       (doc_id,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    ext = Path(row["filename"]).suffix.lower()
    if ext in _TEXT_PREVIEW_EXTS:
        return send_file(io.BytesIO(row["data"]), mimetype="text/plain; charset=utf-8")
    if ext == ".pdf":
        return send_file(io.BytesIO(row["data"]), mimetype="application/pdf")
    abort(415)


@bp.route("/api/document/<int:doc_id>", methods=["DELETE"])
@require_unlock
def delete_document(doc_id):
    conn = get_db()
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── pictures ──────────────────────────────────────────────────────────────────
@bp.route("/api/picture/<person_id>", methods=["POST"])
@require_unlock
def upload_picture(person_id):
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f    = request.files["file"]
    # Served inline by get_picture, so pin the Content-Type to a safe raster
    # type from the extension/allowlist (excludes SVG and non-image types).
    mime = safe_image_mime(f.filename, f.mimetype)
    if mime is None:
        return jsonify({"error": "Not an allowed image type"}), 415
    data = f.read()
    conn = get_db()
    cur  = conn.execute(
        "INSERT INTO pictures (person_id, filename, data, mimetype, size) VALUES (?,?,?,?,?)",
        (person_id, f.filename or "screenshot.png", data, mime, len(data)))
    pic_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "id": pic_id})


@bp.route("/api/picture/<int:pic_id>")
@require_unlock
def get_picture(pic_id):
    conn = get_db()
    row  = conn.execute("SELECT data, mimetype FROM pictures WHERE id = ?", (pic_id,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    return send_file(io.BytesIO(row["data"]), mimetype=row["mimetype"])


@bp.route("/api/picture/<int:pic_id>", methods=["DELETE"])
@require_unlock
def delete_picture(pic_id):
    conn = get_db()
    conn.execute("DELETE FROM pictures WHERE id = ?", (pic_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})
