"""Editable pre-work records never confer execution or research authority."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
from uuid import UUID,uuid4

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from test_robust_research_api import PREFIX as ROBUST,save_grid,declaration
from test_research_campaigns import declaration as phase_declaration
from test_robust_economic_api import economic

BASE='/api/research-workspace'
SETTINGS={'folds','qualification','execution_scenarios','regimes','economic_studies',
          'reliability','terminal_selection','final_evidence'}


def draft_declaration(job=None,records=None):
    if records is None:
        return dict(source_backtest_id='a'*32,sources=[dict(backtest_id='a'*32,sizes=[1])])
    value=declaration(job,records)
    for key in ('campaign_id','confirmed_backtest_count','confirmed_economic_candidate_count'):
        value.pop(key,None)
    value['sources']=[dict(backtest_id=record['id'],sizes=[1]) for record in records]
    return value


def draft_body(name='Workspace draft',**changes):
    return dict(kind='nested',name=name,declaration=draft_declaration())|changes


def created(client,path,body):
    response=client.post(BASE+path,json=body)
    assert response.status_code==201,response.text
    result=response.json()
    assert result['schema_version']=='research-workspace-v1'
    assert UUID(result['id']).hex==result['id'] and result['revision']==1
    return result


def forbid_execution(client,monkeypatch):
    def forbidden(*args,**kwargs):pytest.fail('Workspace metadata operation attempted execution or source-price preparation')
    monkeypatch.setattr(client.app.state.robust_research,'preview',forbidden)
    monkeypatch.setattr(client.app.state.prop_analyses.worker,'submit',forbidden)
    monkeypatch.setattr(client.app.state.optimizations.executor,'submit',forbidden)
    monkeypatch.setattr('alphaquest.robust_research.run_backtest',forbidden)
    monkeypatch.setattr('alphaquest.backtest_data.read_bars',forbidden)
    monkeypatch.setattr('alphaquest.prepared_data.prepare_data',forbidden)


def test_draft_crud_is_revisioned_metadata_only_and_survives_restart(tmp_path,monkeypatch):
    database=tmp_path/'datasets.sqlite3'
    with TestClient(create_app(database)) as client:
        forbid_execution(client,monkeypatch)
        body=draft_body(revision=None)
        saved=created(client,'/drafts',body);id=saved['id']
        assert saved['declaration']['source_backtest_id']=='a'*32
        assert 'campaign_id' not in saved['declaration']
        assert 'a'*32 in json.dumps(saved['missing_sources'])
        assert 'source_summaries' in saved
        response=client.put(BASE+'/drafts/'+id,json=dict(body,name='Edited pre-work',revision=1))
        assert response.status_code==200,response.text
        updated=response.json();assert updated['revision']==2 and updated['name']=='Edited pre-work'
        assert client.put(BASE+'/drafts/'+id,json=dict(body,name='Stale overwrite',revision=1)).status_code==409
        assert client.delete(BASE+'/drafts/'+id,params=dict(revision=1)).status_code==409
        assert client.delete(BASE+'/drafts/'+id).status_code==422
        assert client.get(BASE+'/drafts/'+id).json()==updated
        with client.app.state.prop_analyses.connect() as db:
            assert db.execute('SELECT count(*) FROM analyses').fetchone()[0]==0
            assert db.execute('SELECT count(*) FROM campaign_sources').fetchone()[0]==0
    with TestClient(create_app(database)) as client:
        assert client.get(BASE+'/drafts/'+id).json()==updated
        response=client.delete(BASE+'/drafts/'+id,params=dict(revision=2))
        assert response.status_code==204,response.text
        assert client.get(BASE+'/drafts/'+id).status_code==404


def test_two_simultaneous_draft_edits_cannot_lose_an_update(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        saved=created(client,'/drafts',draft_body())
        def save(name):return client.put(BASE+'/drafts/'+saved['id'],json=draft_body(name,revision=1))
        with ThreadPoolExecutor(max_workers=2) as workers:
            replies=list(workers.map(save,['Concurrent edit A','Concurrent edit B']))
        assert sorted(reply.status_code for reply in replies)==[200,409]
        winner=next(reply.json() for reply in replies if reply.status_code==200)
        assert winner['revision']==2 and client.get(BASE+'/drafts/'+saved['id']).json()==winner


@pytest.mark.parametrize('document_type',['drafts','templates'])
def test_future_document_schema_is_preserved_read_only(tmp_path,document_type):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        body=draft_body() if document_type=='drafts' else dict(name='Future template',settings={})
        saved=created(client,'/'+document_type,body)
        opaque=dict(future_setting=dict(unknown_type=['preserve',17]),source_reference='do not interpret')
        raw=json.dumps(opaque)
        with client.app.state.prop_analyses.connect() as db:
            db.execute('UPDATE research_workspace_documents SET schema_version=?,payload=?,payload_sha256=? WHERE id=?',
                ('research-workspace-v999',raw,sha256(raw.encode()).hexdigest(),saved['id']))
        response=client.get(BASE+'/'+document_type+'/'+saved['id'])
        assert response.status_code==200,response.text
        restored=response.json()
        assert restored['schema_version']=='research-workspace-v999' and restored['editable'] is False
        assert restored['declaration' if document_type=='drafts' else 'settings']==opaque
        assert restored['warnings'] and restored['requires_fresh_preview'] is True
        assert client.put(BASE+'/'+document_type+'/'+saved['id'],json=dict(body,revision=1)).status_code==409
        assert client.get(BASE+'/'+document_type+'/'+saved['id']).json()==restored


def test_saved_document_checksum_mismatch_is_not_opened_or_overwritten_by_get(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        saved=created(client,'/drafts',draft_body())
        with client.app.state.prop_analyses.connect() as db:
            db.execute('UPDATE research_workspace_documents SET payload=? WHERE id=?',
                (json.dumps(draft_declaration()|dict(name='Modified outside revision protocol')),saved['id']))
        response=client.get(BASE+'/drafts/'+saved['id'])
        assert response.status_code==409 and 'integrity' in response.text.lower(),response.text
        assert client.get(BASE+'/drafts').status_code==409


@pytest.mark.parametrize('change',[
    dict(kind='phase'),dict(name=''),dict(unknown='field'),dict(revision=True),
    dict(declaration=dict(source_backtest_id='a'*32,sources=[])),
    dict(declaration=dict(source_backtest_id='a'*32,sources=[dict(backtest_id='a'*32,sizes=[1])],winner='b'*64)),
])
def test_draft_rejects_unsupported_or_untyped_declarations(tmp_path,change):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        response=client.post(BASE+'/drafts',json={**draft_body(),**change})
        assert response.status_code==422,response.text


def test_template_roundtrip_has_settings_only_and_requires_revision(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        defaults=client.get(ROBUST+'/defaults').json()
        settings={key:deepcopy(defaults[key]) for key in ('folds','qualification','regimes','reliability','terminal_selection','final_evidence')}
        forbid_execution(client,monkeypatch)
        body=dict(kind='nested',name='Reusable settings only',settings=settings)
        saved=created(client,'/templates',body);id=saved['id']
        assert set(saved['settings'])<=SETTINGS and 'source_backtest_id' not in json.dumps(saved['settings'])
        assert saved['settings']['qualification']['bootstrap_replicates']==settings['qualification']['bootstrap_replicates']
        assert client.get(BASE+'/templates/'+id).json()==saved
        listing=client.get(BASE+'/templates',params=dict(q='settings only',limit=1,offset=0)).json()
        assert listing['total']==1 and listing['items'][0]['id']==id
        changed=deepcopy(body);changed['name']='Updated settings';changed['revision']=1
        changed['settings']['qualification']['minimum_neighbors']=2
        response=client.put(BASE+'/templates/'+id,json=changed)
        assert response.status_code==200,response.text
        assert response.json()['revision']==2
        assert client.put(BASE+'/templates/'+id,json=changed).status_code==409
        assert client.delete(BASE+'/templates/'+id).status_code==422
        assert client.delete(BASE+'/templates/'+id,params=dict(revision=1)).status_code==409
        assert client.delete(BASE+'/templates/'+id,params=dict(revision=2)).status_code==204


@pytest.mark.parametrize('key,value',[
    ('sources',[dict(backtest_id='a'*32,sizes=[1])]),('source_backtest_id','a'*32),
    ('report_sha256','a'*64),('metrics',dict(cash=1500)),('prior_access',dict(untouched=True)),
    ('candidate_ids',['a'*64]),('reservation_id','a'*32),('eligibility',dict(status='PASS')),
])
def test_template_cannot_copy_source_report_or_eligibility_authority(tmp_path,key,value):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        response=client.post(BASE+'/templates',json=dict(kind='nested',name='Forbidden authority',settings={key:value}))
        assert response.status_code==422,response.text


def test_template_rejects_source_bound_baselines_and_nested_evidence(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        study=economic(client,'funded')
        settings=dict(economic_studies=[study],baselines=[dict(id='Bound source',phase='funded',
            source_configuration_id='a'*64,profile=study['profiles'][0],policy=study['policies'][0],required=True)])
        response=client.post(BASE+'/templates',json=dict(kind='nested',name='Source-bound reference',settings=settings))
        assert response.status_code==422 and ('baseline' in response.text.lower() or 'extra' in response.text.lower()),response.text
        leaked=deepcopy(study);leaked['search_settings']['report_sha256']='a'*64
        response=client.post(BASE+'/templates',json=dict(kind='nested',name='Nested authority',settings=dict(economic_studies=[leaked])))
        assert response.status_code==422,response.text


@pytest.mark.parametrize('key,value',[
    ('report_sha256','a'*64),('manifest_sha256','a'*64),('artifact_sha256','a'*64),
    ('prior_access',dict(untouched=True)),('eligibility',dict(status='PASS')),
])
def test_template_nested_phase_settings_are_not_a_route_for_copied_authority(tmp_path,key,value):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        study=economic(client,'funded');study['search_settings'][key]=value
        response=client.post(BASE+'/templates',json=dict(name='Nested evidence',settings=dict(economic_studies=[study])))
        assert response.status_code==422,response.text


def test_catalogue_search_filters_pagination_and_opening_never_launches_workers(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset,job,records=save_grid(client)
        nested=[]
        for name in ('Workspace needle alpha','Workspace needle beta'):
            body=declaration(job,records);body['name']=name
            response=client.post(ROBUST,json=body);assert response.status_code==201,response.text
            nested.append(response.json()['campaign_id'])
        phases={}
        for phase in ('evaluation','funded'):
            response=client.post('/api/research-campaigns',json=phase_declaration(records[0],phase=phase))
            assert response.status_code==201,response.text
            phases[phase]=response.json()['campaign_id']
        drafts=[created(client,'/drafts',draft_body('Workspace needle draft '+str(i),declaration=draft_declaration(job,records))) for i in range(2)]
        before=client.get('/api/backtests').json()['total']
        forbid_execution(client,monkeypatch)
        first=client.get(BASE,params=dict(q='workspace needle',limit=1,offset=0));assert first.status_code==200,first.text
        total=first.json()['total'];assert total==4
        pages=[client.get(BASE,params=dict(q='workspace needle',limit=1,offset=i)).json() for i in range(total)]
        ids=[page['items'][0]['id'] for page in pages]
        assert len(ids)==len(set(ids))==4 and set(ids)==set(nested+[row['id'] for row in drafts])
        assert client.get(BASE,params=dict(q='workspace needle',limit=1,offset=total)).json()['items']==[]
        exact=client.get(BASE,params=dict(kind='phase',phase='evaluation',status='validated')).json()
        assert [row['id'] for row in exact['items']]==[phases['evaluation']]
        assert all(row['kind']=='nested' for row in client.get(BASE,params=dict(kind='nested')).json()['items'])
        assert all(row['kind']=='draft' for row in client.get(BASE,params=dict(kind='draft')).json()['items'])
        names=[row['name'].casefold() for row in client.get(BASE,params=dict(q='workspace needle',sort='name')).json()['items']]
        assert names==sorted(names)
        assert client.get(BASE,params=dict(q=records[0]['id'])).json()['total']==6
        assert client.get('/api/backtests').json()['total']==before
        for params in (dict(limit=101),dict(limit=0),dict(offset=-1),dict(kind='unknown'),dict(phase='unknown')):
            assert client.get(BASE,params=params).status_code==422,params


def test_deleted_draft_source_is_retained_visible_and_cannot_be_previewed(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset,job,records=save_grid(client)
        draft=created(client,'/drafts',draft_body('Editable source references',declaration=draft_declaration(job,records)))
        before=deepcopy(draft['declaration']);deleted=records[0]['id']
        assert client.delete('/api/backtests/'+deleted).status_code==204,'Drafts must not pin sources like immutable campaigns.'
        response=client.get(BASE+'/drafts/'+draft['id']);assert response.status_code==200,response.text
        changed=response.json();assert changed['declaration']==before
        assert deleted in json.dumps(changed['missing_sources'])
        preview=client.post(ROBUST+'/preview',json=dict(changed['declaration'],campaign_id=uuid4().hex))
        assert preview.status_code in (404,422),preview.text
        # Existing immutable campaign pinning remains independent of draft CRUD.
        response=client.post('/api/research-campaigns',json=phase_declaration(records[1]))
        assert response.status_code==201,response.text
        assert client.delete('/api/backtests/'+records[1]['id']).status_code==409
        assert client.delete(BASE+'/drafts/'+draft['id'],params=dict(revision=1)).status_code==204
        assert client.delete('/api/backtests/'+records[1]['id']).status_code==409


def test_grid_reference_reports_missing_non_anchor_trial_without_silent_membership_change(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset,job,records=save_grid(client)
        body=declaration(job,records)
        for key in ('campaign_id','confirmed_backtest_count','confirmed_economic_candidate_count'):
            body.pop(key,None)
        draft=created(client,'/drafts',draft_body('Complete declared grid',declaration=body))
        assert draft['source_summaries'][0]['id']==job['id']
        assert draft['source_summaries'][0]['selectable'] is True
        assert not draft['missing_sources']
        # A deleted non-anchor member cannot quietly turn the same grid ID into
        # an apparently complete, smaller candidate family on draft reopening.
        assert client.delete('/api/backtests/'+records[1]['id']).status_code==204
        restored=client.get(BASE+'/drafts/'+draft['id']).json()
        assert restored['declaration']==draft['declaration']
        assert restored['anchor_source']['selectable'] is True
        assert restored['source_summaries'][0]['selectable'] is False
        assert restored['missing_sources']
        preview=client.post(ROBUST+'/preview',json=dict(restored['declaration'],campaign_id=uuid4().hex))
        assert preview.status_code in (404,409,422),preview.text
        with client.app.state.runs.connect() as db:
            surviving_trial=db.execute("SELECT trial FROM optimization_trials WHERE optimization_id=? AND json_extract(payload,'$.run_id')=?",
                (job['id'],records[0]['id'])).fetchone()[0]
        subset=deepcopy(body);subset['sources'][0]['trials']=[surviving_trial]
        explicit=created(client,'/drafts',draft_body('Explicit surviving member',declaration=subset))
        assert explicit['source_summaries'][0]['selectable'] is True and not explicit['missing_sources']


def test_appending_an_oos_reference_to_draft_never_confers_is_admission(tmp_path):
    from alphaquest.backtest_api import run_backtest
    from alphaquest.backtest_requests import ExecutionSettings
    from alphaquest.research import dates_for,metadata
    from alphaquest.strategies.registry import get_strategy
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset,job,records=save_grid(client);parent=records[0];plan=parent['run_metadata']['research']['plan']
        attempt,fresh=client.app.state.research.reserve(plan,parent['id'],str(uuid4()));assert fresh
        strategy=get_strategy(parent['run_metadata']['strategy']['id'])
        oos=run_backtest(client.app.state.store,client.app.state.runs,attempt['run_id'],dataset,strategy,
            strategy.parameters(parent['run_metadata']['strategy']['parameters']),
            ExecutionSettings.model_validate(parent['execution_settings']).execution_config(dataset),dates_for(plan,'oos'),lambda *args:None,
            reuse_results=False,prop_analyses=None,research=metadata(plan,'oos',parent_run_id=parent['id'],
                attempt_id=attempt['id'],attempt_number=attempt['number']))
        client.app.state.research.finish(attempt['id'],'complete')
        body=draft_body('Append source draft',declaration=draft_declaration(job,records))
        saved=created(client,'/drafts',body)
        body['declaration']['sources'].append(dict(backtest_id=oos['id'],sizes=[1]));body['revision']=1
        response=client.put(BASE+'/drafts/'+saved['id'],json=body)
        assert response.status_code==200,response.text
        restored=response.json();assert oos['id'] in json.dumps(restored['declaration']['sources'])
        preview=client.post(ROBUST+'/preview',json=dict(restored['declaration'],campaign_id=uuid4().hex))
        assert preview.status_code in (409,422) and ('IS' in preview.text or 'in-sample' in preview.text.lower()),preview.text
        assert client.get('/api/backtests/'+oos['id']).json()['run_metadata']['research']['phase']=='oos'


def test_catalogue_latest_application_status_cannot_be_masked_by_old_completed_report(tmp_path,monkeypatch):
    """Seed durable worker states; this tests navigation, not fabricated results."""
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset,job,records=save_grid(client)
        response=client.post(ROBUST,json=declaration(job,records))
        assert response.status_code==201,response.text
        campaign=response.json()['campaign_id'];store=client.app.state.prop_analyses
        initial,current,final=[uuid4().hex for _ in range(3)]
        current_application,final_application=[uuid4().hex for _ in range(2)]
        with store.connect() as db:
            for id,created,status in ((initial,'2050-01-01T00:00:00+00:00','complete'),
                                     (current,'2050-01-02T00:00:00+00:00','complete'),
                                     (final,'2050-01-03T00:00:00+00:00','error')):
                db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',
                    (id,'a'*64,records[0]['id'],created,status,'Test worker state',None))
            db.execute('UPDATE robust_research SET analysis_id=? WHERE id=?',(initial,campaign))
            db.execute('INSERT INTO research_procedure_applications VALUES (?,?,?,?,?,?,0)',
                (final_application,campaign,'b'*64,'final_verification','{}',final))
        forbid_execution(client,monkeypatch)
        for prior_current in (False,True):
            if prior_current:
                with store.connect() as db:
                    db.execute('INSERT INTO research_procedure_applications VALUES (?,?,?,?,?,?,0)',
                        (current_application,campaign,'b'*64,'current_development','{}',current))
            for latest_status in ('error','running'):
                with store.connect() as db:db.execute('UPDATE analyses SET status=? WHERE id=?',(latest_status,final))
                response=client.get(BASE,params=dict(q=campaign,status=latest_status))
                assert response.status_code==200,response.text
                assert response.json()['total']==1,response.text
                row=response.json()['items'][0]
                assert row['campaign_status']=='complete'
                assert row['status']==latest_status and row['stage']=='final_verification_'+latest_status
                assert row['final_application']==dict(application_id=final_application,analysis_id=final,status=latest_status)
                assert row['next_action']['analysis_id']==final
                assert row['next_action']['kind']!='open_report'
                assert row['readiness']['status']=='NOT_ASSESSED'
                assert client.get(BASE,params=dict(q=campaign,status='complete')).json()['total']==0
                if prior_current:
                    assert row['current_application']['analysis_id']==current
        # A later current-development run is selected by its actual analysis
        # timestamp, not permanently hidden by the existence of a final attempt.
        with store.connect() as db:db.execute('UPDATE analyses SET created=? WHERE id=?',('2050-01-04T00:00:00+00:00',current))
        row=client.get(BASE,params=dict(q=campaign,status='complete')).json()['items'][0]
        assert row['stage']=='current_development_complete'
        assert row['next_action']['analysis_id']==current and row['next_action']['kind']=='open_report'


def test_catalogue_readiness_requires_report_seal_and_never_certifies_production(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        store=client.app.state.prop_analyses;workspace=client.app.state.research_workspace;id=uuid4().hex
        directory=store.root/id;directory.mkdir();report=directory/'report.json'
        report.write_text(json.dumps(dict(calculations=dict(recommendation=[dict(phase='funded',status='LOCAL_EVIDENCE_READY',
            production_qualified=True,evidence_blockers=[],model_blockers=['Synthetic model remains unverified'],operational_blockers=[])]))))
        assert workspace._readiness(id,'complete')['status']=='INTEGRITY_REVIEW_REQUIRED'
        with store.connect() as db:
            db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,NULL)',(id,'a'*64,'b'*32,'2050-01-01','complete',''))
            db.execute('INSERT INTO analysis_report_checks VALUES (?,?)',(id,json.dumps({'report.json':sha256(report.read_bytes()).hexdigest()})))
        result=workspace._readiness(id,'complete')
        assert result['status']=='LOCAL_EVIDENCE_READY' and result['production_qualified'] is False
        assert result['reasons']==['Synthetic model remains unverified']
        report.write_text('{}')
        assert workspace._readiness(id,'complete')['status']=='INTEGRITY_REVIEW_REQUIRED'
        with report.open('wb') as file:file.truncate(2*1024*1024+1)
        original_read=type(report).read_bytes
        def bounded_read(path):
            if path==report:pytest.fail('Catalogue attempted to read a report above its bounded projection limit')
            return original_read(path)
        monkeypatch.setattr(type(report),'read_bytes',bounded_read)
        result=workspace._readiness(id,'complete')
        assert result['status']=='REVIEW_REQUIRED' and result['production_qualified'] is False


def test_imported_trade_source_stays_inspectable_but_is_not_selectable_for_native_nested_research(tmp_path):
    from test_trade_imports import save as import_source
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        imported=import_source(client)
        assert imported['status']=='complete' and imported['run_metadata']['research']['phase']=='is'
        declaration=dict(source_backtest_id=imported['id'],sources=[dict(backtest_id=imported['id'],sizes=[1])])
        draft=created(client,'/drafts',draft_body('Inspect imported evidence',declaration=declaration))
        for summary in [draft['anchor_source'],*draft['source_summaries']]:
            assert summary['available'] is True and summary['selectable'] is False
            assert summary['source_kind']=='external_trade_export'
            assert 'native' in summary['reason'].lower()
        assert draft['missing_sources']
        assert client.get('/api/backtests/'+imported['id']).json()==imported
        response=client.post(ROBUST+'/preview',json=dict(draft['declaration'],campaign_id=uuid4().hex))
        assert response.status_code in (409,422),response.text


def test_catalogue_finds_any_linked_source_activity_report_and_pasted_link(tmp_path,monkeypatch):
    from test_research_campaigns import create,run
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset,job,records=save_grid(client)
        body=phase_declaration(records[0],phase='funded')
        body['sources']=[dict(optimization_id=job['id'],sizes=[1,3])]
        campaign=create(client,body);cid=campaign['campaign_id']
        saved=run(client,cid);aid=saved['analysis_id']
        job_draft=created(client,'/drafts',draft_body('Activity source draft',declaration={key:value for key,value in declaration(job,records).items() if key!='campaign_id'}))
        draft=created(client,'/drafts',draft_body(declaration=draft_declaration(job,records)))
        forbid_execution(client,monkeypatch)
        queries=[*[record['id'] for record in records],job['id'],aid,cid,str(UUID(cid)),cid.upper(),
                 f'http://localhost:8000/#backtests/report/{records[1]["id"]}',
                 f'DELETE /api/backtests/{records[1]["id"]} HTTP/1.1',
                 'consecutive green hold','consecutive_green_hold',dataset['name']]
        for q in queries:
            response=client.get(BASE,params=dict(q=q,kind='phase'))
            assert response.status_code==200,response.text
            row,=response.json()['items']
            assert row['id']==cid,q
            assert row['source_count']==2 and row['activity_count']==1
            assert row['strategies']==['consecutive_green_hold']
        assert client.get(BASE,params=dict(q=job['id'],kind='phase',phase='evaluation')).json()['total']==0
        assert client.get(BASE,params=dict(q=records[1]['id'],kind='draft')).json()['items'][0]['id']==draft['id']
        assert client.get(BASE,params=dict(q=job['id'],kind='draft')).json()['items'][0]['id']==job_draft['id']
        assert client.get(BASE,params=dict(q='nonexistent research',kind='phase')).json()['total']==0
