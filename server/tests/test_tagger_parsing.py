import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.tagger import _parse_tags, auto_tag_reel, _call_openai


def test_parse_plain_array():
    assert _parse_tags('["recipe", "italian"]') == ["recipe", "italian"]


def test_parse_fenced_json():
    content = '```json\n["recipe", "italian"]\n```'
    assert _parse_tags(content) == ["recipe", "italian"]


def test_parse_fence_without_language():
    content = '```\n["funny"]\n```'
    assert _parse_tags(content) == ["funny"]


def test_parse_array_embedded_in_prose():
    content = 'Sure! Here are the tags:\n["travel", "nature"]\nHope that helps.'
    assert _parse_tags(content) == ["travel", "nature"]


def test_parse_tags_object():
    assert _parse_tags('{"tags": ["tech", "ai"]}') == ["tech", "ai"]


def test_parse_filters_non_strings_and_caps_at_five():
    content = '["a", 1, "b", null, "c", "d", "e", "f", "g"]'
    assert _parse_tags(content) == ["a", "b", "c", "d", "e"]


def test_parse_garbage_raises():
    with pytest.raises(ValueError):
        _parse_tags("I could not categorize this reel.")


def test_parse_empty_raises():
    with pytest.raises(ValueError):
        _parse_tags("")


def test_parse_non_list_json_raises():
    with pytest.raises(ValueError):
        _parse_tags('"just a string"')


def _mock_openai_response(content: str):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


@pytest.mark.asyncio
@patch("server.tagger.httpx.AsyncClient")
async def test_call_openai_handles_fenced_response(mock_client_cls):
    client = MagicMock()
    client.post = AsyncMock(
        return_value=_mock_openai_response('```json\n["recipe", "pasta"]\n```')
    )
    mock_client_cls.return_value.__aenter__.return_value = client

    tags = await _call_openai("prompt", "sk-test")
    assert tags == ["recipe", "pasta"]


@pytest.mark.asyncio
@patch("server.tagger.httpx.AsyncClient")
async def test_auto_tag_unparseable_response_returns_none(mock_client_cls):
    client = MagicMock()
    client.post = AsyncMock(
        return_value=_mock_openai_response("No JSON here, sorry!")
    )
    mock_client_cls.return_value.__aenter__.return_value = client

    tags = await auto_tag_reel(
        caption="Some reel",
        creator="user",
        provider="openai",
        api_key="sk-test",
        default_tags=["funny"],
    )
    assert tags is None
