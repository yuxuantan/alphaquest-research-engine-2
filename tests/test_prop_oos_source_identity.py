"""Period-specific session audit output must not invalidate frozen OOS sources."""
from copy import deepcopy
from datetime import date
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from research_fixtures import ResearchClient
from alphaquest.app import create_app
from alphaquest.prop.phase_dispatch import implementations_compatible
from alphaquest.prop.phase_search import strategy_definition, saved_oos_period, check_candidates
from test_campaign_assessments import declaration, create, run
from test_prop_analysis_api import wait


def test_strategy_definition_retains_rules_and_does_not_mutate_audit():
    original = dict(id='vwap', source_sha256='code', parameters={'close_buffer_minutes':5},
        session_flattening=dict(calendar={'sha256':'calendar'}, lookahead=False,
            minutes_before_close=5, sessions=100, closed_sessions=1, early_close_sessions=3,
            examples=[{'date':'2024-01-15'}], early_close_examples=[{'date':'2024-01-15'}], plans_sha256='is-plan'))
    snapshot = deepcopy(original)
    later = deepcopy(original)
    later['session_flattening'].update(sessions=20, closed_sessions=0, early_close_sessions=1,
        examples=[], early_close_examples=[], plans_sha256='oos-plan')
    assert strategy_definition(original) == strategy_definition(later)
    assert original == snapshot
    for key, value in [('calendar', {'sha256':'different'}), ('lookahead', True), ('minutes_before_close',10), ('unknown_rule',True)]:
        changed = deepcopy(later); changed['session_flattening'][key] = value
        assert strategy_definition(original) != strategy_definition(changed)
    assert strategy_definition({'id':'plain'}) == {'id':'plain'}


def test_admission_revision_compatibility_is_exact_directed_and_preserves_hashes():
    from alphaquest.prop.evaluation_optimization import implementation_identity
    current = implementation_identity(); saved = deepcopy(current)
    saved['files']['phase_search.py'] = '5fae2e873d053ed8315225cc8f72a2ca2926a73974e784941f4637dc1ba76e0a'
    snapshot = deepcopy(saved)
    assert implementations_compatible(saved,current)
    assert not implementations_compatible(current,saved)
    previous = deepcopy(current)
    previous['files']['phase_search.py']='a078590de6c3f748e92b54775d900f8b7b9c5ec2ed4ab14b0e65ac94cfc3a051'
    assert implementations_compatible(previous,current)
    assert not implementations_compatible(current,previous)
    assert saved == snapshot
    assert current['files']['phase_search.py'] == sha256(Path('alphaquest/prop/phase_search.py').read_bytes()).hexdigest()
    for key in ('native_engine.py','evaluation_profiles.py','../strategies/vwap_pullback_risk_sizing.py','phase_search.py'):
        changed = deepcopy(current); changed['files'][key] = 'unknown revision'
        assert not implementations_compatible(saved,changed)
    changed = deepcopy(current); changed['numpy'] = 'different'
    assert not implementations_compatible(saved,changed)
    changed = deepcopy(current); del changed['files']['phase_search.py']
    assert not implementations_compatible(saved,changed)


