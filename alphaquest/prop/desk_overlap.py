"""Sequential saved-trade approximation and advisory overlap evidence."""

from decimal import Decimal
from itertools import groupby


POLICY = 'sequential_mae'
LAW = ('Keep overlapping saved trades and score them in entry order. Same-time entries use weight, '
       'basket order and trade ID. Check each trade’s adverse excursion before booking its full net P&L. '
       'Opposite sides are processed as separate saved trades, with no position netting. '
       'Funded opening tiers cap the basket targets proportionally, rounded down per member. '
       'Combined MAE is an advisory sum of standalone excursions at target size. It does not affect '
       'account outcomes and cannot establish the timing or size of an actual combined loss. '
       'If excursion evidence is missing, the simulation uses its existing realized-loss proxy and the overlap screen marks the evidence incomplete.')


def version(base, configuration):
    return f'{base}-sequential-mae-v1' if configuration.get('overlap_policy') == POLICY else base


def threshold(rules):
    """Screen against the smaller initial allowance, without estimating path headroom."""
    if 'maximum_trailing_drawdown' in rules:
        drawdown, daily = rules['maximum_trailing_drawdown'], rules['daily_loss_limit']
    else:
        drawdown, daily = rules['max_dd'], rules.get('daily_loss', rules['levels'][0][2])
    return min(drawdown, daily) if daily else drawdown


def trade_mae(row, quantity):
    # The scenario book uses a one-NQ reference even when the source is MNQ.
    return Decimal(str(row['scenario'][1])) * quantity / 10 if row.get('mae_basis') else None


def overlap_marks(selected, targets, threshold):
    """Return the largest complete overlapping MAE scenario involving each trade."""
    marks, active = {}, []
    for entry, group in groupby(enumerate(selected), key=lambda item: item[1][1]['entry']):
        active = [other for other in active if selected[other][1]['exit'] > entry]
        active.extend(index for index, (_, row) in group if row['exit'] > entry)
        if len(active) < 2:
            continue
        estimates = [trade_mae(selected[other][1], targets[selected[other][0]]) for other in active]
        combined = None if None in estimates else sum(estimates)
        for other in active:
            mark = marks.setdefault(other, dict(combined=None, missing=False, flagged=False))
            if combined is None:
                mark['missing'] = True
            else:
                if mark['combined'] is None or combined > mark['combined']:
                    mark['combined'] = combined
                mark['flagged'] |= combined >= threshold
    return marks
