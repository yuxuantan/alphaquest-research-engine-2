import pytest
from decimal import Decimal
from alphaquest.prop.sizing import choose_quantity

STATE = dict(initial_configured_capital='50000', equity_change_from_initial='0', account_floor_from_initial='-2000', daily_floor_from_initial='-1000', provider_max_contracts=20, user_max_contracts=40)
RISK = dict(sizing_decision_time_utc='2026-01-05T15:00:00Z', initial_stop_known_at_utc='2026-01-05T15:00:00Z', entry_time_utc='2026-01-05T15:01:00Z', execution_timing='next_open', side='long', decision_reference_price='100', initial_stop_price='95')
EXECUTION = dict(tick_size='.25', entry_slippage_ticks=1, stop_exit_slippage_ticks=2, commission_per_contract_per_side='.5')


def choose(policy, **state):
    return choose_quantity(policy, dict(STATE, **state), RISK, EXECUTION)


def test_exact_known_stop_cost_arithmetic_and_whole_rounding():
    # (5 points + .25 entry + .50 stop exit)*$2 + $1 round turn = $12.50.
    r=choose(dict(kind='fixed_dollar_risk', risk_dollars='50'))
    assert r['planned_risk_per_mnq']=='12.50' and r['quantity']==4
    assert r['planned_total_risk']=='50.00'
    assert choose(dict(kind='fixed_dollar_risk',risk_dollars='49.99'))['quantity']==3
    assert choose(dict(kind='fixed_dollar_risk',risk_dollars='12.49'))['action']=='skip'
    assert choose(dict(kind='fixed_dollar_risk',risk_dollars='50',minimum_contracts=5))['quantity']==0


def test_explicit_percentage_denominators_change_with_state():
    initial=dict(kind='percentage_risk',risk_percent='.1',reference='initial_configured_capital')
    current=dict(initial,reference='current_account_balance')
    assert choose(initial,equity_change_from_initial='-5000',account_floor_from_initial='-7000')['quantity']==4
    assert choose(current,equity_change_from_initial='-5000',account_floor_from_initial='-7000')['quantity']==3
    cushion=dict(kind='percentage_risk',risk_percent='2.5',reference='available_drawdown_cushion')
    assert choose(cushion,equity_change_from_initial='100',account_floor_from_initial='-1900')['quantity']==4
    assert choose(cushion,equity_change_from_initial='1100',account_floor_from_initial='-1900')['quantity']==6


def test_caps_and_strict_floor_guards_are_explicit():
    policy=dict(kind='fixed_dollar_risk',risk_dollars='50')
    assert choose(policy,provider_max_contracts=3)['quantity']==3
    assert choose(dict(policy,constrain_to_account_cushion=True),account_floor_from_initial='-50')['quantity']==3
    assert choose(dict(policy,constrain_to_daily_cushion=True),daily_floor_from_initial='-10')['quantity']==0
    assert choose(dict(policy,constrain_to_daily_cushion=True),daily_floor_from_initial=None)['quantity']==4
    assert choose_quantity(dict(kind='fixed_contracts',contracts=4),STATE)['quantity']==4


@pytest.mark.parametrize('mutation', [
    dict(initial_stop_known_at_utc='2026-01-05T15:00:01Z'),
    dict(sizing_decision_time_utc='2026-01-05T15:01:01Z'),
    dict(previous_source_exit_utc='2026-01-05T15:00:01Z'),
    dict(initial_stop_price='100'), dict(initial_stop_price='95.01'),
    dict(actual_entry_fill_price='110'), dict(execution_timing='observed_open'),
    dict(sizing_decision_time_utc='2026-01-04T22:59:00Z',initial_stop_known_at_utc='2026-01-04T22:59:00Z'),
])
def test_future_fill_and_unsupported_stop_or_decision_semantics_reject(mutation):
    with pytest.raises(ValueError):
        choose_quantity(dict(kind='fixed_dollar_risk',risk_dollars='50'),STATE,dict(RISK,**mutation),EXECUTION)


def test_stop_absence_only_blocks_policies_that_need_it():
    assert choose_quantity(dict(kind='fixed_contracts',contracts=2),STATE)['quantity']==2
    for policy in [dict(kind='fixed_dollar_risk',risk_dollars='50'),
                   dict(kind='fixed_contracts',contracts=2,constrain_to_account_cushion=True)]:
        with pytest.raises(ValueError,match='complete causal'):
            choose_quantity(policy,STATE)


def test_short_and_negative_prices_follow_the_same_planned_risk():
    r=choose_quantity(dict(kind='fixed_dollar_risk',risk_dollars='50'),STATE,
                      dict(RISK,side='short',decision_reference_price='-100',initial_stop_price='-95'),EXECUTION)
    assert r['quantity']==4 and r['planned_risk_per_mnq']=='12.50'


