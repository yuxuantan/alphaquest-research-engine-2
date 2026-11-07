"""Independent execution/cost oracles for real scenario reruns."""
from dataclasses import asdict, replace
from decimal import Decimal as D, localcontext
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from alphaquest.execution import EquityPoint, ExecutionError, Trade, execute
from alphaquest.execution_scenarios import (ExecutionScenario, FillAssumptions,
    execution_config_record, resolve_execution_scenario, restore_scenario_config, scenario_metadata)
from alphaquest.intratrade import IntratradeRisk
from alphaquest.strategy import BracketIntent, CloseIntent, EntryIntent
from alphaquest.reporting import json_value
from test_execution import bar, config
from test_next_bar_execution import Orders, prices


def scenario(**values):
    return ExecutionScenario(name='Declared stress', **values)


def replay(bars, schedule, alternative=None, baseline=None):
    settings, fills = resolve_execution_scenario(baseline or config(), alternative)
    strategy = Orders(schedule)
    events = list(execute(bars, strategy, settings, capture_risk=True, fill_assumptions=fills))
    return events, strategy


def trade(events):
    return next(event for event in events if type(event) is Trade)


def risk(events):
    return next(event for event in events if type(event) is IntratradeRisk)


def serialized(events):
    return json.dumps([asdict(event) for event in events], default=json_value, sort_keys=True)


@pytest.mark.parametrize('last', [prices(3, '90', '120', '80', '90'),
    prices(3, '115', '120', '80', '115'), prices(3, '100', '110', '94', '100'),
    prices(3, '100', '110', '96', '100')])
def test_default_assumptions_preserve_all_serialized_events_and_risk(last):
    schedule = {1: EntryIntent(2, 'entry', timing='next_open'), 2: BracketIntent(D(95), D(110))}
    bars = [bar(1), bar(2), last]
    original = list(execute(bars, Orders(schedule), config(), capture_risk=True))
    explicit, _ = replay(bars, schedule, scenario())
    assert serialized(original) == serialized(explicit)


def test_increased_commission_and_market_slippage_change_fills_and_costs_once():
    alternative = scenario(additional_commission_per_contract_per_side='1', additional_slippage_ticks=1)
    events, _ = replay([bar(1), bar(2, '102')], {1: EntryIntent(2, 'entry'), 2: CloseIntent('exit')}, alternative)
    actual = trade(events)
    # Two contracts, $10/point, .5 points per side, $2 fee per side.
    assert (actual.entry_fill_price, actual.exit_fill_price) == (D('100.50'), D('101.50'))
    assert (actual.reference_gross_pnl, actual.slippage_cost, actual.gross_pnl) == (40, 20, 20)
    assert (actual.total_commissions, actual.net_pnl) == (8, 12)
    assert events[-1].equity == 10012
    assert (risk(events).mae_upper, risk(events).mfe_upper, risk(events).net_pnl) == (14, 26, 12)
    assert config().commission_per_contract_per_side == 1  # Immutable baseline.


@pytest.mark.parametrize('short', [False, True])
@pytest.mark.parametrize('gap, expected_net', [(False, -124), (True, -224)])
def test_extra_stop_slippage_includes_gaps_and_risk_without_double_cost(short, gap, expected_net):
    last = prices(3, '90', '200', '80', '90') if gap else prices(3, '100', '101', '94', '100')
    if short:
        last = replace(last, open=200-last.open, high=200-last.low, low=200-last.high, close=200-last.close)
    schedule = {1: EntryIntent(2, 'entry', side='short' if short else 'long', timing='next_open'),
                2: BracketIntent(D(105), D(90)) if short else BracketIntent(D(95), D(110))}
    events, _ = replay([bar(1), bar(2), last], schedule, scenario(stop_extra_slippage_ticks=2))
    actual = trade(events)
    assert actual.exit_reason == 'stop_loss'
    assert actual.exit_fill_price == (D('110.75' if gap else '105.75') if short else D('89.25' if gap else '94.25'))
    assert actual.slippage_cost == 20  # Entry .25 + exit .75, times 2 contracts x $10.
    assert actual.total_commissions == 4 and actual.net_pnl == expected_net
    assert risk(events).net_pnl == expected_net and risk(events).mae_upper == -expected_net
    assert risk(events).exit_phase == ('open' if gap else 'stop')
    if gap:
        assert risk(events).mfe_upper == 0  # Later favorable bar prices were not held.


def test_reason_label_cannot_turn_an_ordinary_market_exit_into_a_stop():
    events, _ = replay([bar(1), bar(2, '102')], {1: EntryIntent(1, 'entry'), 2: CloseIntent('stop_loss')},
                       scenario(stop_extra_slippage_ticks=100))
    assert trade(events).exit_fill_price == D('101.75')
    assert trade(events).net_pnl == 13


