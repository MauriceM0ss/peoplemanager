"""CRUD for persons, meetings, tasks, notes and categories."""
from datetime import date

from flask import Blueprint, jsonify, request

from .. import config
from ..db import get_db
from ..helpers import get_categories, normalize_id
from ..security import require_unlock

bp = Blueprint("records", __name__)


# ── persons ───────────────────────────────────────────────────────────────────
@bp.route("/api/person", methods=["POST"])
@require_unlock
def create_person():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    category = data.get("category", "Other")
    pid      = normalize_id(name)
    conn = get_db()
    try:
        conn.execute("INSERT INTO persons (person_id, name, category) VALUES (?,?,?)",
                     (pid, name, category))
        conn.commit()
    except Exception:
        pass
    conn.close()
    return jsonify({"ok": True, "person_id": pid})


@bp.route("/api/person/<person_id>", methods=["DELETE"])
@require_unlock
def delete_person(person_id):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO hidden_persons (person_id) VALUES (?)", (person_id,))
    conn.execute("DELETE FROM persons          WHERE person_id = ?", (person_id,))
    conn.execute("DELETE FROM meetings         WHERE person_id = ?", (person_id,))
    conn.execute("DELETE FROM person_overrides WHERE person_id = ?", (person_id,))
    conn.execute("DELETE FROM photos           WHERE person_id = ?", (person_id,))
    conn.execute("DELETE FROM notes            WHERE person_id = ?", (person_id,))
    conn.execute("DELETE FROM documents        WHERE person_id = ?", (person_id,))
    conn.execute("DELETE FROM pictures         WHERE person_id = ?", (person_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


ALLOWED_FIELDS = ("details", "profile", "name", "category") + config.PROFILE_FIELD_NAMES


def _validate_field(field: str, content):
    """Return an error message for a bad value, or None when it is acceptable.

    Everything is stored as text and "" always means "not set", so clearing a
    field is never rejected.
    """
    if not isinstance(content, str):
        return f"{field} must be a string"
    content = content.strip()
    if not content:
        return None
    if field in config.PROFILE_DATE_FIELDS:
        try:
            date.fromisoformat(content)
        except ValueError:
            label = "Start date" if field == "start_date" else "Birth date"
            return f"{label} must be a date in YYYY-MM-DD format"
    elif field == "grade" and content not in config.GRADES:
        return "Grade must be one of: " + ", ".join(config.GRADES)
    elif field == "status" and content not in config.STATUSES:
        return "Status must be one of: " + ", ".join(config.STATUSES)
    return None


@bp.route("/api/person/<person_id>", methods=["PUT"])
@require_unlock
def update_person(person_id):
    """Update one field ({"field": ..., "content": ...}) or several at once
    ({"fields": {name: content, ...}}).

    The batch form exists so the edit dialog saves in a single request: nine
    parallel single-field PUTs would each open their own SQLCipher connection
    and contend for the write lock.
    """
    data = request.get_json() or {}
    if "fields" in data:
        updates = data["fields"]
        if not isinstance(updates, dict) or not updates:
            return jsonify({"error": "fields must be a non-empty object"}), 400
    elif "field" in data:
        updates = {data["field"]: data.get("content", "")}
    else:
        return jsonify({"error": "field or fields required"}), 400

    for field, content in updates.items():
        if field not in ALLOWED_FIELDS:
            return jsonify({"error": f"field must be one of {ALLOWED_FIELDS}"}), 400
        err = _validate_field(field, content)
        if err:
            return jsonify({"error": err}), 400

    conn = get_db()
    for field, content in updates.items():
        if field in config.PROFILE_FIELD_NAMES:
            content = content.strip()
        conn.execute(
            f"""INSERT INTO person_overrides (person_id, {field})
                VALUES (?, ?)
                ON CONFLICT(person_id) DO UPDATE SET {field}=excluded.{field},
                    updated_at=CURRENT_TIMESTAMP""",
            (person_id, content))
        if field in ("name", "category"):
            conn.execute(f"UPDATE persons SET {field}=? WHERE person_id=?", (content, person_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── meetings ──────────────────────────────────────────────────────────────────
@bp.route("/api/meeting/<person_id>", methods=["POST"])
@require_unlock
def add_meeting(person_id):
    data = request.get_json() or {}
    if not data.get("title"):
        return jsonify({"error": "title required"}), 400
    conn = get_db()
    cur  = conn.execute(
        "INSERT INTO meetings (person_id, title, content, meeting_date) VALUES (?,?,?,?)",
        (person_id, data["title"], data.get("content", ""), data.get("date") or None))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({"ok": True, "id": new_id})


@bp.route("/api/meeting/<int:meeting_id>", methods=["DELETE"])
@require_unlock
def delete_meeting(meeting_id):
    conn = get_db()
    conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── categories ────────────────────────────────────────────────────────────────
@bp.route("/api/categories", methods=["GET"])
@require_unlock
def list_categories():
    return jsonify(get_categories())


@bp.route("/api/categories", methods=["POST"])
@require_unlock
def add_category():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    conn = get_db()
    try:
        nxt = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 AS n FROM categories").fetchone()["n"]
        conn.execute("INSERT INTO categories (name, position) VALUES (?,?)", (name, nxt))
        conn.commit()
    except Exception:
        conn.close()
        return jsonify({"error": "already exists"}), 409
    conn.close()
    return jsonify({"ok": True})


@bp.route("/api/categories/reorder", methods=["POST"])
@require_unlock
def reorder_categories():
    """Persist the manual category order set in Settings -> Categories."""
    data  = request.get_json() or {}
    order = data.get("order")
    if not isinstance(order, list) or not all(isinstance(n, str) for n in order):
        return jsonify({"error": "order must be a list of category names"}), 400
    conn     = get_db()
    known    = {r["name"] for r in conn.execute("SELECT name FROM categories").fetchall()}
    seen     = []
    for name in order:
        if name in known and name not in seen:
            seen.append(name)
    # Anything the client did not mention keeps its relative place at the end.
    rest = [r["name"] for r in conn.execute(
        "SELECT name FROM categories ORDER BY position, name").fetchall() if r["name"] not in seen]
    for pos, name in enumerate(seen + rest):
        conn.execute("UPDATE categories SET position=? WHERE name=?", (pos, name))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "order": seen + rest})


@bp.route("/api/categories/<path:name>", methods=["PUT"])
@require_unlock
def rename_category(name):
    data     = request.get_json() or {}
    new_name = data.get("new_name", "").strip()
    if not new_name:
        return jsonify({"error": "new_name required"}), 400
    conn = get_db()
    try:
        conn.execute("UPDATE categories SET name=? WHERE name=?", (new_name, name))
        conn.execute("UPDATE persons          SET category=? WHERE category=?", (new_name, name))
        conn.execute("UPDATE person_overrides SET category=? WHERE category=?", (new_name, name))
        conn.commit()
    except Exception:
        conn.close()
        return jsonify({"error": "name already exists"}), 409
    conn.close()
    return jsonify({"ok": True})


@bp.route("/api/categories/<path:name>", methods=["DELETE"])
@require_unlock
def delete_category(name):
    conn = get_db()
    cats = [r["name"] for r in conn.execute(
        "SELECT name FROM categories WHERE name != ? ORDER BY position, name", (name,)).fetchall()]
    fallback = cats[0] if cats else "Other"
    conn.execute("UPDATE persons          SET category=? WHERE category=?", (fallback, name))
    conn.execute("UPDATE person_overrides SET category=? WHERE category=?", (fallback, name))
    conn.execute("DELETE FROM categories WHERE name=?", (name,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "fallback": fallback})


# ── tasks ─────────────────────────────────────────────────────────────────────
@bp.route("/api/task/<person_id>", methods=["POST"])
@require_unlock
def add_task(person_id):
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    conn = get_db()
    cur  = conn.execute("INSERT INTO tasks (person_id, text) VALUES (?,?)", (person_id, text))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({"ok": True, "id": new_id})


@bp.route("/api/task/<int:task_id>", methods=["PATCH"])
@require_unlock
def toggle_task(task_id):
    data = request.get_json() or {}
    done = 1 if data.get("done") else 0
    conn = get_db()
    conn.execute("UPDATE tasks SET done=? WHERE id=?", (done, task_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.route("/api/task/<int:task_id>", methods=["DELETE"])
@require_unlock
def delete_task(task_id):
    conn = get_db()
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── notes ─────────────────────────────────────────────────────────────────────
@bp.route("/api/note/<person_id>", methods=["POST"])
@require_unlock
def add_note(person_id):
    data = request.get_json() or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "content required"}), 400
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO notes (person_id, content, note_date) VALUES (?,?,?)",
        (person_id, content, data.get("date") or None))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({"ok": True, "id": new_id})


@bp.route("/api/note/<int:note_id>", methods=["PUT"])
@require_unlock
def update_note(note_id):
    data = request.get_json() or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "content required"}), 400
    conn = get_db()
    conn.execute("UPDATE notes SET content=?, note_date=? WHERE id=?",
                 (content, data.get("date") or None, note_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.route("/api/note/<int:note_id>", methods=["DELETE"])
@require_unlock
def delete_note(note_id):
    conn = get_db()
    conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})
