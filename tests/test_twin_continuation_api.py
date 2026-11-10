from dataclasses import asdict
from decimal import Decimal
import csv
import io

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.strategies.twin_continuation import Parameters
from research_fixtures import reserved_source
from test_twin_continuation import momentum_rows, momentum_parameters, breakout_rows


def csv_bytes(rows):
    out=io.StringIO(newline='')
    writer=csv.writer(out,lineterminator='\n')
    writer.writerow(['Date','Time','Open','High','Low','Close','Volume','UpVol','DownVol'])
    for b in rows:
        writer.writerow([b.date,b.time[:5],b.open,b.high,b.low,b.close,b.volume,b.up_vol,b.down_vol])
    return out.getvalue().encode()


def values(parameters):
    return {k:str(v) if type(v) is Decimal else v for k,v in asdict(parameters).items()}


@pytest.mark.parametrize('kind,net',[('momentum',148),('breakout',318)])
def test_normal_saved_backtest_trade_risk_downloads_and_reopen(tmp_path,kind,net):
    rows=momentum_rows() if kind=='momentum' else breakout_rows()
    p=momentum_parameters() if kind=='momentum' else Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1,immediate_protection=False)
    raw,split=reserved_source(csv_bytes(rows))
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-twin.csv',name='SYNTHETIC Twin '+kind,
            symbol='NQ',source_timezone='UTC',tick_size='.25',point_value='20'),content=raw)
        assert response.status_code==201,response.text
        dataset=response.json()
        response=client.post('/api/backtests',json=dict(dataset_id=dataset['id'],strategy_id='twin_continuation',
            strategy_parameters=values(p),sample_split=split,
            execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1')))
        assert response.status_code==201,response.text
        record=response.json();run=record['id']
        assert Decimal(record['summary']['total_net_pnl'])==net
        assert record['run_metadata']['strategy']['parameters']==values(p)
        assert not record.get('execution_decisions')  # Not falsely certified as native decision capture.
        trade=client.get(f'/api/backtests/{run}/trades').json()['items'][0]
        assert trade['entry_reason']==('MO-L' if kind=='momentum' else 'BO-L')
        for export in ('report','trades','equity'):
            assert client.get(f'/api/backtests/{run}/exports/{export}').status_code==200
        assert client.get(f"/api/datasets/{dataset['id']}/csv").content==raw
        checked=client.post('/api/prop-analyses/check',json=dict(source_backtest_id=run,trade_file=None,settings={}))
        assert checked.status_code==422 and 'At least two session weekdays' in checked.text
        from alphaquest.prop.source import prepare_source
        source,checked_rows=prepare_source(client.app.state.runs,run,'')
        assert source['reconciliation']['source_totals']['net_pnl']==str(Decimal(net).quantize(Decimal('.01')))
        assert source['excursion_input']['measured_mae_count']==0
        assert source['excursion_input']['native_ohlc_count']==1
        if kind=='breakout':
            from alphaquest.prop.source import prepare_source
            snapshot,trades=prepare_source(client.app.state.runs,run,None)
            assert Decimal(trades[0]['ohlc_mae_lower'])==6
            assert Decimal(trades[0]['ohlc_mae_upper'])==226
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        assert client.get(f'/api/backtests/{run}').json()['summary']==record['summary']


def test_known_nonminute_source_rejects_before_research_claim(tmp_path):
    from datetime import datetime,timedelta,timezone
    from test_twin_continuation import prices
    rows=[prices(i+1,datetime(2024,1,16,tzinfo=timezone.utc)+timedelta(minutes=5*i)) for i in range(10)]
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        saved=client.post('/api/datasets',params=dict(filename='SYNTHETIC-5m.csv',name='SYNTHETIC wrong interval',
            symbol='NQ',source_timezone='UTC',tick_size='.25',point_value='20'),content=csv_bytes(rows)).json()
        response=client.post('/api/backtests',json=dict(dataset_id=saved['id'],strategy_id='twin_continuation',strategy_parameters=values(Parameters()),
            sample_split=dict(mode='dates',is_start='2024-01-16',is_end='2024-01-16',oos_start='2024-01-17',oos_end='2024-01-17'),
            execution_settings=dict(initial_capital='10000',slippage_ticks=0,commission_per_contract_per_side='0')))
        assert response.status_code==422 and 'one-minute' in response.text


def test_missing_session_close_returns_actionable_422_and_failed_progress(tmp_path):
    from datetime import datetime
    from uuid import uuid4
    from test_twin_continuation import prices,CT
    rows=momentum_rows()[:26]
    rows.append(prices(27,datetime(2024,1,16,12,0,tzinfo=CT),120,121,119,120))
    rows.append(prices(28,datetime(2024,1,16,17,1,tzinfo=CT),120,121,119,120))
    raw,split=reserved_source(csv_bytes(rows))
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        saved=client.post('/api/datasets',params=dict(filename='SYNTHETIC-missing-close.csv',name='SYNTHETIC Twin missing close',
            symbol='NQ',source_timezone='UTC',tick_size='.25',point_value='20'),content=raw)
        assert saved.status_code==201,saved.text
        dataset=saved.json();operation=str(uuid4())
        response=client.post('/api/backtests',params=dict(progress_id=operation),json=dict(
            dataset_id=dataset['id'],strategy_id='twin_continuation',strategy_parameters=values(momentum_parameters()),sample_split=split,
            execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1')))
        assert response.status_code==422,response.text
        detail=response.json()['detail']
        for text in ('2024-01-16 16:00','2024-01-16 12:00','2024-01-16 17:01',
                     'selected bar 28','holding MO long','shortened-session policy','No session-close fill was invented'):
            assert text in detail
        progress=client.get('/api/progress/'+operation).json()
        assert progress['stage']=='failed' and progress['error']==detail
        assert client.get('/api/backtests').json()['total']==0
        assert client.get('/api/datasets/'+dataset['id']+'/csv').content==raw
