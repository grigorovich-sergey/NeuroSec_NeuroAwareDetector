# Shared foundation contract

This document distinguishes the implemented shared APIs from the approved C1
interface awaiting implementation. Approval covers one subject-1 practice
pilot; numerical preparation and real-pilot acceptance remain pending.

## Numerical records

`SignalPair(eeg, emg, fs_eeg, fs_emg, eeg_channels, emg_channels)` carries only
numerical inputs and their interpretation. Arrays are copied to finite
float64, are nonempty with shape `(channels, samples)`, and are marked
read-only. Each modality has its own positive sample rate and ordered,
unique, nonempty channel names. Different modality sample counts are allowed.

C1 must prove acquisition pairing and verify source units, the common
duration, channel mapping, and event timing. The record cannot establish
those facts from array shapes. IDs, labels, event provenance, split roles,
and attack information stay outside this payload.

`Prediction(p_eeg, p_emg, p_fused, class_order=(0, 1, 2))` accepts three finite
length-three probability vectors in that fixed order. Values must be in
`[0, 1]` and sums within `atol=1e-8, rtol=0` of one. It never normalizes or
substitutes values. The approved source grasp names for indices 0, 1, 2 are
Cup, Ball, Card. Fusion and label selection belong to C2.

The shared `tests/fixtures/contract_fixture.py` generates a small deterministic
numerical fixture. Its invented channel names, low sampling rates, and random
values make it unsuitable for physiological checks or the proposed filters.
It has no scientific evidentiary role. C1/H must use actual approved inputs
when checking data preparation.

The approved C1 layout uses separate read-only-loadable NPY arrays, with
CSV/JSON provenance. There is no JSON-inline signal serializer in this foundation.

## Approved C1 interface (not yet implemented)

C1 owns the implementation of these functions in `neurosec_core.data`:

```python
inspect_sources(config: Mapping[str, Any]) -> dict[str, Any]
prepare_dataset(config: Mapping[str, Any], out_dir: str | Path) -> dict[str, Any]
read_index(prepared_dir: str | Path) -> list[dict[str, Any]]
load_trial(prepared_dir: str | Path, trial_id: str) -> SignalPair
```

`inspect_sources` returns JSON-compatible source identities, mappings,
event/window checks and diagnostic findings without creating prepared arrays.
`prepare_dataset` receives the same fully resolved configuration and a new
prepared directory inside a caller-allocated practice run. It rechecks source
identities, writes the artifacts below and returns the `dataset.json` manifest
as a dictionary. Failures leave partial output for the shared failure record.
Use the single preparation name `prepare_dataset`; there is no `prepare` alias.

| Artifact | Contract |
| --- | --- |
| `dataset.json` | Versioned source/recipe/split identities, source hashes, class/channel order, rates/units, acquisition interpretation and comments, exclusions/counts, preparation versions, `data_kind`, `cohort_role`, and references to both arrays |
| `trials.csv` | Typed rows in acquisition order, original marker identity, per-modality half-open source intervals, labels/splits, separate EEG/EMG array filenames and a common array index |
| `eeg_s01.npy` | Finite float64 volts, `(n_valid, 20, 7500)` |
| `emg_s01.npy` | Finite float64 volts, `(n_valid, 6, 7500)`, in the same trial order |

The approved index columns, in order, are:

```text
trial_id,subject_id,session_id,source_recording_id,source_event_id,source_event_ordinal,source_marker_description,source_marker_position_1based,onset_reference,onset_seconds,end_seconds_exclusive,eeg_source_file,emg_source_file,eeg_start_index0,eeg_stop_index0_exclusive,emg_start_index0,emg_stop_index0_exclusive,label,split,eeg_array_file,emg_array_file,array_index
```

`read_index` converts declared numeric columns and checks schema, IDs,
uniqueness and array references. `load_trial` resolves one stable ID, checks
schema and consistency, and opens the NPY arrays with `mmap_mode="r"` and
`allow_pickle=False`. It selects one trial before constructing `SignalPair`,
whose existing contract copies only that trial into read-only arrays. Labels,
IDs and provenance stay in the index. Full artifact hash checks belong to
run-level validation rather than each trial lookup. No DataFrame or new shared
numerical record is needed.

Use `deterministic_identifier(..., length=32)` for the recording identity over
`dataset_doi`, subject/session, task/condition and the three source hashes.
Derive each trial identity from that recording ID, subject/session and the
original `source_event_id` (`MkN`). Keep labels, split, recipe, local path and
run identity out of trial identity. Store recipe/split identities separately.

The pilot's reported native rate is 2,500 Hz for both modalities. Windows start
at the execution cue (`S11`, `S21`, `S61`), with the one-based marker position
converted to a zero-based index and no additional offset. The resulting
7,500-sample windows are cue-locked, not measured physiological-onset windows.
Retain the source settings and their uncertainty. The 450 Hz EMG upper cutoff
is a project adaptation; 500 Hz is also below this source's Nyquist frequency.

Classwise chronological split ranges can interleave. C1 preserves exact
source intervals; C3 must check each donor's exclusive end against each
recipient's start. A donor split label alone does not prove earlier capture.

