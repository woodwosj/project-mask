"""Configuration module for PROJECT MASK."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).parent / 'default.yaml'


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file. Uses default.yaml if not specified.

    Returns:
        Dictionary containing configuration values.

    Raises:
        FileNotFoundError: If the config file does not exist.
        yaml.YAMLError: If the config file is invalid YAML.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config or {}


def get_config_value(config: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """Get a nested configuration value using dot notation.

    Args:
        config: Configuration dictionary.
        key_path: Dot-separated path to the value (e.g., 'replay.base_wpm').
        default: Default value if key is not found.

    Returns:
        The configuration value or default.
    """
    keys = key_path.split('.')
    value = config

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default

    return value


__all__ = ['load_config', 'get_config_value', 'DEFAULT_CONFIG_PATH']
