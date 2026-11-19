"""Shared native sizing admission: complete counters, independent quotes, strict clocks."""
from dataclasses import replace
from datetime import timedelta, timezone
from decimal import Decimal as D

import pytest

from test_native_account_execution import owner,bar
from alphaquest.prop.native_control import KnownEntryProposal,ExecutionSnapshot


@pytest.mark.parametrize('capture',[False,True])
@pytest.mark.parametrize('policy,quantity,budget',[
    (dict(kind='fixed_contracts',contracts=3),3,None),
    (dict(kind='fixed_dollar_risk',risk_dollars='100'),10,D(100)),
    (dict(kind='percentage_risk',risk_percent='.25',reference='initial_configured_capital'),12,D('125.00')),
    (dict(kind='percentage_risk',risk_percent='.001',reference='initial_configured_capital'),0,D('.50000')),
])
def test_capture_modes_preserve_every_quote_and_exact_totals(capture,policy,quantity,budget):
    values=[bar(1),bar(2)];control=owner(values,policy);control.set_detail_capture(capture)
    snapshot=ExecutionSnapshot(values[0].timestamp_utc,1,D(10000),D(10000),None)
    control.begin_session(next(iter(control.contexts.values())),snapshot)
    proposal=KnownEntryProposal(snapshot.timestamp_utc,1,'long','next_open',D(100),D(95),snapshot.timestamp_utc,'test',None)
    for index in range(20):
        accepted=control.admit_entry(proposal,snapshot,provisional=True)
        assert accepted.opportunity_id==index+1
        assert accepted.sizing_decision['quantity']==quantity
        if quantity:control.cancel_quoted_entry(accepted,snapshot,'refresh')
        # A consumer cannot mutate the next quote's cached sizing result.
        accepted.sizing_decision['caps']['provider']=0
        accepted.sizing_decision['reasons'].append('caller-only')
    summary=control.sizing_trace.summary
    assert summary['decision_count']==20
    assert summary['quantity_counts']=={str(quantity):20}
    assert 'caller-only' not in summary['reason_counts']
    assert control._event_counts['entry_admission']==20
    assert control._event_counts.get('entry_cancelled',0)==(20 if quantity else 0)
    assert control._sizing_budget==(budget*20 if budget is not None else D(0))
    assert control._sizing_admitted_risk==(D(10)*quantity*20 if budget is not None else D(0))
    assert len(control.events)==(1+20+(20 if quantity else 0) if capture else 0)
    assert len(control.sizing_trace.decisions)==(20 if capture else 0)


@pytest.mark.parametrize('capture',[False,True])
def test_cache_hits_recheck_actual_clocks_types_and_decimal_scale(capture):
    values=[bar(1),bar(2)];control=owner(values,dict(kind='fixed_dollar_risk',risk_dollars='100'))
    control.set_detail_capture(capture)
    snapshot=ExecutionSnapshot(values[0].timestamp_utc,1,D(10000),D(10000),None)
    control.begin_session(next(iter(control.contexts.values())),snapshot)
    proposal=KnownEntryProposal(snapshot.timestamp_utc,1,'long','next_open',D(100),D(95),snapshot.timestamp_utc,'test',None)
    accepted=control.admit_entry(proposal,snapshot,provisional=True);control.cancel_quoted_entry(accepted,snapshot,'refresh')
    for bad in [
        replace(proposal,initial_stop_known_at_utc=snapshot.timestamp_utc+timedelta(minutes=1)),
        replace(proposal,initial_stop_known_at_utc=snapshot.timestamp_utc.replace(tzinfo=None)),
        replace(proposal,initial_stop_known_at_utc=snapshot.timestamp_utc.astimezone(timezone(timedelta(hours=1)))),
        replace(proposal,decision_reference_price=D('100.'+'0'*65)),
        replace(proposal,decision_reference_price=D('NaN')),
        replace(proposal,side='invalid'),replace(proposal,timing='invalid'),
    ]:
        with pytest.raises(ValueError):control.admit_entry(bad,snapshot,provisional=True)
    control._last_exit=snapshot.timestamp_utc+timedelta(minutes=1)
    with pytest.raises(ValueError,match='prior actual trade'):control.admit_entry(proposal,snapshot,provisional=True)


def test_sizing_cache_keeps_recent_quotes_after_more_than_128_geometries(monkeypatch):
    import alphaquest.prop.sizing as sizing
    calls=[];original=sizing.choose_quantity
    def counted(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(sizing,'choose_quantity',counted)
    values=[bar(1),bar(2)];control=owner(values,dict(kind='fixed_dollar_risk',risk_dollars='100'))
    snapshot=ExecutionSnapshot(values[0].timestamp_utc,1,D(10000),D(10000),None)
    control.begin_session(next(iter(control.contexts.values())),snapshot)
    for index in range(130):
        reference=D(100)+index
        proposal=KnownEntryProposal(snapshot.timestamp_utc,1,'long','next_open',reference,reference-5,snapshot.timestamp_utc,'test',None)
        accepted=control.admit_entry(proposal,snapshot,provisional=True);control.cancel_quoted_entry(accepted,snapshot,'refresh')
    assert len(calls)==130 and len(control._quantity_cache)==128
    for _ in range(10):
        accepted=control.admit_entry(proposal,snapshot,provisional=True);control.cancel_quoted_entry(accepted,snapshot,'refresh')
    assert len(calls)==130 and control.sizing_trace.summary['decision_count']==140
    control.provider_cap=1
    assert control.admit_entry(proposal,snapshot,provisional=True).accepted_intent.contracts==1
    assert len(calls)==131


def test_cached_cash_and_orders_invalidate_on_offsets_floors_halts_and_decimal_scale():
    values=[bar(1),bar(2)];control=owner(values,dict(kind='fixed_contracts',contracts=1))
    initial=D(10000);snapshot=ExecutionSnapshot(values[0].timestamp_utc,1,initial,initial,None)
    control.begin_session(next(iter(control.contexts.values())),snapshot)
    first=control.risk_orders(snapshot)
    assert control.risk_orders(snapshot) is first
    for cash in [D('10000.00'),D('10000.000'),D('10001.01')]:
        changed=replace(snapshot,engine_trade_cash=cash);control._sync(changed)
        assert str(control.equity)==str(control.bridge.provider_equity(cash,initial))
    control.bridge.account_start_trading_net=D('100.00')
    control.bridge.cumulative_gross_withdrawals=D('20.000')
    control._sync(snapshot)
    assert str(control.equity)==str(control.bridge.provider_equity(initial,initial))
    orders=control.risk_orders(snapshot)
    assert str(orders.account_floor_engine_equity)==str(control.bridge.engine_barrier(control.account_floor,initial))
    control.account_floor=D('-1900.00');control.daily_floor=D('-1000.00')
    orders=control.risk_orders(snapshot)
    assert str(orders.account_floor_engine_equity)==str(control.bridge.engine_barrier(control.account_floor,initial))
    assert str(orders.daily_floor_engine_equity)==str(control.bridge.engine_barrier(control.daily_floor,initial))
    control._daily_halt=True
    assert control.risk_orders(snapshot).entry_allowed is False
