"""Standard-library oracle for actual saved synthetic funded search outputs.

No production calculator, ranking, sampler or storage imports. Read-only review.
"""
import argparse
import csv
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import zipfile


def verify(library):
    metadata=json.loads((library/'funded-search-verification.json').read_text())
    folder=library/'prop_analyses'/metadata['analysis_id']
    report=json.loads((folder/'report.json').read_text())
    request=report['request'];calendar=request['calendar']
    assert calendar['start_dates']==['2026-01-05']
    assert request['horizon_calendar_days']==14 and request['receipt_delay_calendar_days']==4
    expected={}
    for row in report['calculations']['candidates']:
        c=row['manifest']['configuration']
        assert c['profile']['profile_id']=='apex-50k-eod'
        source_id=c['source']['source_backtest_id']
        with (folder/'inputs'/source_id/'trades.csv').open() as stream:trades=list(csv.DictReader(stream))
        assert all(Decimal(t['total_commissions'])==Decimal(t['slippage_cost'])==0 for t in trades)
        daily_values={Decimal(t['net_pnl'])/Decimal(t['contracts'])/10*c['micros'] for t in trades}
        assert len(daily_values)==1
        daily=daily_values.pop()
        assert daily in (100,300,900)
        # Independent closed-form reasoning for this monotone, ten-session case:
        # $100 cannot qualify, $300 needs 12 sessions for $3600 safety+cap;
        # $900 qualifies five days, has $4500 equity and meets 50% consistency.
        # Deduct $1500 session5, then again session10. Four calendar days later
        # gives Jan13 / Jan20: only Jan13 precedes Jan19.
        expected_cash=1500 if daily==900 else 0
        expected_gross=3000 if daily==900 else 0
        expected_pending=1500 if daily==900 else 0
        expected[row['candidate_id']]=expected_cash
        m=row['metrics']
        assert m['expected_payouts']==m['median_payouts']==m['p10_payouts']==m['p90_payouts']==expected_cash
        assert m['expected_pending_cash']==expected_pending
        assert m['expected_gross_account_deductions']==expected_gross
        assert m['expected_account_lifetime'] is None and m['probability_surviving_to_horizon']==1
        assert m['restricted_mean_account_lifetime_calendar_days']==14
        assert m['expected_days_to_first_payout_conditional_on_payout']==(8 if expected_cash else None)
        for p in row['paths']:
            assert p['cash_received']==expected_cash and p['pending_cash']==expected_pending
            assert p['observed_sessions']==10 and p['lifetime_censored'] and not p['unresolved']
            assert Decimal(str(p['equity']))==10*daily-expected_gross
            if expected_cash:
                assert [e['request_date'] for e in p['payout_events']]==['2026-01-09','2026-01-16']
                assert [e['receipt_date'] for e in p['payout_events']]==['2026-01-13','2026-01-20']
                assert [e['trader_cash_received'] for e in p['payout_events']]==[1500,0]
            else:assert not p['payout_events']
    ranking=sorted(expected,key=lambda id:(-expected[id],id))
    assert report['calculations']['ranking']==ranking
    assert report['calculations']['winner']==ranking[0]
    with zipfile.ZipFile(folder/'analysis.zip') as archive:
        assert archive.read('report.json')==(folder/'report.json').read_bytes()
        for name,info in report['files'].items():
            assert sha256(archive.read(name)).hexdigest()==info['sha256']
            assert archive.read(name)==(folder/name).read_bytes()
    return dict(production_imports=False,analysis_id=metadata['analysis_id'],
        expected_cash=sorted(expected.values()),expected_pending_for_winner=1500,
        expected_gross_for_winner=3000,ranking=ranking,
        checked_zip_files=len(report['files'])+1,preserved_original_files=metadata['unchanged_files'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=verify(args.library)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result,indent=2))
