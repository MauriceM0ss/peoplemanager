"""Setup, lock/unlock, reset, and PIN/session management routes."""
import math
import os
import secrets
import time

import bcrypt
from flask import (Blueprint, jsonify, redirect, render_template, request,
                   session as flask_session, url_for)

from .. import config
from ..db import _HAS_SQLCIPHER, _migrate_plain_to_encrypted, _sqlcipher, init_db
from ..security import (_derive_key, _get_session, _load_pin_config,
                        _save_pin_config, _sessions, _start_session,
                        require_unlock)

bp = Blueprint("auth", __name__)

# Brute-force throttle for the unlock screen. bcrypt already makes each guess
# slow; this adds an escalating cooldown after repeated failures so a short
# numeric PIN can't be ground down. Process-global (single-user app).
_MAX_FAILS = 5
_unlock_state = {"fails": 0, "locked_until": 0.0}


def _throttle_remaining() -> int:
    return max(0, math.ceil(_unlock_state["locked_until"] - time.time()))


def _register_unlock_failure() -> None:
    _unlock_state["fails"] += 1
    if _unlock_state["fails"] >= _MAX_FAILS:
        # 30s, 60s, 120s … capped at 15 min, based on how many lockouts so far.
        blocks = _unlock_state["fails"] // _MAX_FAILS
        cooldown = min(30 * (2 ** (blocks - 1)), 900)
        _unlock_state["locked_until"] = time.time() + cooldown


def _reset_unlock_throttle() -> None:
    _unlock_state["fails"] = 0
    _unlock_state["locked_until"] = 0.0


# Auto-lock choices, in minutes. 0 means "Never" — the unlock session then has
# no idle expiry and the browser never navigates to /lock on its own.
TIMEOUT_CHOICES = (0, 5, 15, 30, 60)


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if _load_pin_config():
        return redirect(url_for("pages.index"))
    if request.method == "GET":
        return render_template("setup.html")
    pin     = request.form.get("pin", "")
    confirm = request.form.get("confirm", "")
    if not (4 <= len(pin) <= 10):
        return render_template("setup.html", error="PIN must be 4–10 characters long.")
    if pin != confirm:
        return render_template("setup.html", error="PINs do not match.")
    try:
        timeout = int(request.form.get("timeout", 15))
        if timeout not in TIMEOUT_CHOICES:
            timeout = 15
    except ValueError:
        timeout = 15

    salt = secrets.token_bytes(32)
    key  = _derive_key(pin, salt)
    ph   = bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()

    _migrate_plain_to_encrypted(key)
    _save_pin_config({
        "pin_hash":        ph,
        "salt":            salt.hex(),
        "timeout_minutes": timeout,
    })
    _start_session(key)
    init_db()
    return redirect(url_for("pages.index"))


@bp.route("/lock", methods=["GET", "POST"])
def lock_screen():
    if not _load_pin_config():
        return redirect(url_for("auth.setup"))
    if request.method == "GET":
        return render_template("lock.html")

    remaining = _throttle_remaining()
    if remaining > 0:
        return render_template(
            "lock.html",
            error=f"Too many attempts. Try again in {remaining}s.",
        ), 429

    pin = request.form.get("pin", "")
    cfg = _load_pin_config()
    if not bcrypt.checkpw(pin.encode(), cfg["pin_hash"].encode()):
        _register_unlock_failure()
        remaining = _throttle_remaining()
        msg = (f"Too many attempts. Try again in {remaining}s."
               if remaining > 0 else "Incorrect PIN.")
        return render_template("lock.html", error=msg), (429 if remaining > 0 else 200)

    _reset_unlock_throttle()
    salt = bytes.fromhex(cfg["salt"])
    key  = _derive_key(pin, salt)
    _start_session(key)
    init_db()
    return redirect(request.args.get("next") or url_for("pages.index"))


@bp.route("/reset", methods=["GET", "POST"])
def reset_confirm():
    if not _load_pin_config():
        return redirect(url_for("auth.setup"))
    if request.method == "GET":
        return render_template("reset.html")
    if request.form.get("confirm", "").strip().upper() != "RESET":
        return render_template("reset.html", error="Type 'RESET' to confirm.")
    _sessions.clear()
    flask_session.clear()
    config._PIN_CONFIG.unlink(missing_ok=True)
    config.DB_PATH.unlink(missing_ok=True)
    return redirect(url_for("auth.setup"))


@bp.route("/api/lock", methods=["POST"])
@require_unlock
def do_lock():
    sid = flask_session.get("sid")
    if sid:
        _sessions.pop(sid, None)
    flask_session.clear()
    return jsonify({"ok": True})


@bp.route("/api/ping", methods=["POST"])
@require_unlock
def ping():
    # require_unlock refreshes the session's last_activity (or returns 403 if the
    # session has expired). The browser uses this as an auto-lock heartbeat.
    return jsonify({"ok": True})


@bp.route("/api/change-pin", methods=["POST"])
@require_unlock
def change_pin():
    data    = request.get_json() or {}
    old_pin = data.get("old_pin", "")
    new_pin = data.get("new_pin", "")
    if not (4 <= len(new_pin) <= 10):
        return jsonify({"error": "New PIN must be 4–10 characters long."}), 400
    cfg = _load_pin_config()
    if not bcrypt.checkpw(old_pin.encode(), cfg["pin_hash"].encode()):
        return jsonify({"error": "Current PIN is incorrect."}), 403

    sess     = _get_session()
    old_key  = sess["key"]
    new_salt = secrets.token_bytes(32)
    new_key  = _derive_key(new_pin, new_salt)

    if _HAS_SQLCIPHER and config.DB_PATH.exists():
        # Re-key: decrypt with old key, re-encrypt with new key
        tmp = config.DB_PATH.parent / "people_rekey.db"
        src = _sqlcipher.connect(str(config.DB_PATH))
        src.execute(f"PRAGMA key = \"x'{old_key}'\"")
        dump = "\n".join(src.iterdump())
        src.close()
        dst = _sqlcipher.connect(str(tmp))
        dst.execute(f"PRAGMA key = \"x'{new_key}'\"")
        dst.executescript(dump)
        dst.close()
        os.replace(str(tmp), str(config.DB_PATH))

    new_ph = bcrypt.hashpw(new_pin.encode(), bcrypt.gensalt()).decode()
    cfg["pin_hash"] = new_ph
    cfg["salt"]     = new_salt.hex()
    _save_pin_config(cfg)
    sess["key"] = new_key
    return jsonify({"ok": True})


@bp.route("/api/settings/timeout", methods=["POST"])
@require_unlock
def update_timeout():
    data = request.get_json() or {}
    try:
        minutes = int(data.get("minutes", 15))
    except (ValueError, TypeError):
        return jsonify({"error": "invalid"}), 400
    if minutes not in TIMEOUT_CHOICES:
        return jsonify({"error": "invalid"}), 400
    cfg = _load_pin_config()
    cfg["timeout_minutes"] = minutes
    _save_pin_config(cfg)
    return jsonify({"ok": True})
