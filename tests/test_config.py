from pathlib import Path

import pytest
import yaml

from neurosec_core.cli import main
from neurosec_core.config import ConfigError, load_config, resolve_config

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def defaults(tmp_path):
    path = tmp_path / "default.yaml"
    path.write_text("run:\n  seed: 1\nmodel:\n  alpha: 0.5\n  channels: [C3, C4]\n")
    return path


def test_partial_merge_and_cli_precedence(defaults, tmp_path):
    partial = tmp_path / "partial.yaml"
    partial.write_text("run:\n  seed: 2\nmodel:\n  alpha: 0.25\n")
    resolved = resolve_config(defaults, partial, {"run": {"seed": 3}})
    assert resolved == {
        "run": {"seed": 3}, "model": {"alpha": 0.25, "channels": ["C3", "C4"]}
    }


def test_empty_partial_list_cannot_erase_original_cli_element_type(defaults, tmp_path):
    partial = tmp_path / "partial.yaml"
    partial.write_text("model:\n  channels: []\n")
    assert resolve_config(defaults, partial)["model"]["channels"] == []
    with pytest.raises(ConfigError, match=r"model\.channels"):
        resolve_config(defaults, partial, {"model": {"channels": [3, 4]}})
    assert resolve_config(
        defaults, partial, {"model": {"channels": ["Cz"]}}
    )["model"]["channels"] == ["Cz"]


@pytest.mark.parametrize("override, message", [
    ({"model": {"typo": 1}}, r"model\.typo"),
    ({"run": {"seed": True}}, r"run\.seed"),
    ({"model": {"alpha": float("nan")}}, r"model\.alpha"),
    ({"model": {3: "C3"}}, "keys must be strings"),
    ({"model": []}, "model"),
])
def test_invalid_overrides_fail(defaults, override, message):
    with pytest.raises(ConfigError, match=message):
        resolve_config(defaults, cli_overrides=override)


@pytest.mark.parametrize("partial_text", [
    "run:\n  mode: development\n",
    "run:\n  seed: -1\n",
    "paths:\n  pilot: outputs/study\n",
    "paths:\n  smoke: ../external\n",
])
def test_execution_constraints_fail(tmp_path, partial_text):
    partial = tmp_path / "partial.yaml"
    partial.write_text(partial_text)
    with pytest.raises(ConfigError):
        load_config(REPO_ROOT, partial)


def test_cli_prints_resolved_cli_values(monkeypatch, capsys):
    monkeypatch.chdir(REPO_ROOT)
    assert main(["check-config", "--seed", "99"]) == 0
    assert yaml.safe_load(capsys.readouterr().out)["run"] == {"mode": "practice", "seed": 99}
