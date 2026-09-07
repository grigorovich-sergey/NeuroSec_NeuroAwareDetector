from dataclasses import replace

import numpy as np
import pytest

from neurosec_core.contracts import Prediction


def test_signal_pair_supports_native_rates_and_copies_inputs(signal_pair):
    assert signal_pair.eeg.shape == (2, 24)
    assert signal_pair.emg.shape == (1, 48)
    assert signal_pair.eeg.shape[1] / signal_pair.fs_eeg == 3
    assert signal_pair.emg.shape[1] / signal_pair.fs_emg == 3
    source = signal_pair.eeg.astype(np.float32)
    copied = replace(signal_pair, eeg=source)
    source[:] = 0
    assert np.any(copied.eeg != 0)
    assert copied.eeg.dtype == np.float64
    with pytest.raises(ValueError):
        copied.eeg[0, 0] = 0


@pytest.mark.parametrize("change", [
    {"eeg": np.zeros((2, 0))},
    {"eeg": np.full((2, 24), np.nan)},
    {"emg": np.zeros(48)},
    {"eeg": np.ones((2, 24), dtype=complex)},
    {"fs_eeg": 0},
    {"fs_emg": np.inf},
    {"fs_eeg": True},
    {"eeg_channels": ("same", "same")},
    {"emg_channels": ("one", "two")},
])
def test_invalid_signal_inputs_fail(signal_pair, change):
    with pytest.raises(ValueError):
        replace(signal_pair, **change)


def test_prediction_preserves_probabilities_without_normalizing():
    probabilities = np.array([0.2, 0.3, 0.500000005])
    prediction = Prediction(probabilities, [1, 0, 0], [0.4, 0.1, 0.5])
    assert np.array_equal(prediction.p_eeg, probabilities)
    probabilities[0] = 0
    assert prediction.p_eeg[0] == 0.2
    assert prediction.class_order == (0, 1, 2)


@pytest.mark.parametrize("vector", [
    [0.2, 0.3, 0.4], [0.2, 0.3, 0.5000001],
    [-0.1, 0.5, 0.6], [np.nan, 0.5, 0.5], [0.5, 0.5],
])
def test_invalid_probabilities_fail(vector):
    with pytest.raises(ValueError):
        Prediction([1, 0, 0], vector, [1, 0, 0])


def test_permuted_class_order_is_not_silently_relabelled():
    with pytest.raises(ValueError, match="class_order"):
        Prediction([1, 0, 0], [1, 0, 0], [1, 0, 0], class_order=(2, 1, 0))
