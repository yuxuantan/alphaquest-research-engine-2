"""Independent saved-IS funded search, maximizing finite-horizon cash receipts."""
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from statistics import NormalDist
from uuid import UUID

import numpy as np

from .adapter import canonical, digest
from .funded_profiles import simulate_dated_funded_profile
from .phase_profiles import (FundedProfile, ResearchPeriod, SamplingConfig, SavedTradeSource,
    SimulationConfig, SourceCosts, SizingConfiguration, positive_integer, verify_phase_source)
from .phase_search import PhaseCalendar, check_candidates

MODEL_VERSION = 'funded-optimization-calendar-receipts-v1'
OBJECTIVE = 'expected_funded_cash_payouts_within_horizon'
DEFAULT_RESEARCH_HORIZONS = (90, 180, 365)


@dataclass(frozen=True)
class FundedCandidate:
    source: SavedTradeSource
    profile: FundedProfile
    micros: int
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    sampling: SamplingConfig = field(default_factory=SamplingConfig)
    costs: SourceCosts = field(default_factory=SourceCosts)
    period: ResearchPeriod | None = None
    sizing: SizingConfiguration | None = None

    def __post_init__(self):
        for name, cls in [('source', SavedTradeSource), ('profile', FundedProfile),
                          ('simulation', SimulationConfig), ('sampling', SamplingConfig), ('costs', SourceCosts)]:
            if type(getattr(self, name)) is not cls:
                raise ValueError(f'Funded candidate requires {cls.__name__} for {name}.')
        if self.period is not None and type(self.period) is not ResearchPeriod:
            raise ValueError('Funded period must be a ResearchPeriod.')
        if self.sizing is not None and type(self.sizing) is not SizingConfiguration:
            raise ValueError('Funded sizing must be a SizingConfiguration.')
        id = self.source.source_backtest_id
        if not isinstance(id, str) or UUID(id).hex != id:
            raise ValueError('Source ID must be a lowercase UUID hex string.')
        if not isinstance(self.source.trade_file, str):
            raise ValueError('Explicit source trade_file must be a string.')
        positive_integer('micros', self.micros, 40)


@dataclass(frozen=True)
class FundedConstraints:
    maximum_account_breach_probability: float | None = None
    minimum_probability_first_payout: float | None = None
    minimum_p10_payouts: float | None = None
    maximum_position_size: int | None = None

    def __post_init__(self):
        for name in ('maximum_account_breach_probability', 'minimum_probability_first_payout', 'minimum_p10_payouts'):
            value = getattr(self, name)
            if value is not None and (type(value) not in (int, float) or not np.isfinite(value) or value < 0
                    or (name != 'minimum_p10_payouts' and value > 1)):
                raise ValueError(f'Invalid funded constraint {name}.')
        if self.maximum_position_size is not None:
            positive_integer('maximum_position_size', self.maximum_position_size, 40)


@dataclass(frozen=True)
class FundedSearch:
    source_backtest_id: str
    candidates: tuple[FundedCandidate, ...]
    calendar: PhaseCalendar
    horizon_calendar_days: int
    receipt_delay_calendar_days: int  # Explicit even for same-date receipt.
    constraints: FundedConstraints = field(default_factory=FundedConstraints)
    bootstrap_replicates: int = 400
    bootstrap_seed: int = 137
    near_tie_cash: float = 0.
    mode: str = 'funded_optimization'

    def __post_init__(self):
        if self.mode != 'funded_optimization' or type(self.calendar) is not PhaseCalendar or type(self.constraints) is not FundedConstraints:
            raise ValueError('Invalid funded-only search contract.')
        if type(self.candidates) is not tuple or not self.candidates or any(type(c) is not FundedCandidate for c in self.candidates):
            raise ValueError('Declare a nonempty immutable set of funded candidates.')
        if self.source_backtest_id not in {c.source.source_backtest_id for c in self.candidates}:
            raise ValueError('Navigation anchor must belong to the candidate set.')
        positive_integer('horizon_calendar_days', self.horizon_calendar_days, 3650)
        if type(self.receipt_delay_calendar_days) is not int or not 0 <= self.receipt_delay_calendar_days <= 365:
            raise ValueError('Receipt delay must be 0–365 calendar days.')
        positive_integer('bootstrap_replicates', self.bootstrap_replicates, 2000)
        if self.bootstrap_replicates < 100:
            raise ValueError('Use at least 100 declared bootstrap replicates.')
        SimulationConfig(seed=self.bootstrap_seed)
        if type(self.near_tie_cash) not in (float, int) or not np.isfinite(self.near_tie_cash) or self.near_tie_cash < 0:
            raise ValueError('near_tie_cash must be finite and nonnegative.')
        for c in self.candidates:
            if c.simulation.simulations % len(self.calendar.start_dates):
                raise ValueError('Simulation count must be divisible by start cohort size.')
        if max(map(date.fromisoformat, self.calendar.start_dates))+timedelta(days=self.horizon_calendar_days) > date.fromisoformat(self.calendar.coverage_end):
            raise ValueError('Calendar must cover every horizon cutoff.')


