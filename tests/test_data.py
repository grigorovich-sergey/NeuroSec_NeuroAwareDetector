"""Claim-critical synthetic checks. No real samples, downloads or study runs."""

import csv
import json
import shutil
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from fixtures.data.brainvision_fixture import CHANNELS, LENGTH, RATE, make_source
from neurosec_core import data
from neurosec_core.config import load_config
from neurosec_core.metadata import (
    RunMetadata, capture_environment_identity, capture_project_state,
    file_sha256,
)
from neurosec_core.runs import RunLayout, new_run_id

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    root = tmp_path_factory.mktemp("c1-source")
    return make_source(root / "source", load_config(REPO_ROOT))


def _prepare_run(config, root, name):
    layout = RunLayout.from_config(root, config["paths"])
    run = layout.create_practice("smoke", new_run_id(name))
    record = RunMetadata.start(
        run_id=run.name, resolved_config=config, invocation=("pytest", "tests/test_data.py", name),
        project_state=capture_project_state(REPO_ROOT),
        environment=capture_environment_identity(("neurosec-core", "numpy", "PyYAML", "scipy")),
        data_kind=config["data"]["data_kind"], cohort_role=config["data"]["cohort_role"],
    )
    layout.write_metadata(run, record)
    try:
        manifest = data.prepare_dataset(config, run / "prepared")
        record.inputs = manifest["source"]["files"]
        record.components = {key: manifest[key] for key in ("dataset_id", "recipe_id", "split_id", "adapter_version")}
        record.warnings = manifest["warnings"]
        record.exclusions = [json.dumps(item, sort_keys=True) for item in manifest["exclusions"]]
        record.mark_completed()
    except BaseException as error:
        record.mark_failed(str(error))
        raise
    finally:
        layout.write_metadata(run, record)
    return run / "prepared", manifest


@pytest.fixture(scope="module")
def prepared(source, tmp_path_factory):
    return _prepare_run(source, tmp_path_factory.mktemp("c1-prepared"), "first")


def test_source_column_scaling_marker_clock_and_comments(source, prepared):
    _, manifest = prepared
    src = manifest["source"]
    header = src["header"]
    assert header["sample_rate_hz"] == RATE
    assert header["selected_channels"]["eeg"][7]["source_column_1based"] == 16
    assert [c["source_column_1based"] for c in header["selected_channels"]["emg"]] == list(range(65, 71))
    assert "[This is not an INI section]" in header["acquisition_comments"]
    assert src["events"][1]["description"] == "Synthetic, fixture"
    assert src["events"][0]["clock"] == "20000101000000000000"
    assert src["clock_timezone"] is None
    first = data.read_index(prepared[0])[0]
    assert (first["source_event_id"], first["source_event_ordinal"], first["label"]) == ("Mk5", 5, 1)
    assert first["eeg_start_index0"] == first["emg_start_index0"] == RATE
    assert first["eeg_stop_index0_exclusive"] == first["emg_stop_index0_exclusive"] == RATE + LENGTH
    assert first["source_marker_position_1based"] == RATE + 1
    assert (first["onset_seconds"], first["end_seconds_exclusive"]) == (1.0, 4.0)
    assert first["eeg_source_file"] == first["emg_source_file"] == "fixture.eeg"
    traces = [t for t in manifest["diagnostics"]["traces"] if t["source_event_id"] == "Mk5"]
    assert traces[0]["channel"] == "C3"
    assert traces[0]["raw"]["trace_volts"][0] == pytest.approx(12345 * 1e-7)
    assert traces[1]["raw"]["trace_volts"][0] == pytest.approx(-2345 * 1e-5)
    # A 30000-count EMG_ref must not be subtracted from EMG_1.
    assert len(traces[1]["raw"]["trace_volts"]) == LENGTH
    assert manifest["data_kind"] == "synthetic"
    assert all(item["sha256"] == file_sha256(Path(source["data"]["source_root"]) / item["name"])
               for item in src["files"])


def _sin_cos_amplitude(values, frequency):
    t = np.arange(len(values)) / RATE
    return 2 * np.array([np.dot(values, np.sin(2 * np.pi * frequency * t)),
                         np.dot(values, np.cos(2 * np.pi * frequency * t))]) / len(values)


