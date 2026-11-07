"""Independent source/date/ZIP audit of the automatic-calendar browser outputs."""
import argparse
import csv
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256
import json
from pathlib import Path
import zipfile


def next_open(day):
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


def verify(root):
    results = []
    for path in sorted(root.glob('test_automatic_calendar_from_s[01]/workflow.json')):
        flow = json.loads(path.read_text())
        for name, checksum in flow['downloads'].items():
            assert sha256((path.parent/name).read_bytes()).hexdigest() == checksum
        folder = path.parent/'prop_analyses'/flow['analysis_id']
        for name in ('report.json', 'analysis.zip'):
            assert (path.parent/name).read_bytes() == (folder/name).read_bytes()
        report = json.loads((folder/'report.json').read_text())
        request = report['request']
        start = date.fromisoformat(request['calendar']['start_dates'][0])
        row = report['calculations']['candidates'][0]
        c = row['manifest']['configuration']
        days = c['retry']['max_calendar_days'] if flow['phase']=='evaluation' else request['horizon_calendar_days']
        expected_end = (start+timedelta(days=days)).isoformat()
        assert request['calendar']['coverage_end'] == flow['expected_coverage_end'] == expected_end
        assert flow['submitted_calendar'] == dict(start_dates=[start.isoformat()])
        assert flow['reopen_posts'] == []
        assert row['manifest']['source']['profile_research_period']['last_session'] == '2026-01-14'
        with (folder/'inputs'/flow['source_id']/'trades.csv').open() as stream:
            trades = list(csv.DictReader(stream))
        assert len(trades) == 8
        assert all(Decimal(t['total_commissions']) == Decimal(t['slippage_cost']) == 0 for t in trades)
        profits = {Decimal(t['net_pnl'])/Decimal(t['contracts'])/10*c['micros'] for t in trades}
        assert len(profits) == 1
        profit = profits.pop()
        if flow['phase'] == 'evaluation':
            sessions = int((Decimal(3000)/profit).to_integral_value(rounding=ROUND_CEILING))
            ready = next_open(start)
            for _ in range(sessions-1+c['retry']['activation_delay_sessions']+1):
                ready = next_open(ready+timedelta(days=1))
            cost = Decimal(c['profile']['evaluation_price'])+Decimal(c['profile']['activation_fee'])
            assert row['metrics']['cost_per_funded'] == cost == 70
            assert row['metrics']['expected_calendar_days_to_funded'] == (ready-start).days == 2
            assert all(p['funded_date'] == ready.isoformat() and Decimal(p['cost_accrued']) == cost for p in row['paths'])
            expected = dict(cost=str(cost),calendar_days=(ready-start).days,ready=ready.isoformat())
        else:
            assert profit == 900
            cutoff = start+timedelta(days=request['horizon_calendar_days'])
            opens = [start+timedelta(days=i) for i in range(request['horizon_calendar_days'])
                if (start+timedelta(days=i)).weekday()<5]
            requests = [opens[4],opens[9]]  # Constant $900 qualifies every session; five-day native cycles.
            receipts = [day+timedelta(days=request['receipt_delay_calendar_days']) for day in requests]
            received = sum(1500 for day in receipts if day<cutoff)
            pending = 3000-received
            for p in row['paths']:
                assert [e['request_date'] for e in p['payout_events']] == [d.isoformat() for d in requests]
                assert [e['receipt_date'] for e in p['payout_events']] == [d.isoformat() for d in receipts]
                assert p['cash_received'] == received == 1500 and p['pending_cash'] == pending == 1500
            assert row['metrics']['expected_payouts'] == received
            assert row['metrics']['expected_gross_account_deductions'] == 3000
            expected = dict(received=received,pending=pending,cutoff=cutoff.isoformat())
        with zipfile.ZipFile(folder/'analysis.zip') as archive:
            assert archive.read('report.json') == (folder/'report.json').read_bytes()
            for name,info in report['files'].items():
                assert sha256(archive.read(name)).hexdigest() == info['sha256']
                assert archive.read(name) == (folder/name).read_bytes()
        results.append(dict(**flow,independent_expected=expected,
            downloads_verified=len(flow['downloads']),zip_artifacts_verified=len(report['files'])+1))
    assert {r['phase'] for r in results} == {'evaluation','funded'}
    return dict(production_imports=False,synthetic=True,workflows=results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.browser_root)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
