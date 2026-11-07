"""Read-only standard-library audit of the saved opt-out grid/campaign journey.

Uses captured trades and independent Decimal/date arithmetic, not AlphaQuest.
Run after test_phase_architecture_browser.py with a fresh output filename.
"""
import argparse
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from review_campaign_portal import audit_report


def verify(browser_root):
    checked = []
    for metadata in sorted(browser_root.glob('test_opt_out_grid_to_independe[01]/workflow.json')):
        flow = json.loads(metadata.read_text())
        directory = metadata.parent
        job = json.loads((directory/'grid.json').read_text())
        assert job['request']['automatic_prop'] is False and job['default_prop_profile'] is None
        assert job['completed_trials'] == job['total_trials'] == 2
        assert job['failed_trials'] == [] and flow['reopen_posts'] == []
        report_directory = directory/'prop_analyses'/flow['analysis_id']
        audit = audit_report(report_directory)
        result = json.loads((report_directory/'calculations.json').read_text())
        assert json.loads((directory/'results.json').read_text()) == result
        rows = result['candidates']
        if flow['phase'] == 'evaluation':
            points = {r['candidate_id']: (Decimal(str(r['metrics']['cost_per_funded'])),
                Decimal(str(r['metrics']['expected_calendar_days_to_funded']))) for r in rows}
            frontier = sorted((id for id, (cost, time) in points.items() if not any(
                c <= cost and t <= time and (c < cost or t < time) for c, t in points.values())),
                key=lambda id: (*points[id], id))
            assert result['frontier'] == frontier and result['winner'] is None
        else:
            cash = {r['candidate_id']: Decimal(str(r['metrics']['expected_payouts'])) for r in rows}
            ranking = sorted(cash, key=lambda id: (-cash[id], id))
            assert result['ranking'] == ranking and result['winner'] == ranking[0]
        checked.append(dict(workflow=flow, report=audit, grid_elapsed_seconds=job['elapsed_seconds'],
            downloads={p.name:sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()
                if p.is_file() and p.suffix in ('.json', '.csv', '.zip')}))
    assert {row['workflow']['phase'] for row in checked} == {'evaluation', 'funded'}
    return dict(production_imports=False, synthetic=True, workflows=checked)


def verify_receipt_boundaries(library):
    metadata = json.loads((library/'funded-boundary-verification.json').read_text())
    checked = []
    for case in metadata['cases']:
        if case['case'] not in ('receipt_at_cutoff', 'receipt_before_cutoff'):
            continue
        report = json.loads((library/'prop_analyses'/case['analysis_id']/'report.json').read_text())
        request = report['request']
        for row in report['calculations']['candidates']:
            for path in row['paths']:
                cutoff = date.fromisoformat(path['start_date'])+timedelta(days=request['horizon_calendar_days'])
                received = pending = Decimal(0)
                for event in path['payout_events']:
                    due = date.fromisoformat(event['request_date'])+timedelta(days=request['receipt_delay_calendar_days'])
                    assert due.isoformat() == event['receipt_date']
                    entitlement = Decimal(str(event['trader_cash_entitlement']))
                    if due < cutoff:
                        received += entitlement
                    else:
                        pending += entitlement
                assert received == Decimal(str(path['cash_received'])) == case['expected_received']
                assert pending == Decimal(str(path['pending_cash'])) == case['expected_pending']
        checked.append(dict(case=case['case'], horizon=request['horizon_calendar_days'],
            received=case['expected_received'], pending=case['expected_pending']))
    assert {c['case'] for c in checked} == {'receipt_at_cutoff', 'receipt_before_cutoff'}
    return checked


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--funded-library', type=Path)
    args = parser.parse_args()
    result = verify(args.browser_root)
    if args.funded_library:
        result['receipt_boundaries'] = verify_receipt_boundaries(args.funded_library)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
