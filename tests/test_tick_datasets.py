"""Independent binary fixtures: no dependency on importer packing/aggregation."""
import io,struct
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
import pytest
from alphaquest.datasets import DatasetStore
from alphaquest.tick_data import build,us
from alphaquest.backtest_data import read_bars
from alphaquest.execution import execute,Trade
from alphaquest.strategy import EntryIntent,EntryProtection,StopEntriesIntent,BracketIntent,CloseIntent,ExecutionConfig

START=datetime(2026,1,5,14,30,tzinfo=timezone.utc)
SETTINGS=dict(tick_size='0.25',point_value='20')
CONFIG=ExecutionConfig(D('50000'),D('.25'),D('20'),0,D('0'))

def raw(rows):
    result=bytearray(b'SCID'+struct.pack('<IIHH',56,40,1,0)+bytes(40))
    for second,price,bid,ask in rows:
        result.extend(struct.pack('<q4f4I',us(START+timedelta(seconds=second)),0,0,0,price,1,bid+ask,bid,ask))
    return bytes(result)

def save(tmp_path,rows):
    path=tmp_path/'example.scid';path.write_bytes(raw(rows))
    store=DatasetStore(tmp_path/'datasets.sqlite3')
    ds=build(store,path,path.name,'Synthetic ticks','NQ','UTC',SETTINGS)
    return store,ds

def bars(store,ds):
    with read_bars(store,ds['id']) as selected:return list(selected)


def test_import_features_and_tamper(tmp_path):
    store,ds=save(tmp_path,[(0,100,1,2),(10,102,0,3),(20,99,4,0),(60,101,2,2)])
    bs=bars(store,ds)
    assert [(b.open,b.high,b.low,b.close,b.volume) for b in bs]==[(D(100),D(102),D(99),D(99),D(10)),(D(101),)*4+(D(4),)]
    assert bs[0].flow.delta==0 and bs[0].flow.records==3
    assert bs[0].flow.vwap==D('100.2')
    assert bs[0].timestamp_utc==START+timedelta(minutes=1)
    assert [r['price'] for r in bs[0].tick_window.array()]==[100,102,99]
    from pathlib import Path
    path=Path(ds['tick_data']['sources'][0]['path']);data=bytearray(path.read_bytes());data[-1]^=1;path.write_bytes(data)
    with pytest.raises(ValueError,match='checksum'):bars(store,ds)

@pytest.mark.parametrize('kind',['inversion','aggregate','offgrid','truncated','quote'])
def test_reject_invalid_sources(tmp_path,kind):
    data=bytearray(raw([(0,100,0,1),(1,101,0,1)]))
    if kind=='inversion':struct.pack_into('<q',data,96,us(START-timedelta(seconds=1)))
    if kind=='aggregate':struct.pack_into('<I',data,80,2)
    if kind=='offgrid':struct.pack_into('<f',data,76,100.1)
    if kind=='truncated':data.pop()
    if kind=='quote':struct.pack_into('<II',data,80,0,0)
    path=tmp_path/'bad.scid';path.write_bytes(data)
    store=DatasetStore(tmp_path/'datasets.sqlite3')
    with pytest.raises(ValueError):build(store,path,path.name,'Bad','NQ','UTC',SETTINGS)
    assert store.list()==[]


@pytest.mark.parametrize('short',[False,True])
def test_tick_order_resolves_oco_and_attached_protection(tmp_path,short):
    rows=[(0,100,1,0),(60,100,1,0),(61,102,0,1),(62,104,0,1),(63,98,1,0),(120,100,1,0)]
    if short:rows=[(t,200-p,b,a) for t,p,b,a in rows]
    store,ds=save(tmp_path,rows)
    class Strategy:
        def on_bar(self,b,p):
            assert b.tick_window is None
            if b.bar_number==1:
                protection=EntryProtection(stop_distance=D(2),target_distance=D(2))
                return StopEntriesIntent(((EntryIntent(1,'buy',side='long',timing='next_open',protection=protection),D(102)),(EntryIntent(1,'sell',side='short',timing='next_open',protection=protection),D(98))))
            return CloseIntent('done') if p else None
        def on_finish(self,b,p):return CloseIntent('finish') if p else None
    events=list(execute(bars(store,ds),Strategy(),CONFIG,capture_risk=True))
    trades=[e for e in events if type(e) is Trade]
    assert len(trades)==1
    t=trades[0];assert (t.side,t.entry_fill_price,t.exit_fill_price,t.net_pnl)==('short' if short else 'long',D(98 if short else 102),D(96 if short else 104),D(40))
    assert t.entry_time_utc==START+timedelta(seconds=61)
    assert t.exit_time_utc==START+timedelta(seconds=62)
    from alphaquest.intratrade import IntratradeRisk
    risk=next(e for e in events if type(e) is IntratradeRisk)
    assert risk.mae_upper==0 # 98 occurred after the exit


