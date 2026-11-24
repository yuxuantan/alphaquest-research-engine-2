"""Entry priority is a declared model; diagnostic limitations never invent P&L."""
from dataclasses import replace
from decimal import Decimal as D

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.entry_protection import OCOEntryAmbiguity, ProtectionAmbiguity, evidence_names, LEGACY_VERSION
from alphaquest.execution import execute, Trade, ExecutionError
from alphaquest.strategy import EntryIntent, EntryProtection, StopEntriesIntent
from alphaquest.strategies.twin_continuation import TwinContinuation
from test_entry_protection_sensitivity import upload_case, upload_inconclusive_case, start_twin_broad
from test_twin_immediate_protection import EntryOnly, sample
from test_twin_continuation import config


class TwoEntries(EntryOnly):
    def __init__(self, oco='upper_entry_first', protection='adverse_first', target=10):
        self.oco_entry_policy = oco
        self.orders = StopEntriesIntent((
            (EntryIntent(1,'BO-L',timing='next_open',protection=EntryProtection(
                stop_price=D(90),target_distance=D(target),ambiguity_policy=protection)),D(110)),
            (EntryIntent(1,'BO-S',side='short',timing='next_open',protection=EntryProtection(
                stop_price=D(110),target_distance=D(target),ambiguity_policy=protection)),D(90))))
    def on_bar(self, bar, position):return self.orders if bar.bar_number == 1 else None


@pytest.mark.parametrize('oco,side,exit_price', [('upper_entry_first','long',90),('lower_entry_first','short',110)])
@pytest.mark.parametrize('protection', ['adverse_first','favorable_first'])
def test_two_sided_priority_and_immediate_exit_arithmetic(oco, side, exit_price, protection):
    events = list(execute(sample((100,130,70,105)),TwoEntries(oco,protection),
        replace(config(),slippage_ticks=0),capture_risk=True,capture_entry_protection=True))
    trades = [e for e in events if type(e) is Trade]
    assert len(trades) == 1  # The other parent was cancelled, not filled after exit.
    trade = trades[0]
    assert trade.side == side and trade.entry_reference_price == (110 if side == 'long' else 90)
    assert trade.entry_bar_number == trade.exit_bar_number == 2
    assert trade.net_pnl == (-402 if protection == 'adverse_first' else 198)
    assert trade.exit_fill_price == (exit_price if protection == 'adverse_first' else 120 if side == 'long' else 80)
    event = next(e for e in events if type(e) is OCOEntryAmbiguity)
    assert event.policy == oco and event.chosen_side == side and event.cancelled_side != side


def test_oco_priority_forces_stop_only_adverse_extreme_after_entry():
    events = list(execute(sample((100,115,85,112)),TwoEntries(protection='favorable_first',target=40),
        replace(config(),slippage_ticks=0),capture_entry_protection=True))
    trade = next(e for e in events if type(e) is Trade)
    assert trade.exit_reason == 'stop_loss' and trade.net_pnl == -402
    assert any(type(e) is OCOEntryAmbiguity for e in events)
    assert not any(type(e) is ProtectionAmbiguity for e in events)


def test_open_gap_winner_precedes_declared_entry_priority_and_unknown_policies_reject():
    trade = next(e for e in execute(sample((112,130,70,105)),TwoEntries('lower_entry_first'),
        replace(config(),slippage_ticks=0)) if type(e) is Trade)
    assert trade.side == 'long' and trade.entry_fill_price == 112
    with pytest.raises(ExecutionError,match='Both OCO entry stops touched on bar 2'):
        list(execute(sample((100,130,70,105)),TwoEntries('reject'),config()))
    with pytest.raises(ExecutionError,match='Unknown OCO'):
        list(execute(sample((100,130,70,105)),TwoEntries('best_profit'),config()))


def test_model_failure_is_inconclusive_but_primary_and_other_scenarios_survive(tmp_path, monkeypatch):
    original = TwinContinuation.on_bar
    def diagnostic_gap(self, bar, position):
        if self.entry_protection_policy == 'favorable_first' and bar.bar_number == 106:
            raise ExecutionError('Synthetic diagnostic holding-price gap')
        return original(self,bar,position)
    monkeypatch.setattr(TwinContinuation,'on_bar',diagnostic_gap)
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _, payload = upload_case(client)
        response = client.post('/api/backtests',json=payload)
        assert response.status_code == 201, response.text
        record = response.json(); saved = record['entry_protection_sensitivity']
        assert D(record['summary']['total_net_pnl']) == -47
        assert saved['status'] == 'inconclusive'
        assert saved['favorable_summary'] is None and saved['favorable_minus_primary_net_pnl'] is None
        assert saved['scenarios']['lower_adverse']['status'] == 'complete'
        for key in ('favorable','lower_favorable'):
            result = saved['scenarios'][key]
            assert result['status'] == 'inconclusive' and result['summary'] is None
            assert result['failure_location']['bar_number'] == 106
            assert result['reason'] == 'Synthetic diagnostic holding-price gap'
            assert result['artifacts_sha256'] == {} and result['artifact_kinds'] == {}
        assert client.get('/api/backtests/'+record['id']+'/exports/entry_protection_favorable_report').status_code == 404
        assert client.get('/api/backtests/'+record['id']+'/exports/entry_protection_sensitivity').status_code == 200
        assert client.post('/api/backtests',json=payload).json()['id'] == record['id']
        assert 'entry_protection_sensitivity.json' in evidence_names(record)


