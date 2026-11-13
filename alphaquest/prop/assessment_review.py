"""Frozen Prop Sim economic review and chronological-start orchestration.

Numerical account transitions stay in the existing phase profile owners. This
module evaluates their saved outputs; it never selects or changes a candidate.
"""
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import math
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

VERSION = 'prop-oos-review-v1'


class AssessmentLimits(BaseModel):
    model_config = ConfigDict(extra='forbid')
    maximum_cost_per_funded: StrictStr | None = None
    maximum_calendar_days_to_funded: StrictInt | None = Field(default=None, ge=1, le=3650)
    minimum_funded_receipts: StrictStr | None = None
    minimum_history_calendar_days: StrictInt = Field(default=90, ge=1, le=3650)
    minimum_closed_trades: StrictInt = Field(default=30, ge=1, le=100000)
    account_start_count: StrictInt = Field(default=5, ge=2, le=12)

    @field_validator('maximum_cost_per_funded', 'minimum_funded_receipts')
    @classmethod
    def money(cls, value):
        if value is None:
            return value
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError('Enter a numeric USD limit.') from exc
        if not number.is_finite() or not 0 < number <= 1000000000:
            raise ValueError('Economic USD limits must be positive and at most one billion.')
        return str(number)

    def for_phase(self, phase):
        if phase == 'evaluation':
            if self.maximum_cost_per_funded is None or self.maximum_calendar_days_to_funded is None or self.minimum_funded_receipts is not None:
                raise ValueError('Evaluation requires maximum acquisition cost and calendar days only.')
        elif phase == 'funded':
            if self.minimum_funded_receipts is None or self.maximum_cost_per_funded is not None or self.maximum_calendar_days_to_funded is not None:
                raise ValueError('Funded requires minimum received cash only; no acquisition inputs.')
        else:
            raise ValueError('Unknown assessment phase.')
        return self


def implementation():
    return dict(version=VERSION, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


def start_plan(period, horizon, count, closures=()):
    first, last = (date.fromisoformat(period[k]) for k in ('first_session', 'last_session'))
    closed = set(closures)
    eligible = [d.date() for d in pd.bdate_range(first, last)
                if str(d.date()) not in closed and d.date()+timedelta(days=horizon-1) <= last]
    starts = [] if len(eligible) < count else [str(eligible[round(i*(len(eligible)-1)/(count-1))]) for i in range(count)]
    return dict(version='evenly-spaced-covered-starts-v1', period=period,
        horizon_calendar_days=horizon, requested_starts=count, starts=starts,
        status='ready' if starts else 'insufficient_coverage',
        eligible_starts=len(eligible),
        selection='Evenly spaced across all eligible weekday starts using coverage only; no P&L, ranking or cherry-picking.',
        clock='Chicago civil dates; exclusive horizon cutoff; inherited declared weekday/closure scenario, not a newly verified exchange calendar.')


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) else None


def distribution(row, phase):
    """All-start distributions; first-receipt timing is explicitly conditional."""
    paths = row.get('paths', [])
    if phase == 'evaluation':
        values = [number(p.get('calendar_days_to_funded', p.get('observed_calendar_days') if p.get('event')=='funded' else None)) for p in paths]
        complete = bool(paths) and all(v is not None for v in values)
        return dict(paths=len(paths), unresolved_paths=sum(v is None for v in values),
            p90_calendar_days=(float(np.quantile(values, .9, method='inverted_cdf')) if complete else None),
            includes_all_paths=True)
    cash = [number(p.get('cash_received')) for p in paths]
    complete = bool(paths) and all(v is not None for v in cash)
    # Read the actual versioned rule owner rather than inferring missing rungs
    # from a sample in which nobody reached the last payout.
    from . import native_engine, lucid_engine
    profile = row['manifest']['configuration']['profile']['profile_id']
    rungs = len((lucid_engine.Rules() if profile == 'lucidflex-50k' else native_engine.Rules()).ladder)
    first = [number(p.get('days_to_first_payout')) for p in paths]
    first = [v for v in first if v is not None]
    times = dict(zip(('median', 'p75', 'p90'), map(float, np.quantile(first, [.5,.75,.9], method='inverted_cdf')))) if first else None
    return dict(paths=len(paths), includes_zero_paths=True,
        probability_zero_received_cash=(sum(v == 0 for v in cash)/len(cash) if complete else None),
        cash_quantiles=(dict(zip(('p10','median','p90'),map(float,np.quantile(cash,[.1,.5,.9],method='inverted_cdf')))) if complete else None),
        first_receipt_calendar_days_conditional_on_receipt=times,
        first_receipt_observations=len(first),
        payout_milestones=[dict(payout=k, probability_requested=sum(len(p.get('payout_events',[]))>=k for p in paths)/len(paths) if paths else None,
            probability_received=sum(sum(float(e.get('trader_cash_received',0))>0 for e in p.get('payout_events',[]))>=k for p in paths)/len(paths) if paths else None) for k in range(1,rungs+1)],
        interpretation='Cash quantiles and zero probability include every path. Timing is conditional on a receipt. Milestones distinguish requests from modeled receipts within the frozen horizon.')


