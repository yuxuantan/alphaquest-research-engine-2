"""Independent entry-bar outcomes, whole-strategy replays and durable evidence."""
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal as D

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.execution import execute, Trade
from alphaquest.entry_protection import ProtectionAmbiguity, evidence_names, sensitivity_replay
from alphaquest.strategy import EntryIntent, EntryProtection, BracketIntent, CloseIntent
from alphaquest.strategies.twin_continuation import Parameters
from test_twin_immediate_protection import EntryOnly, sample
from test_twin_continuation import config, prices, breakout_rows, CT
from test_twin_continuation_api import csv_bytes, values
from research_fixtures import reserved_source


@pytest.mark.parametrize('short', [False, True])
@pytest.mark.parametrize('policy,reason,price,net', [
    ('adverse_first', 'stop_loss', 90, -402), ('favorable_first', 'take_profit', 120, 198)])
def test_both_possible_orders_apply_explicit_assumption_with_costs(short, policy, reason, price, net):
    rows = sample((100, 130, 85, 115))
    if short:
        rows = [replace(b, open=200-b.open, high=200-b.low, low=200-b.high, close=200-b.close) for b in rows]
    plan = EntryProtection(stop_price=D(110 if short else 90), target_distance=D(10), ambiguity_policy=policy)
    entry = EntryIntent(1, 'BO-S' if short else 'BO-L', side='short' if short else 'long', timing='next_open', protection=plan)
    events = list(execute(rows, EntryOnly(entry, D(90 if short else 110)), replace(config(), slippage_ticks=0),
                          capture_risk=True, capture_entry_protection=True))
    trade = next(e for e in events if type(e) is Trade)
    assert trade.exit_reason == reason and trade.exit_fill_price == (200-price if short else price)
    assert trade.net_pnl == net
    event = next(e for e in events if type(e) is ProtectionAmbiguity)
    assert event.policy == policy and event.assumed_outcome == reason and event.assumed_exit_net_pnl == net


def test_reported_real_failure_price_arithmetic_and_preentry_open_is_not_a_stop_fill():
    rows = sample(('14911.75', '14911.75', '14839.00', '14852.75'))
    for policy, expected_exit, expected_net in [('adverse_first', '14885.25', '-708.98'),
                                                 ('favorable_first', '14841.00', '176.02')]:
        plan = EntryProtection(stop_price=D('14885'), target_distance=D('8.8565040781918136064450161470555624218244871855929'), ambiguity_policy=policy)
        entry = EntryIntent(1, 'BO-S', side='short', timing='next_open', protection=plan)
        cfg = replace(config(), commission_per_contract_per_side=D('1.99'))
        trade = next(e for e in execute(rows, EntryOnly(entry, D('14850.25')), cfg) if type(e) is Trade)
        assert trade.entry_fill_price == D('14850')
        assert trade.exit_fill_price == D(expected_exit) and trade.net_pnl == D(expected_net)
        assert trade.entry_bar_number == trade.exit_bar_number == 2


def test_uncertain_stop_only_favorable_assumes_preentry_touch_but_certain_stop_still_exits():
    entry = EntryIntent(1, 'BO-L', timing='next_open', protection=EntryProtection(
        stop_price=D(90), target_distance=D(40), ambiguity_policy='favorable_first'))
    events = list(execute(sample((100, 115, 85, 112)), EntryOnly(entry, D(110)),
                          replace(config(), slippage_ticks=0), capture_entry_protection=True))
    trade = next(e for e in events if type(e) is Trade)
    assert trade.exit_reason == 'end_of_data' and trade.net_pnl == 38
    event = next(e for e in events if type(e) is ProtectionAmbiguity)
    assert event.assumed_outcome == 'remain_open' and event.assumed_exit_net_pnl is None
    events = list(execute(sample((100, 115, 85, 88)), EntryOnly(entry, D(110)),
                          replace(config(), slippage_ticks=0), capture_entry_protection=True))
    assert next(e for e in events if type(e) is Trade).exit_reason == 'stop_loss'
    assert not any(type(e) is ProtectionAmbiguity for e in events)


def test_invalid_policy_rejects():
    with pytest.raises(ValueError, match='ambiguity policy'):
        EntryProtection(stop_price=D(90), ambiguity_policy='guess')


