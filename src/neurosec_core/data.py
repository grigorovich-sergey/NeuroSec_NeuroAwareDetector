"""Approved single-recording BrainVision pilot; no config or run orchestration.

Source units and pairing come from the header and the joint sample clock.
Only trial-local SciPy filtering transforms the selected, scaled samples.
See docs/data_notes.md for the frozen scope and artifact/diagnostic schemas.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from scipy.signal import butter, periodogram, sosfiltfilt

from .contracts import SignalPair
from .metadata import capture_environment_identity, deterministic_identifier, file_sha256

ADAPTER_VERSION = "c1-brainvision-1"
SCHEMA_VERSION = 1
INDEX_COLUMNS = (
    "trial_id", "subject_id", "session_id", "source_recording_id", "source_event_id",
    "source_event_ordinal", "source_marker_description", "source_marker_position_1based",
    "onset_reference", "onset_seconds", "end_seconds_exclusive", "eeg_source_file",
    "emg_source_file", "eeg_start_index0", "eeg_stop_index0_exclusive", "emg_start_index0",
    "emg_stop_index0_exclusive", "label", "split", "eeg_array_file", "emg_array_file",
    "array_index",
)
_INTEGER_COLUMNS = {
    "subject_id", "session_id", "source_event_ordinal", "source_marker_position_1based",
    "eeg_start_index0", "eeg_stop_index0_exclusive", "emg_start_index0",
    "emg_stop_index0_exclusive", "label", "array_index",
}
_FLOAT_COLUMNS = {"onset_seconds", "end_seconds_exclusive"}
_INDEX_TYPES = {key: "int" if key in _INTEGER_COLUMNS else "float" if key in _FLOAT_COLUMNS else "str"
                for key in INDEX_COLUMNS}
_ROLES = ("train", "calibration", "donor", "test")
# These constants are approval guards, not alternate defaults. All parameters
# used for computation are read from the supplied resolved configuration.
_EEG = "FC5 FC3 FC1 FC2 FC4 FC6 C5 C3 C1 Cz C2 C4 C6 CP5 CP3 CP1 CPz CP2 CP4 CP6".split()
_EMG = [f"EMG_{i}" for i in range(1, 7)]
_CLASSES = [
    dict(label=0, name="Cup", event_code=11, preparation_cue_code=1),
    dict(label=1, name="Ball", event_code=21, preparation_cue_code=2),
    dict(label=2, name="Card", event_code=61, preparation_cue_code=6),
]
_PREPARATION = dict(
    onset_reference="execution_cue", window_seconds=3.0, units="V",
    retain_native_rates=True, eeg_design_n=4, eeg_band_hz=[2.0, 30.0],
    emg_design_n=5, emg_band_hz=[10.0, 450.0], emg_rectify=True,
    filter_scope="trial", padtype="odd", padlen=None,
)
_SPLIT = dict(
    order="within_class_chronological", train_percent=50, calibration_percent=20,
    donor_percent=10, minimum_trials_per_class=20,
)
_DIAGNOSTIC_PROTOCOL = dict(
    version=1, selection="first valid chronological trial of each class",
    channels={"eeg": "C3", "emg": "EMG_1"}, trace="full window, native samples",
    spectrum=dict(method="scipy.signal.periodogram", window="hann",
                  detrend="constant", scaling="density", return_onesided=True),
    quality_exclusions=False,
)


def _same(value: Any, expected: Any) -> bool:
    """Preserve booleans/types while permitting YAML's integer/float notation."""
    if isinstance(expected, dict):
        return (isinstance(value, Mapping) and set(value) == set(expected)
                and all(_same(value[k], v) for k, v in expected.items()))
    if isinstance(expected, list):
        return (isinstance(value, list) and len(value) == len(expected)
                and all(_same(a, b) for a, b in zip(value, expected)))
    if type(expected) is float:
        return type(value) in (int, float) and value == expected
    return type(value) is type(expected) and value == expected


def _filename(value: str) -> str:
    if (not isinstance(value, str) or not value or value in (".", "..")
            or any(c in value for c in ("/", "\\", ":", "\x00"))):
        raise ValueError(f"expected a plain sibling filename: {value!r}")
    return value


