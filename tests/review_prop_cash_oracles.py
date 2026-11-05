"""Read-only independent Decimal/date oracle for saved milestone-2 demonstrations.

Uses only the standard library; imports no AlphaQuest or production calculator.
"""
import argparse
import csv
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
import zipfile

D=Decimal


def verify(directory):
    manifest=json.loads((directory/'verification.json').read_text())
    results={}
    expected={'exact_100':('60.00','40.00','0.00','-100.00'),
        'month_reset':('90.00','80.00','0.00','-170.00'),
        'activation_expiry':('60.00','0.00','0.00','-60.00'),
        'pending_at_reset':('30.00','0.00','0.00','-30.00'),
        'receipt_within_horizon':('90.00','80.00','1500.00','1330.00')}
    for name,(eval_fee,act_fee,receipts,net) in expected.items():
        report=json.loads((directory/(name+'-report.json')).read_text())
        assert report['id']==manifest['outcomes'][name]['analysis_id']
        c=report['calculations'];settings=report['settings'];cap=D(settings['MONTHLY_CAP'])
        fees=received=reserved=D(0);monthly={};clock=None
        for row in c['cash_ledger']:
            stamp=datetime.fromisoformat(row['timestamp_utc'])
            assert clock is None or stamp>=clock;clock=stamp
            assert row['month']==row['timestamp_budget'][:7]
            month=row['month'];monthly.setdefault(month,dict(fees=D(0),received=D(0)))
            paid,receipt,change,earmark=[D(row[k]) for k in ('paid_fee','trader_receipt','cash_delta','reservation_delta')]
            assert paid>=0 and receipt>=0 and change==receipt-paid
            if row['event']=='evaluation_purchase':assert paid==D(settings['EVAL_PRICE'])
            elif row['event']=='activation_payment':assert paid==D(settings['ACTIVATION_FEE'])
            else:assert paid==0
            if row['event']!='trader_receipt':assert receipt==0
            fees+=paid;received+=receipt;reserved+=earmark
            monthly[month]['fees']+=paid;monthly[month]['received']+=receipt
            assert D(row['net_cash_to_date'])==received-fees
            assert D(row['paid_this_month'])==monthly[month]['fees']<=cap
            assert D(row['remaining_allowance'])==cap-monthly[month]['fees']
            assert D(row['reserved_allowance'])==reserved>=0
            assert D(row['available_for_purchase'])==cap-monthly[month]['fees']-reserved>=0
        for month in c['monthly_ledger']:
            expected_month=monthly[month['month']]
            assert D(month['paid_fees'])==expected_month['fees']
            assert D(month['trader_receipts'])==expected_month['received']
            assert D(month['net_cash'])==expected_month['received']-expected_month['fees']
        totals=c['cash_totals']
        for key,value in [('paid_evaluation_fees',eval_fee),('paid_activation_fees',act_fee),('received_trader_payouts',receipts),('net_cash_within_horizon',net)]:
            assert D(totals[key])==D(value),(name,key,totals[key],value)
        assert D(totals['net_cash_within_horizon'])==received-fees
        assert D(totals['payout_evaluation_fee_multiple'])==D(receipts)/D(eval_fee)
        end=datetime.fromisoformat(c['budget_contract']['end_exclusive'])
        assert all(datetime.fromisoformat(p['receipt_due_at'])>=end for p in c['pending_receipts'])
        for csv_name,json_name in [('cash_ledger','cash_ledger'),('monthly_ledger','monthly_ledger')]:
            downloaded=list(csv.DictReader(io.StringIO((directory/(name+'-'+csv_name+'.csv')).read_text())))
            assert len(downloaded)==len(c[json_name])
            for row,actual in zip(downloaded,c[json_name]):
                for key in ('paid_fee','trader_receipt','paid_fees','net_cash','remaining_allowance'):
                    if key in row:assert D(row[key])==D(actual[key])
        with zipfile.ZipFile(directory/(name+'-analysis.zip')) as archive:
            for path,record in report['files'].items():
                assert sha256(archive.read(path)).hexdigest()==record['sha256']
            assert json.loads(archive.read('calculations.json'))==c
            assert json.loads(archive.read('inputs/settings.json'))==settings
        results[name]=dict(analysis_id=report['id'],net_cash=net,paid_evaluation_fees=eval_fee,paid_activation_fees=act_fee,
            received_cash=receipts,ledger_rows=len(c['cash_ledger']),monthly_fees={k:str(v['fees']) for k,v in monthly.items()},
            ratio=totals['payout_evaluation_fee_multiple'],zip_hashes_verified=len(report['files']))
    c=json.loads((directory/'exact_100-report.json').read_text())['calculations']
    fees=[(r['timestamp_budget'][:10],r['event'],r['paid_fee']) for r in c['cash_ledger'] if D(r['paid_fee'])]
    assert fees==[('2026-01-05','evaluation_purchase','30.00'),('2026-01-06','evaluation_purchase','30.00'),('2026-01-07','activation_payment','40.00')]
    assert sum((D(v) for _,_,v in fees),D(0))==D(100)
    # Five funded $900 sessions Jan 8, 9, 12, 13, 14 -> equity $4500,
    # first full cap $1500 above $2100 safety net. Receipt is modeled 30 days later.
    assert c['pending_receipts'][0]['requested_at']=='2026-01-14T22:00:00+00:00'
    assert c['pending_receipts'][0]['receipt_due_at']=='2026-02-13T22:00:00+00:00'
    assert D(c['pending_receipts'][0]['trader_amount'])==1500
    assert any(r['event']=='reservation_released' and r['timestamp_budget'].startswith('2026-01-05') and r['reservation_delta']=='-40.00' for r in c['cash_ledger'])
    assert next(r for r in c['cash_ledger'] if r['event']=='purchase_blocked')['timestamp_budget'].startswith('2026-01-16')
    expiry=json.loads((directory/'activation_expiry-report.json').read_text())['calculations']
    assert any(r['event']=='activation_expired' and r['timestamp_budget'].startswith('2026-01-14') for r in expiry['cash_ledger'])
    pending=json.loads((directory/'pending_at_reset-report.json').read_text())['calculations']
    rows=[r for r in pending['cash_ledger'] if r['timestamp_budget'].startswith('2026-02-01')]
    assert [(r['event'],r['reservation_delta']) for r in rows]==[('reservation_released','-40.00'),('month_reset','0.00'),('activation_reserved','40.00')]
    assert pending['accounts'][0]['activation_deadline']=='2026-02-09T22:00:00+00:00'
    assert pending['outcome']=='activation_pending'
    reset=json.loads((directory/'month_reset-report.json').read_text())['calculations']
    assert reset['accounts'][2]['purchased_at']=='2026-02-01T06:00:00+00:00'
    assert reset['accounts'][2]['outcome']=='funded_open' and reset['accounts'][2]['closed_at'] is None
    return dict(production_calculations_imported=False,independent_cash_100=str(D(30)+D(30)+D(40)),
        expected_paid_transactions=fees,all_ledger_rows_conserved=True,all_months_within_cap=True,cases=results)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=verify(args.directory)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result,indent=2))
