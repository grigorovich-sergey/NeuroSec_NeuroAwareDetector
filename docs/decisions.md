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

## Approved C1 pilot prerequisites

C1 checkpoint 1G records the user's approval of the subject-1/session-1
executed-grasp practice pilot, including the orchestrator's two-NPY revision
and clarified acceptance criteria. The retained handoff identities are:

| External handoff | SHA-256 |
| --- | --- |
| `c1_source_review_request.md` | `655a4157c61499b8387f8c38bca2b2c5d06a5b1697a91bf06bfaba6891b1b806` |
| `c1_source_review_response.md` | `cd26b2c0d6aa0a8c63dafc003605f6268a8bbc80b99782ad49d2eb523a883063` |
| `c1_source_review_evidence.json` | `c87c3d4e2908dc2a01ff49863ae02b2a16d7186bdd928ef2b26180c960094a01` |

These handoffs and generated practice output remain outside the repository.
The approved defaults and interface are retained in the shared YAML and
foundation contract. This delivery implements those shared prerequisites,
not C1's adapter.

- Use the original joint BrainVision recording from
  [Jeong's dataset](https://gigadb.org/dataset/100788), with the reported
  2,500 Hz native sample clock and documented channel-specific voltage scales.
  C1 checked the pilot header/marker; binary size/hash came from the user's
  local inspector. Binary samples have not been examined by the instances.
- Use Cup/Ball/Card = 0/1/2 and the execution cues S11/S21/S61. Convert
  one-based marker positions and take a half-open three-second window without
  an additional offset. Physiological movement onset was not measured.
- Keep the approved trial-local SOS filtering and classwise chronological
  split. At 2,500 Hz, the EMG cutoff of 450 Hz is a deliberate adaptation,
  not a Nyquist requirement. No continuous/streaming equivalence is claimed.
- Store separate EEG and EMG NPY arrays for memory-mapped per-trial access,
  with a typed CSV index and JSON manifest. `SignalPair` is unchanged.
- Add `scipy>=1.14.1,<2`; record actual versions for each run.
  [SciPy 1.14.1](https://docs.scipy.org/doc/scipy/release/1.14.1-notes.html)
  added Python 3.13 support and wheels. The existing loader already supports
  the approved list-of-mapping defaults and null-only padding setting.
- Preserve the acquisition-filter uncertainty, actiCAP test-source note and
  missing whole-archive checksum. Source identities, numerical quality and
  repeat preparation must still be checked locally before pilot acceptance.
- No ownership transfers, additional pilot subjects or study execution are
  authorized by this checkpoint. C1 follows acceptance of these prerequisites;
  H's next delivery follows the accepted C1 implementation.

## Still open before the affected component dispatch

The setup documents
`research_software_orchestrator_shared_context_and_rules.md` and
`neurosec_core_v0_orchestrator_plan.md` remain working plans. They are not
silently copied into this repository as frozen scientific specifications.

C1's metadata review and the pilot recipe/interface decision are complete.
The source adapter, numerical preparation, local signal-quality review,
reload/repeat checks and actual accepted trial counts remain pending. The
generic configuration check establishes neither source availability nor
scientific validity. Runtime inspection/preparation CLI wiring follows the
implemented C1 functions; no placeholder scientific command is introduced.

Confirm remaining victim, replay, rejection/calibration and clean-decoding
gate decisions before their respective dispatches and study freeze. This
pilot approval does not settle the attack/defense reassessment or authorize a
final cohort. Later interfaces must use actual producer/consumer requirements.

There is no end-to-end harness execution or scientific validation to report
yet. The next implementation delivery is C1; H's first return follows accepted
C1 APIs. A successful bootstrap check does not pass a scientific gate.
