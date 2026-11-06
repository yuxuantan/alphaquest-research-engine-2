"""Standalone IS Evaluation search; no funded objective or account simulation.

Version 1 fits an empirical IID attempt law using the independent evaluation
component, then runs sequential renewal chains on a declared session calendar.
It deliberately does not reuse the legacy retained-block chain's timing as an
IID/calendar estimate. See docs/prop_simulation.md for the exact estimands.
"""
from bisect import bisect_left
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import numpy as np

from .adapter import canonical, digest
from .evaluation_profiles import simulate_evaluation_profile
from .phase_profiles import (
    EvaluationProfile, EvaluationSamplingConfig, ResearchPeriod, SavedTradeSource,
    SimulationConfig, SourceCosts, positive_integer,
    verify_phase_source,
)

from .phase_search import PhaseCalendar as AcquisitionCalendar

MODEL_VERSION = 'evaluation-optimization-empirical-iid-v1'


@dataclass(frozen=True)
class SequentialRetry:
    model: str = 'independent_empirical_sequential_retry'
    retry_delay_calendar_days: int = 0
    activation_delay_sessions: int = 1
    activation_eligibility: str = 'automatic_after_pass_and_delay'
    max_attempts: int = 10000
    max_calendar_days: int = 3650

    def __post_init__(self):
        if self.model != 'independent_empirical_sequential_retry':
            raise ValueError('Only unlimited independent sequential retries are supported; guards are censoring, not budgets.')
        if self.activation_eligibility != 'automatic_after_pass_and_delay':
            raise ValueError('Only automatic activation eligibility after the saved delay is supported.')
        for name in ('retry_delay_calendar_days', 'activation_delay_sessions'):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 365:
                raise ValueError(f'{name} must be an integer from 0 to 365.')
        positive_integer('max_attempts', self.max_attempts, 10000)
        positive_integer('max_calendar_days', self.max_calendar_days, 36500)


@dataclass(frozen=True)
class EvaluationCandidate:
    source: SavedTradeSource
    profile: EvaluationProfile
    micros: int
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    sampling: EvaluationSamplingConfig = field(default_factory=EvaluationSamplingConfig)
    costs: SourceCosts = field(default_factory=SourceCosts)
    period: ResearchPeriod | None = None
    retry: SequentialRetry = field(default_factory=SequentialRetry)

    def __post_init__(self):
        for name, cls in [('source', SavedTradeSource), ('simulation', SimulationConfig),
                          ('sampling', EvaluationSamplingConfig), ('costs', SourceCosts),
                          ('retry', SequentialRetry)]:
            if not isinstance(getattr(self, name), cls):
                raise ValueError(f'Evaluation candidate requires {cls.__name__} for {name}.')
        if self.period is not None and not isinstance(self.period, ResearchPeriod):
            raise ValueError('Evaluation candidate period must be a ResearchPeriod.')
        id = self.source.source_backtest_id
        if not isinstance(id, str) or UUID(id).hex != id:
            raise ValueError('Saved source ID must be a lowercase UUID hex string.')
        if not isinstance(self.source.trade_file, str):
            raise ValueError('Explicit source trade_file must be a string.')
        if not isinstance(self.profile, EvaluationProfile):
            raise ValueError('Evaluation selection requires only an EvaluationProfile.')
        if self.profile.profile_id != 'apex-50k-eod':
            raise ValueError('Dated IID optimization currently supports Apex EOD only; Lucid calendar inactivity requires a dated attempt kernel.')
        if self.sampling.computational_horizon_weekdays is not None:
            raise ValueError('Apex expiry is a provider event, not a configurable computational horizon.')


@dataclass(frozen=True)
class EvaluationSearch:
    source_backtest_id: str
    candidates: tuple[EvaluationCandidate, ...]
    calendar: AcquisitionCalendar
    mode: str = 'evaluation_optimization'

    def __post_init__(self):
        if self.mode != 'evaluation_optimization':
            raise ValueError('Unsupported phase search mode.')
        if not 1 <= len(self.candidates) <= 128:
            raise ValueError('Declare 1–128 candidates; no implicit search truncation.')
        if self.source_backtest_id not in {c.source.source_backtest_id for c in self.candidates}:
            raise ValueError('The navigation anchor must belong to the candidate set.')
        for c in self.candidates:
            if (date.fromisoformat(self.calendar.coverage_end) - max(map(date.fromisoformat, self.calendar.start_dates))).days < c.retry.max_calendar_days:
                raise ValueError('Calendar coverage must include every chain guard date.')
            if c.sampling.chain_simulations % len(self.calendar.start_dates):
                raise ValueError('Chain count must be divisible by start cohort size for equal weighting.')


