import json
import pytest
from server.db import ReelDB


@pytest.fixture
def db(tmp_path):
    return ReelDB(str(tmp_path / "test.db"))


def test_insert_and_get_reel(db):
    db.insert_reel(
        reel_id="ABC123",
        url="https://www.instagram.com/reel/ABC123/",
        creator_username="chef_anna",
        creator_display_name="Chef Anna",
        caption="Best pasta ever",
        tags=["recipe", "italian"],
        thumbnail_url="https://example.com/thumb.jpg",
        user_note="must try this",
        timestamp="2025-10-29T14:32:00",
        status="processed",
    )
    reel = db.get_reel("ABC123")
    assert reel["id"] == "ABC123"
    assert reel["url"] == "https://www.instagram.com/reel/ABC123/"
    assert reel["creator_username"] == "chef_anna"
    assert reel["caption"] == "Best pasta ever"
    assert json.loads(reel["tags"]) == ["recipe", "italian"]
    assert reel["status"] == "processed"


def test_reel_exists(db):
    assert db.reel_exists("ABC123") is False
    db.insert_reel(
        reel_id="ABC123",
        url="https://www.instagram.com/reel/ABC123/",
        timestamp="2025-10-29T14:32:00",
    )
    assert db.reel_exists("ABC123") is True


def test_get_reels_by_status(db):
    db.insert_reel(
        reel_id="A", url="https://instagram.com/reel/A/",
        timestamp="2025-10-29T10:00:00", status="untagged",
    )
    db.insert_reel(
        reel_id="B", url="https://instagram.com/reel/B/",
        timestamp="2025-10-29T11:00:00", status="processed",
    )
    db.insert_reel(
        reel_id="C", url="https://instagram.com/reel/C/",
        timestamp="2025-10-29T12:00:00", status="untagged",
    )
    untagged = db.get_reels_by_status("untagged")
    assert len(untagged) == 2
    assert untagged[0]["id"] == "A"


def test_update_reel_tags(db):
    db.insert_reel(
        reel_id="A", url="https://instagram.com/reel/A/",
        timestamp="2025-10-29T10:00:00", status="untagged",
    )
    db.update_reel_tags("A", ["funny", "travel"], "processed")
    reel = db.get_reel("A")
    assert json.loads(reel["tags"]) == ["funny", "travel"]
    assert reel["status"] == "processed"


def test_get_nonexistent_reel(db):
    assert db.get_reel("NOPE") is None


def test_get_retry_candidates(db):
    db.insert_reel(
        reel_id="A", url="https://instagram.com/reel/A/",
        timestamp="2025-01-24T10:00:00", status="fetch-failed",
    )
    db.insert_reel(
        reel_id="B", url="https://instagram.com/reel/B/",
        timestamp="2025-01-24T11:00:00", status="processed",
    )
    db.insert_reel(
        reel_id="C", url="https://instagram.com/reel/C/",
        timestamp="2025-01-24T12:00:00", status="untagged",
    )
    candidates = db.get_retry_candidates()
    assert len(candidates) == 2
    ids = [c["id"] for c in candidates]
    assert "A" in ids
    assert "C" in ids
    assert "B" not in ids


def test_get_stats(db):
    db.insert_reel(reel_id="A", url="u", timestamp="t", status="processed")
    db.insert_reel(reel_id="B", url="u", timestamp="t", status="processed")
    db.insert_reel(reel_id="C", url="u", timestamp="t", status="untagged")
    stats = db.get_stats()
    assert stats["processed"] == 2
    assert stats["untagged"] == 1
