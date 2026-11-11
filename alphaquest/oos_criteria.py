"""Frozen OOS acceptance rules and verification of native period measurements."""
from decimal import Decimal
from hashlib import sha256
import json

from .optimization_cache import artifacts, digest
from .decimal_math import multiply

FILE = 'oos_screening.json'
POLICY = dict(version='campaign-oos-v1', minimum_history_months=6, minimum_complete_months=6, minimum_closed_trades=50,
              annual_profit_retention_pct_gte='50', trade_profit_retention_pct_gte='50',
              drawdown_multiple_lte='1.5', profitable_month_floor_pct='40',
              profitable_month_degradation_pp_lte='15', extra_slippage_ticks_per_fill=1,
              annualization_days='365.2425', equity_basis='every observed bar close, including open P&L and charged costs',
              selection='assess every frozen Narrow candidate independently; no reselection')
METRICS = ('oos_history_months', 'oos_annual_net_profit', 'oos_mtm_max_drawdown',
           'oos_profitable_months_pct', 'oos_full_months', 'oos_longest_dd_pct', 'oos_stress_net_profit')


def rules():
    return ['At least six calendar months of observed OOS coverage, six complete months, and 50 closed trades.',
            'Net OOS profit after costs must be positive.',
            'Annualized net OOS profit must retain at least 50% of the same configuration’s IS annualized net profit.',
            'Net profit per closed trade must retain at least 50% of IS profit per trade.',
            'Maximum bar-close MTM drawdown must be no more than 1.5 × IS MTM drawdown. A zero IS drawdown allows only zero OOS drawdown.',
            'Profitable complete OOS months must be at least 40% and no more than 15 percentage points below IS; zero/no-trade months count as nonprofitable.',
            'A native OOS rerun with +1 tick slippage per fill must remain profitable. All seven checks must pass per candidate; multiple candidates can pass.']


def evaluate(captured, reference):
    p = captured['policy']
    if p != POLICY:
        raise ValueError('Unsupported saved OOS acceptance policy.')
    m, base = captured['metrics'], reference['metrics']
    net, trades = Decimal(str(captured['total_net_pnl'])), captured['closed_trades']
    is_net, is_trades = Decimal(str(reference['total_net_pnl'])), reference['closed_trades']
    annual, is_annual = Decimal(str(m['oos_annual_net_profit'])), Decimal(str(base['is_annual_net_profit']))
    dd, is_dd = Decimal(str(m['oos_mtm_max_drawdown'])), Decimal(str(base['is_mtm_max_drawdown']))
    if is_net <= 0 or is_annual <= 0 or is_trades <= 0:
        raise ValueError('Frozen IS comparison must have positive net profit, annualized profit and closed trades.')
    avg, is_avg = net / trades if trades else None, is_net / is_trades
    monthly = Decimal(str(m['oos_profitable_months_pct'])) if m['oos_profitable_months_pct'] is not None else None
    required_monthly = max(Decimal(p['profitable_month_floor_pct']), Decimal(str(base['is_profitable_months_pct'])) - Decimal(p['profitable_month_degradation_pp_lte']))
    annual_retention = annual * 100 / is_annual
    trade_retention = avg * 100 / is_avg if avg is not None else None
    evidence = (m['oos_history_months'] >= p['minimum_history_months'] and m['oos_full_months'] >= p['minimum_complete_months'] and trades >= p['minimum_closed_trades'])
    checks = [
        dict(id='evidence', label='OOS history and trades', passed=evidence,
             actual=f"{m['oos_history_months']} months; {m['oos_full_months']} complete months; {trades} trades", required='≥ 6 observed months, ≥ 6 complete months and ≥ 50 closed trades'),
        dict(id='net_profit', label='Net OOS profitability', passed=net > 0, actual=f'{net:.2f} CU', required='> 0 after costs'),
        dict(id='annual_retention', label='Annualized net profit retention', passed=multiply(annual,Decimal(100)) >= multiply(is_annual,Decimal(p['annual_profit_retention_pct_gte'])),
             actual=f'{annual_retention:.2f}% · OOS {annual:.2f} / IS {is_annual:.2f} CU/year', required='≥ 50% of IS'),
        dict(id='trade_retention', label='Net profit per trade retention', passed=trades > 0 and multiply(net,Decimal(is_trades * 100)) >= multiply(multiply(is_net,Decimal(trades)),Decimal(p['trade_profit_retention_pct_gte'])),
             actual=f'{trade_retention:.2f}%' if trade_retention is not None else 'No closed trades', required='≥ 50% of IS net profit per trade'),
        dict(id='drawdown', label='MTM drawdown deterioration', passed=dd <= multiply(is_dd,Decimal(p['drawdown_multiple_lte'])),
             actual=f'OOS {dd:.2f} / IS {is_dd:.2f} CU', required='OOS ≤ 1.5 × IS; zero IS requires zero OOS'),
        dict(id='profitable_months', label='Profitable months retention', passed=monthly is not None and monthly >= required_monthly,
             actual=f'{monthly:.2f}%' if monthly is not None else 'No complete months', required=f'≥ {required_monthly:.2f}% (40% floor; at most 15 percentage points below IS)'),
        dict(id='cost_stress', label='Extra-slippage OOS rerun', passed=Decimal(str(m['oos_stress_net_profit'])) > 0,
             actual=f"{Decimal(str(m['oos_stress_net_profit'])):.2f} CU", required='Net profit > 0 with +1 tick per fill')]
    qualifies = all(c['passed'] for c in checks)
    return dict(policy=p, qualifies=qualifies, status='passed' if qualifies else 'insufficient_evidence' if not evidence else 'failed',
                checks=checks, annual_profit_retention_pct=str(annual_retention), profit_per_trade_retention_pct=str(trade_retention) if trade_retention is not None else None)


