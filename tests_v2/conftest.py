from copy import deepcopy
from pathlib import Path
from datetime import datetime, timezone
import pytest
from quant_alert.config import load_config
from quant_alert.demo import make_demo, DEMO_NOW

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def cfg():
    return load_config(str(ROOT/"config.yaml"))

@pytest.fixture
def demo(cfg):
    return make_demo(cfg)