def test_tick_bracket_target_precedes_later_stop(tmp_path):
    store,ds=save(tmp_path,[(0,100,1,0),(60,100,1,0),(120,100,1,0),(121,103,0,1),(122,97,1,0)])
    class Strategy:
        def on_bar(self,b,p):
            if b.bar_number==1:return EntryIntent(1,'enter',timing='next_open')
            if p:return BracketIntent(D(98),D(102))
        def on_finish(self,b,p):return CloseIntent('finish') if p else None
    trade=next(e for e in execute(bars(store,ds),Strategy(),CONFIG) if type(e) is Trade)
    assert (trade.exit_fill_price,trade.exit_reason)==(D(102),'take_profit')
    assert trade.exit_time_utc==START+timedelta(seconds=121)


def test_upload_api_csv_backtest_flow_export_and_roll(tmp_path):
    from research_fixtures import ResearchClient,declaration
    from alphaquest.app import create_app
    from test_backtest_api import body
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        uploaded=client.post('/api/datasets/ticks',params=dict(filename='test.scid',name='Synthetic tick API',symbol='NQ',progress_id='11111111-1111-4111-8111-111111111111'),content=raw([(0,100,1,1),(30,101,1,2),(60,101,1,2),(90,102,1,2),(120,102,1,2),(150,103,1,2),(86400,100,1,2)]))
        assert uploaded.status_code==201,uploaded.text
        ds=uploaded.json()
        result=client.post('/api/backtests',json={**body(ds['id']), 'strategy_parameters':dict(green_bar_count=1,hold_minutes=1,contracts=1),'report_detail':'full'})
        assert result.status_code==201,result.text
        report=result.json()
        assert report['run_metadata']['execution_data']['kind']=='ordered_trade_ticks'
        assert report['summary']['trades_taken']>0
        request=dict(name='Synthetic explicit roll',symbol='NQ',segments=[dict(dataset_id=ds['id'],first_session='2026-01-05',last_session='2026-01-05')])
        composed=client.post('/api/datasets/ticks/compose',json=request)
        assert composed.status_code==201,composed.text
        assert composed.json()['row_count']==3
        with pytest.raises(ValueError,match='composed'):client.app.state.store.delete(ds['id'])
        assert client.delete('/api/datasets/'+ds['id']).status_code==409
        bad=client.post('/api/datasets/ticks',params=dict(filename='trades.csv',name='Synthetic CSV',symbol='NQ'),content=b'timestamp,price,volume,bid_volume,ask_volume\n2026-01-06T14:30:00Z,100,3,1,2\n2026-01-06T14:31:00Z,101,1,0,1\n')
        assert bad.status_code==201,bad.text


def native_scid(values):
    data=bytearray(b'SCID'+struct.pack('<IIHH',56,40,1,0)+bytes(40))
    for b in values:
        for i,price in enumerate((b.open,b.high,b.low,b.close)):
            stamp=b.timestamp_utc-timedelta(seconds=60-15*i)
            data.extend(struct.pack('<q4f4I',us(stamp),0,0,0,float(price),1,1,0 if i<3 else 1,1 if i<3 else 0))
    return bytes(data)


