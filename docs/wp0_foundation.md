# WP0 foundation

WP0 owns the shared `neurosec.foundation` package, foundation configurations,
run-location conventions, official dependency definition, foundation smoke script,
focused tests, and the related ignore rules. It provides infrastructure and shared
records; it does not implement a dataset adapter, victim, attack, detector, rolling
policy, integrator, or reportable experiment.

## Public entry points and owned files

- `neurosec.foundation.resolve_config`: strict default/partial/CLI resolution.
- `neurosec.foundation.records`: EEG/EMG trial, attack-manifest, and
  detector/policy-output records plus JSON serialization.
- `neurosec.foundation.RunLayout`: practice and experimental lifecycle paths.
- `neurosec.foundation.RunMetadata`: machine-readable run metadata.
- `scripts/smoke_foundation.py`: deterministic synthetic practice workflow.
- `configs/foundation.yaml`: complete foundation configuration.
- `configs/foundation_smoke_override.yaml`: example recursive partial override.
- `pyproject.toml`: Python requirement and centralized direct dependencies.

The complete WP0 ownership boundary is `src/neurosec/__init__.py`,
`src/neurosec/foundation/`, the two configuration files above,
`scripts/smoke_foundation.py`, this document, `tests/conftest.py`,
`tests/test_config.py`, `tests/test_records.py`, `tests/test_runs.py`,
`pyproject.toml`, `.gitignore`, and the `.gitkeep` path markers under
`runs/practice/` and `runs/experimental/`. Pytest temporary files are explicitly
routed into `runs/practice/pytest/`.

## Configuration

`resolve_config` loads the complete YAML default, recursively applies an optional
partial YAML, and then applies a deliberately small nested mapping of CLI values.
Unknown keys report their dotted path. Nested mappings merge; scalars and lists
replace defaults. Replacements with incompatible types fail. Core functions receive
the resolved mapping and do not inspect YAML or CLI state.

The smoke CLI maps `--seed`, `--mode`, and `--run-id` to `run.seed`, `run.mode`, and
`run.id`. Its `--config` argument names a partial YAML. The resolved configuration,
including those CLI values, is embedded in `run_metadata.json` and also written as
`resolved_config.yaml`.

## Shared records and serialization

`TrialRecord` contains subject, session, trial, source-recording, and task identities;
sampling rate, timestamps, and event markers; EEG samples, channel names, and optional
coordinates; EMG samples, channel names, and optional muscle identities; preprocessing
state, provenance, and a dataset/file reference. The protected arrays are two-dimensional
channel-by-sample NumPy arrays aligned to one timestamp vector. Construction copies the
arrays and makes them read-only. EOG is deliberately not a field, modality, or fallback
class; deserialization rejects unknown fields such as `eog_samples`.

`AttackManifest` permits exactly one attacked modality (`EEG` or `EMG`) and records
channels, family, parameters, severity, interval, seed, and optional replay,
channel-identity-remapping, timing, metadata, and target facts. It records facts only;
the smoke manifest is explicitly representative and does not execute an attack.

`DetectorPolicyOutput` records per-window raw and clean-standardized scores,
modality and unresolved evidence, optional localization and rolling state, attribution,
action, alarm/decision times, lookback, buffering, and latency. Unavailable values are
serialized as JSON `null`, never numeric zero. The action labels are normal fusion,
EEG-only fallback, EMG-only fallback, abstention, and hold. Attribution includes an
explicit unresolved state.

Version-1 record serialization is UTF-8 JSON, not pickle. The WP0 JSON representation
inlines arrays and is intended for small records and smoke checks. A later data owner
should request a WP0 extension before standardizing any external large-array reference.

## Run locations and lifecycle

- Practice output: `runs/practice/<run-id>/` (gitignored).
- Incomplete experimental staging: `runs/staging/<run-id>/` (gitignored).
- Successfully completed experimental output: `runs/experimental/<run-id>/` (tracked).

Run identifiers are validated and paths cannot escape the repository root. Creation
refuses an existing identity. The three configured roots must be distinct and cannot
contain one another. `RunLayout.finalize_experimental` accepts only an explicit
`RunStatus.COMPLETED`, verifies that `run_metadata.json` has the same run identity,
`experimental` mode, and completed status, moves only a direct staging child, and
refuses to overwrite an existing completed run. Practice, failed, or interrupted runs
therefore remain outside the completed evidence tree.

## Run metadata

The metadata writer supports run identity, mode, status and timestamps; fully resolved
configuration; invocation; Git commit and working-tree state; Python, platform, and
selected package versions; seed; source datasets; split/input, attack, detector, victim,
and policy references; warnings, exclusions, deviations, failures; component extension
metadata; and generated-file names, sizes, and SHA-256 hashes.

Project state, environment identity, timestamps, and generated-file inventory can be
captured automatically. Dataset, split, component, warning, exclusion, deviation, and
failure facts must be supplied by the component that knows them. File inventory names
are relative to the run, not machine-specific absolute paths. The metadata file excludes
itself from its inventory to avoid a self-referential digest.

Metadata construction accepts only `practice` or `experimental` mode. When the resolved
configuration contains `run.mode`, that value must match the metadata mode.

## Environment and verification

The supported interpreter is Python 3.11 or newer. The direct runtime dependencies are
NumPy and PyYAML; pytest is the test extra. Set up and verify an isolated environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -c "import neurosec, numpy, yaml; print(neurosec.__version__)"
```

Run the deterministic smoke path and focused checks:

```bash
.venv/bin/python scripts/smoke_foundation.py --seed 2027
.venv/bin/python -m pytest
```

The smoke path resolves the default and example partial override, constructs and
validates synthetic EEG/EMG data, constructs representative manifest/output records,
writes a completed practice run with metadata, and prints its gitignored path. It does
not download data or perform an attack or detector calculation.

## Provenance, deviations, and limitations

Configuration parsing reuses PyYAML `safe_load`; numerical array representation and
validation reuse NumPy; packaging uses Python's standard `venv`/`pip` workflow and
setuptools. Typed records, strict recursive merging, lifecycle checks, and provenance
orchestration are project infrastructure, not scientific algorithms. No earlier
NeuroSec machinery existed at base commit
`ba3a89cd97b659b498c1d3ade689e9ec7d0d5e2c`, so WP0 introduces these minimal contracts.

The current JSON array representation is not intended for full source recordings.
Metadata captures the working-tree change list but does not archive the diff itself.
Environment metadata records selected installed package versions rather than a complete
transitive lock file; accepted direct dependency ranges are centralized in
`pyproject.toml`. The repository does not yet contain dataset acquisition machinery or
an experimental evidence-producing integrator.

A configuration field whose complete default is YAML `null` currently cannot be
overridden with a concrete value. Component configurations should use concrete sentinel
defaults until a downstream requirement justifies a reviewed extension of the strict
type rules.