def parse_request(raw):
    try:
        value = dict(raw)
        candidates = []
        for item in value.pop('candidates'):
            item = dict(item)
            for name, cls in [('source', SavedTradeSource), ('profile', FundedProfile),
                              ('simulation', SimulationConfig), ('sampling', SamplingConfig),
                              ('costs', SourceCosts), ('period', ResearchPeriod), ('sizing', SizingConfiguration)]:
                if item.get(name) is not None: item[name] = cls(**item[name])
            candidates.append(FundedCandidate(**item))
        calendar = dict(value.pop('calendar'))
        for name in ('start_dates', 'closures'):
            if name in calendar: calendar[name] = tuple(sorted(calendar[name]))
        if 'constraints' in value: value['constraints'] = FundedConstraints(**value['constraints'])
        return FundedSearch(candidates=tuple(candidates), calendar=PhaseCalendar(**calendar), **value)
    except (TypeError, KeyError, AttributeError) as exc:
        raise ValueError(f'Invalid funded-only search contract: {exc}') from exc


def check_search(runs, search, *, training_context=None):
    return check_candidates(runs, search, training_context=training_context)


def implementation_identity():
    names = ('funded_optimization.py', 'funded_profiles.py', 'phase_profiles.py', 'phase_search.py',
        'native_analysis.py', 'native_engine.py', 'lucid_engine.py', 'lucid_rules.py', 'source.py',
        'commissions.py', 'phase_lifecycle.py', 'adapter.py', 'sizing.py', 'sizing_runtime.py',
        'external_source.py', 'cash_ledger.py', 'rule_provenance.py', '../canonical_trades.py', '../trade_imports.py')
    return dict(files={name: digest(Path(__file__).parent/name) for name in names},
                kernel='native Python reference account transitions', numpy=np.__version__)


def search_key(search, checks):
    config = asdict(search)
    config.pop('candidates')
    return sha256(canonical(dict(model=MODEL_VERSION, configuration=config,
        candidates=[{k:r[k] for k in ('candidate_id','prior_access','origin_trials')} for r in checks],
        implementation=implementation_identity())).encode()).hexdigest()