def native_source(client,*,days=3,payout=False,dataset_id=None):
    from native_replay_fixtures import bars,parameter_values
    from test_optimization import wait_job
    values=bars(days=days,payout=payout)
    split=dict(mode='dates',is_start=str(values[0].timestamp_utc.date()),is_end=str(values[-1].timestamp_utc.date()),oos_start=str((values[-1].timestamp_utc+timedelta(days=1)).date()),oos_end=str((values[-1].timestamp_utc+timedelta(days=1)).date()))
    values.append(replace(values[-1],bar_number=len(values)+1,timestamp_utc=values[-1].timestamp_utc+timedelta(days=1)))
    uploaded=client.get('/api/datasets/'+dataset_id) if dataset_id else client.post('/api/datasets/ticks',params=dict(filename='SYNTHETIC-native.scid',name='SYNTHETIC native tick price paths',symbol='MNQ',tick_size='.25',point_value='2'),content=native_scid(values))
    assert uploaded.status_code==(200 if dataset_id else 201),uploaded.text
    values={**parameter_values(),'use_order_flow':True}
    result=client.post('/api/optimizations',json=dict(dataset_id=uploaded.json()['id'],method='exhaustive',sample_split=split,workers=1,automatic_prop=False,strategy_id='vwap_pullback_risk_sizing',parameter_ranges={k:dict(start=v,end=v,step='0' if isinstance(v,str) else 0) for k,v in values.items()},execution_settings=dict(initial_capital='10000',slippage_ticks=0,commission_per_contract_per_side='0')))
    assert result.status_code==202,result.text
    job=wait_job(client,result.json()['id']);assert job['status']=='complete',job
    row,=client.get('/api/optimizations/'+job['id']+'/results').json()['items']
    return client.get('/api/backtests/'+row['run_id']).json()


@pytest.mark.parametrize('phase',['evaluation','funded'])
@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_native_tick_orderflow_percentage_account_replay(tmp_path,phase,profile):
    from research_fixtures import ResearchClient
    from alphaquest.app import create_app
    from test_native_replay_api import body,wait
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        original=native_source(client)
        assert original['summary']['trades_taken']==3
        request=body(client,original,phase)
        defaults=client.get('/api/prop-analyses/defaults').json()['native_phase_replay']
        request['profile']=next(p for p in defaults['profiles'][phase] if p['profile_id']==profile)
        if phase=='evaluation':request['profile'].update(evaluation_price='30',activation_fee='40' if profile=='apex-50k-eod' else '0')
        check=client.post('/api/prop-analyses/check',json=request);assert check.status_code==200,check.text
        response=client.post('/api/prop-analyses',json=request);assert response.status_code==202,response.text
        wait(client,response.json()['id'])
        report=client.get('/api/prop-analyses/'+response.json()['id']+'/downloads/report.json').json()
        trades=client.get('/api/backtests/'+report['native_backtest_id']+'/trades').json()['items']
        assert [t['contracts'] for t in trades]==[10,9,5]
        assert [D(t['net_pnl']) for t in trades]==[D(-120),D(180),D(100)]
        assert trades[0]['entry_time_utc'].endswith('15:01:00+00:00') or '15:01:00' in trades[0]['entry_time_utc']


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_prepared_tick_paths_and_worker_spool_match_full_native(tmp_path,phase):
    from native_replay_fixtures import bars as original,parameters
    from test_native_draws import contexts,open_days,owner,chosen,CONFIG as native_config
    from alphaquest.prop.native_draws import build_catalogue,run_path
    from alphaquest.prop.native_preparation import NativeEventPreparation,run_prepared_path,worker_programme
    from datetime import date
    path=tmp_path/'native.scid';path.write_bytes(native_scid(original()))
    store=DatasetStore(tmp_path/'datasets.sqlite3');ds=build(store,path,path.name,'Synthetic prepared ticks','MNQ','UTC',dict(tick_size='.25',point_value='2'))
    values=bars(store,ds);p=replace(parameters(),use_order_flow=True)
    from alphaquest.session_calendar import session_date
    days=sorted({session_date(b.timestamp_utc) for b in values})
    c=build_catalogue(values,contexts(days),p,block_sessions=1,source_identity={'dataset_sha256':ds['sha256']})
    from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
    factory=lambda:VwapPullbackRiskSizing(p,execution_config=native_config,instrument_symbol='MNQ')
    programme=NativeEventPreparation(c,factory,native_config)
    target=contexts(open_days(date(2026,1,12),3),modeled=True)
    from alphaquest.prop.native_draws import build_schedule
    for seed in range(1000):
        schedule=build_schedule(c,target,p,phase=phase,seed=seed,path_index=0,start_date=min(target))
        if [d['source_block_index'] for d in schedule['draws']]==[0,1,2]:break
    else:raise AssertionError('No matching schedule')
    expected=run_path(c,schedule,owner(target,phase=phase),factory,native_config,target)['result']
    prepared=worker_programme(programme,tmp_path/'worker')
    assert prepared.catalogue.bars[900].tick_window==values[900].tick_window
    assert prepared.catalogue.bars[900].flow==values[900].flow
    actual=run_prepared_path(prepared.catalogue,schedule,owner(target,phase=phase),factory,native_config,target,preparation=prepared)['result']
    assert expected==actual


