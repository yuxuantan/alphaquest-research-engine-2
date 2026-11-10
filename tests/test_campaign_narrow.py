"""Native IS Narrow grids, frozen Broad parameters and independent admission gates."""
import json
from hashlib import sha256

from fastapi.testclient import TestClient

from alphaquest.app import create_app
from test_research_workflow import client
from test_campaign_broad import broad_grid, selection, start_grid, wait_job
from test_campaign_mechanics import mechanics_csv, run_validation, checks


def dense_csv():
    """Labeled synthetic oracle: 120 observed IS days, six trades and 78 CU/day."""
    template = mechanics_csv().decode().splitlines()[1:-1]
    lines = ['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol',
             '01/01/2024,09:00,100,100,100,100,100,60,40']
    for year in (2024, 2025):
        for month in range(1, 13):
            for day in range(5, 10):
                for row in template:
                    lines.append(f'{month:02}/{day:02}/{year}' + row[row.index(','):])
    lines.extend(['12/31/2025,09:00,100,100,100,100,100,60,40',
                  '01/01/2026,09:00,900,900,900,900,100,60,40'])
    return ('\n'.join(lines)+'\n').encode()


def narrow_workflow(client):
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-narrow.csv',name='SYNTHETIC 120-day narrow oracle',symbol='SYNTHETIC',source_timezone='UTC',tick_size='.25',point_value='10'),content=dense_csv())
    assert response.status_code==201,response.text
    dataset=response.json()
    body=dict(dataset_id=dataset['id'],strategy_id='consecutive_green_hold',sample_split=dict(mode='dates',is_start='2024-01-01',is_end='2025-12-31',oos_start='2026-01-01',oos_end='2026-01-01'),execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1'))
    workflow=client.post('/api/campaign-workflows',json=body).json()
    result=run_validation(client,workflow);prefix='/api/campaign-workflows/'+workflow['id']
    review=client.patch(prefix+'/review',json=checks(result)).json()
    assert client.post(prefix+'/confirm',json={'revision':review['review']['revision']}).status_code==200
    broad=broad_grid(3,20,2)
    job,_=start_grid(client,prefix,broad)
    rows=client.get(prefix+'/broad/results').json()['items']
    assert [float(row['metrics']['total_net_pnl']) for row in rows]==[9360,18720]
    assert all(row['qualifies'] for row in rows)
    selected=selection(client,prefix,[1,2]).json()
    response=client.post(prefix+'/broad/confirm',json={'job_id':job['id'],'revision':selected['revision']})
    assert response.status_code==200,response.text
    return dataset,workflow,job


def narrow_grid(broad_trial):
    return dict(broad_trial=broad_trial,workers=1,parameter_ranges={
        'green_bar_count':dict(start=3,end=3,step=0),
        'hold_minutes':dict(start=20,end=21,step=1),
        'contracts':dict(start=broad_trial,end=broad_trial,step=0)})


def narrow_start(client,prefix,trial):
    body=narrow_grid(trial)
    response=client.post(prefix+'/narrow/preview',json=body)
    assert response.status_code==200,response.text
    preview=response.json();assert preview['total_trials']==2
    response=client.post(prefix+'/narrow/run',json=dict(body,revision=preview['revision'],preview_token=preview['preview_token']))
    assert response.status_code==202,response.text
    return wait_job(client,response.json()['id'])


def test_narrow_two_branches_real_evidence_selection_and_durability(client):
    dataset,workflow,broad=narrow_workflow(client);prefix='/api/campaign-workflows/'+workflow['id']
    # A Broad-varied input is locked even for a direct API request.
    bad=narrow_grid(1);bad['parameter_ranges']['contracts']=dict(start=1,end=2,step=1)
    assert client.post(prefix+'/narrow/preview',json=bad).status_code==409
    first=narrow_start(client,prefix,1)
    page=client.get(prefix+'/narrow/results',params={'broad_trial':1}).json()
    assert page['all_branches_complete'] is False
    assert not any(row['selectable'] for row in page['items'])
    state=client.get(prefix+'/narrow',params={'broad_trial':1}).json()['state']
    assert client.patch(prefix+'/narrow/selection',json=dict(broad_trial=1,job_id=first['id'],revision=state['revision'],trials=[1])).status_code==409
    second=narrow_start(client,prefix,2)
    assert client.get(prefix+'/phases/oos').status_code==409
    # A changed neighboring trial cannot be used to claim local stability.
    with client.app.state.runs.connect() as db:
        saved_row=db.execute('SELECT payload FROM optimization_trials WHERE optimization_id=? AND trial=2',(first['id'],)).fetchone()[0]
        tampered=json.loads(saved_row);tampered['metrics']['total_net_pnl']='999999'
        db.execute('UPDATE optimization_trials SET payload=? WHERE optimization_id=? AND trial=2',(json.dumps(tampered),first['id']))
    invalid=client.get(prefix+'/narrow/results',params={'broad_trial':1}).json()['items'][0]
    assert not invalid['qualifies'] and 'neighboring trial' in invalid['admission']['error']
    with client.app.state.runs.connect() as db:
        db.execute('UPDATE optimization_trials SET payload=? WHERE optimization_id=? AND trial=2',(saved_row,first['id']))
    for broad_trial,job in [(1,first),(2,second)]:
        page=client.get(prefix+'/narrow/results',params={'broad_trial':broad_trial}).json()
        assert page['all_branches_complete'] and page['family_size']==6
        assert page['total']==2
        for row in page['items']:
            assert row['parameters']['contracts']==broad_trial
            assert row['admission']['family_size']==6
            assert len(row['admission']['checks'])==9
            assert row['admission']['quarter_boundaries']==['2024-01-01','2024-07-01','2024-12-31','2025-07-02','2026-01-01']
            assert row['admission']['confidence']['observed_days']>=100
            if row['trial']==1:
                assert row['admission']['quarter_net_pnl']==[str(2340*broad_trial)+'.00']*4
                assert row['admission']['net_without_best_month']==str(8970*broad_trial)+'.00'
                assert row['admission']['neighbors']==dict(profitable=1,valid=1,fraction=1.0,passed=True)
                assert row['admission']['confidence']['lower_bound']>0
            record=client.get('/api/backtests/'+row['run_id']).json()
            assert record['run_metadata']['research']['workflow_phase']=='is_narrow'
            assert record['run_metadata']['research']['broad_trial']==broad_trial
            assert record['run_metadata']['selection']['from_date']=='2024-01-01'
            assert record['run_metadata']['selection']['to_date']=='2025-12-31'
            assert client.delete('/api/backtests/'+row['run_id']).status_code==409
            assert client.delete('/api/backtests/'+row['screening']['cost_stress']['run_id']).status_code==409
        assert client.delete('/api/backtests/batches/'+job['id']).status_code==409
    eligible=[r for r in client.get(prefix+'/narrow/results',params={'broad_trial':1}).json()['items'] if r['qualifies']]
    assert eligible,client.get(prefix+'/narrow/results',params={'broad_trial':1}).json()
    initial=client.get(prefix+'/narrow',params={'broad_trial':1}).json()['state']
    assert client.patch(prefix+'/narrow/selection',json=dict(broad_trial=1,job_id=first['id'],revision=initial['revision'],trials=[1,2,3])).status_code==422
    disqualified=[r['trial'] for r in client.get(prefix+'/narrow/results',params={'broad_trial':1}).json()['items'] if not r['qualifies']]
    if disqualified:
        assert client.patch(prefix+'/narrow/selection',json=dict(broad_trial=1,job_id=first['id'],revision=initial['revision'],trials=disqualified[:1])).status_code==409
    for trial,job in [(1,first),(2,second)]:
        page=client.get(prefix+'/narrow/results',params={'broad_trial':trial}).json()
        eligible=[r['trial'] for r in page['items'] if r['qualifies']]
        assert eligible
        state=client.get(prefix+'/narrow',params={'broad_trial':trial}).json()['state']
        response=client.patch(prefix+'/narrow/selection',json=dict(broad_trial=trial,job_id=job['id'],revision=state['revision'],trials=eligible[:2]))
        assert response.status_code==200,response.text
        state=response.json()
        response=client.post(prefix+'/narrow/confirm',json=dict(broad_trial=trial,job_id=job['id'],revision=state['revision']))
        assert response.status_code==200,response.text
        assert response.json()['confirmed_at_utc']
        assert client.patch(prefix+'/narrow/selection',json=dict(broad_trial=trial,job_id=job['id'],revision=state['revision'],trials=[])).status_code==409
    assert client.get(prefix+'/phases/oos').status_code==200
    package=client.get(prefix+'/narrow/download',params={'broad_trial':1}).json()
    before={p:sha256(p.read_bytes()).hexdigest() for p in client.app.state.runs.root.glob('*/*') if p.is_file()}
    with TestClient(create_app(client.app.state.store.path)) as reopened:
        assert reopened.get(prefix+'/phases/oos').status_code==200
        assert reopened.get(prefix+'/narrow/download',params={'broad_trial':1}).json()==package
        assert reopened.get('/api/jobs/backtest_batch/'+second['id']).json()['links'][0]['label']=='Open IS Narrow'
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}


def test_statistical_bound_counts_all_attempts_and_missing_evidence_fails():
    from datetime import date,timedelta
    from alphaquest.campaign_narrow import confidence,neighbor_check
    days=[(date(2024,1,1)+timedelta(days=i),10) for i in range(120)]
    assert confidence(days,6)['lower_bound']==10
    assert confidence(days[:20],6) is None
    axes={'a':[1,2,3]}
    rows=[{'parameters':{'a':i},'metrics':{'total_net_pnl':str(p)}} for i,p in [(1,10),(2,-1),(3,10)]]
    assert neighbor_check(rows[1],rows,axes)==dict(profitable=2,valid=2,fraction=1.0,passed=True)
    assert neighbor_check(rows[0],rows,axes)['passed'] is False
