"""Account comparisons and presets layered over the existing Prop Desk owners."""

import csv
import json
from math import sqrt
from pathlib import Path
from statistics import median
from types import SimpleNamespace

from ..optimization_cache import digest
from . import desk, desk_basket as basket, desk_optimizer as optimizer, desk_overlap, desk_subset_optimizer as subsets
from .adapter import canonical, digest as file_digest

SIMULATION_VERSION = 'prop-desk-simulation-v2'
SEARCH_VERSION = 'prop-desk-optimizer-v3'
CONSERVATIVE_BREACH_CAP = 0.20
FUNDED_TIES = ('Within one binomial standard error of the highest in-sample payout rate, sort by '
               'median trading day of first payout. Then use higher rate, smaller MNQ and pool order.')


def prepare(runs, datasets, analyses, body, configuration, *, search):
    owner = subsets if search else optimizer
    prepared = owner.prepare(runs, datasets, analyses, body, configuration)
    version = SEARCH_VERSION if search else SIMULATION_VERSION
    source_hash = file_digest(Path(__file__))
    prepared['evidence']['implementation_sha256'][Path(__file__).name] = source_hash
    prepared['identity'] = digest(dict(version=version, parent=prepared['identity'], adapter=source_hash))
    return prepared


def metrics(phase, paths, rules, horizon, preset, evaluation_metrics):
    if phase == 'evaluation':
        return dict(evaluation_metrics, path_count=len(paths))
    window = basket.FIRST_YEAR if preset == 'first_year' else horizon
    projected = [
        dict(outcome=path['outcome'] if path['observed_weekdays'] <= window else 'open',
             lifetime_censored=path['lifetime_censored'] or path['observed_weekdays'] > window,
             trader_payouts=[event for event in path['trader_payouts'] if event[0] <= window],
             gross_account_deductions=[event for event in path['gross_account_deductions'] if event[0] <= window])
        for path in paths
    ]
    result = desk.funded_measurements(projected, rules)
    return dict(result, path_count=len(paths), reporting_sessions=window,
                median_trader_receipts=median(sum(amount for _, amount in path['trader_payouts'])
                                              for path in projected))


def funded_order(ranking):
    if not ranking:
        return []
    best = max(row['score'] for row in ranking)
    floor = best - sqrt(best * (1 - best) / ranking[0]['path_count'])
    near = [row for row in ranking if row['score'] >= floor]
    rest = [row for row in ranking if row['score'] < floor]
    near.sort(key=lambda row: (row['median_days'] if row['median_days'] is not None else float('inf'),
                               -row['score'], row['micros'], row['combination']))
    rest.sort(key=lambda row: (-row['score'], row['micros'], row['combination']))
    for position, row in enumerate(near + rest, 1):
        row.pop('tied', None)
        row.update(rank=position, near_best=len(near) > 1 and position <= len(near))
    return near + rest


def saved_metrics(output, row, phase, rules, horizon, preset):
    path = output / f'paths_{row["micros"]}.json'
    return metrics(phase, json.loads(path.read_text(encoding='utf-8')), rules, horizon, preset, row['metrics'])


