"""Compare saved-strategy subsets on one observed history and paired account paths."""

from dataclasses import asdict, replace
from itertools import combinations, groupby
from math import comb
from pathlib import Path
from statistics import median

import numpy as np

from ..optimization_cache import digest
from . import desk, desk_basket as basket, lucid_backend, native_backend
from .adapter import canonical, digest as file_digest
from .native_engine import sampled_days
from .phase_profiles import profile_settings

VERSION = 'prop-desk-optimizer-v1'
MODE = 'prop_desk_optimizer'
MAX_PAIRS = 48
MAX_PAIR_SESSIONS = 16_000
OBJECTIVES = {
    'evaluation': 'Highest single-attempt pass probability',
    'funded': 'Highest mean first-year trader receipts',
}
TIES = 'Equal scores share a rank. Within a tie, use smaller total MNQ, then member count and pool order.'
SAMPLING = ('Shared circular blocks over the common observed IS sessions. Each path uses MT19937 '
            'seeded from SeedSequence([base seed, zero-based path index]).')


def workload(pool_size, minimum, maximum, minimum_micros, maximum_micros, horizon):
    if not 1 <= minimum <= maximum <= pool_size:
        raise ValueError('Set minimum and maximum basket members between 1 and the candidate pool size.')
    count = sum(comb(pool_size, size) for size in range(minimum, maximum + 1))
    pairs = count * (maximum_micros - minimum_micros + 1)
    if pairs > MAX_PAIRS or pairs * horizon > MAX_PAIR_SESSIONS:
        limit = min(MAX_PAIRS, MAX_PAIR_SESSIONS // horizon)
        raise ValueError(f'This search requests {pairs:,} combination-size pairs. At this horizon the limit is '
                         f'{limit}. Reduce the candidate pool, member-count range, or MNQ range.')
    return dict(combinations=count, pairs=pairs)


def prepare(runs, datasets, analyses, body, configuration):
    is_records = [basket.checked_record(runs, member.source_backtest_id, 'is') for member in body.members]
    oos_records = {index: basket.checked_record(runs, member.oos_backtest_id, 'oos', is_records[index])
                   for index, member in enumerate(body.members) if member.oos_backtest_id}
    dataset = is_records[0]['run_metadata']['dataset']
    for record in [*is_records, *oos_records.values()]:
        other = record['run_metadata']['dataset']
        if (other['id'], other['sha256']) != (dataset['id'], dataset['sha256']):
            raise ValueError(f'Backtest {record["id"][:8]} must use the same saved NQ/MNQ dataset and version as the pool.')
    current = datasets.get(dataset['id'])
    if not current or current['sha256'] != dataset['sha256']:
        raise ValueError('The original saved dataset is unavailable or its identity changed.')
    inventory = basket.inventory_sessions(datasets, dataset['id'], minimum_sessions=1)
    is_days = basket.period(is_records, inventory, 'is')

    version = desk.rule_version(body.profile_id)
    lucid = body.profile_id == 'lucidflex-50k'
    profile = (desk.EvaluationProfile(body.profile_id, version, '80.50' if lucid else '49', '0' if lucid else '129')
               if body.phase == 'evaluation' else desk.FundedProfile(body.profile_id, version))
    simulation = desk.SimulationConfig(desk.PATHS, desk.SEED, desk.PROFILES[body.profile_id]['caps'][body.phase])
    sampling = desk.SamplingConfig(desk.BLOCK_WEEKDAYS)
    captures = [basket.source_book(runs, analyses, record, profile, is_days) for record in is_records]
    is_snapshots, is_books = map(list, zip(*captures))
    oos_snapshots, oos_books, oos_days = [], {}, {}
    for index, record in oos_records.items():
        days = basket.period([record], inventory, 'oos')
        if days[0] <= is_days[-1]:
            raise ValueError(f'OOS report {record["id"][:8]} must follow the common IS window.')
        snapshot, book = basket.source_book(runs, analyses, record, profile, days)
        oos_snapshots.append(snapshot)
        oos_books[index] = book
        oos_days[index] = days
    snapshots = {'is': is_snapshots, 'oos': oos_snapshots}
    evidence = desk.provenance(body.phase, is_snapshots[0], profile, body.minimum_micros, simulation, sampling)
    del evidence['source']
    implementation = evidence['implementation_sha256']
    for path in (Path(__file__), Path(basket.__file__), Path(desk.__file__),
                 Path(__file__).parents[1] / 'research_folds.py'):
        implementation[path.name] = file_digest(path)
    evidence.update(rng=SAMPLING, dataset=inventory['source'])
    identity = digest(dict(version=VERSION, configuration=configuration, sources=snapshots, is_days=is_days,
                           oos_days=oos_days, provenance=evidence))
    return dict(profile=profile, simulation=simulation, sampling=sampling, evidence=evidence,
                snapshots=snapshots, is_books=is_books, is_days=is_days, oos_books=oos_books,
                oos_days=oos_days, identity=identity)


def evaluation(days, targets, prepared, horizon, path_seeds):
    """Use the single-attempt owner with an independent stream for each path."""
    profile, simulation = prepared['profile'], prepared['simulation']
    setup = dict(prepared, days=basket.session_book(days, targets), evidence=dict(prepared['evidence'], micros=1),
                 settings=profile_settings(profile, desk.SOURCE_COSTS))
    paths = []
    for seed in path_seeds:
        setup['simulation'] = replace(simulation, simulations=1, seed=seed)
        result, outcomes, rules = desk.evaluation(setup, horizon)
        paths.extend(outcomes)
    counts = dict.fromkeys(result['outcome_counts'], 0)
    passing = []
    for path in paths:
        counts[path['outcome']] += 1
        if path['outcome'] == 'passed':
            passing.append(path['trading_sessions'])
    metrics = dict(outcome_counts=counts, probabilities={key: value / len(paths) for key, value in counts.items()},
                   pass_rate_interval_95=desk.wilson(len(passing), len(paths)),
                   median_trading_days_to_target=median(passing) if passing else None)
    return metrics, paths, dict(rules, starting_balance=50000)


def funded(days, targets, prepared, horizon, path_seeds):
    """Share path seeds while leaving tiers, terminal events and payouts to the Funded owner."""
    profile, simulation, sampling = (prepared[key] for key in ('profile', 'simulation', 'sampling'))
    lucid = profile.profile_id == 'lucidflex-50k'
    backend = lucid_backend if lucid else native_backend
    rules = (backend.Rules(daily_loss=1200., inactivity_enforced=profile.lucid_inactivity_enforced)
             if lucid else backend.Rules(approval_day_counts=profile.approval_day_counts))
    requested = max(targets)
    paths = []
    if requested <= rules.levels[0][1]:
        book = basket.session_book(days, targets)
        accounts = (backend.funded(book, 1, 1, seed, sampling.block_weekdays, horizon=horizon, rules=rules)[0]
                    for seed in path_seeds)
    else:
        variants = {cap: basket.session_book(days, targets, cap)
                    for cap in {min(requested, level[1]) for level in rules.levels}}

        def run_accounts():
            for seed in path_seeds:
                account = backend.FundedAccount(rules)
                for index in sampled_days(np.random.RandomState(seed), len(days), sampling.block_weekdays):
                    def trades():
                        yield from variants[account.effective_micros][index]
                    account.advance(trades(), requested, simulation.max_micros)
                    if account.outcome != 'open' or account.day >= horizon:
                        break
                yield account

        accounts = run_accounts()
    for account in accounts:
        paths.append(dict(outcome=account.outcome, observed_weekdays=account.day,
            trader_payouts=list(account.payouts), gross_account_deductions=list(getattr(account, 'withdrawals', account.payouts)),
            equity=account.equity, lifetime_censored=account.outcome == 'open'))
    applied = dict(asdict(rules), starting_balance=50000, max_mnq=simulation.max_micros,
        trail_updates='End of session before payout deduction', withdrawal_fraction=.5 if lucid else None,
        payout_share=.9 if lucid else 1,
        payout_timing='First eligible observed trade close in the request window, otherwise session close.'
                      if lucid else 'At session close.')
    return basket.funded_results(paths, applied), paths, applied


def oos_window(indices, prepared):
    windows = prepared['oos_days']
    if not all(index in windows for index in indices):
        return [], 'OOS equity requires a saved OOS child for each member in this combination.'
    combined = set.intersection(*(set(windows[index]) for index in indices))
    return (sorted(combined), None) if combined else ([], 'These members have no common observed OOS sessions.')


def rank(rows):
    ordered = sorted(rows, key=lambda row: (-row['score'], row['micros'], row['combination']))
    position = 1
    for _, group in groupby(ordered, key=lambda row: row['score']):
        tied = list(group)
        for row in tied:
            row.update(rank=position, tied=len(tied) > 1)
        position += len(tied)
    return ordered


def calculate(runs, body, configuration, prepared, staged, progress):
    basket.verify(runs, prepared)
    horizon = configuration['observation_sessions']
    workload_info = workload(len(body.members), body.minimum_members, body.maximum_members,
                             body.minimum_micros, body.maximum_micros, horizon)
    simulation = prepared['simulation']
    path_seeds = [int(np.random.SeedSequence([simulation.seed, path]).generate_state(1)[0])
                  for path in range(simulation.simulations)]
    is_days = prepared['is_days']
    phase = body.phase
    evaluate = evaluation if phase == 'evaluation' else funded
    subsets = (indices for count in range(body.minimum_members, body.maximum_members + 1)
               for indices in combinations(range(len(body.members)), count))
    ranked, results = [], []
    for number, indices in enumerate(subsets, 1):
        weights = [body.members[index].weight for index in indices]
        books = [prepared['is_books'][index] for index in indices]
        snapshots = {'is': [prepared['snapshots']['is'][index] for index in indices]}
        directory = f'combination_{number}'
        output = staged / directory
        output.mkdir()
        oos_days, oos_note = oos_window(indices, prepared)
        if oos_days:
            by_id = {source['backtest']['id']: source for source in prepared['snapshots']['oos']}
            snapshots['oos'] = [by_id[body.members[index].oos_backtest_id] for index in indices]
            oos_books = [prepared['oos_books'][index] for index in indices]
        sizes = []
        for size in range(body.minimum_micros, body.maximum_micros + 1):
            progress(f'Prop Desk search · {len(ranked) + 1} of {workload_info["pairs"]} pairs')
            allocation = basket.allocation(weights, size)
            targets = allocation['micros']
            admitted_is, skipped = basket.admitted(books, is_days, weights, targets)
            metrics, paths, rules = evaluate(admitted_is, targets, prepared, horizon, path_seeds)
            score = (metrics['probabilities']['passed'] if phase == 'evaluation'
                     else metrics['first_year_mean_receipts'])
            ranked.append(dict(combination=number, micros=size, score=score))
            histories, skips = {'is': admitted_is}, {'is': skipped}
            if oos_days:
                histories['oos'], skips['oos'] = basket.admitted(oos_books, oos_days, weights, targets)
            basket.equity(output, size, histories, targets, snapshots)
            (output / f'paths_{size}.json').write_text(canonical(paths), encoding='utf-8')
            sizes.append(dict(micros=size, allocation=allocation, metrics=metrics, overlap_skips=skips))
        results.append(dict(id=number, members=indices, sizes=sizes, directory=directory,
                            oos_days=oos_days, oos_note=oos_note))
    ranking = rank(ranked)
    basket.verify(runs, prepared)
    return dict(objective=OBJECTIVES[phase], ties=TIES, ranking=ranking, ranking_sha256=digest(ranking),
                combinations=results, workload=workload_info, is_days=is_days, law=basket.LAW), rules, path_seeds
