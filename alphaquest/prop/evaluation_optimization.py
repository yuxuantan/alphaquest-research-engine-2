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
    SimulationConfig, SourceCosts, SizingConfiguration, NativeExecution, positive_integer,
    verify_phase_source,
)

from .phase_search import PhaseCalendar as AcquisitionCalendar

MODEL_VERSION = 'evaluation-optimization-empirical-iid-v1'
CALENDAR_MODEL_VERSION = 'evaluation-optimization-profile-calendar-v3'


def model_version(search):
    return CALENDAR_MODEL_VERSION if search.native_execution is None and any(c.profile.profile_id=='lucidflex-50k' for c in search.candidates) else MODEL_VERSION


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
    sizing: SizingConfiguration | None = None

    def __post_init__(self):
        for name, cls in [('source', SavedTradeSource), ('simulation', SimulationConfig),
                          ('sampling', EvaluationSamplingConfig), ('costs', SourceCosts),
                          ('retry', SequentialRetry)]:
            if not isinstance(getattr(self, name), cls):
                raise ValueError(f'Evaluation candidate requires {cls.__name__} for {name}.')
        if self.period is not None and not isinstance(self.period, ResearchPeriod):
            raise ValueError('Evaluation candidate period must be a ResearchPeriod.')
        if self.sizing is not None and not isinstance(self.sizing, SizingConfiguration):
            raise ValueError('Evaluation sizing must be a SizingConfiguration.')
        id = self.source.source_backtest_id
        if not isinstance(id, str) or UUID(id).hex != id:
            raise ValueError('Saved source ID must be a lowercase UUID hex string.')
        if not isinstance(self.source.trade_file, str):
            raise ValueError('Explicit source trade_file must be a string.')
        if not isinstance(self.profile, EvaluationProfile):
            raise ValueError('Evaluation selection requires only an EvaluationProfile.')
        if self.sampling.computational_horizon_weekdays is not None:
            raise ValueError('Apex expiry is a provider event, not a configurable computational horizon.')


@dataclass(frozen=True)
class EvaluationConstraints:
    maximum_cost_per_funded: float | None = None
    maximum_expected_calendar_days: float | None = None
    minimum_pass_probability: float | None = None

    def __post_init__(self):
        for name in ('maximum_cost_per_funded', 'maximum_expected_calendar_days', 'minimum_pass_probability'):
            value = getattr(self, name)
            if value is not None and (type(value) not in (int, float) or not np.isfinite(value)
                    or value < 0 or (name == 'minimum_pass_probability' and value > 1)):
                raise ValueError(f'Invalid evaluation constraint {name}.')


@dataclass(frozen=True)
class EvaluationSearch:
    source_backtest_id: str
    candidates: tuple[EvaluationCandidate, ...]
    calendar: AcquisitionCalendar
    mode: str = 'evaluation_optimization'
    constraints: EvaluationConstraints | None = None
    native_execution: NativeExecution | None = None

    def __post_init__(self):
        if self.mode != 'evaluation_optimization':
            raise ValueError('Unsupported phase search mode.')
        if self.constraints is not None and type(self.constraints) is not EvaluationConstraints:
            raise ValueError('Evaluation constraints require an EvaluationConstraints contract.')
        if self.native_execution is not None and type(self.native_execution) is not NativeExecution:
            raise ValueError('Native Evaluation requires an explicit NativeExecution contract.')
        if not self.candidates:
            raise ValueError('Declare at least one candidate; no implicit search truncation.')
        if self.source_backtest_id not in {c.source.source_backtest_id for c in self.candidates}:
            raise ValueError('The navigation anchor must belong to the candidate set.')
        for c in self.candidates:
            if self.native_execution is None and c.profile.profile_id == 'lucidflex-50k':
                if c.simulation.simulations!=c.sampling.chain_simulations or c.simulation.seed!=c.sampling.chain_seed:
                    raise ValueError('Calendar Lucid acquisition uses one path count and seed; simulation and chain settings must match.')
                if c.sampling.computational_horizon_weekdays is not None:
                    raise ValueError('Calendar Lucid acquisition uses retry.max_calendar_days; a weekday guard cannot be silently substituted.')
            horizon = self.native_execution.horizon_calendar_days if self.native_execution is not None else c.retry.max_calendar_days
            if (date.fromisoformat(self.calendar.coverage_end) - max(map(date.fromisoformat, self.calendar.start_dates))).days < horizon:
                raise ValueError('Calendar coverage must include every chain guard date.')
            if self.native_execution is not None and not self.native_execution.prepared_execution:
                if c.simulation.simulations != c.sampling.chain_simulations or c.simulation.seed != c.sampling.chain_seed:
                    raise ValueError('Native Evaluation has one actual path sample: simulation and chain counts/seeds must agree.')
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
                              ('costs', SourceCosts), ('period', ResearchPeriod), ('retry', SequentialRetry),
                              ('sizing', SizingConfiguration)]:
                if item.get(name) is not None:
                    item[name] = cls(**item[name])
            candidates.append(EvaluationCandidate(**item))
        calendar = dict(value.pop('calendar'))
        for name in ('start_dates', 'closures'):
            if name in calendar: calendar[name] = tuple(sorted(calendar[name]))
        if value.get('constraints') is not None:
            value['constraints'] = EvaluationConstraints(**value['constraints'])
        if value.get('native_execution') is not None:
            value['native_execution'] = NativeExecution(**value['native_execution'])
        return EvaluationSearch(candidates=tuple(candidates), calendar=AcquisitionCalendar(**calendar), **value)
    except (TypeError, KeyError, AttributeError) as exc:
        raise ValueError(f'Invalid evaluation-only search contract: {exc}') from exc


