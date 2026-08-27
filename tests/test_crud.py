"""Characterization tests for person / meeting / task / note / category CRUD."""
from conftest import make_person


def appmod_profile_fields():
    """The profile fields rendered on the person card, straight from config."""
    from peoplecrm import config
    return config.PROFILE_FIELDS


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


# ── category order ─────────────────────────────────────────────────────────
def test_categories_have_a_manual_order(auth_client):
    """Seeded order is the insertion order, not the alphabet."""
    assert auth_client.get("/api/categories").get_json() == \
        ["Friends", "Family", "Work", "Other"]


def test_new_category_lands_last(auth_client):
    auth_client.post("/api/categories", json={"name": "Aaa Gym"})
    assert auth_client.get("/api/categories").get_json()[-1] == "Aaa Gym"


def test_reorder_categories(auth_client):
    r = auth_client.post("/api/categories/reorder",
                         json={"order": ["Work", "Other", "Friends", "Family"]})
    assert r.status_code == 200
    assert auth_client.get("/api/categories").get_json() == \
        ["Work", "Other", "Friends", "Family"]


def test_reorder_drives_the_tree_order(auth_client):
    auth_client.post("/api/categories/reorder", json={"order": ["Work", "Family"]})
    tree = [c["category"] for c in auth_client.get("/api/tree").get_json()]
    assert tree[:2] == ["Work", "Family"]


def test_reorder_ignores_unknown_names_and_keeps_the_rest(auth_client):
    r = auth_client.post("/api/categories/reorder",
                         json={"order": ["Work", "Nonexistent", "Work"]})
    assert r.status_code == 200
    cats = auth_client.get("/api/categories").get_json()
    assert cats[0] == "Work"
    assert sorted(cats) == sorted(["Friends", "Family", "Work", "Other"])


def test_reorder_rejects_a_bad_payload(auth_client):
    assert auth_client.post("/api/categories/reorder", json={"order": "Work"}).status_code == 400
    assert auth_client.post("/api/categories/reorder", json={"order": [1, 2]}).status_code == 400


def test_delete_category_falls_back_to_the_first_in_order(auth_client):
    auth_client.post("/api/categories/reorder",
                     json={"order": ["Work", "Friends", "Family", "Other"]})
    auth_client.post("/api/categories", json={"name": "Temp"})
    make_person(auth_client, "Eve", "Temp")
    assert auth_client.delete("/api/categories/Temp").get_json()["fallback"] == "Work"


def test_position_backfilled_for_a_pre_existing_database(appmod):
    """Upgrading a DB written before `position` existed must not shuffle names.

    Those databases ordered categories alphabetically, so that becomes the
    starting manual order rather than the arbitrary insertion order.
    """
    import sqlite3

    from peoplecrm.config import DB_PATH

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("CREATE TABLE categories ("
                 "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)")
    for cat in ("Work", "Family", "Friends", "Other"):
        conn.execute("INSERT INTO categories (name) VALUES (?)", (cat,))
    conn.commit()
    conn.close()

    c = appmod.app.test_client()
    assert c.post("/setup", data={"pin": "1234", "confirm": "1234",
                                  "timeout": "15"}).status_code == 302
    assert c.get("/api/categories").get_json() == ["Family", "Friends", "Other", "Work"]


# ── structured profile fields ──────────────────────────────────────────────
def _profile_html(auth_client, pid):
    return auth_client.get(f"/person/{pid}").get_data(as_text=True)


def test_profile_fields_round_trip(auth_client):
    pid = make_person(auth_client)
    fields = {"start_date": "2024-03-12", "birth_date": "1990-07-04",
              "role": "Threat Hunter", "grade": "Grade B",
              "status": "Customer Deployed"}
    assert auth_client.put(f"/api/person/{pid}", json={"fields": fields}).status_code == 200
    html = _profile_html(auth_client, pid)
    assert "12 Mar 2024" in html          # dates are rendered, not raw ISO
    assert "04 Jul 1990" in html
    assert "Threat Hunter" in html
    assert 'value="Grade B" selected' in html
    assert 'value="Customer Deployed" selected' in html


def test_profile_fields_accept_single_field_form(auth_client):
    pid = make_person(auth_client)
    assert auth_client.put(f"/api/person/{pid}",
                           json={"field": "role", "content": "Consultant"}).status_code == 200
    assert "Consultant" in _profile_html(auth_client, pid)


