import pytest
from unittest.mock import patch, MagicMock
from server.metadata import fetch_reel_metadata, extract_reel_id, ReelMetadata


def _make_ytdlp_info(
    id="ABC123",
    title="Funny cat video",
    uploader="cat_lover",
    uploader_id="cat_lover",
    thumbnail="https://example.com/thumb.jpg",
    description="Check out this cat #funny #cats",
):
    return {
        "id": id,
        "title": title,
        "uploader": uploader,
        "uploader_id": uploader_id,
        "thumbnail": thumbnail,
        "description": description,
    }


@patch("server.metadata.yt_dlp.YoutubeDL")
def test_fetch_metadata_success(mock_ytdlp_class):
    mock_instance = MagicMock()
    mock_instance.extract_info.return_value = _make_ytdlp_info()
    mock_ytdlp_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ytdlp_class.return_value.__exit__ = MagicMock(return_value=False)

    result = fetch_reel_metadata("https://www.instagram.com/reel/ABC123/")
    assert isinstance(result, ReelMetadata)
    assert result.reel_id == "ABC123"
    assert result.caption == "Check out this cat #funny #cats"
    assert result.creator_username == "cat_lover"
    assert result.thumbnail_url == "https://example.com/thumb.jpg"


@patch("server.metadata.yt_dlp.YoutubeDL")
def test_fetch_metadata_failure_returns_none(mock_ytdlp_class):
    mock_instance = MagicMock()
    mock_instance.extract_info.side_effect = Exception("Private reel")
    mock_ytdlp_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ytdlp_class.return_value.__exit__ = MagicMock(return_value=False)

    result = fetch_reel_metadata("https://www.instagram.com/reel/PRIVATE/")
    assert result is None


def test_extract_reel_id_from_url():
    assert extract_reel_id("https://www.instagram.com/reel/ABC123/") == "ABC123"
    assert extract_reel_id("https://instagram.com/reel/XYZ789/?igsh=abc") == "XYZ789"
    assert extract_reel_id("https://www.instagram.com/p/DEF456/") == "DEF456"
    assert extract_reel_id("https://example.com/not-a-reel") is None


def test_extract_reel_id_edge_cases():
    assert extract_reel_id("https://www.instagram.com/reel/A-b_C123/") == "A-b_C123"
    assert extract_reel_id("") is None
    assert extract_reel_id("instagram.com/reel/SHORT") == "SHORT"
