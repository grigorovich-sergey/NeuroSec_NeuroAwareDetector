"""Numerical boundaries only: labels and provenance live in separate artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

import numpy as np
from numpy.typing import NDArray

CLASS_ORDER = (0, 1, 2)


def _array(value: object, name: str, ndim: int) -> NDArray[np.float64]:
    raw = np.asarray(value)
    if raw.dtype.kind not in "iuf":
        raise ValueError(f"{name} must contain real numeric values")
    array = np.array(raw, dtype=np.float64, copy=True)
    if array.ndim != ndim or any(size == 0 for size in array.shape):
        raise ValueError(f"{name} must be a nonempty {ndim}-dimensional array")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    array.setflags(write=False)
    return array


@dataclass(frozen=True, slots=True, eq=False)
class SignalPair:
    """One prepared EEG/EMG pair, with independent native sample rates.

    C1 must establish acquisition alignment, units, and the approved duration.
    Numerical validation alone cannot establish those source-dependent facts.
    """

    eeg: NDArray[np.float64]
    emg: NDArray[np.float64]
    fs_eeg: float
    fs_emg: float
    eeg_channels: tuple[str, ...]
    emg_channels: tuple[str, ...]

    def __post_init__(self) -> None:
        for modality in ("eeg", "emg"):
            array = _array(getattr(self, modality), modality, ndim=2)
            rate = getattr(self, f"fs_{modality}")
            if (
                isinstance(rate, (bool, np.bool_))
                or not isinstance(rate, Real)
                or not np.isfinite(rate)
                or rate <= 0
            ):
                raise ValueError(f"fs_{modality} must be positive and finite")
            names = getattr(self, f"{modality}_channels")
            if isinstance(names, str):
                raise ValueError(f"{modality}_channels must be an ordered sequence")
            names = tuple(names)
            if (
                len(names) != array.shape[0]
                or any(not isinstance(name, str) or not name.strip() for name in names)
                or len(set(names)) != len(names)
            ):
                raise ValueError(f"{modality}_channels must uniquely name every channel")
            object.__setattr__(self, modality, array)
            object.__setattr__(self, f"fs_{modality}", float(rate))
            object.__setattr__(self, f"{modality}_channels", names)


@dataclass(frozen=True, slots=True, eq=False)
class Prediction:
    """Three probability vectors in the documented class order.

    No normalization, fusion, label selection, or fallback happens here.
    Source grasp names for indices 0, 1, 2 still require C1's verified mapping.
    """

    p_eeg: NDArray[np.float64]
    p_emg: NDArray[np.float64]
    p_fused: NDArray[np.float64]
    class_order: tuple[int, ...] = CLASS_ORDER

    def __post_init__(self) -> None:
        order = tuple(self.class_order)
        if (
            order != CLASS_ORDER
            or any(isinstance(label, (bool, np.bool_)) for label in order)
            or any(not isinstance(label, (int, np.integer)) for label in order)
        ):
            raise ValueError("class_order must be (0, 1, 2)")
        object.__setattr__(self, "class_order", CLASS_ORDER)
        for name in ("p_eeg", "p_emg", "p_fused"):
            probabilities = _array(getattr(self, name), name, ndim=1)
            if (
                probabilities.shape != (3,)
                or (probabilities < 0).any()
                or (probabilities > 1).any()
                or not np.isclose(probabilities.sum(), 1.0, atol=1e-8, rtol=0)
            ):
                raise ValueError(f"{name} must be three probabilities summing to one")
            object.__setattr__(self, name, probabilities)