def test_percentage_balance_compounds_per_decision_and_fixed_dollars_do_not():
    # Synthetic starting capital $1,000, unit planned loss $10, risk 10%.
    # First +$20/unit earns $200; next -$25/unit loses $300.
    # Quantities are 10 -> 12 -> 9 at balances 1000 -> 1200 -> 900.
    state = dict(STATE, initial_configured_capital='1000')
    execution = dict(EXECUTION, entry_slippage_ticks=0, stop_exit_slippage_ticks=0,
                     commission_per_contract_per_side='0')
    policy = dict(kind='percentage_risk', risk_percent='10', reference='current_account_balance')
    equity, quantities, balances = Decimal(0), [], []
    for outcome_per_contract in [Decimal(20), Decimal(-25), Decimal(0)]:
        state['equity_change_from_initial'] = str(equity)
        decision = choose_quantity(policy, state, RISK, execution)
        quantities.append(decision['quantity'])
        balances.append(Decimal(decision['denominator_value']))
        equity += decision['quantity']*outcome_per_contract
        fixed = choose_quantity(dict(kind='fixed_dollar_risk', risk_dollars='100'), state, RISK, execution)
        assert fixed['quantity'] == 10
    assert quantities == [10, 12, 9] and balances == [1000, 1200, 900]
    assert equity == Decimal('-100')


def test_cushion_percentage_reflects_prior_profit_trail_updates_and_deductions():
    policy = dict(kind='percentage_risk', risk_percent='10', reference='available_drawdown_cushion')
    execution = dict(EXECUTION, entry_slippage_ticks=0, stop_exit_slippage_ticks=0,
                     commission_per_contract_per_side='0')
    decisions = [choose_quantity(policy, dict(STATE, equity_change_from_initial=equity,
        account_floor_from_initial=floor, provider_max_contracts=60, user_max_contracts=60), RISK, execution)
        for equity, floor in [('0', '-2000'), ('500', '-2000'), ('500', '-1500'), ('-300', '-1500')]]
    assert [d['quantity'] for d in decisions] == [20, 25, 20, 12]
    assert [Decimal(d['denominator_value']) for d in decisions] == [2000, 2500, 2000, 1200]


@pytest.mark.parametrize('cushion,expected', [('50', 3), ('50.0001', 4), ('49.9999', 3), ('0', 0), ('-1', 0)])
def test_planned_floor_guard_is_strict_without_floating_epsilon(cushion, expected):
    result = choose(dict(kind='fixed_dollar_risk', risk_dollars='100', constrain_to_account_cushion=True),
                    equity_change_from_initial=cushion, account_floor_from_initial='0')
    assert result['quantity'] == expected


def test_cap_ties_and_minimum_skip_reasons_are_saved_without_forcing_one_contract():
    result = choose(dict(kind='fixed_dollar_risk', risk_dollars='50', maximum_contracts=3), provider_max_contracts=3)
    assert result['quantity'] == 3 and set(result['reasons']) == {'policy_cap', 'provider_cap'}
    result = choose(dict(kind='fixed_dollar_risk', risk_dollars='100', minimum_contracts=5), provider_max_contracts=4)
    assert result['quantity'] == 0
    assert result['reasons'] == ['provider_cap', 'below_minimum_tradable_quantity']
    result = choose(dict(kind='fixed_contracts', contracts=2), user_max_contracts=0)
    assert result['quantity'] == 0 and result['action'] == 'skip'


@pytest.mark.parametrize('reference,state', [
    ('current_account_balance', dict(equity_change_from_initial='-50000')),
    ('current_account_balance', dict(equity_change_from_initial='-50001')),
    ('available_drawdown_cushion', dict(equity_change_from_initial='-2000')),
    ('available_drawdown_cushion', dict(equity_change_from_initial='-2001')),
])
def test_nonpositive_percentage_reference_skips(reference, state):
    result = choose(dict(kind='percentage_risk', risk_percent='1', reference=reference), **state)
    assert result['quantity'] == 0 and Decimal(result['risk_budget']) == 0


@pytest.mark.parametrize('policy', [
    dict(kind='fixed_contracts', contracts=True),
    dict(kind='fixed_contracts', contracts=1, risk_dollars='10'),
    dict(kind='fixed_contracts', contracts=1, minimum_contracts=2, maximum_contracts=1),
    dict(kind='fixed_contracts', contracts=1, constrain_to_account_cushion=1),
    dict(kind='fixed_dollar_risk', risk_dollars='0'),
    dict(kind='fixed_dollar_risk', risk_dollars='-1'),
    dict(kind='fixed_dollar_risk', risk_dollars='NaN'),
    dict(kind='fixed_dollar_risk', risk_dollars='unknown'),
    dict(kind='fixed_dollar_risk', risk_dollars='1e10000'),
    dict(kind='fixed_dollar_risk', risk_dollars=1.0),
    dict(kind='percentage_risk', risk_percent='1'),
    dict(kind='percentage_risk', risk_percent='101', reference='initial_configured_capital'),
    dict(kind='percentage_risk', risk_percent='1', reference='ambiguous_equity'),
])
def test_ambiguous_invalid_or_coerced_policies_reject(policy):
    with pytest.raises(ValueError): choose(policy)


@pytest.mark.parametrize('mutation', [
    dict(tick_size='0'), dict(tick_size='1e-1000000'), dict(point_value='20'),
    dict(commission_per_contract_per_side='-1'), dict(entry_slippage_ticks=True),
    dict(stop_exit_slippage_ticks=-1), dict(actual_exit_commission='2'),
])
def test_invalid_or_realized_execution_inputs_reject(mutation):
    with pytest.raises(ValueError):
        choose_quantity(dict(kind='fixed_dollar_risk', risk_dollars='50'), STATE, RISK, dict(EXECUTION, **mutation))


def test_actual_fill_is_rejected_even_when_a_fixed_policy_does_not_need_stop_risk():
    with pytest.raises(ValueError):
        choose_quantity(dict(kind='fixed_contracts', contracts=2), STATE, dict(RISK, actual_entry_fill_price='110'))