def test_profile_fields_can_be_cleared(auth_client):
    pid = make_person(auth_client)
    auth_client.put(f"/api/person/{pid}", json={"fields": {"role": "Consultant",
                                                           "grade": "Grade A"}})
    r = auth_client.put(f"/api/person/{pid}", json={"fields": {"role": "", "grade": ""}})
    assert r.status_code == 200
    html = _profile_html(auth_client, pid)
    assert "Consultant" not in html
    # Every profile field falls back to the em-dash placeholder.
    assert html.count('profile-value is-empty') == len(appmod_profile_fields())
    assert "selected" not in html.split('id="pf-input-grade"')[1].split("</select>")[0]


def test_profile_field_validation(auth_client):
    pid = make_person(auth_client)
    bad = [{"start_date": "12-03-2024"}, {"birth_date": "not a date"},
           {"grade": "Grade Z"}, {"status": "On Holiday"}]
    for fields in bad:
        r = auth_client.put(f"/api/person/{pid}", json={"fields": fields})
        assert r.status_code == 400, fields
        assert "error" in r.get_json()
    # nothing was written
    html = _profile_html(auth_client, pid)
    assert "Grade Z" not in html and "On Holiday" not in html


def test_update_person_rejects_unknown_field(auth_client):
    pid = make_person(auth_client)
    assert auth_client.put(f"/api/person/{pid}",
                           json={"fields": {"salary": "100"}}).status_code == 400
    assert auth_client.put(f"/api/person/{pid}", json={}).status_code == 400
    assert auth_client.put(f"/api/person/{pid}", json={"fields": {}}).status_code == 400


def test_batched_update_is_all_or_nothing(auth_client):
    pid = make_person(auth_client)
    r = auth_client.put(f"/api/person/{pid}",
                        json={"fields": {"role": "Threat Hunter", "grade": "Grade Q"}})
    assert r.status_code == 400
    # The valid half of the rejected batch must not have landed either.
    assert "Threat Hunter" not in _profile_html(auth_client, pid)


# ── years of experience ────────────────────────────────────────────────────
def test_experience_is_stamped_with_todays_date(auth_client):
    from datetime import date
    pid = make_person(auth_client)
    r = auth_client.put(f"/api/person/{pid}", json={"fields": {"experience_years": "12"}})
    assert r.status_code == 200
    assert r.get_json()["experience_as_of"] == date.today().isoformat()
    html = _profile_html(auth_client, pid)
    assert "12 yrs" in html


def test_experience_stamp_only_moves_when_the_number_changes(auth_client):
    pid = make_person(auth_client)
    auth_client.put(f"/api/person/{pid}", json={"fields": {"experience_years": "12"}})
    # Re-saving the same number must not refresh the stamp, or a stale figure
    # would quietly look current again.
    r = auth_client.put(f"/api/person/{pid}",
                        json={"fields": {"experience_years": "12", "role": "Analyst"}})
    assert r.get_json().get("experience_as_of") is None
    # Changing it does re-stamp.
    r = auth_client.put(f"/api/person/{pid}", json={"fields": {"experience_years": "13"}})
    assert r.get_json()["experience_as_of"] is not None


def test_clearing_experience_clears_the_stamp(auth_client):
    pid = make_person(auth_client)
    auth_client.put(f"/api/person/{pid}", json={"fields": {"experience_years": "12"}})
    r = auth_client.put(f"/api/person/{pid}", json={"fields": {"experience_years": ""}})
    assert r.get_json()["experience_as_of"] == ""
    assert "12 yrs" not in _profile_html(auth_client, pid)


def test_experience_validation(auth_client):
    pid = make_person(auth_client)
    for bad in ("abc", "-1", "200"):
        r = auth_client.put(f"/api/person/{pid}", json={"fields": {"experience_years": bad}})
        assert r.status_code == 400, bad
    # Decimals and comma decimal separators are accepted.
    for good in ("12", "12.5", "12,5", "0"):
        assert auth_client.put(f"/api/person/{pid}",
                               json={"fields": {"experience_years": good}}).status_code == 200


def test_experience_as_of_is_not_client_settable(auth_client):
    pid = make_person(auth_client)
    r = auth_client.put(f"/api/person/{pid}",
                        json={"fields": {"experience_as_of": "1999-01-01"}})
    assert r.status_code == 400


def test_tree_reports_conversation_counts(auth_client):
    pid = make_person(auth_client)
    auth_client.post(f"/api/meeting/{pid}", json={"title": "Chat", "content": "Power BI"})
    tree = auth_client.get("/api/tree").get_json()
    person = next(p for c in tree for p in c["people"] if p["id"] == pid)
    assert person["conversations"] == 1