def _validate_config(config: Mapping[str, Any], *, source_required: bool = True) -> None:
    """Validate this approved adapter's semantics, after the shared YAML loader."""
    try:
        data = config["data"]
        if config["run"]["mode"] != "practice":
            raise ValueError("C1 currently supports practice mode only")
        for name, expected in (("preparation", _PREPARATION), ("split", _SPLIT)):
            if not _same(config[name], expected):
                raise ValueError(f"{name} differs from the approved C1 recipe")
        for name, expected in (("representation", "brainvision_int16_multiplexed"),
                               ("cohort_role", "development"), ("classes", _CLASSES),
                               ("eeg_channels", _EEG), ("emg_channels", _EMG)):
            if not _same(data[name], expected):
                raise ValueError(f"data.{name} differs from the approved C1 contract")
        if data["data_kind"] not in ("real", "synthetic"):
            raise ValueError("data.data_kind must be real or synthetic")
        if not isinstance(data["dataset_doi"], str) or not data["dataset_doi"]:
            raise ValueError("dataset_doi must identify the source")
        if data["data_kind"] == "real" and data["dataset_doi"] != "10.5524/100788":
            raise ValueError("only the approved real dataset is supported")
        if not isinstance(data["recordings"], list) or len(data["recordings"]) != 1:
            raise ValueError("C1 supports exactly one pilot recording")
        recording = data["recordings"][0]
        for key, expected in dict(subject_id=1, session_id=1, task="multigrasp",
                                  condition="realMove").items():
            if not _same(recording[key], expected):
                raise ValueError(f"recordings[0].{key} is outside the approved pilot")
        for role in ("header", "marker", "binary"):
            _filename(recording[f"{role}_file"])
            digest = recording[f"{role}_sha256"]
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"invalid {role}_sha256")
        if len({recording[f"{r}_file"] for r in ("header", "marker", "binary")}) != 3:
            raise ValueError("three distinct source files are required")
        if source_required:
            root = data["source_root"]
            if not isinstance(root, str) or not root or not Path(root).is_absolute():
                raise ValueError("data.source_root must be explicitly resolved to an absolute path")
            if not Path(root).is_dir():
                raise ValueError("data.source_root is not a directory")
    except (KeyError, TypeError) as error:
        raise ValueError(f"incomplete resolved C1 configuration: {error}") from error


