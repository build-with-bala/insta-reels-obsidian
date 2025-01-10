import pytest
from pathlib import Path

from server.config import load_config, ConfigError


def test_load_config_valid(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"""
vault_path: {tmp_path / "vault"}
llm_api_key: sk-test-key
llm_provider: openai
default_tags:
  - funny
  - recipe
server_port: 7890
"""
    )
    (tmp_path / "vault").mkdir()
    config = load_config(str(config_file))
    assert config.vault_path == str(tmp_path / "vault")
    assert config.llm_api_key == "sk-test-key"
    assert config.llm_provider == "openai"
    assert config.default_tags == ["funny", "recipe"]
    assert config.server_port == 7890


def test_load_config_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/config.yaml")


def test_load_config_missing_required_field(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("vault_path: /tmp/vault\n")
    with pytest.raises(ConfigError, match="llm_api_key"):
        load_config(str(config_file))


def test_load_config_defaults(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "vault_path: /tmp/vault\nllm_api_key: sk-test\n"
    )
    config = load_config(str(config_file))
    assert config.llm_provider == "openai"
    assert config.server_port == 7890
    assert len(config.default_tags) == 9


def test_load_config_invalid_provider(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "vault_path: /tmp/vault\nllm_api_key: sk-test\nllm_provider: gemini\n"
    )
    with pytest.raises(ConfigError, match="Invalid llm_provider"):
        load_config(str(config_file))


def test_load_config_invalid_port(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "vault_path: /tmp/vault\nllm_api_key: sk-test\nserver_port: 80\n"
    )
    with pytest.raises(ConfigError, match="server_port"):
        load_config(str(config_file))
