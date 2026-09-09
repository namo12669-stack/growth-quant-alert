import json
import io
import zipfile
import sys
from types import SimpleNamespace
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest
import yaml
from quant_alert.config import load_config, load_universe
from quant_alert.demo import DemoProvider, DEMO_NOW
from quant_alert.app import run_scan
from quant_alert.provider import split_download, CSVProvider, YahooProvider
from scripts.restore_state import extract_state
from scripts.evaluate_alerts import entry_session, evaluate

ROOT=Path(__file__).resolve().parents[1]

def test_load_v2_config_universe():
    cfg=load_config(str(ROOT/'config.yaml')); u=load_universe(str(ROOT/'universe.yaml'))
    assert cfg['model'].startswith('quant-signals-v2')
    assert {'OKLO','NVDA','SMR'} <= set(u['stocks'])
    assert len(u['pairs'])==11

def test_old_config_rejected(tmp_path):
    p=tmp_path/'config.yaml'; p.write_text('model: growth-alert-v1.2')
    with pytest.raises(ValueError): load_config(str(p))

def test_workflow_paths_names_and_secrets():
    f=yaml.safe_load((ROOT/'.github/workflows/alerts.yml').read_text())
    assert f['name']=='Quant Signals V2'
    assert f['on']['workflow_dispatch']['inputs']['mode']['options']==['demo','manual','auto']
    assert all(s['timezone']=='America/New_York' for s in f['on']['schedule'])
    assert f['permissions']['contents']=='read'
    assert 'SEC_USER_AGENT' not in (ROOT/'.github/workflows/alerts.yml').read_text()

@pytest.mark.parametrize('ticker_first',[True,False])
def test_yahoo_multiindex_orientations(ticker_first,demo):
    _,d=demo
    f=pd.concat({'A':d['DEMO_A'],'B':d['DEMO_B']},axis=1)
    if not ticker_first: f=f.swaplevel(axis=1)
    result=split_download(f,['A','B'])
    assert result['A'].Close.iloc[-1]==d['DEMO_A'].Close.iloc[-1]

def test_flat_single_symbol(demo):
    _,d=demo
    assert not split_download(d['DEMO_A'],['A'])['A'].empty

def test_ambiguous_flat_multisymbol_not_assigned_to_wrong_stock(demo):
    _,d=demo
    assert split_download(d['DEMO_A'],['A','B'])['A'].empty

def test_csv_missing_reports_reason(tmp_path):
    p=CSVProvider(str(tmp_path))
    assert p.fetch(['ABC'])['ABC'].empty and p.diagnostics[0]['error']=='CSV_NOT_FOUND'

def test_yahoo_price_only_adapter_does_not_call_info(cfg,demo,monkeypatch):
    _,d=demo
    calls=[]
    def download(**kwargs):
        calls.append(kwargs)
        return pd.concat({'A':d['DEMO_A']},axis=1)
    monkeypatch.setitem(sys.modules,'yfinance',SimpleNamespace(download=download))
    cfg['provider']['pause_seconds']=0
    provider=YahooProvider(cfg)
    assert not provider.fetch(['A'])['A'].empty
    assert calls[0]['auto_adjust'] is True and calls[0]['interval']=='1d'

def test_demo_runs_all_engines_without_state_writes(cfg,tmp_path):
    p=DemoProvider(cfg)
    result=run_scan(cfg,p.universe,p,DEMO_NOW,mode='demo',dry_run=True,
                    output_dir=str(tmp_path/'out'),state_dir=str(tmp_path/'state'))
    assert result['usable_stocks']==6 and result['detected_count']>=5
    assert not (tmp_path/'state').exists()
    text=(tmp_path/'out/telegram_preview.txt').read_text()
    assert 'SYNTHETIC' in text and 'PAIR_SPREAD' in text and 'LEAD_LAG' in text

def test_empty_provider_does_not_create_opportunities(cfg,tmp_path):
    p=DemoProvider(cfg); p.data={}
    r=run_scan(cfg,p.universe,p,DEMO_NOW,mode='manual',dry_run=True,output_dir=str(tmp_path/'out'),state_dir=str(tmp_path/'state'))
    assert r['usable_stocks']==0 and not r['quality_gate'] and r['selected_count']==0
    assert r['fundamentals']=='NOT_REQUESTED_NOT_CHECKED'

def test_started_lead_lag_target_is_not_new_prediction(cfg,tmp_path):
    p=DemoProvider(cfg)
    now=DEMO_NOW+timedelta(hours=2)
    r=run_scan(cfg,p.universe,p,now,mode='manual',dry_run=True,output_dir=str(tmp_path/'out'),state_dir=str(tmp_path/'state'))
    assert any(x['reason']=='LEAD_LAG_TARGET_ALREADY_STARTED' for x in r['suppressed'])

