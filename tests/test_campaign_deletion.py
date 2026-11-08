"""Campaign removal releases only its references; retained evidence stays exact."""
from copy import deepcopy
from hashlib import sha256
import json
import sqlite3
from uuid import uuid4

import pytest
from alphaquest.app import create_app
from research_fixtures import ResearchClient
from test_prop_phases import save_source
from test_research_campaigns import declaration, create, run, files

BASE='/api/research-campaigns/'

@pytest.fixture(scope='module')
def library(tmp_path_factory):
    root=tmp_path_factory.mktemp('campaign-deletion')
    with ResearchClient(create_app(root/'datasets.sqlite3')) as client:
        source=save_source(client,days=8)
        yield client,source,root

def saved(client,source):
    body=declaration(source,phase='funded')
    return body,create(client,body)

def preview(client,id):
    response=client.get(BASE+id+'/deletion');assert response.status_code==200,response.text
    return response.json()

def remove(client,id,token):
    return client.request('DELETE',BASE+id,json=dict(confirmation_sha256=token))

def access_rows(store):
    with store.connect() as db:
        return {name:db.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall()
                for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'research_access_%'")}


def test_completed_campaign_keeps_report_access_and_sources_and_releases_only_its_pins(tmp_path,monkeypatch):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        source=save_source(client,days=8)
        body,created=saved(client,source);id=created['campaign_id']
        completed=run(client,id);aid=completed['analysis_id']
        normal=client.get('/api/prop-analyses/'+aid+'/downloads/report.json')
        report=normal.json();assert sorted(c['metrics']['expected_payouts'] for c in report['calculations']['candidates'])==[0,1500]
        archive=client.get('/api/prop-analyses/'+aid+'/downloads/analysis.zip').content
        assert client.delete('/api/backtests/'+source['id']).status_code==409
        before=files(tmp_path);store=client.app.state.prop_analyses;access=access_rows(store)
        # Metadata inspection/deletion must never read source prices or calculate.
        with monkeypatch.context() as m:
            m.setattr(client.app.state.runs,'get',lambda *a,**k:pytest.fail('Source read during campaign deletion'))
            m.setattr('alphaquest.prop.funded_optimization.optimize_funded',lambda *a,**k:pytest.fail('Recalculated during deletion'))
            p=preview(client,id);assert p['deletable'] and p['source_reference_count']==1
            response=remove(client,id,p['confirmation_sha256']);assert response.status_code==200,response.text
        receipt=response.json();assert receipt['deleted'] and not receipt['deletable']
        assert receipt['source_ids']==[source['id']] and receipt['retained_analyses']==[dict(id=aid,status='complete')]
        assert remove(client,id,p['confirmation_sha256']).json()==receipt
        assert preview(client,id)==receipt
        assert client.get(BASE+id).status_code==404
        assert all(row['campaign_id']!=id for row in client.get(BASE).json()['items'])
        assert client.get('/api/backtests/'+source['id']).status_code==200
        assert files(tmp_path)==before and access_rows(store)==access
        for name,value in [('report.json',normal.content),('analysis.zip',archive)]:
            assert client.get('/api/prop-analyses/'+aid+'/downloads/'+name).content==value
        audit=client.get(BASE+id+'/exports/deletion_record.json');assert audit.status_code==200
        assert audit.json()['campaign_snapshot']['declaration']==created['declaration']
        assert audit.json()['campaign_snapshot']['manifest']==created['manifest']
        assert client.post(BASE.rstrip('/'),json=body).status_code==409
        # The user's original operation now works, and the report remains durable.
        assert client.delete('/api/backtests/'+source['id']).status_code==204
        assert client.get('/api/prop-analyses/'+aid+'/downloads/report.json').content==normal.content
        assert client.get('/api/prop-analyses/'+aid+'/downloads/analysis.zip').content==archive
        assert access_rows(store)==access
        (tmp_path/'deletion-evidence.json').write_text(json.dumps(dict(synthetic=True,source_id=source['id'],campaign_id=id,
            analysis_id=aid,expected_cash=[0,1500],preview=p,receipt=receipt,
            report_sha256=sha256(normal.content).hexdigest(),zip_sha256=sha256(archive).hexdigest(),
            audit_sha256=sha256(audit.content).hexdigest(),source_deleted_explicitly_after_campaign=True,
            access_history_unchanged=True),indent=2))


def test_shared_sources_stale_confirmation_and_other_campaign_remain_pinned(library):
    client,source,_=library
    _,a=saved(client,source);id=a['campaign_id'];old=preview(client,id)
    _,b=saved(client,source)
    rejected=remove(client,id,old['confirmation_sha256']);assert rejected.status_code==409 and 'changed' in rejected.text
    fresh=preview(client,id);assert fresh['deletable']
    assert any(r['id']==b['campaign_id'] for s in fresh['other_source_references'] for r in s['references'])
    assert remove(client,id,fresh['confirmation_sha256']).status_code==200
    assert client.get(BASE+b['campaign_id']).status_code==200
    rejection=client.delete('/api/backtests/'+source['id']);assert rejection.status_code==409 and b['campaign_id'] in rejection.text


def test_shared_completed_analysis_is_kept_with_its_other_campaign(library):
    client,source,_=library
    _,a=saved(client,source);first=run(client,a['campaign_id'])
    _,b=saved(client,source);second=run(client,b['campaign_id'])
    assert first['analysis_id']==second['analysis_id']
    aid=first['analysis_id'];original=client.get('/api/prop-analyses/'+aid+'/downloads/report.json').content
    p=preview(client,a['campaign_id'])
    assert remove(client,a['campaign_id'],p['confirmation_sha256']).status_code==200
    assert client.get(BASE+b['campaign_id']).json()['analysis_id']==aid
    assert client.get('/api/prop-analyses/'+aid+'/downloads/report.json').content==original
    with client.app.state.prop_analyses.connect() as db:
        assert db.execute('SELECT 1 FROM campaign_analyses WHERE campaign_id=? AND analysis_id=?',(b['campaign_id'],aid)).fetchone()
    assert client.delete('/api/prop-analyses/'+aid).status_code==409


@pytest.mark.parametrize('dependency',['queued','running','earlier_running','missing','frozen','assessment','procedure','application','lifecycle','forward','forward_report'])
def test_dependencies_block_deletion_and_identify_owner(library,dependency):
    client,source,_=library;_,c=saved(client,source);id=c['campaign_id'];reference=uuid4().hex
    store=client.app.state.prop_analyses
    before_dependency=preview(client,id)
    with store.connect() as db:
        if dependency in ('queued','running','earlier_running','missing'):
            if dependency!='missing':
                db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(reference,uuid4().hex,source['id'],'2026-01-01', 'running' if dependency=='earlier_running' else dependency,'guard fixture',None))
            db.execute('INSERT INTO campaign_analyses VALUES (?,?)',(id,reference))
            if dependency!='earlier_running':db.execute('UPDATE research_campaigns SET analysis_id=? WHERE id=?',(reference,id))
        elif dependency=='frozen':db.execute('UPDATE research_campaigns SET frozen=? WHERE id=?',('{}',id));reference=id
        elif dependency=='assessment':db.execute('INSERT INTO campaign_assessments VALUES (?,?,?)',(reference,id,'{}'))
        elif dependency=='procedure':db.execute('INSERT INTO research_procedures VALUES (?,?,?,?,?)',(reference,id,uuid4().hex,uuid4().hex,'{}'))
        elif dependency=='application':db.execute('INSERT INTO research_procedure_applications VALUES (?,?,?,?,?,?,?)',(reference,id,uuid4().hex,'current_development','{}',None,0))
        elif dependency=='lifecycle':db.execute('INSERT INTO lifecycle_comparisons VALUES (?,?,?,?)',(reference,json.dumps(dict(pairs=[dict(evaluation=dict(campaign_id=id))])),'{}',uuid4().hex))
        elif dependency=='forward':db.execute('INSERT INTO forward_monitors(id,declaration,policy,created) VALUES (?,?,?,?)',(reference,'{}',json.dumps(dict(policy_snapshot=dict(binding=dict(campaign_id=id)))),'2026-01-01'))
        else:
            aid=uuid4().hex;db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(aid,uuid4().hex,source['id'],'2026-01-01','complete','guard fixture',None))
            db.execute('INSERT INTO campaign_analyses VALUES (?,?)',(id,aid))
            db.execute('INSERT INTO forward_monitors(id,declaration,policy,created) VALUES (?,?,?,?)',(reference,'{}','{}','2026-01-01'))
            db.execute('INSERT INTO forward_report_refs VALUES (?,?,?)',(reference,aid,'phase_training'))
    p=preview(client,id);assert not p['deletable'] and reference in json.dumps(p['blockers'])
    response=remove(client,id,before_dependency['confirmation_sha256']);assert response.status_code==409 and reference in response.text
    with store.connect() as db:
        assert db.execute('SELECT 1 FROM research_campaigns WHERE id=?',(id,)).fetchone()
        assert not db.execute('SELECT 1 FROM campaign_deletions WHERE campaign_id=?',(id,)).fetchone()
        assert db.execute('SELECT 1 FROM campaign_sources WHERE campaign_id=?',(id,)).fetchone()