Source identity/layout/channel/scaling failures stop preparation. Structural
trial exclusions precede splitting and retain reasons. Report flat channels,
values at digital limits, and a small fixed set of raw/prepared traces and
spectra for review; do not add silent cleaning or outcome-driven exclusions.
Real-pilot acceptance requires numerical/reload checks and identical IDs,
splits and bitwise-equal arrays on repeat preparation in the same recorded
environment. Metadata feasibility alone does not pass that gate.

## Configuration

Use `load_config(repo_root, partial_path=None, *, mode=None, seed=None)` from
`neurosec_core.config` once at an execution entry point. Pass the resolved
dictionary into component functions. H must use this loader too.

`resolve_config(default_path, partial_path=None, cli_overrides=None)` supplies
the underlying recursive merge. Both override layers are checked against the
unchanged complete defaults. Mappings merge and lists/scalars replace.
Unknown keys, non-string keys, incompatible types, and nonfinite numeric
values fail. Nonempty homogeneous default lists specify their element type,
which survives an empty partial override. A null default accepts only null.
An empty default list has no inferred element type and is rejected.

`load_config` additionally validates mode, nonnegative integer seed, and output
boundaries. Path overrides may select a subdirectory inside their respective
`outputs/smoke`, `outputs/pilot`, `outputs/study_staging`, or `outputs/study`
tree. This keeps practice and staging writes under the committed ignore rules.

The default YAML also contains the approved C1 `data`, `preparation`, and
`split` groups. `data.source_root=""` means explicitly unset, not the current
directory. A future preparation entry point must require the local directory,
resolve it to an absolute path before retaining the resolved configuration,
and pass that same configuration to C1. Component validation must reject the
unset path, invalid cross-field combinations and unapproved recipe/task/class
semantics. The generic loader does not perform source or scientific validation.

List overrides replace the whole list. Each recording/class mapping must
retain the declared keys and compatible types. `preparation.padlen` is fixed
to null in the approved recipe and existing loader. These defaults do not add
a parameter search or a second configuration mechanism.

`check-config` remains the only implemented CLI command. The orchestrator
coordinates runtime command wiring after C1's functions exist. H imports the
accepted C1 APIs and uses the shared loader and lifecycle below; C1 adds no CLI
or competing run manager.

## Run lifecycle and provenance

Use `RunLayout.from_config(repo_root, config["paths"])` from
`neurosec_core.runs`. Its API is:

- `create_practice("smoke" | "pilot", run_id=None)`: create a new local run.
- `create_experimental_staging(run_id=None)`: create a new staging run; reject
  reuse of a completed identity.
- `write_metadata(run_path, metadata)`: write `results/run_meta.json` only in a
  direct practice or staging run. Running snapshots can be updated; terminal
  snapshots cannot be overwritten.
- `finalize_experimental(staging_path, required_files=[...])`: validate and
  move the whole staging directory into the completed study root.

`RunMetadata.start` requires the run ID, resolved configuration, exact
invocation, captured Git/environment state, `data_kind` (`real` or
`synthetic`), and `cohort_role` (`development` or `report`). Mode and seed come
from the resolved configuration. Inputs cannot silently change the saved
configuration snapshot through a retained dictionary reference.

Capture actual state with `capture_project_state(repo_root)` and
`capture_environment_identity()`. Git capture records commit, branch or
detached state, and visible working-tree changes; it errors outside Git.
Package versions are actual installed versions, with unavailable packages
recorded as null. Dirty state is recorded, not reconstructed: retain the
exact committed code for report reproduction.

For preparation and its H runs, pass
`("neurosec-core", "numpy", "PyYAML", "scipy")` to
`capture_environment_identity` so the actual filtering library version is
recorded. The declared SciPy range is not a lockfile. The caller must keep
run metadata, resolved configuration and prepared-manifest input kind/cohort
consistent; this prerequisite patch performs no real-data preparation.

Metadata includes schema version, timestamps, status, input identities,
component identifiers, warnings, exclusions, deviations, failure details,
and generated file names/sizes/SHA-256 hashes. Component owners populate input
and component provenance as their actual schemas become available.

Write a running snapshot before computation. On success, call
`mark_completed()` then write the terminal snapshot. On failure/interruption,
call `mark_failed(message)` / `mark_interrupted(message)`, write the snapshot,
and retain partial outputs locally. A retry uses a new run ID.

Finalization requires completed metadata, matching ID/mode/seed, recorded Git
and Python identities, and `data_kind=real, cohort_role=report`. The runner
must supply a nonempty list of its required artifacts relative to the run
root. Every required file must exist in the inventory, and the full inventory
must match current files byte-for-byte, including detection of unexpected
files. Symlink artifacts and path traversal are rejected. Metadata excludes
its own checksum.

These checks establish artifact integrity, not scientific correctness or the
truth of a manually supplied `data_kind`. The eventual runner and integration
gates must validate dataset/model/recipe identities and scientific contents
before marking completion. No experimental runner exists in this bootstrap.

This is a single-writer workflow. Finalization uses a directory rename on the
same filesystem. There is no concurrent scheduler or cross-filesystem copy
fallback. Completed paths are immutable through the shared write API; ordinary
filesystem tools can still modify them and must not be used to rewrite results.
