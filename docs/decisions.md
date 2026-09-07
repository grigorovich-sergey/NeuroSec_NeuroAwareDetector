# Bootstrap decisions and source record

## Scope and repository layout

The user approved the orchestrator preparing one bounded foundation patch,
which the user will apply, commit, and push.

Use one active package, `src/neurosec_core/`, in the existing repository root.
This supersedes the earlier draft's nested `core_v0/` layout. Keep the Git
history; there is no second active copy of the old architecture or compatibility
layer. The repository exists to generate article data and meet reproducibility
requirements. Additional expansion interfaces need a concrete use case.

## Inspected previous iteration

Base: [`b98b4e2a1feb0cc99c86ced921fb6173a6fc4c64`](https://github.com/grigorovich-sergey/NeuroSec_NeuroAwareDetector/tree/b98b4e2a1feb0cc99c86ced921fb6173a6fc4c64).
The inspected tree contained 21 tracked files and only the WP0 foundation.
It contained no implemented dataset pipeline, victim, replay, or defenses.

The previous configuration merger, file hashing, provenance capture, unique
run allocation, and staged-finalization ideas are adapted here. Its broad
trial/attack/policy records and synthetic placeholder smoke runner are
replaced by the present small contracts. The old distribution/import names,
configuration files, and smoke command are retired.

Two reproduced defects determine regression coverage:

1. The old merger accepted integer CLI channel names after a partial override
   emptied a string list. Each layer now validates against original defaults.
2. The old finalizer accepted completed metadata naming an absent artifact.
   Finalization now checks the complete file inventory and runner-declared
   required outputs before moving the run.

Old tests passing did not disprove either defect. New tests address these
failure modes alongside numerical validation and practice/study separation.

## Decisions carried into this patch

- Shared numerical input records omit labels and attack metadata.
- One complete YAML plus validated partial override plus limited CLI overrides.
- Separate entirely ignored smoke, pilot, and experimental staging output.
- One recurring H instance composes the implemented pipeline after each
  component merge; its code/tests are tracked and its generated outputs stay local.
- Sequential component deliveries, with owner corrections for blocking
  integration failures and user-created commits/pushes.
- The orchestrator also owns the small `config.py`, `metadata.py`, `runs.py`,
  foundation tests, and foundation documentation introduced in this bootstrap.
  These are shared utilities, not another coding instance.

## Still open before the affected component dispatch

The setup documents
`research_software_orchestrator_shared_context_and_rules.md` and
`neurosec_core_v0_orchestrator_plan.md` remain working plans. They are not
silently copied into this repository as frozen scientific specifications.

C1 needs an actual EEG/EMG source pair or a user-run inspection to establish
file structure, units, execution-event semantics, channel names, grasp-label
mapping, and modality alignment. Those facts are deliberately absent from the
bootstrap YAML. No source-specific parser or guessed mapping is implemented.

Confirm the numerical preparation/model recipe, split/cohort design, replay
eligibility, rejection/calibration rules, and clean-decoding gate before their
respective dispatches and study freeze. Component APIs and artifact formats
must be agreed using the actual producer/consumer requirements.

There is no end-to-end harness execution or scientific validation to report
yet. The next implementation delivery is C1; H's first return follows accepted
C1 APIs. A successful bootstrap check does not pass a scientific gate.
