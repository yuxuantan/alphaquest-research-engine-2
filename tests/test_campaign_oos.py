"""Native frozen OOS family execution and independent deterioration oracles."""
import json
import os
import time
from pathlib import Path
from decimal import Decimal as D
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from alphaquest.app import create_app
from test_research_workflow import client
from test_campaign_narrow import dense_csv,narrow_grid,narrow_start
from test_campaign_broad import broad_grid,start_grid,selection,wait_job
from test_campaign_mechanics import mechanics_csv,run_validation,checks


def oos_csv(degraded=False):
    lines=dense_csv().decode().splitlines()[:-1]
    lines.append('01/01/2026,09:00,100,100,100,100,100,60,40')
    template=mechanics_csv().decode().splitlines()[1:-1]
    for month in range(1,13):
        for day in range(5,10):
            for row in template:
                parts=row.split(',');parts[0]=f'{month:02}/{day:02}/2026'
                if degraded and parts[1].endswith(('23','26','27','22','25','24')):
                    # Six closes sum to 607.8: net 36 CU/day instead of 78.
                    hour=int(parts[1].split(':')[0]);close=['100.8','103','98','101','102','103'][hour-9]
                    parts[2:6]=[close]*4
                lines.append(','.join(parts))
    lines.append('12/31/2026,09:00,100,100,100,100,100,60,40')
    return ('\n'.join(lines)+'\n').encode()


