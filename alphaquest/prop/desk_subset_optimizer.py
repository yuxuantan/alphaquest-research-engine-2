"""Select one in-sample size per subset, then rank the selected allocations."""

from math import sqrt
from pathlib import Path

from ..optimization_cache import digest
from . import desk_optimizer
from .adapter import digest as file_digest

VERSION = 'prop-desk-optimizer-v2'
MODE = 'prop_desk_optimizer_subsets'
SIZE_RULES = {
    'optimal': 'Optimal · highest in-sample pass probability',
    'first_year': 'First year · highest mean trader receipts through trading day 261',
    'account_life': 'Account life · highest mean trader receipts through termination or observation cutoff',
}
EVALUATION_TIES = ('Within one standard error of the highest pass estimate, sort by fastest median days to pass. '
                   'Otherwise sort by pass probability. Remaining ties use smaller total MNQ, then pool order.')


def prepare(runs, datasets, analyses, body, configuration):
    prepared = desk_optimizer.prepare(runs, datasets, analyses, body, configuration)
    source_hash = file_digest(Path(__file__))
    prepared['evidence']['implementation_sha256'][Path(__file__).name] = source_hash
    prepared['identity'] = digest(dict(version=VERSION, sweep=prepared['identity'], selection_sha256=source_hash))
    return prepared


def size_score(metrics, rule):
    if rule == 'optimal':
        return metrics['probabilities']['passed']
    if rule == 'first_year':
        return metrics['first_year_mean_receipts']
    if rule == 'account_life':
        return metrics['mean_trader_receipts']
    raise ValueError(f'Unknown combination sizing rule {rule!r}.')


def select(result, phase, rule, paths):
    """Choose from the existing sweep on IS without reading any chart evidence."""
    evaluation = phase == 'evaluation'
    selected, unranked = [], []
    for combination in result['combinations']:
        eligible = [size for size in combination['sizes'] if all(size['allocation']['micros'])]
        number = combination['id']
        if not eligible:
            unranked.append(dict(combination=number, micros=combination['sizes'][-1]['micros'],
                                 reason='Every included member needs a positive target. Increase the maximum MNQ.'))
            continue
        winner = min(eligible, key=lambda size: (-size_score(size['metrics'], rule), size['micros']))
        metrics = winner['metrics']
        score = metrics['probabilities']['passed'] if evaluation else metrics['probability_any_payout']
        selected.append(dict(combination=number, micros=winner['micros'], score=score,
                             size_score=size_score(metrics, rule),
                             median_days=metrics['median_trading_days_to_target'] if evaluation else None,
                             size_provisional=rule == 'account_life' and
                             any(size['metrics']['open_at_cutoff'] for size in eligible)))
    if evaluation:
        best = max((row['score'] for row in selected), default=0)
        error = sqrt(best * (1 - best) / paths)
        leading = [row for row in selected if row['score'] >= best - error]
        remaining = [row for row in selected if row['score'] < best - error]
        leading.sort(key=lambda row: (row['median_days'] if row['median_days'] is not None else float('inf'),
                                      -row['score'], row['micros'], row['combination']))
        remaining.sort(key=lambda row: (-row['score'], row['micros'], row['combination']))
        ordered = leading + remaining
        for position, row in enumerate(ordered, 1):
            row.update(rank=position, near_best=len(leading) > 1 and position <= len(leading))
        ties = EVALUATION_TIES
    else:
        ordered = desk_optimizer.rank(selected)
        ties = desk_optimizer.TIES
    return dict(result, ranking=ordered, unranked=unranked, ranking_sha256=digest(ordered),
                objective='In-sample pass probability' if evaluation else 'In-sample chance of any payout',
                ties=ties, size_rule=rule, size_rule_label=SIZE_RULES[rule])


def calculate(runs, body, configuration, prepared, staged, progress):
    result, rules, seeds = desk_optimizer.calculate(runs, body, configuration, prepared, staged, progress)
    return select(result, body.phase, configuration['size_rule'], len(seeds)), rules, seeds
