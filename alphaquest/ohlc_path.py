"""MultiCharts non-magnified OHLC emulation, without materializing synthetic ticks.

Segments visit every executable order level between vertices. These are modeled
prices, not observed trades. A suffix starts exactly where an order activates.
"""
from dataclasses import dataclass
from decimal import Decimal
from .decimal_math import subtract

VERSION = 'multicharts-ohlc-nearest-extreme-v1'
POLICIES = ('multicharts', 'high_first', 'low_first')


def prices(bar, policy='multicharts'):
    if policy not in POLICIES:
        raise ValueError('Unknown OHLC path policy.')
    high_first = policy == 'high_first' or (policy == 'multicharts' and
                                          subtract(bar.high, bar.open) < subtract(bar.open, bar.low))
    return (bar.open, bar.high, bar.low, bar.close) if high_first else (bar.open, bar.low, bar.high, bar.close)


@dataclass(frozen=True, slots=True)
class Hit:
    segment: int  # zero means the activation observation (possibly an opening gap)
    price: Decimal

    def suffix(self, path):
        return (self.price, *path[self.segment + 1:]) if self.segment == 0 else (self.price, *path[self.segment:])

    def prefix(self, path):
        return (*path[:self.segment], self.price) if self.segment else (self.price,)


def first_hit(path, *, lower=None, upper=None):
    """Earliest inclusive crossing, with Open observed before interpolated prices."""
    start = path[0]
    if (lower is not None and start <= lower) or (upper is not None and start >= upper):
        return Hit(0, start)
    for i, (a, b) in enumerate(zip(path, path[1:]), 1):
        if upper is not None and a < upper <= b:
            return Hit(i, upper)
        if lower is not None and b <= lower < a:
            return Hit(i, lower)
    return None


def rank(hit, path):
    return hit.segment, subtract(hit.price, path[max(0, hit.segment - 1)]).copy_abs()
