"""Specified selection properties from actual synthetic market-series reruns.

These tests do not claim a statistical test perfectly classifies finite random
samples. Every declaration, seed, change point and parameter family is fixed
before executing the ordinary dataset/grid/nested research workflow.
"""
from copy import deepcopy
from decimal import Decimal
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from research_property_fixtures import NOISE_SEEDS, market_bytes
from test_optimization import wait_job
from test_robust_research_api import PREFIX, declaration, run, save


def source_grid(client, kind, *, count=3, seed=7):
    raw, expected = market_bytes(kind, seed=seed)
    response = client.post('/api/datasets', params=dict(
        filename=f'SYNTHETIC-{kind}-seed{seed}.csv', name=f'SYNTHETIC property {kind}; sparse observed bars',
        source_timezone='America/Chicago', symbol='MNQ', tick_size='.25', point_value='2'), content=raw)
    assert response.status_code == 201, response.text
    response = client.post('/api/optimizations', json=dict(dataset_id=response.json()['id'],
        strategy_id='consecutive_green_hold', method='exhaustive', workers=1, automatic_prop=False,
        parameter_ranges=dict(green_bar_count=dict(start=1,end=1,step=0),
            hold_minutes=dict(start=1,end=count,step=1), contracts=dict(start=1,end=1,step=0)),
        execution_settings=dict(initial_capital='10000',tick_size='.25',point_value='2',slippage_ticks=0,
            commission_per_contract_per_side='0'), sample_split=dict(mode='dates',is_start='2026-01-05',
            is_end='2026-01-22',oos_start='2026-01-23',oos_end='2026-01-30')))
    assert response.status_code == 202,response.text
    job=wait_job(client,response.json()['id']);assert job['status']=='complete',job
    results=client.get('/api/optimizations/'+job['id']+'/results').json()['items']
    records=[client.get('/api/backtests/'+row['run_id']).json() for row in results]
    assert len(records)==count
    if expected:
        for record in records:
            hold=record['run_metadata']['strategy']['parameters']['hold_minutes']
            total=sum(Decimal(values[hold-1]) for day,values in expected.items() if day<='2026-01-22')
            assert Decimal(record['summary']['total_net_pnl'])==total
            trades=client.get('/api/backtests/'+record['id']+'/trades').json()
            assert trades['total']==14*(2 if kind=='regime' else 1)
            assert {int(t['contracts']) for t in trades['items']}=={1}
    return job,records


def research(client, job, records, tmp_path, *, label='base', **qualification):
    body=declaration(job,records)
    body['name']='SYNTHETIC market-series selection property '+label
    body['qualification'].update(additional_round_trip_cost='0',bootstrap_replicates=2000,
        bootstrap_seed=20261108,minimum_neighbor_pass_fraction=1.0)
    body['qualification'].update(qualification)
    return execute_declaration(client,body,tmp_path,label)


def execute_declaration(client,body,tmp_path,label):
    preview=client.post(PREFIX+'/preview',json=body);assert preview.status_code==200,preview.text
    assert not body.get('economic_studies')
    saved=run(client,save(client,body)['campaign_id'])
    report=client.get(PREFIX+'/'+saved['campaign_id']+'/exports/report.json')
    assert report.status_code==200,report.text
    (tmp_path/(label+'-request.json')).write_text(json.dumps(body,indent=2))
    (tmp_path/(label+'-report.json')).write_bytes(report.content)
    for fold in saved['result']['folds']:
        assert fold['outer_test_status']==fold['policy_selection_status']=='not_run'
        assert len(fold['qualification']['candidates'])==len(preview.json()['candidates'])
        assert 'winner' not in fold['qualification']
    return saved['result']


def rows(result, fold=0):
    return {c['parameters']['hold_minutes']:c for c in result['folds'][fold]['qualification']['candidates']}


