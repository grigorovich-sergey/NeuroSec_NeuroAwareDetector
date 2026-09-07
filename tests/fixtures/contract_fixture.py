"""Small in-memory numerical fixture; no dataset realism or efficacy claim."""

import numpy as np

from neurosec_core.contracts import SignalPair


def synthetic_signal_pair(seed: int = 2027) -> SignalPair:
    rng = np.random.default_rng(seed)
    # Same three-second duration with intentionally different modality rates.
    return SignalPair(
        eeg=rng.normal(size=(2, 24)),
        emg=rng.normal(size=(1, 48)),
        fs_eeg=8.0,
        fs_emg=16.0,
        eeg_channels=("synthetic_eeg_0", "synthetic_eeg_1"),
        emg_channels=("synthetic_emg_0",),
    )