def review(row, phase, policy, horizon):
    limits = AssessmentLimits.model_validate(policy['limits']).for_phase(phase)
    period = row['manifest']['configuration']['period']
    days = (date.fromisoformat(period['last_session'])-date.fromisoformat(period['first_session'])).days+1
    trades = row['manifest']['source']['backtest']['summary']['trades_taken']
    evidence = [dict(label='Historical calendar coverage', actual=days, required=limits.minimum_history_calendar_days, passed=days>=limits.minimum_history_calendar_days),
        dict(label='Closed source trades', actual=trades, required=limits.minimum_closed_trades, passed=trades>=limits.minimum_closed_trades),
        dict(label='Complete model estimate', actual=row['status'], required='estimated', passed=row['status']=='estimated')]
    if phase == 'funded':
        evidence.append(dict(label='Full frozen Funded horizon', actual=days, required=horizon, passed=days>=horizon))
    checks = []
    metrics = row['metrics']
    for key, label, limit, maximum in ([('cost_per_funded','Mean acquisition cost',limits.maximum_cost_per_funded,True),
            ('expected_calendar_days_to_funded','Mean calendar days to funded',limits.maximum_calendar_days_to_funded,True)] if phase=='evaluation' else
            [('expected_funded_cash_payouts_within_horizon','Mean trader cash received',limits.minimum_funded_receipts,False)]):
        actual = number(metrics.get(key)); bound = float(limit)
        checks.append(dict(metric=key,label=label,actual=actual,limit=bound,comparison='<=' if maximum else '>=',
            passed=None if actual is None else actual<=bound if maximum else actual>=bound))
    if phase=='funded':
        for violation in row.get('constraint_violations',[]):
            checks.append(dict(metric=violation,label='Frozen optional constraint: '+violation,actual=None,limit=None,comparison='frozen declaration',passed=False))
    complete = all(c['passed'] for c in evidence) and all(c['passed'] is not None for c in checks)
    verdict = 'INCONCLUSIVE' if not complete else 'PASS' if all(c['passed'] for c in checks) else 'FAIL'
    changes = []
    for key, comparison in row.get('is_comparison',{}).items():
        before, after = number(comparison.get('is_value')),number(comparison.get('oos_value'))
        if before is None or after is None:
            continue
        probability = key in ('pass_probability','account_breach_probability','probability_first_payout')
        higher_bad = key in ('cost_per_funded','expected_calendar_days_to_funded','account_breach_probability')
        delta = after-before
        changes.append(dict(metric=key,is_value=before,oos_value=after,delta=delta,
            percentage_points=delta*100 if probability else None,
            relative_change_pct=delta/before*100 if before else None,
            adverse=round(delta*(1 if higher_bad else -1),8)>0))
    return dict(version=VERSION, verdict=verdict, watch=any(c['adverse'] for c in changes),
        evidence=evidence, economic_checks=checks, is_changes=changes,
        declaration_timing=policy['declaration_timing'], policy_sha256=policy['policy_sha256'],
        interpretation='PASS means the declared economic limits and evidence minimums were met. Adverse IS changes are review warnings, not extra gates or proof of statistically significant degradation. MC precision is not future/regime uncertainty. OOS has already been accessed during strategy qualification.')