@pytest.mark.parametrize('short', [False, True])
@pytest.mark.parametrize('opening,extreme,closed,filled', [
    ('100', '105', '104', False),       # A touch does not meet penetration.
    ('105.25', '105.25', '101', False), # Favorable gap still below the fill hurdle.
    ('100', '105.50', '104', True),
    ('105.25', '106', '104', True),     # Later intrabar penetration; fill at limit.
])
def test_limit_penetration_never_invents_a_touch_or_insufficient_gap_fill(short, opening, extreme, closed, filled):
    last = prices(3, opening, extreme, '96', closed)
    if short:
        last = replace(last, open=200-last.open, high=200-last.low, low=200-last.high, close=200-last.close)
    stop, target = (D(105), D(95)) if short else (D(95), D(105))
    events, strategy = replay([bar(1), bar(2), last],
        {1: EntryIntent(1, 'entry', timing='next_open', side='short' if short else 'long'), 2: BracketIntent(stop, target)},
        scenario(limit_penetration_ticks=2), config(slippage_ticks=0, commission_per_contract_per_side=D(0)))
    actual = trade(events)
    assert actual.exit_reason == ('take_profit' if filled else 'end_of_data')
    assert (strategy.observed[-1][1] is None) == filled
    assert actual.exit_fill_price == (target if filled else last.close)
    if filled:
        assert actual.net_pnl == 50
        assert risk(events).mfe_lower == D('55')  # Reached .5 beyond target before its limit fill.


@pytest.mark.parametrize('short', [False, True])
@pytest.mark.parametrize('improvement', [False, True])
def test_limit_opening_improvement_is_explicit_and_market_slippage_never_worsens_limit(short, improvement):
    last = prices(3, '106', '120', '80', '106')
    if short:
        last = replace(last, open=200-last.open, high=200-last.low, low=200-last.high, close=200-last.close)
    stop, target = (D(105), D(95)) if short else (D(95), D(105))
    events, _ = replay([bar(1), bar(2), last],
        {1: EntryIntent(1, 'entry', timing='next_open', side='short' if short else 'long'), 2: BracketIntent(stop, target)},
        scenario(limit_penetration_ticks=2, limit_price_improvement=improvement, additional_slippage_ticks=4))
    assert trade(events).exit_reason == 'take_profit'  # Known opening precedes the later stop touch.
    assert trade(events).exit_fill_price == (last.open if improvement else target)
    assert risk(events).exit_phase == 'open'


def test_stop_wins_when_gap_did_not_meet_limit_penetration_and_both_levels_touch_later():
    events, _ = replay([bar(1), bar(2), prices(3, '105.25', '106', '94', '100')],
        {1: EntryIntent(1, 'entry', timing='next_open'), 2: BracketIntent(D(95), D(105))},
        scenario(limit_penetration_ticks=2))
    assert trade(events).exit_reason == 'stop_loss' and trade(events).exit_fill_price == D('94.75')


def test_failed_limit_hurdle_does_not_extend_an_unrenewed_order():
    events, _ = replay([bar(1), bar(2), prices(3, '100', '105', '96', '104'), prices(4, '104', '120', '96', '103')],
        {1: EntryIntent(1, 'entry', timing='next_open'), 2: BracketIntent(D(95), D(105))},
        scenario(limit_penetration_ticks=2))
    assert trade(events).exit_reason == 'end_of_data' and trade(events).exit_reference_price == 103


def test_strategy_reacts_to_actual_changed_fill_instead_of_scaled_pnl():
    class FillSensitive:
        def on_bar(self, current, position):
            if current.bar_number == 1:
                return EntryIntent(1, 'entry')
            if position and position.entry_fill_price >= D('100.5'):
                return CloseIntent('changed_fill_policy')
        def on_finish(self, current, position):
            return CloseIntent('end') if position else None
    bars = [bar(1), bar(2, '102'), bar(3, '110')]
    baseline = config(slippage_ticks=0, commission_per_contract_per_side=D(0))
    original = list(execute(bars, FillSensitive(), baseline))
    adjusted, fills = resolve_execution_scenario(baseline, scenario(additional_slippage_ticks=2))
    stressed = list(execute(bars, FillSensitive(), adjusted, fill_assumptions=fills))
    assert trade(original).exit_bar_number == 3 and trade(original).net_pnl == 100
    assert trade(stressed).exit_bar_number == 2 and trade(stressed).net_pnl == 10


def test_scenario_cost_arithmetic_is_independent_of_ambient_decimal_precision():
    baseline = config(commission_per_contract_per_side=D('1.123456789123456789123456789'))
    alternative = scenario(additional_commission_per_contract_per_side='0.000000000000000000000000001')
    with localcontext() as context:
        context.prec = 2
        adjusted, _ = resolve_execution_scenario(baseline, alternative)
    assert adjusted.commission_per_contract_per_side == D('1.123456789123456789123456790')