def parse_request(raw):
    """Strict nested contracts: opposite-phase/unknown fields are errors."""
    try:
        value = dict(raw)
        candidates = []
        for item in value.pop('candidates'):
            item = dict(item)
            for name, cls in [('source', SavedTradeSource), ('profile', EvaluationProfile),
                              ('simulation', SimulationConfig), ('sampling', EvaluationSamplingConfig),
                              ('costs', SourceCosts), ('period', ResearchPeriod), ('retry', SequentialRetry)]:
                if item.get(name) is not None:
                    item[name] = cls(**item[name])
            candidates.append(EvaluationCandidate(**item))
        calendar = dict(value.pop('calendar'))
        for name in ('start_dates', 'closures'):
            if name in calendar: calendar[name] = tuple(sorted(calendar[name]))
        return EvaluationSearch(candidates=tuple(candidates), calendar=AcquisitionCalendar(**calendar), **value)
    except (TypeError, KeyError, AttributeError) as exc:
        raise ValueError(f'Invalid evaluation-only search contract: {exc}') from exc


def check_search(runs, search):
    from .phase_search import check_candidates
    return check_candidates(runs, search)


def implementation_identity():
    # Include local source changes, including adapters and numerical kernels.
    names = ('evaluation_optimization.py', 'evaluation_profiles.py', 'phase_profiles.py',
             'native_analysis.py', 'native_engine.py', 'source.py', 'commissions.py',
             'phase_lifecycle.py', 'adapter.py', 'phase_search.py')
    from .native_analysis import kernel_identity
    return dict(files={name: digest(Path(__file__).with_name(name)) for name in names},
                kernel=kernel_identity({'ACCOUNT_TYPE': 'Apex EOD'}), numpy=np.__version__)


def search_key(search, checks):
    return sha256(canonical(dict(model=MODEL_VERSION, calendar=asdict(search.calendar),
        anchor=search.source_backtest_id,
        candidates=[{k:r[k] for k in ('candidate_id','prior_access','origin_trials')} for r in checks],
        implementation=implementation_identity())).encode()).hexdigest()