def account_pair(body, configuration, prepared, combo, row, staged, rules, seeds, common_oos, preset, is_metrics):
    indices = combo['members']
    horizon = configuration['observation_sessions']
    output = staged / combo['directory']
    result = dict(is_metrics=is_metrics)
    missing = [body.members[index].source_backtest_id[:8] for index in indices
               if index not in prepared['oos_books']]
    if missing:
        return dict(result, unavailable='No linked OOS backtest for ' + ', '.join(missing) + '.')
    if not common_oos:
        return dict(result, unavailable='The linked candidate pool has no common observed OOS sessions.')
    targets = row['allocation']['micros']
    sequential = configuration.get('overlap_policy') == desk_overlap.POLICY
    weights = [body.members[index].weight for index in indices]
    days, _ = basket.admitted([prepared['oos_books'][index] for index in indices],
                              common_oos, weights, targets, sequential=sequential)
    owner = optimizer.evaluation if body.phase == 'evaluation' else optimizer.funded
    oos_metrics, paths, applied = owner(days, targets, prepared, horizon, seeds, sequential=sequential)
    if canonical(applied) != canonical(rules):
        raise ValueError('The OOS account rules differ from the IS account rules.')
    path_file = f'oos_paths_{row["micros"]}.json'
    (output / path_file).write_text(canonical(paths), encoding='utf-8')
    trades_file = f'oos_account_trades_{row["micros"]}.csv'
    chart_file = output / f'admitted_trades_{row["micros"]}.csv'
    with chart_file.open(newline='', encoding='utf-8') as source, (output / trades_file).open(
            'w', newline='', encoding='utf-8') as target:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(target, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(trade for trade in reader if trade['role'] == 'oos' and trade['session'] in days)
    return dict(result, oos_metrics=metrics(body.phase, paths, rules, horizon, preset, oos_metrics),
                oos_paths_file=path_file, oos_trades_file=trades_file)


def common_sessions(prepared):
    linked = list(prepared['oos_days'])
    return optimizer.oos_window(linked, prepared)[0] if linked else []


def select_size(sizes, rule):
    if rule == 'manual':
        return sizes[0], None
    eligible = [row for row in sizes if all(row['allocation']['micros'])]
    if not eligible:
        return None, 'No tested size assigns at least 1 MNQ to every member.'
    if rule == 'conservative':
        eligible = [row for row in eligible if row['metrics']['probabilities']['breached'] <= CONSERVATIVE_BREACH_CAP]
        if not eligible:
            return None, 'No tested size has an in-sample breach rate of 20% or less.'
    objective = 'optimal' if rule == 'conservative' else rule
    return min(eligible, key=lambda row: (-subsets.size_score(row['metrics'], objective), row['micros'])), None


def simulation(runs, body, configuration, prepared, staged, progress):
    full_basket = SimpleNamespace(**vars(body), minimum_members=len(body.members), maximum_members=len(body.members))
    result, rules, seeds = optimizer.calculate(runs, full_basket, configuration, prepared, staged, progress)
    combo, = result['combinations']
    sizes = combo['sizes']
    sizing = configuration['size_rule']
    chosen, unavailable = select_size(sizes, sizing)
    preset = 'optimal' if body.phase == 'evaluation' else 'account_life' if sizing == 'account_life' else 'first_year'
    horizon = configuration['observation_sessions']
    for index, row in enumerate(sizes, 1):
        progress(f'Prop Desk account comparison · {index} of {len(sizes)} sizes')
        is_metrics = saved_metrics(staged / combo['directory'], row, body.phase, rules, horizon, preset)
        row['account_comparison'] = account_pair(body, configuration, prepared, combo, row, staged,
                                                 rules, seeds, combo['oos_days'], preset, is_metrics)
    model = dict(size_rule=sizing, selected_micros=chosen['micros'] if chosen else None,
                 size_unavailable=unavailable, reporting_preset=preset,
                 size_provisional=sizing == 'account_life' and
                 any(row['metrics']['open_at_cutoff'] for row in sizes if all(row['allocation']['micros'])))
    return combo, model, rules, seeds


def search(runs, body, configuration, prepared, staged, progress):
    result, rules, seeds = subsets.calculate(runs, body, configuration, prepared, staged, progress)
    preset = configuration['size_rule']
    combinations = {combo['id']: combo for combo in result['combinations']}
    common_oos = common_sessions(prepared)
    comparisons = {}
    ranking = result['ranking']
    saved = {}
    for rank in ranking:
        combo = combinations[rank['combination']]
        row = next(row for row in combo['sizes'] if row['micros'] == rank['micros'])
        is_metrics = saved_metrics(staged / combo['directory'], row, body.phase, rules,
                                   configuration['observation_sessions'], preset)
        saved[combo['id']] = row, is_metrics
    if body.phase == 'funded':
        for rank in ranking:
            _, is_metrics = saved[rank['combination']]
            rank.update(score=is_metrics['probability_any_payout'], path_count=is_metrics['path_count'],
                        median_days=is_metrics['milestones'][0]['median_trading_day'])
        ranking = funded_order(ranking)
        result.update(ranking=ranking, ranking_sha256=digest(ranking), ties=FUNDED_TIES)
    for index, rank in enumerate(ranking, 1):
        combo = combinations[rank['combination']]
        row, is_metrics = saved[combo['id']]
        progress(f'Prop Desk OOS accounts · {index} of {len(ranking)} ranked subsets')
        comparisons[combo['id']] = dict(micros=row['micros'], **account_pair(
            body, configuration, prepared, combo, row, staged, rules, seeds, common_oos, preset, is_metrics))
    result['account_comparison'] = dict(rows=comparisons, reporting_preset=preset,
                                       oos_days=common_oos, method='Common observed sessions of linked candidates')
    return result, rules, seeds
