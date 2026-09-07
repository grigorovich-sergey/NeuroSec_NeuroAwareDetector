# NeuroSec Core v0

An offline EEG-EMG study of genuine-window replay and prediction-based
rejection, built to produce an article's data and a reproducible artifact.

**Current state: shared bootstrap only.** Data preparation, the victim model,
replay, defenses, evaluation, and the developmental pipeline harness are not
implemented. No real-data validation or scientific result is claimed.

## Install and check the bootstrap

From the repository root, use Python 3.11 or later and a fresh environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -q
python -m neurosec_core.cli check-config
```

On Windows, activate with `.venv\Scripts\activate`. The installable package is
`neurosec_core`; the distribution is `neurosec-core`.

The sole implemented CLI command validates and prints configuration. It does
not create a run. An optional partial YAML overrides the complete bootstrap
defaults, then explicit CLI values take precedence:

```bash
python -m neurosec_core.cli check-config --config /path/to/local_override.yaml --seed 99
```

`configs/core_v0.yaml` contains only implemented execution settings. Unknown
keys and incompatible types fail. Scientific settings and source mappings
will be added after their decisions are verified and approved.

## Local output and study output

| Directory | Purpose | Git behavior |
| --- | --- | --- |
| `data/` | Local source data | Ignored |
| `outputs/smoke/` | Synthetic functionality checks, harness smoke runs, pytest temporary files | Entire tree ignored |
| `outputs/pilot/` | Real-data development and harness pilot runs | Entire tree ignored |
| `outputs/study_staging/` | Incomplete experimental runs | Entire tree ignored |
| `outputs/study/` | Verified, completed study runs | Can be tracked after review |

Smoke and pilot output stays local. Do not force-add it or use it as article
evidence. The harness implementation and its tests will be tracked. Legacy
local `runs/` output is also ignored.

Every execution creates a unique run directory. Experimental output starts
in staging; explicit completion, matching metadata, required files, and a
verified SHA-256 inventory precede finalization. The shared write API rejects
completed destinations. See [the foundation contract](docs/foundation.md).

## Implementation ownership

| Owner | Responsibility |
| --- | --- |
| Orchestrator | Shared contracts, config, metadata/run lifecycle, CLI, dependencies, integration review, repository state |
| C1 | Source audit, pairing, preparation, splits, provenance |
| C2 | Features, victim training, saved models, clean inference |
| C3 | Donor eligibility, replay manifests, substitution, attacked inference |
| C4 | Clean calibration, rejection, evaluation, tables and figures |
| H | One recurring harness that runs the whole implemented pipeline after each component merge |

Delivery order is C1 → H → C2 → H → C3 → H → C4 → H, followed by the approved
study and report. H stops at the implemented frontier and records missing
stages; it does not simulate them. A blocking integration failure returns to
the owning instance before the next component starts.

One coding patch is active at a time. The user applies, commits, and pushes;
the next delivery uses the actual resulting base commit. Scope decisions and
the bootstrap's reuse provenance are in [decisions](docs/decisions.md).
