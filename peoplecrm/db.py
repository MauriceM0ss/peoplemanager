"""Database access — opens the plain or SQLCipher-encrypted connection."""
import os
import sqlite3

from flask import abort

from . import config
from .security import _get_session, _key_pragma, _load_pin_config

try:
    import sqlcipher3.dbapi2 as _sqlcipher
    _HAS_SQLCIPHER = True
except ImportError:
    _sqlcipher = None
    _HAS_SQLCIPHER = False


def get_db():
    """Open a connection to the people database.

    When a PIN is configured and SQLCipher is available the connection is
    keyed with the active session's derived key; otherwise a plain SQLite
    connection is returned (pre-setup / migration).
    """
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg = _load_pin_config()
    if cfg and _HAS_SQLCIPHER:
        sess = _get_session()
        if not sess:
            abort(403)
        conn = _sqlcipher.connect(str(config.DB_PATH))
        conn.execute(_key_pragma(sess["key"]))
        conn.row_factory = _sqlcipher.Row
        return conn
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS photos (
        person_id TEXT PRIMARY KEY,
        photo_data BLOB,
        mimetype   TEXT DEFAULT 'image/jpeg',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS meetings (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id    TEXT NOT NULL,
        title        TEXT NOT NULL,
        content      TEXT NOT NULL DEFAULT '',
        meeting_date TEXT,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS person_overrides (
        person_id  TEXT PRIMARY KEY,
        details    TEXT,
        profile    TEXT,
        name       TEXT,
        category   TEXT,
        start_date TEXT,
        birth_date TEXT,
        role       TEXT,
        grade      TEXT,
        status     TEXT,
        experience_years   TEXT,
        experience_as_of   TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    for col in ("name", "category") + config.STORED_PROFILE_FIELDS:
        try:
            conn.execute(f"ALTER TABLE person_overrides ADD COLUMN {col} TEXT")
        except Exception:
            pass
    conn.execute("""CREATE TABLE IF NOT EXISTS persons (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id  TEXT UNIQUE NOT NULL,
        name       TEXT NOT NULL,
        category   TEXT NOT NULL DEFAULT 'Other',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS hidden_persons (
        person_id TEXT PRIMARY KEY
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id  TEXT NOT NULL,
        text       TEXT NOT NULL,
        done       INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS notes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id  TEXT NOT NULL,
        content    TEXT NOT NULL DEFAULT '',
        note_date  TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS categories (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        name     TEXT UNIQUE NOT NULL,
        position INTEGER NOT NULL DEFAULT 0
    )""")
    try:
        conn.execute("ALTER TABLE categories ADD COLUMN position INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass
    conn.execute("""CREATE TABLE IF NOT EXISTS documents (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id   TEXT NOT NULL,
        filename    TEXT NOT NULL,
        data        BLOB NOT NULL,
        mimetype    TEXT NOT NULL DEFAULT 'application/octet-stream',
        size        INTEGER NOT NULL DEFAULT 0,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS pictures (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id   TEXT NOT NULL,
        filename    TEXT NOT NULL,
        data        BLOB NOT NULL,
        mimetype    TEXT NOT NULL DEFAULT 'image/png',
        size        INTEGER NOT NULL DEFAULT 0,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    if not conn.execute("SELECT 1 FROM categories").fetchone():
        for pos, cat in enumerate(("Friends", "Family", "Work", "Other")):
            conn.execute("INSERT OR IGNORE INTO categories (name, position) VALUES (?,?)",
                         (cat, pos))
    # Databases created before the column existed have every position at 0;
    # seed the manual order from the old alphabetical one so nothing jumps.
    elif not conn.execute("SELECT 1 FROM categories WHERE position != 0").fetchone():
        rows = conn.execute("SELECT id FROM categories ORDER BY name").fetchall()
        for pos, row in enumerate(rows):
            conn.execute("UPDATE categories SET position=? WHERE id=?", (pos, row["id"]))
    conn.commit()
    conn.close()


def _migrate_plain_to_encrypted(key: str) -> None:
    """Convert an existing plain SQLite DB to SQLCipher format in-place."""
    if not config.DB_PATH.exists() or not _HAS_SQLCIPHER:
        return
    plain = sqlite3.connect(str(config.DB_PATH))
    dump  = "\n".join(plain.iterdump())
    plain.close()

    tmp = config.DB_PATH.parent / "people_enc.db"
    enc = _sqlcipher.connect(str(tmp))
    enc.execute(f"PRAGMA key = \"x'{key}'\"")
    enc.executescript(dump)
    enc.close()
    os.replace(str(tmp), str(config.DB_PATH))
