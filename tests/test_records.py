from __future__ import annotations

import json

import pytest

from neurosec.foundation.records import (
    AttackManifest,
    DetectorPolicyOutput,
    TrialRecord,
    WindowScore,
    read_trial_record_json,
    write_record_json,
)


def test_trial_record_channel_alignment_survives_json_round_trip(tmp_path, trial_record):
    path = write_record_json(trial_record, tmp_path / "trial.json")

    restored = read_trial_record_json(path)

    assert restored.eeg_channel_names == trial_record.eeg_channel_names
    assert restored.emg_channel_names == trial_record.emg_channel_names
    assert restored.eeg_samples.shape == trial_record.eeg_samples.shape
    assert restored.emg_samples.shape == trial_record.emg_samples.shape
    assert restored.timestamps_s.shape == trial_record.timestamps_s.shape


def test_misaligned_channels_fail(trial_record):
    value = trial_record.to_dict()
    value["eeg_channel_names"] = ["C3"]

    with pytest.raises(ValueError, match="EEG channel names"):
        TrialRecord.from_dict(value)


def test_eog_cannot_enter_core_trial_record(trial_record):
    value = trial_record.to_dict()
    value["eog_samples"] = [[0.0] * 5]

    with pytest.raises(ValueError, match="eog_samples"):
        TrialRecord.from_dict(value)


def test_attack_manifest_rejects_multiple_modalities():
    with pytest.raises(ValueError, match="exactly EEG or EMG"):
        AttackManifest(
            attacked_modality=("EEG", "EMG"),  # type: ignore[arg-type]
            attacked_channels="all",
            attack_family="test",
            parameters={},
            severity=1,
            interval_start_s=0.1,
            interval_end_s=0.2,
            seed=1,
        )


def test_unavailable_detector_evidence_serializes_as_null(tmp_path):
    output = DetectorPolicyOutput(
        window_scores=(WindowScore(0.0, 1.0, None, None),),
        eeg_evidence=None,
        emg_evidence=None,
        unresolved_cross_modal_evidence=None,
        channel_localization_scores=None,
        rolling_state=None,
        attribution="unresolved",
        attribution_confidence=None,
        final_action="hold",
        alarm_time_s=None,
        command_decision_time_s=None,
        lookback_s=1.0,
        buffering_delay_s=0.0,
        processing_latency_s=0.0,
    )

    path = write_record_json(output, tmp_path / "output.json")
    data = json.loads(path.read_text(encoding="utf-8"))["data"]

    assert data["eeg_evidence"] is None
    assert data["emg_evidence"] is None
    assert data["window_scores"][0]["standardized_score"] is None
