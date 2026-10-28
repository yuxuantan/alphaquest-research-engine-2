"""AlphaQuest account arithmetic and resampling, with no external engine calls.

Dollar amounts are relative to initial equity. Inputs are net trade results
and measured adverse excursions per original contract. No result files enter
these calculations. Parity qualification is maintained outside this module.
"""
from dataclasses import dataclass, field
from collections import deque
import numpy as np
import cython


@dataclass(frozen=True)
class Rules:
    max_dd: float = 2000.
    lock_profit: float = 100.
    safety_net: float = 2100.
    ladder: tuple = (1500., 1500., 2000., 2500., 2500., 3000.)
    qualifying_days: int = 5
    qualifying_profit: float = 250.
    consistency: float = .5
    inactivity_days: int = 2
    inactivity_profit: float = 50.
    inactivity_window: int = 21
    approval_day_counts: bool = True
    levels: tuple = ((0., 20, 1000.), (1500., 30, 1000.), (3000., 40, 2000.), (6000., 40, 3000.))


@cython.locals(balance=cython.double, threshold=cython.double, loss=cython.double,
               equity=cython.double, size=cython.double, daily_floor=cython.double, floor=cython.double)
def risk_hit(path, equity, size, daily_floor, floor):
    """First adverse threshold hit; observed jumps liquidate at the observed mark.

    Only record adverse extrema, in order, are needed for fixed session floors.
    Intrabar OHLC segments assume continuous threshold fills. Opening gaps and
    actual cost jumps bypass that assumption and can breach both floors at once.
    """
    threshold = max(daily_floor, floor)
    for loss, gap in path:
        balance = equity - loss * size / 10.
        if balance <= threshold:
            if gap:
                return (2 if balance <= floor else 1), balance
            return (2 if floor >= daily_floor else 1), threshold
    return 0, equity


@dataclass
class FundedAccount:
    rules: Rules = field(default_factory=Rules)
    equity: float = 0.
    high: float = 0.
    locked: bool = False
    day: int = 0
    cycle_start: float = 0.
    best_day: float = 0.
    qualifying: int = 0
    payouts: list = field(default_factory=list)
    activity: deque = field(default_factory=deque)
    outcome: str = 'open'
    approval: bool = False

    @cython.locals(opening=cython.double, floor=cython.double, cap=cython.double,
                   dll=cython.double, size=cython.double, daily_floor=cython.double,
                   net=cython.double, adverse=cython.double, trough=cython.double,
                   profit=cython.double, cycle_profit=cython.double, amount=cython.double)
    def advance(self, trades, micros, max_micros=40):
        """Consume (net, adverse[, ordered adverse frontier]) session trades."""
        if self.outcome != 'open':
            raise ValueError('Cannot advance a closed account.')
        r = self.rules
        self.day += 1
        opening = self.equity
        floor = r.lock_profit if self.locked else self.high - r.max_dd
        if floor >= r.lock_profit:
            self.locked = True
            floor = r.lock_profit
        cap, dll = r.levels[0][1:]
        for threshold, level_cap, level_dll in r.levels:
            if opening >= threshold:
                cap, dll = level_cap, level_dll
        size = min(micros, cap, max_micros)
        daily_floor = opening - dll
        for trade in trades:
            net, adverse = trade[0], trade[1]
            trough = self.equity - adverse * size / 10.
            if len(trade) > 2 and trough <= max(daily_floor, floor):
                hit, balance = risk_hit(trade[2], self.equity, size, daily_floor, floor)
                if hit:
                    self.equity = balance
                    if hit == 2:
                        self.outcome = 'blown'
                        return 0.
                    break
            if daily_floor > floor and trough <= daily_floor:
                self.equity = daily_floor
                break
            if daily_floor <= floor and trough <= floor:
                self.outcome = 'blown'
                return 0.
            self.equity += net * size / 10.
            if daily_floor > floor and self.equity <= daily_floor:
                self.equity = daily_floor
                break
            if daily_floor <= floor and self.equity <= floor:
                self.outcome = 'blown'
                return 0.
        profit = self.equity - opening
        if profit >= r.inactivity_profit:
            self.activity.append(self.day)
        while self.activity and self.activity[0] <= self.day - r.inactivity_window:
            self.activity.popleft()
        if profit < r.inactivity_profit and self.day >= r.inactivity_window and len(self.activity) < r.inactivity_days:
            self.outcome = 'inactive'
            return 0.
        if not self.approval or r.approval_day_counts:
            self.qualifying += profit >= r.qualifying_profit
            self.best_day = max(self.best_day, profit)
        self.approval = False
        cycle_profit = self.equity - self.cycle_start
        amount = 0.
        if (self.qualifying >= r.qualifying_days and cycle_profit > 0
                and self.best_day <= r.consistency * cycle_profit
                and self.equity - r.safety_net >= r.ladder[len(self.payouts)]):
            amount = r.ladder[len(self.payouts)]
            self.equity -= amount
            self.payouts.append((self.day, amount))
            self.cycle_start = self.equity
            self.qualifying = 0
            self.best_day = 0.
            self.approval = True
            if len(self.payouts) == len(r.ladder):
                self.outcome = 'paid_all'
        # The end-of-day trail observes the balance before a payout withdrawal.
        self.high = max(self.high, self.equity + amount)
        return amount


