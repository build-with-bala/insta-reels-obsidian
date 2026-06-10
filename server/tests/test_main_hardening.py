from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from server.db import ReelDB
from server.main import create_app
from server.metadata import ReelMetadata, fetch_reel_metadata


def _config(vault_path, **overrides):
    config = MagicMock()
    config.vault_path = str(vault_path)
    config.llm_api_key = "sk-test"
    config.llm_provider = "openai"
    config.default_tags = ["funny", "recipe"]
    config.server_port = 7890
    config.server_host = "127.0.0.1"
    config.cookies_from_browser = None
    config.cookie_file = None
    config.retry_interval_minutes = 0
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _make_app(tmp_path, **config_overrides):
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    config = _config(vault_path, **config_overrides)
    return create_app(config=config, db_path=str(tmp_path / "test.db"))


def _metadata(reel_id="RACE1"):
    return ReelMetadata(
        reel_id=reel_id,
        caption="caption",
        creator_username="user",
        creator_display_name="User",
        thumbnail_url=None,
    )


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_duplicate_insert_race_returns_duplicate(mock_tagger, mock_fetch, tmp_path):
    """If two requests pass the duplicate check before either inserts, the
    loser of the race gets a clean 'duplicate' instead of a 500."""
    client = TestClient(_make_app(tmp_path))
    mock_fetch.return_value = _metadata("RACE1")
    mock_tagger.return_value = ["funny"]

    first = client.post("/reel", json={
        "url": "https://www.instagram.com/reel/RACE1/",
        "timestamp": "2025-11-09T10:00:00",
    })
    assert first.json()["status"] == "processed"

    # Simulate the race: the duplicate check misses the existing row, so the
    # request proceeds to insert and hits the UNIQUE constraint.
    with patch.object(ReelDB, "get_reel", return_value=None):
        second = client.post("/reel", json={
            "url": "https://www.instagram.com/reel/RACE1/",
            "timestamp": "2025-11-09T10:00:01",
        })
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate", "reel_id": "RACE1"}


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_fetch_failed_insert_race_returns_duplicate(mock_tagger, mock_fetch, tmp_path):
    client = TestClient(_make_app(tmp_path))
    mock_fetch.return_value = None

    first = client.post("/reel", json={
        "url": "https://www.instagram.com/reel/RACE2/",
        "timestamp": "2025-11-09T10:00:00",
    })
    assert first.json()["status"] == "fetch-failed"

    with patch.object(ReelDB, "get_reel", return_value=None):
        second = client.post("/reel", json={
            "url": "https://www.instagram.com/reel/RACE2/",
            "timestamp": "2025-11-09T10:00:01",
        })
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate", "reel_id": "RACE2"}


@patch("server.main.fetch_reel_metadata")
@patch("server.main.auto_tag_reel", new_callable=AsyncMock)
def test_cookie_options_passed_to_metadata_fetch(mock_tagger, mock_fetch, tmp_path):
    client = TestClient(_make_app(tmp_path, cookies_from_browser="chrome"))
    mock_fetch.return_value = _metadata("COOKIE1")
    mock_tagger.return_value = ["funny"]

    client.post("/reel", json={
        "url": "https://www.instagram.com/reel/COOKIE1/",
        "timestamp": "2025-11-09T10:00:00",
    })
    mock_fetch.assert_called_once_with(
        "https://www.instagram.com/reel/COOKIE1/",
        cookies_from_browser="chrome",
        cookie_file=None,
    )


@patch("server.metadata.yt_dlp.YoutubeDL")
def test_yt_dlp_receives_cookie_options(mock_ytdlp_class):
    mock_instance = MagicMock()
    mock_instance.extract_info.return_value = {"id": "ABC123"}
    mock_ytdlp_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ytdlp_class.return_value.__exit__ = MagicMock(return_value=False)

    fetch_reel_metadata(
        "https://www.instagram.com/reel/ABC123/",
        cookies_from_browser="chrome:Profile 1",
        cookie_file="/tmp/cookies.txt",
    )
    opts = mock_ytdlp_class.call_args[0][0]
    assert opts["cookiefile"] == "/tmp/cookies.txt"
    assert opts["cookiesfrombrowser"] == ("chrome", "Profile 1")


@patch("server.metadata.yt_dlp.YoutubeDL")
def test_yt_dlp_no_cookie_options_by_default(mock_ytdlp_class):
    mock_instance = MagicMock()
    mock_instance.extract_info.return_value = {"id": "ABC123"}
    mock_ytdlp_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ytdlp_class.return_value.__exit__ = MagicMock(return_value=False)

    fetch_reel_metadata("https://www.instagram.com/reel/ABC123/")
    opts = mock_ytdlp_class.call_args[0][0]
    assert "cookiefile" not in opts
    assert "cookiesfrombrowser" not in opts


def test_cors_has_no_wildcard_extension_origin(tmp_path):
    app = _make_app(tmp_path)
    cors = next(
        m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"
    )
    origins = cors.kwargs["allow_origins"]
    assert "https://www.instagram.com" in origins
    assert not any("*" in origin for origin in origins)
