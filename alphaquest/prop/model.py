"""Numerical extraction of pinned notebook cells; all mutable state is per instance.

Generated once by scripts/extract_prop_model.py. No Colab, plotting, file upload,
HTTP or presentation dependencies. Cell numbers refer to notebook array indices.
Known notebook behaviors are intentional; see docs/prop_simulation.md.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
_DEFAULT_MAX_DAYS = 21

@dataclass
class ApexChallenge:
    name: str
    account_size: float
    profit_target: float
    max_drawdown: float
    eod_trailing: bool
    daily_loss_limit: float = 0
    min_trading_days: int = 0
    max_trading_days: int = _DEFAULT_MAX_DAYS
    dd_lock_profit: float = 100.0

class NotebookModel:

    def bootstrap_ci(self, x, sims=10000, ci=0.95, seed=42):
        x = pd.Series(x).dropna().to_numpy()
        x = x[np.isfinite(x)]
        if len(x) == 0:
            return (np.array([]), np.nan, np.nan)
        rng = np.random.default_rng(seed)
        n = len(x)
        boot = np.empty(sims)
        batch = max(1, 1_000_000 // n)
        for start in range(0, sims, batch):
            stop = min(sims, start + batch)
            boot[start:stop] = rng.choice(x, size=(stop - start, n), replace=True).mean(axis=1)
        a = (1 - ci) / 2
        return (boot, np.quantile(boot, a), np.quantile(boot, 1 - a))

    def wilson_ci(self, successes, n, z=1.96):
        if n == 0:
            return (np.nan, np.nan)
        p = successes / n
        denom = 1 + z ** 2 / n
        center = (p + z ** 2 / (2 * n)) / denom
        margin = z / denom * np.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2))
        return (max(0, center - margin), min(1, center + margin))

    def verdict_tag(self, pr):
        """Single source of truth for the verdict scale (Cell 7 + Cell 10)."""
        return 'STRONG' if pr >= 0.6 else 'SOLID' if pr >= 0.45 else 'MODERATE' if pr >= 0.35 else 'RISKY' if pr >= 0.2 else 'POOR'

    def apply_day_degradation(self, day_pool, rng, degrade_wr=0.0, degrade_pnl=0.0):
        """Degrade the daily PnL distribution.
    pnl_shrink shrinks WINNING days only (reduces edge, keeps loss/drawdown risk).
    win_rate_adj flips some winning days to SAMPLED losing days. NOTE: this is a
    per-DAY approximation of a per-trade win-rate change (the sim is daily-resolution).
    """
        pool = day_pool.copy()
        if degrade_pnl > 0:
            win_mask = pool['net_pnl_usd'] > 0
            pool.loc[win_mask, 'net_pnl_usd'] *= 1.0 - degrade_pnl
        if degrade_wr < 0:
            win_idx = pool.index[pool['net_pnl_usd'] > 0].to_numpy()
            loss_vals = pool.loc[pool['net_pnl_usd'] < 0, 'net_pnl_usd'].to_numpy()
            n_base = int(pool['is_trade_day'].sum()) if 'is_trade_day' in pool.columns else len(pool)
            if len(win_idx) > 0:
                n_flip = min(int(round(abs(degrade_wr) * n_base)), len(win_idx))
                if n_flip > 0:
                    flip_idx = rng.choice(win_idx, size=n_flip, replace=False)
                    if len(loss_vals) > 0:
                        pool.loc[flip_idx, 'net_pnl_usd'] = rng.choice(loss_vals, size=n_flip, replace=True)
                    else:
                        pool.loc[flip_idx, 'net_pnl_usd'] = -abs(pool['net_pnl_usd'].mean())
        return pool

    def apply_trade_degradation(self, bag, degrade_wr=0.0, degrade_pnl=0.0, deg_seed=20240101):
        """Trade-level counterpart to apply_day_degradation, for the engines that
    run off TRADE_BAG.

    pnl_shrink shrinks WINNING trades only. win_rate_adj flips a share of
    winning trades into sampled losing trades; the flipped trade's MAE is
    resampled together with its P&L so the excursion path stays consistent
    with its new outcome. Unlike apply_day_degradation this is a true
    per-trade win-rate change, not a per-day approximation of one.

    Why this exists: CELL 11 and CELL 15 used to switch from TRADE_BAG to the
    day-level pool whenever degradation was requested, which silently swapped
    a DLL-aware trade-resolution engine for a day-resolution one with no DLL.
    Every measured degradation effect then had that engine change baked into
    it. With this helper the engine stays fixed and only the data degrades.

    Returns a bag in the same shape as the input; the input is never mutated.
    Cached because each sweep calls it once per size with identical arguments.
    """
        if degrade_wr == 0.0 and degrade_pnl == 0.0:
            return bag
        key = (id(bag), degrade_wr, degrade_pnl, deg_seed)
        if key in self._TRADE_DEG_CACHE:
            return self._TRADE_DEG_CACHE[key]
        rng = np.random.default_rng(deg_seed)
        wide = len(bag[0]) == 3
        lens = [len(d[-2]) for d in bag]
        if sum(lens) == 0:
            return bag
        pnl_old = np.concatenate([np.asarray(d[-2], dtype=float) for d in bag])
        mae_old = np.concatenate([np.asarray(d[-1], dtype=float) for d in bag])
        pnl_new, mae_new = (pnl_old.copy(), mae_old.copy())
        if degrade_pnl > 0:
            pnl_new[pnl_new > 0] *= 1.0 - degrade_pnl
        if degrade_wr < 0:
            win_idx = np.flatnonzero(pnl_new > 0)
            loss_idx = np.flatnonzero(pnl_old < 0)
            n_flip = min(int(round(abs(degrade_wr) * len(pnl_old))), len(win_idx))
            if n_flip > 0 and len(loss_idx) > 0:
                flip = rng.choice(win_idx, size=n_flip, replace=False)
                src = rng.choice(loss_idx, size=n_flip, replace=True)
                pnl_new[flip] = pnl_old[src]
                mae_new[flip] = mae_old[src]
        out, k = ([], 0)
        for d, n in zip(bag, lens):
            seg_p, seg_m = (pnl_new[k:k + n], mae_new[k:k + n])
            out.append((d[0], seg_p, seg_m) if wide else (seg_p, seg_m))
            k += n
        self._TRADE_DEG_CACHE[key] = out
        return out

    def simulate_apex(self, daily_pool, challenge, n_sims, n_contracts, rng, degrade_wr=0.0, degrade_pnl=0.0, deg_seed=20240101):
        deg_rng = np.random.default_rng(deg_seed)
        pool = self.apply_day_degradation(daily_pool, deg_rng, degrade_wr, degrade_pnl)
        pool['scaled_day_pnl'] = pool['net_pnl_usd'] * n_contracts
        vals = pool['scaled_day_pnl'].to_numpy()
        flags = pool['is_trade_day'].to_numpy() if 'is_trade_day' in pool.columns else vals != 0
        passed = fail_dd = fail_daily = fail_time = 0
        dll_hits = 0
        days_to_pass, trade_days_to_pass = ([], [])
        max_dds_all, final_equities, equity_at_pass = ([], [], [])
        for _ in range(n_sims):
            equity = eod_hwm = sim_max_dd = 0.0
            trade_days = 0
            outcome = None
            _maxd = self.draw_deadline(rng)
            _days = self.bootstrap_days(rng, len(vals), _maxd)
            for day in range(1, _maxd + 1):
                idx = _days[day - 1]
                day_pnl = vals[idx]
                equity += day_pnl
                if bool(flags[idx]):
                    trade_days += 1
                floor = eod_hwm - challenge.max_drawdown
                if floor > challenge.dd_lock_profit:
                    floor = challenge.dd_lock_profit
                current_dd = eod_hwm - equity
                sim_max_dd = max(sim_max_dd, current_dd)
                if equity <= floor:
                    outcome = 'fail_dd'
                    break
                if equity > eod_hwm:
                    eod_hwm = equity
                if equity >= challenge.profit_target and trade_days >= challenge.min_trading_days:
                    outcome = 'pass'
                    days_to_pass.append(day)
                    trade_days_to_pass.append(trade_days)
                    equity_at_pass.append(equity)
                    break
            if outcome is None:
                outcome = 'fail_time'
            if outcome == 'pass':
                passed += 1
            elif outcome == 'fail_dd':
                fail_dd += 1
            else:
                fail_time += 1
            max_dds_all.append(sim_max_dd)
            final_equities.append(equity)
        pr = passed / n_sims
        return {'challenge_name': challenge.name, 'n_sims': n_sims, 'passed': passed, 'fail_dd': fail_dd, 'fail_daily': fail_daily, 'fail_time': fail_time, 'dll_hits': dll_hits, 'dll_hit_rate': dll_hits / max(1, n_sims * self.DEADLINE_POOL.mean()), 'pass_rate': pr, 'pass_rate_ci': self.wilson_ci(passed, n_sims), 'avg_days_to_pass': np.mean(days_to_pass) if days_to_pass else None, 'median_days_to_pass': np.median(days_to_pass) if days_to_pass else None, 'avg_trade_days_to_pass': np.mean(trade_days_to_pass) if trade_days_to_pass else None, 'days_to_pass': np.array(days_to_pass), 'avg_max_dd': np.mean(max_dds_all), 'p50_max_dd': np.median(max_dds_all), 'p90_max_dd': np.percentile(max_dds_all, 90), 'p95_max_dd': np.percentile(max_dds_all, 95), 'worst_max_dd': np.max(max_dds_all), 'avg_final_equity': np.mean(final_equities), 'avg_equity_at_pass': np.mean(equity_at_pass) if equity_at_pass else None, 'max_dds_all': np.array(max_dds_all), 'final_equities': np.array(final_equities)}

    def simulate_paths(self, daily_pool, challenge, n_paths, n_contracts, rng):
        """
    Equity paths for the spaghetti chart. Uses the same DD logic (incl. lock).
    Failed paths STOP at their failure day (NaN after). Passed paths flatline.
    """
        pool = daily_pool.copy()
        pool['scaled_day_pnl'] = pool['net_pnl_usd'] * n_contracts
        vals = pool['scaled_day_pnl'].to_numpy()
        paths = np.full((n_paths, challenge.max_trading_days), np.nan)
        outcomes = []
        for i in range(n_paths):
            equity = eod_hwm = 0.0
            outcome = None
            _maxd = self.draw_deadline(rng)
            _days = self.bootstrap_days(rng, len(vals), _maxd)
            for d in range(_maxd):
                equity += vals[_days[d]]
                paths[i, d] = equity
                floor = eod_hwm - challenge.max_drawdown
                if floor > challenge.dd_lock_profit:
                    floor = challenge.dd_lock_profit
                if equity <= floor:
                    outcome = 'fail_dd'
                    break
                if equity > eod_hwm:
                    eod_hwm = equity
                if equity >= challenge.profit_target:
                    outcome = 'pass'
                    paths[i, d + 1:] = equity
                    break
            if outcome is None:
                outcome = 'fail_time'
            outcomes.append(outcome)
        return {'paths': paths, 'outcomes': np.array(outcomes)}

    def _apex_trade_engine(self, challenge, n_sims, n_contracts, rng, use_mae):
        passed = fail_dd = fail_time = 0
        dll_hits = 0
        days_to_pass, tdays_to_pass, max_dds = ([], [], [])
        for _ in range(n_sims):
            eq = hwm = mdd = 0.0
            td = 0
            out = None
            _maxd = self.draw_deadline(rng)
            _days = self.bootstrap_days(rng, len(self.TRADE_BAG), _maxd)
            for day in range(1, _maxd + 1):
                pnl, mae = self.TRADE_BAG[_days[day - 1]]
                if len(pnl):
                    td += 1
                floor = hwm - challenge.max_drawdown
                if floor > challenge.dd_lock_profit:
                    floor = challenge.dd_lock_profit
                day_open_eq = eq
                dll_floor = day_open_eq - challenge.daily_loss_limit if challenge.daily_loss_limit > 0 else -np.inf
                dll_first = dll_floor > floor
                for j in range(len(pnl)):
                    if use_mae:
                        trough = eq - mae[j] * n_contracts
                        mdd = max(mdd, hwm - trough)
                        if dll_first:
                            if trough <= dll_floor:
                                eq = dll_floor
                                dll_hits += 1
                                break
                        elif trough <= floor:
                            out = 'dd'
                            break
                    eq += pnl[j] * n_contracts
                    mdd = max(mdd, hwm - eq)
                    if dll_first:
                        if eq <= dll_floor:
                            eq = dll_floor
                            dll_hits += 1
                            break
                    elif eq <= floor:
                        out = 'dd'
                        break
                    if eq >= challenge.profit_target and td >= challenge.min_trading_days:
                        out = 'pass'
                        days_to_pass.append(day)
                        tdays_to_pass.append(td)
                        break
                if out:
                    break
                if eq > hwm:
                    hwm = eq
            if out is None:
                out = 'time'
            passed += out == 'pass'
            fail_dd += out == 'dd'
            fail_time += out == 'time'
            max_dds.append(mdd)
        _dds = np.array(max_dds)
        return {'challenge_name': challenge.name, 'n_contracts': n_contracts, 'micros': int(round(n_contracts * self.MICRO_PER_MINI)), 'pass_rate': passed / n_sims, 'pass_rate_ci': self.wilson_ci(passed, n_sims), 'passed': passed, 'fail_dd': fail_dd, 'fail_daily': 0, 'dll_hits': dll_hits, 'dll_hit_rate': dll_hits / max(1, n_sims * self.DEADLINE_POOL.mean()), 'fail_time': fail_time, 'n_sims': n_sims, 'avg_days_to_pass': float(np.mean(days_to_pass)) if days_to_pass else None, 'median_days_to_pass': float(np.median(days_to_pass)) if days_to_pass else float('nan'), 'p90_days_to_pass': float(np.percentile(days_to_pass, 90)) if days_to_pass else float('nan'), 'avg_trade_days_to_pass': float(np.mean(tdays_to_pass)) if tdays_to_pass else None, 'days_to_pass': np.array(days_to_pass), 'max_dds': _dds, 'avg_max_dd': float(_dds.mean()), 'p50_max_dd': float(np.median(_dds)), 'p90_max_dd': float(np.percentile(_dds, 90)), 'p95_max_dd': float(np.percentile(_dds, 95)), 'worst_max_dd': float(_dds.max())}

    def simulate_apex_trade(self, daily_pool, challenge, n_sims, n_contracts, rng, **kw):
        return self._apex_trade_engine(challenge, n_sims, n_contracts, rng, use_mae=False)

    def simulate_apex_excursion(self, daily_pool, challenge, n_sims, n_contracts, rng, **kw):
        return self._apex_trade_engine(challenge, n_sims, n_contracts, rng, use_mae=True)

    def bootstrap_days(self, rng, n_bag, n_days):
        """Day indices for one simulated run, drawn from the history.

    BOOTSTRAP_BLOCK == 1 is the plain iid bootstrap. Above that it is a
    moving-block bootstrap: a random start, then consecutive days, wrapping at
    the end of the sample. Blocks keep runs of good and bad days together,
    which is what a trailing drawdown actually reacts to.
    """
        b = max(1, int(getattr(self, 'BOOTSTRAP_BLOCK', 1)))
        if b == 1:
            return rng.integers(n_bag, size=n_days)
        starts = rng.integers(n_bag, size=-(-n_days // b))
        return ((starts[:, None] + np.arange(b)) % n_bag).ravel()[:n_days]

    def set_sample(self, which):
        """Point TRADE_BAG and daily_pool at 'train', 'validation' or 'full'.

    Selection (size, and the mix in MultiStrats) runs on 'train'; the reported
    result runs on 'validation', which the selection never saw. With
    VALIDATION_SPLIT = 0 all three are the same data and the notebook says so.
    """
        if self.VALIDATION_SPLIT <= 0:
            self._SAMPLE_SLICE, self.SAMPLE_NAME = (slice(None), 'full sample (no holdout)')
        elif which == 'train':
            self._SAMPLE_SLICE, self.SAMPLE_NAME = (slice(0, self._SPLIT_I), 'train')
        elif which == 'validation':
            self._SAMPLE_SLICE, self.SAMPLE_NAME = (slice(self._SPLIT_I, None), 'validation (held out)')
        else:
            self._SAMPLE_SLICE, self.SAMPLE_NAME = (slice(None), 'full sample')
        self.TRADE_BAG = self.TRADE_BAG_FULL[self._SAMPLE_SLICE]
        _dp = getattr(self, 'DAILY_POOL_FULL', None)
        if _dp is not None:
            _at = dict(getattr(_dp, 'attrs', {}))
            self.daily_pool = _dp.iloc[self._SAMPLE_SLICE].copy()
            self.daily_pool.attrs.update(_at)
        return self.SAMPLE_NAME

    def draw_deadline(self, rng):
        """Trading days available to one simulated evaluation."""
        return int(self.DEADLINE_POOL[rng.integers(len(self.DEADLINE_POOL))])

    def simulate_staged(self, challenge, n_sims, nc_small, nc_big, buffer_usd, rng, mode='dynamic', use_mae=None):
        if use_mae is None:
            use_mae = self._USE_MAE
        passed = 0
        for _ in range(n_sims):
            eq = hwm = 0.0
            td = 0
            big = False
            out = None
            _maxd = self.draw_deadline(rng)
            _days = self.bootstrap_days(rng, len(self.TRADE_BAG), _maxd)
            for day in range(1, _maxd + 1):
                pnl, mae = self.TRADE_BAG[_days[day - 1]]
                if len(pnl):
                    td += 1
                floor = hwm - challenge.max_drawdown
                if floor > challenge.dd_lock_profit:
                    floor = challenge.dd_lock_profit
                for j in range(len(pnl)):
                    if mode == 'ratchet':
                        big = big or eq >= buffer_usd
                    else:
                        big = eq >= buffer_usd
                    sz = nc_big if big else nc_small
                    if use_mae:
                        if eq - mae[j] * sz <= floor:
                            out = 'dd'
                            break
                    eq += pnl[j] * sz
                    if eq <= floor:
                        out = 'dd'
                        break
                    if eq >= challenge.profit_target and td >= challenge.min_trading_days:
                        out = 'pass'
                        break
                if out:
                    break
                if eq > hwm:
                    hwm = eq
            passed += out == 'pass'
        return passed / n_sims

    def _paths_current_engine(self, n_paths, n_contracts, rng, use_mae):
        """EOD equity paths under the Cell 6b engine (trade or excursion).
    Includes the same trade-resolution Daily Loss Limit model as CELL 6b
    (see its comments for the full rationale), so this chart's paths are
    consistent with the pass-rate table above -- CELL 6b's engine drives
    both, using the same TRADE_BAG path/MAE data."""
        P = np.full((n_paths, self.CHALLENGE.max_trading_days), np.nan)
        outs = []
        for i in range(n_paths):
            eq = hwm = 0.0
            td = 0
            out = None
            _maxd = self.draw_deadline(rng)
            _days = self.bootstrap_days(rng, len(self.TRADE_BAG), _maxd)
            for day in range(1, _maxd + 1):
                pnl, mae = self.TRADE_BAG[_days[day - 1]]
                if len(pnl):
                    td += 1
                floor = hwm - self.CHALLENGE.max_drawdown
                if floor > self.CHALLENGE.dd_lock_profit:
                    floor = self.CHALLENGE.dd_lock_profit
                day_open_eq = eq
                dll_floor = day_open_eq - self.CHALLENGE.daily_loss_limit if self.CHALLENGE.daily_loss_limit > 0 else -np.inf
                dll_first = dll_floor > floor
                for j in range(len(pnl)):
                    if use_mae:
                        trough = eq - mae[j] * n_contracts
                        if dll_first:
                            if trough <= dll_floor:
                                eq = dll_floor
                                break
                        elif trough <= floor:
                            out = 'fail_dd'
                            break
                    eq += pnl[j] * n_contracts
                    if dll_first:
                        if eq <= dll_floor:
                            eq = dll_floor
                            break
                    elif eq <= floor:
                        out = 'fail_dd'
                        break
                    if eq >= self.CHALLENGE.profit_target and td >= self.CHALLENGE.min_trading_days:
                        out = 'pass'
                        break
                P[i, day - 1] = eq
                if out:
                    break
                if eq > hwm:
                    hwm = eq
            outs.append(out or 'fail_time')
        return (P, outs)

    def _p_within_n(self, p, n, rho):
        if rho <= 0:
            return 1 - (1 - p) ** n
        a = p * (1 - rho) / rho
        b = (1 - p) * (1 - rho) / rho
        f = 1.0
        for k in range(n):
            f *= (b + k) / (a + b + k)
        return 1 - f

    def simulate_funded(self, daily_pool, n_sims, n_contracts, rng, degrade_wr=0.0, degrade_pnl=0.0, dd_lock_profit=None, deg_seed=20240101, max_horizon=None, inactivity_on=None):
        if dd_lock_profit is None:
            dd_lock_profit = self.PAYOUT_DD_LOCK
        if max_horizon is None:
            max_horizon = self.PAYOUT_MAX_HORIZON
        if inactivity_on is None:
            inactivity_on = self.INACTIVITY_ON
        bag = self.apply_trade_degradation(self.TRADE_BAG, degrade_wr, degrade_pnl, deg_seed)
        qualified = blown = timeout = closed_inactive = 0
        payouts, max_dds, days_to_qual = ([], [], [])
        blocked_by = {'qual_days': 0, 'safety_net': 0, 'consistency': 0}
        _min_equity_ok = self.PAYOUT_MIN_BALANCE
        for _ in range(n_sims):
            equity = eod_hwm = sim_max_dd = 0.0
            best_day = 0.0
            qual_days = 0
            trade_days = 0
            act_q1 = act_q2 = 0
            outcome = None
            _days = self.bootstrap_days(rng, len(bag), max_horizon)
            for day in range(max_horizon):
                floor = eod_hwm - self.PAYOUT_MAX_DD
                if floor > dd_lock_profit:
                    floor = dd_lock_profit
                pnl, mae = bag[_days[day]]
                has_trades = len(pnl) > 0
                dll_floor = equity - self.CHALLENGE.daily_loss_limit if self.CHALLENGE.daily_loss_limit > 0 else -np.inf
                dll_first = dll_floor > floor
                day_start_equity = equity
                day_trough = equity
                day_blown = False
                for j in range(len(pnl)):
                    trough = equity - (mae[j] * n_contracts if self.USE_MAE else 0.0)
                    day_trough = min(day_trough, trough)
                    if dll_first:
                        if trough <= dll_floor:
                            equity = dll_floor
                            break
                    elif trough <= floor:
                        day_blown = True
                        break
                    equity += pnl[j] * n_contracts
                    day_trough = min(day_trough, equity)
                    if dll_first:
                        if equity <= dll_floor:
                            equity = dll_floor
                            break
                    elif equity <= floor:
                        day_blown = True
                        break
                day_pnl = equity - day_start_equity
                if has_trades:
                    trade_days += 1
                if day_pnl >= self.INACTIVITY_PROFIT_THR:
                    act_q2, act_q1 = (act_q1, day)
                elif inactivity_on and day - act_q2 >= self.INACTIVITY_WINDOW_TD:
                    outcome = 'closed_inactive'
                    break
                if day_pnl >= self.PAYOUT_DAY_THR:
                    qual_days += 1
                if day_pnl > best_day:
                    best_day = day_pnl
                sim_max_dd = max(sim_max_dd, eod_hwm - day_trough)
                if day_blown or equity <= floor:
                    outcome = 'blown'
                    break
                if equity > eod_hwm:
                    eod_hwm = equity
                days_ok = qual_days >= self.PAYOUT_QUAL_DAYS and trade_days >= self.PAYOUT_MIN_TRADED
                net_ok = equity >= _min_equity_ok
                consis_ok = best_day < self.CONSISTENCY_LIMIT * equity
                if days_ok and net_ok and consis_ok:
                    outcome = 'qualified'
                    days_to_qual.append(day + 1)
                    break
            max_dds.append(sim_max_dd)
            if outcome == 'blown':
                blown += 1
            elif outcome == 'closed_inactive':
                closed_inactive += 1
            elif outcome == 'qualified':
                qualified += 1
                payouts.append(min((equity - self.PAYOUT_SAFETY_NET) * self.PAYOUT_SPLIT, self.PAYOUT_CAP))
            else:
                timeout += 1
                if qual_days < self.PAYOUT_QUAL_DAYS or trade_days < self.PAYOUT_MIN_TRADED:
                    blocked_by['qual_days'] += 1
                elif equity < _min_equity_ok:
                    blocked_by['safety_net'] += 1
                else:
                    blocked_by['consistency'] += 1
        qr = qualified / n_sims
        avg_pay = float(np.mean(payouts)) if payouts else 0.0
        med_pay = float(np.median(payouts)) if payouts else 0.0
        return {'n_contracts': n_contracts, 'micros': int(round(n_contracts * self.MICRO_PER_MINI)), 'qualified': qualified, 'blown': blown, 'closed_inactive': closed_inactive, 'rule_fail': timeout, 'timeout': timeout, 'qualify_rate': qr, 'qualify_ci': self.wilson_ci(qualified, n_sims), 'blown_rate': blown / n_sims, 'closed_inactive_rate': closed_inactive / n_sims, 'rule_fail_rate': timeout / n_sims, 'timeout_rate': timeout / n_sims, 'blocked_by': blocked_by, 'median_days_to_qualify': float(np.median(days_to_qual)) if days_to_qual else np.nan, 'p90_days_to_qualify': float(np.percentile(days_to_qual, 90)) if days_to_qual else np.nan, 'avg_payout': avg_pay, 'median_payout': med_pay, 'expected_payout': qr * avg_pay, 'p10_payout': float(np.percentile(payouts, 10)) if payouts else 0.0, 'p90_payout': float(np.percentile(payouts, 90)) if payouts else 0.0, 'payouts': np.array(payouts), 'max_dds': np.array(max_dds), 'days_to_qualify': np.array(days_to_qual)}

    def simulate_funded_lifetime(self, daily_pool, n_sims, n_contracts, rng, ladder=None, degrade_wr=0.0, degrade_pnl=0.0, deg_seed=20240101, max_horizon=None, inactivity_on=None):
        if ladder is None:
            ladder = self.PAYOUT_LADDER
        if max_horizon is None:
            max_horizon = self.LIFETIME_HORIZON
        if inactivity_on is None:
            inactivity_on = self.INACTIVITY_ON
        bag = self.apply_trade_degradation(self.TRADE_BAG, degrade_wr, degrade_pnl, deg_seed)
        totals, n_payouts_all, days_alive_all = ([], [], [])
        outcome_ct = {'ladder_done': 0, 'blown': 0, 'closed_inactive': 0, 'horizon': 0}
        first_payout_days = []
        for _ in range(n_sims):
            equity = eod_hwm = 0.0
            locked = False
            act_q1 = act_q2 = 0
            cyc_start = 0.0
            best_day = 0.0
            qual_days = 0
            payout_i = 0
            total_paid = 0.0
            outcome = None
            day = 0
            _days = self.bootstrap_days(rng, len(bag), max_horizon)
            for day in range(1, max_horizon + 1):
                if locked:
                    floor = self.PAYOUT_DD_LOCK
                else:
                    floor = eod_hwm - self.PAYOUT_MAX_DD
                    if floor >= self.PAYOUT_DD_LOCK:
                        locked = True
                        floor = self.PAYOUT_DD_LOCK
                pnl, mae = bag[_days[day - 1]]
                has_trades = len(pnl) > 0
                dll_floor = equity - self.CHALLENGE.daily_loss_limit if self.CHALLENGE.daily_loss_limit > 0 else -np.inf
                dll_first = dll_floor > floor
                day_start_equity = equity
                day_blown = False
                for j in range(len(pnl)):
                    trough = equity - (mae[j] * n_contracts if self.USE_MAE else 0.0)
                    if dll_first:
                        if trough <= dll_floor:
                            equity = dll_floor
                            break
                    elif trough <= floor:
                        day_blown = True
                        break
                    equity += pnl[j] * n_contracts
                    if dll_first:
                        if equity <= dll_floor:
                            equity = dll_floor
                            break
                    elif equity <= floor:
                        day_blown = True
                        break
                day_pnl = equity - day_start_equity
                if day_pnl >= self.INACTIVITY_PROFIT_THR:
                    act_q2, act_q1 = (act_q1, day)
                elif inactivity_on and day - act_q2 >= self.INACTIVITY_WINDOW_TD:
                    outcome = 'closed_inactive'
                    break
                if day_pnl >= self.PAYOUT_DAY_THR:
                    qual_days += 1
                if day_pnl > best_day:
                    best_day = day_pnl
                if day_blown or equity <= floor:
                    outcome = 'blown'
                    break
                if equity > eod_hwm:
                    eod_hwm = equity
                cap = ladder[payout_i]
                withdrawable = equity - self.PAYOUT_SAFETY_NET
                profit_cycle = equity - cyc_start
                days_ok = qual_days >= self.PAYOUT_QUAL_DAYS
                net_ok = withdrawable >= self.PAYOUT_MIN_WITHDRAWAL
                consis_ok = profit_cycle > 0 and best_day < self.CONSISTENCY_LIMIT * profit_cycle
                if days_ok and net_ok and consis_ok:
                    amt = min(withdrawable, cap) * self.PAYOUT_SPLIT
                    total_paid += amt
                    payout_i += 1
                    if payout_i == 1:
                        first_payout_days.append(day)
                    equity -= amt
                    eod_hwm = max(eod_hwm, equity)
                    cyc_start = equity
                    best_day = 0.0
                    qual_days = 0
                    if payout_i >= len(ladder):
                        outcome = 'ladder_done'
                        break
            if outcome is None:
                outcome = 'horizon'
            outcome_ct[outcome] += 1
            totals.append(total_paid)
            n_payouts_all.append(payout_i)
            days_alive_all.append(day)
        self.last_lifetime_days = np.asarray(days_alive_all)
        self.last_first_payout_days = np.asarray(first_payout_days)
        totals = np.array(totals)
        n_payouts_all = np.array(n_payouts_all)
        return {'n_contracts': n_contracts, 'micros': int(round(n_contracts * self.MICRO_PER_MINI)), 'n_sims': n_sims, 'expected_total': float(totals.mean()), 'median_total': float(np.median(totals)), 'p10_total': float(np.percentile(totals, 10)), 'p90_total': float(np.percentile(totals, 90)), 'p_zero': float((totals == 0).mean()), 'p_ladder_done': outcome_ct['ladder_done'] / n_sims, 'blown_rate': outcome_ct['blown'] / n_sims, 'closed_inactive_rate': outcome_ct['closed_inactive'] / n_sims, 'horizon_rate': outcome_ct['horizon'] / n_sims, 'avg_n_payouts': float(n_payouts_all.mean()), 'p_at_least_1': float((n_payouts_all >= 1).mean()), 'median_days_first_payout': float(np.median(first_payout_days)) if first_payout_days else np.nan, 'avg_days_alive': float(np.mean(days_alive_all)), 'totals': totals, 'n_payouts': n_payouts_all, 'outcome_ct': outcome_ct}

    def cell_2(self):
        self.INSTRUMENT = 'NQ'
        self.INSTRUMENT = self.overrides.get('INSTRUMENT', self.INSTRUMENT)
        self.MINI_LABEL = 'MINI'
        self.MINI_LABEL = self.overrides.get('MINI_LABEL', self.MINI_LABEL)
        self.MICRO_LABEL = 'MICRO'
        self.MICRO_LABEL = self.overrides.get('MICRO_LABEL', self.MICRO_LABEL)
        self.MICRO_PER_MINI = 10
        self.MICRO_PER_MINI = self.overrides.get('MICRO_PER_MINI', self.MICRO_PER_MINI)
        self.ALLOW_VARIABLE_CONTRACTS = False
        self.ALLOW_VARIABLE_CONTRACTS = self.overrides.get('ALLOW_VARIABLE_CONTRACTS', self.ALLOW_VARIABLE_CONTRACTS)
        self.BOOTSTRAP_BLOCK = 1
        self.BOOTSTRAP_BLOCK = self.overrides.get('BOOTSTRAP_BLOCK', self.BOOTSTRAP_BLOCK)
        self.VALIDATION_SPLIT = 0.3
        self.VALIDATION_SPLIT = self.overrides.get('VALIDATION_SPLIT', self.VALIDATION_SPLIT)
        self.NUM_CONTRACTS = 1
        self.NUM_CONTRACTS = self.overrides.get('NUM_CONTRACTS', self.NUM_CONTRACTS)
        self.RISK_PER_CONTRACT = 1500.0
        self.RISK_PER_CONTRACT = self.overrides.get('RISK_PER_CONTRACT', self.RISK_PER_CONTRACT)
        self.COMMISSION_PER_CONTRACT = 2.25
        self.COMMISSION_PER_CONTRACT = self.overrides.get('COMMISSION_PER_CONTRACT', self.COMMISSION_PER_CONTRACT)
        self.SLIPPAGE_PER_CONTRACT = 5.0
        self.SLIPPAGE_PER_CONTRACT = self.overrides.get('SLIPPAGE_PER_CONTRACT', self.SLIPPAGE_PER_CONTRACT)
        self.PROP_MC_SIMS = 20000
        self.PROP_MC_SIMS = self.overrides.get('PROP_MC_SIMS', self.PROP_MC_SIMS)
        self.SWEEP_SIMS = 5000
        self.SWEEP_SIMS = self.overrides.get('SWEEP_SIMS', self.SWEEP_SIMS)
        self.EVAL_WINDOW = 'calendar'
        self.EVAL_WINDOW = self.overrides.get('EVAL_WINDOW', self.EVAL_WINDOW)
        self.EVAL_WINDOW_CALENDAR_DAYS = 30
        self.EVAL_WINDOW_CALENDAR_DAYS = self.overrides.get('EVAL_WINDOW_CALENDAR_DAYS', self.EVAL_WINDOW_CALENDAR_DAYS)
        self.MAX_TRADING_DAYS = 21
        self.MAX_TRADING_DAYS = self.overrides.get('MAX_TRADING_DAYS', self.MAX_TRADING_DAYS)
        self.OOS_START_DATE = '2023-01-01'
        self.OOS_START_DATE = self.overrides.get('OOS_START_DATE', self.OOS_START_DATE)
        self.SWEEP_CONTRACTS = [0.3, 0.5, 0.7, 1.0, 1.1, 1.3, 1.5, 1.7, 2.0]
        self.SWEEP_CONTRACTS = self.overrides.get('SWEEP_CONTRACTS', self.SWEEP_CONTRACTS)
        self.SEED = 42
        self.SEED = self.overrides.get('SEED', self.SEED)

    def cell_4(self):
        if self.OOS_START_DATE is not None:
            self._cut = pd.to_datetime(self.OOS_START_DATE)
            self.df_sim = self.df[self.df['datetime'] >= self._cut].copy()
            if len(self.df_sim) == 0:
                raise RuntimeError('❌ No trades on or after OOS_START_DATE. Check the date against the range printed in CELL 3.')
            if len(self.df_sim) < 100:
                pass
            self._label = f'OOS TRADE STATISTICS (from {self._cut.date()})'
        else:
            self.df_sim = self.df.copy()
            self._label = 'TRADE STATISTICS (full sample)'
        self.df_sim['costs_usd'] = self.df_sim['contracts'] * (self.COMMISSION_PER_CONTRACT + self.SLIPPAGE_PER_CONTRACT)
        self.df_sim['profit_net_usd'] = self.df_sim['profit_usd'] - self.df_sim['costs_usd']
        self.df_sim['initial_risk_usd'] = self.df_sim['contracts'] * float(self.RISK_PER_CONTRACT)
        self.df_sim['r_mult'] = self.df_sim['profit_net_usd'] / self.df_sim['initial_risk_usd']
        self.winners = self.df_sim[self.df_sim['profit_net_usd'] > 0]['profit_net_usd']
        self.losers = self.df_sim[self.df_sim['profit_net_usd'] < 0]['profit_net_usd']
        self.b_usd, self.lo, self.hi = self.bootstrap_ci(self.df_sim['profit_net_usd'])
        self.b_r, self.rlo, self.rhi = self.bootstrap_ci(self.df_sim['r_mult'])

    def cell_6(self):
        self.daily_actual = self.df_sim.groupby('date', as_index=False).agg(n_trades=('profit_net_usd', 'count'), gross_pnl_usd=('profit_usd', 'sum'), net_pnl_usd=('profit_net_usd', 'sum'), net_r=('r_mult', 'sum')).sort_values('date').reset_index(drop=True)
        self.all_weekdays = pd.date_range(start=self.df_sim['date'].min(), end=self.df_sim['date'].max(), freq='B')
        self.daily_full = pd.DataFrame({'date': self.all_weekdays}).merge(self.daily_actual, on='date', how='left')
        for self.col in ['n_trades']:
            self.daily_full[self.col] = self.daily_full[self.col].fillna(0).astype(int)
        for self.col in ['gross_pnl_usd', 'net_pnl_usd', 'net_r']:
            self.daily_full[self.col] = self.daily_full[self.col].fillna(0.0)
        self.daily_full['is_trade_day'] = self.daily_full['n_trades'] > 0
        self._recon = int(self.daily_full['n_trades'].sum())
        assert self._recon == len(self.df_sim), f'Trade reconciliation failed: {self._recon} in daily_full vs {len(self.df_sim)} trades'

    def cell_8(self):
        self.CHALLENGE = ApexChallenge(name='Apex 50K EOD', account_size=50000, profit_target=3000, max_drawdown=2000, eod_trailing=True, daily_loss_limit=1000.0, max_trading_days=self.MAX_TRADING_DAYS, dd_lock_profit=3000.0)
        try:
            self.NUM_CONTRACTS
        except NameError:
            raise RuntimeError('❌ NUM_CONTRACTS not defined — run CELL 2 first.')
        self._micros = self.NUM_CONTRACTS * self.MICRO_PER_MINI
        self._TRADE_DEG_CACHE = {}
        self._TRADE_DEG_CACHE = self.overrides.get('_TRADE_DEG_CACHE', self._TRADE_DEG_CACHE)

    def cell_9(self):
        self.ENGINE = 'excursion'
        self.ENGINE = self.overrides.get('ENGINE', self.ENGINE)
        self._bag_src = self.df_sim.sort_values('datetime')
        self._bag_days = pd.date_range(self._bag_src['date'].min(), self._bag_src['date'].max(), freq='B')
        self._mae_col = 'mae_usd' if 'mae_usd' in self._bag_src.columns else None
        self.TRADE_BAG = []
        self.TRADE_BAG = self.overrides.get('TRADE_BAG', self.TRADE_BAG)
        for self._d in self._bag_days:
            self._t = self._bag_src[self._bag_src['date'] == self._d]
            self._pnl = self._t['profit_net_usd'].to_numpy()
            self._mae = self._t[self._mae_col].to_numpy() if self._mae_col is not None else np.clip(-self._pnl, 0, None)
            self.TRADE_BAG.append((self._pnl, self._mae))
        if self.ENGINE == 'excursion' and (self._mae_col is None or not getattr(self, 'HAS_EXCURSIONS', False)):
            self.ENGINE = 'trade'
        if self.simulate_apex.__name__ == 'simulate_apex':
            self.simulate_apex_daily = self.simulate_apex
        self.simulate_apex = {'daily': self.simulate_apex_daily, 'trade': self.simulate_apex_trade, 'excursion': self.simulate_apex_excursion}[self.ENGINE]
        self.USE_MAE = self.ENGINE == 'excursion'
        self.TRADE_BAG_FULL = self.TRADE_BAG
        self._SPLIT_I = int(round(len(self.TRADE_BAG_FULL) * (1.0 - float(self.VALIDATION_SPLIT))))
        self._SPLIT_I = self.overrides.get('_SPLIT_I', self._SPLIT_I)
        self._SAMPLE_SLICE = slice(None)
        self._SAMPLE_SLICE = self.overrides.get('_SAMPLE_SLICE', self._SAMPLE_SLICE)
        self.SAMPLE_NAME = 'full sample'
        self.SAMPLE_NAME = self.overrides.get('SAMPLE_NAME', self.SAMPLE_NAME)
        if self.VALIDATION_SPLIT > 0:
            self._d0 = self._bag_days[0].date()
            self._d1 = self._bag_days[self._SPLIT_I - 1].date()
            self._d2 = self._bag_days[self._SPLIT_I].date()
            self._d3 = self._bag_days[-1].date()
        self._cal_all = pd.date_range(self._bag_days[0], self._bag_days[-1], freq='D')
        self._bag_ix = pd.DatetimeIndex(self._bag_days)
        self._start = self._bag_ix.searchsorted(self._cal_all, side='left')
        self._stop = self._bag_ix.searchsorted(self._cal_all + pd.Timedelta(days=self.EVAL_WINDOW_CALENDAR_DAYS - 1), side='right')
        self._fits = self._cal_all + pd.Timedelta(days=self.EVAL_WINDOW_CALENDAR_DAYS - 1) <= self._bag_days[-1]
        self.DEADLINE_POOL = (self._stop - self._start)[self._fits]
        self.DEADLINE_POOL = self.DEADLINE_POOL[self.DEADLINE_POOL > 0]
        if self.EVAL_WINDOW != 'calendar' or len(self.DEADLINE_POOL) == 0:
            self.DEADLINE_POOL = np.array([self.MAX_TRADING_DAYS])
        self.DEADLINE_MAX = int(self.DEADLINE_POOL.max())
        self.CHALLENGE.max_trading_days = self.DEADLINE_MAX
        if self.EVAL_WINDOW == 'calendar':
            self._u, self._c = np.unique(self.DEADLINE_POOL, return_counts=True)
        self._COV = getattr(self, 'EXCURSION_COVERAGE', None)
        self._COV = self.overrides.get('_COV', self._COV)
        if self.USE_MAE and self._COV is not None and (self._COV < 1.0):
            self._s_a = self._apex_trade_engine(self.CHALLENGE, 2000, self.NUM_CONTRACTS, np.random.default_rng(self.SEED + 9100), True)['pass_rate']
            self._s_b = self._apex_trade_engine(self.CHALLENGE, 2000, self.NUM_CONTRACTS, np.random.default_rng(self.SEED + 9100), False)['pass_rate']
        if self.ENGINE == 'excursion':
            self._all_mae = np.concatenate([m for p, m in self.TRADE_BAG if len(m)])
            self._p95_mae = float(np.percentile(self._all_mae, 95))
            if self._p95_mae > 0:
                pass

    def cell_10(self):
        self.daily_pool = self.daily_full[['date', 'n_trades', 'net_pnl_usd', 'is_trade_day']].copy()
        self.DAILY_POOL_FULL = self.daily_pool
        self.set_sample('full')
        self.res = self.simulate_apex(daily_pool=self.daily_pool, challenge=self.CHALLENGE, n_sims=self.PROP_MC_SIMS, n_contracts=self.NUM_CONTRACTS, rng=np.random.default_rng(self.SEED))

    def cell_11(self):
        self._sample_tag = f'OOS from {pd.to_datetime(self.OOS_START_DATE).date()}' if self.OOS_START_DATE else 'FULL sample'
        self.set_sample('train')
        self.sweep_data = []
        for self.nc in self.SWEEP_CONTRACTS:
            getattr(self, 'progress', lambda _: None)(f'Evaluation size {self.nc:g}')
            self.rs = self.simulate_apex(daily_pool=self.daily_pool, challenge=self.CHALLENGE, n_sims=self.PROP_MC_SIMS, n_contracts=self.nc, rng=np.random.default_rng(self.SEED + 2000))
            self.ci = self.rs['pass_rate_ci']
            self.ad = self.rs['avg_days_to_pass'] if self.rs['avg_days_to_pass'] is not None else np.nan
            self.micros = int(round(self.nc * self.MICRO_PER_MINI))
            self.sweep_data.append({'nc': self.nc, 'micros': self.micros, 'pr': self.rs['pass_rate'], 'ci': self.ci, 'dd': self.rs['avg_max_dd'], 'p95dd': self.rs['p95_max_dd'], 'days': self.ad})
        self._sorted = sorted(self.sweep_data, key=lambda s: s['pr'], reverse=True)
        self._best = self._sorted[0]
        self._tied = [s for s in self._sorted[1:] if s['ci'][1] >= self._best['ci'][0]]
        if self._tied:
            self._rng_lo = min([self._best] + self._tied, key=lambda s: s['micros'])['micros']
            self._rng_hi = max([self._best] + self._tied, key=lambda s: s['micros'])['micros']
        self.set_sample('validation')
        self._val = self.simulate_apex(daily_pool=self.daily_pool, challenge=self.CHALLENGE, n_sims=self.PROP_MC_SIMS, n_contracts=self._best['nc'], rng=np.random.default_rng(self.SEED + 2600))
        self._gap = self._best['pr'] - self._val['pass_rate']
        if self.VALIDATION_SPLIT <= 0:
            pass
        elif self._gap > 0.1:
            pass
        elif self._gap > 0.05:
            pass

    def cell_12(self):
        self.BUFFER_LEVEL = 1000.0
        self.BUFFER_LEVEL = self.overrides.get('BUFFER_LEVEL', self.BUFFER_LEVEL)
        self.STAGE1_FRACS = [0.25, 0.5, 0.75]
        self.STAGE1_FRACS = self.overrides.get('STAGE1_FRACS', self.STAGE1_FRACS)
        self.STAGED_MODE = 'dynamic'
        self.STAGED_MODE = self.overrides.get('STAGED_MODE', self.STAGED_MODE)
        self.STAGED_SIMS = self.PROP_MC_SIMS
        self.STAGED_SIMS = self.overrides.get('STAGED_SIMS', self.STAGED_SIMS)
        self._USE_MAE = self.ENGINE == 'excursion'
        self._USE_MAE = self.overrides.get('_USE_MAE', self._USE_MAE)
        self._opt_nc = self._best['nc']
        self._p_flat = self.simulate_staged(self.CHALLENGE, self.STAGED_SIMS, self._opt_nc, self._opt_nc, self.BUFFER_LEVEL, np.random.default_rng(self.SEED + 15000), self.STAGED_MODE)
        self._lo_f, self._hi_f = self.wilson_ci(int(round(self._p_flat * self.STAGED_SIMS)), self.STAGED_SIMS)
        self._rows = []
        for self.fr in self.STAGE1_FRACS:
            self.nc1 = round(self.fr * self._opt_nc, 2)
            self.p = self.simulate_staged(self.CHALLENGE, self.STAGED_SIMS, self.nc1, self._opt_nc, self.BUFFER_LEVEL, np.random.default_rng(self.SEED + 15000), self.STAGED_MODE)
            self.lo, self.hi = self.wilson_ci(int(round(self.p * self.STAGED_SIMS)), self.STAGED_SIMS)
            self._rows.append((self.nc1, self.p, self.lo, self.hi))
        self._best_staged = max(self._rows, key=lambda r: r[1])
        if self._best_staged[2] > self._hi_f:
            pass
        elif self._best_staged[3] < self._lo_f:
            pass

    def cell_13(self):
        self.ACCENT_GREEN = '#16a34a'
        self.ACCENT_GREEN = self.overrides.get('ACCENT_GREEN', self.ACCENT_GREEN)
        self.ACCENT_RED = '#dc2626'
        self.ACCENT_RED = self.overrides.get('ACCENT_RED', self.ACCENT_RED)
        self.ACCENT_ORANGE = '#d97706'
        self.ACCENT_ORANGE = self.overrides.get('ACCENT_ORANGE', self.ACCENT_ORANGE)
        self.ACCENT_BLUE = '#2563eb'
        self.ACCENT_BLUE = self.overrides.get('ACCENT_BLUE', self.ACCENT_BLUE)
        self.ACCENT_GRAY = '#9ca3af'
        self.ACCENT_GRAY = self.overrides.get('ACCENT_GRAY', self.ACCENT_GRAY)
        self.ACCENT_PURPLE = '#7c3aed'
        self.ACCENT_PURPLE = self.overrides.get('ACCENT_PURPLE', self.ACCENT_PURPLE)
        self.TEXT_COLOR = '#222222'
        self.TEXT_COLOR = self.overrides.get('TEXT_COLOR', self.TEXT_COLOR)
        self.N_SPAGHETTI = 300
        self.N_SPAGHETTI = self.overrides.get('N_SPAGHETTI', self.N_SPAGHETTI)
        if self.ENGINE in ('trade', 'excursion'):
            self.paths, self.outcomes = self._paths_current_engine(self.N_SPAGHETTI, self.NUM_CONTRACTS, np.random.default_rng(self.SEED + 5000), use_mae=self.ENGINE == 'excursion')
        else:
            self._pr = self.simulate_paths(daily_pool=self.daily_pool, challenge=self.CHALLENGE, n_paths=self.N_SPAGHETTI, n_contracts=self.NUM_CONTRACTS, rng=np.random.default_rng(self.SEED + 5000))
            self.paths, self.outcomes = (self._pr['paths'], self._pr['outcomes'])

    def cell_15(self):
        self.RHO_GRID = [0.0, 0.15, 0.3, 0.5]
        self.RHO_GRID = self.overrides.get('RHO_GRID', self.RHO_GRID)
        self.N_MAX_ATT = 6
        self.N_MAX_ATT = self.overrides.get('N_MAX_ATT', self.N_MAX_ATT)
        self.ATTEMPT_FEE = 100.0
        self.ATTEMPT_FEE = self.overrides.get('ATTEMPT_FEE', self.ATTEMPT_FEE)
        self._p_att = self._val['pass_rate'] if '_val' in vars(self) else self.res['pass_rate']
        self._fee_att = self.ATTEMPT_FEE
        self._hdr = ''.join((f'{'ρ=' + format(r, 'g'):>10}' for r in self.RHO_GRID))
        for self.n in range(1, self.N_MAX_ATT + 1):
            self.row = ''.join((f'{self._p_within_n(self._p_att, self.n, r):>10.1%}' for r in self.RHO_GRID))

    def cell_17(self):
        self.RULE_SET = 'apex40'
        self.RULE_SET = self.overrides.get('RULE_SET', self.RULE_SET)
        if self.RULE_SET == 'apex40':
            self.PAYOUT_QUAL_DAYS = 5
            self.PAYOUT_DAY_THR = 250.0
            self.PAYOUT_MIN_TRADED = 0
            self.CONSISTENCY_LIMIT = 0.5
            self.PAYOUT_CAP = 1500.0
        else:
            self.PAYOUT_QUAL_DAYS = 5
            self.PAYOUT_DAY_THR = 50.0
            self.PAYOUT_MIN_TRADED = 8
            self.CONSISTENCY_LIMIT = 0.3
            self.PAYOUT_CAP = 1500.0
        self.PAYOUT_MIN_BALANCE = 2600.0
        self.PAYOUT_MIN_BALANCE = self.overrides.get('PAYOUT_MIN_BALANCE', self.PAYOUT_MIN_BALANCE)
        self.PAYOUT_MIN_WITHDRAWAL = 500.0
        self.PAYOUT_MIN_WITHDRAWAL = self.overrides.get('PAYOUT_MIN_WITHDRAWAL', self.PAYOUT_MIN_WITHDRAWAL)
        self.PAYOUT_SAFETY_NET = self.PAYOUT_MIN_BALANCE - self.PAYOUT_MIN_WITHDRAWAL
        self.PAYOUT_SAFETY_NET = self.overrides.get('PAYOUT_SAFETY_NET', self.PAYOUT_SAFETY_NET)
        self.PAYOUT_MAX_DD = self.CHALLENGE.max_drawdown
        self.PAYOUT_MAX_DD = self.overrides.get('PAYOUT_MAX_DD', self.PAYOUT_MAX_DD)
        self.PAYOUT_DD_LOCK = 100.0
        self.PAYOUT_DD_LOCK = self.overrides.get('PAYOUT_DD_LOCK', self.PAYOUT_DD_LOCK)
        self.PAYOUT_SPLIT = 1.0
        self.PAYOUT_SPLIT = self.overrides.get('PAYOUT_SPLIT', self.PAYOUT_SPLIT)
        self.INACTIVITY_WINDOW_TD = 22
        self.INACTIVITY_WINDOW_TD = self.overrides.get('INACTIVITY_WINDOW_TD', self.INACTIVITY_WINDOW_TD)
        self.INACTIVITY_MIN_QUAL = 2
        self.INACTIVITY_MIN_QUAL = self.overrides.get('INACTIVITY_MIN_QUAL', self.INACTIVITY_MIN_QUAL)
        self.INACTIVITY_PROFIT_THR = 50.0
        self.INACTIVITY_PROFIT_THR = self.overrides.get('INACTIVITY_PROFIT_THR', self.INACTIVITY_PROFIT_THR)
        self.INACTIVITY_ON = True
        self.INACTIVITY_ON = self.overrides.get('INACTIVITY_ON', self.INACTIVITY_ON)
        self.PAYOUT_MAX_HORIZON = 250
        self.PAYOUT_MAX_HORIZON = self.overrides.get('PAYOUT_MAX_HORIZON', self.PAYOUT_MAX_HORIZON)
        self.PAYOUT_SIMS = 20000
        self.PAYOUT_SIMS = self.overrides.get('PAYOUT_SIMS', self.PAYOUT_SIMS)
        self.PAYOUT_SWEEP_SIMS = 5000
        self.PAYOUT_SWEEP_SIMS = self.overrides.get('PAYOUT_SWEEP_SIMS', self.PAYOUT_SWEEP_SIMS)
        self.PAYOUT_CONTRACTS = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 2.0]
        self.PAYOUT_CONTRACTS = self.overrides.get('PAYOUT_CONTRACTS', self.PAYOUT_CONTRACTS)

    def cell_18(self):
        self.BLOWN_COST = 150.0
        self.BLOWN_COST = self.overrides.get('BLOWN_COST', self.BLOWN_COST)
        self.MAX_BLOWN_RATE = 0.5
        self.MAX_BLOWN_RATE = self.overrides.get('MAX_BLOWN_RATE', self.MAX_BLOWN_RATE)
        self.payout_sweep = []
        for self.nc in self.PAYOUT_CONTRACTS:
            getattr(self, 'progress', lambda _: None)(f'Funded/lifetime size {self.nc:g}')
            self.r = self.simulate_funded(daily_pool=self.daily_pool, n_sims=self.PAYOUT_SWEEP_SIMS, n_contracts=self.nc, rng=np.random.default_rng(self.SEED + 8000))
            self._closure_rate = self.r['blown_rate'] + self.r['closed_inactive_rate']
            self.r['net_ev'] = self.r['expected_payout'] - self._closure_rate * self.BLOWN_COST
            self.payout_sweep.append(self.r)
        self.candidates = [r for r in self.payout_sweep if r['blown_rate'] <= self.MAX_BLOWN_RATE] or self.payout_sweep
        self.best = max(self.candidates, key=lambda x: x['net_ev'])

    def cell_19(self):
        self.best_nc = self.best['n_contracts']
        self.best_micros = self.best['micros']
        self.detail = self.simulate_funded(daily_pool=self.daily_pool, n_sims=self.PAYOUT_SIMS, n_contracts=self.best_nc, rng=np.random.default_rng(self.SEED + 9000))
        self.ci = self.detail['qualify_ci']
        self._sample_tag = f'OOS from {pd.to_datetime(self.OOS_START_DATE).date()}' if self.OOS_START_DATE else 'FULL sample'

    def cell_21(self):
        self.PAYOUT_LADDER = [1500.0, 1500.0, 2000.0, 2500.0, 2500.0, 3000.0]
        self.PAYOUT_LADDER = self.overrides.get('PAYOUT_LADDER', self.PAYOUT_LADDER)
        self.LIFETIME_HORIZON = 2000
        self.LIFETIME_HORIZON = self.overrides.get('LIFETIME_HORIZON', self.LIFETIME_HORIZON)
        self.LIFETIME_SIMS = 10000
        self.LIFETIME_SIMS = self.overrides.get('LIFETIME_SIMS', self.LIFETIME_SIMS)
        self.LIFETIME_SWEEP_SIMS = 4000
        self.LIFETIME_SWEEP_SIMS = self.overrides.get('LIFETIME_SWEEP_SIMS', self.LIFETIME_SWEEP_SIMS)
        self.lifetime_sweep = []
        self.lifetime_observations = []
        for self.nc in self.PAYOUT_CONTRACTS:
            getattr(self, 'progress', lambda _: None)(f'Funded/lifetime size {self.nc:g}')
            self.r = self.simulate_funded_lifetime(daily_pool=self.daily_pool, n_sims=self.LIFETIME_SWEEP_SIMS, n_contracts=self.nc, rng=np.random.default_rng(self.SEED + 12000))
            self.lifetime_sweep.append(self.r)
            self.lifetime_observations.append(dict(n_contracts=self.nc,days_alive=self.last_lifetime_days,first_payout_days=self.last_first_payout_days))
        self.LIFETIME_MAX_BLOWN = self.MAX_BLOWN_RATE
        self.LIFETIME_MAX_BLOWN = self.overrides.get('LIFETIME_MAX_BLOWN', self.LIFETIME_MAX_BLOWN)
        self._life_ok = [d for d in self.lifetime_sweep if d['blown_rate'] <= self.LIFETIME_MAX_BLOWN]
        if self._life_ok:
            self.best_life = max(self._life_ok, key=lambda x: x['expected_total'])
        else:
            self.best_life = min(self.lifetime_sweep, key=lambda x: x['blown_rate'])

    def cell_22(self):
        self.robustness = []
        self.EVAL_FEE = 100.0
        self.EVAL_FEE = self.overrides.get('EVAL_FEE', self.EVAL_FEE)
        self.PA_ACTIVATION = 140.0
        self.PA_ACTIVATION = self.overrides.get('PA_ACTIVATION', self.PA_ACTIVATION)
        self._eval_pass = self.res['pass_rate']
        self._acq_cost = 1.0 / self._eval_pass * self.EVAL_FEE + self.PA_ACTIVATION if self._eval_pass > 0 else float('inf')
        self._eval_best = max(self.sweep_data, key=lambda s: s['pr'])
        self._first_best = self.best
        self._life_best = self.best_life
        for self.d in sorted(self.lifetime_sweep, key=lambda x: x['expected_total'], reverse=True)[:5]:
            self.tag = ' ◀ BEST' if self.d['micros'] == self._life_best['micros'] else ''
        self._net = self._life_best['expected_total'] - self._acq_cost
        self._mult = self._life_best['expected_total'] / self._acq_cost if self._acq_cost > 0 else float('inf')
        if self._net <= 0:
            pass
        elif self._mult < 2 or self._life_best['p_zero'] > 0.7:
            pass
        elif self._mult < 4:
            pass
        self._blk0 = self.BOOTSTRAP_BLOCK
        try:
            for self._b in (1, 5, 10):
                getattr(self, 'progress', lambda _: None)(f'Robustness block {self._b}')
                self.BOOTSTRAP_BLOCK = self._b
                self._e = self.simulate_apex(daily_pool=self.daily_pool, challenge=self.CHALLENGE, n_sims=self.PROP_MC_SIMS, n_contracts=self.NUM_CONTRACTS, rng=np.random.default_rng(self.SEED + 7700))
                self._f = self.simulate_funded(daily_pool=self.daily_pool, n_sims=self.PAYOUT_SWEEP_SIMS, n_contracts=self._life_best['n_contracts'], rng=np.random.default_rng(self.SEED + 7700))
                self.robustness.append(dict(block=self._b, evaluation=self._e, funded=self._f))
        finally:
            self.BOOTSTRAP_BLOCK = self._blk0
        self.verdict = 'NEGATIVE EV' if self._net <= 0 else 'THIN' if self._mult < 2 or self._life_best['p_zero'] > 0.7 else 'WORKABLE' if self._mult < 4 else 'STRONG'