def sampled_days(rng, length, block):
    """Streaming circular blocks. Draw only when the previous block is used."""
    while True:
        start = int(rng.randint(length))
        for i in range(block):
            yield (start + i) % length


def compact_neutral_runs(days):
    """Keep one floor check per consecutive run of (zero net, zero adverse).

    Repeated neutral trades cannot change account state between those checks.
    Retaining the first also preserves an exact-floor hit. Session boundaries,
    all nonneutral trades and random day/block selection remain identical.
    """
    result=[]
    for day in days:
        compact=[];previous_neutral=False
        for trade in day:
            neutral=trade[0]==0 and trade[1]==0
            if not neutral or not previous_neutral:compact.append(trade)
            previous_neutral=neutral
        result.append(compact)
    return result


@cython.locals(equity=cython.double, high=cython.double, size=cython.double,
               opening=cython.double, floor=cython.double, daily_floor=cython.double,
               net=cython.double, adverse=cython.double, trough=cython.double,
               day=cython.longlong, duration=cython.longlong, attempt=cython.longlong)
def evaluation(days, micros, sims, seed, block=5, deadline=21, chain=False,
               max_micros=40):
    rng = np.random.RandomState(seed)
    outcomes, durations, attempts = [], [], []
    for _ in range(sims):
        duration = 0
        sequence = sampled_days(rng, len(days), block)
        for attempt in range(1, 10001 if chain else 2):
            equity = high = 0.
            result = 'timeout'
            size = min(micros, 60, max_micros)
            for day in range(1, deadline + 1):
                opening = equity
                floor = min(high - 2000., 3000.)
                daily_floor = opening - 1000.
                for trade in days[next(sequence)]:
                    net, adverse = trade[0], trade[1]
                    trough = equity - adverse * size / 10.
                    if len(trade) > 2 and trough <= max(daily_floor, floor):
                        hit, balance = risk_hit(trade[2], equity, size, daily_floor, floor)
                        if hit:
                            equity = balance
                            if hit == 2:result = 'blown'
                            break
                    if daily_floor > floor and trough <= daily_floor:
                        equity = daily_floor
                        break
                    if daily_floor <= floor and trough <= floor:
                        result = 'blown'
                        break
                    equity += net * size / 10.
                    if daily_floor > floor and equity <= daily_floor:
                        equity = daily_floor
                        break
                    if daily_floor <= floor and equity <= floor:
                        result = 'blown'
                        break
                    if equity >= 3000.:
                        result = 'passed'
                        break
                high = max(high, equity)
                if result != 'timeout':
                    break
            duration += day
            if not chain or result == 'passed':
                break
        if chain and result != 'passed':
            raise ValueError('No pass within the 10,000-attempt funding-time bound; acquisition time is unavailable.')
        outcomes.append(result)
        durations.append(duration + int(chain))
        attempts.append(attempt)
    return dict(outcomes=np.array(outcomes), days=np.array(durations), attempts=np.array(attempts))


def funded(days, micros, sims, seed, block=5, horizon=2000, rules=Rules(), max_micros=40):
    rng = np.random.RandomState(seed)
    accounts = []
    for _ in range(sims):
        account = FundedAccount(rules)
        for idx in sampled_days(rng, len(days), block):
            account.advance(days[idx], micros, max_micros)
            if account.outcome != 'open' or account.day == horizon:
                break
        accounts.append(account)
    return accounts
