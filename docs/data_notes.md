# C1 data adapter

`neurosec_core.data` implements the approved subject-1/session-1 executed
multigrasp practice pilot. It accepts one original joint BrainVision recording
and returns paired EEG/EMG windows. Real-pilot numerical acceptance remains a
separate local gate; synthetic tests and the real text metadata establish only
the checks described below. CLI wiring belongs to the orchestrator; integrated
execution belongs to H.

## Source and interpretation

The source is [Jeong's GigaDB dataset, DOI 10.5524/100788](https://gigadb.org/dataset/100788),
described in the [dataset paper](https://doi.org/10.1093/gigascience/giaa098).
The already downloaded `RawData.tar.gz` contains the pilot siblings under
`RawData/session1_sub1_multigrasp_realMove.{vhdr,vmrk,eeg}`. Extracted files
stay local; neither recordings nor generated arrays are test fixtures. No
whole-archive checksum was available. The configured extracted-file hashes
are the bounded input identity:

| File suffix | SHA-256 |
| --- | --- |
| `.vhdr` | `ee3782324d1cd9ed2ab7942e4646a61ccf51484ad0d8b9376fb611f3bf5bc5f0` |
| `.vmrk` | `de51f353336796766484748f5ef69854277c21d9f7e9f750c4984e6303302f7c` |
| `.eeg` | `80a92c2dc0d99194004a06eeed0c27181039be82095d4017e8a8152f6970a917` |

C1 independently checked the attached header/marker bytes. The user's local
inspection reported the binary hash and 547,381,600 bytes: 3,854,800 joint
sample frames, 71 signed 16-bit columns, 1,541.92 seconds. The binary has not
been received or numerically inspected by the coding instance. Actual
preparation verifies all three files before reading samples and again after
processing. It never treats the reported binary identity as locally verified.

The supported header layout is UTF-8, `BINARY`, `MULTIPLEXED`, `INT_16`, little
endian, with no data offset or big-endian override. `ChN` defines binary column
order; physical-channel numbers in the free-text comments do not. All 71
channels must have unique names and explicit positive finite resolution in
microvolts. The parser handles the BrainVision `\1` escaped comma and keeps
`[Comment]` as opaque text. It is a source-specific reader, not a general
BrainVision import framework. References: [BrainVision format](https://www.brainproducts.com/support-resources/brainvision-core-data-format-1-0/),
and the source header/marker documentation retained with the dataset.

The attached header gives `SamplingInterval=400` microseconds: both modalities
share the 2,500 Hz clock. EEG and EMG samples are acquired columns of the same
binary; pairing is not inferred by sorting independently exported modalities.
This establishes joint digital sample indexing, not calibrated sub-sample
hardware latency. The original segment clock is retained as text with unknown
timezone; all trial times are recording-relative.

| Output | Ordered names | Source columns, one based | Volts/count |
| --- | --- | --- | --- |
| EEG | FC5 FC3 FC1 FC2 FC4 FC6 C5 C3 C1 Cz C2 C4 C6 CP5 CP3 CP1 CPz CP2 CP4 CP6 | 11 12 13 43 44 45 15 16 17 18 47 48 49 20 21 22 23 51 52 53 | 0.1 × 10⁻⁶ |
| EMG | EMG_1 EMG_2 EMG_3 EMG_4 EMG_5 EMG_6 | 65 66 67 68 69 70 | 10 × 10⁻⁶ |

The implementation selects actual names and applies each channel's documented
resolution after conversion to float64. It retains the recorded reference;
`EMG_ref` (column 71) is not subtracted. No magnitude-based unit inference occurs.

| Label | Grasp | Preparation cue | Execution cue |
| --- | --- | --- | --- |
| 0 | Cup | S1 | S11 |
| 1 | Ball | S2 | S21 |
| 2 | Card | S6 | S61 |

The dataset README and provided `ACC_HandGrasping.m`/conversion scripts establish
the task and trigger interpretation. S8 is rest; S13/S14 are acquisition start/end
provenance. Object names are the canonical labels here; anatomical naming differs
among source scripts. Rest, preparation cues and imagery are not classes.

## Preparation and splitting

All scientific parameters come from the caller's resolved `configs/core_v0.yaml`.
Component guards reject changes outside the approved task, classes, channel
order, recipe and split. They are approval checks, not another default/merge
mechanism. `data.source_root` must be explicitly set to an existing absolute
directory before calling the API. `data_kind="synthetic"` supports the authored
practice fixture; it never supplies real or study evidence. Only practice and
development execution are currently supported.

For an original one-based execution marker position `p`, extract
`[p - 1, p - 1 + round(window_seconds * native_fs))`. For this pilot that is
7,500 samples. There is no additional three-second offset. Record
`onset_reference="execution_cue"`: these are cue-locked windows, not measured
physiological-onset windows.

1. Extract the selected raw trial columns, convert to float64, scale to volts.
2. Design EEG Butterworth `N=4`, 2–30 Hz; EMG `N=5`, 10–450 Hz. Use
   `btype="bandpass", fs=native_fs, output="sos"`.
3. Apply `sosfiltfilt` separately to each extracted trial on `axis=-1`, with
   `padtype="odd", padlen=None`. No neighboring observed samples or filter
   state are shared across windows.
4. Rectify EMG with absolute value **after** filtering. Keep the native rates.

The direct dependency is the orchestrator-approved `scipy>=1.14.1,<2`.
Actual installed versions and SOS coefficients are retained in each manifest.
SciPy implements the numerical design/application; C1 implements source
interpretation and orchestration around those calls. See [butter](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.butter.html)
and [sosfiltfilt](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html).
Design order `N`, bandpass transformation and forward/backward application are
distinct; the manifest does not call the final operation simply an Nth-order filter.

The adapter rejects insufficient Nyquist frequency. At 2,500 Hz, 500 Hz is also
feasible: 450 Hz is an approved project adaptation, not a sampling necessity.
There is no resampling, ICA, interpolation, extra notch, rereferencing, filter
reversal, continuous filtering or padding of incomplete source windows.

Structural exclusions are exactly `incomplete_source_window` and
`window_crosses_new_segment`, retaining original event ID, interval, label and
all applicable reasons. They happen before splitting. Duplicate marker keys,
unordered marker positions, duplicate/overlapping execution windows, unsupported
codes/layout and contradictory preparation-cue/execution-cue/rest context fail
for source review. No ambiguous candidate is silently selected as the survivor.
An exclusive window end at a segment or rest boundary is permitted.

Valid trials remain in original acquisition order. Within each class, allocate
floor(50%) train, floor(20%) calibration, floor(10%) donor, and all remainder
test. Require at least 20 valid trials per class. `inspect_sources` returns a
`split_error` when this minimum fails; `prepare_dataset` raises. Inspection
can therefore preserve exclusions/counts in the caller's failure record.
With the supplied metadata, 50 candidates per class imply 25/10/5/10 per class
and 75/30/15/30 in total, pending actual numerical preparation.

All selected source intervals are disjoint. **Classwise role ranges interleave.**
The pilot's latest prospective donor end is 1,285.5308 s and its earliest test
onset is 1,191.7852 s. C3 must enforce donor end before the particular recipient
onset; a donor split label does not establish earlier capture.

## Diagnostics and acquisition uncertainty

Diagnostic protocol 1 is fixed before observing signal values: the first valid
chronological trial of each class, C3 and EMG_1, gives six selections. Store
their full native-rate raw and prepared traces in volts. Sample `i` is at
`i / sample_rate_hz` seconds relative to the execution cue. Each trace includes
a one-sided full-window Hann periodogram, constant detrending, density scaling,
and FFT length equal to the window length. Frequencies are Hz and density is
V²/Hz. These are review diagnostics, not classifier features. See
[SciPy periodogram](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.periodogram.html).

`diagnostics.source_channels` reports min/max counts, exact flatness and counts
at -32768/32767 for all 71 columns across the whole recording, using bounded
blocks. `diagnostics.trial_findings` reports raw/prepared exact flatness and
raw digital-limit counts for selected channels in individual valid windows.
Digital-limit occupancy is a finding, not proof of a particular clipping cause.
`diagnostics.traces` contains the six raw/prepared vectors and spectra. The
manifest keeps the protocol and selection identities. No plotting dependency
is introduced by C1; H can consume these vectors for local review displays.

These findings never trigger automatic cleaning, channel replacement or trial
exclusion. Nonfinite prepared values fail the run; they are not removed to
obtain sufficient counts. Small statistical amplitudes are not called flat.
The diagnostic selections do not certify physiology across the entire recording.

The source comments report Recorder 1.21.0402; amplifier low cutoff 10 seconds,
high cutoff 1,000 Hz and notch off; software EEG/EOG 0.3 seconds, 70 Hz, 60 Hz
notch; software EMG off/off with 60 Hz notch. The saved-versus-display effect
of software filtering remains unresolved. Preserve these comments without
adding or reversing a filter. The manufacturer distinguishes the
[signal paths](https://pressrelease.brainproducts.com/amplifier-signal-pipeline/).

`Test Signal from actiCAP is used.` is retained as an acquisition warning.
The manufacturer-authored [Recorder manual](https://doczz.net/doc/1508429/brainvision-recorder-manual),
version 1.20.0601, distinguishes test-source preference from test-mode activation.
It is an earlier manual than the recorded software. The preference interpretation
is an inference, not proof of physiological data. No test-mode markers were
observed in the supplied pilot text. Any test-related marker descriptions are
reported for review rather than silently interpreted as physiological validity.

## Public APIs and artifact version 1

The four public functions are `inspect_sources(config)`,
`prepare_dataset(config, out_dir)`, `read_index(prepared_dir)` and
`load_trial(prepared_dir, trial_id)`. There is no `prepare` alias. Core functions
do not read YAML, allocate runs, parse arguments or write run status.

Inspection returns JSON-compatible identities, header/channel mappings, original
events, candidate rows, exclusions/counts, warnings and raw diagnostics without
creating artifacts. Preparation requires a new directory whose parent already
exists inside the caller's allocated practice run. Existing destinations fail.
It writes exactly:

| File | Contents |
| --- | --- |
| `dataset.json` | Schema/adapter/dataset/recipe/split identities; portable config; source files and original markers; native clock and mappings; comments; counts/exclusions; diagnostics; environment and SOS coefficients; artifact hashes |
| `trials.csv` | Exact columns/types in `docs/foundation.md`, in acquisition order |
| `eeg_s01.npy` | Float64 `(n_valid, 20, 7500)` volts at the observed rate |
| `emg_s01.npy` | Float64 `(n_valid, 6, 7500)` volts, with the same trial indices |

The two arrays require 234,000,000 payload bytes for 150 valid trials, plus NPY
headers. The manifest also retains a few MB of local diagnostic vectors.
`dataset.json` is written last. On error the caller marks the run failed or
interrupted and retains partial output. Manifest presence alone does not replace
the caller's completed run status, hash checks and numerical validation.

The source identity input is `{dataset_doi, subject_id, session_id, task,
condition, source_hashes: {header_sha256, marker_sha256, binary_sha256}}`.
Apply the shared `deterministic_identifier(..., length=32)`. Trial identity uses
`{source_recording_id, subject_id, session_id, source_event_id}` with the same
helper and length. Original `MkN` and the ordinal counting **all** markers remain
in the index. Local path, filename, recipe, label, split, seed and run ID do not
enter trial identity; source-byte changes create a new recording identity.

Recipe identity includes adapter version, preparation parameters, class mapping
and ordered channel selections. Split identity includes the split parameters
and ordered `{trial_id, split}` assignments. Dataset identity includes schema
version and the recording/recipe/split IDs. Exact library environment is retained
separately; these IDs are not a promise of bitwise portability between versions.

`read_index` converts the declared integer/float columns and verifies them
against original events, identities, intervals, counts, splits and array header
references. `load_trial` opens separate NPY files with `mmap_mode="r"` and
`allow_pickle=False`, selects one trial, then constructs the existing
`SignalPair`. Only that pair is copied into finite read-only float64 arrays.
It carries channels/rates but no labels or provenance. No full artifact hash
scan occurs on each lookup; run-level verification compares retained hashes.
See [NumPy memory-mapped loading](https://numpy.org/doc/stable/reference/generated/numpy.load.html).

The caller uses the shared `load_config`, `RunLayout`, `RunMetadata`, project
and environment capture, and inventory functions. Retain the full resolved
config, actual code HEAD/working state, invocation, inputs, warnings, exclusions
and terminal status. Include SciPy in environment capture. Failed retries use
new run identities. Practice output remains ignored; nothing here authorizes
a cohort expansion, study run, victim, replay or defense.

## Implementation provenance and verification

The public donor review was pinned to
[`mgpritchard/emg-eeg-CASH@dbd2d5525ab0b5c2137552dfd65f1bccf64fd8f7`](https://github.com/mgpritchard/emg-eeg-CASH/tree/dbd2d5525ab0b5c2137552dfd65f1bccf64fd8f7).
Its EEG/EMG scripts trace to the supplied dataset `ACC_HandGrasping.m` and
BBCI helpers. C1 reviewed those source semantics but copies no MATLAB/BBCI code.
The approved pipeline differs from the donor's continuous causal filtering,
inclusive windows and 500 Hz EMG cutoff. This is an offline project adaptation,
not a reproduction of the donor's reported performance or a streaming method.
Scientific computation uses installed NumPy/SciPy APIs; no upstream reader is
vendored. The fixture generator authors invented signal values and clocks.

Run `python -m pytest -q tests/test_data.py` for C1 checks and
`python -m pytest -q` for the existing shared suite plus C1. Tests cover parsing,
column scaling and cue clock, analytical pass/stop-band and phase behavior,
rectification, trial isolation, structural exclusions/minimum/floored splits,
identity stability, source and index corruption, memory-mapped per-trial access,
read-only finite payloads, repeated bitwise arrays and shared failed-run records.
Test outputs use ignored smoke roots and explicitly synthetic metadata.

Local real acceptance still requires full preparation, index and numerical
reload checks, source and artifact hash verification, quality review, and repeat
preparation with identical IDs/splits and **bitwise-equal array values** in the
same recorded environment. Container-file hash equality is an integrity check,
not the numerical repeat criterion. H consumes these APIs after the C1 delivery
is accepted; the external handoff supplies the bounded local verification
procedure. No real binary was processed by the coding instance.
