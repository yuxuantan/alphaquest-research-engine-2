"""Native IS Narrow grids, frozen Broad parameters and independent admission gates."""
import json
from hashlib import sha256
import pytest

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


def narrow_workflow(client, *, refinement=False):
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-narrow.csv',name='SYNTHETIC 120-day narrow oracle',symbol='SYNTHETIC',source_timezone='UTC',tick_size='.25',point_value='10'),content=dense_csv())
    assert response.status_code==201,response.text
    dataset=response.json()
    body=dict(dataset_id=dataset['id'],strategy_id='consecutive_green_hold',sample_split=dict(mode='dates',is_start='2024-01-01',is_end='2025-12-31',oos_start='2026-01-01',oos_end='2026-01-01'),execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1'))
    workflow=client.post('/api/campaign-workflows',json=body).json()
    result=run_validation(client,workflow);prefix='/api/campaign-workflows/'+workflow['id']
    review=client.patch(prefix+'/review',json=checks(result)).json()
    assert client.post(prefix+'/confirm',json={'revision':review['review']['revision']}).status_code==200
    broad=broad_grid(3,40,1) if refinement else broad_grid(3,20,2)
    job,_=start_grid(client,prefix,broad)
    rows=client.get(prefix+'/broad/results').json()['items']
    if refinement:
        assert float(rows[0]['metrics']['total_net_pnl'])==9360
        assert rows[0]['qualifies']
    else:
        assert [float(row['metrics']['total_net_pnl']) for row in rows]==[9360,18720]
        assert all(row['qualifies'] for row in rows)
    selected=selection(client,prefix,[1] if refinement else [1,2]).json()
    response=client.post(prefix+'/broad/confirm',json={'job_id':job['id'],'revision':selected['revision']})
    assert response.status_code==200,response.text
    return dataset,workflow,job


def narrow_grid(broad_trial):
    return dict(broad_trial=broad_trial,workers=1,parameter_ranges={
        'green_bar_count':dict(start=3,end=3,step=0),
        'hold_minutes':dict(start=14,end=20,step=2),
        'contracts':dict(start=broad_trial,end=broad_trial,step=0)})


def narrow_start(client,prefix,trial):
    body=narrow_grid(trial)
    response=client.post(prefix+'/narrow/preview',json=body)
    assert response.status_code==200,response.text
    preview=response.json();assert preview['total_trials']==4
    response=client.post(prefix+'/narrow/run',json=dict(body,revision=preview['revision'],preview_token=preview['preview_token']))
    assert response.status_code==202,response.text
    return wait_job(client,response.json()['id'],timeout=60)


def test_narrow_two_branches_real_evidence_selection_and_durability(client, monkeypatch):
    dataset,workflow,broad=narrow_workflow(client);prefix='/api/campaign-workflows/'+workflow['id']
    # A Broad-varied input is locked even for a direct API request.
    bad=narrow_grid(1);bad['parameter_ranges']['contracts']=dict(start=1,end=2,step=1)
    assert client.post(prefix+'/narrow/preview',json=bad).status_code==409
    too_sparse=narrow_grid(1);too_sparse['parameter_ranges']['hold_minutes']=dict(start=17,end=18,step=1)
    rejected=client.post(prefix+'/narrow/preview',json=too_sparse)
    assert rejected.status_code==409 and 'at least two distinct ordered-numeric neighbors' in rejected.text
    first=narrow_start(client,prefix,1)
    page=client.get(prefix+'/narrow/results',params={'broad_trial':1}).json()
    assert page['all_branches_complete'] is False
    assert page['family_size']==6
    assert [row['trial'] for row in page['items'] if row['selectable']]==[2,3]
    state=client.get(prefix+'/narrow',params={'broad_trial':1}).json()['state']
    assert client.patch(prefix+'/narrow/selection',json=dict(broad_trial=1,job_id=first['id'],revision=state['revision'],trials=[1])).status_code==409
    assert client.patch(prefix+'/narrow/selection',json=dict(broad_trial=1,job_id=first['id'],revision=state['revision'],trials=[1,2,3])).status_code==422
    from alphaquest import campaign_narrow
    with monkeypatch.context() as patch:
        # This diagnostic injection deliberately bypasses the disposable display cache.
        patch.setattr(client.app.state.runs,'replay_cache',None)
        patch.setattr(campaign_narrow,'confidence',lambda days,family: {'lower_bound':-1,'observed_days':len(days)})
        advisory=client.get(prefix+'/narrow/results',params={'broad_trial':1}).json()['items']
        assert [row['trial'] for row in advisory if row['qualifies']]==[2,3]
        assert all('-1.0000 CU/day' in row['admission']['observations'][-1]['actual'] for row in advisory)
    selected=client.patch(prefix+'/narrow/selection',json=dict(broad_trial=1,job_id=first['id'],revision=state['revision'],trials=[2,3]))
    assert selected.status_code==200,selected.text
    confirmed=client.post(prefix+'/narrow/confirm',json=dict(broad_trial=1,job_id=first['id'],revision=selected.json()['revision']))
    assert confirmed.status_code==200,confirmed.text
    assert confirmed.json()['family_size']==6 and len(confirmed.json()['selection'])==2
    first_package=client.get(prefix+'/narrow/download',params={'broad_trial':1}).json()
    assert client.patch(prefix+'/narrow/selection',json=dict(broad_trial=1,job_id=first['id'],revision=confirmed.json()['revision'],trials=[])).status_code==409
    assert client.get(prefix+'/phases/oos').status_code==409
    second=narrow_start(client,prefix,2)
    assert client.get(prefix+'/narrow/download',params={'broad_trial':1}).json()==first_package
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
        assert page['all_branches_complete'] and page['family_size']==(6 if broad_trial==1 else 10)
        assert page['total']==4
        for row in page['items']:
            assert row['parameters']['contracts']==broad_trial
            assert row['admission']['family_size']==(6 if broad_trial==1 else 10)
            assert len(row['admission']['checks'])==7
            assert len(row['admission']['observations'])==4
            assert all(row['admission']['period_observed_dates'])
            assert row['admission']['quarter_boundaries']==['2024-01-01','2024-07-01','2024-12-31','2025-07-02','2026-01-01']
            assert row['admission']['confidence']['observed_days']>=100
            if row['trial']==1:
                assert row['admission']['quarter_net_pnl']==[str(2340*broad_trial)+'.00']*4
                assert row['admission']['net_without_best_month']==str(8970*broad_trial)+'.00'
                assert row['admission']['neighbors']==dict(profitable=1,valid=1,fraction=1.0,passed=False)
                assert row['admission']['confidence']['lower_bound']>0
            record=client.get('/api/backtests/'+row['run_id']).json()
            assert record['run_metadata']['research']['workflow_phase']=='is_narrow'
            assert record['run_metadata']['research']['broad_trial']==broad_trial
            assert record['run_metadata']['selection']['from_date']=='2024-01-01'
            assert record['run_metadata']['selection']['to_date']=='2025-12-31'
            assert client.delete('/api/backtests/'+row['run_id']).status_code==409
            assert client.delete('/api/backtests/'+row['screening']['cost_stress']['run_id']).status_code==409
        assert client.delete('/api/backtests/batches/'+job['id']).status_code==409
    for trial,job in [(2,second)]:
        page=client.get(prefix+'/narrow/results',params={'broad_trial':trial}).json()
        eligible=[r['trial'] for r in page['items'] if r['qualifies']]
        assert len(eligible)==2
        state=client.get(prefix+'/narrow',params={'broad_trial':trial}).json()['state']
        response=client.patch(prefix+'/narrow/selection',json=dict(broad_trial=trial,job_id=job['id'],revision=state['revision'],trials=eligible[:2]))
        assert response.status_code==200,response.text
        state=response.json()
        response=client.post(prefix+'/narrow/confirm',json=dict(broad_trial=trial,job_id=job['id'],revision=state['revision']))
        assert response.status_code==200,response.text
        assert response.json()['confirmed_at_utc'] and len(response.json()['selection'])==2
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


def test_previous_numeric_neighborhood_excludes_categorical_axes_and_one_neighbor():
    from alphaquest.campaign_narrow import PREVIOUS_POLICY as POLICY, neighbor_check
    fields=[dict(name='length',type='int'),dict(name='mode',type='int',refinement_kind='categorical')]
    axes=dict(length=[3,4,5],mode=[1,2])
    rows=[dict(parameters=dict(length=length,mode=mode),metrics=dict(total_net_pnl='10'))
          for length in axes['length'] for mode in axes['mode']]
    center=next(row for row in rows if row['parameters']==dict(length=4,mode=1))
    edge=next(row for row in rows if row['parameters']==dict(length=3,mode=1))
    assert neighbor_check(center,rows,axes,target_policy=POLICY,fields=fields)==dict(
        profitable=2,valid=2,fraction=1.0,passed=True)
    assert neighbor_check(edge,rows,axes,target_policy=POLICY,fields=fields)==dict(
        profitable=1,valid=1,fraction=1.0,passed=False)
    rows[3]['metrics']['total_net_pnl']='-100'
    assert neighbor_check(center,rows,axes,target_policy=POLICY,fields=fields)['passed']
    numeric_fields=[dict(name='length',type='int'),dict(name='mode',type='int')]
    assert neighbor_check(center,rows,axes,target_policy=POLICY,fields=numeric_fields)==dict(
        profitable=2,valid=3,fraction=2/3,passed=True)


@pytest.mark.parametrize('version', ['is-narrow-v1', 'is-narrow-v2', 'is-narrow-v3'])
def test_confirmed_older_narrow_selection_keeps_its_original_admission(client, version):
    from types import SimpleNamespace
    from alphaquest.campaign_narrow import (LEGACY_POLICY, PREVIOUS_POLICY, FINE_GRID_POLICY, NarrowGrid, branches, chosen_candidate,
                                            family_size, period_boundaries, prepare)
    from alphaquest.optimization_cache import digest
    from alphaquest.research import metadata, dates_for
    from alphaquest.workflow_criteria import DRAWDOWN_VERSION, policy
    _,workflow,_=narrow_workflow(client,refinement=True)
    original_policy={'is-narrow-v1':LEGACY_POLICY,'is-narrow-v2':PREVIOUS_POLICY,'is-narrow-v3':FINE_GRID_POLICY}[version]
    prefix='/api/campaign-workflows/'+workflow['id']
    body=NarrowGrid.model_validate(dict(broad_trial=1,workers=1,parameter_ranges={
        'green_bar_count':dict(start=3,end=3,step=0),
        'hold_minutes':dict(start=18,end=20,step=1),
        'contracts':dict(start=1,end=1,step=0)},refine_broad_parameters=['hold_minutes']))
    saved,dataset,definition,config,axes,total,request,_,current,fixed=prepare(
        SimpleNamespace(app=client.app),workflow['id'],body)
    research=metadata(saved['declaration']['plan'],workflow_id=workflow['id'],
        workflow_phase='is_narrow',broad_trial=1,
        broad_selection_identity=digest(current['broad_selection']),
        screening_policy=policy(DRAWDOWN_VERSION),narrow_policy=original_policy,
        period_boundaries=[day.isoformat() for day in period_boundaries(saved['declaration']['plan'])],
        frozen_broad_parameters={name:current['broad_selection']['parameters'][name] for name in fixed})
    if version=='is-narrow-v3':
        research['plateau_steps']={'hold_minutes':'1'}
    job=client.app.state.optimizations.create(request,dataset,definition,config,axes,total,research)
    client.app.state.optimizations.run(job,client.app.state.store,definition,config,
                                        dates_for(saved['declaration']['plan']))
    state=dict(broad_trial=1,job_id=job['id'],revision=1,selected_trials=[],selection=[],
               confirmed_at_utc='2026-11-10T00:00:00+00:00',
               broad_selection_identity=research['broad_selection_identity'],policy=original_policy)
    with client.app.state.runs.connect() as db:
        db.execute('INSERT INTO campaign_narrow_jobs VALUES (?,?,?)',(job['id'],workflow['id'],1))
        db.execute('INSERT INTO campaign_narrow_state VALUES (?,?,?)',(workflow['id'],1,json.dumps(state)))
        frozen=chosen_candidate(client.app.state.campaign_workflows,workflow['id'],
                                branches(client.app.state.campaign_workflows,workflow['id'],db)[0],2,db,
                                family_size(db,workflow['id']))
        assert frozen['admission']['policy']==original_policy
        assert len(frozen['admission']['checks'])==(9 if version=='is-narrow-v1' else 7)
        if version=='is-narrow-v3':
            assert frozen['admission']['plateau']['passed']
            assert frozen['admission']['checks'][-2]['label']=='Fine-grid parameter plateau'
        else:
            assert 'plateau' not in frozen['admission']
        state.update(selected_trials=[2],selection=[frozen],family_size=family_size(db,workflow['id']))
        db.execute('UPDATE campaign_narrow_state SET payload=? WHERE workflow_id=? AND broad_trial=1',
                   (json.dumps(state),workflow['id']))
    assert client.get(prefix+'/phases/oos').status_code==200
    result=client.get(prefix+'/narrow/results',params={'broad_trial':1}).json()
    assert result['source_policy']==result['selection_policy']==original_policy
    assert result['items'][1]['admission']==frozen['admission']|{'provisional':False}
    assert client.get(prefix+'/narrow/download',params={'broad_trial':1}).json()['policy']==original_policy


def test_refinement_eligibility_uses_numeric_spacing_without_campaign_declarations():
    from alphaquest.campaign_narrow import refinement_options,validate_refinement
    from alphaquest.strategies.registry import get_strategy
    fields=get_strategy('vwap_pullback_risk_sizing').description()['parameters']
    axes={field['name']:[field['default']] for field in fields}
    axes.update(stop_swing_len=[5,20],target_swing_len=[5,20],retest_mode=[1,2])
    choices=refinement_options(fields,axes)
    assert choices['stop_swing_len']=={'type':'int','broad_min_step':'15'}
    assert choices['target_swing_len']=={'type':'int','broad_min_step':'15'}
    assert 'retest_mode' not in choices
    fields=[dict(field,refinement_kind='categorical') if field['name']=='stop_swing_len' else field for field in fields]
    assert 'stop_swing_len' not in refinement_options(fields,axes)
    decimal_fields=[{'name':'threshold','type':'Decimal'}]
    assert refinement_options(decimal_fields,{'threshold':['0.5','1.5']})=={'threshold':{'type':'Decimal','broad_min_step':'1.0'}}
    assert validate_refinement(decimal_fields,{'threshold':['0.5','1.5']},{'threshold':'0.5'},
                               {'threshold':['0.4','0.5','0.6']},['threshold'])==[]


def test_refined_broad_value_runs_native_narrow_grid_and_freezes_choice(client):
    dataset,workflow,broad=narrow_workflow(client,refinement=True)
    prefix='/api/campaign-workflows/'+workflow['id']
    detail=client.get(prefix+'/narrow',params={'broad_trial':1}).json()
    assert detail['fixed_parameters']==['hold_minutes']
    assert detail['refinable_parameters']['hold_minutes']=={'type':'int','broad_min_step':'20'}
    body=dict(broad_trial=1,workers=1,parameter_ranges={
        'green_bar_count':dict(start=3,end=3,step=0),
        'hold_minutes':dict(start=18,end=21,step=1),
        'contracts':dict(start=1,end=1,step=0)})
    def rejected(request):
        result=client.post(prefix+'/narrow/preview',json=request)
        assert result.status_code==409,result.text
    rejected(body)  # Default lock applies at the API, not only in the form.
    rejected(dict(body,refine_broad_parameters=['contracts']))
    rejected(dict(body,refine_broad_parameters=['hold_minutes','hold_minutes']))
    coarse=json.loads(json.dumps(body));coarse['parameter_ranges']['hold_minutes']=dict(start=20,end=40,step=20)
    rejected(dict(coarse,refine_broad_parameters=['hold_minutes']))
    far=json.loads(json.dumps(body));far['parameter_ranges']['hold_minutes']=dict(start=19,end=30,step=1)
    rejected(dict(far,refine_broad_parameters=['hold_minutes']))
    omitted=json.loads(json.dumps(body));omitted['parameter_ranges']['hold_minutes']=dict(start=18,end=19,step=1)
    rejected(dict(omitted,refine_broad_parameters=['hold_minutes']))
    body['refine_broad_parameters']=['hold_minutes']
    response=client.post(prefix+'/narrow/preview',json=body)
    assert response.status_code==200,response.text
    preview=response.json()
    assert preview['total_trials']==4 and preview['fixed_parameters']==[]
    assert preview['refined_parameters']==['hold_minutes']
    changed=dict(body,refine_broad_parameters=[])
    assert client.post(prefix+'/narrow/run',json=dict(changed,revision=preview['revision'],preview_token=preview['preview_token'])).status_code==409
    launched=client.post(prefix+'/narrow/run',json=dict(body,revision=preview['revision'],preview_token=preview['preview_token']))
    assert launched.status_code==202,launched.text
    job=wait_job(client,launched.json()['id'])
    assert job['axes']['hold_minutes']==[18,19,20,21]
    assert job['research']['refined_broad_parameters']==['hold_minutes']
    assert job['research']['broad_anchor_parameters']['hold_minutes']==20
    assert job['research']['frozen_broad_parameters']=={}
    page=client.get(prefix+'/narrow/results',params={'broad_trial':1}).json()
    assert page['family_size']==6 and page['all_branches_complete']
    assert [row['parameters']['hold_minutes'] for row in page['items']]==[18,19,20,21]
    eligible=[row for row in page['items'] if row['qualifies']]
    assert eligible,page
    assert [row['parameters']['hold_minutes'] for row in eligible]==[19]
    assert page['items'][2]['admission']['plateau']['status']=='failed'
    for row in page['items']:
        report=client.get('/api/backtests/'+row['run_id']).json()
        assert report['run_metadata']['research']['refined_broad_parameters']==['hold_minutes']
        assert report['run_metadata']['research']['broad_anchor_parameters']['hold_minutes']==20
    state=client.get(prefix+'/narrow',params={'broad_trial':1}).json()['state']
    selected=client.patch(prefix+'/narrow/selection',json=dict(broad_trial=1,job_id=job['id'],revision=state['revision'],trials=[eligible[0]['trial']]))
    assert selected.status_code==200,selected.text
    confirmed=client.post(prefix+'/narrow/confirm',json=dict(broad_trial=1,job_id=job['id'],revision=selected.json()['revision']))
    assert confirmed.status_code==200,confirmed.text
    assert client.get(prefix+'/phases/oos').status_code==200
    package=client.get(prefix+'/narrow/download',params={'broad_trial':1}).json()
    with client.app.state.runs.connect() as db:
        original=db.execute('SELECT payload FROM campaign_narrow_state WHERE workflow_id=? AND broad_trial=1',(workflow['id'],)).fetchone()[0]
        altered=json.loads(original);altered['refined_broad_parameters']=[]
        db.execute('UPDATE campaign_narrow_state SET payload=? WHERE workflow_id=? AND broad_trial=1',(json.dumps(altered),workflow['id']))
    assert client.get(prefix+'/phases/oos').status_code==409
    with client.app.state.runs.connect() as db:
        db.execute('UPDATE campaign_narrow_state SET payload=? WHERE workflow_id=? AND broad_trial=1',(original,workflow['id']))
    with TestClient(create_app(client.app.state.store.path)) as reopened:
        assert reopened.get(prefix+'/phases/oos').status_code==200
        assert reopened.get(prefix+'/narrow/download',params={'broad_trial':1}).json()==package


def test_plateau_requires_both_sides_retention_and_stressed_neighbor_profit():
    from decimal import Decimal
    from alphaquest.campaign_narrow import fine_plateau_check as plateau_check
    fields=[dict(name='stop',type='int'),dict(name='target',type='int'),
            dict(name='mode',type='int',refinement_kind='categorical')]
    axes=dict(stop=[3,4,5],target=[9,10,11],mode=[1,2])
    # Only one coordinate changes at a time. Diagonal/categorical losses cannot
    # be passed off as nearby numeric evidence or included in a local average.
    rows=[]
    for stop in axes['stop']:
        for target in axes['target']:
            for mode in axes['mode']:
                net='100' if mode==1 and (stop==4 or target==10) else '-100'
                rows.append(dict(trial=len(rows)+1,run_id=str(len(rows)),parameters=dict(stop=stop,target=target,mode=mode),
                                 metrics=dict(total_net_pnl=net),screening=dict(metrics=dict(is_stress_net_profit='1'))))
    center=next(row for row in rows if row['parameters']==dict(stop=4,target=10,mode=1))
    neighbor=next(row for row in rows if row['parameters']==dict(stop=3,target=10,mode=1))
    neighbor['metrics']['total_net_pnl']='70'
    result=plateau_check(center,rows,axes,fields)
    assert result['passed'] and result['required_neighbors']==result['tested_neighbors']==4
    assert Decimal(result['minimum_retention_pct'])==70
    assert Decimal(result['lowest_neighbor_profit'])==70
    assert {entry['parameter'] for entry in result['neighbors']}=={'stop','target'}
    # Admission compares unrounded decimals, including the exact 70% boundary.
    neighbor['metrics']['total_net_pnl']='69.99999999999999999999999999999'
    assert plateau_check(center,rows,axes,fields)['status']=='failed'
    neighbor['metrics']['total_net_pnl']='70'
    neighbor['screening']['metrics']['is_stress_net_profit']='0'
    assert not plateau_check(center,rows,axes,fields)['passed']
    neighbor['screening']['metrics']['is_stress_net_profit']='1'
    edge=plateau_check(neighbor,rows,axes,fields)
    assert edge['status']=='insufficient_evidence' and edge['missing_neighbors']==1
    with pytest.raises(ValueError,match='neighbor is missing'):
        plateau_check(center,[row for row in rows if row is not neighbor],axes,fields)


def test_plateau_local_steps_are_explicit_and_coarse_grids_are_not_interpolated():
    from alphaquest.campaign_narrow import local_steps,fine_plateau_check as plateau_check
    fields=[dict(name='length',type='int')]
    axes=dict(length=[5,10,15])
    rows=[dict(trial=i,run_id=str(i),parameters=dict(length=value),metrics=dict(total_net_pnl='100'),
               screening=dict(metrics=dict(is_stress_net_profit='50'))) for i,value in enumerate(axes['length'],1)]
    assert plateau_check(rows[1],rows,axes,fields)['missing_neighbors']==2
    assert plateau_check(rows[1],rows,axes,fields,{'length':'5'})['passed']
    for invalid in ('0','-1','0.5','NaN','Infinity','1e999999999','bad'):
        with pytest.raises(ValueError):
            local_steps(fields,axes,{'length':invalid})
    with pytest.raises(ValueError,match='only for varied ordered-numeric'):
        local_steps(fields,axes,{'other':'1'})
    decimal_fields=[dict(name='length',type='Decimal')]
    decimal_axes=dict(length=['0.1','0.2','0.3'])
    decimal_rows=[dict(row,parameters=dict(length=value)) for row,value in zip(rows,decimal_axes['length'])]
    assert local_steps(decimal_fields,decimal_axes)=={'length':'0.1'}
    assert plateau_check(decimal_rows[1],decimal_rows,decimal_axes,decimal_fields)['passed']
    assert plateau_check(decimal_rows[1],decimal_rows,decimal_axes,decimal_fields,{'length':'0.01'})['status']=='insufficient_evidence'


@pytest.mark.parametrize('source_version', ['is-narrow-v2', 'is-narrow-v3'])
def test_old_coarse_grid_is_reassessed_without_backtests_or_report_changes(client, monkeypatch, source_version):
    from types import SimpleNamespace
    from alphaquest.campaign_narrow import PREVIOUS_POLICY,FINE_GRID_POLICY,POLICY,NarrowGrid,prepare,period_boundaries
    from alphaquest.optimization_cache import digest
    from alphaquest.research import metadata,dates_for
    from alphaquest.workflow_criteria import policy
    _,workflow,_=narrow_workflow(client)
    prefix='/api/campaign-workflows/'+workflow['id']
    body=narrow_grid(1)
    preview=client.post(prefix+'/narrow/preview',json=body)
    assert preview.status_code==200,preview.text
    assert 'plateau_steps' not in preview.json()
    saved,dataset,definition,config,axes,total,request,_,current,fixed=prepare(
        SimpleNamespace(app=client.app),workflow['id'],NarrowGrid.model_validate(body))
    source_policy=PREVIOUS_POLICY if source_version=='is-narrow-v2' else FINE_GRID_POLICY
    research=metadata(saved['declaration']['plan'],workflow_id=workflow['id'],workflow_phase='is_narrow',
        broad_trial=1,broad_selection_identity=digest(current['broad_selection']),
        screening_policy=policy(),narrow_policy=source_policy,
        period_boundaries=[day.isoformat() for day in period_boundaries(saved['declaration']['plan'])],
        frozen_broad_parameters={name:current['broad_selection']['parameters'][name] for name in fixed})
    if source_version=='is-narrow-v3':
        research['plateau_steps']={'hold_minutes':'2'}
    old=client.app.state.optimizations.create(request,dataset,definition,config,axes,total,research)
    client.app.state.optimizations.run(old,client.app.state.store,definition,config,dates_for(saved['declaration']['plan']))
    state=dict(broad_trial=1,job_id=old['id'],revision=1,selected_trials=[],selection=[],confirmed_at_utc=None,
               broad_selection_identity=research['broad_selection_identity'],policy=source_policy,selection_policy=source_policy)
    with client.app.state.runs.connect() as db:
        db.execute('INSERT INTO campaign_narrow_jobs VALUES (?,?,?)',(old['id'],workflow['id'],1))
        db.execute('INSERT INTO campaign_narrow_state VALUES (?,?,?)',(workflow['id'],1,json.dumps(state)))
        job_count=db.execute('SELECT COUNT(*) FROM optimizations').fetchone()[0]
    before={path:sha256(path.read_bytes()).hexdigest() for path in client.app.state.runs.root.glob('*/*') if path.is_file()}
    def no_new_backtests(*args,**kwargs):
        raise AssertionError('Saved-grid plateau assessment must not launch another backtest')
    monkeypatch.setattr(client.app.state.optimizations,'create',no_new_backtests)
    monkeypatch.setattr(client.app.state.optimizations,'run',no_new_backtests)
    page=client.get(prefix+'/narrow/results',params={'broad_trial':1}).json()
    assert page['source_policy']==source_policy and page['selection_policy']==POLICY
    assert [row['trial'] for row in page['items'] if row['qualifies']]==[2,3]
    assert all(row['admission']['plateau']['grid_steps']=={'hold_minutes':['2']} for row in page['items'])
    assert page['items'][0]['admission']['plateau']['one_sided']
    selected=client.patch(prefix+'/narrow/selection',json=dict(broad_trial=1,job_id=old['id'],revision=1,trials=[2,3]))
    assert selected.status_code==200,selected.text
    confirm=client.post(prefix+'/narrow/confirm',json=dict(broad_trial=1,job_id=old['id'],revision=selected.json()['revision']))
    assert confirm.status_code==200,confirm.text
    assert confirm.json()['selection_policy']==POLICY
    assert all(row['admission']['plateau']['basis']=='existing_grid' for row in confirm.json()['selection'])
    assert before=={path:sha256(path.read_bytes()).hexdigest() for path in before}
    with client.app.state.runs.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM optimizations').fetchone()[0]==job_count


def test_tested_grid_plateau_uses_available_neighbors_at_coarse_boundaries():
    from decimal import Decimal
    from alphaquest.campaign_narrow import plateau_check
    fields=[dict(name='stop',type='int'),dict(name='target',type='int'),
            dict(name='mode',type='int',refinement_kind='categorical')]
    axes=dict(stop=[5,10,15],target=[5,10,15],mode=[1,2])
    rows=[dict(trial=i,run_id=str(i),parameters=dict(stop=stop,target=target,mode=mode),
               metrics=dict(total_net_pnl='100' if mode==1 else '-100'),
               screening=dict(metrics=dict(is_stress_net_profit='50')))
          for i,(stop,target,mode) in enumerate(( (s,t,m) for s in axes['stop'] for t in axes['target'] for m in axes['mode']),1)]
    corner=rows[0]
    result=plateau_check(corner,rows,axes,fields)
    assert result['passed'] and result['one_sided'] and result['tested_neighbors']==2
    assert result['one_sided_parameters']==['stop','target']
    assert result['grid_steps']=={'stop':['5'],'target':['5']}
    assert {row['parameter'] for row in result['neighbors']}=={'stop','target'}
    assert all(row['value']=='10' for row in result['neighbors'])
    neighbor=next(row for row in rows if row['parameters']==dict(stop=10,target=5,mode=1))
    neighbor['metrics']['total_net_pnl']='70'
    assert plateau_check(corner,rows,axes,fields)['passed']
    neighbor['metrics']['total_net_pnl']='69.99999999999999999999999999999'
    assert not plateau_check(corner,rows,axes,fields)['passed']
    neighbor['metrics']['total_net_pnl']='70'
    neighbor['screening']['metrics']['is_stress_net_profit']='0'
    assert plateau_check(corner,rows,axes,fields)['status']=='failed'
    with pytest.raises(ValueError,match='neighbor is missing'):
        plateau_check(corner,[row for row in rows if row is not neighbor],axes,fields)
    # Adjacent Decimal values need not be equally spaced. Use the nearest actual
    # tested value on each side; no synthetic +/-1 or diagonal observation.
    decimal_fields=[dict(name='threshold',type='Decimal')]
    decimal_axes={'threshold':['0.1','0.3','0.8']}
    decimal_rows=[dict(trial=i,run_id=str(i),parameters={'threshold':value},metrics={'total_net_pnl':'100'},
                       screening={'metrics':{'is_stress_net_profit':'50'}})
                  for i,value in enumerate(decimal_axes['threshold'],1)]
    center=plateau_check(decimal_rows[1],decimal_rows,decimal_axes,decimal_fields)
    assert center['passed'] and not center['one_sided']
    assert center['grid_steps']=={'threshold':['0.2','0.5']}
    assert Decimal(center['minimum_retention_pct'])==100
    endpoint=plateau_check(decimal_rows[0],decimal_rows,decimal_axes,decimal_fields)
    assert endpoint['status']=='insufficient_evidence' and endpoint['tested_neighbors']==1
