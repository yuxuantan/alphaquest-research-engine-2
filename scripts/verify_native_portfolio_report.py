#!/usr/bin/env python3
"""Independent arithmetic audit of a normal Prop Sim portfolio evidence ZIP.

This inspects recorded inputs/events. It does not import or rerun the account
engine and does not certify provider rules, missing observations or future cash.
"""
import argparse
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json
from zipfile import ZipFile


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def verify(path):
    with ZipFile(path) as archive:
        report=json.loads(archive.read('report.json'))
        for filename,identity in report['files'].items():
            raw=archive.read(filename)
            assert len(raw)==identity['bytes'] and sha256(raw).hexdigest()==identity['sha256'],filename
    calc=report['calculations'];frozen=calc['frozen'];snapshot=dict(frozen);expected=snapshot.pop('sha256')
    assert sha256(canonical(snapshot).encode()).hexdigest()==expected,'frozen package identity'
    rows=calc['allocation_search'];best=max(Decimal(r['cash']['net_cash']) for r in rows)
    assert best>=0 and best==Decimal(frozen['is_net_cash']),'IS ranking including zero-purchase baseline'
    assert any(r['allocation']['placement']=='separate' and not any(r['allocation']['counts']) for r in rows),'baseline membership'
    summaries={}
    scenarios=dict(calc['results'])
    if calc.get('abstention_alternative'):scenarios['is_alternative']=calc['abstention_alternative']
    for name,result in scenarios.items():
        assert name=='is_alternative' or result['allocation']==frozen['allocation'],'OOS/full period cannot reselect'
        cash=result['cash'];fees=Decimal(0);received=Decimal(0);by_month=defaultdict(lambda:[Decimal(0),Decimal(0)])
        for event in result['cash_ledger']:
            fee=Decimal(event['paid_fee']);receipt=Decimal(event['trader_receipt']);fees+=fee;received+=receipt
            assert Decimal(event['cash_delta'])==receipt-fee
            assert Decimal(event['net_cash'])==received-fees
            assert Decimal(event['paid_this_month'])+Decimal(event['reserved_allowance'])<=Decimal(frozen['monthly_cap'])
            assert Decimal(event['available_allowance'])>=0
            by_month[event['month']][0]+=fee;by_month[event['month']][1]+=receipt
            if event['event']=='account_deduction':assert event['already_applied_by_account_owner'] and fee==receipt==0
        assert fees==Decimal(cash['paid_fees'])==Decimal(cash['paid_evaluation_fees'])+Decimal(cash['paid_activation_fees'])
        assert received==Decimal(cash['received_trader_cash']) and received-fees==Decimal(cash['net_cash'])
        assert Decimal(cash['pending_receipts'])==sum((Decimal(p['amount']) for p in result['pending_settlements'] if not p['received']),Decimal(0))
        for month in cash['monthly']:
            assert [Decimal(month['paid_fees']),Decimal(month['trader_receipts'])]==by_month[month['month']]
            assert Decimal(month['paid_fees'])<=Decimal(month['cap'])
        assert result['counts']['evaluation_attempts']==sum(e['event']=='evaluation_purchase' for e in result['cash_ledger'])
        previous={}
        for trade in result['trades']:
            direction=1 if trade['side']=='long' else -1
            gross=(Decimal(trade['exit_fill_price'])-Decimal(trade['entry_fill_price']))*direction*trade['contracts']*2
            assert gross==Decimal(trade['gross_pnl'])
            assert gross-Decimal(trade['total_commissions'])==Decimal(trade['net_pnl'])
            assert trade['entry']<=trade['exit']
            assert previous.get(trade['slot'],'')<=trade['entry'],'no overlapping positions in a slot'
            previous[trade['slot']]=trade['exit']
        for decision in result['sizing_decisions']:
            if decision.get('risk_budget') is None:continue
            budget=Fraction(Decimal(decision['risk_budget']));unit=Fraction(Decimal(decision['planned_risk_per_mnq']))
            requested=int(budget//unit);q=min(requested,*decision['caps'].values())
            policy=frozen[decision['phase']+'_sizing']
            if q<policy['minimum_contracts']:q=0
            assert requested==decision['requested_contracts'] and q==decision['quantity'],'whole-contract pre-entry risk budget'
            assert Decimal(decision['planned_total_risk'])<=Decimal(decision['risk_budget'])
        for account in result['accounts']:
            conservation=account.get('conservation')
            if conservation:
                assert Decimal(conservation['trading_net_pnl'])==Decimal(conservation['provider_equity_from_initial'])+Decimal(conservation['cumulative_gross_withdrawals'])+Decimal(conservation.get('prior_attempt_trading_net','0'))
        summaries[name]=dict(net_cash=cash['net_cash'],fees=str(fees),received=str(received),trades=len(result['trades']),sizing_decisions=len(result['sizing_decisions']),counts=result['counts'])
    return dict(status='passed',analysis_id=report['id'],allocation=frozen['allocation'],scenarios=summaries,
        interpretation='Recorded-event arithmetic, risk rounding, membership and frozen allocation checks; no provider or future-performance certification.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('evidence_zip');args=parser.parse_args()
    print(json.dumps(verify(args.evidence_zip),indent=2))