def test_sql_failure_rolls_back_audit_and_all_reference_changes(library):
    client,source,_=library;_,c=saved(client,source);id=c['campaign_id']
    store=client.app.state.prop_analyses
    with store.connect() as db:
        aid=uuid4().hex
        db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(aid,uuid4().hex,source['id'],'2026-01-01','error','Retained failed attempt','synthetic failure'))
        db.execute('INSERT INTO campaign_analyses VALUES (?,?)',(id,aid))
        db.execute('INSERT INTO campaign_jobs VALUES (?,?)',(id,uuid4().hex))
        # Fail only after all three association tables have been modified.
        db.execute(f"CREATE TRIGGER campaign_delete_failure BEFORE DELETE ON research_campaigns WHEN OLD.id='{id}' BEGIN SELECT RAISE(ABORT,'injected'); END")
    p=preview(client,id)
    try:
        response=remove(client,id,p['confirmation_sha256']);assert response.status_code==500 and 'No campaign deletion was committed' in response.text
        assert preview(client,id)==p
        with store.connect() as db:assert not db.execute('SELECT 1 FROM campaign_deletions WHERE campaign_id=?',(id,)).fetchone()
    finally:
        with store.connect() as db:db.execute('DROP TRIGGER campaign_delete_failure')
    assert remove(client,id,p['confirmation_sha256']).status_code==200


