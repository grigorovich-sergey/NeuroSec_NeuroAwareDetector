"""Invented 71-column INT_16 source at 2500 Hz; never physiological evidence.

Binary files are generated only inside ignored practice/test directories.
Names match the observed format; values, clocks and event spacing are invented.
"""

from copy import deepcopy
from pathlib import Path

import numpy as np

from neurosec_core.metadata import file_sha256

CHANNELS = (
    "Fp1 AF7 AF3 AFz F7 F5 F3 F1 Fz FT7 FC5 FC3 FC1 T7 C5 C3 C1 Cz TP7 "
    "CP5 CP3 CP1 CPz P7 P5 P3 P1 Pz PO7 PO3 POz hEOG_L hEOG_R vEOG_U vEOG_D "
    "Fp2 AF4 AF8 F2 F4 F6 F8 FC2 FC4 FC6 FT8 C2 C4 C6 T8 CP2 CP4 CP6 TP8 "
    "P2 P4 P6 P8 PO4 PO8 O1 Oz O2 Iz EMG_1 EMG_2 EMG_3 EMG_4 EMG_5 EMG_6 EMG_ref"
).split()
RATE = 2500
LENGTH = 7500


def make_source(directory: Path, defaults: dict, *, per_class: int = 20) -> dict:
    """Return resolved synthetic parameters and create a deterministic source."""
    directory.mkdir()
    config = deepcopy(defaults)
    config["data"].update(source_root=str(directory.resolve()), data_kind="synthetic",
                          dataset_doi="synthetic:c1-format-fixture-v1")
    recording = config["data"]["recordings"][0]
    recording.update(header_file="fixture.vhdr", marker_file="fixture.vmrk", binary_file="fixture.eeg")
    starts = RATE + np.arange(per_class * 3) * (LENGTH + 5)
    samples = int(starts[-1]) + LENGTH + 4
    raw = np.memmap(directory / recording["binary_file"], dtype="<i2", mode="w+", shape=(samples, 71))
    raw[:] = 0
    t = np.arange(LENGTH) / RATE
    template = np.empty((LENGTH, 71), dtype="<i2")
    for i in range(64):
        template[:, i] = np.rint((800 * np.sin(2 * np.pi * 10 * t)
                                 + 700 * np.sin(2 * np.pi * 200 * t)) * (1 + i / 71)).astype("<i2")
    for i in range(64, 70):
        template[:, i] = np.rint((300 * np.sin(2 * np.pi * 80 * t)
                                 + 200 * np.sin(2 * np.pi * 600 * t)) * (i - 63)).astype("<i2")
    template[:, CHANNELS.index("CP6")] = 0
    template[:, CHANNELS.index("EMG_6")] = 0
    template[:, CHANNELS.index("EMG_ref")] = 30000
    for start in starts:
        raw[int(start):int(start) + LENGTH] = template
    raw[int(starts[0]), CHANNELS.index("C3")] = 12345
    raw[int(starts[0]), CHANNELS.index("EMG_1")] = -2345
    raw[int(starts[0]):int(starts[0]) + 2, CHANNELS.index("FC5")] = [-32768, 32767]
    raw.flush()
    del raw
    channels = "\n".join(f"Ch{i + 1}={name},,{10 if i >= 64 else 0.1},µV" for i, name in enumerate(CHANNELS))
    header = (
        "Brain Vision Data Exchange Header File Version 1.0\n"
        "[Common Infos]\nCodepage=UTF-8\nDataFile=fixture.eeg\nMarkerFile=fixture.vmrk\n"
        "DataFormat=BINARY\nDataOrientation=MULTIPLEXED\nNumberOfChannels=71\nSamplingInterval=400\n"
        "[Binary Infos]\nBinaryFormat=INT_16\n[Channel Infos]\n" + channels +
        "\n[Comment]\nInvented practice fixture only.\n[This is not an INI section]\n"
    )
    (directory / recording["header_file"]).write_text(header, encoding="utf-8-sig")
    markers = ["Mk1=New Segment,,1,1,0,20000101000000000000", "Mk2=Comment,Synthetic\\1 fixture,2,1,0",
               "Mk3=Stimulus,S 13,100,1,0"]
    for i, start in enumerate(starts):
        cue, execution = ((2, 21), (6, 61), (1, 11))[i % 3]
        for code, position in ((cue, int(start)), (execution, int(start) + 1), (8, int(start) + LENGTH + 1)):
            markers.append(f"Mk{len(markers) + 1}=Stimulus,S {code:2d},{position},1,0")
    markers.append(f"Mk{len(markers) + 1}=Stimulus,S 14,{samples},1,0")
    (directory / recording["marker_file"]).write_text(
        "Brain Vision Data Exchange Marker File, Version 1.0\n[Common Infos]\n"
        "Codepage=UTF-8\nDataFile=fixture.eeg\n[Marker Infos]\n" + "\n".join(markers) + "\n", encoding="utf-8"
    )
    for role in ("header", "marker", "binary"):
        recording[f"{role}_sha256"] = file_sha256(directory / recording[f"{role}_file"])
    return config
