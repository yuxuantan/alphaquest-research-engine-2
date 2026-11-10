"""Versioned strategy-screening policy, shared by execution, admission and the portal."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from .decimal_math import subtract
from .drawdown import Drawdown

VERSION = 'is-broad-v2'
FILE = 'is_screening.json'
METRICS = ('is_history_months', 'is_annual_net_profit', 'is_mtm_max_drawdown',
           'is_annual_profit_dd_ratio', 'is_profitable_months_pct', 'is_full_months',
           'is_longest_dd_pct', 'is_stress_net_profit')


def policy():
    return dict(version=VERSION, minimum_history_months=24, minimum_closed_trades=100,
                annual_profit_dd_ratio_gt='1', profitable_months_pct_gt='50',
                longest_dd_period_fraction_lt='0.25', extra_slippage_ticks_per_fill=1,
                equity_basis='every observed bar close, cash plus open-position P&L; not tick/intrabar equity',
                calendar_basis='source timezone; inclusive IS dates; complete calendar months only; zero/no-trade months count as nonprofitable',
                annualization_days='365.2425')


def stage_criteria():
    return [dict(id='mechanic_validation', label='Mechanic validation', implemented=True, rules=[
        'Run the default parameters on IS data.',
        'Review every outcome metric for MultiCharts parity and every sampled trade for parity and execution correctness.',
        'Confirm all required checks. A zero-trade validation cannot pass.']),
        dict(id='is_broad', label='IS Broad', implemented=True, policy=policy(), rules=[
            'At least 24 calendar months of observed IS coverage and 100 closed trades.',
            'Total net IS profit > 0 after commissions and slippage.',
            'Annualized net profit / maximum mark-to-market drawdown > 1.',
            'More than 50% of complete IS calendar months profitable; zero/no-trade months are nonprofitable.',
            'Longest mark-to-market drawdown < 25% of the IS period, including any unresolved drawdown through IS end.',
            'A native rerun with one extra tick of slippage per fill remains net profitable, with identical parameters.',
            'All six tests must pass before selecting and permanently confirming one or two configurations.']),
        dict(id='is_narrow', label='IS Narrow', implemented=False, rules=[
            'Retain all six IS Broad criteria.',
            'At least 70% of valid immediate parameter neighbors are profitable, using the predeclared grid steps and every applicable direction.',
            'At least three of four consecutive, approximately equal IS calendar periods are profitable, including the most recent.',
            'Total net profit remains positive after excluding the single best complete calendar month.',
            'The 95% lower confidence bound on mean net daily P&L is above zero, preserving time dependence and adjusting for all Broad/Narrow configurations tried, including reruns.',
            'Freeze the selected configurations before final OOS. These additional checks are agreed requirements; execution is not implemented yet.']),
        dict(id='oos', label='OOS', implemented=False, rules=[
            'Assess frozen choices without parameter reselection or using OOS to select IS candidates.',
            'Execution and final acceptance thresholds will be implemented separately; no OOS pass is currently available.'])]


def next_month(day):
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def seconds(delta):
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1_000_000


def evaluate(metrics, closed_trades, total_net, snapshot):
    """Re-evaluate exact saved measurements; no rounded UI values drive admission."""
    p = snapshot
    net = Decimal(str(total_net))
    full_months = int(metrics['is_full_months'])
    history = int(metrics['is_history_months'])
    dd = Decimal(str(metrics['is_mtm_max_drawdown']))
    annual = Decimal(str(metrics['is_annual_net_profit']))
    profitable = Decimal(str(metrics['is_profitable_months_pct'])) if full_months else None
    duration_pct = Decimal(str(metrics['is_longest_dd_pct']))
    stress = Decimal(str(metrics['is_stress_net_profit']))
    checks = [
        dict(id='evidence', label='History and trades', passed=history >= p['minimum_history_months'] and closed_trades >= p['minimum_closed_trades'],
             actual=f'{history} months; {closed_trades} closed trades', required='≥ 24 months and ≥ 100 closed trades'),
        dict(id='net_profit', label='Overall profitability', passed=net > 0, actual=str(net), required='Net IS profit > 0'),
        dict(id='annual_profit_dd', label='Annual profit / MTM drawdown', passed=annual > dd * Decimal(p['annual_profit_dd_ratio_gt']),
             actual=f'Annual net {annual}; MTM drawdown {dd}', required='Annualized net profit / MTM drawdown > 1'),
        dict(id='profitable_months', label='Profitable months', passed=profitable is not None and profitable > Decimal(p['profitable_months_pct_gt']),
             actual='No complete months' if profitable is None else f'{profitable}% of {full_months} complete months', required='> 50% profitable; zero/no-trade months included'),
        dict(id='drawdown_duration', label='Longest MTM drawdown', passed=duration_pct < Decimal(p['longest_dd_period_fraction_lt']) * 100,
             actual=f'{duration_pct}% of IS', required='< 25% of IS, including unresolved drawdown'),
        dict(id='cost_stress', label='Extra-slippage native rerun', passed=stress > 0, actual=str(stress), required='Net profit > 0 with +1 tick per fill')]
    if any(not Decimal(str(value)).is_finite() for key, value in metrics.items() if value is not None):
        raise ValueError('Screening measurements must be finite.')
    return dict(status='qualified' if all(c['passed'] for c in checks) else
                'insufficient_evidence' if not checks[0]['passed'] or not full_months else 'not_qualified',
                qualifies=all(c['passed'] for c in checks), checks=checks)


def verified_screening(runs, report):
    """Read immutable native evidence and verify the paired cost-stress run."""
    captured = report.get('is_screening')
    if not captured or captured.get('policy') != policy():
        raise ValueError('This grid lacks the six-criterion screening evidence. Run a new IS Broad grid.')
    path = runs.root / report['id'] / FILE
    if path.is_symlink() or sha256(path.read_bytes()).hexdigest() != captured['sha256']:
        raise ValueError('Saved IS screening evidence is missing or changed.')
    if json.loads(path.read_bytes()) != {k: v for k, v in captured.items() if k != 'sha256'}:
        raise ValueError('IS screening evidence differs from the saved report.')
    if (captured['closed_trades'] != report['summary']['trades_taken'] or
            captured['total_net_pnl'] != report['summary']['total_net_pnl']):
        raise ValueError('Screening totals differ from the native backtest.')
    check = evaluate(captured['metrics'], captured['closed_trades'], captured['total_net_pnl'], captured['policy'])
    if any(captured[key] != check[key] for key in check):
        raise ValueError('Screening verdict differs from its measured criteria.')
    stress = runs.get(captured['cost_stress']['run_id'])
    if not stress:
        raise ValueError('The native cost-stress report is unavailable.')
    expected = dict(report['execution_settings'])
    expected['slippage_ticks'] += captured['policy']['extra_slippage_ticks_per_fill']
    left, right = report['run_metadata'], stress['run_metadata']
    paired_candidate = left.get('detailed_from_run_id') or left.get('risk_from_run_id') or report['id']
    if (stress['execution_settings'] != expected or right['dataset'] != left['dataset'] or
            right['strategy'] != left['strategy'] or right['selection'] != left['selection'] or
            right['research'].get('source_candidate_run_id') != paired_candidate or
            right['research'].get('workflow_phase') != 'is_broad_cost_stress' or
            right['research'].get('workflow_id') != left['research']['workflow_id'] or
            right['research']['plan'] != left['research']['plan'] or
            right['research']['phase'] != 'is' or
            stress['summary'] != captured['cost_stress']['summary'] or
            stress['execution_settings'] != captured['cost_stress']['execution_settings']):
        raise ValueError('The cost-stress report does not match the same IS source, parameters and +1-tick execution.')
    stress_file = runs.root / stress['id'] / stress['artifacts']['report']
    if stress_file.is_symlink() or sha256(stress_file.read_bytes()).hexdigest() != captured['cost_stress']['report_sha256']:
        raise ValueError('The saved cost-stress report changed.')
    from .optimization_cache import artifacts
    if artifacts(runs.root, stress) != captured['cost_stress']['artifacts']:
        raise ValueError('Saved native cost-stress artifacts are missing or changed.')
    return captured, stress


class ScreeningCapture:
    """Bounded streaming measurements of authoritative engine equity, never reconstructed fills."""
    def __init__(self, initial, research, source_timezone):
        self.policy = research['screening_policy']
        if self.policy != policy():
            raise ValueError('Unsupported IS Broad screening policy. Start a new grid.')
        self.plan = research['plan']
        self.zone = ZoneInfo(source_timezone)
        self.start_day = date.fromisoformat(self.plan['is_start'])
        self.end_day = date.fromisoformat(self.plan['is_end']) + timedelta(days=1)
        self.start = datetime.combine(self.start_day, time(), self.zone).astimezone(ZoneInfo('UTC'))
        self.end = datetime.combine(self.end_day, time(), self.zone).astimezone(ZoneInfo('UTC'))
        self.initial = self.last_equity = initial
        self.first_day = self.last_day = None
        self.month_ends = {}
        self.drawdown = Drawdown(initial, self.start)
        self.stress = research['cost_stress']

    def observe(self, point):
        if point.timestamp_utc is None:
            return
        if not self.start <= point.timestamp_utc < self.end:
            raise ValueError('IS screening received an observation outside its frozen IS period.')
        day = point.timestamp_utc.astimezone(self.zone).date()
        self.first_day = self.first_day or day
        self.last_day = day
        self.last_equity = point.equity
        self.month_ends[date(day.year, day.month, 1)] = point.equity
        self.drawdown.observe(point.timestamp_utc, point.equity)

    def finish(self, trades, total_net):
        if self.first_day is None:
            raise ValueError('IS screening requires observed source bars.')
        dd = self.drawdown.finish(self.end)
        duration = seconds(self.end - self.start)
        annual = Decimal(str(total_net)) * Decimal(self.policy['annualization_days']) * 86400 / duration
        # Coverage uses actual first/last observed source dates, not padded declaration dates.
        coverage_end = self.last_day + timedelta(days=1)
        months = (coverage_end.year - self.first_day.year) * 12 + coverage_end.month - self.first_day.month
        months -= coverage_end.day < self.first_day.day
        rows = []
        month = date(self.start_day.year, self.start_day.month, 1)
        previous = self.initial
        while month < self.end_day:
            end = next_month(month)
            equity = self.month_ends.get(month, previous)
            full = month >= max(self.start_day, self.first_day) and end <= min(self.end_day, coverage_end)
            rows.append(dict(month=month.isoformat()[:7], net_pnl=subtract(equity, previous), complete=full))
            previous, month = equity, end
        complete = [r for r in rows if r['complete']]
        profitable = sum(r['net_pnl'] > 0 for r in complete)
        metrics = dict(is_history_months=months, is_annual_net_profit=annual,
                       is_mtm_max_drawdown=dd['max_drawdown_amount'],
                       is_annual_profit_dd_ratio=annual / dd['max_drawdown_amount'] if dd['max_drawdown_amount'] else None,
                       is_profitable_months_pct=Decimal(profitable) * 100 / len(complete) if complete else None,
                       is_full_months=len(complete), is_longest_dd_pct=dd['max_drawdown_duration_seconds'] * 100 / duration,
                       is_stress_net_profit=self.stress['summary']['total_net_pnl'])
        return dict(policy=self.policy, metrics=metrics, closed_trades=trades, total_net_pnl=total_net,
                    months=rows, observed_start=self.first_day.isoformat(), observed_end=self.last_day.isoformat(),
                    period_start_utc=self.start.isoformat(), period_end_exclusive_utc=self.end.isoformat(),
                    mtm_drawdown_duration_seconds=dd['max_drawdown_duration_seconds'], cost_stress=self.stress,
                    **evaluate(metrics, trades, total_net, self.policy))