def test_actual_filter_passband_stopband_phase_rectification_and_isolation(prepared):
    directory, _ = prepared
    rows = data.read_index(directory)
    pair = data.load_trial(directory, rows[1]["trial_id"])
    assert pair.eeg.shape == (20, LENGTH) and pair.emg.shape == (6, LENGTH)
    assert pair.fs_eeg == pair.fs_emg == RATE
    assert pair.eeg.dtype == pair.emg.dtype == np.float64
    assert not pair.eeg.flags.writeable and not pair.emg.flags.writeable
    assert np.isfinite(pair.eeg).all() and np.isfinite(pair.emg).all()
    central = pair.eeg[7, RATE:2 * RATE]
    sin10, cos10 = _sin_cos_amplitude(central, 10)
    expected = 800 * (1 + CHANNELS.index("C3") / 71) * 1e-7
    assert sin10 == pytest.approx(expected, rel=0.02)
    assert abs(cos10) < 0.02 * expected
    assert np.linalg.norm(_sin_cos_amplitude(central, 200)) < 0.005 * expected
    assert pair.emg.min() >= 0
    assert pair.emg[0, RATE:2 * RATE].mean() == pytest.approx(300 * 1e-5 * 2 / np.pi, rel=0.03)
    # All later raw trial windows are identical despite different source times
    # and neighboring impulses in the first trial. They must prepare identically.
    for modality in ("eeg", "emg"):
        array = np.load(directory / f"{modality}_s01.npy", mmap_mode="r", allow_pickle=False)
        assert np.array_equal(array[1].view(np.uint64), array[2].view(np.uint64))
        assert np.array_equal(array[1].view(np.uint64), array[-1].view(np.uint64))
    assert "label" not in pair.__slots__ and "trial_id" not in pair.__slots__


def test_quality_findings_do_not_remove_or_replace_trials(prepared):
    directory, manifest = prepared
    assert manifest["counts"]["valid"] == 60 and manifest["exclusions"] == []
    assert manifest["counts"]["by_split"] == dict(train=30, calibration=12, donor=6, test=12)
    quality = {item["channel"]: item for item in manifest["diagnostics"]["source_channels"]}
    assert quality["CP6"]["flat"] and quality["EMG_6"]["flat"]
    assert quality["FC5"]["at_lower_digital_limit"] == quality["FC5"]["at_upper_digital_limit"] == 1
    assert len(manifest["diagnostics"]["traces"]) == 6
    assert not manifest["diagnostics"]["protocol"]["quality_exclusions"]
    assert {trace["label"] for trace in manifest["diagnostics"]["traces"]} == {0, 1, 2}
    assert all("raw" in t and "prepared" in t for t in manifest["diagnostics"]["traces"])
    pair = data.load_trial(directory, data.read_index(directory)[0]["trial_id"])
    assert (pair.eeg[-1] == 0).all() and (pair.emg[-1] == 0).all()


def test_repeat_bitwise_arrays_ids_splits_and_inventory(source, prepared, tmp_path):
    original_dir, original = prepared
    repeat_dir, repeat = _prepare_run(source, tmp_path, "repeat")
    assert data.read_index(original_dir) == data.read_index(repeat_dir)
    for key in ("dataset_id", "recipe_id", "split_id"):
        assert repeat[key] == original[key]
    for modality in ("eeg", "emg"):
        left = np.load(original_dir / f"{modality}_s01.npy", mmap_mode="r", allow_pickle=False)
        right = np.load(repeat_dir / f"{modality}_s01.npy", mmap_mode="r", allow_pickle=False)
        for index in range(len(left)):
            assert np.array_equal(left[index].view(np.uint64), right[index].view(np.uint64))
    for artifact in repeat["artifacts"]:
        assert file_sha256(repeat_dir / artifact["name"]) == artifact["sha256"]
    metadata = json.loads((repeat_dir.parent / "results/run_meta.json").read_text())
    assert metadata["status"] == "completed" and metadata["mode"] == "practice"
    assert metadata["environment"]["packages"]["scipy"]
    assert len(metadata["generated_files"]) == 4
    with pytest.raises(FileExistsError):
        data.prepare_dataset(source, repeat_dir)