def _interval(values):
    se = float(np.std(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else None
    mean = float(np.mean(values))
    return dict(mean=mean, se=se, ci=None if se is None else [max(0., mean-1.96*se), mean+1.96*se])


def acquisition_metrics(component, profile, retry, calendar, sampling):
    """IID empirical renewal model retaining outcome/duration dependence.

    Guards observe partial paths; no successful-only acquisition means. Per-path
    schedules are seeded independently, so candidate ordering cannot affect draws.
    All times are local civil days to the first usable funded session.
    """
    from .native_analysis import wilson
    outcomes = component.outcomes
    durations = component.duration_weekdays
    if not outcomes or len(outcomes) != len(durations) or any(type(d) is not int or d < 1 for d in durations):
        raise ValueError('Attempt outcomes require matching positive whole-session durations.')
    if set(outcomes) - {'passed', 'blown', 'timeout', 'inactive'}:
        raise ValueError('Unsupported evaluation attempt outcome.')
    n = len(outcomes)
    passed = outcomes.count('passed')
    p = passed / n
    censored = component.censoring.censored_paths or 0
    fee, activation = Decimal(profile.evaluation_price), Decimal(profile.activation_fee)
    p_ci = wilson(passed, n)
    metrics = dict(pass_probability=p, pass_probability_ci=p_ci,
        pass_probability_bounds=[p, (passed+censored)/n], cost_per_funded=None,
        expected_calendar_days_to_funded=None, median_calendar_days_to_funded=None,
        p90_calendar_days_to_funded=None, probability_funded_by_day_30=None,
        probability_funded_by_day_60=None, expected_attempts_per_funded=None,
        funded_accounts_per_30_calendar_days=None)
    assumptions = dict(model=retry.model, retry=asdict(retry), calendar=asdict(calendar),
        attempt_law='Uniform empirical joint distribution of independent component outcome/session-duration pairs; stationary IID fresh-account retries, no retained block across retries',
        capital='Unlimited acquisition capital; no budget or economic horizon. Numerical guards censor the unlimited model.',
        activation='Automatic eligibility after the declared session delay; fee paid once at eligibility, only after passing; readiness is the next open session',
        time='Local civil date difference from purchase to first usable funded session; includes initial weekend/closure wait, failures, retry delay, activation delay and readiness wait; not 24-hour UTC durations',
        calendar_status='User-declared full-session closures and Monday–Friday openings; not a verified exchange/settlement calendar; no early closes',
        distribution='Inverse empirical CDF quantiles; equal-weight declared start-date cohort',
        chain_rng='PCG64 with SeedSequence([chain_seed, path_index]); input order never changes path streams; no paired-inference claim',
        legacy_chain='Existing component retained-block chain diagnostics are preserved separately, never used as IID calendar objectives')
    uncertainty = dict(pass_probability_se=float(np.sqrt(p*(1-p)/n)), cost_se=None, cost_ci=None,
        calendar_mean_se=None, calendar_mean_ci=None,
        interpretation='Nominal Monte Carlo intervals conditional on saved source/model. Calendar intervals condition on fitted empirical attempt law; they exclude first-stage fitting error. No simultaneous or paired dominance certification.',
        robust_dominance='not_established', quantile_ci=None,
        future_uncertainty='Historical sampling, model/rule uncertainty and future regime changes are not covered')
    reason = 'attempt_censoring' if censored else ('zero_observed_passes' if not passed else None)
    paths = []
    if reason:
        for day in (30, 60):
            metrics[f'probability_funded_by_day_{day}_bounds'] = [0., 1.]
        return dict(metrics=metrics, status='unresolved', reason=reason, paths=paths,
            censoring=dict(attempt_paths=censored, chain_paths=None, chains_run=0),
            uncertainty=uncertainty, assumptions=assumptions)
    first = min(map(date.fromisoformat, calendar.start_dates))
    end = date.fromisoformat(calendar.coverage_end)
    closed = set(calendar.closures)
    sessions = [first + timedelta(days=i) for i in range((end-first).days+1)
                if (first+timedelta(days=i)).weekday() < 5 and (first+timedelta(days=i)).isoformat() not in closed]
    schedule_hash = sha256()
    for i in range(sampling.chain_simulations):
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([sampling.chain_seed, i])))
        start = date.fromisoformat(sorted(calendar.start_dates)[i % len(calendar.start_dates)])
        cutoff = start + timedelta(days=retry.max_calendar_days)
        cursor = start
        cost = Decimal(0)
        paid = False
        attempts = 0
        state = 'attempt_guard'
        funded_date = None
        observed = start
        for _ in range(retry.max_attempts):
            # A new attempt is bought at cursor; its first session may be later.
            if cursor >= cutoff:
                observed = cutoff; state = 'calendar_guard'; break
            cost += fee; attempts += 1
            index = int(rng.integers(n))
            schedule_hash.update(f'{i}:{index};'.encode())
            last_index = bisect_left(sessions, cursor) + durations[index] - 1
            if last_index >= len(sessions) or sessions[last_index] >= cutoff:
                observed = cutoff; state = 'calendar_guard'; break
            last = sessions[last_index]
            # All failed and passed attempts consume their own full durations.
            observed = last + timedelta(days=1)
            if outcomes[index] == 'passed':
                eligible_index = last_index + retry.activation_delay_sessions
                ready_index = eligible_index + 1
                if eligible_index < len(sessions) and sessions[eligible_index] < cutoff:
                    cost += activation; paid = True
                if ready_index >= len(sessions) or sessions[ready_index] > cutoff:
                    observed = cutoff; state = 'activation_guard'; break
                funded_date = sessions[ready_index]
                observed = funded_date; state = 'funded'; break
            cursor = last + timedelta(days=1+retry.retry_delay_calendar_days)
        paths.append(dict(path=i, start_date=start.isoformat(), attempts=attempts,
            event=state, observed_calendar_days=(observed-start).days,
            funded_date=funded_date.isoformat() if funded_date else None,
            cost_accrued=str(cost), activation_paid=paid,
            pending_activation=state == 'activation_guard' and not paid,
            pending_readiness=state == 'activation_guard'))
    unresolved = [r for r in paths if r['event'] != 'funded']
    for day in (30, 60):
        known = sum(r['event'] == 'funded' and r['observed_calendar_days'] <= day for r in paths)
        possible = sum(r['event'] != 'funded' and r['observed_calendar_days'] <= day for r in paths)
        bounds = [known/len(paths), (known+possible)/len(paths)]
        metrics[f'probability_funded_by_day_{day}_bounds'] = bounds
        metrics[f'probability_funded_by_day_{day}'] = bounds[0] if not possible else None
        uncertainty[f'probability_funded_by_day_{day}_ci'] = wilson(known, len(paths)) if not possible else None
    times = [r['observed_calendar_days'] for r in paths]
    # Identifiable quantiles use all starts; unknown tails count as +infinity.
    for q, key in [(.5, 'median_calendar_days_to_funded'), (.9, 'p90_calendar_days_to_funded')]:
        known_times = sorted(r['observed_calendar_days'] for r in paths if r['event'] == 'funded')
        rank = int(np.ceil(q*len(paths)))
        if len(known_times) >= rank and all(r['observed_calendar_days'] > known_times[rank-1] for r in unresolved):
            metrics[key] = known_times[rank-1]
    if not unresolved:
        stats = _interval(times)
        # Equal cohort allocation: use within-start variance, not between-start
        # date variation, for conditional simulation error of the cohort mean.
        groups = [[r['observed_calendar_days'] for r in paths if r['start_date']==start]
                  for start in sorted(calendar.start_dates)]
        se = (float(np.sqrt(sum(np.var(g, ddof=1)/len(g) for g in groups))/len(groups))
              if all(len(g)>1 for g in groups) else None)
        stats.update(se=se, ci=None if se is None else [max(0.,stats['mean']-1.96*se),stats['mean']+1.96*se])
        metrics.update(cost_per_funded=float(fee * Decimal(n) / Decimal(passed) + activation),
            expected_attempts_per_funded=1/p, expected_calendar_days_to_funded=stats['mean'],
            funded_accounts_per_30_calendar_days=30/stats['mean'])
        uncertainty.update(cost_se=float(fee)*np.sqrt(p*(1-p)/n)/p**2,
            cost_ci=[float(fee)/p_ci[1]+float(activation), float(fee)/p_ci[0]+float(activation)],
            calendar_mean_se=stats['se'], calendar_mean_ci=stats['ci'])
    if len(calendar.start_dates)>1:
        # Fixed start strata are not identically distributed Bernoulli trials.
        for day in (30,60): uncertainty[f'probability_funded_by_day_{day}_ci'] = None
    return dict(metrics=metrics, status='censored' if unresolved else 'estimated',
        reason='chain_guard' if unresolved else None, paths=paths, assumptions=assumptions,
        uncertainty=uncertainty, schedule_sha256=schedule_hash.hexdigest(),
        censoring=dict(attempt_paths=censored, chain_paths=len(unresolved), chains_run=len(paths),
            mean_accrued_cost_lower_bound=float(np.mean([float(r['cost_accrued']) for r in paths])),
            mean_observed_days_lower_bound=float(np.mean(times)),
            restricted_mean_at_guard=float(np.mean(times)) if not any(r['event']=='attempt_guard' for r in paths) else None))


