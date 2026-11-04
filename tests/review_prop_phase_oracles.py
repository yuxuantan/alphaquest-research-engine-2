"""Independent Decimal/date qualification of actual milestone-1 saved outputs.

Imports no production account, adaptation, sampling or report calculation code.
The synthetic expectations belong to tests, never to product inputs or screens.
"""
import argparse
import csv
from datetime import date,datetime,timedelta
from decimal import Decimal as D
import json
from pathlib import Path


def weekday_after(day,n):
    while n:
        day+=timedelta(days=1)
        if day.weekday()<5:n-=1
    return day


def apex_payouts(days,daily):
    equity=D(0);qualifying=0;payouts=[]
    ladder=list(map(D,['1500','1500','2000','2500','2500','3000']))
    for day in days:
        equity+=daily;qualifying+=daily>=250
        if qualifying>=5 and equity>=2100+ladder[len(payouts)]:
            amount=ladder[len(payouts)];equity-=amount;qualifying=0
            payouts.append((day,amount))
            if len(payouts)==6:break
    return payouts


def verify(library,lucid_path,manifest=None):
    meta=json.loads((library/'verification.json').read_text());checked={}
    if manifest:meta['outcomes']=json.loads(manifest.read_text())['current_outcomes']
    for label,case in meta['outcomes'].items():
        directory=library/'prop_analyses'/case['analysis_id']
        report=json.loads((directory/'report.json').read_text());c=report['calculations']
        inputs={phase:list(csv.DictReader((directory/'inputs'/phase/'source_trades.csv').open())) for phase in ('evaluation','funded')}
        assert all(D(row['net_pnl'])==3000 for row in inputs['evaluation'])
        if label=='recovering':
            assert c['trace'][0]['first_limit_hit']=='account_breach' and D(str(c['trace'][0]['equity']))==-3000
            assert c['phase_metrics']['funded']['sessions']==0
            checked[label]=dict(expected_source_winner=3000,expected_observed_gap=-3000,expected_outcome='account_breach')
            continue
        first=date.fromisoformat(inputs['evaluation'][0]['entry_time_utc'][:10])
        eligible=weekday_after(first,1);funded_start=weekday_after(eligible,1)
        assert c['activation']['eligible_session']==eligible.isoformat()
        assert c['activation']['funded_start_session']==funded_start.isoformat()
        usable=[r for r in inputs['funded'] if date.fromisoformat(r['entry_time_utc'][:10])>=funded_start]
        assert int(usable[0]['trade_number'])==3
        assert c['trace'][2]['source_trade_ids']==[3]
        daily=D(usable[0]['net_pnl'])/D(usable[0]['contracts'])/10*3
        assert all(D(r['net_pnl'])/D(r['contracts'])/10*3==daily for r in usable)
        expected=apex_payouts([r['entry_time_utc'][:10] for r in usable],daily) if daily>=250 else []
        actual=[(t['date'],D(str(t['trader_payout']))) for t in c['trace'] if t['trader_payout']]
        assert actual==expected,(label,actual,expected)
        assert D(str(c['phase_metrics']['funded']['trader_payouts']))==sum((p for _,p in expected),D(0))
        checked[label]=dict(independent_daily_pnl=str(daily),eligible=eligible.isoformat(),funded_start=funded_start.isoformat(),
            payouts=[(d,str(p)) for d,p in expected],total=str(sum((p for _,p in expected),D(0))))
    lucid=json.loads(lucid_path.read_text());c=lucid['calculations']
    # Three equal evaluation days: $9000 equity, 1/3 consistency <40%.
    start=date(2026,1,5);pass_day=weekday_after(start,2);funded=weekday_after(pass_day,1)
    assert c['phase_metrics']['evaluation']['pass_date']==pass_day.isoformat()
    assert c['activation']['eligible_session']==pass_day.isoformat()
    assert c['activation']['funded_start_session']==funded.isoformat()
    expected=[(weekday_after(funded,5*i-1).isoformat(),D(1800)) for i in range(1,6)]
    actual=[(t['date'],D(str(t['trader_payout']))) for t in c['trace'] if t['trader_payout']]
    assert actual==expected
    assert c['phase_metrics']['funded']['gross_withdrawals']==10000
    checked['lucid']=dict(payouts=[(d,str(p)) for d,p in expected],gross=10000,trader_payouts=9000)
    return dict(production_calculations_imported=False,independent_cases=checked)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--lucid-report',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--manifest',type=Path)
    args=parser.parse_args();result=verify(args.library,args.lucid_report,args.manifest)
    with args.output.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
