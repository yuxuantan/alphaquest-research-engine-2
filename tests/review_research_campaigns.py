"""Independent standard-library review of the actual saved campaign outputs."""
import argparse
import csv
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256
import json
from pathlib import Path
import zipfile


def next_session(day):
    while day.weekday()>=5:day+=timedelta(days=1)
    return day


def verify(root):
    evidence=json.loads((root/'campaign-verification.json').read_text())
    results=[]
    for campaign in evidence['campaigns']:
        directory=root/'prop_analyses'/campaign['analysis_id']
        raw=(directory/'report.json').read_bytes();report=json.loads(raw)
        assert sha256(raw).hexdigest()==campaign['frozen']['report_sha256']
        package=dict(campaign['frozen']);digest=package.pop('package_sha256')
        assert sha256(json.dumps(package,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==digest
        points={}
        for row in report['calculations']['candidates']:
            config=row['manifest']['configuration'];id=config['source']['source_backtest_id']
            with (directory/'inputs'/id/'trades.csv').open() as stream:trades=list(csv.DictReader(stream))
            assert all(Decimal(t['total_commissions'])==Decimal(t['slippage_cost'])==0 for t in trades)
            per_day={Decimal(t['net_pnl'])/Decimal(t['contracts'])/10*config['micros'] for t in trades}
            assert len(per_day)==1
            daily=per_day.pop();m=row['metrics']
            if report['phase']=='evaluation':
                sessions=int((Decimal(3000)/daily).to_integral_value(rounding=ROUND_CEILING))
                # One passing purchase + activation; pass at session end,
                # one full activation weekday then next session is usable.
                current=date(2026,1,5)
                for _ in range(sessions):current=next_session(current)+timedelta(days=1)
                current=next_session(current)+timedelta(days=1)
                ready=next_session(current)
                expected_days=(ready-date(2026,1,5)).days
                assert m['cost_per_funded']==70
                assert m['expected_calendar_days_to_funded']==expected_days
                points[row['candidate_id']]=(70,expected_days)
            else:
                assert daily in (100,300,900)
                # Ten sessions: only $900 qualifies; requests Jan9/16,
                # four-day settlement Jan13/20, exclusive cutoff Jan19.
                expected=1500 if daily==900 else 0
                assert m['expected_payouts']==expected
                assert m['expected_pending_cash']==expected
                assert m['expected_gross_account_deductions']==2*expected
                for p in row['paths']:
                    assert p['cash_received']==expected and p['pending_cash']==expected
                    if expected:
                        assert [e['request_date'] for e in p['payout_events']]==['2026-01-09','2026-01-16']
                        assert [e['receipt_date'] for e in p['payout_events']]==['2026-01-13','2026-01-20']
                points[row['candidate_id']]=expected
        if report['phase']=='evaluation':
            frontier=sorted([key for key,(c,t) in points.items() if not any(c2<=c and t2<=t and (c2,t2)!=(c,t) for c2,t2 in points.values())],key=lambda k:(*points[k],k))
            assert report['calculations']['frontier']==frontier
        else:
            ranking=sorted(points,key=lambda k:(-points[k],k))
            assert report['calculations']['ranking']==ranking
        with zipfile.ZipFile(directory/'analysis.zip') as archive:
            assert archive.read('report.json')==raw
            for name,info in report['files'].items():
                assert sha256(archive.read(name)).hexdigest()==info['sha256']
        results.append(dict(phase=report['phase'],campaign_id=campaign['campaign_id'],analysis_id=campaign['analysis_id'],
                            expected_values=sorted(points.values()),checked_artifacts=len(report['files'])+1))
    return dict(production_imports=False,campaigns=results,unchanged_prior_files=evidence['unchanged_files'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--library',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=verify(args.library)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result,indent=2))
