"""Exhaustively rank the declared Prop Desk allocations on common IS paths."""

from pathlib import Path
from time import monotonic

from ..optimization_cache import digest
from . import desk_basket, desk_overlap, desk_parity, desk_recommendation as engine, parallel
from .adapter import digest as file_digest

VERSION = 'prop-desk-global-ranking-v1'
MAX_ALLOCATIONS = 1000
MAX_ALLOCATION_SESSIONS = 100_000
TOP = 5
BATCH_SIZE = 12


def workload(configuration):
    low, high = configuration['minimum_micros'], configuration['maximum_micros']
    groups = engine.subsets(len(configuration['members']), configuration['minimum_members'])
    total = sum(engine.feasible_count(len(group), low, high) for group in groups)
    limit = min(MAX_ALLOCATIONS, MAX_ALLOCATION_SESSIONS // configuration['observation_sessions'])
    if not total or total > limit:
        raise ValueError(f'Full grid has {total:,} allocations. This horizon allows 1–{limit:,}. '
                         'Narrow the total MNQ range or raise the minimum strategy count.')
    return total


def prepare(runs, datasets, analyses, body, configuration):
    prepared = engine.prepare(runs, datasets, analyses, body, configuration)
    implementation = prepared['evidence']['implementation_sha256']
    implementation[Path(__file__).name] = file_digest(Path(__file__))
    prepared['identity'] = digest(dict(version=VERSION, parent=prepared['identity'], implementation=implementation))
    return prepared


def score_batch(task):
    days, targets, prepared, configuration, seeds = task
    results, rules = [], None
    for counts in targets:
        metrics, _, rules = engine.evaluate(days, counts, prepared, configuration, seeds)
        results.append(metrics)
    return results, rules


def top_allocations(groups, configuration, paths):
    evaluation = configuration['phase'] == 'evaluation'
    entries = []
    for group in groups:
        for row in group['candidates']:
            if row['paths'] != paths:
                continue
            metrics = row['metrics']
            score = metrics['probabilities']['passed'] if evaluation else metrics['probability_any_payout']
            days = (metrics['median_trading_days_to_target'] if evaluation else metrics['milestones'][0]['median_trading_day'])
            key = (-score, days if days is not None else float('inf'), row['tested_total'], row['combination'], row['targets'])
            entries.append((key, dict(combination=row['combination'], candidate=row['id'], micros=row['tested_total'],
                score=score, median_days=days, path_count=paths, size_score=-engine.size_key(row, configuration)[0],
                size_provisional=row['size_provisional'])))
    top = sorted(entries, key=lambda item: item[0])[:TOP]
    return [dict(entry, rank=position) for position, (_, entry) in enumerate(top, 1)]


def calculate(prepared, configuration, progress):
    total = workload(configuration)
    seeds = engine.path_seeds(prepared['simulation'])
    paths = len(seeds)
    members = configuration['members']
    low, high = configuration['minimum_micros'], configuration['maximum_micros']
    sequential = bool(configuration.get('overlap_policy'))
    worker_inputs = {key: prepared[key] for key in ('profile', 'simulation', 'sampling')}
    worker_inputs['evidence'] = {'kernel': prepared['evidence']['kernel']}
    groups, tasks, batches = [], [], []
    for number, indices in enumerate(engine.subsets(len(members), configuration['minimum_members']), 1):
        targets = list(engine.positive_mixes(len(indices), low, high))
        if not targets:
            continue
        weights = [members[i]['weight'] for i in indices]
        books = [prepared['is_books'][i] for i in indices]
        # Every included member has a positive target. Admission and overlap
        # order are the same for each size, before the account applies its rules.
        admitted, _ = desk_basket.admitted(books, prepared['is_days'], weights, [1] * len(indices), sequential=sequential)
        days = {day: [(member, {'scenario': trade['scenario']}) for member, trade in stream]
                for day, stream in admitted.items()}
        rows = [dict(id=f'{number}-' + '-'.join(map(str, counts)), combination=number, targets=counts,
                     paths=paths, path_stages=[paths], tested_total=sum(counts)) for counts in targets]
        groups.append(dict(id=number, members=indices, feasible=len(rows), candidates=rows, unavailable=None))
        for offset in range(0, len(rows), BATCH_SIZE):
            batch = rows[offset:offset + BATCH_SIZE]
            tasks.append((days, [row['targets'] for row in batch], worker_inputs, configuration, seeds))
            batches.append(batch)

    last_update = 0.

    def notify(done, count, workers, _):
        nonlocal last_update
        now = monotonic()
        if now - last_update >= 0.5 or done == count:
            progress(f'Scoring {total:,} allocations · {done}/{count} batches · {workers} workers')
            last_update = now

    scored = parallel.map_reported(score_batch, tasks, checkpoint=lambda: None, notify=notify, cancel=lambda: None)
    winners, applied = [], None
    for batch, (scores, applied) in zip(batches, scored, strict=True):
        for row, metrics in zip(batch, scores, strict=True):
            row['metrics'] = metrics
            row['size_provisional'] = configuration['size_rule'] == 'account_life' and bool(metrics['open_at_cutoff'])
    for group in groups:
        winners.append(min(group['candidates'], key=lambda row: engine.size_key(row, configuration)))
    ranking = top_allocations(groups, configuration, paths)
    return dict(law=desk_overlap.LAW if sequential else desk_basket.LAW, ranking=ranking,
                ranking_sha256=digest(ranking), group_ranking=engine.rank(winners, configuration, paths),
                groups=groups, is_days=prepared['is_days'], oos_days=desk_parity.common_sessions(prepared),
                search_policy=dict(method='global_full_grid', top=TOP),
                workload=dict(feasible=total, tested=total, exhaustive=True, account_paths_computed=total * paths,
                              workers=parallel.diagnostics()['workers_used'])), applied, seeds
