from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

DB = Path("data/etf_data.db")

requires_db = pytest.mark.skipif(not DB.exists(), reason="live warehouse not present")


@pytest.fixture(scope="session")
def warehouse():
    from tradeclassifier.loaders import Warehouse
    return Warehouse(DB)
