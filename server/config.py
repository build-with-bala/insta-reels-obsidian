from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml


class ConfigError(Exception):
    pass


@dataclass
class Config:
    vault_path: str
    llm_api_key: str
    llm_provider: str = "openai"
    default_tags: List[str] = field(
        default_factory=lambda: [
            "funny", "recipe", "travel", "fitness", "tech",
            "music", "fashion", "motivation", "education",
        ]
    )
    server_port: int = 7890


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

    return Config(
        vault_path=str(data["vault_path"]),
        llm_api_key=str(data["llm_api_key"]),
        llm_provider=data.get("llm_provider", "openai"),
        default_tags=data.get("default_tags", Config.default_tags),
        server_port=int(data.get("server_port", 7890)),
    )
