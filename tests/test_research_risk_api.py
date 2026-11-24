from decimal import Decimal
from copy import deepcopy
import json
import pytest
from test_native_replay_api import source
from research_fixtures import ResearchClient
from alphaquest.app import create_app

@pytest.fixture
def client(tmp_path):
 with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as value:yield value


def test_saved_causal_risk_report_download_and_historical_derivation_preserve_source(client):
 record=source(client)
 id=record['id'];runs=client.app.state.runs
 before=(runs.root/id/'trades.csv').read_bytes()
 response=client.get(f'/api/backtests/{id}/risk-diagnostics');assert response.status_code==200,response.text
 data=response.json();assert data['coverage']==dict(valid_trades=3,total_trades=3,complete=True,missing_reasons={})
 # Independent fixture: initial stop distances 5,5,10 MNQ points with no costs;
 # net -10,+20,+20 per one contract, respectively -1R,+2R,+1R.
 assert [Decimal(r['planned_risk_per_contract']) for r in data['trades']]==[10,10,20]
 assert [Decimal(r['planned_net_r']) for r in data['trades']]==[-1,2,1]
 assert data['version']=='planned-net-r-v1'
 download=client.get(f'/api/backtests/{id}/exports/risk_metrics');assert download.status_code==200
 assert 'attachment' in download.headers['content-disposition'];assert download.json()==data
 assert (runs.root/id/'trades.csv').read_bytes()==before
 path=runs.root/id/'risk_metrics.json';assert path.exists()
 original=path.read_bytes();path.write_bytes(b'{}')
 assert client.get(f'/api/backtests/{id}/risk-diagnostics').status_code==409
 path.unlink()
 assert client.get(f'/api/backtests/{id}/risk-diagnostics').status_code==409
 path.write_bytes(original)
 # Same source and captured decision evidence can derive metrics without a rerun.
 with runs.connect() as db:
  raw=json.loads(db.execute('SELECT manifest FROM runs WHERE id=?',(id,)).fetchone()[0]);historical=deepcopy(raw)
  historical.pop('risk_diagnostics');historical['artifacts'].pop('risk_metrics_json')
  db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(historical),id))
 old=client.get(f'/api/backtests/{id}/risk-diagnostics');assert old.status_code==200,old.text
 assert old.json()['summary']==data['summary']
 assert (runs.root/id/'trades.csv').read_bytes()==before

 # Historical absence stays unavailable, rather than inventing initial stops.
 with runs.connect() as db:
  historical.pop('execution_decisions');historical['artifacts'].pop('execution_decisions_jsonl')
  db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(historical),id))
 missing=client.get(f'/api/backtests/{id}/risk-diagnostics')
 assert missing.status_code==200,missing.text
 assert missing.json()['status']=='unavailable'
 assert missing.json()['summary']['mean_planned_net_r'] is None
 assert missing.json()['coverage']['missing_reasons']=={'initial_stop_unavailable':3}
 assert (runs.root/id/'trades.csv').read_bytes()==before
