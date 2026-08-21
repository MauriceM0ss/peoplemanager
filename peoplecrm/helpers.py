"""Pure helpers, people aggregation, and Jinja template filters."""
import re
from datetime import date

from .db import get_db

# ── formatting ────────────────────────────────────────────────────────────────
def human_size(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def normalize_id(name: str) -> str:
    s = name.lower()
    for ch, rep in [("ë", "e"), ("ä", "a"), ("ö", "o"), ("ü", "u"), ("é", "e"),
                    ("è", "e"), ("ï", "i"), ("-", " ")]:
        s = s.replace(ch, rep)
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return re.sub(r"\s+", "_", s.strip())


# ── queries ───────────────────────────────────────────────────────────────────
def get_categories() -> list[str]:
    """Categories in the user's manual order (Settings → Categories)."""
    conn = get_db()
    rows = conn.execute("SELECT name FROM categories ORDER BY position, name").fetchall()
    conn.close()
    return [r["name"] for r in rows]


def parse_people() -> list[dict]:
    conn = get_db()
    db_persons = conn.execute("SELECT person_id, name, category FROM persons").fetchall()
    hidden = {r["person_id"] for r in conn.execute("SELECT person_id FROM hidden_persons").fetchall()}
    overrides = {r["person_id"]: r for r in conn.execute(
        "SELECT person_id, name, category FROM person_overrides").fetchall()}
    meeting_stats = {r["person_id"]: r for r in conn.execute(
        "SELECT person_id, COUNT(*) as cnt, MAX(meeting_date) as last_date "
        "FROM meetings GROUP BY person_id").fetchall()}
    conn.close()

    result = []
    for row in db_persons:
        pid = row["person_id"]
        if pid in hidden:
            continue
        p = {"id": pid, "name": row["name"], "category": row["category"],
             "details": "", "profile": "", "meetings": []}
        ov = overrides.get(pid)
        if ov:
            if ov["name"]:     p["name"]     = ov["name"]
            if ov["category"]: p["category"] = ov["category"]
        stats = meeting_stats.get(pid)
        p["meeting_count"] = stats["cnt"] if stats else 0
        if stats and stats["last_date"]:
            try:
                p["last_meeting"] = date.fromisoformat(stats["last_date"])
            except ValueError:
                p["last_meeting"] = None
        else:
            p["last_meeting"] = None
        result.append(p)

    result.sort(key=lambda p: p["name"].lower())
    return result


# ── template filters ──────────────────────────────────────────────────────────
_PALETTE = [
    "#4f46e5", "#7c3aed", "#db2777", "#dc2626",
    "#d97706", "#059669", "#0284c7", "#0891b2",
    "#7c2d12", "#166534", "#1e3a5f", "#4a044e",
]


def stable_hash(s: str) -> int:
    """Deterministic 32-bit string hash, mirrored by hashColor() in base.html.

    Python's built-in hash() is salted per process, so the same name picked a
    different colour after every restart — and the browser could never derive
    the matching colour when it repaints a badge without a page reload.
    """
    h = 0
    for ch in s:
        h = (31 * h + ord(ch)) & 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    return h


def initials_color(person_id: str) -> str:
    return _PALETTE[abs(stable_hash(person_id)) % len(_PALETTE)]


def category_color(name: str) -> str:
    return _PALETTE[abs(stable_hash(name)) % len(_PALETTE)]


def pretty_date(iso: str) -> str:
    """'2024-03-12' -> '12 Mar 2024'. Blank or unparseable input yields ''."""
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso).strftime("%d %b %Y")
    except (ValueError, TypeError):
        return ""


def doc_icon(ext: str) -> str:
    if ext in {'xls', 'xlsx', 'ods', 'csv'}:   return '📊'
    if ext in {'doc', 'docx', 'odt', 'rtf'}:   return '📝'
    if ext in {'ppt', 'pptx', 'odp'}:          return '📑'
    if ext == 'pdf':                           return '📋'
    return '📄'


def register_filters(app):
    app.template_filter("initials_color")(initials_color)
    app.template_filter("category_color")(category_color)
    app.template_filter("doc_icon")(doc_icon)
    app.template_filter("pretty_date")(pretty_date)
