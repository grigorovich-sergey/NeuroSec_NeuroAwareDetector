"""Typed shared EEG/EMG records and documented JSON serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


def _json_value(value: Any, path: str = "value") -> JSONValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, np.generic):
        return _json_value(value.item(), path)
    if isinstance(value, np.ndarray):
        return _json_value(value.tolist(), path)
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError(f"{path} mapping keys must be strings")
        return {key: _json_value(item, f"{path}.{key}") for key, item in value.items()}
    raise TypeError(f"{path} is not JSON serializable: {type(value).__name__}")


def _readonly_float_array(value: Any, *, ndim: int, name: str) -> np.ndarray:
    array = np.array(value, dtype=float, copy=True)
    if array.ndim != ndim:
        raise ValueError(f"{name} must have {ndim} dimensions, got {array.ndim}")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    array.setflags(write=False)
    return array


def _nonempty_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class EventMarker:
    name: str
    time_s: float
    sample_index: int

    def __post_init__(self) -> None:
        _nonempty_text(self.name, "event name")
        if self.sample_index < 0:
            raise ValueError("event sample_index must be non-negative")

    def to_dict(self) -> dict[str, JSONValue]:
        return {"name": self.name, "time_s": self.time_s, "sample_index": self.sample_index}


@dataclass(frozen=True, slots=True)
class SourceFileReference:
    path: str
    sha256: str
    size_bytes: int | None = None

    def __post_init__(self) -> None:
        _nonempty_text(self.path, "source file path")
        if len(self.sha256) != 64 or any(ch not in "0123456789abcdef" for ch in self.sha256.lower()):
            raise ValueError("source file sha256 must be a 64-character hexadecimal digest")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("source file size_bytes must be non-negative")

    def to_dict(self) -> dict[str, JSONValue]:
        return {"path": self.path, "sha256": self.sha256, "size_bytes": self.size_bytes}


@dataclass(frozen=True, slots=True)
class DatasetReference:
    identifier: str
    version: str
    representation: str
    files: tuple[SourceFileReference, ...]

    def __post_init__(self) -> None:
        _nonempty_text(self.identifier, "dataset identifier")
        _nonempty_text(self.version, "dataset version")
        _nonempty_text(self.representation, "dataset representation")
        if not self.files:
            raise ValueError("dataset reference must include at least one source file")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "identifier": self.identifier,
            "version": self.version,
            "representation": self.representation,
            "files": [item.to_dict() for item in self.files],
        }


@dataclass(frozen=True, slots=True)
class TrialRecord:
    subject_id: str
    session_id: str
    trial_id: str
    source_recording_id: str
    task_label: str
    sampling_rate_hz: float
    timestamps_s: np.ndarray
    events: tuple[EventMarker, ...]
    eeg_samples: np.ndarray
    eeg_channel_names: tuple[str, ...]
    emg_samples: np.ndarray
    emg_channel_names: tuple[str, ...]
    source_dataset: DatasetReference
    preprocessing_state: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    eeg_coordinates: Mapping[str, Sequence[float]] | None = None
    emg_muscle_identities: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        for name in (
            "subject_id",
            "session_id",
            "trial_id",
            "source_recording_id",
            "task_label",
        ):
            _nonempty_text(getattr(self, name), name)
        if self.sampling_rate_hz <= 0:
            raise ValueError("sampling_rate_hz must be positive")

        timestamps = _readonly_float_array(self.timestamps_s, ndim=1, name="timestamps_s")
        eeg = _readonly_float_array(self.eeg_samples, ndim=2, name="eeg_samples")
        emg = _readonly_float_array(self.emg_samples, ndim=2, name="emg_samples")
        object.__setattr__(self, "timestamps_s", timestamps)
        object.__setattr__(self, "eeg_samples", eeg)
        object.__setattr__(self, "emg_samples", emg)

        sample_count = timestamps.shape[0]
        if sample_count == 0:
            raise ValueError("trial must contain at least one sample")
        if sample_count > 1 and not np.all(np.diff(timestamps) > 0):
            raise ValueError("timestamps_s must be strictly increasing")
        if sample_count > 1 and not np.allclose(
            np.diff(timestamps), 1.0 / self.sampling_rate_hz, rtol=1e-3, atol=1e-9
        ):
            raise ValueError("timestamps_s are inconsistent with sampling_rate_hz")
        if eeg.shape != (len(self.eeg_channel_names), sample_count):
            raise ValueError("EEG channel names, samples, and timestamps are not aligned")
        if emg.shape != (len(self.emg_channel_names), sample_count):
            raise ValueError("EMG channel names, samples, and timestamps are not aligned")
        if not self.eeg_channel_names or not self.emg_channel_names:
            raise ValueError("both EEG and EMG must contain at least one channel")
        if len(set(self.eeg_channel_names)) != len(self.eeg_channel_names):
            raise ValueError("EEG channel names must be unique")
        if len(set(self.emg_channel_names)) != len(self.emg_channel_names):
            raise ValueError("EMG channel names must be unique")
        for channel in self.eeg_channel_names + self.emg_channel_names:
            _nonempty_text(channel, "channel name")
        if any(event.sample_index >= sample_count for event in self.events):
            raise ValueError("event sample_index lies outside the trial")
        for event in self.events:
            if not np.isclose(
                event.time_s,
                timestamps[event.sample_index],
                rtol=0.0,
                atol=0.5 / self.sampling_rate_hz,
            ):
                raise ValueError("event time is inconsistent with its sample_index")
        if self.emg_muscle_identities is not None and len(self.emg_muscle_identities) != len(
            self.emg_channel_names
        ):
            raise ValueError("EMG muscle identities must align with EMG channels")
        if self.eeg_coordinates is not None:
            unknown = set(self.eeg_coordinates) - set(self.eeg_channel_names)
            if unknown:
                raise ValueError(f"EEG coordinates contain unknown channels: {sorted(unknown)}")
            for channel, coordinate in self.eeg_coordinates.items():
                if len(coordinate) != 3:
                    raise ValueError(f"EEG coordinate for {channel} must have three values")
                if not np.isfinite(np.asarray(coordinate, dtype=float)).all():
                    raise ValueError(f"EEG coordinate for {channel} must be finite")
        _json_value(self.preprocessing_state, "preprocessing_state")
        _json_value(self.provenance, "provenance")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "subject_id": self.subject_id,
            "session_id": self.session_id,
            "trial_id": self.trial_id,
            "source_recording_id": self.source_recording_id,
            "task_label": self.task_label,
            "sampling_rate_hz": self.sampling_rate_hz,
            "timestamps_s": self.timestamps_s.tolist(),
            "events": [event.to_dict() for event in self.events],
            "eeg_samples": self.eeg_samples.tolist(),
            "eeg_channel_names": list(self.eeg_channel_names),
            "eeg_coordinates": _json_value(self.eeg_coordinates, "eeg_coordinates"),
            "emg_samples": self.emg_samples.tolist(),
            "emg_channel_names": list(self.emg_channel_names),
            "emg_muscle_identities": (
                None if self.emg_muscle_identities is None else list(self.emg_muscle_identities)
            ),
            "preprocessing_state": _json_value(self.preprocessing_state, "preprocessing_state"),
            "provenance": _json_value(self.provenance, "provenance"),
            "source_dataset": self.source_dataset.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TrialRecord":
        allowed = {
            "subject_id",
            "session_id",
            "trial_id",
            "source_recording_id",
            "task_label",
            "sampling_rate_hz",
            "timestamps_s",
            "events",
            "eeg_samples",
            "eeg_channel_names",
            "eeg_coordinates",
            "emg_samples",
            "emg_channel_names",
            "emg_muscle_identities",
            "preprocessing_state",
            "provenance",
            "source_dataset",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown TrialRecord fields: {sorted(unknown)}")
        source = value["source_dataset"]
        dataset = DatasetReference(
            identifier=source["identifier"],
            version=source["version"],
            representation=source["representation"],
            files=tuple(SourceFileReference(**item) for item in source["files"]),
        )
        return cls(
            subject_id=value["subject_id"],
            session_id=value["session_id"],
            trial_id=value["trial_id"],
            source_recording_id=value["source_recording_id"],
            task_label=value["task_label"],
            sampling_rate_hz=value["sampling_rate_hz"],
            timestamps_s=value["timestamps_s"],
            events=tuple(EventMarker(**item) for item in value["events"]),
            eeg_samples=value["eeg_samples"],
            eeg_channel_names=tuple(value["eeg_channel_names"]),
            eeg_coordinates=value.get("eeg_coordinates"),
            emg_samples=value["emg_samples"],
            emg_channel_names=tuple(value["emg_channel_names"]),
            emg_muscle_identities=(
                None
                if value.get("emg_muscle_identities") is None
                else tuple(value["emg_muscle_identities"])
            ),
            preprocessing_state=value.get("preprocessing_state", {}),
            provenance=value.get("provenance", {}),
            source_dataset=dataset,
        )


@dataclass(frozen=True, slots=True)
class AttackManifest:
    attacked_modality: str
    attacked_channels: str | tuple[str, ...]
    attack_family: str
    parameters: Mapping[str, Any]
    severity: str | float | int
    interval_start_s: float
    interval_end_s: float
    seed: int
    replay_donor: Mapping[str, Any] | None = None
    channel_identity_mapping: Mapping[str, str] | None = None
    timing_modifications: Mapping[str, Any] | None = None
    metadata_modifications: Mapping[str, Any] | None = None
    expected_attacker_target: str | None = None

    def __post_init__(self) -> None:
        if self.attacked_modality not in {"EEG", "EMG"}:
            raise ValueError("attacked_modality must be exactly EEG or EMG")
        if self.attacked_channels != "all" and (
            not isinstance(self.attacked_channels, tuple) or not self.attacked_channels
        ):
            raise ValueError("attacked_channels must be 'all' or a non-empty tuple")
        if isinstance(self.attacked_channels, tuple):
            for channel in self.attacked_channels:
                _nonempty_text(channel, "attacked channel")
        _nonempty_text(self.attack_family, "attack_family")
        if self.interval_start_s < 0 or self.interval_end_s <= self.interval_start_s:
            raise ValueError("attack interval must be positive and ordered")
        for name in (
            "parameters",
            "replay_donor",
            "channel_identity_mapping",
            "timing_modifications",
            "metadata_modifications",
        ):
            _json_value(getattr(self, name), name)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "attacked_modality": self.attacked_modality,
            "attacked_channels": (
                self.attacked_channels
                if self.attacked_channels == "all"
                else list(self.attacked_channels)
            ),
            "attack_family": self.attack_family,
            "parameters": _json_value(self.parameters, "parameters"),
            "severity": self.severity,
            "interval_start_s": self.interval_start_s,
            "interval_end_s": self.interval_end_s,
            "seed": self.seed,
            "replay_donor": _json_value(self.replay_donor, "replay_donor"),
            "channel_identity_mapping": _json_value(
                self.channel_identity_mapping, "channel_identity_mapping"
            ),
            "timing_modifications": _json_value(
                self.timing_modifications, "timing_modifications"
            ),
            "metadata_modifications": _json_value(
                self.metadata_modifications, "metadata_modifications"
            ),
            "expected_attacker_target": self.expected_attacker_target,
        }


@dataclass(frozen=True, slots=True)
class WindowScore:
    start_s: float
    end_s: float
    raw_score: float | None
    standardized_score: float | None

    def __post_init__(self) -> None:
        if self.start_s < 0 or self.end_s <= self.start_s:
            raise ValueError("window times must be positive and ordered")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "start_s": self.start_s,
            "end_s": self.end_s,
            "raw_score": self.raw_score,
            "standardized_score": self.standardized_score,
        }


@dataclass(frozen=True, slots=True)
class DetectorPolicyOutput:
    window_scores: tuple[WindowScore, ...]
    eeg_evidence: float | None
    emg_evidence: float | None
    unresolved_cross_modal_evidence: float | None
    channel_localization_scores: Mapping[str, float] | None
    rolling_state: Mapping[str, Any] | None
    attribution: str
    attribution_confidence: float | None
    final_action: str
    alarm_time_s: float | None
    command_decision_time_s: float | None
    lookback_s: float
    buffering_delay_s: float
    processing_latency_s: float

    def __post_init__(self) -> None:
        if self.attribution not in {"EEG", "EMG", "unresolved", "none"}:
            raise ValueError("invalid attribution label")
        if self.final_action not in {
            "normal_fusion",
            "eeg_only_fallback",
            "emg_only_fallback",
            "abstention",
            "hold",
        }:
            raise ValueError("invalid final action")
        if self.attribution_confidence is not None and not 0 <= self.attribution_confidence <= 1:
            raise ValueError("attribution_confidence must be in [0, 1]")
        if min(self.lookback_s, self.buffering_delay_s, self.processing_latency_s) < 0:
            raise ValueError("lookback and delay fields must be non-negative")
        _json_value(self.channel_localization_scores, "channel_localization_scores")
        _json_value(self.rolling_state, "rolling_state")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "window_scores": [item.to_dict() for item in self.window_scores],
            "eeg_evidence": self.eeg_evidence,
            "emg_evidence": self.emg_evidence,
            "unresolved_cross_modal_evidence": self.unresolved_cross_modal_evidence,
            "channel_localization_scores": _json_value(
                self.channel_localization_scores, "channel_localization_scores"
            ),
            "rolling_state": _json_value(self.rolling_state, "rolling_state"),
            "attribution": self.attribution,
            "attribution_confidence": self.attribution_confidence,
            "final_action": self.final_action,
            "alarm_time_s": self.alarm_time_s,
            "command_decision_time_s": self.command_decision_time_s,
            "lookback_s": self.lookback_s,
            "buffering_delay_s": self.buffering_delay_s,
            "processing_latency_s": self.processing_latency_s,
        }


Record = TrialRecord | AttackManifest | DetectorPolicyOutput


def write_record_json(record: Record, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "record_type": type(record).__name__,
        "data": record.to_dict(),
    }
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    return destination


def read_trial_record_json(path: str | Path) -> TrialRecord:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("record_type") != "TrialRecord":
        raise ValueError("file is not a supported TrialRecord JSON document")
    return TrialRecord.from_dict(payload["data"])
