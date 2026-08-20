"""HTML pages and the navigation tree."""
from datetime import date, datetime

from flask import Blueprint, abort, jsonify, render_template

from ..db import get_db
from ..helpers import get_categories, human_size, parse_people
from ..security import require_unlock

bp = Blueprint("pages", __name__)


@bp.route("/api/tree")
@require_unlock
def tree_data():
    people = parse_people()
    conn = get_db()
    open_tasks = {r["person_id"]: r["cnt"] for r in conn.execute(
        "SELECT person_id, COUNT(*) AS cnt FROM tasks WHERE done = 0 GROUP BY person_id").fetchall()}
    note_counts = {r["person_id"]: r["cnt"] for r in conn.execute(
        "SELECT person_id, COUNT(*) AS cnt FROM notes GROUP BY person_id").fetchall()}
    doc_counts = {r["person_id"]: r["cnt"] for r in conn.execute(
        "SELECT person_id, COUNT(*) AS cnt FROM documents GROUP BY person_id").fetchall()}
    conn.close()
    ordered = get_categories()
    cats: dict[str, list] = {cat: [] for cat in ordered}
    for p in people:
        if p["category"] not in cats:
            cats[p["category"]] = []      # orphan category: shown after the known ones
            ordered.append(p["category"])
        cats[p["category"]].append({
            "id": p["id"], "name": p["name"], "category": p["category"],
            "tasks":     open_tasks.get(p["id"], 0),
            "notes":     note_counts.get(p["id"], 0),
            "documents": doc_counts.get(p["id"], 0),
        })
    result = [
        {"category": cat, "people": sorted(cats[cat], key=lambda x: x["name"].lower())}
        for cat in ordered
    ]
    return jsonify(result)


@bp.route("/")
@require_unlock
def index():
    people = parse_people()
    conn = get_db()
    photo_ids = {r["person_id"] for r in conn.execute("SELECT person_id FROM photos").fetchall()}
    conn.close()
    for p in people:
        p["has_photo"] = p["id"] in photo_ids
    return render_template("index.html", people=people, categories=get_categories())


@bp.route("/person/<person_id>")
@require_unlock
def person_detail(person_id):
    people = parse_people()
    person = next((p for p in people if p["id"] == person_id), None)
    if not person:
        abort(404)
    conn      = get_db()
    has_photo = conn.execute("SELECT 1 FROM photos WHERE person_id = ?", (person_id,)).fetchone()
    db_meetings = conn.execute(
        "SELECT id, title, content, meeting_date FROM meetings "
        "WHERE person_id = ? ORDER BY meeting_date DESC, id DESC", (person_id,)).fetchall()
    override = conn.execute(
        "SELECT details, profile, name, category FROM person_overrides WHERE person_id = ?",
        (person_id,)).fetchone()
    db_tasks = conn.execute(
        "SELECT id, text, done FROM tasks WHERE person_id = ? ORDER BY done ASC, id ASC",
        (person_id,)).fetchall()
    db_notes = conn.execute(
        "SELECT id, content, note_date FROM notes "
        "WHERE person_id = ? ORDER BY note_date DESC, id DESC", (person_id,)).fetchall()
    db_docs = conn.execute(
        "SELECT id, filename, size, uploaded_at FROM documents "
        "WHERE person_id = ? ORDER BY uploaded_at DESC, id DESC", (person_id,)).fetchall()
    db_pics = conn.execute(
        "SELECT id, filename, size, uploaded_at FROM pictures "
        "WHERE person_id = ? ORDER BY uploaded_at DESC, id DESC", (person_id,)).fetchall()
    conn.close()

    person["has_photo"] = has_photo is not None
    if override:
        if override["details"]  is not None: person["details"]  = override["details"]
        if override["profile"]  is not None: person["profile"]  = override["profile"]
        if override["name"]     is not None: person["name"]     = override["name"]
        if override["category"] is not None: person["category"] = override["category"]

    for row in db_meetings:
        d = date.fromisoformat(row["meeting_date"]) if row["meeting_date"] else None
        person["meetings"].insert(0, {
            "title": row["title"], "content": row["content"], "date": d, "db_id": row["id"],
        })
    person["meetings"].sort(key=lambda m: m["date"] or date.min, reverse=True)
    person["meeting_count"] = len(person["meetings"])
    tasks = [{"id": r["id"], "text": r["text"], "done": bool(r["done"])} for r in db_tasks]
    notes = [{"id": r["id"], "content": r["content"],
              "date": date.fromisoformat(r["note_date"]) if r["note_date"] else None}
             for r in db_notes]
    documents = [{"id": r["id"], "filename": r["filename"],
                  "size_human": human_size(r["size"]),
                  "uploaded_at": datetime.fromisoformat(r["uploaded_at"])}
                 for r in db_docs]
    pictures = [{"id": r["id"], "filename": r["filename"],
                 "size_human": human_size(r["size"]),
                 "uploaded_at": datetime.fromisoformat(r["uploaded_at"])}
                for r in db_pics]
    return render_template("person.html", person=person, today=date.today().isoformat(),
                           categories=get_categories(), tasks=tasks, notes=notes,
                           documents=documents, pictures=pictures)
