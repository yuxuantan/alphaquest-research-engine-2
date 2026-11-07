"""Independent native draw identities, actual fills and two-clock cash oracles."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from native_replay_fixtures import bars, parameters
from alphaquest.prop.native_draws import (build_catalogue, build_schedule, modeled_stamp,
    run_path, verify_catalogue, _hash)
from alphaquest.prop.native_control import SessionContext
from alphaquest.prop.funded_profiles import NativeFundedController
from alphaquest.prop.evaluation_profiles import NativeEvaluationController
from alphaquest.prop.phase_profiles import (FundedProfile, EvaluationProfile, SizingConfiguration,
                                           rule_version)
from alphaquest.prop.evaluation_optimization import SequentialRetry
from alphaquest.prop.phase_search import PhaseCalendar
from alphaquest.session_calendar import CT, load_calendar, session_date
from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
from alphaquest.strategy import ExecutionConfig

D = Decimal
CONFIG = ExecutionConfig(D(10000), D('.25'), D(2), 0, D(0))
CALENDAR = load_calendar(symbol='MNQ')


def open_days(first, count):
    result = []
    while len(result) < count:
        if first.weekday() < 5:
            result.append(first)
        first += timedelta(days=1)
    return result


def contexts(days, *, modeled=False, close_hour=None):
    result = {}
    for day in days:
        close = CALENDAR.plan(day, parameters().eod_flat_time, parameters().close_buffer_minutes).close.astimezone(timezone.utc)
        if close_hour is not None:
            close = datetime(day.year, day.month, day.day, close_hour, tzinfo=CT).astimezone(timezone.utc)
        beginning = datetime.combine(day-timedelta(days=1), datetime.min.time().replace(hour=17, minute=1), CT).astimezone(timezone.utc)
        count = int((close-beginning).total_seconds()/60)+1
        result[day] = SessionContext(day, close, 'test-modeled-calendar' if modeled else 'reviewed-source-calendar',
            CALENDAR.sha256, 0 if modeled else count, not modeled,
            kind='modeled' if modeled else 'observed', expected_bar_count=count if modeled else None)
    return result


def catalog(source=None, block=1):
    values = bars() if source is None else source
    days = sorted({session_date(b.timestamp_utc) for b in values})
    return build_catalogue(values, contexts(days), parameters(), block_sessions=block,
                           source_identity={'source_manifest_sha256':'a'*64, 'dataset_sha256':'b'*64})


def owner(target, *, phase='funded', fixed=None, percentage='.2'):
    policy = (dict(kind='fixed_contracts', contracts=fixed) if fixed else
              dict(kind='percentage_risk', risk_percent=percentage, reference='current_account_balance'))
    sizing = SizingConfiguration(policy, '50000', dict(tick_size='.25', point_value='2',
        entry_slippage_ticks=0, stop_exit_slippage_ticks=0, commission_per_contract_per_side='0'))
    common = dict(session_contexts=target, start_date=min(target), cutoff_date_exclusive=max(target)+timedelta(days=1))
    if phase == 'funded':
        return NativeFundedController(FundedProfile('apex-50k-eod', rule_version('apex-50k-eod')), sizing,
            40, **common, receipt_delay_calendar_days=2)
    return NativeEvaluationController(EvaluationProfile('apex-50k-eod', rule_version('apex-50k-eod'), '30', '40'),
        sizing, 40, **common, calendar=PhaseCalendar((str(min(target)),), str(max(target)+timedelta(days=2))),
        retry=SequentialRetry(activation_delay_sessions=0))


def schedule(catalogue, target, *, phase='funded', seed=3, path=0):
    return build_schedule(catalogue, target, parameters(), phase=phase, seed=seed,
                          path_index=path, start_date=min(target))


def chosen(catalogue, target, indices, *, phase='funded'):
    # Find a seeded schedule; never inject a hand-picked draw into execution.
    for seed in range(1000):
        value = schedule(catalogue, target, phase=phase, seed=seed)
        if [d['source_block_index'] for d in value['draws']] == indices:
            return value
    raise AssertionError('Fixture seed not found.')


def run(catalogue, plan, control, target, *, capture=True, config=CONFIG):
    return run_path(catalogue, plan, control,
        lambda: VwapPullbackRiskSizing(parameters(), execution_config=config, instrument_symbol='MNQ'),
        config, target, capture=capture)


def trades(output):
    return [event for block in output['captures'] for event in block['events'] if event['event_type']=='Trade']


def test_actual_source_draws_causal_warmup_and_exact_provider_continuation():
    source = catalog()
    target = contexts(open_days(date(2026, 3, 2), 3), modeled=True)
    plan = chosen(source, target, [0, 1, 2])
    output = run(source, plan, owner(target), target)
    actual = trades(output); result = output['result']
    assert [t['contracts'] for t in actual] == [10, 9, 5]
    assert [D(t['net_pnl']) for t in actual] == [D(-100), D(180), D(100)]
    assert D(result['trading_profit']) == D(result['equity']) == 180
    assert result['observation_kind'] == 'modeled' and 'historical_paths' not in result
    assert [m['warmup_bars'] for m in output['source_model_clock_mapping']] == [0, 1380, 2760]
    assert len(result['sizing_decisions']) == 3
    assert [t['entry_time_utc'][:10] for t in actual] == ['2026-01-05','2026-01-06','2026-01-07']
    assert [t['date'] for t in result['trace']] == ['2026-03-02','2026-03-03','2026-03-04']
    assert output['captures'][1]['original_source_rows'][0] == 1381
    assert source.metadata()['source_row_number_convention']=='one_based_admitted_selection_ordinal'
    assert output['captures'][1]['source_row_number_convention']=='one_based_admitted_selection_ordinal'
    assert output['captures'][1]['events'][0]['bar_number'] < 1380
    assert result['trace'][1]['source_session']=='2026-01-06'
    assert result['trace'][1]['target_session']=='2026-03-03'
    assert result['trace'][1]['draw_slot']==1
    assert all(row['path_index']==0 for row in result['control_events'])
    assert result['sizing_decisions'][1]['source_session']=='2026-01-06'


def test_repeated_nonmonotonic_source_dates_never_form_fake_chronological_history():
    source = catalog(); target = contexts(open_days(date(2026, 3, 2), 3), modeled=True)
    output = run(source, chosen(source, target, [1, 0, 1]), owner(target), target)
    actual = trades(output)
    assert [D(t['net_pnl']) for t in actual] == [D(200), D(-100), D(200)]
    assert actual[1]['entry_time_utc'] < actual[0]['entry_time_utc'] == actual[2]['entry_time_utc']
    assert D(output['result']['equity']) == 300


@pytest.mark.parametrize('block,count,expected', [(5,7,80), (10,13,200)])
def test_real_contiguous_blocks_reset_once_and_use_declared_final_prefix(block,count,expected):
    source = catalog(bars(days=block), block)
    target = contexts(open_days(date(2026, 3, 2), count), modeled=True)
    plan = schedule(source, target)
    assert len(source.blocks) == 1
    assert [d['used_sessions'] for d in plan['draws']] == [block, count-block]
    assert plan['draws'][-1]['leading_prefix_tail']
    output = run(source, plan, owner(target, fixed=1), target)
    assert D(output['result']['trading_profit']) == expected
    assert len(trades(output)) == count
    assert all(row['warmup_bars'] == 0 for row in output['source_model_clock_mapping'])


def test_phase_addressed_schedules_are_stable_and_do_not_share_opposite_phase_state():
    source = catalog(bars(days=6), 5)
    target = contexts(open_days(date(2026, 3, 2), 5), modeled=True)
    first = schedule(source, target)
    schedule(source, target, phase='evaluation', seed=999, path=20)
    schedule(source, target, phase='funded', seed=3, path=99)
    assert first == schedule(source, target)
    assert first['pools'][0]['indices'] == [0] # Tuesday->Monday cannot hide Fri->Mon gap shape.
    with pytest.raises(ValueError, match='independent phase'):
        schedule(source, target, phase='joint')
    with pytest.raises(ValueError, match='seed'):
        schedule(source, target, seed=True)


@pytest.mark.parametrize('prefix', [False, True])
def test_actual_bar_and_prefix_content_tamper_rejected_before_account_events(prefix):
    source = catalog(); target = contexts([date(2026, 3, 2)], modeled=True)
    plan = chosen(source, target, [1 if prefix else 0])
    values = list(source.bars)
    index = 0 if prefix else 960
    values[index] = replace(values[index], volume=D(2))
    mutated = replace(source, bars=tuple(values))
    control = owner(target)
    with pytest.raises(ValueError, match='content/prefix identity'):
        run(mutated, plan, control, target)
    assert control.events == []


def test_restored_schedule_rehash_cannot_bypass_modeled_shape_or_choice():
    source = catalog(); target = contexts([date(2026, 3, 2)], modeled=True)
    plan = schedule(source, target)
    changed = contexts([date(2026, 3, 2)], modeled=True, close_hour=12)
    with pytest.raises(ValueError, match='No complete source block'):
        run(source, plan, owner(changed), changed)
    tampered = {**plan, 'draws':[{**plan['draws'][0], 'source_block_index':999}]}
    tampered['schedule_sha256'] = _hash({k:v for k,v in tampered.items() if k!='schedule_sha256'})
    with pytest.raises(ValueError, match='schedule content'):
        run(source, tampered, owner(target), target)


def test_unknown_early_close_pool_and_civil_gap_are_rejections_without_redraw():
    source = catalog(bars(days=5), 5)
    with pytest.raises(ValueError, match='No complete source block'):
        schedule(source, contexts([date(2026, 3, 2)], modeled=True, close_hour=12))
    odd = contexts([date(2026, 3, 2), date(2026, 3, 4)], modeled=True)
    with pytest.raises(ValueError, match='civil-gap'):
        schedule(source, odd)


def test_source_target_context_roles_costs_and_source_window_are_strict():
    source = catalog(); day = date(2026, 3, 2)
    with pytest.raises(ValueError, match='explicitly modeled'):
        schedule(source, contexts([day]))
    with pytest.raises(ValueError, match='follow the admitted'):
        schedule(source, contexts([date(2026, 1, 6)], modeled=True))
    values = bars()
    with pytest.raises(ValueError, match='outside the permitted'):
        build_catalogue(values, contexts([date(2026, 1, 5)]), parameters(), block_sessions=1,
                        source_identity={'source':'identity'})
    target = contexts([day], modeled=True)
    with pytest.raises(ValueError, match='costs must exactly match'):
        run(source, schedule(source,target), owner(target), target, config=replace(CONFIG,slippage_ticks=1))


def test_mapping_preserves_chicago_clock_and_rejects_ambiguous_times():
    original = datetime(2026, 1, 5, 9, 1, tzinfo=CT).astimezone(timezone.utc)
    mapped = modeled_stamp(original, date(2026,1,5), date(2026,7,6))
    assert original.hour == 15 and mapped.hour == 14 and mapped.astimezone(CT).hour == 9
    ambiguous = datetime(2026,1,4,1,30,tzinfo=CT).astimezone(timezone.utc)
    with pytest.raises(ValueError, match='Ambiguous'):
        modeled_stamp(ambiguous,date(2026,1,5),date(2026,11,2))


def test_capture_limit_changes_no_actual_fills_or_account_math():
    source = catalog(); target = contexts([date(2026,3,2)], modeled=True); plan = schedule(source,target)
    detailed = run(source,plan,owner(target),target)
    compact = run(source,plan,owner(target),target,capture=False)
    assert compact['result'] == detailed['result']
    assert compact['captures'] == []


def test_evaluation_uses_same_actual_draw_law_with_all_fees_and_censoring():
    source=catalog(); target=contexts(open_days(date(2026,3,2),3),modeled=True)
    plan=chosen(source,target,[0,1,2],phase='evaluation')
    output=run(source,plan,owner(target,phase='evaluation'),target)
    assert [t['contracts'] for t in trades(output)] == [10,9,5]
    assert D(output['result']['paid_fees']) == 30
    assert D(output['result']['net_cash']) == -30
    assert output['result']['censored'] and not output['result']['acquisition_completed']
    assert 'cash_received' not in output['result']


def test_funded_repeated_source_payout_uses_model_dates_and_provider_gross_offset():
    source=catalog(bars(days=1,payout=True)); target=contexts(open_days(date(2026,3,16),7),modeled=True)
    output=run(source,schedule(source,target),owner(target,percentage='.06'),target)
    result=output['result']
    assert [t['contracts'] for t in trades(output)] == [3]*7
    assert [D(row['denominator_value']) for row in result['sizing_decisions']] == list(map(D,[50000,50900,51800,52700,53600,53000,53900]))
    assert D(result['trading_profit']) == 6300 and D(result['equity']) == 4800
    assert D(result['cash_received']) == D(result['gross_account_deductions']) == 1500
    assert result['payout_events'][0]['request_date'] == '2026-03-20'
    assert result['payout_events'][0]['receipt_date'] == '2026-03-22'
    assert all(t['entry_time_utc'][:10]=='2026-01-05' for t in trades(output))


def test_full_calendar_cutoff_binds_closed_day_receipts_and_cannot_be_changed_by_owner():
    source=catalog(bars(days=1,payout=True)); target=contexts(open_days(date(2026,3,16),5),modeled=True)
    short=schedule(source,target)
    control=owner(target,fixed=3)
    output=run(source,short,control,target)
    assert D(output['result']['cash_received']) == 0
    long=build_schedule(source,target,parameters(),phase='funded',seed=3,path_index=0,
        start_date=min(target),cutoff_date_exclusive=date(2026,3,23))
    assert short['schedule_sha256'] != long['schedule_sha256']
    control=owner(target,fixed=3)
    with pytest.raises(ValueError,match='exclusive cutoff'):
        run(source,long,control,target)
    control=NativeFundedController(control.profile,control.sizing,40,session_contexts=target,
        start_date=min(target),cutoff_date_exclusive=date(2026,3,23),receipt_delay_calendar_days=2)
    output=run(source,long,control,target)
    assert D(output['result']['cash_received']) == 1500
    assert output['result']['payout_events'][0]['receipt_date']=='2026-03-22'
