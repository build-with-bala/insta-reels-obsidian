from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from server.metadata import ReelMetadata


def _config(vault_path):
    config = MagicMock()
    config.vault_path = str(vault_path)
    config.llm_api_key = "sk-test"
    config.llm_provider = "openai"
    config.default_tags = ["funny", "recipe"]
    config.server_port = 7890
    config.server_host = "127.0.0.1"
    config.cookies_from_browser = None
    config.cookie_file = None
    config.retry_interval_minutes = 0  # keep the background loop off in tests
    return config


@pytest.fixture
def setup(tmp_path):
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    app = create_app(config=_config(vault_path), db_path=str(tmp_path / "test.db"))
    return TestClient(app), vault_path


def _metadata(reel_id="RETRY1", caption="Sunset timelapse"):
    return ReelMetadata(
        reel_id=reel_id,
        caption=caption,
        creator_username="sky_watcher",
        creator_display_name="Sky Watcher",
        thumbnail_url=None,
    )


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_retry_endpoint_recovers_fetch_failed_reel(mock_tagger, mock_fetch, setup):
    client, vault_path = setup

    mock_fetch.return_value = None
    resp = client.post("/reel", json={
        "url": "https://www.instagram.com/reel/RETRY1/",
        "timestamp": "2025-11-09T10:00:00",
        "userNote": "keep this",
    })
    assert resp.json()["status"] == "fetch-failed"

    log = (vault_path / "Instagram Reels" / "Log.md").read_text()
    assert "#fetch-failed" in log

    # Metadata fetch works now.
    mock_fetch.return_value = _metadata()
    mock_tagger.return_value = ["travel", "nature"]

    resp = client.post("/retry")
    assert resp.status_code == 200
    assert resp.json() == {"retried": 1, "recovered": 1, "still_pending": 0}

    assert client.get("/status").json()["reel_counts"] == {"processed": 1}

    # Vault entry was replaced, not duplicated.
    log = (vault_path / "Instagram Reels" / "Log.md").read_text()
    assert "#fetch-failed" not in log
    assert log.count("RETRY1") == 1
    assert "@sky_watcher" in log
    assert "Sunset timelapse" in log
    assert "keep this" in log  # user note survives the retry
    assert (vault_path / "Instagram Reels" / "Tags" / "travel.md").exists()
    failed_tag = (vault_path / "Instagram Reels" / "Tags" / "fetch-failed.md")
    assert "RETRY1" not in failed_tag.read_text()


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_reshare_of_fetch_failed_reel_triggers_retry(mock_tagger, mock_fetch, setup):
    client, vault_path = setup

    mock_fetch.return_value = None
    client.post("/reel", json={
        "url": "https://www.instagram.com/reel/RESHARE1/",
        "timestamp": "2025-11-09T10:00:00",
    })

    # Re-sharing the same reel must NOT dead-end as a duplicate.
    mock_fetch.return_value = _metadata(reel_id="RESHARE1")
    mock_tagger.return_value = ["travel"]

    resp = client.post("/reel", json={
        "url": "https://www.instagram.com/reel/RESHARE1/",
        "timestamp": "2025-11-09T11:00:00",
    })
    data = resp.json()
    assert data["status"] == "processed"
    assert data["tags"] == ["travel"]
    assert client.get("/status").json()["reel_counts"] == {"processed": 1}


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_reshare_of_processed_reel_is_still_duplicate(mock_tagger, mock_fetch, setup):
    client, _ = setup

    mock_fetch.return_value = _metadata(reel_id="DONE1")
    mock_tagger.return_value = ["funny"]
    client.post("/reel", json={
        "url": "https://www.instagram.com/reel/DONE1/",
        "timestamp": "2025-11-09T10:00:00",
    })

    resp = client.post("/reel", json={
        "url": "https://www.instagram.com/reel/DONE1/",
        "timestamp": "2025-11-09T11:00:00",
    })
    assert resp.json()["status"] == "duplicate"


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_retry_recovers_untagged_reel(mock_tagger, mock_fetch, setup):
    client, vault_path = setup

    mock_fetch.return_value = _metadata(reel_id="UNTAG1", caption="Leg day tips")
    mock_tagger.return_value = None  # tagging fails initially
    resp = client.post("/reel", json={
        "url": "https://www.instagram.com/reel/UNTAG1/",
        "timestamp": "2025-11-09T10:00:00",
    })
    assert resp.json()["status"] == "untagged"

    mock_tagger.return_value = ["fitness"]
    resp = client.post("/retry")
    assert resp.json() == {"retried": 1, "recovered": 1, "still_pending": 0}

    assert client.get("/status").json()["reel_counts"] == {"processed": 1}
    log = (vault_path / "Instagram Reels" / "Log.md").read_text()
    assert "#fitness" in log
    assert "#untagged" not in log
    assert log.count("UNTAG1") == 1
    # Tagging retries reuse the stored caption; no metadata re-fetch needed.
    assert mock_fetch.call_count == 1


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_retry_keeps_failing_reel_retryable(mock_tagger, mock_fetch, setup):
    client, _ = setup

    mock_fetch.return_value = None
    client.post("/reel", json={
        "url": "https://www.instagram.com/reel/STUCK1/",
        "timestamp": "2025-11-09T10:00:00",
    })

    resp = client.post("/retry")
    assert resp.json() == {"retried": 1, "recovered": 0, "still_pending": 1}

    # Still retryable on the next pass; recovery works once fetch succeeds.
    mock_fetch.return_value = _metadata(reel_id="STUCK1")
    mock_tagger.return_value = ["travel"]
    resp = client.post("/retry")
    assert resp.json() == {"retried": 1, "recovered": 1, "still_pending": 0}


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_retry_with_nothing_pending(mock_tagger, mock_fetch, setup):
    client, _ = setup
    resp = client.post("/retry")
    assert resp.json() == {"retried": 0, "recovered": 0, "still_pending": 0}
