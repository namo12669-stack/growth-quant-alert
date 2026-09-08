from pathlib import Path

import pytest
import yaml

from growth_alert.config import load_config, load_universe
from growth_alert.factors import FEATURES


def test_feature_weights_and_count():
    assert sum(len(v) for v in FEATURES.values()) == 13
    assert all(abs(sum(v.values())-1) < 1e-10 for v in FEATURES.values())


def test_no_core_speculative_overlap():
    universe = load_universe()
    assert len(universe['core']) == 40
    assert len(universe['speculative']) == 3
    assert not set(universe['core']) & set(universe['speculative'])


def test_reject_bad_weights(tmp_path):
    config = load_config()
    config['scoring']['family_weights']['growth'] = .5
    path = tmp_path/'bad.yaml'
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match='total'):
        load_config(path)


def test_all_workflows_parse_and_schedule_timezone():
    for path in Path('.github/workflows').glob('*.yml'):
        # BaseLoader avoids YAML 1.1 interpreting the GitHub key 'on' as True.
        parsed = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        assert 'on' in parsed and 'jobs' in parsed
    alerts = yaml.load(Path('.github/workflows/alerts.yml').read_text(), Loader=yaml.BaseLoader)
    assert len(alerts['on']['schedule']) == 3
    assert all(s['timezone'] == 'America/New_York' for s in alerts['on']['schedule'])
    assert alerts['permissions'] == {'contents': 'read', 'actions': 'read'}
