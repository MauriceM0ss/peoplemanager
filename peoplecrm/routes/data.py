"""Encrypted database export and import."""
import io
import os
import sqlite3

from flask import Blueprint, abort, jsonify, request, send_file

from .. import config
from ..db import _HAS_SQLCIPHER, _sqlcipher, get_db
from ..security import (_get_session, _key_pragma, _load_pin_config,
                        require_unlock)

bp = Blueprint("data", __name__)


@bp.route("/api/export")
@require_unlock
def export_db():
    if not config.DB_PATH.exists():
        abort(404)

    tmp = config.DB_PATH.parent / "people_export.db"
    tmp.unlink(missing_ok=True)

    try:
        cfg = _load_pin_config()
        if cfg and _HAS_SQLCIPHER:
            # Decrypt encrypted DB into a plain SQLite temp file, then read into memory.
            # Using ATTACH + sqlcipher_export avoids the BLOB-in-SQL-string issues of iterdump().
            sess = _get_session()
            enc = _sqlcipher.connect(str(config.DB_PATH))
            enc.execute(_key_pragma(sess["key"]))
            enc.execute(f"ATTACH DATABASE '{tmp}' AS plaintext KEY ''")
            enc.execute("SELECT sqlcipher_export('plaintext')")
            enc.execute("DETACH DATABASE plaintext")
            enc.close()
        else:
            conn = get_db()
            conn.execute(f"VACUUM INTO '{tmp}'")
            conn.close()

        file_bytes = tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)

    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=True,
        download_name="people.db",
        mimetype="application/x-sqlite3",
    )


@bp.route("/api/import", methods=["POST"])
@require_unlock
def import_db():
    if "db" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    data = request.files["db"].read()
    if len(data) < 16 or data[:16] != b"SQLite format 3\x00":
        return jsonify({"error": "Invalid file (not a SQLite database)"}), 400

    tmp_plain = config.DB_PATH.parent / "people_import_plain.db"
    tmp_plain.write_bytes(data)

    try:
        test = sqlite3.connect(str(tmp_plain))
        test.execute("SELECT 1 FROM sqlite_master")
        test.close()
    except Exception as e:
        tmp_plain.unlink(missing_ok=True)
        return jsonify({"error": f"Invalid file: {e}"}), 400

    cfg = _load_pin_config()
    if cfg and _HAS_SQLCIPHER:
        # Encrypt the imported plain file before replacing
        sess    = _get_session()
        tmp_enc = config.DB_PATH.parent / "people_import_enc.db"
        try:
            plain = sqlite3.connect(str(tmp_plain))
            dump  = "\n".join(plain.iterdump())
            plain.close()
            enc = _sqlcipher.connect(str(tmp_enc))
            enc.execute(_key_pragma(sess["key"]))
            enc.executescript(dump)
            enc.close()
            os.replace(str(tmp_enc), str(config.DB_PATH))
        except Exception as e:
            tmp_enc.unlink(missing_ok=True)
            tmp_plain.unlink(missing_ok=True)
            return jsonify({"error": f"Error during encryption: {e}"}), 500
        finally:
            tmp_plain.unlink(missing_ok=True)
    else:
        os.replace(str(tmp_plain), str(config.DB_PATH))

    return jsonify({"ok": True})