def test_missed_scheduled_window_does_not_send(cfg,tmp_path):
    p=DemoProvider(cfg)
    r=run_scan(cfg,p.universe,p,DEMO_NOW,mode='preopen',scheduled=True,
               output_dir=str(tmp_path/'out'),state_dir=str(tmp_path/'state'),
               clock=lambda:DEMO_NOW+timedelta(hours=2))
    assert r['delivery']=='SKIPPED_LATE' and not (tmp_path/'state').exists()

def test_safe_state_extract_only_allowlist(tmp_path):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z: z.writestr('state.json','{}')
    extract_state(b.getvalue(),tmp_path)
    assert (tmp_path/'state.json').exists()

@pytest.mark.parametrize('name',['../evil.txt','/tmp/evil','fundamentals/NVDA.json','token.txt'])
def test_state_extract_rejects_unexpected_files(tmp_path,name):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr(name,'x')
    with pytest.raises(ValueError):extract_state(b.getvalue(),tmp_path)

@pytest.mark.parametrize('now,day',[
 ('2026-09-09T12:45:00Z','2026-09-09'),
 ('2026-09-09T19:30:00Z','2026-09-10'),
 ('2026-09-06T19:30:00Z','2026-09-08'),
])
def test_forward_evaluation_never_fills_before_alert(now,day):
    assert str(entry_session(datetime.fromisoformat(now)))==day

def test_future_outcomes_stay_pending(demo):
    _,data=demo
    rec={'signal_id':'x','kind':'TEST','symbols':['DEMO_BREAK'],'direction':'bullish','observed_at':DEMO_NOW.isoformat()}
    out=evaluate([rec],data,benchmark='DEMO_MKT')
    assert len(out)==3 and (out.status=='PENDING_OR_MISSING_DATA').all()

class FakeTelegram:
    def __init__(self): self.messages=[]
    def send(self,text):
        self.messages.append(text)
        return [len(self.messages)]

def test_live_style_delivery_uses_ack_time_not_earlier_scan_time(cfg,tmp_path):
    p=DemoProvider(cfg); client=FakeTelegram(); delivered=DEMO_NOW+timedelta(minutes=2)
    r=run_scan(cfg,p.universe,p,DEMO_NOW,mode='manual',client=client,
               output_dir=str(tmp_path/'out'),state_dir=str(tmp_path/'state'),clock=lambda:delivered)
    lines=(tmp_path/'state/journal.jsonl').read_text().splitlines()
    assert lines and all(json.loads(x)['observed_at']==delivered.isoformat() for x in lines)
    assert r['delivery']=='SENT'

def test_manual_run_cannot_send_expired_next_session_forecast(cfg,tmp_path):
    p=DemoProvider(cfg); client=FakeTelegram()
    r=run_scan(cfg,p.universe,p,DEMO_NOW,mode='manual',client=client,
               output_dir=str(tmp_path/'out'),state_dir=str(tmp_path/'state'),
               clock=lambda:DEMO_NOW+timedelta(hours=2))
    assert any(s['reason']=='LEAD_LAG_TARGET_STARTED_BEFORE_SEND' for s in r['suppressed'])
    assert not any(x.startswith('LEAD_LAG |') for x in client.messages)

def test_demo_send_never_writes_live_journal(cfg,tmp_path):
    p=DemoProvider(cfg); client=FakeTelegram()
    run_scan(cfg,p.universe,p,DEMO_NOW,mode='demo',client=client,
             output_dir=str(tmp_path/'out'),state_dir=str(tmp_path/'state'))
    assert client.messages and all('SYNTHETIC' in x for x in client.messages)
    assert not (tmp_path/'state').exists()


def test_evaluation_cli_all_pending_does_not_fail(tmp_path, demo, monkeypatch):
    from scripts.evaluate_alerts import main as evaluation_main
    _, data = demo
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    for symbol, frame in data.items():
        frame.to_csv(inputs / f'{symbol}_daily.csv', index_label='Date')
    record = {'signal_id': 'pending', 'kind': 'TEST', 'symbols': ['DEMO_BREAK'],
              'direction': 'bullish', 'observed_at': DEMO_NOW.isoformat()}
    journal = tmp_path / 'journal.jsonl'
    journal.write_text(json.dumps(record)+'\n')
    out = tmp_path / 'evaluation'
    monkeypatch.setattr(sys, 'argv', ['evaluate_alerts.py', '--journal', str(journal),
                                    '--prices', str(inputs), '--benchmark', 'DEMO_MKT',
                                    '--out', str(out)])
    assert evaluation_main() == 0
    results = pd.read_csv(out / 'forward_outcomes.csv')
    assert (results.status == 'PENDING_OR_MISSING_DATA').all()
    assert json.loads((out / 'summary.json').read_text())['stats'] == []


def test_evaluation_empty_journal_has_stable_schema():
    out = evaluate([], {})
    assert out.empty and {'status', 'metric', 'value'} <= set(out.columns)
