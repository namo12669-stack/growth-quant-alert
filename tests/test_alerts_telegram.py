from datetime import timedelta

import pytest
import requests

from growth_alert.alerts import choose_alerts
from growth_alert.demo import demo_records
from growth_alert.scoring import score_records
from growth_alert.telegram import TelegramClient, TelegramError, split_messages, utf16_length


def test_alert_cooldown(cfg, now):
    ranked = score_records(demo_records(now, cfg), cfg)
    first = choose_alerts(ranked, {}, 'preopen', now, cfg)
    assert first
    state = {'last_alerts': {f"preopen:{r['symbol']}": {'score': r['score'], 'at': now.isoformat(),
                                                        'triggers': r['triggers']} for r in first}}
    # Disable additional candidates to isolate repeat suppression.
    subset = [r for r in ranked if r['symbol'] in {x['symbol'] for x in first}]
    assert not choose_alerts(subset, state, 'preopen', now + timedelta(days=1), cfg)
    assert choose_alerts(subset, state, 'preopen', now + timedelta(days=6), cfg)


def test_stale_intraday_never_triggers_gap(cfg, now):
    ranked = score_records(demo_records(now, cfg), cfg)
    top = ranked[0]
    top.update(session_return=.2, intraday_available=False)
    alerts = choose_alerts([top], {}, 'preopen', now, cfg)
    assert 'PREMARKET_GAP_UP' not in alerts[0]['triggers']


def test_messages_split_with_utf16_emoji():
    text = ('abc \U0001f680\n' * 2000)
    chunks = split_messages(text)
    assert len(chunks) > 1
    assert all(utf16_length(c) <= 3800 for c in chunks)
    assert ''.join(c.replace('\n', '') for c in chunks) == text.replace('\n', '')


class Response:
    def __init__(self, status, body):
        self.status_code, self.body = status, body
    def json(self):
        return self.body


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
    def post(self, url, **kwargs):
        self.calls.append(kwargs)
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


def test_send_success_and_no_parse_mode():
    session = FakeSession([Response(200, {'ok': True, 'result': {'message_id': 42}})])
    client = TelegramClient('123:NOT_A_REAL_TOKEN', '456', session=session)
    assert client.send('A < B & x_y') == [42]
    assert 'parse_mode' not in session.calls[0]['json']


def test_rate_limit_retry():
    session = FakeSession([Response(429, {'ok': False, 'parameters': {'retry_after': 1}}),
                           Response(200, {'ok': True, 'result': {'message_id': 1}})])
    sleeps = []
    client = TelegramClient('123:NOT_A_REAL_TOKEN', '456', session, sleeps.append)
    assert client.send('test') == [1]
    assert sleeps == [1]


def test_secret_not_leaked_on_connection_failure():
    token = '123:VERY_SECRET_TOKEN'
    session = FakeSession([requests.ConnectionError('https://api.telegram.org/bot' + token)])
    client = TelegramClient(token, '456', session)
    with pytest.raises(TelegramError) as exc:
        client.send('test')
    assert token not in str(exc.value)
    assert len(session.calls) == 1  # No uncertain-delivery retry.


def test_unauthorized_redacted():
    session = FakeSession([Response(401, {'ok': False, 'error_code': 401})])
    with pytest.raises(TelegramError, match='BotFather'):
        TelegramClient('123:FAKE', '456', session).send('test')
