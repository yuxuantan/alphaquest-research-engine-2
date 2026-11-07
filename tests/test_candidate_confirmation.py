"""Full declared membership, automatic counts and explicit large-search consent."""
from copy import deepcopy
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.prop.phase_search import CandidateConfirmationRequired, require_candidate_confirmation
from alphaquest.research_campaigns import CampaignRequest, FreezeRequest
from test_optimization import wait_job
from test_prop_phases import phase_history
from test_research_campaigns import declaration, create, run


def saved_large_grid(client):
    response = client.post('/api/datasets', params=dict(filename='SYNTHETIC-candidate-confirmation.csv',
        name='SYNTHETIC 43-trial candidate confirmation', source_timezone='UTC', symbol='NQ',
        tick_size='.25', point_value='20'), content=phase_history(24))
    assert response.status_code == 201, response.text
    response = client.post('/api/optimizations', json=dict(dataset_id=response.json()['id'],
        strategy_id='consecutive_green_hold', method='exhaustive', workers=1, automatic_prop=False,
        parameter_ranges=dict(green_bar_count=dict(start=1,end=1,step=0),
            hold_minutes=dict(start=1,end=1,step=0),contracts=dict(start=1,end=43,step=1)),
        execution_settings=dict(initial_capital='10000000',slippage_ticks=0,commission_per_contract_per_side='0'),
        sample_split=dict(mode='dates',is_start='2026-01-05',is_end='2026-01-14',
            oos_start='2026-01-15',oos_end='2026-02-05')))
    assert response.status_code == 202, response.text
    job = wait_job(client,response.json()['id'])
    assert job['status'] == 'complete', job
    rows = client.get(f"/api/optimizations/{job['id']}/results?limit=100").json()['items']
    assert len(rows) == 43
    return client.get('/api/backtests/'+rows[0]['run_id']).json(),job,rows


def large_declaration(source, job, phase='evaluation'):
    body = declaration(source,phase=phase)
    body.pop('maximum_candidates')
    body['sources'] = [dict(optimization_id=job['id'], sizes=[10,11,12] if phase=='evaluation' else [3,4,5])]
    body['search_settings']['calendar'].pop('coverage_end')
    return body


@pytest.fixture(scope='module')
def large_library(tmp_path_factory):
    root=tmp_path_factory.mktemp('candidate-library')
    with TestClient(create_app(root/'datasets.sqlite3')) as client:
        yield client,*saved_large_grid(client),root


@pytest.mark.parametrize('count,confirmed,allowed',[(128,None,True),(129,None,False),
    (129,128,False),(129,129,True),(1000,1000,True),(128,127,False)])
def test_confirmation_threshold(count,confirmed,allowed):
    if allowed:
        require_candidate_confirmation(count,confirmed)
    else:
        with pytest.raises(CandidateConfirmationRequired) as error:
            require_candidate_confirmation(count,confirmed)
        assert error.value.detail['candidate_count'] == count


