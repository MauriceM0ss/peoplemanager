"""People Viewer — application factory."""
import logging
import secrets
import time
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

from . import config
from .helpers import register_filters
from .security import _load_pin_config

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_logger = logging.getLogger("peoplecrm")


def _configure_logging() -> None:
    if _logger.handlers:  # idempotent across app rebuilds / reloads
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [peoplecrm] %(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)


def _get_or_create_secret() -> bytes:
    """Persistent secret key so sessions survive container restarts."""
    p = config.DB_PATH.parent / "app_secret.key"
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        return p.read_bytes()
    k = secrets.token_bytes(32)
    p.write_bytes(k)
    return k


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(config.TEMPLATE_DIR),
        static_folder=str(config.STATIC_DIR),
    )
    app.secret_key = _get_or_create_secret()
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024

    _configure_logging()
    register_filters(app)

    @app.route("/healthz")
    def _healthz():
        # Liveness probe: no PIN/DB required, so it works while locked.
        return {"status": "ok"}, 200

    @app.before_request
    def _start_timer():
        g._start = time.monotonic()

    @app.after_request
    def _access_log(resp):
        if request.path != "/healthz":  # don't spam on the healthcheck poll
            dur_ms = (time.monotonic() - getattr(g, "_start", time.monotonic())) * 1000
            _logger.info("%s %s -> %s (%.0f ms)",
                         request.method, request.full_path.rstrip("?"),
                         resp.status_code, dur_ms)
        return resp

    @app.errorhandler(Exception)
    def _handle_error(exc):
        if isinstance(exc, HTTPException):
            return exc  # preserve 4xx/redirect behaviour unchanged
        _logger.exception("Unhandled error on %s %s", request.method, request.path)
        return jsonify({"error": "internal server error"}), 500

    @app.before_request
    def _csrf_origin_guard():
        """Reject unsafe cross-origin requests (defence in depth over SameSite).

        A browser always sends Origin on cross-origin POST/PUT/PATCH/DELETE and
        cannot be forced to omit it, so a mismatch means a forged cross-site
        request. Requests without an Origin (non-browser tooling, same-origin
        form posts on older clients) fall back to a Referer check and are
        otherwise allowed.
        """
        if request.method not in _UNSAFE_METHODS:
            return None
        origin = request.headers.get("Origin")
        source = origin or request.headers.get("Referer")
        if not source:
            return None
        if urlsplit(source).netloc != request.host:
            return jsonify({"error": "cross-origin request blocked"}), 403
        return None

    @app.after_request
    def _security_headers(resp):
        # Stop browsers MIME-sniffing served blobs into active content.
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        return resp

    @app.context_processor
    def _inject_security():
        cfg = _load_pin_config()
        return {
            "pin_enabled":     cfg is not None,
            "timeout_minutes": (cfg or {}).get("timeout_minutes", 15),
        }

    from .routes import BLUEPRINTS
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)

    return app
