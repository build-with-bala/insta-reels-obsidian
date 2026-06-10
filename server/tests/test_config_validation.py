import pytest

from server.config import (
    API_KEY_ENV_VAR,
    ConfigError,
    load_config,
    validate_startup,
)


def _write_config(tmp_path, body: str):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(body)
    return str(config_file)


def test_placeholder_vault_path_rejected(tmp_path):
    path = _write_config(
        tmp_path,
        "vault_path: /path/to/your/obsidian/vault\nllm_api_key: sk-test\n",
    )
    with pytest.raises(ConfigError, match="placeholder"):
        load_config(path)


def test_placeholder_api_key_rejected(tmp_path):
    path = _write_config(
        tmp_path,
        f"vault_path: {tmp_path}\nllm_api_key: your-api-key-here\n",
    )
    with pytest.raises(ConfigError, match="llm_api_key"):
        load_config(path)


def test_empty_api_key_rejected(tmp_path):
    path = _write_config(
        tmp_path,
        f"vault_path: {tmp_path}\nllm_api_key: ''\n",
    )
    with pytest.raises(ConfigError, match="llm_api_key"):
        load_config(path)


def test_empty_vault_path_rejected(tmp_path):
    path = _write_config(tmp_path, "vault_path: ''\nllm_api_key: sk-test\n")
    with pytest.raises(ConfigError, match="vault_path"):
        load_config(path)


def test_env_var_supplies_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "sk-from-env")
    path = _write_config(tmp_path, f"vault_path: {tmp_path}\n")
    config = load_config(path)
    assert config.llm_api_key == "sk-from-env"


def test_env_var_overrides_placeholder_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "sk-from-env")
    path = _write_config(
        tmp_path,
        f"vault_path: {tmp_path}\nllm_api_key: your-api-key-here\n",
    )
    config = load_config(path)
    assert config.llm_api_key == "sk-from-env"


def test_env_var_takes_precedence_over_real_yaml_key(tmp_path, monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "sk-from-env")
    path = _write_config(
        tmp_path,
        f"vault_path: {tmp_path}\nllm_api_key: sk-from-yaml\n",
    )
    config = load_config(path)
    assert config.llm_api_key == "sk-from-env"


def test_new_options_parsed(tmp_path):
    path = _write_config(
        tmp_path,
        f"""
vault_path: {tmp_path}
llm_api_key: sk-test
server_host: 0.0.0.0
cookies_from_browser: chrome
retry_interval_minutes: 5
""",
    )
    config = load_config(path)
    assert config.server_host == "0.0.0.0"
    assert config.cookies_from_browser == "chrome"
    assert config.cookie_file is None
    assert config.retry_interval_minutes == 5


def test_new_options_defaults(tmp_path):
    path = _write_config(tmp_path, f"vault_path: {tmp_path}\nllm_api_key: sk-test\n")
    config = load_config(path)
    assert config.server_host == "127.0.0.1"
    assert config.cookies_from_browser is None
    assert config.cookie_file is None
    assert config.retry_interval_minutes == 10


def test_invalid_retry_interval_rejected(tmp_path):
    path = _write_config(
        tmp_path,
        f"vault_path: {tmp_path}\nllm_api_key: sk-test\n"
        "retry_interval_minutes: often\n",
    )
    with pytest.raises(ConfigError, match="retry_interval_minutes"):
        load_config(path)


def test_validate_startup_ok(tmp_path):
    path = _write_config(
        tmp_path, f"vault_path: {tmp_path}\nllm_api_key: sk-test\n"
    )
    config = load_config(path)
    validate_startup(config)  # should not raise


def test_validate_startup_missing_vault(tmp_path):
    path = _write_config(
        tmp_path,
        f"vault_path: {tmp_path / 'does-not-exist'}\nllm_api_key: sk-test\n",
    )
    config = load_config(path)
    with pytest.raises(ConfigError, match="does not exist"):
        validate_startup(config)


def test_validate_startup_vault_is_file(tmp_path):
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("hi")
    path = _write_config(
        tmp_path, f"vault_path: {not_a_dir}\nllm_api_key: sk-test\n"
    )
    config = load_config(path)
    with pytest.raises(ConfigError, match="not a directory"):
        validate_startup(config)


def test_validate_startup_vault_not_writable(tmp_path):
    vault = tmp_path / "readonly-vault"
    vault.mkdir()
    vault.chmod(0o500)
    try:
        path = _write_config(
            tmp_path, f"vault_path: {vault}\nllm_api_key: sk-test\n"
        )
        config = load_config(path)
        with pytest.raises(ConfigError, match="not writable"):
            validate_startup(config)
    finally:
        vault.chmod(0o700)


def test_validate_startup_missing_cookie_file(tmp_path):
    path = _write_config(
        tmp_path,
        f"vault_path: {tmp_path}\nllm_api_key: sk-test\n"
        f"cookie_file: {tmp_path / 'missing-cookies.txt'}\n",
    )
    config = load_config(path)
    with pytest.raises(ConfigError, match="cookie_file"):
        validate_startup(config)
