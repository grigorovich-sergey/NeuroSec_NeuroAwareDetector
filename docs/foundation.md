# Shared foundation contract

These are the implemented bootstrap APIs. They do not freeze the remaining
scientific recipe or the source-file schema.

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
substitutes values. Source grasp names for indices 0, 1, 2 await C1's audit.
Fusion and label selection belong to C2.

The shared `tests/fixtures/contract_fixture.py` generates a small deterministic
numerical fixture. Its invented channel names, low sampling rates, and random
values make it unsuitable for physiological checks or the proposed filters.
It has no scientific evidentiary role. C1/H must use actual approved inputs
when checking data preparation.

Signal arrays will be stored in NPZ by C1, with separate CSV/JSON provenance.
There is no JSON-inline signal serializer in this foundation.

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
