from copy import deepcopy
from datetime import datetime, timezone

import pytest

from growth_alert.config import load_config


@pytest.fixture
def cfg(tmp_path):
    result = deepcopy(load_config())
    result["data"]["state_dir"] = str(tmp_path / "state")
    result["data"]["output_dir"] = str(tmp_path / "output")
    return result


@pytest.fixture
def now():
    return datetime(2026, 9, 8, 12, 40, tzinfo=timezone.utc)