def test_invalid_confirmation_and_unknown_id_do_not_mutate(library):
    client,source,_=library;_,c=saved(client,source);id=c['campaign_id']
    assert client.request('DELETE',BASE+id,json={}).status_code==422
    assert remove(client,id,'0'*64).status_code==409
    assert client.get(BASE+id).status_code==200
    assert remove(client,uuid4().hex,'0'*64).status_code==404
    assert client.get(BASE+uuid4().hex+'/deletion').status_code==404


def test_grid_pins_release_and_deleted_id_cannot_be_rebound_as_nested(tmp_path):
    from test_robust_research_api import save_grid,declaration as nested_declaration
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,job,records=save_grid(client)
        body=declaration(records[0],phase='funded');body['sources']=[dict(optimization_id=job['id'],sizes=[1,3])]
        c=create(client,body);id=c['campaign_id'];p=preview(client,id)
        assert p['source_reference_count']==2 and p['optimization_ids']==[job['id']]
        assert remove(client,id,p['confirmation_sha256']).status_code==200
        with client.app.state.prop_analyses.connect() as db:
            assert not db.execute('SELECT 1 FROM campaign_jobs WHERE campaign_id=?',(id,)).fetchone()
        raw=nested_declaration(job,records);raw['campaign_id']=id
        response=client.post('/api/research-campaigns/robust',json=raw);assert response.status_code==409,response.text
        assert all(client.get('/api/backtests/'+r['id']).status_code==200 for r in records)