def _text_sections(path: Path, signature: str) -> tuple[dict[str, dict[str, str]], str]:
    """Strict UTF-8 BrainVision sections; [Comment] is opaque free text."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0].strip() != signature:
        raise ValueError(f"unsupported BrainVision signature: {path.name}")
    sections: dict[str, dict[str, str]] = {}
    current = None
    for index, line in enumerate(lines[1:], 1):
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line == "[Comment]":
            return sections, "\n".join(lines[index + 1:])
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            if current in sections:
                raise ValueError(f"duplicate section {current} in {path.name}")
            sections[current] = {}
        elif current is None or "=" not in line:
            raise ValueError(f"malformed section entry in {path.name}: {line!r}")
        else:
            key, value = (part.strip() for part in line.split("=", 1))
            if key in sections[current]:
                raise ValueError(f"duplicate key {key} in {path.name}")
            sections[current][key] = value
    return sections, ""


def _positive_number(value: str, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _read_header(path: Path, recording: Mapping[str, Any], data: Mapping[str, Any],
                 preparation: Mapping[str, Any]) -> dict[str, Any]:
    sections, comments = _text_sections(
        path, "Brain Vision Data Exchange Header File Version 1.0"
    )
    try:
        common, binary = sections["Common Infos"], sections["Binary Infos"]
        if (common["Codepage"] != "UTF-8" or common["DataFormat"] != "BINARY"
                or common["DataOrientation"] != "MULTIPLEXED"
                or binary["BinaryFormat"] != "INT_16"
                or any(section.get("UseBigEndianOrder", "NO") != "NO" for section in (common, binary))
                or any(section.get("DataOffset", "0") != "0" for section in (common, binary))):
            raise ValueError("unsupported BrainVision layout (need UTF-8, multiplexed little-endian INT_16)")
        if (common["DataFile"] != recording["binary_file"]
                or common["MarkerFile"] != recording["marker_file"]):
            raise ValueError("header source-file references do not match the configuration")
        count = int(common["NumberOfChannels"])
        if count != 71:
            raise ValueError("the observed C1 layout requires 71 source columns")
        rate = 1e6 / _positive_number(common["SamplingInterval"], "SamplingInterval")
        for modality in ("eeg", "emg"):
            if rate / 2 <= preparation[f"{modality}_band_hz"][1]:
                raise ValueError(f"native Nyquist frequency is insufficient for the {modality} band")
        entries = sections["Channel Infos"]
        if set(entries) != {f"Ch{i}" for i in range(1, count + 1)}:
            raise ValueError("Channel Infos must uniquely define every ChN source column")
        channels = []
        for number in range(1, count + 1):
            fields = entries[f"Ch{number}"].split(",")
            if len(fields) < 4 or any(fields[4:]):
                raise ValueError("unsupported channel fields")
            name, reference, resolution, unit = fields[:4]
            name, reference = name.replace("\\1", ","), reference.replace("\\1", ",")
            if not name or unit not in ("µV", "μV", "uV"):
                raise ValueError(f"missing channel name or unsupported source unit at Ch{number}")
            resolution = _positive_number(resolution, "channel resolution")
            channels.append(dict(name=name, reference=reference, source_column_1based=number,
                                 resolution=resolution, unit=unit, volts_per_count=resolution * 1e-6))
        names = [channel["name"] for channel in channels]
        if len(set(names)) != len(names):
            raise ValueError("duplicate source channel name")
        selected = {}
        for modality in ("eeg", "emg"):
            if any(name not in names for name in data[f"{modality}_channels"]):
                raise ValueError(f"missing required {modality} channel")
            selected[modality] = [channels[names.index(name)] for name in data[f"{modality}_channels"]]
        return dict(sample_rate_hz=rate, sampling_interval_us=float(common["SamplingInterval"]),
                    channel_count=count, dtype="<i2", orientation="MULTIPLEXED", channels=channels,
                    selected_channels=selected, common_infos=common, binary_infos=binary,
                    acquisition_comments=comments)
    except KeyError as error:
        raise ValueError(f"missing BrainVision header field: {error}") from error


def _read_markers(path: Path, binary_name: str, samples: int) -> list[dict[str, Any]]:
    sections, _ = _text_sections(path, "Brain Vision Data Exchange Marker File, Version 1.0")
    try:
        if (sections["Common Infos"]["Codepage"] != "UTF-8"
                or sections["Common Infos"]["DataFile"] != binary_name):
            raise ValueError("marker source reference/encoding does not match the header")
        events = []
        previous = 0
        for ordinal, (key, value) in enumerate(sections["Marker Infos"].items(), 1):
            if not re.fullmatch(r"Mk[1-9][0-9]*", key):
                raise ValueError(f"invalid original event ID: {key}")
            fields = value.split(",")
            if len(fields) not in (5, 6):
                raise ValueError(f"unsupported marker fields: {key}")
            kind, description = (x.replace("\\1", ",") for x in fields[:2])
            position, size, channel = map(int, fields[2:5])
            if position < previous or position < 1 or position > samples or size < 1 or not 0 <= channel <= 71:
                raise ValueError(f"invalid or unordered marker: {key}")
            previous = position
            match = re.fullmatch(r"S\s*(\d+)", description) if kind == "Stimulus" else None
            events.append(dict(source_event_id=key, source_event_ordinal=ordinal, type=kind,
                               description=description, position_1based=position, size=size,
                               channel=channel, clock=fields[5] if len(fields) == 6 else None,
                               stimulus_code=int(match[1]) if match else None))
        segments = [e for e in events if e["type"] == "New Segment"]
        if not segments or segments[0]["position_1based"] != 1:
            raise ValueError("the recording must start with a New Segment at sample 1")
        positions = [e["position_1based"] for e in segments]
        if len(set(positions)) != len(positions):
            raise ValueError("ambiguous duplicate New Segment positions")
        return events
    except KeyError as error:
        raise ValueError(f"missing BrainVision marker field: {error}") from error


def _source_files(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    data, files = config["data"], []
    recording = data["recordings"][0]
    for role in ("header", "marker", "binary"):
        name = recording[f"{role}_file"]
        path = Path(data["source_root"]) / name
        digest = file_sha256(path)
        if digest != recording[f"{role}_sha256"]:
            raise ValueError(f"source SHA-256 mismatch: {name}")
        files.append(dict(role=role, name=name, size_bytes=path.stat().st_size, sha256=digest))
    return files


def _recording_identity(data: Mapping[str, Any]) -> dict[str, Any]:
    recording = data["recordings"][0]
    return dict(dataset_doi=data["dataset_doi"],
                **{key: recording[key] for key in ("subject_id", "session_id", "task", "condition")},
                source_hashes={key: recording[key] for key in
                               ("header_sha256", "marker_sha256", "binary_sha256")})


def _assign_splits(rows: list[dict[str, Any]], split: Mapping[str, Any]) -> str | None:
    # Input rows already follow the original acquisition order.
    classes = [[row for row in rows if row["label"] == label] for label in (0, 1, 2)]
    if any(len(group) < split["minimum_trials_per_class"] for group in classes):
        return "fewer than 20 structurally valid trials in at least one class"
    for group in classes:
        counts = [len(group) * split[f"{role}_percent"] // 100 for role in _ROLES[:3]]
        counts.append(len(group) - sum(counts))
        offset = 0
        for role, count in zip(_ROLES, counts):
            for row in group[offset:offset + count]:
                row["split"] = role
            offset += count
    return None


def _trial_rows(source: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[list, list, str | None]:
    data, preparation = config["data"], config["preparation"]
    recording = data["recordings"][0]
    recording_id = deterministic_identifier(_recording_identity(data), length=32)
    rate = source["header"]["sample_rate_hz"]
    length = round(preparation["window_seconds"] * rate)
    classes = {entry["event_code"]: entry for entry in data["classes"]}
    segments = [event["position_1based"] - 1 for event in source["events"]
                if event["type"] == "New Segment"]
    stimuli = [event for event in source["events"] if event["type"] == "Stimulus"]
    allowed_codes = {1, 2, 6, 8, 11, 21, 61, 13, 14}
    if any(event["stimulus_code"] not in allowed_codes for event in stimuli):
        raise ValueError("stimulus codes outside the observed executed-grasp protocol")
    rows, exclusions, previous_stop = [], [], None
    for index, event in enumerate(stimuli):
        code = event["stimulus_code"]
        if code not in classes:
            continue
        if event["size"] != 1 or event["channel"] != 0:
            raise ValueError("execution cues must be size-one markers on the joint clock")
        start = event["position_1based"] - 1
        stop = start + length
        if previous_stop is not None and start < previous_stop:
            raise ValueError("ambiguous duplicate or overlapping execution windows")
        previous_stop = stop
        row = dict(
            trial_id=deterministic_identifier(dict(source_recording_id=recording_id,
                subject_id=recording["subject_id"], session_id=recording["session_id"],
                source_event_id=event["source_event_id"]), length=32),
            subject_id=recording["subject_id"], session_id=recording["session_id"],
            source_recording_id=recording_id, source_event_id=event["source_event_id"],
            source_event_ordinal=event["source_event_ordinal"],
            source_marker_description=event["description"],
            source_marker_position_1based=event["position_1based"],
            onset_reference=preparation["onset_reference"], onset_seconds=start / rate,
            end_seconds_exclusive=stop / rate, eeg_source_file=recording["binary_file"],
            emg_source_file=recording["binary_file"], eeg_start_index0=start,
            eeg_stop_index0_exclusive=stop, emg_start_index0=start, emg_stop_index0_exclusive=stop,
            label=classes[code]["label"], split=None, eeg_array_file="eeg_s01.npy",
            emg_array_file="emg_s01.npy", array_index=len(rows),
        )
        reasons = []
        if stop > source["sample_count"]:
            reasons.append("incomplete_source_window")
        if any(start < boundary < stop for boundary in segments):
            reasons.append("window_crosses_new_segment")
        if reasons:
            exclusions.append(dict(trial_id=row["trial_id"], source_event_id=event["source_event_id"],
                                   label=row["label"], start_index0=start,
                                   stop_index0_exclusive=stop, reasons=reasons))
            continue
        # A contradictory cue/rest context requires source review, not a new label
        # or an automatic exclusion. No extra time offset is inferred from it.
        if (index == 0 or index + 1 == len(stimuli)
                or stimuli[index - 1]["stimulus_code"] != classes[code]["preparation_cue_code"]
                or stimuli[index - 1]["position_1based"] >= event["position_1based"]
                or stimuli[index + 1]["stimulus_code"] != 8
                or stimuli[index + 1]["position_1based"] - 1 < stop):
            raise ValueError(f"execution cue/rest context contradicts the approved protocol: {event['source_event_id']}")
        rows.append(row)
    error = _assign_splits(rows, config["split"])
    return rows, exclusions, error


def _counts(rows: list[dict[str, Any]], exclusions: list[dict[str, Any]]) -> dict[str, Any]:
    return dict(valid=len(rows), excluded=len(exclusions), candidates=len(rows) + len(exclusions),
                by_class={str(label): sum(r["label"] == label for r in rows) for label in (0, 1, 2)},
                by_split={role: sum(r["split"] == role for r in rows) for role in _ROLES},
                by_class_and_split={str(label): {role: sum(r["label"] == label and r["split"] == role
                                                          for r in rows) for role in _ROLES}
                                    for label in (0, 1, 2)})


def _raw_array(config: Mapping[str, Any], source: Mapping[str, Any]) -> np.memmap:
    path = Path(config["data"]["source_root"]) / config["data"]["recordings"][0]["binary_file"]
    return np.memmap(path, dtype="<i2", mode="r", shape=(source["sample_count"], 71))


def _raw_trial(raw: np.ndarray, row: Mapping[str, Any], source: Mapping[str, Any], modality: str) -> np.ndarray:
    selected = source["header"]["selected_channels"][modality]
    columns = [channel["source_column_1based"] - 1 for channel in selected]
    block = raw[row[f"{modality}_start_index0"]:row[f"{modality}_stop_index0_exclusive"]]
    # Cast before arithmetic; no int16 overflow or reference subtraction.
    return block[:, columns].T.astype(np.float64) * np.array(
        [channel["volts_per_count"] for channel in selected], dtype=np.float64
    )[:, None]


def _source_quality(raw: np.ndarray, source: Mapping[str, Any]) -> list[dict[str, Any]]:
    low, high = np.full(71, 32767), np.full(71, -32768)
    lower, upper = np.zeros(71, dtype=np.int64), np.zeros(71, dtype=np.int64)
    for start in range(0, len(raw), 100_000):
        block = raw[start:start + 100_000]
        low = np.minimum(low, block.min(axis=0))
        high = np.maximum(high, block.max(axis=0))
        lower += (block == -32768).sum(axis=0)
        upper += (block == 32767).sum(axis=0)
    return [dict(channel=channel["name"], source_column_1based=i + 1,
                 minimum_count=int(low[i]), maximum_count=int(high[i]), flat=bool(low[i] == high[i]),
                 at_lower_digital_limit=int(lower[i]), at_upper_digital_limit=int(upper[i]))
            for i, channel in enumerate(source["header"]["channels"])]


def _trace_spectrum(values: np.ndarray, rate: float) -> dict[str, Any]:
    frequency, density = periodogram(values, fs=rate, window="hann", detrend="constant",
                                     scaling="density", return_onesided=True)
    return dict(trace_volts=values.tolist(), frequency_hz=frequency.tolist(),
                power_density_v2_per_hz=density.tolist())


def inspect_sources(config: Mapping[str, Any]) -> dict[str, Any]:
    """Hash/inspect the local source; return JSON data, creating no artifacts.

    An insufficient class count is returned as split_error for inspection;
    preparation refuses it. Contradictory/ambiguous source semantics raise.
    Numerical quality is reported without quality-based exclusions.
    """
    _validate_config(config)
    data, files = config["data"], _source_files(config)
    recording = data["recordings"][0]
    root = Path(data["source_root"])
    header = _read_header(root / recording["header_file"], recording, data, config["preparation"])
    size = files[2]["size_bytes"]
    if size == 0 or size % (2 * header["channel_count"]):
        raise ValueError("binary byte count is not a positive whole number of 71-channel INT_16 frames")
    samples = size // (2 * header["channel_count"])
    source = dict(files=files, recording_identity=_recording_identity(data),
                  source_recording_id=deterministic_identifier(_recording_identity(data), length=32),
                  header=header, sample_count=samples, duration_seconds=samples / header["sample_rate_hz"],
                  events=_read_markers(root / recording["marker_file"], recording["binary_file"], samples),
                  clock_timezone=None, whole_archive_sha256=None)
    rows, exclusions, split_error = _trial_rows(source, config)
    # Freeze selection using event metadata before observing any sample values.
    selected_rows = [next((row for row in rows if row["label"] == label), None) for label in (0, 1, 2)]
    raw = _raw_array(config, source)
    quality = _source_quality(raw, source)
    traces = []
    for row in selected_rows:
        if row is None:
            continue
        for modality, channel in _DIAGNOSTIC_PROTOCOL["channels"].items():
            values = _raw_trial(raw, row, source, modality)[data[f"{modality}_channels"].index(channel)]
            traces.append(dict(trial_id=row["trial_id"], source_event_id=row["source_event_id"],
                               label=row["label"], modality=modality, channel=channel,
                               sample_rate_hz=header["sample_rate_hz"],
                               raw=_trace_spectrum(values, header["sample_rate_hz"])))
    del raw
    if _source_files(config) != files:
        raise ValueError("source changed during inspection")
    warnings = [
        "Execution cues are protocol timing, not measured physiological onset.",
        "Source acquisition comments are retained; saved versus display software filtering is unresolved.",
        "Whole-archive checksum is unavailable; extracted-file hashes are verified.",
        "Classwise split ranges interleave; C3 must check each donor end against each recipient onset.",
    ]
    if "Test Signal from actiCAP" in header["acquisition_comments"]:
        warnings.append("The actiCAP test-source preference comment does not establish whether test mode was active.")
    if any("test" in event["description"].lower() for event in source["events"]):
        warnings.append("Marker descriptions mentioning test mode require acquisition review.")
    if any(q["flat"] or q["at_lower_digital_limit"] or q["at_upper_digital_limit"] for q in quality):
        warnings.append("Source flat-channel or digital-limit findings require review; no quality exclusions applied.")
    return dict(schema_version=SCHEMA_VERSION, adapter_version=ADAPTER_VERSION,
                data_kind=data["data_kind"], cohort_role=data["cohort_role"], source=source,
                stimulus_counts=dict(Counter(str(e["stimulus_code"]) for e in source["events"]
                                             if e["type"] == "Stimulus")),
                trials=rows, exclusions=exclusions, counts=_counts(rows, exclusions), split_error=split_error,
                diagnostics=dict(protocol=deepcopy(_DIAGNOSTIC_PROTOCOL), source_channels=quality, traces=traces),
                warnings=warnings)


def _recipe_identity(config: Mapping[str, Any]) -> dict[str, Any]:
    return dict(adapter_version=ADAPTER_VERSION, preparation=config["preparation"],
                **{key: config["data"][key] for key in ("classes", "eeg_channels", "emg_channels")})


def _split_identity(config: Mapping[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return dict(parameters=config["split"], assignments=[dict(trial_id=r["trial_id"], split=r["split"]) for r in rows])


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def prepare_dataset(config: Mapping[str, Any], out_dir: str | Path) -> dict[str, Any]:
    """Write one new four-file dataset inside a caller-allocated practice run.

    Caller owns running/terminal metadata and retains partial files on error.
    The directory must not exist; its parent must already exist. dataset.json
    is written last, so interrupted arrays cannot be mistaken for a dataset.
    """
    _validate_config(config)
    destination = Path(out_dir)
    destination.mkdir(exist_ok=False)
    report = inspect_sources(config)
    if report["split_error"]:
        raise ValueError(report["split_error"])
    rows, source = report.pop("trials"), report["source"]
    rate = source["header"]["sample_rate_hz"]
    length = round(config["preparation"]["window_seconds"] * rate)
    raw = _raw_array(config, source)
    arrays, array_specs, filters = {}, {}, {}
    trial_findings = []
    try:
        for modality in ("eeg", "emg"):
            name = f"{modality}_s01.npy"
            shape = (len(rows), len(config["data"][f"{modality}_channels"]), length)
            arrays[modality] = np.lib.format.open_memmap(destination / name, mode="w+", dtype=np.float64, shape=shape)
            array_specs[modality] = dict(file=name, shape=list(shape), dtype="float64", units="V", sample_rate_hz=rate)
            filters[modality] = butter(config["preparation"][f"{modality}_design_n"],
                config["preparation"][f"{modality}_band_hz"], btype="bandpass", fs=rate, output="sos")
        for row in rows:
            for modality in ("eeg", "emg"):
                values = _raw_trial(raw, row, source, modality)
                prepared = sosfiltfilt(filters[modality], values, axis=-1,
                                      padtype=config["preparation"]["padtype"],
                                      padlen=config["preparation"]["padlen"])
                if modality == "emg" and config["preparation"]["emg_rectify"]:
                    prepared = np.abs(prepared)
                if not np.isfinite(prepared).all():
                    raise ValueError(f"nonfinite preparation output: {row['trial_id']} {modality}")
                arrays[modality][row["array_index"]] = prepared
                for i, channel in enumerate(config["data"][f"{modality}_channels"]):
                    scale = source["header"]["selected_channels"][modality][i]["volts_per_count"]
                    flat_raw = bool(np.ptp(values[i]) == 0)
                    flat_prepared = bool(np.ptp(prepared[i]) == 0)
                    lower = int(np.count_nonzero(values[i] == -32768 * scale))
                    upper = int(np.count_nonzero(values[i] == 32767 * scale))
                    if flat_raw or flat_prepared or lower or upper:
                        trial_findings.append(dict(trial_id=row["trial_id"], modality=modality, channel=channel,
                            raw_flat=flat_raw, prepared_flat=flat_prepared,
                            at_lower_digital_limit=lower, at_upper_digital_limit=upper))
                for trace in report["diagnostics"]["traces"]:
                    if trace["trial_id"] == row["trial_id"] and trace["modality"] == modality:
                        index = config["data"][f"{modality}_channels"].index(trace["channel"])
                        trace["prepared"] = _trace_spectrum(prepared[index], rate)
        for modality in arrays:
            arrays[modality].flush()
    finally:
        # Explicitly release mappings on Windows before the caller inventories
        # or handles a failed run. No partial output is removed.
        del raw
        arrays.clear()
    if _source_files(config) != source["files"]:
        raise ValueError("source changed during preparation")
    report["diagnostics"]["trial_findings"] = trial_findings
    if trial_findings:
        report["warnings"].append("Trial flat-channel/digital-limit findings retained without exclusions.")
    with (destination / "trials.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=INDEX_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    recipe_id = deterministic_identifier(_recipe_identity(config), length=32)
    split_id = deterministic_identifier(_split_identity(config, rows), length=32)
    # Store portable scientific configuration; local paths, seeds and the full
    # resolved execution configuration belong in the shared run metadata.
    portable = json.loads(json.dumps({key: config[key] for key in ("run", "data", "preparation", "split")}))
    portable["data"].pop("source_root")
    manifest = dict(
        **report, artifact_kind="neurosec_prepared_dataset", config=portable,
        recipe_id=recipe_id, split_id=split_id,
        dataset_id=deterministic_identifier(dict(source_recording_id=source["source_recording_id"],
                                               recipe_id=recipe_id, split_id=split_id,
                                               schema_version=SCHEMA_VERSION), length=32),
        class_order=[0, 1, 2], arrays=array_specs, index_file="trials.csv",
        index_columns=list(INDEX_COLUMNS),
        index_types=dict(_INDEX_TYPES),
        environment=capture_environment_identity(("neurosec-core", "numpy", "PyYAML", "scipy")),
        filter_sos={key: value.tolist() for key, value in filters.items()},
        artifacts=[dict(name=name, size_bytes=(destination / name).stat().st_size,
                        sha256=file_sha256(destination / name))
                   for name in ("trials.csv", "eeg_s01.npy", "emg_s01.npy")],
    )
    _write_json(destination / "dataset.json", manifest)
    return manifest


def _manifest(prepared_dir: Path) -> dict[str, Any]:
    try:
        value = json.loads((prepared_dir / "dataset.json").read_text(encoding="utf-8"))
        if (type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION
                or value["adapter_version"] != ADAPTER_VERSION
                or value["artifact_kind"] != "neurosec_prepared_dataset"
                or value["index_file"] != "trials.csv" or value["index_columns"] != list(INDEX_COLUMNS)
                or value["index_types"] != _INDEX_TYPES or value["class_order"] != [0, 1, 2]):
            raise ValueError("unsupported prepared dataset schema")
        _validate_config(value["config"], source_required=False)
        if (value["data_kind"] != value["config"]["data"]["data_kind"]
                or value["cohort_role"] != value["config"]["data"]["cohort_role"]
                or value["source"]["recording_identity"] != _recording_identity(value["config"]["data"])
                or value["source"]["source_recording_id"] != deterministic_identifier(
                    value["source"]["recording_identity"], length=32)
                or value["recipe_id"] != deterministic_identifier(_recipe_identity(value["config"]), length=32)):
            raise ValueError("inconsistent dataset/recording/recipe provenance")
        recording = value["config"]["data"]["recordings"][0]
        files = value["source"]["files"]
        if len(files) != 3:
            raise ValueError("three source file identities are required")
        for role, item in zip(("header", "marker", "binary"), files):
            if (item["role"] != role or item["name"] != recording[f"{role}_file"]
                    or item["sha256"] != recording[f"{role}_sha256"]
                    or type(item["size_bytes"]) is not int or item["size_bytes"] <= 0):
                raise ValueError("inconsistent source file identity")
        if (type(value["source"]["sample_count"]) is not int
                or value["source"]["sample_count"] * 142 != files[2]["size_bytes"]):
            raise ValueError("inconsistent source sample count")
        return value
    except (KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        raise ValueError(f"missing or invalid prepared manifest: {error}") from error


def _open_arrays(directory: Path, manifest: Mapping[str, Any], count: int) -> dict[str, np.memmap]:
    arrays = {}
    for modality in ("eeg", "emg"):
        spec = manifest["arrays"][modality]
        rate = manifest["source"]["header"]["sample_rate_hz"]
        shape = (count, len(manifest["config"]["data"][f"{modality}_channels"]),
                 round(manifest["config"]["preparation"]["window_seconds"] * rate))
        expected = dict(file=f"{modality}_s01.npy", shape=list(shape), dtype="float64", units="V", sample_rate_hz=rate)
        if spec != expected:
            raise ValueError(f"inconsistent {modality} array specification")
        path = directory / spec["file"]
        if path.is_symlink():
            raise ValueError("prepared arrays must be local regular files")
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        if not isinstance(array, np.memmap) or array.shape != shape or array.dtype != np.dtype(np.float64):
            raise ValueError(f"invalid {modality} NPY shape/dtype")
        arrays[modality] = array
    return arrays


def _read_prepared(directory: Path) -> tuple[dict, list, dict]:
    manifest = _manifest(directory)
    try:
        with (directory / "trials.csv").open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(INDEX_COLUMNS):
                raise ValueError("invalid trial index schema/column order")
            rows = []
            for row in reader:
                if set(row) != set(INDEX_COLUMNS) or any(v is None or v == "" for v in row.values()):
                    raise ValueError("incomplete trial index row")
                for key in _INTEGER_COLUMNS:
                    row[key] = int(row[key])
                for key in _FLOAT_COLUMNS:
                    row[key] = float(row[key])
                    if not np.isfinite(row[key]):
                        raise ValueError("nonfinite trial time")
                rows.append(row)
        expected, exclusions, error = _trial_rows(manifest["source"], manifest["config"])
        if error or rows != expected or manifest["exclusions"] != exclusions:
            raise ValueError("trial index disagrees with original events, IDs, intervals or splits")
        if (manifest["counts"] != _counts(rows, exclusions)
                or manifest["split_error"] is not None
                or len({r["trial_id"] for r in rows}) != len(rows)
                or len({r["source_event_id"] for r in rows}) != len(rows)
                or manifest["split_id"] != deterministic_identifier(_split_identity(manifest["config"], rows), length=32)):
            raise ValueError("inconsistent counts, trial identities or split provenance")
        identity = dict(source_recording_id=manifest["source"]["source_recording_id"],
                        recipe_id=manifest["recipe_id"], split_id=manifest["split_id"], schema_version=SCHEMA_VERSION)
        if manifest["dataset_id"] != deterministic_identifier(identity, length=32):
            raise ValueError("inconsistent dataset identity")
        arrays = _open_arrays(directory, manifest, len(rows))
        return manifest, rows, arrays
    except (KeyError, TypeError, OSError) as error:
        raise ValueError(f"invalid prepared index or array reference: {error}") from error


def read_index(prepared_dir: str | Path) -> list[dict[str, Any]]:
    """Read typed acquisition-order rows and verify source, split and NPY references.

    Does not scan signal samples or hash full artifacts on each lookup. The
    caller's run-level verification must check manifest/inventory file hashes.
    """
    _, rows, _ = _read_prepared(Path(prepared_dir))
    return rows


def load_trial(prepared_dir: str | Path, trial_id: str) -> SignalPair:
    """Select one trial from read-only NPY mappings, then copy into SignalPair."""
    directory = Path(prepared_dir)
    manifest, rows, arrays = _read_prepared(directory)
    row = next((row for row in rows if row["trial_id"] == trial_id), None)
    if row is None:
        raise KeyError(f"unknown trial_id: {trial_id}")
    data = manifest["config"]["data"]
    return SignalPair(
        eeg=arrays["eeg"][row["array_index"]], emg=arrays["emg"][row["array_index"]],
        fs_eeg=manifest["arrays"]["eeg"]["sample_rate_hz"],
        fs_emg=manifest["arrays"]["emg"]["sample_rate_hz"],
        eeg_channels=tuple(data["eeg_channels"]), emg_channels=tuple(data["emg_channels"]),
    )
