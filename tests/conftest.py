from pathlib import Path

import pytest

from fixtures.contract_fixture import synthetic_signal_pair
from neurosec_core.config import load_config
from neurosec_core.runs import RunLayout

REPO_ROOT = Path(__file__).resolve().parents[1]


def pytest_configure():
    # Ignored output directories do not exist in a fresh checkout.
    (REPO_ROOT / "outputs/smoke").mkdir(parents=True, exist_ok=True)


@pytest.fixture
def signal_pair():
    return synthetic_signal_pair()


@pytest.fixture
def config():
    return load_config(REPO_ROOT)


@pytest.fixture
def layout(tmp_path, config):
    # All test study directories are nested inside pytest's ignored smoke root.
    return RunLayout.from_config(tmp_path, config["paths"])
