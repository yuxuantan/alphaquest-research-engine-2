"""Predeclared small synthetic markets, never evidence of a real trading edge.

Prices are quarter-point MNQ observations. Sparse controlled paths deliberately
gap between red candles so entry eligibility and subsequent payoff are distinct.
Noise paths instead have IID symmetric close increments; no returns are filtered
or regenerated after observing a qualification result.
"""
from datetime import date, timedelta
from decimal import Decimal
from random import Random


D = Decimal
NOISE_SEEDS = (7, 31)


def sessions():
    result = []
    day = date(2026, 1, 5)
    while len(result) < 20:
        if day.weekday() < 5:
            result.append(day)
        day += timedelta(days=1)
    return result


def market_bytes(kind, *, seed=7):
    """Return source bytes and declared daily net per 1-MNQ hold parameter.

    Controlled paths enter at 101 and exit at the requested later close. Red
    candles after that entry cannot trigger a second position. Exact payoff is
    (exit - 101) * $2, with explicit zero costs. Clock-regime paths have two
    independent opportunities per session; unknown noise outcomes are not used
    to choose a seed, signal, grid, or qualification threshold.
    """
    lines = ['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    expected = {}
    rng = Random(seed)
    price = D(100)

    def emit(day, clock, opening, close):
        opening, close = D(opening), D(close)
        lines.append(','.join([day.strftime('%m/%d/%Y'), clock, str(opening),
            str(max(opening, close)+D('.25')), str(min(opening, close)-D('.25')),
            str(close), '10', '5', '5']))

    for index, day in enumerate(sessions()):
        if kind == 'noise':
            for minute in range(16):
                close = price + rng.choice((-1, 1))*D('.25')
                emit(day, f'09:{minute:02d}', price, close)
                price = close
            continue
        groups = [('09', [D(106)+i for i in range(6)])]
        if kind == 'isolated':
            groups = [('09', [D(96), D(111), D(96), D(96), D(96), D(96)])]
        elif kind == 'disappearing':
            # This change point precedes seeing any saved research result.
            groups = [('09', [D(106) if index < 6 else D(96)]*6)]
        elif kind == 'regime':
            groups = [('03', [D(100)]*6), ('09', [D(111)]*6)]
        elif kind != 'stable':
            raise ValueError(kind)
        daily = [D(0)]*6
        for hour, closes in groups:
            emit(day, hour+':00', 100, 100)
            emit(day, hour+':01', 100, 101)
            for offset, close in enumerate(closes, 2):
                emit(day, f'{hour}:{offset:02d}', close+D('.25'), close)
                daily[offset-2] += (close-D(101))*D(2)
            emit(day, hour+':08', 100, 100)
        emit(day, '16:00', 100, 100)
        expected[day.isoformat()] = [str(value) for value in daily]
    return ('\n'.join(lines)+'\n').encode(), expected
