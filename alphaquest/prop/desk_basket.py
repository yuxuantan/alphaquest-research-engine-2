"""Fixed weighted baskets of synchronized saved opportunities for Prop Desk."""

from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from statistics import mean, stdev
import csv
import math

import numpy as np

from ..optimization_cache import digest
from ..research_folds import inventory_sessions
from . import desk, native_backend, lucid_backend
from .adapter import canonical, digest as file_digest, source_record
from .commissions import adapt, source_instrument
from .native_analysis import day_book
from .native_engine import sampled_days
from .phase_lifecycle import instant, session_date, validate_phase_source
from .phase_profiles import profile_settings, verify_phase_source
from .phase_search import declared_is_coverage, saved_oos_period, strategy_definition
from .source import prepare_source

VERSION = 'prop-desk-basket-v1'
FIRST_YEAR = 261
LAW = ('Fixed saved opportunities on shared observed sessions. At most one position. '
       'Earliest entry first, with higher weight and then basket order breaking ties. '
       'An entry at a prior exit is allowed after the exit. Positions and signals are not rerun. '
       'Saved net costs and adverse marks are scaled linearly to whole MNQ. '
       'Funded tiers cap each admitted member target at the session opening tier.')


def allocation(weights, total):
    quantities = [total * weight // sum(weights) for weight in weights]
    return dict(micros=quantities, unused=total - sum(quantities))


def period(records, inventory, role):
    # Take only sessions with identical and complete observed coverage in all
    # saved runs. This describes coverage of the saved dataset, not exchange hours.
    start = max(instant(record['period_start_utc']) for record in records)
    end = min(instant(record['period_end_utc']) for record in records)
    declarations = [(saved_oos_period if role == 'oos' else declared_is_coverage)(record)
                    for record in records]
    first = max(d['first_session'] for d in declarations)
    last = min(d['last_session'] for d in declarations)
    days = [day for day in inventory['sessions']
            if first <= day <= last and start <= instant(inventory['bounds'][day]['first_utc'])
            and instant(inventory['bounds'][day]['last_utc']) <= end]
    if not days:
        raise ValueError(f'Basket members have no common observed {role.upper()} sessions.')
    return days


def checked_record(runs, id, role, parent=None):
    record = source_record(runs, id)
    meta = record['run_metadata']
    research = meta.get('research') or {}
    if not source_instrument(record) or meta.get('source', {}).get('kind') == 'external_trade_export':
        raise ValueError(f'Backtest {id[:8]} requires a native saved NQ/MNQ dataset for basket coverage.')
    if research.get('phase') != role:
        raise ValueError(f'Backtest {id[:8]} must be a saved {role.upper()} run.')
    if parent:
        original = parent['run_metadata']
        if (research.get('parent_run_id') != parent['id'] or research.get('plan') != original['research']['plan']
                or meta['dataset'] != original['dataset']
                or strategy_definition(meta['strategy']) != strategy_definition(original['strategy'])
                or parent['execution_settings'] != record['execution_settings']):
            raise ValueError(f'OOS report {id[:8]} must retain its selected IS parent, split, strategy and costs.')
    return record


def source_book(runs, analyses, record, profile, days):
    settings = profile_settings(profile, desk.SOURCE_COSTS)
    id = record['id']
    source = desk.SavedTradeSource(id)
    try:
        snapshot, rows = prepare_source(runs, id, '', allow_empty=True)
        adapt(snapshot, rows, settings)
        validate_phase_source(snapshot, rows)
        verify_phase_source(runs, source, snapshot)
        analyses.check_oos(snapshot, settings, runs)
        grid, book, _ = day_book(rows, settings) if rows else ([], [], None)
    except ValueError as exc:
        raise ValueError(f'Backtest {id[:8]}: {exc}') from exc
    by_day = {str(stamp.date()): trades for stamp, trades in zip(grid, book, strict=True)}
    ordered = sorted(rows, key=lambda row: (instant(row['entry_utc']), int(row['trade_id'])))
    offsets = dict.fromkeys(days, 0)
    result = {day: [] for day in days}
    scale = Decimal(10 if snapshot['phase_suitability']['instrument'] == 'NQ' else 1)
    for row in ordered:
        entry = instant(row['entry_utc'])
        day = str(session_date(entry))
        if day not in offsets:
            continue
        units = Decimal(row['quantity']) * scale
        result[day].append(dict(entry=entry, exit=instant(row['exit_utc']), id=row['trade_id'],
            scenario=by_day[day][offsets[day]], net=Decimal(row['source_net_pnl']) / units,
            commission=Decimal(row['source_commission']) / units,
            slippage=Decimal(row['source_slippage']) / units))
        offsets[day] += 1
    snapshot['profile_research_period'] = dict(first_session=days[0], last_session=days[-1],
        weekdays=len(days), convention='Common observed CME session labels, including no-trade sessions.')
    return snapshot, result


def prepare(runs, datasets, analyses, body, configuration):
    is_records = [checked_record(runs, m.source_backtest_id, 'is') for m in body.members]
    oos_records = ([checked_record(runs, m.oos_backtest_id, 'oos', parent)
                    for m, parent in zip(body.members, is_records, strict=True)]
                   if body.members[0].oos_backtest_id else [])
    records = is_records + oos_records
    dataset = is_records[0]['run_metadata']['dataset']
    if any((r['run_metadata']['dataset']['id'], r['run_metadata']['dataset']['sha256'])
           != (dataset['id'], dataset['sha256']) for r in records):
        raise ValueError('Basket sources must use the same saved NQ/MNQ dataset and data version.')
    current = datasets.get(dataset['id'])
    if not current or current['sha256'] != dataset['sha256']:
        raise ValueError('The original saved dataset is unavailable or its identity changed.')
    inventory = inventory_sessions(datasets, dataset['id'], minimum_sessions=1)
    windows = {'is': period(is_records, inventory, 'is')}
    if oos_records:
        windows['oos'] = period(oos_records, inventory, 'oos')
        if windows['is'][-1] >= windows['oos'][0]:
            raise ValueError('The common OOS sessions must follow the entire common IS window.')
    version = desk.rule_version(body.profile_id)
    lucid = body.profile_id == 'lucidflex-50k'
    profile = (desk.EvaluationProfile(body.profile_id, version, '80.50' if lucid else '49', '0' if lucid else '129')
               if body.phase == 'evaluation' else desk.FundedProfile(body.profile_id, version))
    simulation = desk.SimulationConfig(desk.PATHS, desk.SEED, desk.PROFILES[body.profile_id]['caps'][body.phase])
    sampling = desk.SamplingConfig(desk.BLOCK_WEEKDAYS)
    snapshots, books = {}, {}
    for role, selected in [('is', is_records), ('oos', oos_records)]:
        if selected:
            captures = [source_book(runs, analyses, record, profile, windows[role]) for record in selected]
            snapshots[role], books[role] = map(list, zip(*captures))
    if len(is_records) == 1 and not snapshots['is'][0]['reconciliation']['source_count']:
        raise ValueError('The one-member basket uses the single-strategy model, which requires saved source trades.')
    evidence = desk.provenance(body.phase, snapshots['is'][0], profile, body.minimum_micros, simulation, sampling)
    evidence.pop('source')
    evidence['implementation_sha256']['desk_basket.py'] = file_digest(Path(__file__))
    evidence['implementation_sha256']['desk.py'] = file_digest(Path(desk.__file__))
    evidence['implementation_sha256']['research_folds.py'] = file_digest(Path(__file__).parents[1] / 'research_folds.py')
    hashes = {role: [dict(manifest=s['manifest_sha256'], trades=s['trades_sha256'],
                          risk=s['excursion_input']) for s in group] for role, group in snapshots.items()}
    identity = digest(dict(version=VERSION, configuration=configuration, source=hashes,
                           dataset=inventory['source'], windows=windows, provenance=evidence))
    return dict(profile=profile, simulation=simulation, sampling=sampling, evidence=evidence,
                snapshots=snapshots, books=books, windows=windows, identity=identity)


def verify(runs, prepared):
    for group in prepared['snapshots'].values():
        for snapshot in group:
            verify_phase_source(runs, desk.SavedTradeSource(snapshot['backtest']['id']), snapshot)


def admitted(book, days, weights, targets):
    combined, skipped = {}, 0
    for day in days:
        entries = [(index, row) for index, member in enumerate(book) if targets[index] for row in member[day]]
        entries.sort(key=lambda pair: (pair[1]['entry'], -weights[pair[0]], pair[0], pair[1]['id']))
        selected, last_exit = [], None
        for index, row in entries:
            if last_exit is not None and row['entry'] < last_exit:
                skipped += 1
                continue
            selected.append((index, row))
            last_exit = row['exit']
        combined[day] = selected
    return combined, skipped


def session_book(days, targets, cap=None):
    """Scale tuples once. With a Funded tier each tuple still enters at its absolute member target."""
    scaled = []
    for selected in days.values():
        trades = []
        for index, row in selected:
            net, adverse, *extras = row['scenario']
            factor = targets[index] if cap is None else min(targets[index], cap) / cap
            if extras and extras[0] is not None:
                extras[0] = tuple((loss * factor, jump) for loss, jump in extras[0])
            trades.append((net * factor, adverse * factor, *extras))
        scaled.append(trades)
    return scaled


def funded_paths(days, targets, prepared, horizon):
    profile, simulation, sampling = (prepared[key] for key in ('profile', 'simulation', 'sampling'))
    lucid = profile.profile_id == 'lucidflex-50k'
    backend = lucid_backend if lucid else native_backend
    rules = (backend.Rules(daily_loss=1200., inactivity_enforced=profile.lucid_inactivity_enforced)
             if lucid else backend.Rules(approval_day_counts=profile.approval_day_counts))
    requested = max(targets)
    if requested <= rules.levels[0][1]:
        accounts = backend.funded(session_book(days, targets), 1, simulation.simulations,
            simulation.seed, sampling.block_weekdays, horizon=horizon, rules=rules)
    else:
        # The existing account owner determines the effective opening tier before
        # it consumes the iterable. Its own stop, payout and activity law is unchanged.
        variants = {cap: session_book(days, targets, cap)
                    for cap in {min(requested, level[1]) for level in rules.levels}}
        rng = np.random.RandomState(simulation.seed)
        accounts = []
        for _ in range(simulation.simulations):
            account = backend.FundedAccount(rules)
            for index in sampled_days(rng, len(days), sampling.block_weekdays):
                def trades():
                    yield from variants[account.effective_micros][index]
                account.advance(trades(), requested, simulation.max_micros)
                if account.outcome != 'open' or account.day >= horizon:
                    break
            accounts.append(account)
    paths = [dict(outcome=a.outcome, observed_weekdays=a.day, trader_payouts=list(a.payouts),
        gross_account_deductions=list(getattr(a, 'withdrawals', a.payouts)), equity=a.equity,
        lifetime_censored=a.outcome == 'open') for a in accounts]
    return paths, dict(asdict(rules), starting_balance=50000, max_mnq=simulation.max_micros,
        trail_updates='End of session before payout deduction', withdrawal_fraction=.5 if lucid else None,
        payout_share=.9 if lucid else 1,
        payout_timing='First eligible observed trade close in the request window, otherwise session close.'
                      if lucid else 'At session close.')


def funded_results(paths, rules):
    result = desk.funded_measurements(paths, rules)
    result['first_year_mean_receipts'] = mean(sum(v for day, v in p['trader_payouts'] if day <= FIRST_YEAR)
                                             for p in paths)
    result['account_life_mean_receipts'] = None if result['open_at_cutoff'] else result['mean_trader_receipts']
    return result


def equity(staged, size, timeline, targets, snapshots):
    """Historical target-size curves from admitted, unforced saved closed trades."""
    values = [Decimal(0)] * len(targets)
    peak = drawdown = Decimal(0)
    dates, levels, daily = [], [], []
    name = f'admitted_trades_{size}.csv'
    oos_start = None
    with (staged / name).open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output)
        writer.writerow(('role', 'session', 'source_backtest_id', 'source_trade_id', 'member', 'entry_utc',
                         'exit_utc', 'target_mnq', 'commission', 'slippage', 'net_pnl'))
        for role, days in timeline.items():
            if role == 'oos':
                oos_start = next(iter(days))
            for day, selected in days.items():
                prior = sum(values)
                for index, row in selected:
                    quantity = targets[index]
                    net = row['net'] * quantity
                    values[index] += net
                    value = sum(values)
                    peak = max(peak, value)
                    drawdown = max(drawdown, peak - value)
                    writer.writerow((role, day, snapshots[role][index]['backtest']['id'], row['id'], index + 1,
                                     row['entry'].isoformat(), row['exit'].isoformat(), quantity,
                                     row['commission'] * quantity, row['slippage'] * quantity, net))
                dates.append(day)
                levels.append([float(sum(values)), *map(float, values)])
                daily.append(float(sum(values) - prior))
    def stats(observations, loss):
        avg = mean(observations)
        sd = stdev(observations) if len(observations) > 1 else None
        return dict(annual_return=avg * 252, annual_volatility=sd * math.sqrt(252) if sd is not None else None,
                    sharpe=avg / sd * math.sqrt(252) if sd else None, maximum_drawdown=float(loss))
    result = dict(dates=dates, levels=levels, oos_start=oos_start, metrics=stats(daily, drawdown),
                  final_equity_change=float(sum(values)), trades_file=name)
    (staged / f'equity_{size}.json').write_text(canonical(result), encoding='utf-8')