@pytest.mark.parametrize('values', [dict(name=' '), dict(additional_slippage_ticks=True),
    dict(additional_slippage_ticks='1'), dict(stop_extra_slippage_ticks=-1), dict(limit_penetration_ticks=1.5),
    dict(limit_price_improvement='false'), dict(additional_commission_per_contract_per_side='NaN'),
    dict(additional_commission_per_contract_per_side='-1'), dict(additional_commission_per_contract_per_side=0.1),
    dict(random_fill_probability=.5)])
def test_scenario_contract_rejects_coercion_unknown_assumptions_and_invalid_costs(values):
    with pytest.raises(ValueError):
        ExecutionScenario(**dict(dict(name='stress'), **values))


def test_fill_assumptions_are_separate_and_strict():
    with pytest.raises(ValueError): FillAssumptions(stop_extra_slippage_ticks=True)
    with pytest.raises(ValueError): FillAssumptions(limit_price_improvement=1)
    with pytest.raises(ExecutionError, match='FillAssumptions'):
        list(execute([bar(1)], Orders({}), config(), fill_assumptions={}))


def test_default_cache_shape_unchanged_and_scenario_identity_isolated(monkeypatch):
    from alphaquest import backtest_cache
    monkeypatch.setattr(backtest_cache, 'engine_identity', lambda: 'fixed-code-identity')
    definition = SimpleNamespace(provenance=lambda parameters: dict(parameters=parameters))
    args = ({'id': 'source'}, definition, {'length': 1}, config(), 'dates', 'compact', False, False)
    expected = backtest_cache.digest(dict(engine='fixed-code-identity', dataset=args[0],
        strategy=definition.provenance(args[2]), execution=asdict(config()), dates='dates',
        detail='compact', compress=False, prop=None, research=None, market_benchmark=None))
    assert backtest_cache.key(*args) == expected
    assert backtest_cache.key(*args, execution_scenario=None) == expected
    assert backtest_cache.key(*args, execution_scenario=scenario()) != expected
    assert backtest_cache.key(*args, execution_scenario=scenario(stop_extra_slippage_ticks=1)) != backtest_cache.key(*args, execution_scenario=scenario())


def test_normal_saved_backtest_scenario_metadata_reuse_and_detailed_replay(tmp_path, monkeypatch):
    from alphaquest import backtest_api
    from alphaquest.backtest_data import DateRange
    from alphaquest.backtest_runs import RunStore
    from alphaquest.datasets import DatasetStore, validate_csv
    from alphaquest.strategies.registry import get_strategy
    raw = b'Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol\n01/05/2026,10:00,99,100,99,100,0,0,0\n01/05/2026,10:01,100,102,100,102,0,0,0\n'
    store = DatasetStore(tmp_path/'datasets.sqlite3')
    saved = store.save(raw, dict(validate_csv(raw, 'SYNTHETIC-scenario.csv'),
        instrument_settings=dict(tick_size='0.25', point_value='10')), 'SYNTHETIC execution scenario', 'SYNTHETIC')
    runs = RunStore(tmp_path)
    definition = get_strategy('consecutive_green_hold')
    parameters = definition.parameters(dict(green_bar_count=1, hold_minutes=1, contracts=2))
    baseline = config()
    alternative = scenario(additional_slippage_ticks=1, additional_commission_per_contract_per_side='1', stop_extra_slippage_ticks=2)
    args = (store, runs)
    def run(**kwargs):
        return backtest_api.run_backtest(*args, uuid4().hex, saved, definition, parameters,
            kwargs.pop('config', baseline), DateRange(), lambda *a: None, **kwargs)
    original = run()
    result = run(execution_scenario=alternative)
    assert original['id'] != result['id']
    assert 'execution_scenario' not in original['run_metadata']
    assert D(original['summary']['total_net_pnl']) == 26
    assert D(result['summary']['total_net_pnl']) == 12
    adjusted, _ = resolve_execution_scenario(baseline, alternative)
    assert result['execution_settings'] == execution_config_record(adjusted)
    metadata = result['run_metadata']['execution_scenario']
    assert metadata == scenario_metadata(baseline, alternative)
    assert restore_scenario_config(metadata) == (baseline, alternative)
    captured = (runs.root/result['id']/'trades.csv').read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(backtest_api, 'execute', lambda *a, **kw: pytest.fail('Saved scenario result was recomputed'))
        assert run(execution_scenario=alternative)['id'] == result['id']
    # Stored settings are already adjusted; reconstruct the saved baseline once.
    detailed = run(source_record=result, config=adjusted)
    assert detailed['summary'] == result['summary']
    assert detailed['run_metadata']['execution_scenario'] == metadata
    assert (runs.root/detailed['id']/'trades.csv').read_bytes() == captured
    with pytest.raises(ValueError, match='cannot override'):
        run(source_record=result, config=adjusted, execution_scenario=scenario())
    assert (runs.root/result['id']/'trades.csv').read_bytes() == captured
