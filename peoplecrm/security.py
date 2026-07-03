"""PIN configuration, key derivation, unlock sessions and the access guard."""
import hashlib
import json
import time
import uuid
from functools import wraps

from flask import (jsonify, redirect, request, session as flask_session,
                   url_for)

from . import config

# In-memory unlock sessions, stored server-side; the derived key never reaches
# the browser cookie. Keyed by a random sid held in the Flask session cookie.
_sessions: dict = {}  # sid -> {"key": str, "last_activity": float}


# ── PIN config on disk ────────────────────────────────────────────────────────
def _load_pin_config() -> dict | None:
    if not config._PIN_CONFIG.exists():
        return None
    try:
        return json.loads(config._PIN_CONFIG.read_text())
    except Exception:
        return None


def _save_pin_config(cfg: dict) -> None:
    config._PIN_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    config._PIN_CONFIG.write_text(json.dumps(cfg))


# ── key derivation ────────────────────────────────────────────────────────────
def _derive_key(pin: str, salt: bytes) -> str:
    """PBKDF2-HMAC-SHA256 → 32-byte raw key returned as hex string."""
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 260_000, dklen=32)
    return dk.hex()


def _key_pragma(key: str) -> str:
    """Return the SQLCipher PRAGMA key statement for a hex key."""
    return "PRAGMA key = \"x'" + key + "'\""


# ── sessions ──────────────────────────────────────────────────────────────────
def _get_session() -> dict | None:
    """Return the current unlock session, or None if locked/expired."""
    sid = flask_session.get("sid")
    if not sid or sid not in _sessions:
        return None
    sess = _sessions[sid]
    cfg  = _load_pin_config()
    timeout = (cfg or {}).get("timeout_minutes", 15) * 60
    if time.time() - sess["last_activity"] > timeout:
        _sessions.pop(sid, None)
        flask_session.clear()
        return None
    sess["last_activity"] = time.time()
    return sess


def _start_session(key: str) -> None:
    """Store a new unlock session and write the sid to the Flask cookie."""
    sid = str(uuid.uuid4())
    _sessions[sid] = {"key": key, "last_activity": time.time()}
    flask_session["sid"] = sid


# ── access guard ──────────────────────────────────────────────────────────────
def require_unlock(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        cfg    = _load_pin_config()
        is_api = request.path.startswith("/api/")
        if cfg is None:
            return (jsonify({"error": "setup required"}), 403) if is_api \
                   else redirect(url_for("auth.setup"))
        if _get_session() is None:
            return (jsonify({"error": "locked"}), 403) if is_api \
                   else redirect(url_for("auth.lock_screen"))
        return f(*args, **kwargs)
    return decorated
