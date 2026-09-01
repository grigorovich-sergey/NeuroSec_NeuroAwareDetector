from __future__ import annotations

import numpy as np
import pytest

from neurosec.foundation.records import (
    DatasetReference,
    EventMarker,
    SourceFileReference,
    TrialRecord,
)


@pytest.fixture
def trial_record() -> TrialRecord:
    return TrialRecord(
        subject_id="subject-01",
        session_id="session-01",
        trial_id="trial-01",
        source_recording_id="recording-01",
        task_label="grasp",
        sampling_rate_hz=100.0,
        timestamps_s=np.arange(5) / 100.0,
        events=(EventMarker("start", 0.0, 0),),
        eeg_samples=np.arange(10, dtype=float).reshape(2, 5),
        eeg_channel_names=("C3", "C4"),
        eeg_coordinates={"C3": (-1.0, 0.0, 1.0), "C4": (1.0, 0.0, 1.0)},
        emg_samples=np.arange(10, 20, dtype=float).reshape(2, 5),
        emg_channel_names=("flexor", "extensor"),
        emg_muscle_identities=("flexor", "extensor"),
        preprocessing_state={"track": "raw"},
        provenance={"adapter": "test"},
        source_dataset=DatasetReference(
            identifier="example",
            version="1",
            representation="test",
            files=(SourceFileReference("source.bin", "a" * 64, 160),),
        ),
    )
