from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import pytest
import requests
from quant_alert.models import Signal
from quant_alert import state
from quant_alert.telegram import TelegramClient, TelegramError, split_messages, utf16_length
from quant_alert.storage import write_json

@pytest.fixture
def sig():
    return Signal('TEST',['XYZ'],'bullish','1D','2026-09-08','event-one',['test only'])

def test_fingerprint_stable(sig):
    assert sig.signal_id==sig.signal_id and len(sig.signal_id)==20

def test_mark_after_success_and_dedup(cfg,sig,tmp_path):
    now=datetime(2026,9,9,tzinfo=timezone.utc); h=state.load(tmp_path)
    assert state.select([sig],h,now,cfg)[0]
    state.mark_delivered(tmp_path,h,sig,now,'manual',[123])
    assert state.select([sig],state.load(tmp_path),now,cfg)[0]==[]
    assert json.loads((tmp_path/'journal.jsonl').read_text())['signal_id']==sig.signal_id

def test_same_run_duplicate_suppressed(cfg,sig,tmp_path):
    chosen,reasons=state.select([sig,sig],state.load(tmp_path),datetime.now(timezone.utc),cfg)
    assert len(chosen)==1 and reasons[0]['reason']=='ALREADY_SENT_EVENT'

def test_distinct_new_event_respects_cooldown(cfg,sig,tmp_path):
    now=datetime.now(timezone.utc); h=state.load(tmp_path)
    state.mark_delivered(tmp_path,h,sig,now,'manual',[1])
    new=Signal('TEST',['XYZ'],'bullish','1D','2026-09-09','event-two',['test'])
    assert state.select([new],h,now+timedelta(hours=1),cfg)[1][0]['reason']=='COOLDOWN'
    assert state.select([new],h,now+timedelta(hours=49),cfg)[0]

def test_corrupt_state_fails_closed(tmp_path):
    (tmp_path/'state.json').write_text('{broken')
    with pytest.raises(ValueError): state.load(tmp_path)

def test_old_state_not_silently_reused(tmp_path):
    write_json(tmp_path/'state.json',{'schema':1})
    with pytest.raises(ValueError): state.load(tmp_path)

def test_utf16_splitting_preserves_all_text():
    text=('Signal '+chr(0x1F680)+' '*3)*2000
    parts=split_messages(text)
    assert len(parts)>1 and all(utf16_length(x)<=3800 for x in parts)

def test_missing_token_fails():
    with pytest.raises(TelegramError): TelegramClient('')

class Response:
    def __init__(self,code,body): self.status_code=code; self.body=body
    def json(self): return self.body

class Session:
    def __init__(self,responses): self.responses=iter(responses); self.calls=[]
    def post(self,*args,**kwargs):
        self.calls.append(kwargs)
        response=next(self.responses)
        if isinstance(response,Exception): raise response
        return response

def test_telegram_success():
    sess=Session([Response(200,{'ok':True,'result':{'message_id':10}})])
    assert TelegramClient('123:test','999',session=sess).send('test')==[10]

def test_rate_limit_retries_with_retry_after():
    sleeps=[]
    sess=Session([Response(429,{'ok':False,'parameters':{'retry_after':2}}),Response(200,{'ok':True,'result':{'message_id':11}})])
    assert TelegramClient('123:test','999',session=sess,sleep=sleeps.append).send('test')==[11]
    assert sleeps==[2]

def test_timeout_does_not_blindly_retry_or_leak_token():
    sess=Session([requests.Timeout('https://api.telegram.org/bot123:secret/sendMessage')])
    with pytest.raises(TelegramError) as err:
        TelegramClient('123:secret','999',session=sess).send('test')
    assert 'secret' not in str(err.value) and len(sess.calls)==1

def test_unauthorized_is_redacted():
    sess=Session([Response(401,{'ok':False,'error_code':401,'description':'123:secret'})])
    with pytest.raises(TelegramError) as err:
        TelegramClient('123:secret','999',session=sess).send('test')
    assert 'secret' not in str(err.value)