def pareto_sort(rows):
    """Strict two-objective nondominance; exact ties retain full membership."""
    rows = sorted(rows, key=lambda r: r['candidate_id'])
    def point(row):
        return row['metrics']['cost_per_funded'], row['metrics']['expected_calendar_days_to_funded']
    resolved = [r for r in rows if r['status'] == 'estimated' and all(x is not None and np.isfinite(x) for x in point(r))]
    unresolved = [r['candidate_id'] for r in rows if r not in resolved]
    for row in rows:
        dominated_by = []
        if row in resolved:
            c, t = point(row)
            dominated_by = [r['candidate_id'] for r in resolved if point(r)[0] <= c and point(r)[1] <= t and point(r) != (c,t)]
        row.update(pareto_member=row in resolved and not dominated_by,
            dominated=bool(dominated_by) if row in resolved else None,
            estimated_dominated_by=dominated_by, robust_dominated=None,
            pareto_rank=None,
            dominance_status='estimated_only' if row in resolved else 'unresolved_not_excluded')
    remaining = {r['candidate_id']:r for r in resolved}
    rank = 0
    while remaining:
        layer = [id for id,r in remaining.items() if not set(r['estimated_dominated_by']) & remaining.keys()]
        for id in layer: remaining.pop(id)['pareto_rank'] = rank
        rank += 1
    frontier = sorted([r for r in rows if r['pareto_member']], key=lambda r: (*point(r), r['candidate_id']))
    marginal = []
    for slow, fast in zip(frontier, frontier[1:]):
        cs, ts = point(slow); cf, tf = point(fast)
        marginal.append(dict(slow_candidate_id=slow['candidate_id'], fast_candidate_id=fast['candidate_id'],
            usd_per_calendar_day_saved=(cf-cs)/(ts-tf) if ts > tf else None,
            reason=None if ts > tf else 'identical_objectives_no_positive_time_saving'))
    return dict(candidates=rows, frontier=[r['candidate_id'] for r in frontier],
        unresolved_candidates=unresolved, marginal_acceleration_cost=marginal,
        winner=None, certified_frontier=False, dominance='estimated point estimates; robust dominance not established',
        tie_behavior='Exact cost/time ties all remain; ascending candidate SHA-256 is presentation only',
        acceleration_interpretation='USD per calendar day saved between adjacent points, not a lambda or recommendation; nonconvex Pareto points are retained')


