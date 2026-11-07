"""Synthetic canonical observations with independent causal sizing arithmetic.

Each of two explicit sessions repeats one-MNQ net outcomes [-10, +20, 0]
and decision-time stop distances [5, 5, 10] points. Source fees and slip are
explicitly zero. At $50,000, $100 planned risk gives [10, 10, 5]; 0.2% of
current balance gives [10, 9, 5] on the first simulated session, with
reference balances [50000, 49900, 50080]. Later sampled sessions compound.
These are fixture oracles, never claimed historical or future results.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from test_canonical_trades import envelope, raw


SESSIONS = ['2026-01-05', '2026-01-06']
FIRST_SESSION_IDS = [f'SYNTHETIC-2026-01-05-trade-{i}' for i in range(1, 4)]


def sizing_document():
    doc = envelope()
    doc['export_id'] = 'SYNTHETIC-causal-sizing-two-sessions'
    manifest = doc['manifest']
    manifest['initial_capital'] = '50000'
    manifest['strategy'].update(id='SYNTHETIC_causal_sizing', parameters={'example': 'three_causal_stops'})
    manifest['dataset']['name'] = 'SYNTHETIC causal sizing observations'
    manifest['research']['declaration'] = 'Synthetic arithmetic fixture; exported IS declaration only.'
    manifest['execution'].update(sizing_path_invariance='exporter_declared',
        assumptions=['SYNTHETIC: one-MNQ fills and ordered marks assumed invariant under supported size changes.',
                     'SYNTHETIC: zero commissions and zero slippage explicitly declared.'])
    trades, events = [], []
    for session in SESSIONS:
        for index, (net, stop, middle) in enumerate([('-10', '95', '97.5'), ('20', '95', '99.75'), ('0', '90', '99.75')], 1):
            opened = datetime.fromisoformat(session).replace(hour=15, tzinfo=timezone.utc)+timedelta(minutes=(index-1)*5)
            stamp = lambda delta: (opened+timedelta(seconds=delta)).isoformat().replace('+00:00', 'Z')
            closed_price = str(Decimal(100)+Decimal(net)/2)
            intermediate_net = str((Decimal(middle)-100)*2)
            values = [Decimal(0), Decimal(intermediate_net), Decimal(net)]
            minimum, maximum = min(values), max(values)
            times = [stamp(0), stamp(60), stamp(120)]
            trade_id = f'SYNTHETIC-{session}-trade-{index}'
            trades.append(dict(trade_id=trade_id, side='long', quantity=1,
                entry_time_utc=stamp(0), exit_time_utc=stamp(120),
                entry_reference_price='100', exit_reference_price=closed_price,
                entry_fill_price='100', exit_fill_price=closed_price,
                entry_commission='0', exit_commission='0', total_commissions='0',
                reference_gross_pnl=net, slippage_cost='0', gross_pnl=net, net_pnl=net,
                entry_reason='SYNTHETIC causal entry', exit_reason='SYNTHETIC observed close',
                entry_bar_number=None, exit_bar_number=None,
                sizing_decision=dict(timestamp_utc=stamp(-60), reference_price='100', execution_timing='next_open'),
                initial_stop=dict(price=stop, known_at_utc=stamp(-60), basis='strategy_decision'),
                stop_updates=[], excursions=dict(basis='observed_marks_net_equity',
                    mae=str(-minimum), mfe=str(maximum),
                    mae_time_utc=times[values.index(minimum)], mfe_time_utc=times[values.index(maximum)])))
            for sequence, (kind, mark, equity) in enumerate([('open', '100', '0'), ('mark', middle, intermediate_net), ('close', closed_price, net)], 1):
                events.append(dict(trade_id=trade_id, sequence=len(events)+1, timestamp_utc=times[sequence-1], kind=kind,
                    current_quantity=0 if kind=='close' else 1, mark_price=mark, stop_price=None,
                    cumulative_realized_gross=net if kind=='close' else '0', commissions_charged='0',
                    marked_trade_net_equity=equity))
    doc['payload'] = dict(trades=trades, risk_events=events)
    doc['completion'].update(trade_count=len(trades), event_count=len(events))
    return doc


def sizing_bytes():
    return raw(sizing_document(), indent=2)


def sizing_configuration(kind='fixed_dollar_risk', **policy_overrides):
    policy = dict(kind=kind, minimum_contracts=1, maximum_contracts=40,
                  constrain_to_account_cushion=False, constrain_to_daily_cushion=False)
    if kind == 'percentage_risk':
        policy.update(risk_percent='0.2', reference='current_account_balance')
    elif kind == 'fixed_contracts':
        policy['contracts'] = 10
    else:
        policy['risk_dollars'] = '100'
    policy.update(policy_overrides)
    return dict(policy=policy, initial_configured_capital='50000', planning_execution=dict(
        tick_size='0.25', point_value='2', entry_slippage_ticks=0,
        stop_exit_slippage_ticks=0, commission_per_contract_per_side='0'))