def funded_metrics(paths, search):
    """All-start receipts and censored lifetime; never use survivor-only cash."""
    from .native_analysis import wilson
    cash = np.array([p['cash_received'] for p in paths], dtype=float)
    n = len(paths)
    incomplete = sum(not p['horizon_observations_complete'] or p['unresolved'] for p in paths)
    open_count = sum(p['lifetime_censored'] for p in paths)
    first = [p['days_to_first_payout'] for p in paths if p['days_to_first_payout'] is not None]
    mean = float(cash.mean())
    quantiles = np.quantile(cash, [.1,.5,.9], method='inverted_cdf').tolist()
    metrics = dict(expected_funded_cash_payouts_within_horizon=None if incomplete else mean,
        expected_payouts=None if incomplete else mean, median_payouts=None if incomplete else quantiles[1],
        p10_payouts=None if incomplete else quantiles[0], p90_payouts=None if incomplete else quantiles[2],
        probability_first_payout=None if incomplete else len(first)/n,
        expected_days_to_first_payout_conditional_on_payout=float(np.mean(first)) if first and not incomplete else None,
        probability_zero_payout=None if incomplete else float(np.mean(cash == 0)),
        account_breach_probability=None if incomplete else sum(p['outcome']=='blown' for p in paths)/n,
        expected_account_lifetime=None if open_count or incomplete else float(np.mean([p['observed_calendar_days'] for p in paths])),
        restricted_mean_account_lifetime_calendar_days=float(np.mean([p['observed_calendar_days'] for p in paths])),
        probability_surviving_to_horizon=None if incomplete else open_count/n,
        expected_number_of_payouts=None if incomplete else float(np.mean([p['number_of_payouts'] for p in paths])),
        expected_pending_cash=float(np.mean([p['pending_cash'] for p in paths])),
        expected_gross_account_deductions=float(np.mean([p['gross_account_deductions'] for p in paths])),
        probability_inactivity=None if incomplete else sum(p['outcome']=='inactive' for p in paths)/n,
        probability_payout_limit_completion=None if incomplete else sum(p['outcome']=='paid_all' for p in paths)/n)
    groups = [cash[[p['start_date']==start for p in paths]] for start in sorted(search.calendar.start_dates)]
    se = float(np.sqrt(sum(np.var(g,ddof=1)/len(g) for g in groups))/len(groups)) if all(len(g)>1 for g in groups) and not incomplete else None
    z = NormalDist().inv_cdf(1-.05/(2*len(search.candidates)))
    interval = None if se is None else [max(0.,mean-z*se),mean+z*se]
    rng = np.random.default_rng(search.bootstrap_seed)
    boot = []
    if se is not None:
        for _ in range(search.bootstrap_replicates):
            draw = np.concatenate([rng.choice(g, len(g), replace=True) for g in groups])
            boot.append([float(draw.mean()), *np.quantile(draw,[.1,.5,.9],method='inverted_cdf').tolist()])
    bootstrap = dict(zip(('mean','p10','median','p90'),np.quantile(boot,[.025,.975],axis=0).T.tolist())) if boot else None
    probabilities = {}
    if len(groups)==1 and not incomplete:
        for key, count in [('probability_first_payout',len(first)), ('probability_zero_payout',int(sum(cash==0))),
                           ('account_breach_probability',sum(p['outcome']=='blown' for p in paths)),
                           ('probability_surviving_to_horizon',open_count)]:
            probabilities[key] = wilson(count,n)
    return dict(metrics=metrics, status='unresolved' if incomplete else 'estimated',
        censoring=dict(lifetime_censored_paths=open_count, unresolved_horizon_paths=incomplete,
            cash_observations_complete=not incomplete, mean_accrued_cash_lower_bound=mean,
            cash_upper_bound=None, reason='Open accounts are right-censored for total lifetime only; complete horizon cash is observed.' if open_count else None),
        uncertainty=dict(mean_monte_carlo_se=se, mean_family_interval=interval,
            bootstrap_nominal_95_intervals=bootstrap, probability_nominal_95_intervals=probabilities,
            method='Fixed equal start-date strata; whole-path bootstrap and within-stratum mean SE; normal Bonferroni mean intervals across all declared candidates',
            limitations='Conditional Monte Carlo error only; normal/bootstrap approximations may fail for rare or unobserved events. No paired inference, future uncertainty, or precision-qualified optimum. Risk constraints use empirical estimates; intervals do not certify provider risk.'),
        distribution=dict(values=cash.tolist(), quantiles='inverse empirical CDF', includes_zero_paths=True))


def apply_constraints(rows, search):
    c = search.constraints
    for row in rows:
        m = row['metrics']; violations = []
        for name, limit, observed, maximum in [
            ('maximum_account_breach_probability',c.maximum_account_breach_probability,m['account_breach_probability'],True),
            ('minimum_probability_first_payout',c.minimum_probability_first_payout,m['probability_first_payout'],False),
            ('minimum_p10_payouts',c.minimum_p10_payouts,m['p10_payouts'],False),
            ('maximum_position_size',c.maximum_position_size,row['manifest']['configuration']['micros'],True)]:
            if limit is not None and (observed is None or (observed > limit if maximum else observed < limit)):
                violations.append(name)
        row.update(constraint_violations=violations, feasible=not violations and row['status']=='estimated', rank=None)


def rank_candidates(rows, search, *, tie_key=None):
    apply_constraints(rows, search)
    ranked = sorted([r for r in rows if r['feasible']],
        key=lambda r:(-r['metrics'][OBJECTIVE], tie_key(r) if tie_key else r['candidate_id'], r['candidate_id']))
    for rank,row in enumerate(ranked,1): row['rank'] = rank
    unresolved = [r['candidate_id'] for r in rows if r['status']!='estimated']
    winner = ranked[0] if ranked and not unresolved else None
    near = []
    if winner:
        for row in ranked[1:]:
            a,b = winner['uncertainty']['mean_family_interval'],row['uncertainty']['mean_family_interval']
            if winner['metrics'][OBJECTIVE]-row['metrics'][OBJECTIVE] <= search.near_tie_cash or a is None or b is None or b[1]>=a[0]:
                near.append(row['candidate_id'])
    return dict(candidates=sorted(rows,key=lambda r:r['candidate_id']), ranking=[r['candidate_id'] for r in ranked],
        winner=winner['candidate_id'] if winner else None, near_ties=near, unresolved_candidates=unresolved,
        objective=OBJECTIVE, certified_optimum=False,
        selection_status='estimated_only' if winner else ('unresolved' if unresolved else 'no_feasible_candidate'),
        tie_breaking=('Descending expected received cash, then phase-only configuration SHA-256; generated IDs break identical-configuration presentation ties only'
            if tie_key else 'Descending expected received cash, then ascending candidate SHA-256; no evaluation inputs'),
        near_tie_definition='Within declared cash tolerance or overlapping family mean intervals; missing intervals also mark uncertainty')


