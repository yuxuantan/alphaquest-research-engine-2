"""Read-only qualification of a saved AQ evaluation against a Bridge export.

Bridge files are comparison oracles only. All scenario calculations use local
AQ code; none are published as production reports or change account defaults.
The independent scalar ledger checks every repeated-funding path as well.
"""
import argparse
import ast
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace

import numpy as np

from alphaquest.prop.lucid_backend import evaluation, identity
from alphaquest.prop.native_analysis import day_book, prepare
from review_lucid_funding_reference import ledger


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def fingerprints(paths):
    return {str(p.resolve()): sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths)) if p.is_file()}


def review(report_path, bridge_path, workbook, data, output):
    output.mkdir(parents=True, exist_ok=False)
    report = json.loads(report_path.read_text())
    bridge = json.loads((bridge_path / 'results.json').read_text())
    assert bridge['status'] == 'ok' and not bridge['demo']
    oracle = bridge['part1']['hero'][0]
    settings_file, = bridge_path.glob('settings_*.txt')
    captured = {}
    for line in settings_file.read_text().splitlines():
        if ' = ' in line and not line.startswith('#'):
            key, value = line.split(' = ', 1)
            if key not in captured:
                try:captured[key] = ast.literal_eval(value)
                except (ValueError, SyntaxError):pass
    consistency = captured['EVAL_ACCOUNT']['consistency']
    bridge_size = int(oracle['MNQ'])
    source_id = report['source']['backtest']['id']
    source_dir = data / 'backtest_runs' / source_id
    protected = [*report_path.parent.rglob('*'), *source_dir.rglob('*'),
                 *bridge_path.rglob('*'), workbook]
    before = fingerprints(protected)
    write(output / 'preservation-before.json', before)
    shutil.copyfile(report_path, output / 'aq-report.json')
    shutil.copyfile(bridge_path / 'results.json', output / 'bridge-results.json')
    shutil.copyfile(settings_file, output / 'bridge-settings.txt')

    @contextmanager
    def connect():
        db = sqlite3.connect(f'file:{(data / "backtests.sqlite3").resolve()}?mode=ro', uri=True)
        try:yield db
        finally:db.close()

    runs = SimpleNamespace(root=data / 'backtest_runs', connect=connect)
    original = report['settings']
    selected = report['calculations']['evaluation']['selected_micros']
    bridge_date = bridge['dates']['out_of_sample_from']
    scenarios = [
        ('AQ saved configuration', selected, .4, {}, ''),
        ('Change size only', bridge_size, .4, {}, ''),
        ('Also use Bridge consistency', bridge_size, consistency, {}, ''),
        ('Also retain source costs', bridge_size, consistency, {'COMMISSION_MODE': 'source'}, ''),
        ('Also align validation date', bridge_size, consistency,
         {'COMMISSION_MODE': 'source', 'OUT_OF_SAMPLE_FROM': bridge_date}, ''),
        ('Also retain exact workbook floating values', bridge_size, consistency,
         {'COMMISSION_MODE': 'source', 'OUT_OF_SAMPLE_FROM': bridge_date}, str(workbook)),
    ]
    results = []
    for index, (label, size, share, overrides, trade_file) in enumerate(scenarios):
        snapshot, rows, settings = prepare(runs, source_id, trade_file, dict(original, **overrides))
        grid, days, split = day_book(rows, settings)
        sample = days[split:]
        sim = evaluation(sample, size, 20000, 43, 5, consistency=share)
        chain = evaluation(sample, size, 20000, 44, 5, consistency=share, chain=True)
        assert not any(sim['outcomes'] == 'timeout')
        passed = int(sum(sim['outcomes'] == 'passed'))
        result = dict(scenario=label, micros=size, consistency=share,
            commission_mode=settings['COMMISSION_MODE'], sample=[str(grid[split].date()), str(grid[-1].date())],
            sample_weekdays=len(sample), simulations=20000, evaluation_seed=43, funding_seed=44, block_days=5,
            passed=passed, pass_rate=passed / 20000,
            cost_per_funded=float(settings['EVAL_PRICE']) / (passed / 20000),
            evaluation_chain_days=float(chain['days'].mean()),
            evaluation_chain_median=float(np.median(chain['days'])),
            median_successful_attempt_days=float(np.median(sim['days'][sim['outcomes'] == 'passed'])),
            censored_paths=int(sum(sim['outcomes'] == 'timeout')))
        if index in (0, len(scenarios)-1):
            expected = ledger(sample, 20000, 44, 5, size, 1200., consistency=share)
            actual = np.column_stack([chain['days'], chain['attempts'], chain['longest_attempt_days']])
            assert np.array_equal(actual, expected), 'Independent chain ledger differs'
            np.savez_compressed(output / f'chains-{index}.npz', actual=actual, independent=expected)
            result['independent_chains_match'] = 20000
            if index == 0:
                saved = report['calculations']['evaluation']
                assert result['passed'] == saved['passed']
                assert result['cost_per_funded'] == saved['cost_per_funded']
                assert result['evaluation_chain_days'] == saved['days_to_funded']
            else:
                write(output / 'workbook-reconciliation.json', snapshot)
        results.append(result)
        print(json.dumps(result), flush=True)

    aligned = results[-1]
    # Bridge documents counting the next funded-start weekday; AQ records only
    # the evaluation chain, and starts funded trading on a subsequent session.
    assert aligned['pass_rate'] == oracle['pass_rate']
    assert aligned['cost_per_funded'] == oracle['cost_per_funded']
    assert aligned['evaluation_chain_days'] + 1 == oracle['days_to_funded']
    assert aligned['evaluation_chain_median'] + 1 == float(oracle['days_to_funded_median_text'])
    assert aligned['median_successful_attempt_days'] == float(oracle['median_days_to_pass_text'])
    # Independent arithmetic boundary: $1,000/MNQ/day reaches target on day 3.
    # A 2-day guard must censor; a continuous touch at -$2,000 must breach even
    # if the source trade ultimately makes a profit.
    for limit, outcome in ((2, 'timeout'), (3, 'passed')):
        sim = evaluation([[(10000., 0.)]], 1, 4, 42, deadline=limit)
        assert sim['outcomes'].tolist() == [outcome] * 4
    sim = evaluation([[(100., 2000.)]], 10, 4, 42, daily_loss=None)
    assert sim['outcomes'].tolist() == ['blown'] * 4
    try:prepare(runs, source_id, str(workbook), dict(original, SLOTS='6'))
    except ValueError as exc:
        assert 'SLOTS' in str(exc)
        rejection = str(exc)
    else:raise AssertionError('Invalid slot count accepted')
    after = fingerprints(protected)
    assert before == after, 'Existing evidence/source/report changed'
    write(output / 'preservation-after.json', after)
    result = dict(aq_id=report['id'], source_id=source_id, kernel=identity(),
        bridge_reference=str(bridge_path.resolve()), bridge_oracle=oracle,
        bridge_evaluation_objective=captured['EVAL_PICK'],
        bridge_evaluation_search_cap=captured['EVAL_MAX_MICROS'],
        aq_evaluation_objective='max(training passed count)', aq_evaluation_search_cap=40,
        cases=results, exact_pass_cost_and_timing_match=True,
        bridge_funded_start_day_adjustment=1, independent_chains_checked=40000,
        independent_boundaries_passed=True, invalid_slot_rejection=rejection,
        protected_files=len(before), existing_files_unchanged=True,
        qualification_scope='These evaluation metrics for this source only; no funded-account or provider-rule parity claim.',
        production_changes=False, bridge_executed=False)
    write(output / 'comparison.json', result)
    print('Exact match; source and saved results preserved.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--bridge', type=Path, required=True)
    parser.add_argument('--workbook', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=Path('data'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review(args.report, args.bridge, args.workbook, args.data, args.output)
