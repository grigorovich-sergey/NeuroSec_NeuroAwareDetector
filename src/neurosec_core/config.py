"""Complete YAML defaults, recursively merged partial YAML, then CLI overrides."""

from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml

from .runs import RunLayout


class ConfigError(ValueError):
    """Configuration violates the original defaults or execution constraints."""


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConfigError(f"invalid YAML in {path}: {error}") from error
    if not isinstance(value, dict):
        raise ConfigError(f"configuration must be a mapping: {path}")
    return value


def _validate_default(value: Any, path: str = "config") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ConfigError(f"configuration keys must be strings at {path}")
            _validate_default(child, f"{path}.{key}")
    elif isinstance(value, list):
        if not value:
            raise ConfigError(f"{path}: an empty default list has no element type")
        for item in value:
            _validate_default(item, path)
            if not _type_compatible(value[0], item):
                raise ConfigError(f"{path}: default lists must be homogeneous")
    elif not (value is None or isinstance(value, (str, bool, int, float))):
        raise ConfigError(f"unsupported configuration value at {path}")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ConfigError(f"nonfinite configuration value at {path}")


def _type_compatible(default: Any, replacement: Any) -> bool:
    if isinstance(default, dict):
        return (
            isinstance(replacement, Mapping)
            and replacement.keys() == default.keys()
            and all(_type_compatible(default[key], replacement[key]) for key in default)
        )
    if isinstance(default, list):
        return isinstance(replacement, list) and all(
            _type_compatible(default[0], item) for item in replacement
        )
    if isinstance(default, float):
        return (
            isinstance(replacement, (int, float))
            and not isinstance(replacement, bool)
            and math.isfinite(replacement)
        )
    return type(replacement) is type(default)


def _merge_known(
    resolved: dict[str, Any],
    schema: Mapping[str, Any],
    override: Mapping[str, Any],
    path: tuple[str, ...] = (),
) -> None:
    for key, replacement in override.items():
        if not isinstance(key, str):
            raise ConfigError(f"configuration keys must be strings at {'.'.join(path)}")
        dotted = ".".join((*path, key))
        if key not in schema:
            raise ConfigError(f"unknown configuration key: {dotted}")
        default = schema[key]
        if isinstance(default, dict) and isinstance(replacement, Mapping):
            _merge_known(resolved[key], default, replacement, (*path, key))
        elif not _type_compatible(default, replacement):
            raise ConfigError(f"type mismatch at {dotted}: expected {type(default).__name__}")
        else:
            resolved[key] = float(replacement) if isinstance(default, float) else deepcopy(replacement)


def resolve_config(
    default_path: str | Path,
    partial_path: str | Path | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate both override layers against the untouched original defaults.

    Mappings merge; lists/scalars replace. Nonempty homogeneous default lists
    declare their element type; an override may replace such a list with [].
    A null default accepts only null. No untyped extension keys are supported.
    """
    schema = _load_yaml_mapping(Path(default_path))
    _validate_default(schema)
    resolved = deepcopy(schema)
    if partial_path is not None:
        _merge_known(resolved, schema, _load_yaml_mapping(Path(partial_path)))
    if cli_overrides is not None:
        _merge_known(resolved, schema, cli_overrides)
    return resolved


def load_config(
    repo_root: str | Path,
    partial_path: str | Path | None = None,
    *,
    mode: str | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """The shared entry point for CLI and future H; also checks execution paths."""
    overrides = {}
    if mode is not None:
        overrides["mode"] = mode
    if seed is not None:
        overrides["seed"] = seed
    config = resolve_config(
        Path(repo_root) / "configs/core_v0.yaml", partial_path, {"run": overrides}
    )
    if config["run"]["mode"] not in ("practice", "experimental"):
        raise ConfigError("run.mode must be practice or experimental")
    if type(config["run"]["seed"]) is not int or config["run"]["seed"] < 0:
        raise ConfigError("run.seed must be a nonnegative integer")
    try:
        RunLayout.from_config(repo_root, config["paths"])
    except ValueError as error:
        raise ConfigError(str(error)) from error
    return config