def frozen_workflow(client, degraded=False):
    raw=oos_csv(degraded)
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-oos.csv',name='SYNTHETIC frozen OOS',symbol='SYNTHETIC',source_timezone='UTC',tick_size='.25',point_value='10'),content=raw)
    assert response.status_code==201,response.text
    dataset=response.json()
    body=dict(dataset_id=dataset['id'],strategy_id='consecutive_green_hold',sample_split=dict(mode='dates',is_start='2024-01-01',is_end='2025-12-31',oos_start='2026-01-01',oos_end='2026-12-31'),execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1'))
    workflow=client.post('/api/campaign-workflows',json=body).json();prefix='/api/campaign-workflows/'+workflow['id']
    result=run_validation(client,workflow);review=client.patch(prefix+'/review',json=checks(result)).json()
    assert client.post(prefix+'/confirm',json={'revision':review['review']['revision']}).status_code==200
    broad,_=start_grid(client,prefix,broad_grid(3,20,2))
    selected=selection(client,prefix,[1,2]).json()
    assert client.post(prefix+'/broad/confirm',json=dict(job_id=broad['id'],revision=selected['revision'])).status_code==200
    first=narrow_start(client,prefix,1)
    for trial in (1,2):
        if trial==2:
            grid=narrow_grid(2);grid['parameter_ranges']['green_bar_count']=dict(start=2,end=3,step=1)
            preview=client.post(prefix+'/narrow/preview',json=grid).json()
            launched=client.post(prefix+'/narrow/run',json=dict(grid,revision=preview['revision'],preview_token=preview['preview_token']))
            assert launched.status_code==202,launched.text
            job=wait_job(client,launched.json()['id'])
        else:job=first
        state=client.get(prefix+'/narrow',params={'broad_trial':trial}).json()['state']
        selected=client.patch(prefix+'/narrow/selection',json=dict(broad_trial=trial,job_id=job['id'],revision=state['revision'],trials=[2,3] if trial==1 else [5,8]))
        assert selected.status_code==200,selected.text
        response=client.post(prefix+'/narrow/confirm',json=dict(broad_trial=trial,job_id=job['id'],revision=selected.json()['revision']))
        assert response.status_code==200,response.text
    return dataset,client.get(prefix).json()


def run_oos(client, workflow, workers=1):
    prefix='/api/campaign-workflows/'+workflow['id']+'/oos'
    body=dict(request_id=str(uuid4()),workers=workers)
    response=client.post(prefix+'/run',json=body)
    assert response.status_code==202,response.text
    job=wait_job(client,response.json()['id'],timeout=120)
    return job,body


@pytest.mark.parametrize('degraded',[False,True])
def test_native_oos_exact_frozen_membership_measurements_and_history(client,degraded):
    dataset,workflow=frozen_workflow(client,degraded)
    prefix='/api/campaign-workflows/'+workflow['id'];family=[x for branch in workflow['narrow'] for x in branch['selection']]
    before={p:sha256(p.read_bytes()).hexdigest() for c in family for p in (client.app.state.runs.root/c['run_id']).iterdir() if p.is_file()}
    job,body=run_oos(client,workflow,workers=4)
    assert job['total_trials']==4 and len(job['candidate_parameters'])==4
    assert len(job['axes']['hold_minutes'])*len(job['axes']['contracts'])==8
    assert client.post(prefix+'/oos/run',json=body).json()['id']==job['id']
    page=client.get(prefix+'/oos/results').json()
    assert len(page['items'])==4 and page['passed']==(0 if degraded else 4)
    assert [i['parameters'] for i in page['items']]==[c['parameters'] for c in family]
    for item in page['items']:
        quantity=item['parameters']['contracts']
        assert D(item['metrics']['total_net_pnl'])==D(2160 if degraded else 4680)*quantity
        assert D(item['metrics']['oos_stress_net_profit'])==D(360 if degraded else 2880)*quantity
        assert len(item['admission']['checks'])==7
        assert item['metrics']['oos_history_months']==12
        assert item['qualifies'] is (not degraded)
        native=client.get('/api/backtests/'+item['run_id']).json()
        assert native['run_metadata']['research']['phase']=='oos'
        assert native['run_metadata']['selection']['from_date']=='2026-01-01'
        assert native['run_metadata']['selection']['to_date']=='2026-12-31'
        assert native['run_metadata']['research']['parent_run_id']==item['is_run_id']
        assert client.get('/api/backtests/'+item['run_id']+'/exports/oos_screening').status_code==200
        assert client.delete('/api/backtests/'+item['run_id']).status_code==409
    assert client.delete('/api/backtests/batches/'+job['id']).status_code==409
    status=client.get(prefix).json()
    assert status['phases'][-1]['status']==('not_qualified' if degraded else 'passed')
    assert status['narrow']==workflow['narrow']
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}

    assert client.get('/api/jobs/backtest_batch/'+job['id']).json()['links'][0]['label']=='Open OOS'
    history=client.app.state.research.status(dataset,'consecutive_green_hold')
    assert history['used']==4 and all(a['status']=='complete' for a in history['attempts'])
    package=client.get(prefix+'/oos/download').json()
    assert package['job']['research']['prior_oos_attempts']==0
    assert client.get(prefix+'/oos/download?format=csv').status_code==200
    assert client.post(prefix+'/oos/run',json=dict(body,parameters={'contracts':99})).status_code==422
    # Verdict and native sidecar corruption cannot silently retain qualification.
    with client.app.state.runs.connect() as db:
        original=db.execute('SELECT payload FROM optimization_trials WHERE optimization_id=? AND trial=1',(job['id'],)).fetchone()[0]
        changed=json.loads(original);changed['oos_admission']['qualifies']=not changed['oos_admission']['qualifies']
        db.execute('UPDATE optimization_trials SET payload=? WHERE optimization_id=? AND trial=1',(json.dumps(changed),job['id']))
    assert client.get(prefix+'/oos/results').json()['items'][0]['status']=='unavailable'
    with client.app.state.runs.connect() as db:
        db.execute('UPDATE optimization_trials SET payload=? WHERE optimization_id=? AND trial=1',(original,job['id']))
    path=client.app.state.runs.root/page['items'][0]['run_id']/'oos_screening.json'
    original_bytes=path.read_bytes();path.write_text('{}')
    assert client.get(prefix+'/oos/results').json()['items'][0]['status']=='unavailable'
    assert client.get('/api/backtests/'+page['items'][0]['run_id']+'/exports/oos_screening').status_code==409
    path.write_bytes(original_bytes)
    if not degraded:
        repeated,_=run_oos(client,workflow,workers=1)
        assert repeated['id']!=job['id'] and repeated['research']['prior_oos_attempts']==4
        assert repeated['research']['prior_access']['untouched_certificate'] is False
        assert client.get(prefix+'/oos/download?job='+job['id']).json()==package
        assert len(client.get(prefix+'/oos').json()['history'])==2
    if degraded and (destination:=os.environ.get('ALPHAQUEST_OOS_EVIDENCE_DIR')):
        folder=Path(destination)/'degraded';folder.mkdir(parents=True,exist_ok=True)
        (folder/'SYNTHETIC-source.csv').write_bytes(oos_csv(True))
        (folder/'oos-assessment.json').write_text(json.dumps(package,indent=2))
        (folder/'journey.json').write_text(json.dumps(dict(workflow_id=workflow['id'],job_id=job['id'],
            expected_oos_net=[2160,2160,4320,4320],expected_stressed_net=[360,360,720,720],
            expected_passed=0,expected_profit_per_trade_retention_pct='46.15384615384615384615384615',synthetic=True,
            server='Stopped by TestClient teardown.'),indent=2))
        for name,id in [('is',page['items'][0]['is_run_id']),('oos',page['items'][0]['run_id']),('stress',page['items'][0]['cost_stress_run_id'])]:
            native=client.get('/api/backtests/'+id).json()
            for kind in ('report','trades','equity'):
                suffix=native['artifacts']['report'] if kind=='report' else kind+'.csv'
                (folder/(name+'-'+suffix)).write_bytes(client.get('/api/backtests/'+id+'/exports/'+kind).content)
    with TestClient(create_app(client.app.state.store.path)) as reopened:
        assert reopened.get(prefix+'/oos/download?job='+job['id']).json()==package
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}