def check_search(runs, search, *, training_context=None, datasets=None):
    from .phase_search import check_candidates
    return check_candidates(runs, search, training_context=training_context, datasets=datasets)


def implementation_identity():
    # Include local source changes, including adapters and numerical kernels.
    names = ('evaluation_optimization.py', 'evaluation_profiles.py', 'phase_profiles.py',
             'native_analysis.py', 'native_engine.py', 'native_backend.py',
             'lucid_engine.py', 'lucid_rules.py', 'lucid_backend.py', 'source.py', 'commissions.py',
             'phase_lifecycle.py', 'adapter.py', 'phase_search.py', 'sizing.py', 'sizing_runtime.py', 'saved_trade_simulation.py', 'path_parallel.py',
             'external_source.py', 'cash_ledger.py', 'rule_provenance.py', 'native_control.py', 'native_money.py',
             'native_draws.py', 'native_replay.py', 'native_search.py', 'native_preparation.py', 'native_market_hours.py', 'twin_preparation.py', '../risk_metrics.py', '../decimal_math.py', '../execution.py', '../execution_scenarios.py', '../decision_capture.py',
             '../tick_data.py', '../intratrade.py', '../session_calendar.py', '../strategies/vwap_pullback_risk_sizing.py', '../canonical_trades.py', '../trade_imports.py')
    from .native_analysis import kernel_identity
    return dict(files={name: digest(Path(__file__).parent/name) for name in names},
                kernel=kernel_identity({'ACCOUNT_TYPE': 'Apex EOD'}),
                lucid_kernel=kernel_identity({'ACCOUNT_TYPE': 'LucidFlex'}), numpy=np.__version__)


def search_key(search, checks):
    return sha256(canonical(dict(model=model_version(search), calendar=asdict(search.calendar),
        constraints=asdict(search.constraints) if search.constraints is not None else None,
        anchor=search.source_backtest_id,
        candidates=[{k:r[k] for k in ('candidate_id','prior_access','origin_trials')} for r in checks],
        implementation=implementation_identity())).encode()).hexdigest()


