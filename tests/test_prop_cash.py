"""Independent cash arithmetic, fixed-source path and calendar/budget boundaries."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import json

import pandas as pd
import pytest

from alphaquest.prop.cash_ledger import replay
from alphaquest.prop.native_analysis import resolved_settings


def cash_settings(**overrides):
    return resolved_settings(dict(ANALYSIS_MODE='budgeted_lifecycle',EVALUATION_MICROS='10',FUNDED_MICROS='3',
        COMMISSION_MODE='source',SLOTS='1',EVAL_PRICE='30',ACTIVATION_FEE='40',MONTHLY_CAP='100',
        BUDGET_TIMEZONE='America/Chicago',START_DATE='2026-01-05',HORIZON_END='2026-01-31',
        PAYOUT_RECEIPT_DAYS='30',PAYOUT_TIMING_ASSUMPTION='SYNTHETIC unverified: receipt 30 calendar days after request.',
        ACTIVATION_DEADLINE_DAYS='7',ACTIVATION_PAYMENT_DELAY_DAYS='0',
        ACTIVATION_TIMING_ASSUMPTION='SYNTHETIC unverified: deadline 7 calendar days after eligibility; pay immediately.',
        FEE_OVERRIDE_NOTE='SYNTHETIC $30/$40 fee overrides; not current provider prices.',**overrides))


def inputs(*, start='2026-01-05', periods=35, first_failure=True, funded_failure=True, net='3000'):
    grid=pd.bdate_range(start,periods=periods)
    rows={}
    for phase in ('evaluation','funded'):
        rows[phase]=[]
        for index,stamp in enumerate(grid):
            day=str(stamp.date());loss=3000 if phase=='evaluation' and index==0 and first_failure else 30000 if phase=='funded' and day=='2026-01-15' and funded_failure else 0
            rows[phase].append(dict(trade_id=index+1,entry_utc=day+'T18:01:00+00:00',exit_utc=day+'T18:02:00+00:00',quantity='1',
                source_net_pnl=net,export_net_pnl=None,measured_mae=str(loss),ohlc_adverse_path=json.dumps([[str(loss),True]] if loss else [])))
    source=dict(backtest=dict(id='a'*32))
    snap=dict(phase_sources=dict(evaluation=source,funded=source),phase_checks=dict(start_utc=rows['evaluation'][0]['entry_utc'],
        end_utc=rows['evaluation'][-1]['exit_utc'],first_session=str(grid[0].date()),last_session=str(grid[-1].date())))
    return snap,rows


def run(settings=None, **kwargs):
    return replay(*inputs(**kwargs), settings or cash_settings())


def assert_conservation(c):
    fees=receipts=Decimal(0)
    per_month={}
    for r in c['cash_ledger']:
        paid,received=Decimal(r['paid_fee']),Decimal(r['trader_receipt'])
        fees+=paid;receipts+=received
        per_month[r['month']]=per_month.get(r['month'],Decimal(0))+paid
        assert Decimal(r['cash_delta'])==received-paid
        assert Decimal(r['net_cash_to_date'])==receipts-fees
        assert Decimal(r['paid_this_month'])<=100
        assert Decimal(r['available_for_purchase'])>=0
        assert Decimal(r['remaining_allowance'])==100-Decimal(r['paid_this_month'])
    assert all(v<=100 for v in per_month.values())
    assert Decimal(c['cash_totals']['net_cash_within_horizon'])==receipts-fees


def test_exact_100_failed_then_passed_activation_block_and_late_receipt():
    c=run();assert_conservation(c)
    transactions=[(r['timestamp_budget'][:10],r['event'],r['paid_fee']) for r in c['cash_ledger'] if Decimal(r['paid_fee'])]
    assert transactions==[('2026-01-05','evaluation_purchase','30.00'),('2026-01-06','evaluation_purchase','30.00'),('2026-01-07','activation_payment','40.00')]
    assert c['cash_totals']==dict(received_trader_payouts='0.00',paid_evaluation_fees='60.00',paid_activation_fees='40.00',total_paid_fees='100.00',
        net_cash_within_horizon='-100.00',payout_evaluation_fee_multiple='0',pending_trader_receipts='1500.00',remaining_allowance='0.00',
        reserved_allowance='0.00',pending_activation_obligations='0.00',potential_evaluation_activation='0.00')
    assert [(r['timestamp_budget'][:10],r['reason'],r['reservation_delta']) for r in c['cash_ledger'] if r['event']=='reservation_released' and Decimal(r['amount'])]==[
        ('2026-01-05','account_breach','-40.00'),('2026-01-07','Activation payment consumes the obligation.','-40.00')]
    assert c['accounts'][0]['outcome']=='account_breach'
    assert c['accounts'][1]['funded_start']=='2026-01-08'
    assert c['accounts'][1]['outcome']=='account_breach'
    assert next(r for r in c['cash_ledger'] if r['event']=='purchase_blocked')['timestamp_budget'].startswith('2026-01-16')
    p=c['pending_receipts'][0]
    assert p['requested_at']=='2026-01-14T22:00:00+00:00' and p['receipt_due_at']=='2026-02-13T22:00:00+00:00'
    assert not any(r['event']=='trader_receipt' for r in c['cash_ledger'])


def test_month_reset_replaces_account_and_keeps_open_at_horizon():
    s=cash_settings();s['HORIZON_END']='2026-02-10'
    c=run(s);assert_conservation(c)
    assert [r['paid_fees'] for r in c['monthly_ledger']]==['100.00','70.00']
    assert [r['remaining_allowance'] for r in c['monthly_ledger']]==['0.00','30.00']
    assert c['accounts'][2]['purchased_at']=='2026-02-01T06:00:00+00:00'
    assert c['accounts'][2]['passed_on']=='2026-02-02' and c['accounts'][2]['funded_start']=='2026-02-04'
    assert c['accounts'][2]['outcome']=='funded_open' and c['accounts'][2]['closed_at'] is None
    assert c['cash_totals']['net_cash_within_horizon']=='-170.00'


def test_expiry_releases_reservation_without_refund_and_defers_purchase():
    s=cash_settings();s['ACTIVATION_PAYMENT_DELAY_DAYS']='8'
    c=run(s);assert_conservation(c)
    assert c['cash_totals']['total_paid_fees']=='60.00'
    assert not any(r['event']=='activation_payment' for r in c['cash_ledger'])
    assert next(r for r in c['cash_ledger'] if r['event']=='activation_expired')['timestamp_budget'].startswith('2026-01-14')
    assert any(r['event']=='reservation_released' and r['reason']=='activation_expired' and r['reservation_delta']=='-40.00' for r in c['cash_ledger'])
    assert any(r['event']=='purchase_blocked' and r['remaining_allowance']=='40.00' for r in c['cash_ledger'])


def test_pending_obligation_rereserved_on_reset_deadline_not_extended():
    s=cash_settings();s.update(START_DATE='2026-01-30',HORIZON_END='2026-02-10',ACTIVATION_PAYMENT_DELAY_DAYS='8')
    c=run(s,first_failure=False,funded_failure=False);assert_conservation(c)
    a=c['accounts'][0]
    assert a['eligible_at']=='2026-02-02T22:00:00+00:00' and a['activation_deadline']=='2026-02-09T22:00:00+00:00'
    feb=[r for r in c['cash_ledger'] if r['timestamp_budget'].startswith('2026-02-01')]
    assert any(r['event']=='activation_reserved' and r['reserved_allowance']=='40.00' and r['paid_this_month']=='0.00' for r in feb)
    assert c['monthly_ledger'][0]['unused_expired']=='70.00'  # Full unspent amount; reservation was not a fee.
    assert any(r['event']=='activation_expired' and r['timestamp_budget'].startswith('2026-02-09') for r in c['cash_ledger'])


@pytest.mark.parametrize('delay,activated', [('7',True),('8',False)])
def test_inclusive_activation_deadline(delay,activated):
    s=cash_settings();s['ACTIVATION_PAYMENT_DELAY_DAYS']=delay
    c=run(s)
    assert any(r['event']=='activation_payment' for r in c['cash_ledger']) is activated


def test_receipt_on_horizon_counts_and_after_exclusive_boundary_does_not():
    s=cash_settings();s['HORIZON_END']='2026-02-13'
    c=run(s);assert_conservation(c)
    assert c['cash_totals']['received_trader_payouts']=='1500.00'
    assert c['cash_totals']['total_paid_fees']=='170.00'
    assert c['cash_totals']['net_cash_within_horizon']=='1330.00'
    assert c['cash_totals']['payout_evaluation_fee_multiple']==str(Decimal(1500)/90)
    s['HORIZON_END']='2026-02-12'
    assert run(s)['cash_totals']['received_trader_payouts']=='0.00'


def test_payouts_do_not_expand_budget_and_zero_fees_multiple_unavailable():
    s=cash_settings();s.update(PAYOUT_RECEIPT_DAYS='0')
    c=run(s);assert_conservation(c)
    assert c['cash_totals']['received_trader_payouts']=='1500.00'
    assert c['cash_totals']['total_paid_fees']=='100.00'
    assert c['cash_totals']['payout_evaluation_fee_multiple']=='25'
    assert any(r['event']=='purchase_blocked' for r in c['cash_ledger'])
    s.update(EVAL_PRICE='0.00',ACTIVATION_FEE='0.00')
    c=run(s);assert c['cash_totals']['payout_evaluation_fee_multiple'] is None
    assert c['cash_totals']['total_paid_fees']=='0.00'


def test_no_purchase_if_reservation_would_exceed_cap():
    s=cash_settings();s['MONTHLY_CAP']='69.99'
    c=run(s)
    assert not c['accounts'] and c['cash_totals']['total_paid_fees']=='0.00'
    assert c['cash_totals']['payout_evaluation_fee_multiple'] is None


def test_evaluation_pending_horizon_and_unresolved_month_reset():
    s=cash_settings();s['HORIZON_END']='2026-02-03'
    c=run(s,first_failure=False,funded_failure=False,net='1')
    # Apex times out after 21 weekdays Jan 5–Feb 2; exact fees, new attempt Feb 3.
    assert c['accounts'][0]['outcome']=='evaluation_expired'
    assert c['accounts'][1]['outcome']=='evaluation_open' and c['accounts'][1]['closed_at'] is None
    assert c['cash_totals']['total_paid_fees']=='60.00'
    assert c['cash_totals']['potential_evaluation_activation']=='40.00'


@pytest.mark.parametrize('key,value', [('MONTHLY_CAP','nan'),('EVAL_PRICE','30.001'),('BUDGET_TIMEZONE','Mars/Local'),
    ('PAYOUT_TIMING_ASSUMPTION',''),('PAYOUT_RECEIPT_DAYS',''),('ACTIVATION_TIMING_ASSUMPTION',''),
    ('ACTIVATION_DEADLINE_DAYS','0'),('START_DATE','20260105'),('SLOTS','2')])
def test_invalid_cash_settings(key,value):
    original=cash_settings();original[key]=value
    with pytest.raises(ValueError):resolved_settings(original)


def test_cash_settings_cannot_silently_run_annualized():
    with pytest.raises(ValueError,match='budgeted_lifecycle'):resolved_settings(dict(MONTHLY_CAP='100'))


def test_lucid_retains_no_activation_fee_and_trader_share():
    s=cash_settings();s.update(PROP_FIRM='Lucid',ACCOUNT_TYPE='LucidFlex',ACTIVATION_FEE='0',PAYOUT_RECEIPT_DAYS='0')
    s=resolved_settings(s)
    c=run(s,first_failure=False,funded_failure=False)
    assert c['accounts'][0]['passed_on']=='2026-01-07' and c['accounts'][0]['funded_start']=='2026-01-08'
    first=c['payout_settlements'][0]
    assert Decimal(first['gross_account_deduction'])==Decimal('2000.00') and first['trader_amount']=='1800.00'
    assert c['cash_totals']['paid_activation_fees']=='0.00'
    s['ACTIVATION_FEE']='40'
    with pytest.raises(ValueError,match='zero activation'):resolved_settings(s)


def test_budget_timezone_controls_month_and_dst_calendar_day_receipt():
    s=cash_settings();s.update(BUDGET_TIMEZONE='Asia/Singapore',START_DATE='2026-01-30',HORIZON_END='2026-02-10')
    c=run(s,first_failure=False,funded_failure=False)
    reset=next(r for r in c['cash_ledger'] if r['event']=='month_reset' and r['month']=='2026-02')
    assert reset['timestamp_utc']=='2026-01-31T16:00:00+00:00'
    s=cash_settings();s.update(START_DATE='2026-02-23',HORIZON_END='2026-03-20',PAYOUT_RECEIPT_DAYS='10')
    c=run(s,start='2026-02-23',periods=25,first_failure=False,funded_failure=False)
    p=c['payout_settlements'][0]
    assert p['requested_at']=='2026-03-03T22:00:00+00:00' and p['receipt_due_at']=='2026-03-13T21:00:00+00:00'


def test_fractional_lucid_entitlements_preserve_account_deduction_round_only_receipt():
    s=cash_settings();s.update(PROP_FIRM='Lucid',ACCOUNT_TYPE='LucidFlex',ACTIVATION_FEE='0',FUNDED_MICROS='1',PAYOUT_RECEIPT_DAYS='0')
    c=run(resolved_settings(s),first_failure=False,funded_failure=False,net='3000.01')
    p=c['payout_settlements'][0]
    raw=Decimal(p['raw_trader_entitlement'])
    from decimal import ROUND_HALF_UP
    assert Decimal(p['trader_amount'])==raw.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    assert Decimal(p['gross_account_deduction'])!=Decimal(p['gross_account_deduction']).quantize(Decimal('.01'))
    # Deduction stays in the trading account; it never becomes another cash fee.
    assert c['cash_totals']['total_paid_fees']=='30.00'


def test_horizon_does_not_close_pending_activation_or_evaluation():
    s=cash_settings();s['HORIZON_END']='2026-01-06'
    c=run(s)
    assert c['outcome']=='activation_pending' and c['accounts'][-1]['closed_at'] is None
    assert c['cash_totals']['pending_activation_obligations']=='40.00'
    assert c['cash_totals']['reserved_allowance']=='40.00'
    s['HORIZON_END']='2026-01-05'
    c=run(s,first_failure=False,net='1')
    assert c['outcome']=='evaluation_open' and c['accounts'][-1]['closed_at'] is None
    assert c['cash_totals']['net_cash_within_horizon']=='-30.00'


def test_many_independent_paths_conserve_cash_and_cap_every_month():
    import random
    rng=random.Random(917)
    for path in range(32):
        s=cash_settings();s.update(HORIZON_END='2026-03-20',PAYOUT_RECEIPT_DAYS=str(path%11),
            ACTIVATION_PAYMENT_DELAY_DAYS=str(path%10))
        snapshot,rows=inputs(periods=60,first_failure=False,funded_failure=False)
        for phase,trades in rows.items():
            for row in trades:
                net=rng.choice([-5000,-2000,-1500,0,1000,3000,6000])
                adverse=rng.choice([0,500,3000,9000])+max(0,-net)
                row.update(source_net_pnl=str(net),measured_mae=str(adverse),ohlc_adverse_path=json.dumps([[str(adverse),True]]))
        c=replay(snapshot,rows,s);assert_conservation(c)
        assert all(Decimal(r['paid_fees'])==Decimal(r['evaluation_fees'])+Decimal(r['activation_fees'])<=100 for r in c['monthly_ledger'])
        assert sum((Decimal(r['paid_fees']) for r in c['monthly_ledger']),Decimal(0))==Decimal(c['cash_totals']['total_paid_fees'])


def test_source_net_trading_costs_are_not_charged_again_as_cash():
    c=run(first_failure=True,funded_failure=True,net='2990')
    assert next(r for r in c['trace'] if r['phase']=='funded')['equity']==897
    assert c['cash_totals']['paid_evaluation_fees']=='60.00'
    assert c['cash_totals']['paid_activation_fees']=='40.00'
    assert not any(Decimal(r['paid_fee']) not in (0,30,40) for r in c['cash_ledger'])


def test_budget_window_admission_and_saved_settings_identity(monkeypatch):
    from test_prop_phase_validation import inputs as admission_inputs, install
    from alphaquest.prop.phase_lifecycle import prepare_request
    from alphaquest.prop.store import request_key
    sources,rows=admission_inputs();install(monkeypatch,sources,rows)
    s=cash_settings();s['HORIZON_END']='2026-01-09'
    body=dict(source_backtest_id='a'*32,funded_source_backtest_id='b'*32,settings=s)
    snapshot,_,resolved=prepare_request(None,body)
    key=request_key(snapshot,resolved)
    for name,value in [('MONTHLY_CAP','90.00'),('BUDGET_TIMEZONE','UTC'),('START_DATE','2026-01-06'),
                       ('HORIZON_END','2026-01-08'),('EVAL_PRICE','31.00'),('ACTIVATION_FEE','41.00'),
                       ('PAYOUT_RECEIPT_DAYS','31'),('PAYOUT_TIMING_ASSUMPTION','different saved timing'),
                       ('ACTIVATION_DEADLINE_DAYS','8'),('ACTIVATION_PAYMENT_DELAY_DAYS','1'),
                       ('ACTIVATION_TIMING_ASSUMPTION','different saved deadline'),('FEE_OVERRIDE_NOTE','different saved note')]:
        assert request_key(snapshot,{**resolved,name:value})!=key
    body['settings']={**s,'HORIZON_END':'2026-01-10'}
    with pytest.raises(ValueError,match='observed'):prepare_request(None,body)
    body['settings']={**s,'START_DATE':'2026-01-04'}
    with pytest.raises(ValueError,match='observed'):prepare_request(None,body)
