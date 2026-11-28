"""Rank whole-MNQ allocations using verified saved trades and paired account paths."""

from collections import Counter, OrderedDict
import csv
from functools import lru_cache
from itertools import combinations
from math import comb, sqrt
from pathlib import Path
from statistics import mean, median, stdev
from threading import Lock

import numpy as np

from ..optimization_cache import digest
from . import desk, desk_basket as basket, desk_optimizer as optimizer, desk_overlap, desk_parity
from . import lucid_backend, native_backend, parallel
from .adapter import canonical, digest as file_digest

VERSION = 'prop-desk-recommendation-v2'
LEGACY_VERSION = 'prop-desk-recommendation-v1'
DETAIL_VERSION = 'prop-desk-recommendation-evidence-v1'
MAX_MEMBERS = 4
EXACT_LIMIT = 24
FULL_SCREEN_LIMIT = 256
SCREEN_PATHS = 96
REFINEMENT_PATHS = 384
PAIRED_SE_MULTIPLIER = 2
SCREEN_PER_SUBSET = 9
FINALISTS = 2
CACHE_LIMIT = 4096


def prepare(runs, datasets, analyses, body, configuration):
    prepared = optimizer.prepare(runs, datasets, analyses, body, configuration)
    implementation = prepared['evidence']['implementation_sha256']
    for module in (desk_parity, parallel):
        path = Path(module.__file__)
        implementation[path.name] = file_digest(path)
    implementation[Path(__file__).name] = file_digest(Path(__file__))
    prepared['identity'] = digest(dict(version=VERSION, parent=prepared['identity'], implementation=implementation))
    return prepared


def subsets(size, minimum):
    return list(indices for count in range(minimum, size + 1) for indices in combinations(range(size), count))


def weighted(target_weights, low, high):
    allocations = {}
    for total in range(low, high + 1):
        row = tuple(basket.allocation(target_weights, total)['micros'])
        if all(row):
            allocations.setdefault(row, total)
    return allocations


def feasible_count(size, low, high):
    return comb(high, size) - comb(max(low, size) - 1, size) if high >= size else 0


def positive_mixes(size, low, high):
    if size == 1:
        for value in range(max(1, low), high + 1):
            yield (value,)
        return
    for first in range(1, high - size + 2):
        for rest in positive_mixes(size - 1, low - first, high - first):
            yield (first, *rest)


def balanced(size, total):
    share, remainder = divmod(total, size)
    return tuple(share + (index < remainder) for index in range(size))


def neighbors(row, low, high):
    for index in range(len(row)):
        for delta in (-1, 1):
            if row[index] + delta > 0 and low <= sum(row) + delta <= high:
                yield tuple(value + (delta if i == index else 0) for i, value in enumerate(row))
        if row[index] > 1:
            for other in range(len(row)):
                if index != other:
                    yield tuple(value - (i == index) + (i == other) for i, value in enumerate(row))


@lru_cache(maxsize=8)
def path_seeds(simulation):
    return tuple(int(np.random.SeedSequence([simulation.seed, index]).generate_state(1)[0])
                 for index in range(simulation.simulations))


@lru_cache(maxsize=8)
def schedules(length, seeds, horizon, block):
    blocks = (horizon + block - 1) // block
    offsets = np.arange(block, dtype=np.int32)
    result = np.empty((len(seeds), horizon), dtype=np.int32)
    for index, seed in enumerate(seeds):
        starts = np.random.RandomState(seed).randint(length, size=blocks)
        result[index] = ((starts[:, None] + offsets) % length).ravel()[:horizon]
    result.flags.writeable = False
    return result