def test_saved_oos_period_uses_covered_dates_inside_the_frozen_split():
    record = dict(period_start_utc='2025-01-02T15:00:00Z', period_end_utc='2025-01-03T20:00:00Z',
        run_metadata=dict(research=dict(plan=dict(oos_start='2025-01-01',oos_end='2025-01-10'))))
    snapshot = deepcopy(record)
    assert saved_oos_period(record) == dict(first_session='2025-01-02',last_session='2025-01-03')
    assert record == snapshot
    record['run_metadata']['research']['plan'].update(oos_start='2025-01-03',oos_end='2025-01-03')
    assert saved_oos_period(record) == dict(first_session='2025-01-03',last_session='2025-01-03')
    record['run_metadata']['research']['plan'].update(oos_start='2025-01-10',oos_end='2025-01-20')
    with pytest.raises(ValueError,match='no saved coverage'):
        saved_oos_period(record)


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_actual_calendar_strategy_frozen_oos_and_strict_mismatch_guards(tmp_path, monkeypatch, phase):
    from test_inferred_session_close import session_rows, retime, csv_bytes, request_body
    from alphaquest.prop.phase_dispatch import module_for
    def session(close):
        rows = session_rows(close=close)
        rows[122] = replace(rows[122],low=Decimal('110'),high=Decimal('120'))
        rows[123] = replace(rows[123],high=Decimal('131'),close=Decimal('120'))
        return rows
    rows = session((12,0)) + session((16,0))
    for day in (18,19,22):
        rows += [retime(row,date(2024,1,day)) for row in session((16,0))]
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset = client.post('/api/datasets', params=dict(filename='SYNTHETIC-calendar-IS-OOS.csv',
            name='SYNTHETIC VWAP session audit identity', symbol='NQ', source_timezone='UTC',tick_size='.25',point_value='20'),content=csv_bytes(rows))
        assert dataset.status_code == 201, dataset.text
        body = request_body(dataset.json()['id'],day_reset_time=700)
        body['sample_split'] = dict(mode='dates',is_start='2024-01-15',is_end='2024-01-16',oos_start='2024-01-17',oos_end='2024-01-22')
        response = client.post('/api/backtests',json=body)
        assert response.status_code == 201,response.text
        source = response.json()
        assert source['summary']['total_net_pnl'] == '586.00'
        request = declaration(source,phase=phase); request['sources'][0]['sizes'] = [20]
        if phase == 'funded':request['search_settings']['constraints'] = {}
        campaign = run(client,create(client,request)['campaign_id']); prefix='/api/research-campaigns/'+campaign['campaign_id']
        original = client.get(prefix+'/exports/report.json').content
        calc = json.loads(original)['calculations']; selected = calc['frontier'] if phase=='evaluation' else calc['ranking']
        assert len(selected) == 1,calc
        frozen = client.post(prefix+'/freeze',json=dict(candidate_ids=selected,rationale='Calendar audit output is period-specific; fixed rules retained.'))
        assert frozen.status_code == 200,frozen.text
        before = client.get(prefix+'/exports/frozen_package.json').content
        # OOS cannot call the selector, even though its audit statistics differ.
        with monkeypatch.context() as m:
            import traceback
            import alphaquest.backtest_api as backtests
            failures = []
            replay = backtests.run_backtest
            def checked_replay(*args, **kwargs):
                try:
                    return replay(*args, **kwargs)
                except Exception:
                    failures.append(traceback.format_exc())
                    raise
            m.setattr(backtests,'run_backtest',checked_replay)
            m.setattr(module_for(phase),'pareto_sort' if phase=='evaluation' else 'rank_candidates',lambda *a,**k:pytest.fail('OOS reselected'))
            assessment = client.post(prefix+'/assessments',json=dict(request_id=uuid4().hex))
            assert assessment.status_code == 202,assessment.text+'\n'+'\n'.join(failures)
            job = wait(client,assessment.json()['analysis_id']); assert job['status']=='complete',job
        response = client.get('/api/prop-analyses/'+job['id']+'/downloads/report.json'); report=response.json()
        observed = report['calculations']['candidates'][0]['manifest']['source']['backtest']
        old = source['run_metadata']['strategy']; new = observed['run_metadata']['strategy']
        assert old != new and strategy_definition(old) == strategy_definition(new)
        assert old['session_flattening']['sessions'] == 2
        assert new['session_flattening']['sessions'] == 3
        assert report['request']['candidates'][0]['period'] == dict(first_session='2024-01-18',last_session='2024-01-22')
        assert observed['summary']['total_net_pnl'] == '879.00'
        assert report['calculations']['selection_status'] == 'assessment_only_no_reselection'
        assert report['calculations']['winner'] is None
        assert client.get(prefix+'/exports/report.json').content == original
        assert client.get(prefix+'/exports/frozen_package.json').content == before
        search = module_for(phase).parse_request(report['request'])
        import alphaquest.prop.phase_search as admission
        source_record = admission.source_record
        changes = [
            lambda r:r['run_metadata']['research'].update(parent_run_id=uuid4().hex),
            lambda r:r['run_metadata']['strategy']['parameters'].update(close_buffer_minutes=10),
            lambda r:r['run_metadata']['strategy'].update(source_sha256='changed'),
            lambda r:r['run_metadata']['dataset'].update(sha256='changed'),
            lambda r:r['execution_settings'].update(commission_per_contract_per_side='99'),
            lambda r:r['run_metadata']['research']['plan'].update(is_start='2024-01-14'),
            lambda r:r['run_metadata']['strategy']['session_flattening']['calendar'].update(sha256='changed'),
            lambda r:r['run_metadata']['strategy']['session_flattening'].update(minutes_before_close=10),
            lambda r:r['run_metadata']['strategy']['session_flattening'].update(lookahead=True),
        ]
        for change in changes:
            def altered(runs,id):
                record = deepcopy(source_record(runs,id)); change(record); return record
            with monkeypatch.context() as m:
                m.setattr(admission,'source_record',altered)
                with pytest.raises(ValueError,match='frozen'):
                    check_candidates(client.app.state.runs,search,report['assessment'])
        if destination:=os.environ.get('ALPHAQUEST_OOS_AUDIT_EVIDENCE_DIR'):
            folder=Path(destination)/phase; folder.mkdir(parents=True,exist_ok=True)
            for name,content in [('is-report.json',original),('frozen-package.json',before),('oos-report.json',response.content),
                    ('oos-evidence.zip',client.get('/api/prop-analyses/'+job['id']+'/downloads/analysis.zip').content)]:
                (folder/name).write_bytes(content)
