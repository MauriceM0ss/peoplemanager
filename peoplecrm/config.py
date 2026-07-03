"""Paths and static configuration, resolved from the environment at import."""
import os
from pathlib import Path

# Repository root (one level above this package) — templates and static assets
# live there, alongside app.py.
ROOT_DIR      = Path(__file__).resolve().parent.parent
TEMPLATE_DIR  = ROOT_DIR / "templates"
STATIC_DIR    = ROOT_DIR / "static"

DB_PATH     = Path(os.environ.get("DB_PATH",    "/data/people.db"))
_PIN_CONFIG = Path(os.environ.get("PIN_CONFIG", "/data/pin.json"))

ALLOWED_DOC_EXTS = {
    '.txt', '.md', '.log', '.csv', '.rtf', '.json', '.xml', '.yaml', '.yml',
    '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.odt', '.ods', '.odp', '.pdf',
}

ALLOWED_IMG_EXTS = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.heic', '.heif',
}

# Raster-image types that are safe to serve inline. The served Content-Type is
# derived from the extension via this map (never trusted from the client), so a
# file uploaded with a text/html or image/svg+xml mimetype can't be replayed as
# active content — SVG is deliberately excluded because it can carry script.
IMG_MIME_BY_EXT = {
    '.png':  'image/png',
    '.jpg':  'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif':  'image/gif',
    '.webp': 'image/webp',
    '.bmp':  'image/bmp',
    '.heic': 'image/heic',
    '.heif': 'image/heif',
}
SAFE_IMG_MIMES = set(IMG_MIME_BY_EXT.values())

_TEXT_PREVIEW_EXTS = {
    '.txt', '.md', '.log', '.csv', '.json', '.xml', '.yaml', '.yml', '.rtf',
}

# Maximum accepted request body (uploads are read fully into memory / the DB).
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "32"))


def safe_image_mime(filename: str, client_mime: str) -> str | None:
    """Return a safe inline image Content-Type, or None if not an allowed image.

    Prefers the extension; falls back to the client mimetype only when it is a
    known-safe raster type. SVG / HTML / unknown types return None.
    """
    from pathlib import Path
    ext = Path(filename or "").suffix.lower()
    if ext in IMG_MIME_BY_EXT:
        return IMG_MIME_BY_EXT[ext]
    if client_mime in SAFE_IMG_MIMES:
        return client_mime
    return None
