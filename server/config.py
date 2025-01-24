import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

logger = logging.getLogger(__name__)

VALID_PROVIDERS = ("openai", "anthropic")


class ConfigError(Exception):
    pass


@dataclass
class Config:
    vault_path: str
    llm_api_key: str
    llm_provider: str = "openai"
    default_tags: List[str] = field(default_factory=lambda: list(DEFAULT_TAGS))
    server_port: int = 7890


DEFAULT_TAGS = [
    "funny", "recipe", "travel", "fitness", "tech",
    "music", "fashion", "motivation", "education",
]

REQUIRED_FIELDS = ["vault_path", "llm_api_key"]


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

    provider = data.get("llm_provider", "openai")
    if provider not in VALID_PROVIDERS:
        raise ConfigError(
            f"Invalid llm_provider '{provider}'. Must be one of: {VALID_PROVIDERS}"
        )

    port = int(data.get("server_port", 7890))
    if not (1024 <= port <= 65535):
        raise ConfigError(f"server_port must be between 1024 and 65535, got {port}")

    vault_path = Path(data["vault_path"])
    if not vault_path.exists():
        logger.warning(f"Vault path does not exist yet: {vault_path}")

    return Config(
        vault_path=str(data["vault_path"]),
        llm_api_key=str(data["llm_api_key"]),
        llm_provider=provider,
        default_tags=data.get("default_tags", DEFAULT_TAGS),
        server_port=port,
    )
