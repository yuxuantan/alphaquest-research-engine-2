"""Standard-library arithmetic/artifact audit of actual portal IS/OOS outputs.

No production imports. Reads captured trades, independently derives constant
synthetic-path expectations, checks all report/ZIP hashes and frozen identities.
"""
import argparse
import csv
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256
import json
from pathlib import Path
import zipfile


def next_open(day):
    while day.weekday()>4:day+=timedelta(days=1)
    return day


def audit_report(directory):
    raw=(directory/'report.json').read_bytes();report=json.loads(raw)
    expected=[]
    for row in report['calculations']['candidates']:
        c=row['manifest']['configuration'];id=c['source']['source_backtest_id']
        with (directory/'inputs'/id/'trades.csv').open() as f:trades=list(csv.DictReader(f))
        assert trades and all(Decimal(t['total_commissions'])==Decimal(t['slippage_cost'])==0 for t in trades)
        daily={Decimal(t['net_pnl'])/Decimal(t['contracts'])/10*c['micros'] for t in trades}
        assert len(daily)==1
        daily=daily.pop();m=row['metrics']
        if report['phase']=='evaluation':
            sessions=int((Decimal(3000)/daily).to_integral_value(rounding=ROUND_CEILING))
            cursor=date(2026,1,5)
            for _ in range(sessions):cursor=next_open(cursor)+timedelta(days=1)
            # One additional activation session; readiness is next session.
            ready=next_open(next_open(cursor)+timedelta(days=1))
            days=(ready-date(2026,1,5)).days
            assert m['cost_per_funded']==70 and m['expected_calendar_days_to_funded']==days
            assert m['median_calendar_days_to_funded']==m['p90_calendar_days_to_funded']==days
            assert m['pass_probability']==m['probability_funded_by_day_30']==m['probability_funded_by_day_60']==1
            assert m['funded_accounts_per_30_calendar_days']==30/days
            expected.append([70,days])
        else:
            # Ten target sessions in [Jan5,Jan19). Only $900/day reaches
            # payout availability ($2100 safety net + first $1500 request).
            # Qualifying requests Jan9/16; four civil-day receipts Jan13/20.
            assert daily in (100,300,900)
            cash=1500 if daily==900 else 0
            assert m['expected_payouts']==m['median_payouts']==m['p10_payouts']==m['p90_payouts']==cash
            assert m['expected_pending_cash']==cash and m['expected_gross_account_deductions']==2*cash
            assert m['account_breach_probability']==0 and m['probability_surviving_to_horizon']==1
            assert m['probability_first_payout']==bool(cash)
            assert m['expected_days_to_first_payout_conditional_on_payout']==(8 if cash else None)
            for path in row['paths']:
                assert path['cash_received']==path['pending_cash']==cash
                if cash:
                    assert [p['request_date'] for p in path['payout_events']]==['2026-01-09','2026-01-16']
                    assert [p['receipt_date'] for p in path['payout_events']]==['2026-01-13','2026-01-20']
            expected.append(cash)
    with zipfile.ZipFile(directory/'analysis.zip') as z:
        assert z.read('report.json')==raw
        for name,value in report['files'].items():
            data=(directory/name).read_bytes()
            assert z.read(name)==data and sha256(data).hexdigest()==value['sha256']
    with (directory/'phase_metrics.csv').open() as f:assert len(list(csv.DictReader(f)))==len(expected)
    if report.get('assessment'):
        calc=report['calculations'];assert calc['winner'] is None
        assert calc.get('ranking',calc.get('frontier'))==[]
        assert calc['selection_status']=='assessment_only_no_reselection'
    return dict(id=report['id'],phase=report['phase'],expected=sorted(expected),artifacts_checked=len(report['files'])+1,sha256=sha256(raw).hexdigest())


def verify(root):
    checked=[]
    for metadata in sorted(root.glob('test_campaign_portal_frozen_oo[01]/portal-evidence.json')):
        evidence=json.loads(metadata.read_text());library=metadata.parent
        campaign=json.loads((library/'campaign.json').read_text())
        frozen=campaign['frozen'];package=dict(frozen);digest=package.pop('package_sha256')
        assert sha256(json.dumps(package,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()==digest
        assert sha256((library/'frozen_package.json').read_bytes()).hexdigest()==evidence['freeze_sha256']
        for rule in frozen['rule_sources'].values():assert sha256(rule['source'].encode()).hexdigest()==rule['sha256']
        is_audit=audit_report(library/'prop_analyses'/campaign['analysis_id'])
        oos_audit=audit_report(library/'prop_analyses'/evidence['assessment_id'])
        assert frozen['report_sha256']==is_audit['sha256']
        assert evidence['reopen_posts']==[]
        checked.append(dict(campaign_id=campaign['campaign_id'],is_report=is_audit,oos_report=oos_audit))
    assert len(checked)==2,'Both actual portal workflows are required.'
    return dict(production_imports=False,synthetic=True,campaigns=checked)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--browser-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=verify(args.browser_root)
    with args.output.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
