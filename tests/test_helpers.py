"""Characterization tests for pure helper functions."""
import pytest


def test_normalize_id_basic(appmod):
    assert appmod.normalize_id("Alice Smith") == "alice_smith"


def test_normalize_id_accents_and_punctuation(appmod):
    # accents folded, punctuation dropped, hyphen → space → underscore
    assert appmod.normalize_id("Zoë  Müller-O'Brien") == "zoe_muller_obrien"


def test_normalize_id_strips_and_collapses(appmod):
    assert appmod.normalize_id("  Bob   Jones  ") == "bob_jones"


@pytest.mark.parametrize(
    "n,expected",
    [
        (0, "0 B"),
        (512, "512 B"),
        (1024, "1 KB"),
        (1536, "2 KB"),
        (1024 * 1024, "1 MB"),
        (5 * 1024 * 1024 * 1024, "5 GB"),
        (5 * 1024 * 1024 * 1024 * 1024, "5.0 GB"),  # TB range hits the .1f branch
    ],
)
def test_human_size(appmod, n, expected):
    assert appmod.human_size(n) == expected


def test_derive_key_is_deterministic(appmod):
    salt = b"\x01" * 32
    k1 = appmod._derive_key("1234", salt)
    k2 = appmod._derive_key("1234", salt)
    assert k1 == k2
    assert len(k1) == 64  # 32 bytes hex-encoded
    # different PIN → different key
    assert appmod._derive_key("9999", salt) != k1


def test_doc_icon(appmod):
    assert appmod.doc_icon("xlsx") == "📊"
    assert appmod.doc_icon("docx") == "📝"
    assert appmod.doc_icon("pdf") == "📋"
    assert appmod.doc_icon("unknown") == "📄"


# ── colours ────────────────────────────────────────────────────────────────
def test_stable_hash_is_process_independent(appmod):
    """Must not use Python's salted hash(): the browser mirrors this in JS.

    The expected values are what
    ``[...s].reduce((h,c) => (Math.imul(31,h)+c.charCodeAt(0))|0, 0)``
    produces for the same input, so a badge repainted client-side matches the
    colour the server would have rendered.
    """
    from peoplecrm.helpers import stable_hash

    assert stable_hash("") == 0
    assert stable_hash("Work") == 2702129
    assert stable_hash("Friends") == 1064558965
    # 32-bit signed wrap-around
    assert stable_hash("a long category name that overflows") == -904489808


def test_category_color_is_stable(appmod):
    from peoplecrm.helpers import category_color

    assert category_color("Work") == category_color("Work")
    assert category_color("Work").startswith("#")


def test_pretty_date(appmod):
    assert appmod.pretty_date("2024-03-12") == "12 Mar 2024"
    assert appmod.pretty_date("") == ""
    assert appmod.pretty_date("not a date") == ""
    assert appmod.pretty_date(None) == ""


def test_whole_years_since_counts_anniversaries(appmod):
    from datetime import date
    w = appmod.whole_years_since
    # Two calendar years is two, even though 730 days / 365.25 rounds to one.
    assert w("2024-08-27", date(2026, 8, 27)) == 2
    assert w("2024-08-28", date(2026, 8, 27)) == 1
    assert w("2024-02-29", date(2025, 2, 28)) == 0
    assert w("2024-02-29", date(2025, 3, 1)) == 1
    assert w("2030-01-01", date(2026, 1, 1)) == 0   # future dates never go negative
    assert w("not a date") == 0


def test_experience_display(appmod):
    from datetime import date
    e, today = appmod.experience_display, date.today().isoformat()
    assert e("", "") == {}
    assert e("abc", today) == {}
    assert e("12", today) == {"primary": "12 yrs", "note": f"noted {appmod.pretty_date(today)}"}
    assert e("1", today)["primary"] == "1 yr"
    assert e("12.5", today)["primary"] == "12.5 yrs"
    assert e("12", "")["note"] == ""
    aged = e("12", "2024-08-27")
    assert aged["primary"].startswith("~")
    assert "noted 27 Aug 2024" in aged["note"]