def evaluation_paths(days, targets, prepared, horizon, seeds, sequential):
    book = basket.session_book(days, targets, sequential=sequential)
    profile = prepared['profile']
    lucid = profile.profile_id == 'lucidflex-50k'
    _, _, rules = optimizer.evaluation(days, targets, prepared, horizon, seeds[:1], sequential=sequential)
    draws = schedules(len(book), seeds, horizon, prepared['sampling'].block_weekdays)
    timeout = 'observation_cutoff' if lucid else 'provider_expired'
    paths = []
    if lucid:
        session = lucid_backend.module()._fixed_evaluation_session
        consistency = profile.consistency_percent / 100
        # Actual calendar is necessary even though desk Evaluation currently leaves inactivity disabled.
        calendar = [(index // 5) * 7 + index % 5 for index in range(horizon)]
        for draw in draws:
            equity = high = best = 0.
            last = 0
            for day, index in enumerate(draw):
                equity, high, best, last, state, _, _ = session(book[index], equity, high, best, last,
                    calendar[day], 1, 1200., consistency, profile.lucid_inactivity_enforced)
                if state != 'open':
                    break
            paths.append(dict(outcome={'open': timeout, 'blown': 'breached'}.get(state, state), trading_sessions=day + 1))
    else:
        session = native_backend.module().evaluation_session
        for draw in draws:
            equity = high = 0.
            for day, index in enumerate(draw, 1):
                equity, high, state, _, _ = session(book[index], equity, high, 1)
                if state != 'open':
                    break
            paths.append(dict(outcome={'open': timeout, 'blown': 'breached'}.get(state, state), trading_sessions=day))
    counts = dict.fromkeys(('passed', 'breached', timeout), 0)
    counts.update(Counter(row['outcome'] for row in paths))
    passing = [row['trading_sessions'] for row in paths if row['outcome'] == 'passed']
    metrics = dict(outcome_counts=counts, probabilities={key: value / len(paths) for key, value in counts.items()},
                   pass_rate_interval_95=desk.wilson(len(passing), len(paths)),
                   median_trading_days_to_target=median(passing) if passing else None)
    return metrics, paths, rules


def funded_paths(days, targets, prepared, horizon, seeds, sequential):
    lucid = prepared['profile'].profile_id == 'lucidflex-50k'
    requested = sum(targets) if sequential else max(targets)
    backend = lucid_backend if lucid else native_backend
    # The Lucid first-tier owner uses its fixed compiled transition. Keep that exact numerical path.
    if lucid and requested <= backend.Rules().levels[0][1]:
        return optimizer.funded(days, targets, prepared, horizon, seeds, sequential=sequential)
    _, _, applied = optimizer.funded(days, targets, prepared, horizon, seeds[:1], sequential=sequential)
    profile, simulation = prepared['profile'], prepared['simulation']
    rules = (backend.Rules(daily_loss=1200., inactivity_enforced=profile.lucid_inactivity_enforced)
             if lucid else backend.Rules(approval_day_counts=profile.approval_day_counts))
    opening = rules.levels[0][1]
    dynamic = requested > opening
    if dynamic:
        variants = {cap: basket.session_book(days, targets, cap, sequential=sequential)
                    for cap in {min(requested, cap, simulation.max_micros) for _, cap, _ in rules.levels}}
    else:
        book = basket.session_book(days, targets, sequential=sequential)
    paths = []
    create = backend.module().FundedAccount
    for draw in schedules(len(days), seeds, horizon, prepared['sampling'].block_weekdays):
        account = create(rules)
        for index in draw:
            if dynamic:
                def trades():
                    yield from variants[account.effective_micros][index]
                account.advance(trades(), requested, simulation.max_micros)
            else:
                account.advance(book[index], 1, simulation.max_micros)
            if account.outcome != 'open':
                break
        paths.append(dict(outcome=account.outcome, observed_weekdays=account.day, trader_payouts=list(account.payouts),
            gross_account_deductions=list(getattr(account, 'withdrawals', account.payouts)), equity=account.equity,
            lifetime_censored=account.outcome == 'open'))
    return basket.funded_results(paths, applied), paths, applied


def evaluate(days, targets, prepared, configuration, seeds):
    phase = configuration['phase']
    owner = evaluation_paths if phase == 'evaluation' else funded_paths
    horizon = configuration['observation_sessions']
    metrics, paths, rules = owner(days, targets, prepared, horizon, seeds,
                                  configuration.get('overlap_policy') == desk_overlap.POLICY)
    preset = configuration['size_rule']
    if phase == 'funded' and (preset == 'account_life' or horizon == basket.FIRST_YEAR):
        # Every path is already bounded by this reporting horizon.
        reported = dict(path_count=len(paths), reporting_sessions=horizon,
                        median_trader_receipts=median(sum(amount for _, amount in path['trader_payouts'])
                                                      for path in paths))
    else:
        reported = desk_parity.metrics(phase, paths, rules, horizon, preset, metrics)
    metrics = {**metrics, **reported}
    return metrics, paths, rules


_scores = OrderedDict()
_lock = Lock()


def cached_score(key):
    with _lock:
        if key in _scores:
            _scores.move_to_end(key)
            return _scores[key]
    return None


def save_score(key, value):
    with _lock:
        _scores[key] = value
        if len(_scores) > CACHE_LIMIT:
            _scores.popitem(last=False)


def score_task(task):
    days, targets, prepared, configuration, seeds, collect_outcomes = task
    metrics, paths, rules = evaluate(days, targets, prepared, configuration, seeds)
    outcomes = ()
    if collect_outcomes:
        if configuration['phase'] == 'evaluation':
            outcomes = tuple(int(path['outcome'] == 'passed') for path in paths)
        else:
            horizon = metrics['reporting_sessions']
            outcomes = tuple(sum(amount for day, amount in path['trader_payouts'] if day <= horizon)
                             for path in paths)
    return metrics, rules, outcomes


def size_key(row, configuration):
    metrics = row['metrics']
    total = row['tested_total']
    if configuration['phase'] == 'evaluation':
        days = metrics['median_trading_days_to_target']
        return -metrics['probabilities']['passed'], total, (days if days is not None else float('inf')), row['targets']
    return -metrics['mean_trader_receipts'], total, row['targets']


def refine_targets(leaders, outcomes):
    leader = outcomes[leaders[0]['targets']]
    retained = [row['targets'] for row in leaders[:FINALISTS]]
    for row in leaders[FINALISTS:]:
        targets = row['targets']
        differences = [a - b for a, b in zip(leader, outcomes[targets], strict=True)]
        error = stdev(differences) / sqrt(len(differences))
        if mean(differences) <= PAIRED_SE_MULTIPLIER * error:
            retained.append(targets)
    return retained


def rank(winners, configuration, count):
    evaluation = configuration['phase'] == 'evaluation'
    ranking = []
    for row in winners:
        metrics = row['metrics']
        ranking.append(dict(combination=row['combination'], candidate=row['id'], micros=row['tested_total'],
            score=metrics['probabilities']['passed'] if evaluation else metrics['probability_any_payout'],
            median_days=(metrics['median_trading_days_to_target'] if evaluation else metrics['milestones'][0]['median_trading_day']),
            path_count=count, size_score=-size_key(row, configuration)[0],
            size_provisional=row['size_provisional']))
    return desk_parity.funded_order(ranking)


def calculate(prepared, configuration, progress):
    seeds = path_seeds(prepared['simulation'])
    members = configuration['members']
    groups = subsets(len(members), configuration['minimum_members'])
    low, high = configuration['minimum_micros'], configuration['maximum_micros']
    weights = [member['weight'] for member in members]
    weighted_mode = configuration['allocation_search'] == 'weighted'
    group_weights = [[weights[i] for i in group] for group in groups]
    counts = [len(weighted(w, low, high)) if weighted_mode else feasible_count(len(group), low, high)
              for group, w in zip(groups, group_weights, strict=True)]
    total = sum(counts)
    exact = weighted_mode or total <= EXACT_LIMIT
    full_screen = not exact and total <= FULL_SCREEN_LIMIT
    if not total:
        raise ValueError('No feasible allocation. Increase maximum total MNQ or lower the strategy minimum.')
    law = desk_overlap.LAW if configuration.get('overlap_policy') else basket.LAW
    identity = digest(dict(implementation=prepared['evidence']['implementation_sha256'],
        kernel=prepared['evidence']['kernel'], profile=prepared['evidence']['profile'],
        dataset=prepared['evidence']['dataset'], dates=prepared['is_days'],
        settings={key: configuration.get(key) for key in ('phase', 'observation_sessions', 'size_rule', 'overlap_policy')},
        sampling=prepared['evidence']['sampling'], simulation=prepared['evidence']['simulation']))
    results, winners, solo = [], [], {}
    pending = []
    parallel_funded = configuration['phase'] == 'funded' and len(prepared['is_days']) >= 120
    worker_prepared = {key: prepared[key] for key in ('profile', 'simulation', 'sampling')}
    worker_prepared['evidence'] = {'kernel': prepared['evidence']['kernel']}
    cache_hits = tests = path_count = 0
    applied = None
    for number, (group, w, count) in enumerate(zip(groups, group_weights, counts, strict=True), 1):
        books = [prepared['is_books'][i] for i in group]
        snapshots = [prepared['snapshots']['is'][i] for i in group]
        source_key = digest([(s['manifest_sha256'], s['trades_sha256'], s['excursion_input'], s.get('native_risk'))
                             for s in snapshots])
        progress(f'Ranking subset {number} of {len(groups)}')
        low_here = max(low, len(group))
        weighted_totals = weighted(w, low, high)
        baseline = list(weighted_totals)
        if not weighted_mode:
            baseline = [targets for targets in baseline if low_here <= sum(targets) <= high]
        rows = {}
        screen_outcomes = {}

        def test(targets, n, defer=False, *, collect_outcomes=False):
            nonlocal applied, cache_hits, tests, path_count
            previous = rows.get(targets)
            if previous and previous['paths'] == n:
                return previous
            key = (identity, source_key, tuple(w), targets, seeds[:n], collect_outcomes)

            cached = cached_score(key)
            tests += 1
            result = dict(id=f'{number}-' + '-'.join(map(str, targets)), combination=number,
                          targets=targets, paths=n, screened=previous is not None,
                          path_stages=[*(previous['path_stages'] if previous else []), n],
                          tested_total=weighted_totals[targets] if weighted_mode else sum(targets),
                          weighted_baseline=targets in baseline)
            if cached is not None:
                result['metrics'], applied, outcomes = cached
                cache_hits += 1
            else:
                path_count += n
                days, _ = basket.admitted(books, prepared['is_days'], w, targets,
                                           sequential=bool(configuration.get('overlap_policy')))
                if defer:
                    days = {day: [(member, {'scenario': trade['scenario']}) for member, trade in stream]
                            for day, stream in days.items()}
                task = (days, targets, worker_prepared, configuration, seeds[:n], collect_outcomes)
                if defer:
                    pending.append((key, result, task))
                else:
                    result['metrics'], applied, outcomes = value = score_task(task)
                    save_score(key, value)
            if collect_outcomes:
                screen_outcomes[targets] = outcomes
            rows[targets] = result
            return result

        if count:
            defer = parallel_funded and len(group) > 1
            if exact or count <= FINALISTS:
                mixes = baseline if weighted_mode else positive_mixes(len(group), low, high)
                for choice in mixes:
                    test(choice, len(seeds), defer)
            elif full_screen:
                screening = min(SCREEN_PATHS, len(seeds))
                refinement = min(REFINEMENT_PATHS, len(seeds))
                for choice in positive_mixes(len(group), low, high):
                    test(choice, screening, collect_outcomes=screening < refinement)
                if screening < refinement:
                    leaders = sorted(rows.values(), key=lambda row: size_key(row, configuration))
                    advancing = refine_targets(leaders, screen_outcomes)
                    baseline_row = next((row for row in leaders if row['targets'] in baseline), None)
                    if baseline_row and baseline_row['targets'] not in advancing:
                        advancing.append(baseline_row['targets'])
                    for choice in advancing:
                        test(choice, refinement)
                    leaders = sorted((rows[choice] for choice in advancing), key=lambda row: size_key(row, configuration))
                    finalists = [row['targets'] for row in leaders[:FINALISTS]]
                    baseline_row = next((row for row in leaders if row['targets'] in baseline), None)
                    if baseline_row and baseline_row['targets'] not in finalists:
                        finalists.append(baseline_row['targets'])
                    for choice in finalists:
                        test(choice, len(seeds), defer)
            else:
                screening = min(SCREEN_PATHS, len(seeds))
                totals = sorted({low_here, (low_here + high) // 2, high})
                starts = [balanced(len(group), total) for total in totals]
                starts.extend(baseline[i] for i in sorted({0, len(baseline) // 2, len(baseline) - 1}) if baseline)
                if all(i in solo for i in group):
                    solo_mix = tuple(solo[i] for i in group)
                    if low_here <= sum(solo_mix) <= high:
                        starts.append(solo_mix)
                for choice in dict.fromkeys(starts):
                    test(choice, screening)
                leaders = sorted(rows.values(), key=lambda row: size_key(row, configuration))
                for leader in leaders[:2]:
                    for choice in neighbors(leader['targets'], low_here, high):
                        if len(rows) == SCREEN_PER_SUBSET:
                            break
                        test(choice, screening)
                leaders = sorted(rows.values(), key=lambda row: size_key(row, configuration))
                finalists = [row['targets'] for row in leaders[:FINALISTS]]
                # Give the strongest screened weighted baseline the same confirmation budget.
                baseline_row = next((row for row in leaders if row['targets'] in baseline), None)
                if baseline_row and baseline_row['targets'] not in finalists:
                    finalists.append(baseline_row['targets'])
                for choice in finalists:
                    test(choice, len(seeds), defer)
            if len(group) == 1:
                scored = [row for row in rows.values() if row['paths'] == len(seeds)]
                solo[group[0]] = min(scored, key=lambda row: size_key(row, configuration))['targets'][0]
        results.append(dict(id=number, members=group, feasible=count, candidates=list(rows.values()),
                            unavailable=None if count else 'No positive allocation fits this subset.'))
    if pending:
        computed = parallel.map_reported(score_task, [task for _, _, task in pending], checkpoint=lambda: None,
            notify=lambda done, total, workers, _: progress(f'Confirming Funded allocations · {done}/{total}'),
            cancel=lambda: None)
        for (key, row, _), value in zip(pending, computed, strict=True):
            row['metrics'], applied, _ = value
            save_score(key, value)
    for group in results:
        if group['unavailable']:
            continue
        scored = [row for row in group['candidates'] if row['paths'] == len(seeds)]
        winner = min(scored, key=lambda row: size_key(row, configuration))
        winner['size_provisional'] = configuration['size_rule'] == 'account_life' and any(
            row['metrics']['open_at_cutoff'] for row in scored)
        winners.append(winner)
    ranking = rank(winners, configuration, len(seeds))
    return dict(law=law, ranking=ranking, ranking_sha256=digest(ranking), groups=results,
                is_days=prepared['is_days'], oos_days=desk_parity.common_sessions(prepared),
                search_policy=dict(method='exhaustive' if exact else 'full_screen' if full_screen else 'local_screen',
                                   exact_limit=EXACT_LIMIT, full_screen_limit=FULL_SCREEN_LIMIT,
                                   refinement_paths=REFINEMENT_PATHS, paired_se_multiplier=PAIRED_SE_MULTIPLIER,
                                   screening_paths=SCREEN_PATHS,
                                   screened_per_subset=SCREEN_PER_SUBSET, finalists=FINALISTS,
                                   retain_best_screened_weighted_baseline=True),
                workload=dict(feasible=total, tested=sum(len(group['candidates']) for group in results),
                              exhaustive=exact or all(len(group['candidates']) == group['feasible'] and
                                  all(row['paths'] == len(seeds) for row in group['candidates']) for group in results),
                              score_calls=tests, score_cache_hits=cache_hits, account_paths_computed=path_count,
                              workers=parallel.diagnostics()['workers_used'])), applied, seeds


def find_candidate(report, id):
    search = report['recommendation']
    for group in search['groups']:
        for candidate in group['candidates']:
            if candidate['id'] == id:
                return group, candidate
    raise ValueError('This allocation was not evaluated in the saved search.')


def evidence(runs, prepared, report, group, row, staged):
    configuration = report['configuration']
    indices = group['members']
    targets = row['targets']
    snapshots = {'is': [prepared['snapshots']['is'][i] for i in indices]}
    plan = [configuration['members'][i] for i in indices]
    weights = [member['weight'] for member in plan]
    sequential = configuration.get('overlap_policy') == desk_overlap.POLICY
    seeds = tuple(report['provenance']['path_seeds'])[:row['paths']]
    is_days = report['recommendation']['is_days']
    days, skipped = basket.admitted([prepared['is_books'][i] for i in indices], is_days, weights, targets,
                                    sequential=sequential)
    metrics, paths, rules = evaluate(days, targets, prepared, configuration, seeds)
    if digest(metrics) != digest(row['metrics']) or digest(rules) != digest(report['rules']):
        raise ValueError('The regenerated IS account evidence differs from the sealed allocation.')
    (staged / f'paths_{sum(targets)}.json').write_text(canonical(paths), encoding='utf-8')
    pair = dict(is_metrics=metrics, overlap_skips={'is': skipped})
    timeline = {'is': days}
    missing = [plan[offset]['source_backtest_id'][:8] for offset, i in enumerate(indices) if i not in prepared['oos_books']]
    common_oos = report['recommendation']['oos_days']
    if missing:
        pair['unavailable'] = 'No linked OOS backtest for ' + ', '.join(missing) + '.'
    elif not common_oos:
        pair['unavailable'] = 'The linked candidate pool has no common observed OOS sessions.'
    else:
        by_id = {s['backtest']['id']: s for s in prepared['snapshots']['oos']}
        snapshots['oos'] = [by_id[member['oos_backtest_id']] for member in plan]
        days, skipped = basket.admitted([prepared['oos_books'][i] for i in indices], common_oos,
                                        weights, targets, sequential=sequential)
        oos, paths, applied = evaluate(days, targets, prepared, configuration, seeds)
        if digest(applied) != digest(rules):
            raise ValueError('The OOS account rules differ from the sealed IS rules.')
        (staged / 'oos_paths.json').write_text(canonical(paths), encoding='utf-8')
        pair.update(oos_metrics=oos, oos_days=common_oos)
        pair['overlap_skips']['oos'] = skipped
        timeline['oos'] = days
    threshold = desk_overlap.threshold(rules) if sequential else None
    basket.equity(staged, sum(targets), timeline, targets, snapshots, overlap_threshold=threshold)
    if 'oos' in timeline:
        with (staged / f'admitted_trades_{sum(targets)}.csv').open(newline='', encoding='utf-8') as source, \
                (staged / 'oos_trades.csv').open('w', newline='', encoding='utf-8') as output:
            reader = csv.DictReader(source)
            writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
            writer.writeheader()
            writer.writerows(row for row in reader if row['role'] == 'oos')
    basket.verify(runs, prepared)
    return pair, snapshots