def test_primary_model_failure_and_diagnostic_implementation_errors_still_fail_closed(tmp_path, monkeypatch):
    original = TwinContinuation.on_bar
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _, payload = upload_case(client)
        def broken_primary(self,bar,position):
            if self.entry_protection_policy == 'adverse_first' and self.oco_entry_policy == 'upper_entry_first' and bar.bar_number == 106:
                raise ExecutionError('Synthetic primary gap')
            return original(self,bar,position)
        monkeypatch.setattr(TwinContinuation,'on_bar',broken_primary)
        response = client.post('/api/backtests',json=payload)
        assert response.status_code == 422 and 'Synthetic primary gap' in response.text
        assert client.get('/api/backtests').json()['total'] == 0
        def broken_diagnostic(self,bar,position):
            if self.entry_protection_policy == 'favorable_first': raise RuntimeError('Synthetic implementation error')
            return original(self,bar,position)
        monkeypatch.setattr(TwinContinuation,'on_bar',broken_diagnostic)
        response = client.post('/api/backtests',json=payload)
        assert response.status_code == 500
        assert client.get('/api/backtests').json()['total'] == 0


def test_real_diagnostic_holding_gap_does_not_block_flat_primary(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        raw,payload=upload_inconclusive_case(client)
        response=client.post('/api/backtests',json=payload)
        assert response.status_code == 201,response.text
        record=response.json();evidence=record['entry_protection_sensitivity']
        assert D(record['summary']['total_net_pnl']) == -47
        assert evidence['status'] == 'inconclusive'
        assert 'No session-close fill was invented' in evidence['scenarios']['favorable']['reason']
        assert evidence['scenarios']['favorable']['failure_location']['bar_number'] == 108
        assert evidence['scenarios']['favorable']['summary'] is None
        assert evidence['scenarios']['lower_adverse']['status'] == 'complete'
        assert client.get('/api/datasets/'+payload['dataset_id']+'/csv').content == raw


def test_oco_broad_worker_saves_all_four_models_and_screening_uses_primary(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        workflow, job, raw = start_twin_broad(client,oco=True)
        assert job['status'] == 'complete' and job['completed_trials'] == 2
        rows = client.get('/api/campaign-workflows/'+workflow['id']+'/broad/results').json()['items']
        assert [D(r['metrics']['total_net_pnl']) for r in rows] == [-412,-52]
        record = client.get('/api/backtests/'+rows[1]['run_id']).json()
        evidence = record['entry_protection_sensitivity']
        assert evidence['primary_oco_entry_policy'] == 'upper_entry_first'
        assert evidence['primary_ambiguities']['oco_ambiguous_entries'] == 1
        assert {key:D(s['summary']['total_net_pnl']) for key,s in evidence['scenarios'].items()} == {
            'favorable':D(338),'lower_adverse':D(-52),'lower_favorable':D(338)}
        for kind in record['artifacts']:
            if kind.startswith('entry_protection') or kind == 'entry_oco_ambiguities':
                assert client.get('/api/backtests/'+record['id']+'/exports/'+kind).status_code == 200
        assert D(rows[1]['screening']['metrics']['is_stress_net_profit']) == -57
        assert not rows[1]['qualifies']
        from alphaquest.optimization_cache import artifacts
        root = client.app.state.runs.root
        before = artifacts(root,record)
        path = root/record['id']/record['artifacts']['entry_protection_lower_adverse_entry_oco_ambiguities']
        content=path.read_bytes();path.write_bytes(content+b'\n')
        assert artifacts(root,record) != before
        assert client.get('/api/backtests/'+record['id']+'/exports/entry_protection_lower_adverse_entry_oco_ambiguities').status_code == 409
        path.write_bytes(content)
        assert client.get('/api/datasets/'+workflow['declaration']['dataset']['id']+'/csv').content == raw


def test_inconclusive_cost_stress_diagnostics_do_not_abort_broad_trial(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        workflow,job,_=start_twin_broad(client,diagnostic_gap=True)
        assert job['status']=='complete' and job['completed_trials']==1
        row=client.get('/api/campaign-workflows/'+workflow['id']+'/broad/results').json()['items'][0]
        assert D(row['metrics']['total_net_pnl'])==-52
        record=client.get('/api/backtests/'+row['run_id']).json()
        assert record['entry_protection_sensitivity']['status']=='inconclusive'
        stress=client.get('/api/backtests/'+record['is_screening']['cost_stress']['run_id']).json()
        assert D(stress['summary']['total_net_pnl'])==-57
        assert stress['entry_protection_sensitivity']['status']=='inconclusive'
        assert stress['entry_protection_sensitivity']['favorable_summary'] is None
        from alphaquest.workflow_criteria import verified_screening
        verified_screening(client.app.state.runs,record)


def test_historical_v1_evidence_does_not_require_new_oco_files():
    from alphaquest.entry_protection import scenario_artifacts, FILE
    names = scenario_artifacts('favorable',legacy=True)
    record = dict(entry_protection=dict(version=LEGACY_VERSION), artifacts=dict(
        entry_protection_ambiguities=FILE,entry_protection_sensitivity='entry_protection_sensitivity.json',**names),
        entry_protection_sensitivity=dict(version=LEGACY_VERSION,favorable_artifacts_sha256={name:'saved-hash' for name in names.values()}))
    expected = {FILE,'entry_protection_sensitivity.json',*names.values()}
    assert evidence_names(record) == expected