def optimize_funded(runs, search, checks=None, progress=lambda message: None, *, assessment=False, training_context=None):
    if assessment and training_context is not None:
        raise ValueError('Assessment cannot consume a training context.')
    if training_context is not None:
        current = check_search(runs, search, training_context=training_context)
        if checks is not None and canonical(current) != canonical(checks):
            raise ValueError('Nested training sources changed after checking.')
        checks = current
    checks = checks if checks is not None else check_search(runs,search)
    configurations = {canonical(asdict(c)):c for c in search.candidates}
    rows = []
    for check in checks:
        c = configurations[canonical(check['manifest']['configuration'])]
        progress(f'Completed {len(rows)} / {len(checks)} candidates · Simulating funded candidate '+check['candidate_id'][:12])
        component = simulate_dated_funded_profile(runs,c.source,c.profile,c.micros,search.horizon_calendar_days,
            search.calendar,search.receipt_delay_calendar_days,c.simulation,c.period,c.sampling,c.costs,
            **({'sizing':c.sizing} if c.sizing is not None else {}),
            **({'observed_sessions':training_context['train_window']['sessions']} if training_context is not None else {}))
        if canonical(component['provenance']['source']) != canonical(check['manifest']['source']):
            raise ValueError('Candidate source changed after source checking.')
        rows.append(dict(candidate_id=check['candidate_id'], **funded_metrics(component['paths'],search),
            paths=component['paths'], schedule_sha256=component['schedule_sha256'], provenance=component['provenance'],
            manifest=check['manifest'], origin_trials=check['origin_trials']))
    for check in checks:
        c = configurations[canonical(check['manifest']['configuration'])]
        verify_phase_source(runs,c.source,check['manifest']['source'])
    if assessment:
        # Compute individual constraint status, never compare or choose OOS rows.
        apply_constraints(rows, search)
        return dict(model_version=MODEL_VERSION, phase='funded', candidates=rows,
            ranking=[], winner=None, near_ties=[], certified_optimum=False,
            selection_status='assessment_only_no_reselection', objective=OBJECTIVE,
            unresolved_candidates=[r['candidate_id'] for r in rows if r['status'] != 'estimated'])
    from .phase_search import stable_phase_policy_identity
    tie_key = (lambda row: stable_phase_policy_identity(row, 'funded')) if training_context is not None else None
    return dict(model_version=MODEL_VERSION,phase='funded',**rank_candidates(rows,search,tie_key=tie_key))


def write_report(runs, staged, search, checks, calculations):
    import csv
    from .phase_search import capture_inputs, write_sizing_artifacts
    staged = Path(staged)
    capture_inputs(runs, staged, search, calculations)
    write_sizing_artifacts(staged, calculations)
    def save(name,data): (staged/name).write_text(canonical(data),encoding='utf-8')
    from .rule_provenance import search_review, readiness
    provider_rules = search_review(search)
    save('provider_rules.json', provider_rules)
    save('source_checks.json',checks)
    save('phase_candidates.json',[dict(candidate_id=r['candidate_id'], origin_trials=r['origin_trials'],**r['manifest']) for r in calculations['candidates']])
    save('phase_metrics.json',[{k:r[k] for k in ('candidate_id','metrics','status','censoring','uncertainty','feasible','constraint_violations','rank')} for r in calculations['candidates']])
    save('ranking.json',{k:v for k,v in calculations.items() if k!='candidates'})
    save('calculations.json',calculations)
    save('request.json',asdict(search))
    save('sampling.json',[dict(candidate_id=r['candidate_id'],configuration=r['manifest']['configuration']['sampling'],
        simulation=r['manifest']['configuration']['simulation'],schedule_sha256=r['schedule_sha256'],
        calendar=asdict(search.calendar),bootstrap_seed=search.bootstrap_seed,bootstrap_replicates=search.bootstrap_replicates) for r in calculations['candidates']])
    with (staged/'phase_metrics.csv').open('w',newline='') as stream:
        fields = ['candidate_id','status','feasible','rank',*calculations['candidates'][0]['metrics']]
        writer = csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in calculations['candidates']: writer.writerow({**{k:row[k] for k in fields[:4]},**row['metrics']})
    anchor = next(r['manifest']['source'] for r in checks if r['manifest']['source']['backtest']['id']==search.source_backtest_id)
    return dict(format_version=5,model_version=MODEL_VERSION,phase='funded',source=anchor,
        settings=dict(ANALYSIS_MODE='funded_optimization'),calculations=calculations,implementation=implementation_identity(),
        request=asdict(search),provider_rules=provider_rules,deployment_readiness=readiness(provider_rules),
        parity_status='Independent arithmetic and matching native-account regression only; no provider/external-engine parity claim')
