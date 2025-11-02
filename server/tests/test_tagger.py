import pytest
from unittest.mock import patch
from server.tagger import auto_tag_reel, _build_prompt


@pytest.mark.asyncio
@patch("server.tagger._call_openai")
async def test_auto_tag_openai(mock_call):
    mock_call.return_value = ["recipe", "italian", "food"]
    tags = await auto_tag_reel(
        caption="Amazing homemade pasta recipe",
        creator="chef_anna",
        provider="openai",
        api_key="sk-test",
        default_tags=["recipe", "funny", "travel"],
    )
    assert tags == ["recipe", "italian", "food"]
    mock_call.assert_called_once()


@pytest.mark.asyncio
@patch("server.tagger._call_anthropic")
async def test_auto_tag_anthropic(mock_call):
    mock_call.return_value = ["funny", "cats"]
    tags = await auto_tag_reel(
        caption="Hilarious cat compilation",
        creator="cat_lover",
        provider="anthropic",
        api_key="sk-test",
        default_tags=["funny", "recipe"],
    )
    assert tags == ["funny", "cats"]


@pytest.mark.asyncio
@patch("server.tagger._call_openai")
async def test_auto_tag_failure_returns_none(mock_call):
    mock_call.side_effect = Exception("API error")
    tags = await auto_tag_reel(
        caption="Some reel",
        creator="user",
        provider="openai",
        api_key="sk-test",
        default_tags=[],
    )
    assert tags is None


def test_build_prompt_includes_context():
    prompt = _build_prompt("pasta recipe", "chef_anna", ["recipe", "funny"])
    assert "pasta recipe" in prompt
    assert "chef_anna" in prompt
    assert "recipe" in prompt


def test_build_prompt_default_tags():
    prompt = _build_prompt("test", "user", [])
    assert "funny" in prompt
    assert "education" in prompt