def test_class_chronology_floor_counts_and_stable_original_identity(source, prepared):
    _, manifest = prepared
    cfg = deepcopy(source)
    src = deepcopy(manifest["source"])
    rows, _, error = data._trial_rows(src, cfg)
    assert error is None
    for label in (0, 1, 2):
        group = [row for row in rows if row["label"] == label]
        assert [row["split"] for row in group] == ["train"] * 10 + ["calibration"] * 4 + ["donor"] * 2 + ["test"] * 4
    for left, right in zip(rows, rows[1:]):
        assert left["eeg_stop_index0_exclusive"] <= right["eeg_start_index0"]
        assert left["source_event_ordinal"] < right["source_event_ordinal"]
    cfg["data"]["source_root"] = "/different/local/path"
    cfg["run"]["seed"] += 1
    cfg["split"].update(train_percent=51, calibration_percent=19)
    changed, _, _ = data._trial_rows(src, cfg)
    assert [r["trial_id"] for r in rows] == [r["trial_id"] for r in changed]
    # Class and recipe are deliberately absent from the approved identity input.
    cfg["data"]["classes"][0]["label"] = 2
    cfg["data"]["classes"][2]["label"] = 0
    relabelled, _, _ = data._trial_rows(src, cfg)
    assert [r["trial_id"] for r in rows] == [r["trial_id"] for r in relabelled]
    cfg["data"]["recordings"][0]["binary_sha256"] = "0" * 64
    replaced, _, _ = data._trial_rows(src, cfg)
    assert not {r["trial_id"] for r in rows} & {r["trial_id"] for r in replaced}


def test_structural_exclusions_precede_split_and_minimum(source, prepared):
    _, manifest = prepared
    src = deepcopy(manifest["source"])
    first = next(e for e in src["events"] if e["source_event_id"] == "Mk5")
    src["events"].append(dict(type="New Segment", position_1based=first["position_1based"] + 10))
    src["sample_count"] -= 100  # Last candidate is now incomplete.
    rows, exclusions, error = data._trial_rows(src, source)
    assert len(rows) == 58
    assert {reason for e in exclusions for reason in e["reasons"]} == {
        "window_crosses_new_segment", "incomplete_source_window"}
    assert all(row["split"] is None for row in rows)
    assert "fewer than 20" in error


def test_split_flooring_leaves_all_remainder_in_test(source):
    rows = [dict(label=label, source_event_ordinal=3 * i + label, split=None)
            for i in range(23) for label in (0, 1, 2)]
    assert data._assign_splits(rows, source["split"]) is None
    for label in (0, 1, 2):
        group = [r for r in rows if r["label"] == label]
        assert [r["split"] for r in group] == ["train"] * 11 + ["calibration"] * 4 + ["donor"] * 2 + ["test"] * 6
        assert [r["source_event_ordinal"] for r in group] == list(range(label, 69, 3))


def test_duplicate_original_marker_id_is_rejected(source, tmp_path):
    recording = source["data"]["recordings"][0]
    content = (Path(source["data"]["source_root"]) / recording["marker_file"]).read_text()
    path = tmp_path / "duplicate.vmrk"
    path.write_text(content + "Mk5=Stimulus,S 21,2501,1,0\n")
    with pytest.raises(ValueError, match="duplicate key Mk5"):
        data._read_markers(path, "fixture.eeg", 500000)


@pytest.mark.parametrize("delta", [0, 1, LENGTH - 1])
def test_duplicate_or_overlapping_original_intervals_fail(source, prepared, delta):
    src = deepcopy(prepared[1]["source"])
    first = next(e for e in src["events"] if e["source_event_id"] == "Mk5")
    duplicate = dict(first, source_event_id="Mk9999", position_1based=first["position_1based"] + delta)
    location = src["events"].index(first) + 1
    src["events"].insert(location, duplicate)
    # Ensure the original cue retains its expected following rest while making
    # a second, structurally overlapping cue context. Ambiguity still stops it.
    src["events"].insert(location, dict(type="Stimulus", stimulus_code=8,
                                      position_1based=first["position_1based"] + LENGTH))
    with pytest.raises(ValueError, match="duplicate or overlapping"):
        data._trial_rows(src, source)


