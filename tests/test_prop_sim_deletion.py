"""Deletion lifecycle oracles in an isolated catalogue; no numerical fixture reports."""
import json
from pathlib import Path
from uuid import uuid4

from test_research_workflow import client
from alphaquest.prop_sim import Configuration


def seed(client,*,reuse=None):
    store=client.app.state.prop_analyses;id=uuid4().hex;source=uuid4().hex
    request=dict(request_id=id,selections=[dict(workflow_id=uuid4().hex,oos_job_id=uuid4().hex,monte_carlo_id=uuid4().hex,candidate=1)],start_date='2026-11-16')
    saved=dict(id=id,created_at_utc='2026-11-12T00:00:00+00:00',configuration=Configuration.model_validate(request).model_dump(mode='json'),
        qualification=dict(source_backtest_id=source,strategy_id='fixture_metadata_only'),campaign_ids={p:uuid4().hex for p in ('evaluation','funded')})
    ids=reuse or {p:uuid4().hex for p in ('evaluation','funded')}
    with store.connect() as db:
        for phase,cid in saved['campaign_ids'].items():
            aid=ids[phase]
            if not reuse:
                db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,NULL)',(aid,uuid4().hex,source,saved['created_at_utc'],'complete','Fixture metadata only'))
                folder=store.root/aid;folder.mkdir();(folder/'diagnostic.txt').write_text('Deletion test file; not a simulation output.')
                db.execute('INSERT INTO analysis_sources VALUES (?,?)',(aid,source))
                db.execute('INSERT INTO calculation_reuse VALUES (?,?,?,?)',(uuid4().hex,'fixture',aid,'fixture'))
                db.execute('INSERT INTO phase_analysis_control VALUES (?,0)',(aid,))
            manifest=dict(phase=phase,candidate_search_count=1,refinement=dict(status='not_requested'))
            db.execute('INSERT INTO research_campaigns VALUES (?,?,?,?,?,NULL)',(cid,saved['created_at_utc'],'{}',json.dumps(manifest),aid))
            db.execute('INSERT INTO campaign_analyses VALUES (?,?)',(cid,aid))
            db.execute('INSERT INTO campaign_sources VALUES (?,?)',(cid,source))
            db.execute('INSERT INTO workflow_prop_sim_phases VALUES (?,?,?)',(id,phase,cid))
        db.execute('INSERT INTO workflow_prop_simulations VALUES (?,?,?)',(id,saved['created_at_utc'],json.dumps(saved)))
    return saved,ids,request


def preview(client,id):
    response=client.get('/api/prop-sim/'+id+'/deletion');assert response.status_code==200,response.text
    return response.json()


def delete(client,id,plan):return client.request('DELETE','/api/prop-sim/'+id,json=dict(confirmation_sha256=plan['confirmation_sha256']))


def test_delete_unshared_catalogue_files_jobs_and_prevent_id_reuse(client):
    saved,ids,request=seed(client);store=client.app.state.prop_analyses
    plan=preview(client,saved['id']);assert plan['deletable'] and len(plan['analysis_ids_to_delete'])==2
    assert client.get('/api/prop-sim/'+saved['id']).status_code==200
    forged=dict(plan,confirmation_sha256='0'*64);assert delete(client,saved['id'],forged).status_code==409
    response=delete(client,saved['id'],plan);assert response.status_code==200,response.text
    assert response.json()['deleted'] and response.json()['cleanup_pending']==[]
    assert client.get('/api/prop-sim/'+saved['id']).status_code==404
    assert not client.get('/api/prop-sim').json()['items']
    for aid in ids.values():
        assert store.get(aid) is None and not (store.root/aid).exists()
        assert client.get('/api/jobs/prop_analysis/'+aid).status_code==404
    assert delete(client,saved['id'],plan).json()==response.json()
    response=client.post('/api/prop-sim',json=request)
    assert response.status_code==409 and 'was deleted' in response.text
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM calculation_reuse').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM phase_analysis_control').fetchone()[0]==0


