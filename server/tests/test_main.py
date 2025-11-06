import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from server.main import create_app


@pytest.fixture
def app(tmp_path):
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    db_path = str(tmp_path / "test.db")

    config = MagicMock()
    config.vault_path = str(vault_path)
    config.llm_api_key = "sk-test"
    config.llm_provider = "openai"
    config.default_tags = ["funny", "recipe"]
    config.server_port = 7890

    return create_app(config=config, db_path=db_path)


@pytest.fixture
def client(app):
    return TestClient(app)


def test_status_endpoint(client):
    resp = client.get("/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_post_reel_success(mock_tagger, mock_metadata, client):
    mock_metadata.return_value = MagicMock(
        reel_id="ABC123",
        caption="Great pasta",
        creator_username="chef_anna",
        creator_display_name="Chef Anna",
        thumbnail_url="https://example.com/thumb.jpg",
    )
    mock_tagger.return_value = ["recipe", "italian"]

    resp = client.post("/reel", json={
        "url": "https://www.instagram.com/reel/ABC123/",
        "timestamp": "2025-11-05T14:32:00",
        "userNote": "must try",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data["reel_id"] == "ABC123"
    assert data["tags"] == ["recipe", "italian"]


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_post_reel_duplicate(mock_tagger, mock_metadata, client):
    mock_metadata.return_value = MagicMock(
        reel_id="DUP123",
        caption="Dupe",
        creator_username="user",
        creator_display_name="User",
        thumbnail_url=None,
    )
    mock_tagger.return_value = ["funny"]

    client.post("/reel", json={
        "url": "https://www.instagram.com/reel/DUP123/",
        "timestamp": "2025-11-05T14:00:00",
    })
    resp = client.post("/reel", json={
        "url": "https://www.instagram.com/reel/DUP123/",
        "timestamp": "2025-11-05T14:01:00",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "duplicate"


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_post_reel_metadata_failure(mock_tagger, mock_metadata, client):
    mock_metadata.return_value = None
    mock_tagger.return_value = None

    resp = client.post("/reel", json={
        "url": "https://www.instagram.com/reel/FAIL123/",
        "timestamp": "2025-11-05T14:32:00",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "fetch-failed"


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_post_reel_tagging_failure(mock_tagger, mock_metadata, client):
    mock_metadata.return_value = MagicMock(
        reel_id="TAG_FAIL",
        caption="Some reel",
        creator_username="user",
        creator_display_name="User",
        thumbnail_url=None,
    )
    mock_tagger.return_value = None

    resp = client.post("/reel", json={
        "url": "https://www.instagram.com/reel/TAG_FAIL/",
        "timestamp": "2025-11-05T14:32:00",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "untagged"
    assert resp.json()["tags"] == ["untagged"]
