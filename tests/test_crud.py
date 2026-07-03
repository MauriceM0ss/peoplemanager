"""Characterization tests for person / meeting / task / note / category CRUD."""
from conftest import make_person


# ── persons ────────────────────────────────────────────────────────────────
def test_create_person_appears_in_tree(auth_client):
    pid = make_person(auth_client, "Alice Smith", "Friends")
    assert pid == "alice_smith"
    tree = auth_client.get("/api/tree").get_json()
    friends = next(c for c in tree if c["category"] == "Friends")
    assert any(p["id"] == pid for p in friends["people"])


def test_create_person_requires_name(auth_client):
    assert auth_client.post("/api/person", json={"name": "  "}).status_code == 400


def test_update_person_name_and_details(auth_client):
    pid = make_person(auth_client)
    assert auth_client.put(f"/api/person/{pid}",
                           json={"field": "name", "content": "Alice B"}).status_code == 200
    assert auth_client.put(f"/api/person/{pid}",
                           json={"field": "details", "content": "hello"}).status_code == 200
    r = auth_client.get(f"/person/{pid}")
    assert r.status_code == 200
    assert b"Alice B" in r.data


def test_update_person_rejects_bad_field(auth_client):
    pid = make_person(auth_client)
    r = auth_client.put(f"/api/person/{pid}", json={"field": "evil", "content": "x"})
    assert r.status_code == 400


def test_delete_person_hides_it(auth_client):
    pid = make_person(auth_client)
    assert auth_client.delete(f"/api/person/{pid}").status_code == 200
    tree = auth_client.get("/api/tree").get_json()
    assert all(p["id"] != pid for cat in tree for p in cat["people"])


# ── meetings ───────────────────────────────────────────────────────────────
def test_meeting_add_and_delete(auth_client):
    pid = make_person(auth_client)
    r = auth_client.post(f"/api/meeting/{pid}",
                         json={"title": "Coffee", "content": "chat", "date": "2026-01-02"})
    assert r.status_code == 200
    mid = r.get_json()["id"]
    assert b"Coffee" in auth_client.get(f"/person/{pid}").data
    assert auth_client.delete(f"/api/meeting/{mid}").status_code == 200


def test_meeting_requires_title(auth_client):
    pid = make_person(auth_client)
    assert auth_client.post(f"/api/meeting/{pid}", json={"content": "x"}).status_code == 400


# ── tasks ──────────────────────────────────────────────────────────────────
def test_task_lifecycle(auth_client):
    pid = make_person(auth_client)
    tid = auth_client.post(f"/api/task/{pid}", json={"text": "call back"}).get_json()["id"]
    # open task shows in tree count
    tree = auth_client.get("/api/tree").get_json()
    person = next(p for cat in tree for p in cat["people"] if p["id"] == pid)
    assert person["tasks"] == 1
    assert auth_client.patch(f"/api/task/{tid}", json={"done": True}).status_code == 200
    tree = auth_client.get("/api/tree").get_json()
    person = next(p for cat in tree for p in cat["people"] if p["id"] == pid)
    assert person["tasks"] == 0
    assert auth_client.delete(f"/api/task/{tid}").status_code == 200


# ── notes ──────────────────────────────────────────────────────────────────
def test_note_lifecycle(auth_client):
    pid = make_person(auth_client)
    nid = auth_client.post(f"/api/note/{pid}",
                           json={"content": "remember birthday", "date": "2026-03-03"}
                           ).get_json()["id"]
    assert auth_client.put(f"/api/note/{nid}",
                           json={"content": "updated", "date": "2026-03-04"}).status_code == 200
    assert b"updated" in auth_client.get(f"/person/{pid}").data
    assert auth_client.delete(f"/api/note/{nid}").status_code == 200


def test_note_requires_content(auth_client):
    pid = make_person(auth_client)
    assert auth_client.post(f"/api/note/{pid}", json={"content": " "}).status_code == 400


# ── categories ─────────────────────────────────────────────────────────────
def test_category_add_rename_delete(auth_client):
    assert auth_client.post("/api/categories", json={"name": "Gym"}).status_code == 200
    assert "Gym" in auth_client.get("/api/categories").get_json()
    # duplicate rejected
    assert auth_client.post("/api/categories", json={"name": "Gym"}).status_code == 409
    # rename
    assert auth_client.put("/api/categories/Gym", json={"new_name": "Sports"}).status_code == 200
    cats = auth_client.get("/api/categories").get_json()
    assert "Sports" in cats and "Gym" not in cats


def test_delete_category_reassigns_people(auth_client):
    auth_client.post("/api/categories", json={"name": "Temp"})
    pid = make_person(auth_client, "Dave", "Temp")
    r = auth_client.delete("/api/categories/Temp")
    assert r.status_code == 200
    fallback = r.get_json()["fallback"]
    # person moved to the fallback category
    tree = auth_client.get("/api/tree").get_json()
    found = next(p for cat in tree for p in cat["people"] if p["id"] == pid)
    assert found  # still present
    fb_cat = next(c for c in tree if c["category"] == fallback)
    assert any(p["id"] == pid for p in fb_cat["people"])
