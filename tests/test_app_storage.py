import io
import json
import zipfile
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from growth_alert.app import run
from growth_alert.provider import pack_payload, unpack_payload
from growth_alert.storage import read_json, write_json
from scripts.restore_state import extract_state
from test_factors import make_payload


class Messenger:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail
    def send(self, text):
        if self.fail:
            raise RuntimeError('Synthetic delivery failure')
        self.sent.append(text)
        return [1]


class Provider:
    def __init__(self, fail=False):
        self.fail = fail
    def daily(self, symbol):
        if self.fail:
            raise RuntimeError('Synthetic provider failure')
        idx = pd.bdate_range('2025-01-01', '2026-09-04', tz='America/New_York')
        return pd.DataFrame({'Close': 20., 'Adj Close': 20., 'High': 21., 'Low': 19., 'Volume': 2000000}, index=idx)
    def fundamentals(self, symbol):
        p = make_payload()
        p['info'].update(marketCap=2e9, sector='Software')
        return p
    def intraday(self, symbol):
        return pd.DataFrame()


def universe():
    return {'core': [f'TEST{i}' for i in range(12)], 'speculative': []}


def test_demo_dry_run_no_network_or_state(cfg, now):
    result = run(cfg, universe(), 'demo', True, clock=lambda: now)
    assert result['selected'] > 0
    assert not (Path(cfg['data']['state_dir']) / 'state.json').exists()
    text = (Path(cfg['data']['output_dir']) / 'telegram_preview.txt').read_text()
    assert 'SYNTHETIC DATA - NOT LIVE' in text
    snapshot = json.loads((Path(cfg['data']['output_dir']) / 'snapshot.json').read_text())
    assert snapshot['metadata']['demo'] is True


def test_auto_send_and_deduplicate(cfg, now):
    messenger = Messenger()
    one = run(cfg, universe(), 'auto', False, Provider(), messenger, lambda: now)
    two = run(cfg, universe(), 'auto', False, Provider(), messenger, lambda: now)
    assert one['status'] == 'complete'
    assert two['reason'] == 'already_sent'
    assert len(messenger.sent) == 1
    assert (Path(cfg['data']['state_dir']) / 'journal.jsonl').exists()


def test_send_failure_not_marked_done(cfg, now):
    with pytest.raises(RuntimeError):
        run(cfg, universe(), 'auto', False, Provider(), Messenger(fail=True), lambda: now)
    assert not (Path(cfg['data']['state_dir']) / 'state.json').exists()


def test_failed_provider_sends_data_quality_not_candidates(cfg, now):
    messenger = Messenger()
    result = run(cfg, universe(), 'auto', False, Provider(fail=True), messenger, lambda: now)
    assert result['selected'] == 0
    assert result['meta']['data_degraded']
    assert 'DATA QUALITY ALERT' in messenger.sent[0]


def test_elapsed_window_cannot_send_late(cfg, now):
    calls = [0]
    def clock():
        calls[0] += 1
        return now if calls[0] == 1 else now + timedelta(minutes=60)
    messenger = Messenger()
    with pytest.raises(RuntimeError, match='window elapsed'):
        run(cfg, universe(), 'auto', False, Provider(), messenger, clock)
    assert not messenger.sent


def test_holiday_skips_before_provider_or_secrets(cfg):
    now = pd.Timestamp('2026-09-07T12:40:00Z').to_pydatetime()
    result = run(cfg, universe(), 'auto', clock=lambda: now)
    assert result['reason'] == 'calendar_or_time'


def test_json_nan_is_null_and_atomic(cfg):
    path = Path(cfg['data']['state_dir']) / 'test.json'
    write_json(path, {'value': float('nan')})
    assert read_json(path)['value'] is None
    assert not path.with_suffix('.json.tmp').exists()


def test_payload_roundtrip():
    data = make_payload()
    result = unpack_payload(pack_payload(data))
    assert result['income'].shape == data['income'].shape
    assert result['eps_trend'].loc['+1y', 'current'] == 1.2


def test_restore_rejects_path_traversal(tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('../secret.txt', 'bad')
    with pytest.raises(ValueError, match='Unsafe'):
        extract_state(stream.getvalue(), tmp_path / 'state')


def test_restore_valid_state(tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('state.json', '{"schema":1}')
        z.writestr('fundamentals/ABC.json', '{}')
    extract_state(stream.getvalue(), tmp_path / 'state')
    assert (tmp_path / 'state' / 'state.json').exists()