def verified_oos(runs, report):
    captured = report.get('oos_screening')
    if not captured or captured['policy'] != POLICY:
        raise ValueError('The native OOS measurements or policy are unavailable.')
    path = runs.root / report['id'] / FILE
    if path.is_symlink() or sha256(path.read_bytes()).hexdigest() != captured['sha256']:
        raise ValueError('Saved OOS measurements are missing or changed.')
    if json.loads(path.read_bytes()) != {k:v for k,v in captured.items() if k != 'sha256'}:
        raise ValueError('Saved OOS measurements differ from the native report.')
    research = report['run_metadata']['research']
    if (research['phase'] != 'oos' or research['workflow_phase'] != 'oos' or research['oos_policy'] != POLICY
            or captured['closed_trades'] != report['summary']['trades_taken'] or captured['total_net_pnl'] != report['summary']['total_net_pnl']):
        raise ValueError('OOS measurements differ from the frozen native run.')
    stress = runs.get(captured['cost_stress']['run_id'])
    expected = dict(report['execution_settings']);expected['slippage_ticks'] += POLICY['extra_slippage_ticks_per_fill']
    if not stress:
        raise ValueError('The saved OOS cost-stress report is missing.')
    left, right = report['run_metadata'], stress['run_metadata']
    if (stress['execution_settings'] != expected or right['dataset'] != left['dataset'] or right['strategy'] != left['strategy']
            or right['selection'] != left['selection'] or right['research']['plan'] != research['plan']
            or right['research'].get('source_candidate_run_id') != report['id']
            or right['research'].get('workflow_phase') != 'oos_cost_stress'
            or right['research'].get('phase') != 'oos' or right['research'].get('parent_run_id') != research['parent_run_id']
            or right['research'].get('frozen_identity') != research['frozen_identity']
            or stress['summary'] != captured['cost_stress']['summary']
            or artifacts(runs.root, stress) != captured['cost_stress']['artifacts']):
        raise ValueError('OOS cost stress does not match the same frozen candidate, source, dates and extra tick.')
    if sha256((runs.root / stress['id'] / stress['artifacts']['report']).read_bytes()).hexdigest() != captured['cost_stress']['report_sha256']:
        raise ValueError('Saved OOS cost-stress report changed.')
    return captured, stress
