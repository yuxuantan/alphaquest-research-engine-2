"""Adapt causal source metadata and current account state to pure MNQ sizing.

This module does not decide whether a source is invariant under changed sizes or
skips. Source admission must establish that capability before entering a kernel.
Original source timestamps describe templates; sampled sessions never rewrite or
compare them with timestamps from another sampled session.
"""
from decimal import Decimal
import math
from .sizing import DecisionRisk, SizingPolicy, PlanningExecution, choose_quantity, amount


def resolve_runtime(policy, context, trace):
    if policy is None:
        if context is not None or trace is not None:
            raise ValueError('Sizing context/trace requires an explicit sizing policy.')
        return None
    policy = SizingPolicy.model_validate(policy)
    if (type(context) is not dict
            or set(context)-{'initial_configured_capital', 'planning_execution', 'trace_context'}
            or 'initial_configured_capital' not in context):
        raise ValueError('Sizing context requires explicit initial configured capital and only supported fields.')
    capital = amount(context['initial_configured_capital'])
    if capital <= 0:
        raise ValueError('Initial configured capital must be positive.')
    execution = PlanningExecution.model_validate(context['planning_execution']) if context.get('planning_execution') is not None else None
    needs_stop = policy.kind != 'fixed_contracts' or policy.constrain_to_account_cushion or policy.constrain_to_daily_cushion
    if needs_stop and execution is None:
        raise ValueError('Risk sizing requires predeclared planning execution assumptions.')
    if trace is not None and not callable(trace):
        raise ValueError('Trace must be callable.')
    tags = context.get('trace_context', {})
    if type(tags) is not dict:
        raise ValueError('Trace context must be a dictionary.')
    return dict(policy=policy, capital=str(capital), execution=execution, trace=trace, tags=dict(tags), needs_stop=needs_stop)


def with_tags(context, **tags):
    return dict(context, trace_context={**context.get('trace_context', {}), **tags})


def decimal_float(value):
    if not math.isfinite(value):
        raise ValueError('Account state must be finite.')
    return format(Decimal(str(value)), 'f')


def whole_cap(value):
    if isinstance(value, bool) or int(value) != value:
        raise ValueError('Quantity ceilings require whole MNQ contracts.')
    return int(value)


def decision_risk_from_metadata(metadata):
    """Strict mapping of saved causal facts; actual fill prices are not inputs."""
    if metadata is None:
        raise ValueError('Risk sizing requires saved causal decision and initial-stop metadata.')
    allowed = {'source_trade_id', 'side', 'entry_time_utc', 'sizing_decision', 'initial_stop', 'previous_source_exit_utc'}
    if type(metadata) is not dict or set(metadata)-allowed:
        raise ValueError('Sizing metadata contains unsupported fields.')
    if not isinstance(metadata.get('source_trade_id'), str) or not metadata['source_trade_id']:
        raise ValueError('Sizing metadata requires a source trade identifier.')
    decision, stop = metadata.get('sizing_decision'), metadata.get('initial_stop')
    if decision is None or stop is None:
        raise ValueError('Risk sizing requires saved causal decision and initial-stop metadata.')
    if type(decision) is not dict or set(decision) != {'timestamp_utc', 'reference_price', 'execution_timing'}:
        raise ValueError('Sizing decision requires only timestamp, decision reference price and execution timing.')
    if type(stop) is not dict or set(stop) != {'price', 'known_at_utc', 'basis'} or stop['basis'] not in {'strategy_decision', 'submitted_order'}:
        raise ValueError('Initial stop requires price, known-at timestamp and a supported declared basis.')
    return DecisionRisk.model_validate(dict(
        sizing_decision_time_utc=decision['timestamp_utc'], initial_stop_known_at_utc=stop['known_at_utc'],
        entry_time_utc=metadata.get('entry_time_utc'), execution_timing=decision['execution_timing'],
        side=metadata.get('side'), decision_reference_price=decision['reference_price'], initial_stop_price=stop['price'],
        previous_source_exit_utc=metadata.get('previous_source_exit_utc')))


def before_trade(runtime, trade, equity, floor, daily_floor, provider_cap, user_cap, phase, session, index):
    metadata = None
    if len(trade) > 4:
        if len(trade) != 5 or type(trade[3]) is not bool or type(trade[4]) is not dict:
            raise ValueError('Sized day tuples require (net, adverse, path, payout_allowed, metadata).')
        metadata = trade[4]
    elif trade and isinstance(trade[-1], dict):
        raise ValueError('Sizing metadata must occupy tuple index 4; index 3 remains payout eligibility.')
    risk = decision_risk_from_metadata(metadata) if runtime['needs_stop'] else None
    state = dict(initial_configured_capital=runtime['capital'], equity_change_from_initial=decimal_float(equity),
        account_floor_from_initial=decimal_float(floor),
        daily_floor_from_initial=None if daily_floor == -float('inf') else decimal_float(daily_floor),
        provider_max_contracts=whole_cap(provider_cap), user_max_contracts=whole_cap(user_cap))
    decision = choose_quantity(runtime['policy'], state, risk, runtime['execution'])
    return dict({**runtime['tags'], 'phase': phase, 'session_index': session, 'opportunity_index': index},
        source_trade_id=metadata.get('source_trade_id') if metadata else None,
        decision_time_utc=risk.sizing_decision_time_utc if risk else None,
        decision=decision, state_before=state, quantity=decision['quantity'], action=decision['action'],
        requested_contracts=decision['requested_contracts'], caps=decision['caps'], reasons=decision['reasons'])


def finish_trace(runtime, record, equity, hit, outcome):
    if runtime['trace'] is not None:
        after = dict(record['state_before'], equity_change_from_initial=decimal_float(equity))
        runtime['trace'](dict(record, state_after=after, equity_after=after['equity_change_from_initial'],
            account_hit=int(hit), outcome=outcome))