def test_oos_is_locked_before_narrow_confirmation(client):
    from test_campaign_narrow import narrow_workflow
    _,workflow,_=narrow_workflow(client)
    prefix='/api/campaign-workflows/'+workflow['id']+'/oos'
    assert client.get(prefix).status_code==409
    assert client.post(prefix+'/run',json=dict(request_id=str(uuid4()))).status_code==409


def test_stopped_oos_resumes_remaining_frozen_candidates(client,monkeypatch):
    _,workflow=frozen_workflow(client)
    prefix='/api/campaign-workflows/'+workflow['id']+'/oos'
    store=client.app.state.optimizations;original=store.publish
    def publish_then_stop(job_id,trial,*args):
        result=original(job_id,trial,*args)
        if trial==1:store.request_stop(job_id)
        return result
    monkeypatch.setattr(store,'publish',publish_then_stop)
    response=client.post(prefix+'/run',json=dict(request_id=str(uuid4()),workers=1));assert response.status_code==202,response.text
    job=response.json();deadline=time.monotonic()+90
    while True:
        stopped=store.get(job['id'])
        if stopped['status'] not in ('queued','running'):break
        assert time.monotonic()<deadline;time.sleep(.02)
    assert stopped['status']=='cancelled' and stopped['completed_trials']==1
    assert client.post('/api/backtests/batches/'+job['id']+'/cancel').status_code==200
    first=client.get(prefix+'/results').json()['items'][0]
    assert first['qualifies']
    saved=client.app.state.runs.root/first['run_id']/'report.json'
    original_hash=sha256(saved.read_bytes()).hexdigest()
    monkeypatch.setattr(store,'publish',original)
    resumed=client.post(prefix+'/jobs/'+job['id']+'/resume')
    assert resumed.status_code==200,resumed.text
    done=wait_job(client,job['id'],timeout=120)
    assert done['completed_trials']==4 and len(done['previous_attempts'])==1
    assert client.get(prefix+'/results').json()['passed']==4
    assert sha256(saved.read_bytes()).hexdigest()==original_hash