def optimize_evaluation(runs, search, checks=None, progress=lambda message: None):
    checks = checks if checks is not None else check_search(runs, search)
    configurations = {canonical(asdict(c)): c for c in search.candidates}
    rows = []
    for check in checks:
        candidate = configurations[canonical(check['manifest']['configuration'])]
        progress('Evaluating '+check['candidate_id'][:12])
        component = simulate_evaluation_profile(runs, candidate.source, candidate.profile,
            candidate.micros, candidate.simulation, candidate.period, candidate.sampling, candidate.costs)
        if canonical(component.provenance['source']) != canonical(check['manifest']['source']):
            raise ValueError('Candidate source changed after source checking.')
        result = acquisition_metrics(component, candidate.profile, candidate.retry, search.calendar, candidate.sampling)
        rows.append(dict(candidate_id=check['candidate_id'], **result,
            component=asdict(component), manifest=check['manifest'], origin_trials=check['origin_trials']))
    # Recheck all sources at the publication boundary, including earlier candidates.
    for check in checks:
        c = configurations[canonical(check['manifest']['configuration'])]
        verify_phase_source(runs, c.source, check['manifest']['source'])
    return dict(model_version=MODEL_VERSION, phase='evaluation', **pareto_sort(rows))


def write_report(runs, staged, search, checks, calculations):
    """Capture inputs once and publish through the normal AnalysisStore files."""
    import csv
    staged = Path(staged)
    def save(name, data):
        (staged/name).write_text(canonical(data), encoding='utf-8')
    from .phase_search import capture_inputs
    capture_inputs(runs, staged, search, calculations)
    save('source_checks.json', checks)
    save('phase_candidates.json', [dict(candidate_id=r['candidate_id'], origin_trials=r['origin_trials'],
        **r['manifest']) for r in calculations['candidates']])
    save('phase_metrics.json', [dict(candidate_id=r['candidate_id'], metrics=r['metrics'], status=r['status'],
        uncertainty=r['uncertainty'], censoring=r['censoring'], assumptions=r['assumptions'],
        pareto_member=r['pareto_member'], dominated=r['dominated'], pareto_rank=r['pareto_rank']) for r in calculations['candidates']])
    save('frontier.json', {k:v for k,v in calculations.items() if k != 'candidates'})
    save('calculations.json', calculations)
    save('request.json', asdict(search))
    save('sampling.json', [dict(candidate_id=r['candidate_id'], configuration=r['manifest']['configuration']['sampling'],
        schedule_sha256=r.get('schedule_sha256'), uncertainty=r['uncertainty']) for r in calculations['candidates']])
    with (staged/'phase_metrics.csv').open('w', newline='') as stream:
        fields = ['candidate_id', 'status', 'pareto_member', 'dominated', *calculations['candidates'][0]['metrics']]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore'); writer.writeheader()
        for row in calculations['candidates']:
            writer.writerow({**{k:row[k] for k in fields[:4]}, **row['metrics']})
    anchor = next(r['manifest']['source'] for r in checks if r['manifest']['source']['backtest']['id'] == search.source_backtest_id)
    return dict(format_version=4, model_version=MODEL_VERSION, phase='evaluation', source=anchor,
        settings=dict(ANALYSIS_MODE='evaluation_optimization'), calculations=calculations,
        implementation=implementation_identity(), request=asdict(search),
        parity_status='Independent mathematical qualification only; no provider or external-engine numerical parity claimed')
