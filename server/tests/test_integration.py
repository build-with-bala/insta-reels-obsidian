from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from server.metadata import ReelMetadata


@pytest.fixture
def setup(tmp_path):
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    db_path = str(tmp_path / "test.db")

    config = MagicMock()
    config.vault_path = str(vault_path)
    config.llm_api_key = "sk-test"
    config.llm_provider = "openai"
    config.default_tags = ["funny", "recipe"]
    config.server_port = 7890

    app = create_app(config=config, db_path=db_path)
    client = TestClient(app)
    return client, vault_path


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_full_pipeline_creates_all_vault_files(mock_tagger, mock_metadata, setup):
    client, vault_path = setup

    mock_metadata.return_value = ReelMetadata(
        reel_id="INTEG123",
        caption="Beautiful sunset in Bali",
        creator_username="travel_guru",
        creator_display_name="Travel Guru",
        thumbnail_url="https://example.com/thumb.jpg",
    )
    mock_tagger.return_value = ["travel", "nature"]

    resp = client.post("/reel", json={
        "url": "https://www.instagram.com/reel/INTEG123/",
        "timestamp": "2025-11-09T18:45:00",
        "userNote": "add to bucket list",
    })

    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"

    # Verify Log.md
    log = (vault_path / "Instagram Reels" / "Log.md").read_text()
    assert "@travel_guru" in log
    assert "INTEG123" in log
    assert "Beautiful sunset in Bali" in log
    assert "#travel" in log
    assert "add to bucket list" in log

    # Verify Daily note
    daily = (
        vault_path / "Instagram Reels" / "Daily" / "2025-11-09.md"
    ).read_text()
    assert "type: instagram-reel-daily" in daily
    assert "@travel_guru" in daily

    # Verify Tag files
    travel_tag = (
        vault_path / "Instagram Reels" / "Tags" / "travel.md"
    ).read_text()
    assert "tag: travel" in travel_tag
    assert "INTEG123" in travel_tag

    nature_tag = (
        vault_path / "Instagram Reels" / "Tags" / "nature.md"
    ).read_text()
    assert "tag: nature" in nature_tag


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_multiple_reels_same_day(mock_tagger, mock_metadata, setup):
    client, vault_path = setup

    for i, (creator, tags) in enumerate([
        ("chef_anna", ["recipe"]),
        ("gym_bro", ["fitness"]),
    ]):
        mock_metadata.return_value = ReelMetadata(
            reel_id=f"MULTI{i}",
            caption=f"Reel {i}",
            creator_username=creator,
            creator_display_name=creator,
            thumbnail_url=None,
        )
        mock_tagger.return_value = tags

        client.post("/reel", json={
            "url": f"https://www.instagram.com/reel/MULTI{i}/",
            "timestamp": f"2025-11-09T{10+i}:00:00",
        })

    daily = (
        vault_path / "Instagram Reels" / "Daily" / "2025-11-09.md"
    ).read_text()
    assert "@chef_anna" in daily
    assert "@gym_bro" in daily

    log = (vault_path / "Instagram Reels" / "Log.md").read_text()
    assert "@chef_anna" in log
    assert "@gym_bro" in log


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_fetch_failed_still_creates_vault_entry(mock_tagger, mock_metadata, setup):
    client, vault_path = setup

    mock_metadata.return_value = None

    resp = client.post("/reel", json={
        "url": "https://www.instagram.com/reel/BROKEN/",
        "timestamp": "2025-11-09T20:00:00",
        "userNote": "check later",
    })

    assert resp.json()["status"] == "fetch-failed"

    log = (vault_path / "Instagram Reels" / "Log.md").read_text()
    assert "BROKEN" in log
    assert "#fetch-failed" in log
