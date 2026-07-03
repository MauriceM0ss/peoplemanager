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
