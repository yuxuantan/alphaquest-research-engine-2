"""Independent arithmetic for the standalone trade-close diagnostic model."""

from itertools import accumulate
from math import floor
import numpy as np
import pytest

from alphaquest.prop import desk_diagnostics as diagnostics


class Draws:
    """Supply an explicit schedule, independent of the numerical generator."""
    def __init__(self, schedules):
        self.schedules = iter(schedules)

    def integers(self, limit, *, size):
        result = np.array(next(self.schedules))
        assert result.shape == ((size,) if isinstance(size, int) else size)
        assert (result < limit).all()
        return result


def test_closed_trade_recovery_and_fixed_cone_paths():
    values = [5, -3, 4, -4, 1, -3, 8, -2, -1, 2, -5, 2, -2, 1, -1, -1]
    trades = [dict(role='is' if index < 6 else 'oos', exit_utc=f'trade-{index + 1}', net_pnl=str(value))
              for index, value in enumerate(values)]
    actual = diagnostics.history(trades)
    assert [point['equity'] for point in actual['curve']] == [
        5, 2, 6, 2, 3, 0, 8, 6, 5, 7, 2, 4, 2, 3, 2, 1]
    assert [point['drawdown'] for point in actual['curve']] == [
        0, -3, 0, -4, -3, -6, 0, -2, -3, -1, -6, -4, -6, -5, -6, -7]
    assert actual['episodes'] == [
        dict(peak_trade=1, trough_trade=2, depth=3, recovered_at=3, through_trade=3, duration_trades=2),
        dict(peak_trade=3, trough_trade=6, depth=6, recovered_at=7, through_trade=7, duration_trades=4),
        dict(peak_trade=7, trough_trade=16, depth=7, recovered_at=None, through_trade=16, duration_trades=9),
    ]
    assert (actual['net'], actual['maximum_drawdown'], actual['longest_drawdown_trades']) == (1, 7, 9)
    # Four explicit two-trade paths: 5+5, 5-3, -3+5, -3-3.
    cone = diagnostics.cone([5, -3], 2, Draws([[0, 0, 1, 1], [0, 1, 0, 1]]), 4, observed=2)
    assert cone['points'][1]['bands'] == [-3, -3, 1, 5, 5]
    assert cone['points'][2]['bands'] == pytest.approx([-4.8, 0, 2, 4, 8.8])
    assert cone['observed_endpoint_percentile'] == 25


def test_matrix_depths_include_starting_equity_and_sum_needs_actual_history():
    source = [8, -2, -1, 2, -5, 2, -2, 1, -1, -1]
    indices = [[0] * 100, [1] * 100, [4, 0] * 50, list(range(10)) * 10]
    matrix = diagnostics.matrix(source, current_depth=7, rng=Draws([indices]), paths=4)
    assert [row['trades'] for row in matrix] == [10, 20, 30, 50, 100]

    def quantiles(values):
        values = sorted(values)
        result = []
        for percentile in (5, 50, 95):
            offset = (len(values) - 1) * percentile / 100
            low = floor(offset)
            result.append(values[low] + (values[low + 1] - values[low]) * (offset - low))
        return result

    for result in matrix:
        horizon = result['trades']
        paths = [[0, *accumulate(source[i] for i in draws[:horizon])] for draws in indices]
        counts = [max(max(path[:index + 1]) - path[index] for index in range(len(path))) for path in paths]
        terminal = [path[-1] for path in paths]
        assert result['drawdown_usd'] == pytest.approx([-value for value in quantiles(counts)])
        assert result['sum_usd'] == pytest.approx(quantiles(terminal))
        assert result['drawdown_percentile'] == 25 * sum(value < 7 for value in counts)
        assert result['observed_sum'] == (1 if horizon == 10 else None)
        assert result['sum_percentile'] == (25 * sum(value < 1 for value in terminal) if horizon == 10 else None)
