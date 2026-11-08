"""The full qualified native policy family is frozen before real outer bars."""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
from threading import Event
from time import monotonic
from uuid import uuid4

from alphaquest.app import create_app
from research_fixtures import ResearchClient
from test_native_replay_api import source,body as native_body
from test_robust_research_api import PREFIX


def native_nested_declaration(client,original):
    study=deepcopy(client.get(PREFIX+'/defaults').json()['economic_studies']['funded'])
    percent=native_body(client,original)['sizing']
    dollar=deepcopy(percent);dollar['policy']=dict(kind='fixed_dollar_risk',risk_dollars='100')
    study.update(policies=[dict(micros=40,sizing=dollar),dict(micros=40,sizing=percent)],
        simulation=dict(simulations=4,seed=1729,max_micros=40),sampling=dict(block_weekdays=1),
        costs=dict(mode='source',instrument='MNQ'))
    study['search_settings'].update(native_execution=dict(model='observed_contiguous_blocks_with_prior_prefix_v1',
        capture_paths=1,early_closes={}),receipt_delay_calendar_days=2)
    return dict(campaign_id=uuid4().hex,name='SYNTHETIC native full-policy nested arithmetic',
        source_backtest_id=original['id'],sources=[dict(backtest_id=original['id'],sizes=[1])],
        folds=dict(outer_train_sessions=5,outer_test_sessions=2,inner_train_sessions=1,inner_validation_sessions=2,
            mode='rolling',purge_sessions=0,embargo_sessions=0,minimum_inner_folds=2,minimum_outer_folds=2),
        qualification=dict(minimum_folds=2,minimum_sessions=4,minimum_trades=4,minimum_trades_per_fold=2,
            minimum_positive_fold_fraction=1.0,maximum_profit_concentration=.6,minimum_neighbors=0,
            bootstrap_replicates=400,bootstrap_block_sessions=1,confidence_level=.95,minimum_bootstrap_tail_samples=5),
        economic_studies=[study])


def test_native_inner_search_and_frozen_outer_rerun_use_complete_policy_family(tmp_path):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        # Two observed sessions per validation fold are required for the
        # declared one-session block bootstrap; increasing replicates cannot
        # substitute for those independent historical observations.
        original=source(client,days=9)
        request=native_nested_declaration(client,original)
        preview=client.post(PREFIX+'/preview',json=request);assert preview.status_code==200,preview.text
        assert preview.json()['economic_plan']['maximum_phase_candidates']==4
        created=client.post(PREFIX,json=request);assert created.status_code==201,created.text
        id=created.json()['campaign_id']
        launched=client.post(PREFIX+'/'+id+'/run');assert launched.status_code==202,launched.text
        deadline=monotonic()+120
        while monotonic()<deadline:
            row=client.get(PREFIX+'/'+id).json()
            if row['status'] not in ('queued','running'):break
            Event().wait(.05)
        assert row['status']=='complete',row
        folds=row['result']['folds'];assert len(folds)==2
        for fold in folds:
            selected=fold['economic_selection'];assert selected['status']=='SELECTION_FROZEN'
            assert len(selected['membership']['configuration_ids'])==1
            phase,=selected['phases'];assert phase['complete_search_candidate_count']==2
            assert len(phase['frozen_packages'])==2
            report=client.get(f"/api/prop-analyses/{phase['analysis_id']}/downloads/report.json").json()
            assert report['request']['native_execution']['horizon_calendar_days']==2
            assert len(report['calculations']['candidates'])==2
            for item in fold['chronological_replay']['items']:
                actual=item['result']
                assert actual['mode']=='native_historical_chronological_replay'
                assert actual['historical_paths']==1 and actual['horizon_observations_complete'] is True
                assert actual['frozen_binding']['package_sha256']==item['frozen_package_sha256']
                assert Decimal(actual['cash_received'])==Decimal(actual['pending_cash'])==0
                # Each actual later source session has a $10 unit risk / +$20 unit net.
                # Both $100 and0.2% balance policies submit10 contracts on each day.
                assert [d['quantity'] for d in actual['sizing_decisions']]==[10,10]
                assert Decimal(actual['trading_profit'])==400
                child=client.get('/api/backtests/'+item['outer_run_id']).json()
                assert child['native_account_control']
                assert child['run_metadata']['research']['selection_seal_sha256']==selected['selection_seal_sha256']
                assert client.delete('/api/backtests/'+child['id']).status_code==409
        raw=client.get(PREFIX+'/'+id+'/exports/report.json').content
        assert client.get(PREFIX+'/'+id+'/exports/report.json').content==raw
        (tmp_path/'native-nested-evidence.json').write_text(json.dumps(dict(source_id=original['id'],campaign_id=id,
            analysis_id=row['analysis_id'],request=request,library=str(tmp_path),report_sha256=sha256(raw).hexdigest(),
            expected=dict(outer_folds=2,complete_policy_candidates_per_fold=2,retained_family_per_fold=2,
                outer_quantities=[10,10],outer_trading_profit=400,outer_cash_received=0)),indent=2))
