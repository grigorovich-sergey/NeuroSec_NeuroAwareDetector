"""Strict default, partial-YAML, and limited-CLI configuration resolution."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml


class ConfigError(ValueError):
    """Raised when configuration input violates the default schema."""


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ConfigError(f"configuration must be a mapping: {path}")
    if not all(isinstance(key, str) for key in value):
        raise ConfigError(f"configuration keys must be strings: {path}")
    return value


def _type_compatible(default: Any, replacement: Any) -> bool:
    if default is None:
        return replacement is None
    if isinstance(default, bool):
        return isinstance(replacement, bool)
    if isinstance(default, float):
        return isinstance(replacement, (int, float)) and not isinstance(replacement, bool)
    if isinstance(default, int):
        return isinstance(replacement, int) and not isinstance(replacement, bool)
    if isinstance(default, list):
        if not isinstance(replacement, list):
            return False
        if not default:
            return True
        exemplar = default[0]
        return all(_type_compatible(exemplar, item) for item in replacement)
    return isinstance(replacement, type(default))


def _merge_known(
    resolved: dict[str, Any], override: Mapping[str, Any], path: tuple[str, ...] = ()
) -> None:
    for key, replacement in override.items():
        current_path = path + (key,)
        dotted = ".".join(current_path)
        if key not in resolved:
            raise ConfigError(f"unknown configuration key: {dotted}")

        default = resolved[key]
        if isinstance(default, dict):
            if not isinstance(replacement, Mapping):
                raise ConfigError(
                    f"type mismatch at {dotted}: expected mapping, "
                    f"got {type(replacement).__name__}"
                )
            _merge_known(default, replacement, current_path)
        else:
            if not _type_compatible(default, replacement):
                raise ConfigError(
                    f"type mismatch at {dotted}: expected {type(default).__name__}, "
                    f"got {type(replacement).__name__}"
                )
            resolved[key] = float(replacement) if isinstance(default, float) else deepcopy(replacement)


def resolve_config(
    default_path: str | Path,
    partial_path: str | Path | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a complete default with a partial YAML and nested CLI mapping.

    Both override sources are checked against the keys and value types in the
    complete default. Nested mappings merge; scalar values and lists replace.
    """

    resolved = deepcopy(_load_yaml_mapping(Path(default_path)))
    if partial_path is not None:
        _merge_known(resolved, _load_yaml_mapping(Path(partial_path)))
    if cli_overrides:
        _merge_known(resolved, cli_overrides)
    return resolved