def run_start_sensitivity(runs, search, checks, policy, checkpoint, progress):
    """Invoke existing chronological owners on each predetermined covered slice."""
    from .phase_profiles import prepare_phase_source, verify_phase_source
    from .phase_search import PhaseCalendar
    from .evaluation_profiles import calendar_evaluation_paths
    from .funded_profiles import _dated_funded_paths
    from .adapter import canonical
    phase = search.mode.removesuffix('_optimization')
    plan = policy['start_plan']; output=[]
    from dataclasses import asdict
    configs = {canonical(asdict(c)):c for c in search.candidates}
    for check in checks:
        checkpoint()
        candidate = configs[canonical(check['manifest']['configuration'])]
        if policy['phase'] != phase or plan['period'] != check['manifest']['configuration']['period']:
            raise ValueError('Account-start plan does not match the frozen OOS coverage.')
        snapshot, days, _ = prepare_phase_source(runs,candidate.source,candidate.profile,candidate.micros,candidate.simulation,candidate.period,candidate.costs,candidate.sizing)
        grid = [str(d.date()) for d in pd.bdate_range(candidate.period.first_session,candidate.period.last_session)]
        if len(grid) != len(days):
            raise ValueError('Chronological daybook does not match its captured weekday calendar.')
        closed=set(search.calendar.closures); book=dict(zip(grid,days)); paths=[]
        for start in plan['starts']:
            checkpoint();progress(f'Account-start sensitivity · {candidate.micros} MNQ · {start}')
            cutoff=date.fromisoformat(start)+timedelta(days=plan['horizon_calendar_days'])
            subset=[book[d] for d in grid if start<=d<str(cutoff) and d not in closed]
            calendar=PhaseCalendar((start,),str(cutoff),tuple(sorted(d for d in closed if start<=d<=str(cutoff))))
            if phase=='evaluation':
                result,_=calendar_evaluation_paths(subset,candidate.profile,candidate.micros,candidate.simulation,candidate.sampling,
                    replace(candidate.retry,max_calendar_days=plan['horizon_calendar_days']),calendar,chronological=True,checkpoint=checkpoint,sizing=candidate.sizing)
            else:
                result,_,_=_dated_funded_paths(subset,candidate.profile,candidate.micros,search.horizon_calendar_days,calendar,
                    search.receipt_delay_calendar_days,candidate.simulation,candidate.sampling,candidate.sizing,chronological=True,checkpoint=checkpoint)
            paths.append(dict(start_date=start,cutoff_exclusive=str(cutoff),result=result[0]))
        verify_phase_source(runs,candidate.source,snapshot)
        output.append(dict(frozen_candidate_id=check['frozen_candidate_id'],micros=candidate.micros,paths=paths,
            summary=start_summary(paths,phase)))
    return dict(plan=plan,candidates=output,status='COMPLETE' if plan['starts'] else 'INCONCLUSIVE',simulations=len(plan['starts'])*len(output),
        interpretation='One actual-order saved-signal account per predetermined start, no resampling, replacement or selection. Overlapping windows are dependent scenarios, not independent experiments. An Evaluation not funded before cutoff is window-censored, not a provider-deadline breach.')


def start_summary(paths, phase):
    """Descriptive ranges, never a completed-only acquisition estimate."""
    rows=[p['result'] for p in paths]
    def spread(key):
        values=[number(r.get(key)) for r in rows]
        if not values or any(v is None for v in values):return None
        return dict(minimum=min(values),median=float(np.median(values)),maximum=max(values))
    if phase=='evaluation':
        return dict(starts=len(rows),funded=sum(bool(r['acquisition_completed']) for r in rows),
            window_censored=sum(bool(r['censored']) for r in rows),
            paid_fees=spread('paid_fees'),calendar_days_to_funded=spread('calendar_days_to_funded'),
            interpretation='Funding-time range is unavailable if any start is censored. Fees include every start, including failed attempts. These are dependent scenarios, not MC probabilities.')
    return dict(starts=len(rows),cash_received=spread('cash_received'),pending_cash=spread('pending_cash'),
        zero_receipt_starts=sum(r['cash_received']==0 for r in rows),
        outcomes={key:sum(r['outcome']==key for r in rows) for key in sorted({r['outcome'] for r in rows})},
        interpretation='Cash ranges include zero-receipt accounts. Open accounts are observed for the full horizon; lifetime remains censored. No replacement accounts.')


def enrich(calculations, search, assessment, runs, checks, checkpoint, progress):
    options=assessment['prop_sim_review']
    if options['implementation']!=implementation():
        raise ValueError('Assessment review implementation changed after declaration.')
    from .adapter import canonical
    policy=options['policy']
    if (policy['implementation']!=options['implementation'] or
            sha256(canonical({k:v for k,v in policy.items() if k!='policy_sha256'}).encode()).hexdigest()!=policy['policy_sha256']):
        raise ValueError('Declared assessment policy identity changed.')
    phase=search.mode.removesuffix('_optimization')
    for row in calculations['candidates']:
        row['outcome_summary']=distribution(row,phase)
        row['economic_assessment']=review(row,phase,options['policy'],getattr(search,'horizon_calendar_days',None))
    calculations['assessment_policy']=options['policy']
    calculations['review_implementation']=options['implementation']
    calculations['assessment_kind']=options['kind']
    calculations.pop('account_start_sensitivity',None)
    if options['kind']=='account_starts':
        calculations['account_start_sensitivity']=run_start_sensitivity(runs,search,checks,options['policy'],checkpoint,progress)
    return calculations