def test_shared_reports_kept_and_fresh_preview_required(client):
    saved,ids,_=seed(client);store=client.app.state.prop_analyses;old=preview(client,saved['id'])
    before={aid:(store.root/aid/'diagnostic.txt').read_bytes() for aid in ids.values()}
    other,_,_=seed(client,reuse=ids)
    assert delete(client,saved['id'],old).status_code==409
    fresh=preview(client,saved['id']);assert fresh['analysis_ids_to_delete']==[] and len(fresh['retained_analyses'])==2
    response=delete(client,saved['id'],fresh);assert response.status_code==200,response.text
    assert client.get('/api/prop-sim/'+other['id']).status_code==200
    for aid in ids.values():assert store.get(aid) and (store.root/aid/'diagnostic.txt').read_bytes()==before[aid]
    assert delete(client,other['id'],preview(client,other['id'])).status_code==200
    assert all(store.get(aid) is None for aid in ids.values())


def test_active_rejected_and_frozen_phase_retained(client):
    saved,ids,_=seed(client);store=client.app.state.prop_analyses
    with store.connect() as db:db.execute("UPDATE analyses SET status='running' WHERE id=?",(ids['evaluation'],))
    plan=preview(client,saved['id']);assert not plan['deletable']
    assert delete(client,saved['id'],plan).status_code==409
    assert client.get('/api/prop-sim/'+saved['id']).status_code==200
    with store.connect() as db:
        db.execute("UPDATE analyses SET status='complete' WHERE id=?",(ids['evaluation'],))
        db.execute("UPDATE research_campaigns SET frozen='{}' WHERE id=?",(saved['campaign_ids']['evaluation'],))
    plan=preview(client,saved['id']);assert len(plan['retained_campaigns'])==1 and len(plan['retained_analyses'])==1
    response=delete(client,saved['id'],plan);assert response.status_code==200,response.text
    assert store.get(ids['evaluation']) and not store.get(ids['funded'])
    assert client.get('/api/research-campaigns/'+saved['campaign_ids']['evaluation']).status_code==200


def test_sql_failure_restores_parent_campaigns_and_report_files(client,monkeypatch):
    saved,ids,_=seed(client);store=client.app.state.prop_analyses;original=store.remove_catalogue_record;count=0
    def fail(db,id):
        nonlocal count
        count+=1
        if count==2:
            import sqlite3
            raise sqlite3.OperationalError('Injected catalogue failure')
        return original(db,id)
    monkeypatch.setattr(store,'remove_catalogue_record',fail)
    response=delete(client,saved['id'],preview(client,saved['id']));assert response.status_code==409,response.text
    assert client.get('/api/prop-sim/'+saved['id']).status_code==200
    for aid in ids.values():assert store.get(aid) and (store.root/aid/'diagnostic.txt').is_file() and not (store.root/('.deleted-'+aid)).exists()
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM workflow_prop_sim_deletions').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM campaign_deletions').fetchone()[0]==0


def test_cleanup_failure_can_be_retried_after_catalogue_delete(client,monkeypatch):
    import shutil
    saved,ids,_=seed(client);store=client.app.state.prop_analyses;original=shutil.rmtree
    plan=preview(client,saved['id']);target=store.root/('.deleted-'+ids['evaluation'])
    def fail(path,*args,**kwargs):
        if Path(path)==target:raise OSError('Injected cleanup failure')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(shutil,'rmtree',fail)
    response=delete(client,saved['id'],plan);assert response.status_code==200,response.text
    assert response.json()['cleanup_pending']==[ids['evaluation']] and target.exists()
    monkeypatch.setattr(shutil,'rmtree',original)
    retry=delete(client,saved['id'],plan);assert retry.status_code==200 and retry.json()['cleanup_pending']==[]
    assert not target.exists()


def test_symbolic_link_refusal_restores_metadata(client,tmp_path):
    import shutil
    saved,ids,_=seed(client);store=client.app.state.prop_analyses
    target=tmp_path/'outside-report';target.mkdir();(target/'keep.txt').write_text('Keep this file')
    folder=store.root/ids['evaluation'];shutil.rmtree(folder);folder.symlink_to(target,target_is_directory=True)
    response=delete(client,saved['id'],preview(client,saved['id']));assert response.status_code==409,response.text
    assert client.get('/api/prop-sim/'+saved['id']).status_code==200
    assert (target/'keep.txt').read_text()=='Keep this file' and folder.is_symlink()
