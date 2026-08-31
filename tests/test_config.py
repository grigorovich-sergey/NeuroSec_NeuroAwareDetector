from __future__ import annotations

import json

import pytest

from neurosec.foundation.config import ConfigError, resolve_config
from neurosec.foundation.metadata import RunMetadata, write_run_metadata


def _write_configs(tmp_path):
    default = tmp_path / "default.yaml"
    partial = tmp_path / "partial.yaml"
    default.write_text(
        "run:\n  seed: 1\n  mode: practice\nmodel:\n  alpha: 0.5\n  channels: [C3, C4]\n",
        encoding="utf-8",
    )
    partial.write_text("model:\n  alpha: 0.25\n", encoding="utf-8")
    return default, partial


def test_recursive_partial_override_preserves_unspecified_defaults(tmp_path):
    default, partial = _write_configs(tmp_path)

    resolved = resolve_config(default, partial)

    assert resolved["model"] == {"alpha": 0.25, "channels": ["C3", "C4"]}
    assert resolved["run"] == {"seed": 1, "mode": "practice"}


def test_unknown_nested_configuration_key_fails_with_path(tmp_path):
    default, partial = _write_configs(tmp_path)
    partial.write_text("model:\n  beta: 0.1\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=r"model\.beta"):
        resolve_config(default, partial)


def test_type_incompatible_override_fails(tmp_path):
    default, partial = _write_configs(tmp_path)
    partial.write_text("run:\n  seed: wrong\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=r"run\.seed"):
        resolve_config(default, partial)


def test_type_incompatible_list_element_fails(tmp_path):
    default, partial = _write_configs(tmp_path)
    partial.write_text("model:\n  channels: [3, 4]\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=r"model\.channels"):
        resolve_config(default, partial)


def test_cli_override_is_retained_in_written_run_metadata(tmp_path):
    default, partial = _write_configs(tmp_path)
    resolved = resolve_config(default, partial, {"run": {"seed": 99}})
    metadata = RunMetadata.start(
        run_id="test-run",
        mode="practice",
        resolved_config=resolved,
        invocation=("test",),
        project_state={"commit": "abc", "working_tree_clean": True},
        environment={"python": "test"},
        rng_seed=99,
    )
    metadata.mark_completed()
    path = write_run_metadata(metadata, tmp_path / "metadata.json")

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["resolved_config"]["run"]["seed"] == 99