@pytest.mark.parametrize('placement',['separate','shared'])
def test_tick_portfolio_replays_actual_percentage_positions(tmp_path,placement):
    from test_prop_portfolio_core import context
    from alphaquest.prop.portfolio_lifecycle import run_lineup
    from alphaquest.session_calendar import session_date
    c=context()
    path=tmp_path/'portfolio.scid';path.write_bytes(native_scid([b for rs in c['bars'].values() for b in rs]))
    store=DatasetStore(tmp_path/'datasets.sqlite3');ds=build(store,path,path.name,'Synthetic portfolio ticks','MNQ','UTC',dict(tick_size='.25',point_value='2'))
    books={}
    for b in bars(store,ds):books.setdefault(session_date(b.timestamp_utc),[]).append(b)
    c['bars']=books;c['strategies'][0]['parameters']['use_order_flow']=True
    allocation=dict(placement=placement,**(dict(counts=[1]) if placement=='separate' else dict(weights=[4],accounts=1)))
    actual=run_lineup(c,allocation,capture=True)
    assert [t['contracts'] for t in actual['trades']]==[10,9,5]
    assert [D(t['net_pnl']) for t in actual['trades']]==[-120,180,100]
    assert D(actual['cash']['net_cash'])==-49


def test_tick_campaign_all_phases_monte_carlo_and_fixed_prop_searches(tmp_path):
    """Normal public campaign and Prop Sim routes, with no gate bypasses."""
    from research_fixtures import ResearchClient
    from alphaquest.app import create_app
    from test_campaign_oos import frozen_workflow,oos_csv,run_oos
    from test_prop_sim import body,wait_prop
    from test_prop_sim_automatic import wait_automatic
    from test_native_replay_api import wait
    from alphaquest.strategy import Bar
    import csv,json
    def convert(raw_csv):
        output=[]
        for i,r in enumerate(csv.DictReader(io.StringIO(raw_csv.decode())),1):
            stamp=datetime.strptime(r['Date']+' '+r['Time'],'%m/%d/%Y %H:%M').replace(tzinfo=timezone.utc)
            if stamp.weekday()>=5:continue
            prices=[D(10000)+(D(r[k])-100)*100 for k in ('Open','High','Low','Close')]
            output.append(Bar(len(output)+1,stamp,r['Date'],r['Time'],*prices,D(4),D(3),D(1),()))
        return native_scid(output)
    class TickClient(ResearchClient):
        def post(self,url,**kwargs):
            if str(url).endswith('/api/datasets'):
                kwargs['content']=convert(kwargs['content']);kwargs['params']=dict(kwargs['params'],filename='SYNTHETIC-campaign.scid')
                url='/api/datasets/ticks'
            return super().post(url,**kwargs)
    with TickClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset,workflow=frozen_workflow(client,symbol='NQ',point_value='20')
        assert dataset['tick_data']['records']>0
        job,_=run_oos(client,workflow)
        prefix='/api/campaign-workflows/'+workflow['id']+'/oos/monte-carlo'
        response=client.post(prefix+'/run',json={'job_id':job['id']});assert response.status_code==202,response.text
        wait(client,response.json()['id'])
        sources=client.get('/api/prop-sim/candidates').json()['items'];assert sources
        request=dict(body(sources[0]),automatic=True,maximum_funded_breach_probability=None)
        response=client.post('/api/prop-sim',json=request);assert response.status_code==202,response.text
        result=wait_automatic(client,response.json()['id'])
        assert all(p['stage']=='complete' for p in result['automation']['phases'].values()),result['automation']
        for phase in ('evaluation','funded'):
            assert result['phases'][phase]['status']=='complete'
            aid=result['phases'][phase]['analysis_id']
            saved=client.get('/api/prop-analyses/'+aid+'/downloads/report.json');assert saved.status_code==200
            assert 'ordered_trade_ticks' in saved.text