@pytest.mark.parametrize("before,after,match", [
    ("DataOrientation=MULTIPLEXED", "DataOrientation=VECTORIZED", "layout"),
    ("BinaryFormat=INT_16", "BinaryFormat=IEEE_FLOAT_32", "layout"),
    ("BinaryFormat=INT_16", "BinaryFormat=INT_16\nUseBigEndianOrder=YES", "layout"),
    ("SamplingInterval=400", "SamplingInterval=2000", "Nyquist"),
    ("Ch16=C3,,0.1,µV", "Ch16=C3,,0,µV", "resolution"),
    ("Ch16=C3,,0.1,µV", "Ch16=C3,,nan,µV", "resolution"),
    ("Ch16=C3,,0.1,µV", "Ch16=C3,,0.1,unknown", "source unit"),
    ("Ch16=C3,,0.1,µV", "Ch16=missing,,0.1,µV", "missing required"),
    ("Ch16=C3,,0.1,µV", "Ch16=C5,,0.1,µV", "duplicate source channel"),
])
def test_unsupported_layout_scaling_and_channels_fail(source, tmp_path, before, after, match):
    recording = source["data"]["recordings"][0]
    header = Path(source["data"]["source_root"]) / recording["header_file"]
    changed = tmp_path / "changed.vhdr"
    changed.write_text(header.read_text(encoding="utf-8-sig").replace(before, after), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        data._read_header(changed, recording, source["data"], source["preparation"])


def test_hash_failure_is_failed_run_with_no_completed_dataset(source, tmp_path):
    config = deepcopy(source)
    config["data"]["recordings"][0]["binary_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _prepare_run(config, tmp_path, "hash-failure")
    run, = (tmp_path / "outputs/smoke").glob("hash-failure-*")
    metadata = json.loads((run / "results/run_meta.json").read_text())
    assert metadata["status"] == "failed"
    assert (run / "prepared").is_dir() and not (run / "prepared/dataset.json").exists()


@pytest.mark.parametrize("group,key,value", [
    ("data", "source_root", ""), ("data", "source_root", "relative/path"),
    ("preparation", "window_seconds", 6.0), ("preparation", "padlen", 30),
    ("preparation", "emg_band_hz", [10.0, 500.0]), ("split", "minimum_trials_per_class", 1),
    ("run", "mode", "experimental"), ("data", "recordings", []),
])
def test_component_refuses_unresolved_paths_and_unapproved_semantics(source, group, key, value):
    config = deepcopy(source)
    config[group][key] = value
    with pytest.raises(ValueError):
        data.inspect_sources(config)


def _copy_prepared_metadata(prepared, directory):
    original = prepared[0]
    for name in ("dataset.json", "trials.csv"):
        shutil.copyfile(original / name, directory / name)
    # NPY samples are immutable in these metadata-mutation checks.
    for name in ("eeg_s01.npy", "emg_s01.npy"):
        (directory / name).hardlink_to(original / name)


@pytest.mark.parametrize("field,value", [
    ("trial_id", "0" * 32), ("split", "test"), ("array_index", "1"),
    ("eeg_start_index0", "2501"), ("emg_array_file", "../other.npy"),
    ("onset_seconds", "nan"), ("source_event_id", "Mk999"),
])
def test_reload_rejects_index_identity_interval_split_and_reference_corruption(prepared, tmp_path, field, value):
    _copy_prepared_metadata(prepared, tmp_path)
    with (tmp_path / "trials.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    rows[0][field] = value
    with (tmp_path / "trials.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=data.INDEX_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError):
        data.read_index(tmp_path)


def test_reload_uses_mmap_then_copies_one_trial_and_rejects_nonfinite(prepared, tmp_path, monkeypatch):
    directory, manifest = prepared
    rows = data.read_index(directory)
    actual_load = np.load
    opened = []

    def checked_load(*args, **kwargs):
        assert kwargs == dict(mmap_mode="r", allow_pickle=False)
        result = actual_load(*args, **kwargs)
        assert isinstance(result, np.memmap) and not result.flags.writeable
        opened.append(result)
        return result

    monkeypatch.setattr(np, "load", checked_load)
    pair = data.load_trial(directory, rows[0]["trial_id"])
    assert len(opened) == 2
    assert pair.eeg.nbytes + pair.emg.nbytes == 26 * LENGTH * 8
    assert all(not np.shares_memory(pair.eeg, a) and not np.shares_memory(pair.emg, a) for a in opened)
    with pytest.raises(KeyError, match="unknown trial_id"):
        data.load_trial(directory, "unknown")
    monkeypatch.setattr(np, "load", actual_load)
    _copy_prepared_metadata(prepared, tmp_path)
    (tmp_path / "emg_s01.npy").unlink()  # Do not mutate the linked baseline.
    spec = manifest["arrays"]["emg"]
    bad = np.lib.format.open_memmap(tmp_path / spec["file"], mode="w+", dtype="float64", shape=tuple(spec["shape"]))
    bad[:] = 0
    bad[0, 0, 0] = np.nan
    bad.flush()
    del bad
    with pytest.raises(ValueError, match="finite"):
        data.load_trial(tmp_path, rows[0]["trial_id"])
