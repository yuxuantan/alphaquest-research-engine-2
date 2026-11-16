"""Permanent individual-workflow deletion through the real API, in temporary catalogues."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID,uuid4

import pytest
from fastapi.testclient import TestClient
from alphaquest.app import create_app
from alphaquest.campaign_dataset_links import identity
from test_research_workflow import client
from test_campaign_mechanics import create_workflow,run_validation


def preview(client,workflow):
    body=dict(strategy_id=workflow['declaration']['strategy_id'],source=identity(workflow['declaration']['dataset']))
    if workflow.get('id'):
        body['workflow_id']=workflow['id']
    else:
        groups=client.get('/api/strategies/'+body['strategy_id']+'/datasets').json()['items']
        body['group_id']=next(g['id'] for g in groups if identity(g['dataset'])==body['source'])
    response=client.post('/api/campaign-dataset-links/preview',json=body)
    assert response.status_code==200,response.text
    return body,response.json()


def remove(client,body,p):
    return client.request('DELETE','/api/campaign-dataset-links',json=dict(body,confirmation_sha256=p['confirmation_sha256']))


def test_permanent_results_and_jobs_deleted_dataset_campaign_kept_and_reopen(client):
    dataset,config,workflow=create_workflow(client);result=run_validation(client,workflow)
    runs=client.app.state.runs;folder=runs.root/result['run_id']
    body,p=preview(client,workflow)
    assert p['workflow_ids']==[workflow['id']] and p['run_ids']==[result['run_id']] and p['deletable']
    assert p['file_count'] and any(f['path'].endswith('trades.csv') for f in p['files'])
    response=remove(client,body,p);assert response.status_code==200,response.text
    receipt=response.json();assert receipt['deleted'] and receipt['cleanup_pending']==[]
    assert remove(client,body,p).json()==receipt
    assert not folder.exists()
    assert client.get('/api/campaign-workflows/'+workflow['id']).status_code==404
    assert client.get('/api/backtests/'+result['run_id']).status_code==404
    assert client.get('/api/jobs/mechanic_validation/'+result['run_id']).status_code==404
    assert client.get('/api/datasets/'+dataset['id']).status_code==200
    assert any(s['id']==config['strategy_id'] for s in client.get('/api/strategies/library').json()['items'])
    assert client.get('/api/strategies/'+config['strategy_id']+'/datasets').json()['total']==0
    # Reversible removal/restore is retired. No strategy-only deletion is allowed.
    assert client.get('/api/campaign-dataset-links?strategy_id='+config['strategy_id']).status_code==405
    assert client.post(f"/api/campaign-dataset-links/{config['strategy_id']}/{p['source_key']}/restore").status_code==404
    assert client.request('DELETE','/api/campaign-dataset-links',json=dict(strategy_id=config['strategy_id'])).status_code==422
    with TestClient(create_app(client.app.state.store.path)) as reopened:
        assert reopened.get('/api/campaign-workflows/'+workflow['id']).status_code==404
        assert remove(reopened,body,p).json()==receipt
        created=reopened.post('/api/campaign-workflows',json=config)
        assert created.status_code==201 and created.json()['id']!=workflow['id']


def test_legacy_group_has_explicit_scope_and_stale_membership_rejects(client):
    from test_research_workflow import save,start_is
    dataset=save(client);record=start_is(client,dataset)
    legacy=dict(declaration=dict(strategy_id='consecutive_green_hold',dataset=record['run_metadata']['dataset']))
    body,p=preview(client,legacy)
    assert p['workflow_ids']==[] and p['run_ids']==[record['id']]
    assert remove(client,body,dict(confirmation_sha256='0'*64)).status_code==409
    another=start_is(client,dataset)
    assert remove(client,body,p).status_code==409
    body,p=preview(client,legacy)
    assert set(p['run_ids'])=={record['id'],another['id']}
    assert remove(client,body,p).status_code==200
    assert client.get('/api/datasets/'+dataset['id']).status_code==200


def test_deleting_one_of_two_same_dataset_workflows_keeps_other_results(client):
    dataset,config,w=create_workflow(client);first=run_validation(client,w)
    created=client.post('/api/campaign-workflows',json=dict(config,execution_settings=dict(config['execution_settings'],slippage_ticks=2)))
    assert created.status_code==201,created.text
    other=created.json();second=run_validation(client,other)
    assert first['run_id']!=second['run_id']
    folder=client.app.state.runs.root/second['run_id']
    before={p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
    body,p=preview(client,w)
    assert p['workflow_ids']==[w['id']] and p['run_ids']==[first['run_id']]
    # Source-wide and mixed-scope requests cannot reproduce the old remove-both bug.
    source_only={k:v for k,v in body.items() if k!='workflow_id'}
    assert client.post('/api/campaign-dataset-links/preview',json=source_only).status_code==422
    assert client.post('/api/campaign-dataset-links/preview',json=dict(body,group_id='a'*64)).status_code==422
    assert remove(client,dict(body,workflow_id=other['id']),p).status_code==409
    assert remove(client,body,p).status_code==200
    assert client.get('/api/campaign-workflows/'+other['id']).json()==second
    assert client.get('/api/backtests/'+second['run_id']).status_code==200
    assert before=={p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
    assert client.get('/api/datasets/'+dataset['id']).status_code==200
    with TestClient(create_app(client.app.state.store.path)) as reopened:
        assert reopened.get('/api/campaign-workflows/'+w['id']).status_code==404
        assert reopened.get('/api/campaign-workflows/'+other['id']).status_code==200


def test_workflow_stale_confirmation_and_unknown_scope_reject(client):
    _,_,w=create_workflow(client)
    body,p=preview(client,w)
    run_validation(client,w)
    assert remove(client,body,p).status_code==409
    unknown=deepcopy(body);unknown['source']['sha256']='f'*64
    assert client.post('/api/campaign-dataset-links/preview',json=unknown).status_code==404
    assert client.post('/api/campaign-dataset-links/preview',json=dict(body,workflow_id=uuid4().hex)).status_code==404


def seed_family(client):
    """Metadata-only graph fixtures; the mechanics report itself is a real backtest."""
    dataset,config,workflow=create_workflow(client);result=run_validation(client,workflow)
    store=client.app.state.prop_analyses;runs=client.app.state.runs
    batches=[uuid4().hex for _ in range(3)]
    with runs.connect() as db:
        for table,jid in zip(('campaign_broad_jobs','campaign_narrow_jobs','campaign_oos_jobs'),batches):
            job=dict(id=jid,status='complete',dataset=workflow['declaration']['dataset'],strategy=dict(id=config['strategy_id']))
            db.execute('INSERT INTO optimizations VALUES (?,?,?)',(jid,'2026-11-15',json.dumps(job)))
            db.execute('INSERT INTO optimization_trials VALUES (?,?,?)',(jid,1,json.dumps(dict(run_id=result['run_id']))))
            values=(jid,workflow['id'])+((1,) if table=='campaign_narrow_jobs' else (uuid4().hex,) if table=='campaign_oos_jobs' else ())
            db.execute(f'INSERT INTO {table} VALUES ({",".join("?" for _ in values)})',values)
        db.execute('INSERT INTO optimization_trial_cache VALUES (?,?)',(uuid4().hex,json.dumps(dict(row=dict(run_id=result['run_id'])))))
    from test_prop_sim_deletion import seed
    saved,ids,_=seed(client)
    with store.connect() as db:
        saved['configuration']['selections'][0]['workflow_id']=str(UUID(workflow['id']))
        saved['qualification']['source_backtest_id']=result['run_id']
        saved['qualification']['strategy_id']=config['strategy_id']
        db.execute('UPDATE workflow_prop_simulations SET payload=? WHERE id=?',(json.dumps(saved),saved['id']))
        for cid in saved['campaign_ids'].values():
            db.execute("UPDATE research_campaigns SET frozen='{}' WHERE id=?",(cid,))
            db.execute('UPDATE campaign_sources SET source_id=? WHERE campaign_id=?',(result['run_id'],cid))
        for aid in ids.values():
            db.execute('UPDATE analysis_sources SET source_id=? WHERE analysis_id=?',(result['run_id'],aid))
            db.execute('UPDATE analyses SET source_id=? WHERE id=?',(result['run_id'],aid))
        mc=uuid4().hex
        db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,NULL)',(mc,uuid4().hex,result['run_id'],'2026-11-15','complete','Synthetic deletion graph only'))
        db.execute('INSERT INTO campaign_sanity_jobs VALUES (?,?,?)',(mc,workflow['id'],batches[-1]))
        db.execute('INSERT INTO analysis_sources VALUES (?,?)',(mc,result['run_id']))
        folder=store.root/mc;folder.mkdir();(folder/'fixture.txt').write_text('Not a numerical simulation result.')
        # An OOS assessment owned by a frozen phase is included in the cascade.
        db.execute('INSERT INTO campaign_assessments VALUES (?,?,?)',(uuid4().hex,saved['campaign_ids']['evaluation'],json.dumps(dict(analysis_id=ids['evaluation']))))
    return dataset,config,workflow,result,batches,saved,dict(ids,monte_carlo=mc)


def test_cascade_frozen_phases_mc_and_shared_evidence_protection(client):
    dataset,config,w,result,batches,sim,analyses=seed_family(client)
    store=client.app.state.prop_analyses;runs=client.app.state.runs
    _,before=preview(client,w)
    assert set(before['job_ids'])==set(batches) and set(before['analysis_ids'])==set(analyses.values())
    assert before['simulation_ids']==[sim['id']] and set(before['phase_campaign_ids'])==set(sim['campaign_ids'].values())
    # Another independent phase campaign owns the Evaluation analysis and source.
    cid=uuid4().hex
    with store.connect() as db:
        db.execute('INSERT INTO research_campaigns VALUES (?,?,?,?,?,NULL)',(cid,'2026-11-15','{}','{}',analyses['evaluation']))
        db.execute('INSERT INTO campaign_sources VALUES (?,?)',(cid,result['run_id']))
        db.execute('INSERT INTO campaign_analyses VALUES (?,?)',(cid,analyses['evaluation']))
    assert remove(client,dict(strategy_id=config['strategy_id'],source=identity(w['declaration']['dataset']),workflow_id=w['id']),before).status_code==409
    body,p=preview(client,w)
    assert p['run_ids']==[] and p['retained_runs'][0]['id']==result['run_id']
    assert analyses['evaluation'] not in p['analysis_ids'] and p['retained_analyses'][0]['id']==analyses['evaluation']
    assert remove(client,body,p).status_code==200
    assert (runs.root/result['run_id']).exists() and store.get(analyses['evaluation'])
    assert all(store.get(aid) is None and not (store.root/aid).exists() for phase,aid in analyses.items() if phase!='evaluation')
    assert client.get('/api/prop-sim/'+sim['id']).status_code==404
    assert all(client.get('/api/backtests/batches/'+jid).status_code==404 for jid in batches)
    with store.connect() as db:
        assert db.execute('SELECT id FROM research_campaigns').fetchall()==[(cid,)]
        assert db.execute('SELECT count(*) FROM campaign_sanity_jobs').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM campaign_assessments').fetchone()[0]==0
    assert client.get('/api/backtests/'+result['run_id']).status_code==200
    # Once the external owner releases it, remaining source evidence can be deleted.
    with store.connect() as db:
        for table in ('campaign_sources','campaign_analyses'):db.execute(f'DELETE FROM {table} WHERE campaign_id=?',(cid,))
        db.execute('DELETE FROM research_campaigns WHERE id=?',(cid,))
    body,p=preview(client,dict(declaration=w['declaration']));assert result['run_id'] in p['run_ids']
    assert remove(client,body,p).status_code==200
    assert not (runs.root/result['run_id']).exists() and store.get(analyses['evaluation']) is None


@pytest.mark.parametrize('kind',['mechanic','batch','analysis','forward'])
def test_busy_work_and_forward_binding_block_entire_delete(client,kind):
    _,_,w,result,batches,sim,analyses=seed_family(client)
    store=client.app.state.prop_analyses
    if kind=='mechanic':
        with client.app.state.runs.connect() as db:db.execute("UPDATE mechanic_job_attempts SET status='running' WHERE workflow_id=?",(w['id'],))
    elif kind=='batch':
        with client.app.state.runs.connect() as db:db.execute("UPDATE optimizations SET payload=json_set(payload,'$.status','running') WHERE id=?",(batches[0],))
    elif kind=='analysis':
        with store.connect() as db:db.execute("UPDATE analyses SET status='running' WHERE id=?",(analyses['funded'],))
    else:
        with store.connect() as db:db.execute('INSERT INTO forward_monitors VALUES (?,?,?,?,0,0)',(uuid4().hex,json.dumps(dict(application_id=sim['id'])),'{}','2026-11-15'))
    body,p=preview(client,w);assert not p['deletable'] and p['blockers']
    assert remove(client,body,p).status_code==409
    assert client.get('/api/campaign-workflows/'+w['id']).status_code==200
    assert client.get('/api/prop-sim/'+sim['id']).status_code==200
    assert (client.app.state.runs.root/result['run_id']).exists()


def test_cross_catalogue_rollback_file_cleanup_retry_and_crash_recovery(client,monkeypatch):
    import shutil
    _,config,w,result,batches,sim,analyses=seed_family(client)
    runs=client.app.state.runs;owner=client.app.state.campaign_dataset_links;store=client.app.state.prop_analyses
    body,p=preview(client,w)
    with runs.connect() as db:
        db.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON runs BEGIN SELECT RAISE(ABORT,'injected SQL failure'); END")
    assert remove(client,body,p).status_code==409
    assert client.get('/api/campaign-workflows/'+w['id']).status_code==200 and client.get('/api/prop-sim/'+sim['id']).status_code==200
    assert (runs.root/result['run_id']).exists() and all((store.root/id).exists() for id in analyses.values())
    with runs.connect() as db:db.execute('DROP TRIGGER fail_delete')
    original=shutil.rmtree
    def fail(path,*args,**kwargs):
        if Path(path).name.startswith('.workflow-deleted-'):raise OSError('Injected cleanup failure')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(shutil,'rmtree',fail)
    deleted=remove(client,body,p);assert deleted.status_code==200,deleted.text
    assert deleted.json()['cleanup_pending']
    assert client.get('/api/prop-sim/'+sim['id']).status_code==404
    monkeypatch.setattr(shutil,'rmtree',original)
    # Startup recovery finishes committed physical cleanup without reintroducing evidence.
    owner.recover();assert remove(client,body,p).json()['cleanup_pending']==[]
    # Simulate a process dying after one rename but before the catalogue commit.
    fresh=client.post('/api/campaign-workflows',json=config).json();native=run_validation(client,fresh)
    _,plan=preview(client,fresh);id=native['run_id'];dest=runs.root/id;staged=runs.root/('.workflow-deleted-'+id)
    with runs.connect() as db:db.execute('INSERT INTO campaign_dataset_deletions VALUES (?,?)',(plan['confirmation_sha256'],json.dumps(dict(preview=plan,deleted=False))))
    dest.rename(staged);owner.recover()
    assert dest.exists() and not staged.exists() and runs.get(id)


def test_symbolic_link_refusal_keeps_outside_files(client,tmp_path):
    _,_,w=create_workflow(client);native=run_validation(client,w)
    folder=client.app.state.runs.root/native['run_id'];outside=tmp_path/'outside';outside.mkdir();(outside/'keep.txt').write_text('keep')
    (folder/'unsafe').symlink_to(outside,target_is_directory=True)
    body,p=preview(client,w);assert not p['deletable'] and remove(client,body,p).status_code==409
    assert (outside/'keep.txt').read_text()=='keep'


def test_campaign_and_external_source_kind_isolation(client):
    from test_campaign_mechanics import mechanics_csv
    from test_canonical_trades import envelope,raw
    uploaded=client.post('/api/datasets',params=dict(filename='SYNTHETIC-shared.csv',name='SYNTHETIC shared source',symbol='NQ',source_timezone='UTC',tick_size='.25',point_value='20'),content=mechanics_csv())
    assert uploaded.status_code==201,uploaded.text
    dataset=uploaded.json()
    config=dict(dataset_id=dataset['id'],strategy_id='consecutive_green_hold',sample_split=dict(mode='dates',is_start='2026-01-05',is_end='2026-01-05',oos_start='2026-01-06',oos_end='2026-01-06'),execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1'))
    w=client.post('/api/campaign-workflows',json=config).json();result=run_validation(client,w)
    other=client.post('/api/campaign-workflows',json=dict(config,strategy_id='vwap_pullback_risk_sizing'))
    assert other.status_code==201,other.text
    document=envelope();document['manifest']['strategy']['id']=config['strategy_id']
    document['manifest']['dataset']['sha256']=dataset['sha256'];document['manifest']['time']['source_timezone']='UTC'
    imported=client.post('/api/backtests/imports',params=dict(filename='SYNTHETIC.json'),content=raw(document))
    assert imported.status_code==201,imported.text
    # Native source deletion must preserve the external report even if its declared data hash matches.
    body,p=preview(client,w);assert imported.json()['id'] not in p['run_ids']
    assert remove(client,body,p).status_code==200
    assert client.get('/api/campaign-workflows/'+other.json()['id']).status_code==200
    assert client.get('/api/backtests/'+imported.json()['id']).status_code==200
    groups=client.get('/api/strategies/'+config['strategy_id']+'/datasets').json()['items']
    group=next(g for g in groups if g.get('source_kind')=='external_trade_export')
    external=dict(declaration=dict(strategy_id=config['strategy_id'],dataset=group['dataset']))
    body,p=preview(client,external);assert p['run_ids']==[imported.json()['id']]
    assert remove(client,body,p).status_code==200
    assert client.get('/api/backtests/'+imported.json()['id']).status_code==404
    assert client.get('/api/campaign-workflows/'+other.json()['id']).status_code==200


def test_shared_backtest_and_automatic_analysis_survive_other_workflow_owner(client):
    from test_research_workflow import save,start_is
    dataset=save(client);report=start_is(client,dataset)
    request=dict(dataset_id=dataset['id'],strategy_id='consecutive_green_hold',sample_split=dict(mode='percentage',is_percent=50),execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1'))
    first=client.post('/api/campaign-workflows',json=request).json()
    second=client.post('/api/campaign-workflows',json=dict(request,execution_settings=dict(request['execution_settings'],slippage_ticks=2))).json()
    # Two stored owners pin one real report. No calculated metric is fabricated.
    for workflow in [first,second]:
        with client.app.state.runs.connect() as db:
            saved=client.app.state.campaign_workflows.raw(workflow['id'],db)
            saved.update(run_id=report['id'],status='review_required')
            client.app.state.campaign_workflows.write(db,saved)
    aid=report['run_metadata']['automatic_prop_analysis']['id']
    body,p=preview(client,first)
    assert p['run_ids']==[] and aid not in p['analysis_ids']
    assert report['id'] in {r['id'] for r in p['retained_runs']}
    assert aid in {r['id'] for r in p['retained_analyses']}
    assert remove(client,body,p).status_code==200
    assert client.get('/api/campaign-workflows/'+second['id']).status_code==200
    assert client.get('/api/backtests/'+report['id']).status_code==200
    assert client.app.state.prop_analyses.get(aid) is not None


def test_oos_access_history_survives_permanent_result_deletion(client):
    from test_research_workflow import save,start_is,oos,status
    dataset=save(client);record=start_is(client,dataset)
    assessed=oos(client,record);assert assessed.status_code==201,assessed.text
    before=status(client,dataset)
    assert before['used']==1
    legacy=dict(declaration=dict(strategy_id='consecutive_green_hold',dataset=record['run_metadata']['dataset']))
    body,p=preview(client,legacy)
    assert {record['id'],assessed.json()['id']}<=set(p['run_ids'])
    assert remove(client,body,p).status_code==200
    after=status(client,dataset)
    assert after['used']==before['used'] and len(after['attempts'])==1
    assert after['attempts'][0]['report_available']==0
    assert client.get('/api/backtests/'+assessed.json()['id']).status_code==404


def test_actual_broad_grid_is_scoped_and_removed_with_its_workflow(client):
    from test_campaign_broad import passed_mechanics,start_grid,broad_grid
    dataset,config,w=passed_mechanics(client)
    job,_=start_grid(client,'/api/campaign-workflows/'+w['id'],broad_grid(3,20,1))
    rows=client.get('/api/campaign-workflows/'+w['id']+'/broad/results').json()['items']
    body,p=preview(client,w)
    assert job['id'] in p['job_ids'] and {r['run_id'] for r in rows}<=set(p['run_ids'])
    assert remove(client,body,p).status_code==200
    assert client.get('/api/backtests/batches/'+job['id']).status_code==404
    assert all(client.get('/api/backtests/'+r['run_id']).status_code==404 for r in rows)
    assert client.get('/api/datasets/'+dataset['id']).status_code==200


def test_deleted_downstream_package_ids_have_metadata_only_tombstones(client):
    _,_,w,_,_,sim,_=seed_family(client)
    body,p=preview(client,w);assert remove(client,body,p).status_code==200
    with client.app.state.prop_analyses.connect() as db:
        tombstone=json.loads(db.execute('SELECT payload FROM workflow_prop_sim_deletions WHERE id=?',(sim['id'],)).fetchone()[0])
        assert set(tombstone)=={'receipt'} and tombstone['receipt']['deleted']
        for cid in sim['campaign_ids'].values():
            saved=json.loads(db.execute('SELECT payload FROM campaign_deletions WHERE campaign_id=?',(cid,)).fetchone()[0])
            assert set(saved)=={'receipt'} and saved['receipt']['deleted']
            assert 'frozen' not in saved and 'manifest' not in saved and 'metrics' not in saved


def test_controlled_native_child_reports_are_deleted_with_their_analysis(client):
    from test_research_workflow import save,start_is
    _,_,w,_,_,_,analyses=seed_family(client)
    child=start_is(client,save(client))
    # Explicit metadata-only ownership fixture over a real native report.
    child['run_metadata']['native_account_control']=dict(analysis_id=analyses['funded'])
    with client.app.state.runs.connect() as db:
        db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(child),child['id']))
    with client.app.state.prop_analyses.connect() as db:
        db.execute('INSERT INTO analysis_sources VALUES (?,?)',(analyses['funded'],child['id']))
    body,p=preview(client,w)
    assert child['id'] in p['run_ids'] and analyses['funded'] in p['analysis_ids']
    assert remove(client,body,p).status_code==200
    assert not (client.app.state.runs.root/child['id']).exists()
    assert client.get('/api/backtests/'+child['id']).status_code==404


def test_other_workflows_prop_sim_using_a_shared_report_is_not_cascaded(client):
    _,config,w,result,_,sim,_=seed_family(client)
    other=client.post('/api/campaign-workflows',json=dict(config,execution_settings=dict(config['execution_settings'],slippage_ticks=2))).json()
    with client.app.state.runs.connect() as db:
        saved=client.app.state.campaign_workflows.raw(other['id'],db)
        saved['run_id']=result['run_id'];client.app.state.campaign_workflows.write(db,saved)
    from test_prop_sim_deletion import seed
    sibling,ids,_=seed(client)
    store=client.app.state.prop_analyses
    with store.connect() as db:
        sibling['configuration']['selections'][0]['workflow_id']=str(UUID(other['id']))
        sibling['qualification']['source_backtest_id']=result['run_id']
        db.execute('UPDATE workflow_prop_simulations SET payload=? WHERE id=?',(json.dumps(sibling),sibling['id']))
        for cid in sibling['campaign_ids'].values():
            db.execute('UPDATE campaign_sources SET source_id=? WHERE campaign_id=?',(result['run_id'],cid))
        for aid in ids.values():
            db.execute('UPDATE analyses SET source_id=? WHERE id=?',(result['run_id'],aid))
            db.execute('UPDATE analysis_sources SET source_id=? WHERE analysis_id=?',(result['run_id'],aid))
    before={aid:(store.root/aid/'diagnostic.txt').read_bytes() for aid in ids.values()}
    body,p=preview(client,w)
    assert p['simulation_ids']==[sim['id']]
    assert not set(ids.values()) & set(p['analysis_ids'])
    assert remove(client,body,p).status_code==200
    assert client.get('/api/prop-sim/'+sibling['id']).status_code==200
    assert client.get('/api/campaign-workflows/'+other['id']).status_code==200
    assert client.get('/api/backtests/'+result['run_id']).status_code==200
    assert before=={aid:(store.root/aid/'diagnostic.txt').read_bytes() for aid in ids.values()}


def test_wal_catalogue_rejects_before_any_files_move(client):
    _,_,w=create_workflow(client);report=run_validation(client,w)
    folder=client.app.state.runs.root/report['run_id']
    before={p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
    with client.app.state.prop_analyses.connect() as db:
        assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
    response=client.post('/api/campaign-dataset-links/preview',json=dict(strategy_id=w['declaration']['strategy_id'],
        source=identity(w['declaration']['dataset']),workflow_id=w['id']))
    assert response.status_code==409 and 'rollback-journal' in response.text
    assert before=={p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