def test_chunk_boundaries_deleted_records_and_equal_timestamp_order(tmp_path,monkeypatch):
    import alphaquest.tick_data as ticks
    monkeypatch.setattr(ticks,'IMPORT_CHUNK_RECORDS',2)
    content=bytearray(raw([(0,100,1,0),(0,102,0,1),(0,99,1,0),(60,101,0,1),(60,103,0,1)]))
    # An all-zero deleted Sierra record in the middle must not change ordinals.
    content[96:96]=bytes(40)
    path=tmp_path/'ties.scid';path.write_bytes(content)
    store=DatasetStore(tmp_path/'datasets.sqlite3');ds=build(store,path,path.name,'Synthetic timestamp ties','NQ','UTC',SETTINGS)
    values=bars(store,ds)
    assert [r['price'] for r in values[0].tick_window.array()]==[100,102,99]
    assert values[0].tick_window.first==0 and values[0].tick_window.count==4
    assert values[1].tick_window.first==4 and values[1].flow.records==2
    assert ds['tick_data']['records']==5


def test_ordered_adverse_frontier_retains_each_first_crossing(tmp_path):
    from alphaquest.intratrade import RiskCapture
    from alphaquest.strategy import Position
    store,ds=save(tmp_path,[(0,100,1,0),(1,99,1,0),(2,101,0,1),(3,98,1,0),(4,97,1,0)])
    b=bars(store,ds)[0]
    risk=RiskCapture(Position(1,START,D(100),1),CONFIG,D(0),D(100),'open')
    b.tick_window.observe(risk,b)
    assert risk.adverse_path==[['20.0',True],['40.0',True],['60.0',True]]
    from alphaquest.prop.native_engine import risk_hit
    assert risk_hit([(float(v),g) for v,g in risk.adverse_path],0,10,-30,-100)==(1,-40)


def test_prepared_date_selection_preserves_flow_and_source_identity(tmp_path):
    from alphaquest.prepared_data import prepare_data
    from alphaquest.backtest_data import DateRange
    from datetime import date
    store,ds=save(tmp_path,[(0,100,1,2),(60,101,1,2),(86400,102,0,1)])
    prepared=prepare_data(store,ds['id'],DateRange(date(2026,1,5),date(2026,1,5)),tmp_path/'bars.bin')
    with prepared.selected() as selected:result=list(selected.bars)
    assert len(result)==2 and all(b.flow.records==1 for b in result)
    assert result[0].tick_window.source[1]==ds['tick_data']['sources'][0]['sha256']


@pytest.mark.parametrize('row',['2026-01-05T14:30:00Z,abc,1,0,1','2026-01-05T14:30:00Z,100,1,0','2026-01-05T14:30:00Z,100,1,0,1,EXTRA'])
def test_malformed_trade_csv_is_a_validation_error(tmp_path,row):
    from fastapi.testclient import TestClient
    from alphaquest.app import create_app
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        response=client.post('/api/datasets/ticks',params=dict(filename='bad.csv',name='Bad CSV'),content=('timestamp,price,volume,bid_volume,ask_volume\n'+row+'\n').encode())
        assert response.status_code==422,response.text
        assert client.get('/api/datasets').json()==[]


def test_raw_integrity_is_verified_before_cached_replay_or_iteration(tmp_path):
    from pathlib import Path
    store,ds=save(tmp_path,[(0,100,1,1)])
    with read_bars(store,ds['id']):pass
    path=Path(ds['tick_data']['sources'][0]['path']);raw=bytearray(path.read_bytes());raw[-1]^=1;path.write_bytes(raw)
    with pytest.raises(ValueError,match='checksum'):
        with read_bars(store,ds['id']):pass
