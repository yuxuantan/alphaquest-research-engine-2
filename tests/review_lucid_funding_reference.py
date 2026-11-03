"""Independent scalar ledger for an actual source's Lucid funding chains.

Uses the source adapter for reconciled inputs, never production account or
sampling helpers. Scalar MT19937 draws are compared with the compiled batch.
"""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace

import numpy as np


def ledger(days, count, seed, block, micros, dll, consistency=.4):
    rng = np.random.RandomState(seed)
    results = []
    for path in range(count):
        def sessions():
            while True:
                start = int(rng.randint(len(days)))
                for offset in range(block):yield days[(start+offset) % len(days)]
        source = sessions()
        total = longest = 0
        for attempt in range(1, 10001):
            balance = peak = best_profit = 0.
            last_active = 0
            finished = None
            for day in range(1, 20001):
                calendar = 7*((day-1)//5) + (day-1) % 5
                if calendar-last_active > 30:
                    finished = 'inactive'
                    break
                opened = balance
                account_floor = min(peak-2000., 100.)
                day_floor = opened-dll if dll is not None else -float('inf')
                stop = max(account_floor, day_floor)
                for trade in next(source):
                    before = balance
                    hit = None
                    # First observed crossing of the account/day stop. Gaps
                    # retain observed balance; continuous segments use the stop.
                    if len(trade) > 2 and trade[2] is not None:
                        for adverse, observed_jump in trade[2]:
                            mark = before-adverse*micros/10.
                            if mark <= stop:
                                balance = mark if observed_jump else stop
                                hit = 'blown' if (balance <= account_floor if observed_jump else account_floor >= day_floor) else 'pause'
                                break
                    if hit is None and before-trade[1]*micros/10. <= stop:
                        balance = stop
                        hit = 'blown' if account_floor >= day_floor else 'pause'
                    if hit is None:
                        balance = before+trade[0]*micros/10.
                        if balance <= stop:hit = 'blown' if balance <= account_floor else 'pause'
                    if abs(balance-before) >= 1:last_active = calendar
                    if hit:
                        if hit == 'blown':finished = 'blown'
                        break
                best_profit = max(best_profit, balance-opened)
                peak = max(peak, balance)
                if finished == 'blown':break
                if balance >= 3000. and best_profit <= consistency*balance:
                    finished = 'passed'
                    break
                if calendar-last_active >= 30:
                    finished = 'inactive'
                    break
            total += day
            longest = max(longest, day)
            if finished == 'passed':break
            if finished is None:raise AssertionError('Reference has an unresolved 20,000-session path')
        else:raise AssertionError('Reference exceeds funding-attempt limit')
        results.append((total, attempt, longest))
        if (path+1) % 5000 == 0:print('Independent chains:', path+1, flush=True)
    return np.array(results)


def main(old_report, data, output, count=20000):
    from alphaquest.prop.native_analysis import prepare, day_book
    from alphaquest.prop.native_backend import compact_neutral_runs
    from alphaquest.prop.lucid_backend import evaluation
    @contextmanager
    def connect():
        db = sqlite3.connect(f'file:{(data / "backtests.sqlite3").resolve()}?mode=ro', uri=True)
        try:yield db
        finally:db.close()
    report = json.loads(old_report.read_text())
    runs = SimpleNamespace(root=data / 'backtest_runs', connect=connect)
    snapshot, rows, settings = prepare(runs, report['source']['backtest']['id'], '', report['settings'])
    _, days, split = day_book(rows, settings)
    train = compact_neutral_runs(days)[:split]
    size = report['calculations']['training_economics']['evaluation_micros']
    block = int(settings['BLOCK_DAYS'])
    dll = 1200. if settings['DAILY_LOSS_LIMIT'] == 'on' else None
    started = time.monotonic()
    expected = ledger(train, count, 45, block, size, dll)
    actual = evaluation(train, size, count, 45, block, chain=True, daily_loss=dll)
    observed = np.column_stack([actual['days'], actual['attempts'], actual['longest_attempt_days']])
    assert np.array_equal(expected, observed), 'Independent and compiled funding chains differ'
    result = dict(source_id=report['source']['backtest']['id'], trades_sha256=snapshot['trades_sha256'],
        seed=45, simulations=count, every_chain_matches=True, mean_days=float(expected[:, 0].mean()),
        median_days=float(np.median(expected[:, 0])), continued_chains=int(sum(expected[:, 2] > 2000)),
        longest_attempt=int(max(expected[:, 2])), elapsed_seconds=time.monotonic()-started)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--old-report', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=Path('data'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=20000)
    args = parser.parse_args()
    main(args.old_report, args.data, args.output, args.count)
