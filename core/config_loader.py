"""
Config loader for Nova.

Loads config.yaml (PyYAML) and .env (python-dotenv) at startup.
Validates required keys and raises clear errors if missing.
"""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv


REQUIRED_KEYS = [
    ("brain", "model"),
    ("brain", "base_url"),
    ("memory", "db_path"),
]


def load_config(config_path: str = "config.yaml") -> dict:
    """
    Load configuration from config_path and .env.

    Args:
        config_path: Path to the YAML config file. Defaults to "config.yaml".

    Returns:
        dict: Parsed configuration.

    Raises:
        FileNotFoundError: If config_path does not exist.
        ValueError: If required configuration keys are missing.
    """
    # Load .env into environment (silently ignores missing .env)
    load_dotenv(dotenv_path=".env", override=False)

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Copy config.example.yaml to config.yaml and fill in your settings."
        )

    with config_file.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    _validate(config, config_path)
    return config


def _validate(config: dict, config_path: str) -> None:
    """Validate that all required keys are present in the config."""
    for key_path in REQUIRED_KEYS:
        node = config
        for part in key_path:
            if not isinstance(node, dict) or part not in node:
                dotted = ".".join(key_path)
                raise ValueError(
                    f"Missing required config key '{dotted}' in {config_path}"
                )
            node = node[part]