def calculate(runs, body, configuration, prepared, staged, progress):
    verify(runs, prepared)
    weights = [member.weight for member in body.members]
    results = []
    for size in range(body.minimum_micros, body.maximum_micros + 1):
        progress(f'Prop Desk basket · {size} MNQ of {body.maximum_micros}')
        sizing = allocation(weights, size)
        targets = sizing['micros']
        histories = {role: admitted(book, prepared['windows'][role], weights, targets)
                     for role, book in prepared['books'].items()}
        days = histories['is'][0]
        horizon = configuration['observation_sessions']
        if len(body.members) == 1:
            # Exactly the Milestone 1 branch including its saved weekday convention and RNG.
            from types import SimpleNamespace
            single = SimpleNamespace(profile_id=body.profile_id, phase=body.phase,
                                     source_backtest_id=body.members[0].source_backtest_id, micros=size)
            declared = dict(source_backtest_id=single.source_backtest_id, profile_id=body.profile_id,
                            phase=body.phase, micros=size, observation_sessions=horizon)
            checked = desk.prepare(runs, single, declared)
            metrics, paths, rules = desk.calculate(runs, single, declared, checked)
            if body.phase == 'funded':
                metrics = funded_results(paths, rules)
        elif body.phase == 'evaluation':
            setup = dict(prepared, days=session_book(days, targets), evidence=dict(prepared['evidence'], micros=1),
                         settings=profile_settings(prepared['profile'], desk.SOURCE_COSTS))
            metrics, paths, rules = desk.evaluation(setup, horizon)
            rules['starting_balance'] = 50000
        else:
            paths, rules = funded_paths(days, targets, prepared, horizon)
            metrics = funded_results(paths, rules)
        equity(staged, size, {role: h[0] for role, h in histories.items()}, targets, prepared['snapshots'])
        (staged / f'paths_{size}.json').write_text(canonical(paths), encoding='utf-8')
        results.append(dict(micros=size, allocation=sizing, metrics=metrics,
                            overlap_skips={role: h[1] for role, h in histories.items()}))
    verify(runs, prepared)
    return results, rules
