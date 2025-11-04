import pytest
from pathlib import Path
from server.vault_writer import VaultWriter


@pytest.fixture
def vault(tmp_path):
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    return VaultWriter(str(vault_path))


def _sample_reel():
    return {
        "id": "ABC123",
        "url": "https://www.instagram.com/reel/ABC123/",
        "creator_username": "chef_anna",
        "creator_display_name": "Chef Anna",
        "caption": "Amazing pasta recipe",
        "tags": ["recipe", "italian", "food"],
        "user_note": "must try this",
        "timestamp": "2025-11-03T14:32:00",
    }


def test_format_reel_entry(vault):
    entry = vault.format_entry(_sample_reel())
    assert "### [Reel by @chef_anna]" in entry
    assert "instagram.com/reel/ABC123" in entry
    assert "2025-11-03 14:32" in entry
    assert "Amazing pasta recipe" in entry
    assert "#recipe" in entry
    assert "must try this" in entry


def test_write_to_log(vault):
    vault.write_reel(_sample_reel())
    log_path = Path(vault.vault_path) / "Instagram Reels" / "Log.md"
    assert log_path.exists()
    content = log_path.read_text()
    assert "@chef_anna" in content
    assert "ABC123" in content


def test_write_to_daily(vault):
    vault.write_reel(_sample_reel())
    daily_path = (
        Path(vault.vault_path) / "Instagram Reels" / "Daily" / "2025-11-03.md"
    )
    assert daily_path.exists()
    content = daily_path.read_text()
    assert "type: instagram-reel-daily" in content
    assert "@chef_anna" in content


def test_write_to_tag_files(vault):
    vault.write_reel(_sample_reel())
    tags_dir = Path(vault.vault_path) / "Instagram Reels" / "Tags"
    assert (tags_dir / "recipe.md").exists()
    assert (tags_dir / "italian.md").exists()
    assert (tags_dir / "food.md").exists()
    content = (tags_dir / "recipe.md").read_text()
    assert "type: instagram-reel-tag" in content
    assert "tag: recipe" in content
    assert "@chef_anna" in content


def test_write_multiple_reels_appends(vault):
    vault.write_reel(_sample_reel())
    reel2 = _sample_reel()
    reel2["id"] = "DEF456"
    reel2["url"] = "https://www.instagram.com/reel/DEF456/"
    reel2["creator_username"] = "travel_mike"
    reel2["timestamp"] = "2025-11-03T15:00:00"
    vault.write_reel(reel2)

    log_path = Path(vault.vault_path) / "Instagram Reels" / "Log.md"
    content = log_path.read_text()
    assert "@chef_anna" in content
    assert "@travel_mike" in content


def test_write_reel_no_tags(vault):
    reel = _sample_reel()
    reel["tags"] = []
    vault.write_reel(reel)
    log_path = Path(vault.vault_path) / "Instagram Reels" / "Log.md"
    assert log_path.exists()


def test_write_reel_missing_optional_fields(vault):
    reel = {
        "id": "MIN123",
        "url": "https://www.instagram.com/reel/MIN123/",
        "creator_username": None,
        "creator_display_name": None,
        "caption": None,
        "tags": ["fetch-failed"],
        "user_note": None,
        "timestamp": "2025-11-03T14:32:00",
    }
    vault.write_reel(reel)
    log_path = Path(vault.vault_path) / "Instagram Reels" / "Log.md"
    content = log_path.read_text()
    assert "MIN123" in content
