import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

logger = logging.getLogger(__name__)

VALID_PROVIDERS = ("openai", "anthropic")

# Environment variable consulted for the LLM API key. Takes precedence over
# config.yaml so real keys can stay out of the (potentially committed) file.
API_KEY_ENV_VAR = "INSTA_REELS_LLM_API_KEY"

# Values that indicate the user never edited the shipped config.
PLACEHOLDER_VAULT_MARKER = "/path/to/"
PLACEHOLDER_API_KEYS = {
    "",
    "your-api-key",
    "your-api-key-here",
    "sk-your-key-here",
    "sk-ant-your-key-here",
}


class ConfigError(Exception):
    pass


@dataclass
class Config:
    vault_path: str
    llm_api_key: str
    llm_provider: str = "openai"
    default_tags: List[str] = field(default_factory=lambda: list(DEFAULT_TAGS))
    server_port: int = 7890
    server_host: str = "127.0.0.1"
    cookies_from_browser: Optional[str] = None
    cookie_file: Optional[str] = None
    retry_interval_minutes: float = 10.0


DEFAULT_TAGS = [
    "funny", "recipe", "travel", "fitness", "tech",
    "music", "fashion", "motivation", "education",
]

REQUIRED_FIELDS = ["vault_path"]


def _resolve_api_key(data: dict, path: str) -> str:
    """Resolve the LLM API key: env var first, config.yaml as fallback."""
    env_key = os.environ.get(API_KEY_ENV_VAR, "").strip()
    if env_key and env_key not in PLACEHOLDER_API_KEYS:
        return env_key

    yaml_key = str(data.get("llm_api_key") or "").strip()
    if yaml_key and yaml_key not in PLACEHOLDER_API_KEYS:
        return yaml_key

    if yaml_key in PLACEHOLDER_API_KEYS and data.get("llm_api_key") is not None:
        raise ConfigError(
            "llm_api_key is empty or still set to a placeholder value.\n"
            f"  Fix: export {API_KEY_ENV_VAR}=<your OpenAI or Anthropic key> "
            f"(recommended), or set llm_api_key in {path}."
        )
    raise ConfigError(
        "No LLM API key configured (missing llm_api_key).\n"
        f"  Fix: export {API_KEY_ENV_VAR}=<your OpenAI or Anthropic key> "
        f"(recommended), or set llm_api_key in {path}."
    )


def load_config(path: str) -> Config:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ConfigError("Config file is empty or malformed")

    for field_name in REQUIRED_FIELDS:
        if field_name not in data:
            raise ConfigError(f"Missing required field: {field_name}")

    vault_path = str(data["vault_path"] or "").strip()
    if not vault_path:
        raise ConfigError(f"vault_path is empty. Set it in {path}.")
    if PLACEHOLDER_VAULT_MARKER in vault_path:
        raise ConfigError(
            f"vault_path is still the placeholder '{vault_path}'.\n"
            f"  Fix: edit {path} and set vault_path to your actual Obsidian "
            "vault directory (it must already exist)."
        )
    vault_path = str(Path(vault_path).expanduser())

    api_key = _resolve_api_key(data, path)

    provider = data.get("llm_provider", "openai")
    if provider not in VALID_PROVIDERS:
        raise ConfigError(
            f"Invalid llm_provider '{provider}'. Must be one of: {VALID_PROVIDERS}"
        )

    port = int(data.get("server_port", 7890))
    if not (1024 <= port <= 65535):
        raise ConfigError(f"server_port must be between 1024 and 65535, got {port}")

    server_host = str(data.get("server_host", "127.0.0.1")).strip() or "127.0.0.1"

    cookies_from_browser = data.get("cookies_from_browser") or None
    if cookies_from_browser is not None:
        cookies_from_browser = str(cookies_from_browser).strip() or None

    cookie_file = data.get("cookie_file") or None
    if cookie_file is not None:
        cookie_file = str(Path(str(cookie_file).strip()).expanduser())

    try:
        retry_interval = float(data.get("retry_interval_minutes", 10))
    except (TypeError, ValueError):
        raise ConfigError(
            "retry_interval_minutes must be a number "
            f"(got {data.get('retry_interval_minutes')!r}). Use 0 to disable."
        )
    if retry_interval < 0:
        raise ConfigError("retry_interval_minutes must be >= 0 (0 disables retries)")

    if not Path(vault_path).exists():
        logger.warning(f"Vault path does not exist yet: {vault_path}")

    return Config(
        vault_path=vault_path,
        llm_api_key=api_key,
        llm_provider=provider,
        default_tags=data.get("default_tags", DEFAULT_TAGS),
        server_port=port,
        server_host=server_host,
        cookies_from_browser=cookies_from_browser,
        cookie_file=cookie_file,
        retry_interval_minutes=retry_interval,
    )


def validate_startup(config: Config) -> None:
    """Extra checks run before the server starts serving.

    Raises ConfigError with an actionable message instead of letting the
    server crash later with a raw OSError.
    """
    vault = Path(config.vault_path)
    if not vault.exists():
        raise ConfigError(
            f"Vault path does not exist: {vault}\n"
            "  Fix: set vault_path in config.yaml to your existing Obsidian "
            "vault directory."
        )
    if not vault.is_dir():
        raise ConfigError(
            f"Vault path is not a directory: {vault}\n"
            "  Fix: vault_path must point to your Obsidian vault folder."
        )
    if not os.access(vault, os.W_OK):
        raise ConfigError(
            f"Vault path is not writable: {vault}\n"
            "  Fix: adjust permissions so this user can write to the vault."
        )
    if config.cookie_file and not Path(config.cookie_file).exists():
        raise ConfigError(
            f"cookie_file does not exist: {config.cookie_file}\n"
            "  Fix: export your Instagram cookies to that file (Netscape "
            "format), or use cookies_from_browser instead."
        )