def test_no_request_list_or_freeze_ceiling_and_strict_confirmation():
    source='a'*32
    body=dict(campaign_id='b'*32,phase='evaluation',profile={},
        sources=[dict(backtest_id=source,sizes=[1])]*129,maximum_candidates=10000,
        is_window={},simulation={},sampling={},costs={},search_settings={})
    assert len(CampaignRequest(**body).sources) == 129
    body['sources']=[dict(optimization_id=source,trials=list(range(129)),sizes=[1])]
    assert len(CampaignRequest(**body).sources[0].trials) == 129
    assert len(FreezeRequest(candidate_ids=[str(i) for i in range(129)],rationale='All declared members.').candidate_ids) == 129
    for bad in (True,'129',0,-1):
        with pytest.raises(ValueError):
            CampaignRequest(**dict(body,confirmed_candidate_count=bad))


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_full_search_confirmation_boundaries_run_and_freeze(large_library,phase):
    client,source,job,rows,root=large_library
    body=large_declaration(source,job,phase)
    for confirmed in (None,128):
        attempt=deepcopy(body)
        if confirmed is not None:attempt['confirmed_candidate_count']=confirmed
        response=client.post('/api/research-campaigns',json=attempt)
        assert response.status_code == 409,response.text
        assert response.json()['detail']['candidate_count'] == 129
        assert client.get('/api/research-campaigns/'+body['campaign_id']).status_code == 404
    # Exactly 128 proceeds without confirmation and includes every selected member.
    boundary=deepcopy(body);boundary['campaign_id']=uuid4().hex
    trials=sorted(r['trial'] for r in rows)
    sizes=body['sources'][0]['sizes']
    boundary['sources']=[dict(optimization_id=job['id'],trials=trials[:-1],sizes=sizes),
        dict(optimization_id=job['id'],trials=trials[-1:],sizes=sizes[:2])]
    assert create(client,boundary)['manifest']['candidate_search_count'] == 128
    body['confirmed_candidate_count']=129
    campaign=create(client,body)
    assert campaign['manifest']['candidate_confirmation'] == dict(threshold=128,confirmed_count=129)
    assert len(campaign['manifest']['request']['candidates']) == 129
    saved=run(client,campaign['campaign_id'])
    result=client.get(f"/api/research-campaigns/{saved['campaign_id']}/exports/results.json").json()
    assert len(result['candidates']) == 129
    expected={(r['run_id'],size) for r in rows for size in sizes}
    actual={(c['manifest']['configuration']['source']['source_backtest_id'],c['manifest']['configuration']['micros']) for c in result['candidates']}
    assert actual == expected
    for candidate in result['candidates']:
        metrics=candidate['metrics']
        if phase=='evaluation':
            assert metrics['cost_per_funded'] == 70 and metrics['expected_calendar_days_to_funded'] == 2
        else:
            assert metrics['expected_payouts'] == metrics['expected_pending_cash'] == 1500
    selected=result['frontier'] if phase=='evaluation' else result['ranking']
    assert len(selected) == 129
    response=client.post(f"/api/research-campaigns/{saved['campaign_id']}/freeze",
        json=dict(candidate_ids=selected,rationale='Independent synthetic 129-member arithmetic.'))
    assert response.status_code == 200,response.text
    assert len(response.json()['candidate_ids']) == 129
    assert client.delete('/api/optimizations/'+job['id']).status_code == 409
    assert client.delete('/api/backtests/'+rows[0]['run_id']).status_code == 409
    # Confirmation is provenance, not a numerical input or cache discriminator.
    equivalent=deepcopy(body);equivalent['campaign_id']=uuid4().hex;equivalent['maximum_candidates']=1
    assert run(client,create(client,equivalent)['campaign_id'])['analysis_id'] == saved['analysis_id']
    assert create(client,body)['campaign_id'] == campaign['campaign_id']
    (root/(phase+'-verification.json')).write_text(json.dumps(dict(campaign_id=saved['campaign_id'],
        analysis_id=saved['analysis_id'],count=129,full_membership=True,frozen_count=len(selected)),indent=2))


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_direct_phase_apis_require_confirmation_and_preserve_resource_bounds(large_library,phase):
    client,source,job,rows,root=large_library
    body=large_declaration(source,job,phase);body['confirmed_candidate_count']=129
    raw=create(client,body)['manifest']['request']
    for endpoint in ('/api/prop-analyses/check','/api/prop-analyses'):
        response=client.post(endpoint,json=raw)
        assert response.status_code == 409 and response.json()['detail']['candidate_count'] == 129
    checked=client.post('/api/prop-analyses/check',json=dict(raw,confirmed_candidate_count=129))
    assert checked.status_code == 200 and len(checked.json()['candidates']) == 129
    too_large=deepcopy(raw)
    for c in too_large['candidates']:
        c['simulation']['simulations']=20000
        if phase=='evaluation':c['sampling']['chain_simulations']=20000
    response=client.post('/api/prop-analyses',json=dict(too_large,confirmed_candidate_count=129))
    assert response.status_code == 422 and 'report resource bound' in response.text


def test_legacy_saved_declaration_retries_without_new_default_fields(large_library):
    client,source,job,rows,root=large_library
    body=declaration(source)
    campaign=create(client,body)
    # Simulate the exact old JSON shape without rewriting its manifest or results.
    old=deepcopy(campaign['declaration']);old.pop('confirmed_candidate_count')
    with client.app.state.prop_analyses.connect() as db:
        db.execute('UPDATE research_campaigns SET declaration=? WHERE id=?',(json.dumps(old),body['campaign_id']))
    assert create(client,body)['declaration'] == old
