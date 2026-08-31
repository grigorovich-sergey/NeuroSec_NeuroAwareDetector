from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from neurosec.foundation.metadata import RunStatus, deterministic_identifier, file_sha256
from neurosec.foundation.runs import RunLayout


def _layout(tmp_path):
    return RunLayout.from_config(
        tmp_path,
        {
            "practice": "runs/practice",
            "experimental_staging": "runs/staging",
            "experimental_completed": "runs/experimental",
        },
    )


def test_practice_output_uses_practice_tree(tmp_path):
    layout = _layout(tmp_path)

    path = layout.create_practice("practice-01")

    assert path == tmp_path / "runs/practice/practice-01"

    repo_root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["git", "check-ignore", "runs/practice/hypothetical-run"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_incomplete_experiment_cannot_be_finalized(tmp_path):
    layout = _layout(tmp_path)
    staging = layout.create_experimental_staging("experiment-01")

    with pytest.raises(ValueError, match="explicitly completed"):
        layout.finalize_experimental(staging, RunStatus.FAILED)

    assert staging.exists()
    assert not (tmp_path / "runs/experimental/experiment-01").exists()


def test_completed_experiment_cannot_be_overwritten(tmp_path):
    layout = _layout(tmp_path)
    staging = layout.create_experimental_staging("experiment-01")
    (staging / "run_metadata.json").write_text(
        json.dumps({"run_id": "experiment-01", "status": "completed"}), encoding="utf-8"
    )
    completed = layout.finalize_experimental(staging, RunStatus.COMPLETED)

    assert completed.exists()
    with pytest.raises(FileExistsError, match="already exists"):
        layout.create_experimental_staging("experiment-01")


def test_running_metadata_cannot_enter_completed_tree(tmp_path):
    layout = _layout(tmp_path)
    staging = layout.create_experimental_staging("experiment-01")
    (staging / "run_metadata.json").write_text(
        json.dumps({"run_id": "experiment-01", "status": "running"}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="metadata is not marked completed"):
        layout.finalize_experimental(staging, RunStatus.COMPLETED)


def test_hashes_and_deterministic_identifiers_are_stable(tmp_path):
    path = tmp_path / "evidence.txt"
    path.write_bytes(b"same input")
    first_hash = file_sha256(path)
    first_id = deterministic_identifier({"subject": "01", "trial": 2})

    assert file_sha256(path) == first_hash
    assert deterministic_identifier({"trial": 2, "subject": "01"}) == first_id