def _interval(values):
    se = float(np.std(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else None
    mean = float(np.mean(values))
    return dict(mean=mean, se=se, ci=None if se is None else [max(0., mean-1.96*se), mean+1.96*se])


def acquisition_metrics(component, profile, retry, calendar, sampling, *, preparation=None, summary_only=False, checkpoint=lambda:None):
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
    from .evaluation_profiles import DatedEvaluationPreparation
    from .native_backend import module
    preparation=preparation if preparation is not None else DatedEvaluationPreparation()
    paths,schedule_sha256=module().renewal_acquisition(outcomes,durations,fee,activation,retry,calendar,sampling,
        preparation=preparation,summary_only=summary_only,checkpoint=checkpoint)
    if summary_only:
        complete=bool(np.all(paths['completed']))
        if complete:
            times=paths['times'];groups=[times[np.arange(len(times))%len(calendar.start_dates)==i]
                for i,_ in enumerate(sorted(calendar.start_dates))]
            se=(float(np.sqrt(sum(np.var(g,ddof=1)/len(g) for g in groups))/len(groups))
                if all(len(g)>1 for g in groups) else None)
            metrics.update(cost_per_funded=float(fee*Decimal(n)/Decimal(passed)+activation),
                expected_calendar_days_to_funded=float(np.mean(times)))
            uncertainty.update(cost_se=float(fee)*np.sqrt(p*(1-p)/n)/p**2,calendar_mean_se=se)
        return dict(metrics=metrics,uncertainty=uncertainty,status='estimated' if complete else 'censored')
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
        uncertainty=uncertainty, schedule_sha256=schedule_sha256,
        censoring=dict(attempt_paths=censored, chain_paths=len(unresolved), chains_run=len(paths),
            mean_accrued_cost_lower_bound=float(np.mean([float(r['cost_accrued']) for r in paths])),
            mean_observed_days_lower_bound=float(np.mean(times)),
            restricted_mean_at_guard=float(np.mean(times)) if not any(r['event']=='attempt_guard' for r in paths) else None))


def apply_constraints(rows, constraints):
    """Evaluate declared limits before nondominance, retaining every row."""
    for row in rows:
        reasons = []
        for metric, limit, maximum in (
            ('cost_per_funded', constraints.maximum_cost_per_funded, True),
            ('expected_calendar_days_to_funded', constraints.maximum_expected_calendar_days, True),
            ('pass_probability', constraints.minimum_pass_probability, False)):
            value = row['metrics'].get(metric)
            if limit is not None and (value is None or not np.isfinite(value)
                    or (value > limit if maximum else value < limit)):
                reasons.append(metric)
        row.update(feasible=row['status'] == 'estimated' and not reasons, constraint_violations=reasons)


def pareto_sort(rows, constraints=None):
    """Strict two-objective nondominance; exact ties retain full membership."""
    rows = sorted(rows, key=lambda r: r['candidate_id'])
    def point(row):
        return row['metrics']['cost_per_funded'], row['metrics']['expected_calendar_days_to_funded']
    numerical = [r for r in rows if r['status'] == 'estimated' and all(x is not None and np.isfinite(x) for x in point(r))]
    unresolved = [r['candidate_id'] for r in rows if r not in numerical]
    if constraints is not None:
        apply_constraints(rows, constraints)
    resolved = [r for r in numerical if constraints is None or r['feasible']]
    for row in rows:
        dominated_by = []
        if row in resolved:
            c, t = point(row)
            dominated_by = [r['candidate_id'] for r in resolved if point(r)[0] <= c and point(r)[1] <= t and point(r) != (c,t)]
        row.update(pareto_member=row in resolved and not dominated_by,
            dominated=bool(dominated_by) if row in resolved else None,
            estimated_dominated_by=dominated_by, robust_dominated=None,
            pareto_rank=None,
            dominance_status='estimated_only' if row in resolved else 'constraint_excluded' if row in numerical else 'unresolved_not_excluded')
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


def paired_precision(rows):
    """Conditional paired MC diagnostics; never change point-estimate membership."""
    from itertools import combinations
    from statistics import NormalDist
    comparisons=[]
    pairs=list(combinations(rows,2))
    z=NormalDist().inv_cdf(1-.05/(2*max(1,len(pairs))*2))
    for row in rows:
        row['funding_time_near_ties']=[]
        se=row['uncertainty'].get('calendar_mean_se');mean=row['metrics'].get('expected_calendar_days_to_funded')
        if se is not None and mean is not None:
            row['uncertainty']['calendar_mean_ci']=[max(0.,mean-1.96*se),mean+1.96*se]
            row['uncertainty']['calendar_interval_scope']='Nominal 95% conditional MC interval; not future uncertainty or a frontier certificate.'
    for a,b in pairs:
        pa,pb=a.get('paths',[]),b.get('paths',[])
        if a['status']!='estimated' or b['status']!='estimated' or len(pa)<2 or len(pa)!=len(pb):continue
        if [(p['path'],p['start_date']) for p in pa]!=[(p['path'],p['start_date']) for p in pb]:continue
        data={}
        for key in ('time','cost'):
            def value(p):return p.get('calendar_days_to_funded',p.get('observed_calendar_days')) if key=='time' else float(p.get('paid_fees',p.get('cost_accrued')))
            groups=[]
            for start in sorted({p['start_date'] for p in pa}):
                groups.append(np.array([value(x)-value(y) for x,y in zip(pa,pb) if x['start_date']==start]))
            if any(len(g)<2 for g in groups):break
            mean=float(np.mean([g.mean() for g in groups]));se=float(np.sqrt(sum(g.var(ddof=1)/len(g) for g in groups))/len(groups))
            data[key]=dict(mean_difference=mean,mc_standard_error=se,family_95_interval=[mean-z*se,mean+z*se])
        if len(data)!=2:continue
        interval=data['time']['family_95_interval'];near=interval[0]<=0<=interval[1]
        comparisons.append(dict(candidate_a=a['candidate_id'],candidate_b=b['candidate_id'],**data,funding_time_difference_unresolved=near))
        if near:
            a['funding_time_near_ties'].append(b['candidate_id']);b['funding_time_near_ties'].append(a['candidate_id'])
    return dict(paired_comparisons=comparisons,precision_interpretation=
        'Differences are A minus B, paired by saved path and start cohort. Normal approximate Bonferroni 95% intervals cover declared pairs and both objectives. '
        'Conditional simulation error only; no future/provider certification. Near ties mean a funding-time interval includes zero; costs can differ. Point-estimate Pareto membership is unchanged.')


def optimize_evaluation(runs, search, checks=None, progress=lambda message: None, *, assessment=False, training_context=None, datasets=None, checkpoint=lambda:None, reserve_child=None):
    if assessment and training_context is not None:
        raise ValueError('Assessment cannot consume a training context.')
    if search.native_execution is not None:
        return optimize_native_evaluation(datasets,runs,search,checks,progress,
            assessment=assessment,training_context=training_context,checkpoint=checkpoint,reserve_child=reserve_child)
    if isinstance(assessment,dict) and assessment.get('kind'):
        return assess_saved_evaluation(runs,search,checks,assessment,progress,checkpoint)
    if training_context is not None:
        current = check_search(runs, search, training_context=training_context)
        if checks is not None and canonical(current) != canonical(checks):
            raise ValueError('Nested training sources changed after checking.')
        checks = current
    checks = checks if checks is not None else check_search(runs, search)
    configurations = {canonical(asdict(c)): c for c in search.candidates}
    from .path_parallel import available,run_candidates
    # Apex's legacy attempt sampler shares a serial MT19937 stream across paths.
    # Parallelize independent sizes instead, retaining the original RNG law.
    parallel_rows=(run_candidates(runs,search,checks,training_context,checkpoint,progress)
        if available() and len(checks)>1 and all(c.profile.profile_id=='apex-50k-eod' for c in search.candidates) else None)
    rows = parallel_rows or []
    for check in ([] if parallel_rows is not None else checks):
        candidate = configurations[canonical(check['manifest']['configuration'])]
        progress(f'Completed {len(rows)} / {len(checks)} candidates · Evaluating '+check['candidate_id'][:12])
        if candidate.profile.profile_id=='lucidflex-50k':
            from .evaluation_profiles import simulate_calendar_evaluation_profile
            result=simulate_calendar_evaluation_profile(runs,candidate,search.calendar,
                observed_sessions=training_context['train_window']['sessions'] if training_context else None,
                checkpoint=checkpoint,progress=progress)
            if canonical(result['component']['provenance']['source'])!=canonical(check['manifest']['source']):
                raise ValueError('Candidate source changed after source checking.')
            rows.append(dict(candidate_id=check['candidate_id'],**result,manifest=check['manifest'],origin_trials=check['origin_trials']))
        else:
            component = simulate_evaluation_profile(runs, candidate.source, candidate.profile,
                candidate.micros, candidate.simulation, candidate.period, candidate.sampling, candidate.costs,
                **({'sizing':candidate.sizing} if candidate.sizing is not None else {}),
                **({'observed_sessions':training_context['train_window']['sessions']} if training_context is not None else {}),checkpoint=checkpoint,progress=progress)
            if canonical(component.provenance['source']) != canonical(check['manifest']['source']):
                raise ValueError('Candidate source changed after source checking.')
            result = acquisition_metrics(component, candidate.profile, candidate.retry, search.calendar, candidate.sampling)
            rows.append(dict(candidate_id=check['candidate_id'], **result,
                component=asdict(component), manifest=check['manifest'], origin_trials=check['origin_trials']))
    from .saved_trade_simulation import describe_results
    describe_results(rows)
    # Recheck all sources at the publication boundary, including earlier candidates.
    for check in checks:
        c = configurations[canonical(check['manifest']['configuration'])]
        verify_phase_source(runs, c.source, check['manifest']['source'])
    if assessment:
        if search.constraints is not None:
            apply_constraints(rows, search.constraints)
        for row in rows:
            row.update(pareto_member=False, dominated=None, pareto_rank=None)
        return dict(model_version=model_version(search), phase='evaluation', candidates=rows,
            frontier=[], marginal_acceleration_cost=[], winner=None, certified_frontier=False,
            selection_status='assessment_only_no_reselection',
            unresolved_candidates=[r['candidate_id'] for r in rows if r['status'] != 'estimated'])
    precision=paired_precision(rows)
    return dict(model_version=model_version(search), phase='evaluation', **pareto_sort(rows, search.constraints),**precision)


def assess_saved_evaluation(runs,search,checks,assessment,progress,checkpoint):
    """Assess frozen sizes only, with OOS MC + chronology or declared IS sensitivity."""
    from dataclasses import replace
    from datetime import timedelta
    from .phase_profiles import assessment_scenarios,prepare_phase_source
    from .evaluation_profiles import simulate_calendar_evaluation_profile,calendar_evaluation_paths
    from .phase_search import check_candidates
    current=check_candidates(runs,search,assessment)
    if checks is not None and canonical(checks)!=canonical(current):raise ValueError('Frozen assessment inputs changed.')
    configurations={canonical(asdict(c)):c for c in search.candidates};rows=[]
    for check in current:
        c=configurations[canonical(check['manifest']['configuration'])]
        for label,scenario in assessment_scenarios(c,assessment):
            checkpoint();progress(f"{assessment['kind']} · {c.micros} MNQ · {label}")
            if c.profile.profile_id=='lucidflex-50k':
                result=simulate_calendar_evaluation_profile(runs,scenario,search.calendar,checkpoint=checkpoint,progress=progress)
            else:
                component=simulate_evaluation_profile(runs,scenario.source,scenario.profile,scenario.micros,
                    scenario.simulation,scenario.period,scenario.sampling,scenario.costs,scenario.sizing,checkpoint=checkpoint,progress=progress)
                result=acquisition_metrics(component,scenario.profile,scenario.retry,search.calendar,scenario.sampling)
                result['component']=asdict(component)
            row=dict(candidate_id=check['candidate_id'],frozen_candidate_id=check['frozen_candidate_id'],scenario=label,
                configuration=asdict(scenario),**result,manifest=check['manifest'],origin_trials=check['origin_trials'],
                pareto_member=False,dominated=None,pareto_rank=None)
            if assessment['kind']=='oos':
                snapshot,days,_=prepare_phase_source(runs,c.source,c.profile,c.micros,c.simulation,c.period,c.costs,c.sizing)
                first=date.fromisoformat(c.period.first_session);last=date.fromisoformat(c.period.last_session)
                calendar=AcquisitionCalendar((str(first),),str(last+timedelta(days=c.retry.max_calendar_days+2)),())
                paths,_=calendar_evaluation_paths(days,c.profile,c.micros,c.simulation,c.sampling,
                    replace(c.retry,max_calendar_days=(last-first).days+1),calendar,chronological=True,checkpoint=checkpoint,sizing=c.sizing)
                row['chronological_replay']=dict(paths[0],interpretation='One chronological OOS saved-signal scenario; no resampling or reselection. Window-censored acquisition has no finite funding-time estimate.')
                base=assessment['is_metrics'][check['frozen_candidate_id']]
                row['is_comparison']={key:dict(is_value=base.get(key),oos_value=row['metrics'].get(key),
                    oos_over_is=(row['metrics'][key]/base[key] if base.get(key) and row['metrics'].get(key) is not None else None))
                    for key in ('cost_per_funded','expected_calendar_days_to_funded','pass_probability')}
            rows.append(row)
        verify_phase_source(runs,c.source,check['manifest']['source'])
    from .saved_trade_simulation import describe_results
    describe_results(rows)
    precision=paired_precision(rows) if assessment['kind']!='is_robustness' else {}
    return dict(model_version=model_version(search),phase='evaluation',candidates=rows,frontier=[],winner=None,
        marginal_acceleration_cost=[],certified_frontier=False,selection_status='assessment_only_no_reselection',
        assessment_kind=assessment['kind'],unresolved_candidates=[r['candidate_id'] for r in rows if r['status']!='estimated'],**precision)


def optimize_native_evaluation(datasets,runs,search,checks,progress,*,assessment=False,training_context=None,checkpoint=lambda:None,reserve_child=None):
    from .native_search import prepare_native_candidate,verify_native_candidate
    from .evaluation_profiles import forecast_native_evaluation,native_acquisition_metrics
    if assessment:
        return assess_native_evaluation(datasets,runs,search,checks,assessment,progress,checkpoint,reserve_child)
    current=check_search(runs,search,datasets=datasets,training_context=training_context)
    if checks is not None and canonical(checks)!=canonical(current):raise ValueError('Native candidate membership changed.')
    checks=current;rows=[];prepared_cache={}
    configurations={canonical(asdict(candidate)):candidate for candidate in search.candidates}
    for check in checks:
        candidate=configurations[canonical(check['manifest']['configuration'])]
        progress(f'Native Evaluation candidate {len(rows)+1}/{len(checks)}')
        inputs,plan=prepare_native_candidate(datasets,runs,search,candidate,check,private_admission=training_context is not None,checkpoint=checkpoint,cache=prepared_cache,progress=progress)
        forecast=forecast_native_evaluation(**inputs,retry=candidate.retry,progress=progress,checkpoint=checkpoint,chain_sampling=candidate.sampling)
        if not search.native_execution.prepared_execution and canonical(forecast['schedules'])!=canonical(plan['schedules']):raise ValueError('Native candidate schedule changed.')
        provenance=dict(source=check['manifest']['source'],rules=forecast['captures'][0]['result']['modeled_rules'],
            native_execution=asdict(search.native_execution))
        rows.append({**native_acquisition_metrics(forecast),'candidate_id':check['candidate_id'],
            'native_forecast':forecast,'manifest':check['manifest'],'origin_trials':check['origin_trials'],
            'native_schedule_sha256':plan['plan_sha256'],'provenance':provenance,'component':dict(provenance=provenance)})
    if search.native_execution.prepared_execution:
        from .native_preparation import quantity_summary
        for row in rows:row['quantity_summary']=quantity_summary(row['native_forecast'])
    progress('Verifying saved source and preparing durable results')
    for check in checks:
        candidate=configurations[canonical(check['manifest']['configuration'])]
        verify_native_candidate(datasets,runs,search,candidate,check,private_admission=training_context is not None,cache=prepared_cache)
    return dict(model_version=('independent-native-percentage-v2' if search.native_execution is not None and search.native_execution.prepared_execution else MODEL_VERSION),phase='evaluation',execution_model=search.native_execution.model,
        **pareto_sort(rows,search.constraints))


def assess_native_evaluation(datasets,runs,search,checks,assessment,progress,checkpoint,reserve_child):
    if search.native_execution.prepared_execution:
        from .native_search import assess_prepared_candidates
        return assess_prepared_candidates(datasets,runs,search,checks,assessment,progress,checkpoint,reserve_child)
    from .phase_search import check_candidates
    from .native_search import execute_native_assessment
    current=check_candidates(runs,search,assessment,datasets=datasets)
    if checks is not None and canonical(checks)!=canonical(current):raise ValueError('Frozen native assessment sources changed.')
    configurations={canonical(asdict(c)):c for c in search.candidates};rows=[]
    for check in current:
        c=configurations[canonical(check['manifest']['configuration'])]
        execution=execute_native_assessment(datasets,runs,search,c,check,assessment,
            reserve_child=reserve_child,checkpoint=checkpoint,progress=progress)
        actual=execution['native_chronological_replay']
        rows.append(dict(candidate_id=check['candidate_id'],frozen_candidate_id=check['frozen_candidate_id'],
            **execution,manifest=check['manifest'],origin_trials=check['origin_trials'],
            status='historical_observation',metrics=dict(observed_paid_fees=actual['paid_fees'],
                observed_calendar_days_to_funded=actual['calendar_days_to_funded'],acquisition_completed=actual['acquisition_completed']),
            uncertainty=dict(interpretation='One observed chronological scenario; no Monte Carlo or expected-mean estimate.'),
            censoring=dict(censored=actual['censored'],outcome=actual['outcome']),assumptions=actual['assumptions'],
            pareto_member=False,dominated=None,pareto_rank=None,feasible=None,constraint_violations=[],
            component=dict(provenance=dict(source=check['manifest']['source'],sizing=actual['sizing']))))
    return dict(model_version=('independent-native-percentage-v2' if search.native_execution is not None and search.native_execution.prepared_execution else MODEL_VERSION),phase='evaluation',candidates=rows,frontier=[],
        marginal_acceleration_cost=[],winner=None,certified_frontier=False,
        selection_status='assessment_only_no_reselection',unresolved_candidates=[],
        execution_model='native_actual_chronological_frozen_oos')


def write_report(runs, staged, search, checks, calculations):
    """Capture inputs once and publish through the normal AnalysisStore files."""
    import csv
    staged = Path(staged)
    def save(name, data):
        (staged/name).write_text(canonical(data), encoding='utf-8')
    from .phase_search import capture_inputs, write_sizing_artifacts
    from .rule_provenance import search_review, readiness
    provider_rules = search_review(search)
    save('provider_rules.json', provider_rules)
    capture_inputs(runs, staged, search, calculations)
    from .native_search import write_native_artifacts
    write_native_artifacts(runs,staged,calculations)
    write_sizing_artifacts(staged, calculations)
    save('source_checks.json', checks)
    save('phase_candidates.json', [dict(candidate_id=r['candidate_id'], origin_trials=r['origin_trials'],
        **r['manifest']) for r in calculations['candidates']])
    save('phase_metrics.json', [dict(candidate_id=r['candidate_id'], metrics=r['metrics'], status=r['status'],
        uncertainty=r['uncertainty'], censoring=r['censoring'], assumptions=r['assumptions'],
        pareto_member=r['pareto_member'], dominated=r['dominated'], pareto_rank=r['pareto_rank'],
        **({k:r[k] for k in ('feasible','constraint_violations')} if 'feasible' in r else {})) for r in calculations['candidates']])
    save('frontier.json', {k:v for k,v in calculations.items() if k != 'candidates'})
    save('calculations.json', calculations)
    save('request.json', asdict(search))
    save('sampling.json', [dict(candidate_id=r['candidate_id'], scenario=r.get('scenario'),configuration=r.get('configuration',r['manifest']['configuration'])['sampling'],
        schedule_sha256=r.get('schedule_sha256'), uncertainty=r['uncertainty']) for r in calculations['candidates']])
    with (staged/'phase_metrics.csv').open('w', newline='') as stream:
        fields = ['candidate_id', 'status', 'pareto_member', 'dominated', *calculations['candidates'][0]['metrics']]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore'); writer.writeheader()
        for row in calculations['candidates']:
            writer.writerow({**{k:row[k] for k in fields[:4]}, **row['metrics']})
    anchor = next(r['manifest']['source'] for r in checks if r['manifest']['source']['backtest']['id'] == search.source_backtest_id)
    return dict(format_version=4, model_version=calculations['model_version'], phase='evaluation', source=anchor,
        settings=dict(ANALYSIS_MODE='evaluation_optimization'), calculations=calculations,
        implementation=implementation_identity(), request=asdict(search),
        provider_rules=provider_rules, deployment_readiness=readiness(provider_rules),
        parity_status='Independent mathematical qualification only; no provider or external-engine numerical parity claimed')
