"""Deterministic synthetic WP0 smoke workflow."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from .config import resolve_config
from .metadata import (
    RunMetadata,
    capture_environment_identity,
    capture_project_state,
    write_run_metadata,
)
from .records import (
    AttackManifest,
    DatasetReference,
    DetectorPolicyOutput,
    EventMarker,
    SourceFileReference,
    TrialRecord,
    WindowScore,
    write_record_json,
)
from .runs import ExecutionMode, RunLayout, new_run_id


def _synthetic_trial(config: Mapping[str, Any]) -> TrialRecord:
    seed = config["run"]["seed"]
    settings = config["synthetic"]
    sample_count = settings["sample_count"]
    sampling_rate_hz = settings["sampling_rate_hz"]
    eeg_names = tuple(settings["eeg_channels"])
    emg_names = tuple(settings["emg_channels"])
    rng = np.random.default_rng(seed)
    timestamps = np.arange(sample_count, dtype=float) / sampling_rate_hz
    eeg = rng.normal(0.0, 1.0, (len(eeg_names), sample_count))
    emg = rng.normal(0.0, 0.2, (len(emg_names), sample_count))
    source_digest = hashlib.sha256(eeg.tobytes() + emg.tobytes()).hexdigest()
    source = DatasetReference(
        identifier="neurosec-synthetic",
        version="1",
        representation="in-memory-smoke",
        files=(
            SourceFileReference(
                path="synthetic://wp0/eeg-emg",
                sha256=source_digest,
                size_bytes=eeg.nbytes + emg.nbytes,
            ),
        ),
    )
    return TrialRecord(
        subject_id="synthetic-subject-01",
        session_id="synthetic-session-01",
        trial_id="synthetic-trial-01",
        source_recording_id="synthetic-recording-01",
        task_label="synthetic-grasp",
        sampling_rate_hz=sampling_rate_hz,
        timestamps_s=timestamps,
        events=(EventMarker(name="trial_start", time_s=0.0, sample_index=0),),
        eeg_samples=eeg,
        eeg_channel_names=eeg_names,
        eeg_coordinates={name: (float(index), 0.0, 1.0) for index, name in enumerate(eeg_names)},
        emg_samples=emg,
        emg_channel_names=emg_names,
        emg_muscle_identities=emg_names,
        preprocessing_state={"state": "raw synthetic"},
        provenance={"generator": "neurosec.foundation.smoke", "seed": seed},
        source_dataset=source,
    )


def run_foundation_smoke(
    *,
    repo_root: str | Path,
    default_config: str | Path,
    partial_config: str | Path | None,
    seed: int | None = None,
    mode: str = ExecutionMode.PRACTICE.value,
    run_id: str | None = None,
    invocation: Sequence[str] | None = None,
) -> Path:
    """Exercise WP0 interfaces and return the generated practice directory."""

    if mode != ExecutionMode.PRACTICE.value:
        raise ValueError("the foundation smoke workflow only produces practice output")
    actual_run_id = new_run_id("wp0-smoke") if run_id is None else run_id
    cli_run: dict[str, Any] = {"mode": mode, "id": actual_run_id}
    if seed is not None:
        cli_run["seed"] = seed
    resolved = resolve_config(default_config, partial_config, {"run": cli_run})
    root = Path(repo_root).resolve()
    layout = RunLayout.from_config(root, resolved["paths"])
    output = layout.create_practice(resolved["run"]["id"])

    trial = _synthetic_trial(resolved)
    attack = AttackManifest(
        attacked_modality="EEG",
        attacked_channels=(trial.eeg_channel_names[0],),
        attack_family="representative-only",
        parameters={"implemented": False},
        severity="not-applicable",
        interval_start_s=0.01,
        interval_end_s=0.05,
        seed=resolved["run"]["seed"],
        expected_attacker_target=None,
    )
    output_record = DetectorPolicyOutput(
        window_scores=(WindowScore(0.0, 0.05, raw_score=None, standardized_score=None),),
        eeg_evidence=None,
        emg_evidence=None,
        unresolved_cross_modal_evidence=None,
        channel_localization_scores=None,
        rolling_state={"implemented": False},
        attribution="unresolved",
        attribution_confidence=None,
        final_action="hold",
        alarm_time_s=None,
        command_decision_time_s=None,
        lookback_s=0.05,
        buffering_delay_s=0.0,
        processing_latency_s=0.0,
    )

    write_record_json(trial, output / "trial.json")
    write_record_json(attack, output / "attack_manifest.json")
    write_record_json(output_record, output / "detector_policy_output.json")
    (output / "resolved_config.yaml").write_text(
        yaml.safe_dump(resolved, sort_keys=False), encoding="utf-8"
    )

    metadata = RunMetadata.start(
        run_id=resolved["run"]["id"],
        mode=resolved["run"]["mode"],
        resolved_config=resolved,
        invocation=tuple(sys.argv if invocation is None else invocation),
        project_state=capture_project_state(root),
        environment=capture_environment_identity(resolved["metadata"]["environment_packages"]),
        rng_seed=resolved["run"]["seed"],
        component_metadata={"wp0_smoke": True, "synthetic_only": True},
    )
    metadata.source_datasets = [trial.source_dataset.to_dict()]
    metadata.attack = {"record": "attack_manifest.json", "implemented": False}
    metadata.detector = {"record": "detector_policy_output.json", "implemented": False}
    metadata.mark_completed()
    write_run_metadata(metadata, output / "run_metadata.json", inventory_root=output)
    return output