def test_stable_market_region_keeps_every_neighbor_with_exact_price_arithmetic(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        job,records=source_grid(client,'stable')
        result=research(client,job,records,tmp_path)
        for fold in range(2):
            actual=rows(result,fold)
            assert {c['status'] for c in actual.values()}=={'PASS'}
            for hold,row in actual.items():
                assert Decimal(row['metrics']['mean_session_net'])==Decimal(8+2*hold)
                assert row['uncertainty']['lower']==row['uncertainty']['upper']==8+2*hold
                assert row['metrics']['validation_trades']==row['metrics']['validation_sessions']==4


@pytest.mark.parametrize('seed',NOISE_SEEDS)
def test_seeded_iid_noise_uses_saved_family_bounds_and_never_promotes_point_mean_alone(tmp_path,seed):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        job,records=source_grid(client,'noise',seed=seed)
        result=research(client,job,records,tmp_path,label=f'noise-{seed}')
        for fold in result['folds']:
            qualification=fold['qualification']
            assert qualification['multiplicity_family_size']==3
            assert qualification['historical_observation_count']==4
            assert not all(c['status']=='PASS' for c in qualification['candidates'])
            for row in qualification['candidates']:
                if row['uncertainty']:
                    assert row['uncertainty']['nominal_candidate_confidence_level']==pytest.approx(1-.05/3)
                if row['status']=='PASS':
                    assert row['uncertainty']['lower']>0
                    assert Decimal(row['metrics']['mean_session_net'])>0
                    assert row['parameter_stability']['neighbor_ids']
        assert any(Decimal(c['metrics']['mean_session_net'])>0 and c['status']!='PASS'
            for fold in result['folds'] for c in fold['qualification']['candidates'])
        # Exact repeat uses saved immutable result; random paths are never redrawn
        # until a favorable market or favorable qualification is encountered.
        report=json.loads((tmp_path/f'noise-{seed}-report.json').read_bytes())
        assert client.get('/api/prop-analyses/'+report['id']+'/downloads/report.json').content==(tmp_path/f'noise-{seed}-report.json').read_bytes()


def test_disappearing_market_signal_fails_predeclared_temporal_robustness(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        job,records=source_grid(client,'disappearing')
        result=research(client,job,records,tmp_path)
        for row in rows(result).values():
            assert row['status']=='FAIL',row
            assert 'too_few_profitable_inner_folds' in row['reasons']
        assert not result['folds'][0]['qualification']['approved_ids']


def test_isolated_profitable_market_parameter_cannot_be_its_own_stable_region(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        job,records=source_grid(client,'isolated')
        result=research(client,job,records,tmp_path)
        for fold in range(2):
            actual=rows(result,fold);peak=actual[2]
            assert [Decimal(actual[i]['metrics']['mean_session_net']) for i in (1,2,3)]==[-10,20,-10]
            assert peak['uncertainty']['lower']==20
            assert peak['status']=='FAIL' and 'unstable_parameter_region' in peak['reasons']
            assert set(peak['parameter_stability']['neighbor_ids'])=={actual[1]['candidate_id'],actual[3]['candidate_id']}
            assert not result['folds'][fold]['qualification']['approved_ids']


def test_regime_dependent_market_can_specialize_but_required_adverse_regime_blocks(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        job,records=source_grid(client,'regime',count=2)
        body=declaration(job,records)
        body['regimes']=dict(enabled_names=['us_session','europe_session'],lookback_bars=2,minimum_training_features=2)
        body['qualification'].update(additional_round_trip_cost='0',bootstrap_replicates=2000,
            bootstrap_seed=20261108,required_regimes=['us_session'],minimum_regime_sessions=4,minimum_regime_trades=4)
        result=execute_declaration(client,body,tmp_path,'specialized')
        for fold in result['folds']:
            for row in fold['qualification']['candidates']:
                assert row['status']=='PASS',row
                conditions={c['name']:c for c in row['market_conditions']}
                assert Decimal(conditions['us_session']['mean_session_net'])==20
                assert Decimal(conditions['europe_session']['mean_session_net'])==-2
                assert conditions['us_session']['status']=='PASS' and conditions['us_session']['required']
                assert conditions['europe_session']['status']=='FAIL' and not conditions['europe_session']['required']
            for evidence in fold['regime_evidence']:
                assert all(a['feature_asof'] is None or a['feature_asof']<a['entry_time'] for a in evidence['assignments'])
        required=deepcopy(body);required['campaign_id']=uuid4().hex
        required['qualification']['required_regimes']=['us_session','europe_session']
        rejected=execute_declaration(client,required,tmp_path,'both-required')
        assert all(not f['qualification']['approved_ids'] for f in rejected['folds'])
        assert all(c['status']=='FAIL' for f in rejected['folds'] for c in f['qualification']['candidates'])


def test_excessive_market_parameter_family_withholds_unresolved_tail_and_does_not_invent_samples(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        job,records=source_grid(client,'stable',count=6)
        sparse=research(client,job,records,tmp_path,label='unresolved-family',bootstrap_replicates=400)
        for fold in sparse['folds']:
            assert fold['qualification']['multiplicity_family_size']==6
            assert not fold['qualification']['approved_ids']
            assert all(c['status']=='INSUFFICIENT_EVIDENCE' and 'bootstrap_tail_resolution' in c['reasons']
                for c in fold['qualification']['candidates'])
        resolved=research(client,job,records,tmp_path,label='resolved-family',bootstrap_replicates=2000)
        for fold in resolved['folds']:
            assert len(fold['qualification']['approved_ids'])==6
            assert fold['qualification']['historical_observation_count']==4
            assert all(c['metrics']['validation_sessions']==c['metrics']['validation_trades']==4
                for c in fold['qualification']['candidates'])
