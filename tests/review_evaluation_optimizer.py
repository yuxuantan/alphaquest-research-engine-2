"""Standard-library-only oracle for the saved synthetic Evaluation demo.

Read captured source trades and local Apex assumptions; import no production
calculator, sampler, Pareto helper or report storage. Never modify the library.
"""
import argparse
import csv
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256
import io
import json
from pathlib import Path
import zipfile


def next_open(day, closures):
    day += timedelta(days=1)
    while day.weekday() >= 5 or day.isoformat() in closures:
        day += timedelta(days=1)
    return day


def verify(library):
    metadata = json.loads((library/'evaluation-search-verification.json').read_text())
    directory = library/'prop_analyses'/metadata['analysis_id']
    report = json.loads((directory/'report.json').read_text())
    expected = {}
    for row in report['calculations']['candidates']:
        configuration = row['manifest']['configuration']
        source_id = configuration['source']['source_backtest_id']
        with (directory/'inputs'/source_id/'trades.csv').open() as stream:
            trades = list(csv.DictReader(stream))
        # This particular synthetic source is NQ, flat daily, no costs or adverse
        # price moves. Every session earns the same known net amount.
        assert row['manifest']['source']['phase_suitability']['instrument'] == 'NQ'
        assert all(Decimal(t['total_commissions']) == Decimal(t['slippage_cost']) == 0 for t in trades)
        nets = {Decimal(t['net_pnl']) / Decimal(t['contracts']) / 10 for t in trades}
        assert len(nets) == 1
        daily = nets.pop()*configuration['micros']
        assert daily > 0
        duration = int((Decimal(3000)/daily).to_integral_value(rounding=ROUND_CEILING))
        assert duration <= 21
        assert row['component']['outcomes'] == ['passed']*configuration['simulation']['simulations']
        assert row['component']['duration_weekdays'] == [duration]*configuration['simulation']['simulations']
        profile = configuration['profile']; retry = configuration['retry']
        assert profile['profile_id'] == 'apex-50k-eod'
        cost = Decimal(profile['evaluation_price']) + Decimal(profile['activation_fee'])
        calendar = report['request']['calendar']
        assert len(calendar['start_dates']) == 1
        start = date.fromisoformat(calendar['start_dates'][0]); last = start
        closures = set(calendar['closures'])
        while last.weekday() >= 5 or last.isoformat() in closures:
            last += timedelta(days=1)
        for _ in range(duration-1+retry['activation_delay_sessions']+1):
            last = next_open(last, closures)
        days = (last-start).days
        metrics = row['metrics']
        assert Decimal(str(metrics['cost_per_funded'])) == cost
        assert metrics['expected_calendar_days_to_funded'] == days
        assert metrics['median_calendar_days_to_funded'] == metrics['p90_calendar_days_to_funded'] == days
        assert metrics['pass_probability'] == metrics['expected_attempts_per_funded'] == 1
        assert all(p['funded_date'] == last.isoformat() and Decimal(p['cost_accrued']) == cost for p in row['paths'])
        expected[row['candidate_id']] = (cost, days)
    frontier = sorted((id for id,(c,t) in expected.items()
        if not any(cc <= c and tt <= t and (cc < c or tt < t) for cc,tt in expected.values())),
        key=lambda id: (*expected[id],id))
    assert report['calculations']['frontier'] == frontier
    assert report['calculations']['winner'] is None
    for marginal in report['calculations']['marginal_acceleration_cost']:
        cs,ts = expected[marginal['slow_candidate_id']]; cf,tf = expected[marginal['fast_candidate_id']]
        assert Decimal(str(marginal['usd_per_calendar_day_saved'])) == (cf-cs)/(ts-tf)
    with zipfile.ZipFile(directory/'analysis.zip') as archive:
        assert archive.read('report.json') == (directory/'report.json').read_bytes()
        for name,check in report['files'].items():
            assert sha256(archive.read(name)).hexdigest() == check['sha256']
            assert archive.read(name) == (directory/name).read_bytes()
    return dict(production_imports=False, analysis_id=metadata['analysis_id'],
        expected_points=sorted((str(c),t) for c,t in expected.values()), frontier=frontier,
        checked_zip_files=len(report['files'])+1, preserved_original_files=metadata['unchanged_files'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.library)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