def upload_case(client):
    raw, split = reserved_source(csv_bytes(breakout_rows()))
    response = client.post('/api/datasets', params=dict(filename='SYNTHETIC-entry-protection.csv',
        name='SYNTHETIC entry-bar sensitivity', symbol='NQ', source_timezone='UTC', tick_size='.25', point_value='20'), content=raw)
    assert response.status_code == 201, response.text
    p = Parameters(max_bars_back=0, use_momentum=False, bo_pivot_tf=15, bo_atr_period=1, bo_max_stop_mult=D('.25'))
    payload = dict(dataset_id=response.json()['id'], strategy_id='twin_continuation', strategy_parameters=values(p), sample_split=split,
        execution_settings=dict(initial_capital='10000', slippage_ticks=1, commission_per_contract_per_side='1'))
    return raw, payload


def upload_inconclusive_case(client):
    """Adverse entry exit is flat; favorable hold crosses a missing close bar."""
    rows = breakout_rows()
    later = rows[0].timestamp_utc + timedelta(days=1)
    rows.append(prices(108,later,120,121,119,120))
    raw, split = reserved_source(csv_bytes(rows))
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-diagnostic-gap.csv',
        name='SYNTHETIC diagnostic holding gap',symbol='NQ',source_timezone='UTC',tick_size='.25',point_value='20'),content=raw)
    assert response.status_code == 201,response.text
    p=Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1,
                 bo_max_stop_mult=D('.25'),bo_target_mult=D(0))
    return raw,dict(dataset_id=response.json()['id'],strategy_id='twin_continuation',strategy_parameters=values(p),sample_split=split,
        execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1'))


def campaign_source(oco=False, diagnostic_gap=False):
    """Seven session-aligned 6h swing candles, then one labeled breakout.

    The short last candle of session one is 300 minutes. No maintenance rows
    are invented. Range changes are 8,10,12,20,12,10,8; frozen ATR is between
    8 and 9. With .25 ATR cap the adverse stop rounds to 108, then slips to
    107.75. Entry 110.25, $20/point, $2 costs => -52; stress entry 110.50,
    stop 108.25 then 107.75 => -57. Target distance rounds to 17 points => 338.
    """
    ranges = [(104,96),(105,95),(106,94),(110,90),(106,94),(105,95),(104,96)]
    rows = []
    for day, count, offset in [(15,1380,0),(16,1080,4)]:
        start = datetime(2024,1,day,17,1,tzinfo=CT)
        for i in range(count):
            rows.append(prices(len(rows)+1,start+timedelta(minutes=i),100,*ranges[offset+i//360],100))
    end = rows[-1].timestamp_utc
    rows += [prices(len(rows)+1,end+timedelta(minutes=1),109,160,60 if oco else 99,111),
             prices(len(rows)+2,end+timedelta(minutes=2),120,160,119,126)]
    if diagnostic_gap:
        rows.append(prices(len(rows)+1,datetime(2024,1,17,17,1,tzinfo=CT),120,121,119,120))
    return reserved_source(csv_bytes(rows))


def start_twin_broad(client, workers=1, oco=False, diagnostic_gap=False):
    """Normal mechanics -> attested test checklist -> native IS Broad worker."""
    from test_campaign_mechanics import run_validation, checks
    from test_campaign_broad import start_grid
    raw, split = campaign_source(oco=oco,diagnostic_gap=diagnostic_gap)
    saved = client.post('/api/datasets',params=dict(filename='SYNTHETIC-twin-campaign.csv',
        name='SYNTHETIC Twin conservative campaign',symbol='NQ',source_timezone='UTC',tick_size='.25',point_value='20'),content=raw)
    assert saved.status_code == 201, saved.text
    body = dict(dataset_id=saved.json()['id'],strategy_id='twin_continuation',sample_split=split,
        execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1'))
    response = client.post('/api/campaign-workflows',json=body)
    assert response.status_code == 201, response.text
    workflow = response.json(); prefix = '/api/campaign-workflows/'+workflow['id']
    mechanics = run_validation(client,workflow)
    assert mechanics['report']['summary']['trades_taken'] == 1
    # Synthetic test attestation only; this is not measured MultiCharts parity.
    review = client.patch(prefix+'/review',json=checks(mechanics))
    assert review.status_code == 200, review.text
    confirmed = client.post(prefix+'/confirm',json=dict(revision=review.json()['review']['revision']))
    assert confirmed.status_code == 200, confirmed.text
    axes = {k:dict(start=v,end=v,step='0' if isinstance(v,str) else 0) for k,v in values(Parameters()).items()}
    axes['bo_max_stop_mult'] = dict(start='0',end='.25',step='.25')
    if diagnostic_gap:
        axes['bo_target_mult'] = dict(start='0',end='0',step='0')
        axes['bo_max_stop_mult'] = dict(start='.25',end='.25',step='0')
    job, _ = start_grid(client,prefix,dict(workers=workers,parameter_ranges=axes))
    return client.get(prefix).json(), job, raw


def test_campaign_workers_screen_only_conservative_and_verify_sensitivity(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        workflow, job, raw = start_twin_broad(client, workers=2)
        assert job['status'] == 'complete' and job['completed_trials'] == 2
        prefix = '/api/campaign-workflows/'+workflow['id']
        rows = client.get(prefix+'/broad/results').json()['items']
        assert [D(r['metrics']['total_net_pnl']) for r in rows] == [338,-52]
        report = client.get('/api/backtests/'+rows[1]['run_id']).json()
        assert D(report['entry_protection_sensitivity']['favorable_summary']['total_net_pnl']) == 338
        assert D(rows[1]['screening']['total_net_pnl']) == -52
        assert D(rows[1]['screening']['metrics']['is_stress_net_profit']) == -57
        assert not rows[1]['qualifies']  # Neither positivity nor insufficient history is rescued by diagnostic profit.
        stress = client.get('/api/backtests/'+report['is_screening']['cost_stress']['run_id']).json()
        assert stress['entry_protection']['assumed_stop_losses'] == 1
        assert D(stress['entry_protection_sensitivity']['favorable_summary']['total_net_pnl']) == 338
        from alphaquest.workflow_criteria import verified_screening
        verified_screening(client.app.state.runs, report)
        path = client.app.state.runs.root / stress['id'] / stress['artifacts']['entry_protection_favorable_trades']
        original = path.read_bytes(); path.write_bytes(original+b'\n')
        with pytest.raises(ValueError, match='artifacts'):
            verified_screening(client.app.state.runs, report)
        path.write_bytes(original)
        assert client.get('/api/datasets/'+workflow['declaration']['dataset']['id']+'/csv').content == raw


def test_normal_api_reports_downloads_reuse_detail_and_tamper(tmp_path):
    db = tmp_path / 'datasets.sqlite3'
    with TestClient(create_app(db)) as client:
        raw, payload = upload_case(client)
        response = client.post('/api/backtests', json=payload)
        assert response.status_code == 201, response.text
        record = response.json(); run = record['id']
        assert D(record['summary']['total_net_pnl']) == -47
        sensitivity = record['entry_protection_sensitivity']
        assert D(sensitivity['favorable_summary']['total_net_pnl']) == 318
        assert D(sensitivity['favorable_minus_primary_net_pnl']) == 365
        assert record['entry_protection']['ambiguous_entries'] == 1
        assert sensitivity['favorable_ambiguities']['assumed_take_profits'] == 1
        assert sensitivity['source_identity']['id'] == payload['dataset_id']
        assert client.get('/api/datasets/'+payload['dataset_id']+'/csv').content == raw
        assert client.get('/api/backtests').json()['total'] == 1  # Diagnostic is evidence inside its parent.
        for kind in record['artifacts']:
            if kind.startswith('entry_protection'):
                response = client.get(f'/api/backtests/{run}/exports/{kind}')
                assert response.status_code == 200, response.text
        before = client.get(f'/api/backtests/{run}/exports/report').content
        assert client.post('/api/backtests', json=payload).json()['id'] == run
        detail = client.post(f'/api/backtests/{run}/detailed')
        assert detail.status_code == 201, detail.text
        assert detail.json()['summary'] == record['summary']
        assert detail.json()['entry_protection_sensitivity']['favorable_summary'] == sensitivity['favorable_summary']
        assert client.get(f'/api/backtests/{run}/exports/report').content == before
        from alphaquest.optimization_cache import artifacts
        root = client.app.state.runs.root
        fingerprint = artifacts(root, record)
        assert evidence_names(record) <= fingerprint.keys()
        path = root / run / record['artifacts']['entry_protection_favorable_trades']
        original = path.read_bytes(); path.write_bytes(original+b'\n')
        assert client.get(f'/api/backtests/{run}/exports/entry_protection_favorable_trades').status_code == 409
        assert artifacts(root, record) != fingerprint
        path.write_bytes(original)
    with TestClient(create_app(db)) as client:
        assert client.get(f'/api/backtests/{run}/exports/report').content == before
        assert client.get(f'/api/backtests/{run}').json()['entry_protection_sensitivity'] == sensitivity


def test_sensitivity_cancellation_publishes_no_report(tmp_path):
    from alphaquest.backtest_api import prepare_backtest_report, BacktestStopped
    from alphaquest.backtest_data import DateRange
    from alphaquest.strategies.registry import get_strategy
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _, payload = upload_case(client)
        definition = get_strategy('twin_continuation')
        dataset = client.app.state.store.get(payload['dataset_id'])
        def progress(stage, done, total):
            if stage == 'entry_protection_sensitivity':
                raise BacktestStopped('test stop during diagnostic replay')
        with pytest.raises(BacktestStopped):
            prepare_backtest_report(client.app.state.store, tmp_path/'unpublished', dataset, definition,
                definition.parameters(payload['strategy_parameters']), config(), DateRange.parse('2024-01-15','2024-01-16'), progress)
        assert not (tmp_path/'unpublished').exists()
        assert client.get('/api/backtests').json()['total'] == 0


def test_unambiguous_immediate_and_legacy_timing_remain_distinct(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _, payload = upload_case(client)
        payload['strategy_parameters']['bo_max_stop_mult'] = '0'
        immediate = client.post('/api/backtests',json=payload)
        assert immediate.status_code == 201, immediate.text
        record = immediate.json()
        assert record['entry_protection']['ambiguous_entries'] == 0
        assert record['entry_protection_sensitivity']['favorable_summary'] == record['summary']
        payload['strategy_parameters']['immediate_protection'] = False
        legacy = client.post('/api/backtests',json=payload)
        assert legacy.status_code == 201, legacy.text
        assert 'entry_protection' not in legacy.json() and 'entry_protection_sensitivity' not in legacy.json()
        assert legacy.json()['run_metadata']['strategy']['session_flattening']['entry_protection_ambiguity_policy'] == 'not_applicable'


def test_full_replay_changes_later_position_gates_and_trade_count(tmp_path):
    """Stop-only ambiguity changes a later entry gate, not just the first P&L."""
    from types import SimpleNamespace
    from alphaquest.prepared_data import PreparedData, write_stream
    class Stateful:
        def __init__(self):
            self.entry_protection_policy = 'adverse_first'
            self.session_flattening = {}
        def on_bar(self, bar, position):
            if bar.bar_number in (1, 2) and position is None:
                from alphaquest.strategy import StopEntriesIntent
                return StopEntriesIntent(((EntryIntent(1, 'BO-L', timing='next_open', protection=EntryProtection(
                    stop_price=D(90), target_distance=D(40), ambiguity_policy=self.entry_protection_policy)), D(110)),))
            if position is not None: return BracketIntent(D(90), D(150))
        def on_finish(self, bar, position):return CloseIntent('end_of_data') if position else None
    rows = sample((100,115,85,112))
    rows.append(prices(3,rows[-1].timestamp_utc+timedelta(minutes=1),112,120,111,119))
    stream = tmp_path/'bars.bin'; write_stream(stream, rows)
    definition = SimpleNamespace(acceleration=None, execution_assumption='test-explicit-OHLC',
        create=lambda *a, **kw: Stateful())
    cfg = replace(config(), slippage_ticks=0)
    primary = [e for e in execute(rows, Stateful(), cfg) if type(e) is Trade]
    _, favorable = sensitivity_replay(tmp_path/'favorable',definition,None,cfg,
        PreparedData(stream,dict(row_count=3)),{},dict(symbol='NQ'),dict(strategy={}),None,lambda *a:None)
    assert len(primary) == 2 and sum(t.net_pnl for t in primary) == -264  # -402 then +138.
    assert favorable['summary']['trades_taken'] == 1
    assert favorable['summary']['total_net_pnl'] == 178  # One uninterrupted 110 -> 119 trade, minus $2.
