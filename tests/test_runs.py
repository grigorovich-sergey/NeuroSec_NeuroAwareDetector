import json
import subprocess
from pathlib import Path

import pytest

from neurosec_core.metadata import (
    METADATA_PATH,
    RunMetadata,
    capture_environment_identity,
    capture_project_state,
    deterministic_identifier,
    file_sha256,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _metadata(path, config, *, mode="practice", data_kind="synthetic", cohort_role="development"):
    config["run"]["mode"] = mode
    return RunMetadata.start(
        run_id=path.name, resolved_config=config, invocation=("pytest",),
        project_state=capture_project_state(REPO_ROOT),
        environment=capture_environment_identity(),
        data_kind=data_kind, cohort_role=cohort_role,
    )


def _completed_fixture(layout, config):
    """Simulate final metadata only; every byte remains under local test output."""
    staging = layout.create_experimental_staging("test-study")
    (staging / "results").mkdir()
    (staging / "results/metrics.csv").write_text("fixture_only\n1\n")
    metadata = _metadata(
        staging, config, mode="experimental", data_kind="real", cohort_role="report"
    )
    metadata.mark_completed()
    layout.write_metadata(staging, metadata)
    return staging


def test_practice_snapshot_keeps_config_and_records_failures(layout, config):
    run = layout.create_practice("smoke", "test-smoke")
    config["run"]["seed"] = 99
    metadata = _metadata(run, config)
    config["run"]["seed"] = 100
    (run / "partial.txt").write_text("retained intermediate")
    layout.write_metadata(run, metadata)
    metadata.mark_failed("fixture failure")
    path = layout.write_metadata(run, metadata)
    saved = json.loads(path.read_text())
    assert saved["resolved_config"]["run"]["seed"] == saved["rng_seed"] == 99
    assert saved["status"] == "failed"
    assert saved["failure"]["message"] == "fixture failure"
    assert saved["generated_files"][0]["sha256"] == file_sha256(run / "partial.txt")
    with pytest.raises(ValueError, match="cannot be overwritten"):
        layout.write_metadata(run, metadata)
    with pytest.raises(ValueError, match="cannot change status"):
        metadata.mark_completed()


def test_completed_run_moves_once_and_all_write_paths_reject_reuse(layout, config):
    staging = _completed_fixture(layout, config)
    completed = layout.finalize_experimental(staging, required_files=["results/metrics.csv"])
    assert not staging.exists()
    assert (completed / "results/metrics.csv").is_file()
    with pytest.raises(FileExistsError, match="already exists"):
        layout.create_experimental_staging("test-study")
    with pytest.raises(ValueError, match="writes require"):
        layout.write_metadata(completed, _metadata(completed, config))
    another = layout.create_experimental_staging("another")
    with pytest.raises(FileExistsError):
        layout.create_experimental_staging(another.name)


@pytest.mark.parametrize("change", ["missing", "tampered", "unrecorded"])
def test_finalization_rejects_inventory_mismatches(layout, config, change):
    staging = _completed_fixture(layout, config)
    if change == "missing":
        (staging / "results/metrics.csv").unlink()
    elif change == "tampered":
        (staging / "results/metrics.csv").write_text("fixture_only\n2\n")  # same size
    else:
        (staging / "unexpected.txt").write_text("not inventoried")
    with pytest.raises(ValueError, match="inventory"):
        layout.finalize_experimental(staging, required_files=["results/metrics.csv"])
    assert staging.is_dir()
    assert not (layout.study_root / staging.name).exists()


@pytest.mark.parametrize("required", [[], ["missing.csv"], ["../escape.csv"]])
def test_finalization_requires_declared_present_outputs(layout, config, required):
    staging = _completed_fixture(layout, config)
    with pytest.raises(ValueError):
        layout.finalize_experimental(staging, required_files=required)
    assert staging.exists()


@pytest.mark.parametrize("change", [
    {"status": "running", "finished_at": None},
    {"mode": "practice"},
    {"cohort_role": "development"},
    {"data_kind": "synthetic", "cohort_role": "development"},
    {"run_id": "different"},
    {"schema_version": 2},
    {"resolved_config": []},
    {"project_state": {}},
    {"generated_files": [{"name": "missing.csv", "size_bytes": 0, "sha256": "a" * 64}]},
])
def test_invalid_metadata_cannot_finalize(layout, config, change):
    staging = _completed_fixture(layout, config)
    path = staging / METADATA_PATH
    saved = json.loads(path.read_text())
    saved.update(change)
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError):
        layout.finalize_experimental(staging, required_files=["results/metrics.csv"])
    assert staging.exists()


def test_practice_cannot_be_promoted_and_symlink_artifacts_fail(layout, config, tmp_path):
    practice = layout.create_practice("pilot", "test-pilot")
    with pytest.raises(ValueError, match="only experimental"):
        layout.finalize_experimental(practice, required_files=["any.csv"])
    external = tmp_path / "external.txt"
    external.write_text("mutable source")
    (practice / "link.txt").symlink_to(external)
    with pytest.raises(ValueError, match="symlinks"):
        layout.write_metadata(practice, _metadata(practice, config))


def test_hash_and_environment_provenance():
    assert deterministic_identifier({"a": 1, "b": 2}) == deterministic_identifier({"b": 2, "a": 1})
    with pytest.raises(ValueError):
        deterministic_identifier({"bad": float("nan")})
    assert capture_environment_identity(["neurosec-intentionally-absent"])["packages"] == {
        "neurosec-intentionally-absent": None
    }


def test_generated_practice_and_staging_files_are_ignored():
    paths = [
        "outputs/smoke/run/results.csv", "outputs/pilot/run/results.csv",
        "outputs/study_staging/run/results.csv", "runs/practice/old/results.csv",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"], input="\n".join(paths) + "\n",
        cwd=REPO_ROOT, check=True, text=True, capture_output=True,
    )
    assert result.stdout.splitlines() == paths
    tracked = subprocess.run(
        ["git", "ls-files", "--", "outputs/smoke", "outputs/pilot", "outputs/study_staging"],
        cwd=REPO_ROOT, check=True, text=True, capture_output=True,
    )
    assert not tracked.stdout
    assert subprocess.run(
        ["git", "check-ignore", "outputs/study/report/results.csv"], cwd=REPO_ROOT,
        capture_output=True,
    ).returncode == 1
