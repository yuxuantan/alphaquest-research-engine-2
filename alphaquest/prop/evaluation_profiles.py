"""Evaluation-only orchestration over the existing provider kernels."""
import numpy as np

from .phase_profiles import (
    CONTRACT_VERSION, Censoring, EvaluationProfile, EvaluationProfileResult,
    EvaluationSamplingConfig, ResearchPeriod, SavedTradeSource, SimulationConfig,
    SourceCosts, SizingConfiguration, SizingTrace, prepare_phase_source, provenance, verify_phase_source,
)


def simulate_evaluation_profile(
    runs, source: SavedTradeSource, profile: EvaluationProfile, micros: int,
    simulation: SimulationConfig = SimulationConfig(),
    period: ResearchPeriod | None = None,
    sampling: EvaluationSamplingConfig = EvaluationSamplingConfig(),
    costs: SourceCosts = SourceCosts(),
    sizing: SizingConfiguration | None = None,
    observed_sessions=None,
) -> EvaluationProfileResult:
    """Evaluate one saved source/size, stopping at acquisition; never run funded.

    Cost keeps the legacy fee/pass-probability estimator. Replacement duration
    keeps the retained-block repeated-attempt estimator and activation weekday.
    A failed chain guard leaves timing unavailable, never a completed-path mean.
    """
    from .native_analysis import evaluation_model, evaluation_diagnostics, is_lucid, wilson
    if not isinstance(profile, EvaluationProfile):
        raise ValueError('Evaluation simulation requires an EvaluationProfile.')
    if not isinstance(sampling, EvaluationSamplingConfig):
        raise ValueError('Evaluation simulation requires EvaluationSamplingConfig.')
    if sampling.computational_horizon_weekdays is not None and profile.profile_id != 'lucidflex-50k':
        raise ValueError('Apex has a fixed 21-weekday provider deadline; no computational override is supported.')
    snapshot, days, settings = prepare_phase_source(runs, source, profile, micros, simulation, period, costs, sizing,
        observed_sessions=observed_sessions)
    trace = SizingTrace(sizing) if sizing is not None else None

    def runner(*args, **kwargs):
        if sampling.computational_horizon_weekdays is not None:
            kwargs['deadline'] = sampling.computational_horizon_weekdays
        if sizing is not None:
            kwargs.update(sizing.kernel_arguments(stage='attempt_sample' if not kwargs.get('chain') else 'legacy_chain'))
            if not kwargs.get('chain'):
                kwargs['trace'] = trace
        return evaluation_model(*args, **kwargs)

    sim = runner(days, micros, simulation.simulations, simulation.seed,
                 sampling.block_weekdays, settings, max_micros=simulation.max_micros)
    outcomes = sim['outcomes']
    passed = int(sum(outcomes == 'passed'))
    diagnostics = evaluation_diagnostics(sim)
    selected = dict(micros=micros, passed=passed, simulations=simulation.simulations,
                    evaluation_seed=simulation.seed, **{k:v for k,v in diagnostics.items() if k != 'simulations'})
    acquisition = acquisition_economics(days, selected, settings, sampling.block_weekdays,
        simulation.max_micros, [snapshot['profile_research_period'][key] for key in ('first_session', 'last_session')],
        chain_simulations=sampling.chain_simulations, chain_seed=sampling.chain_seed, evaluation_runner=runner)
    # Legacy wording/keys remain untouched in the compatibility entry point.
    acquisition['source'] = 'Requested single evaluation source and research period; no funded simulation or selection'
    if not passed:
        acquisition['reason'] = 'No sampled evaluation passed; acquisition cost and replacement time remain unresolved.'
    computational_censored = int(sum(outcomes == 'timeout')) if is_lucid(settings) else 0
    if computational_censored and not passed:
        acquisition['reason'] = 'Evaluation paths remain computationally censored; acquisition cost and timing are unavailable.'
    chain_status = ('resolved' if acquisition['status'] == 'calibrated' else
                    'censored' if acquisition['funding_chain_simulations'] == 0 and passed and not computational_censored else 'not_run')
    status = 'censored' if computational_censored or chain_status == 'censored' else ('resolved' if passed else 'unresolved')
    evaluation = dict(simulations=simulation.simulations, passed=passed,
        outcome_counts={str(key):int(sum(outcomes == key)) for key in np.unique(outcomes)},
        pass_rate=passed / simulation.simulations, pass_rate_ci=wilson(passed, simulation.simulations),
        pass_probability_bounds=[passed / simulation.simulations,
                                 (passed + computational_censored) / simulation.simulations],
        pass_rate_estimand='Observed pass fraction through the attempt cutoff; censored paths remain unresolved for eventual pass probability',
        median_weekdays_to_pass_conditional=float(np.median(sim['days'][outcomes == 'passed'])) if passed else None,
        provider_deadline_weekdays=None if is_lucid(settings) else 21,
        expired_paths=0 if is_lucid(settings) else int(sum(outcomes == 'timeout')),
        **{k:v for k,v in diagnostics.items() if k != 'simulations'})
    verify_phase_source(runs, source, snapshot)
    return EvaluationProfileResult(CONTRACT_VERSION, evaluation, acquisition,
        outcomes.tolist(), sim['days'].tolist(),
        Censoring(status, computational_censored, acquisition.get('reason'), chain_status,
                  0 if chain_status == 'resolved' else None),
        provenance('evaluation', snapshot, profile, micros, simulation, sampling,
            acquisition_cost_estimand='evaluation fee / single-attempt pass probability + activation fee; legacy Monte Carlo delta-method SE',
            replacement_duration_estimand='Repeated funding chain trading weekdays including existing activation delay; no calendar conversion',
            chain_guard='10,000 attempts; provider-specific computational horizon; aborted chains return no per-path censoring count',
            block_continuity='An unfinished circular block is retained across evaluation retries',
            selection='None; one requested source, profile and size',
            **({'sizing':trace.result()} if trace is not None else {})))


def acquisition_economics(train, selected, settings, block, max_micros, sample, chain_stats=None, *, chain_simulations=20000, chain_seed=45, evaluation_runner=None):
    """Freeze acquisition inputs from training only, before holdout is touched."""
    from .native_analysis import evaluation_model, evaluation_diagnostics, is_lucid, wilson
    runner = evaluation_runner or evaluation_model
    probability=selected['passed']/selected['simulations']
    result=dict(method='training_simulation',status='unavailable',sample=sample,
                evaluation_micros=selected['micros'],passed=selected['passed'],
                screening_passed=selected['passed'],screening_simulations=selected['simulations'],
                evaluation_censored_paths=int(selected.get('censored_paths',0)),
                simulations=selected['simulations'],pass_rate=probability,
                pass_rate_ci=wilson(selected['passed'],selected['simulations']),
                evaluation_seed=selected.get('evaluation_seed',42),funding_chain_seed=chain_seed,funding_chain_simulations=0,requested_funding_chain_simulations=chain_simulations,
                evaluation_price=float(settings['EVAL_PRICE']),activation_fee=float(settings['ACTIVATION_FEE']),
                activation_days=0 if is_lucid(settings) else 1,cost_per_funded=None,replacement_days=None,
                cost_se=None,replacement_days_se=None,
                source='Training joint sizing and repeated funding chains only; frozen before all holdout simulations')
    if not selected['passed']:
        result['reason']='No training evaluation passed. Acquisition cost and replacement time cannot be calibrated; funded sizing is unavailable.'
        return result
    if selected.get('censored_paths',0):
        result['reason']='Training evaluation paths remain censored; acquisition probability and timing are unavailable.'
        return result
    result.update(cost_per_funded=float(settings['EVAL_PRICE'])/probability+float(settings['ACTIVATION_FEE']),
                  evaluations_per_funded=1/probability,
                  cost_se=float(settings['EVAL_PRICE'])*np.sqrt(probability*(1-probability)/selected['simulations'])/probability**2)
    if chain_stats is not None:
        if chain_stats['status']=='calibrated':
            for key in ('status','funding_chain_simulations','replacement_days','replacement_days_median','replacement_days_se','funding_chain_diagnostics'):
                if key in chain_stats:result[key]=chain_stats[key]
        else:result['reason']=chain_stats['reason']
        return result
    try:
        chain=runner(train,selected['micros'],chain_simulations,chain_seed,block,settings,chain=True,max_micros=max_micros)
    except ValueError as exc:
        if not str(exc).startswith(('No pass within the 10,000-attempt funding-time bound','LucidFlex funding chain is censored')):raise
        result['reason']='Training funding time is unavailable: '+str(exc)
        return result
    result.update(status='calibrated',funding_chain_simulations=chain_simulations,replacement_days=float(chain['days'].mean()),
                  replacement_days_median=float(np.median(chain['days'])),
                  replacement_days_se=float(chain['days'].std(ddof=1)/np.sqrt(len(chain['days']))))
    if is_lucid(settings):result['funding_chain_diagnostics']=evaluation_diagnostics(chain)
    return result



def replay_evaluation_profile(runs, source, profile, micros, window, calendar, *, retry,
        max_micros=40, costs=SourceCosts(), sizing=None, frozen_binding, checkpoint=lambda: None):
    """Frozen acquisition policy on actual dates, including subsequent retries.

    This is one historical fixed-signal-path scenario. No source resampling,
    funded trading, phase selection or expected acquisition charge enters it.
    """
    from datetime import date
    from decimal import Decimal
    from hashlib import sha256
    from . import native_engine, lucid_engine
    from .adapter import canonical
    from .cash_ledger import cash, replay_calendar_sessions, next_evaluation_purchase, acquisition_schedule
    from .evaluation_optimization import SequentialRetry
    from .phase_profiles import prepare_chronological_source, verify_frozen_replay, chronological_kernel_arguments
    if type(retry) is not SequentialRetry or type(profile) is not EvaluationProfile:
        raise ValueError('Chronological acquisition requires evaluation-only profile and retry contracts.')
    snapshot, book, settings = prepare_chronological_source(runs, source, 'evaluation', profile, micros,
        max_micros, costs, sizing, window, calendar, frozen_binding, retry=retry)
    first, end = date.fromisoformat(window.first_session), date.fromisoformat(window.cutoff_date_exclusive)
    from datetime import timedelta
    guard = first+timedelta(days=retry.max_calendar_days)
    cutoff = min(end, guard)
    lucid = profile.profile_id == 'lucidflex-50k'
    kernel = lucid_engine if lucid else native_engine
    fee, activation = cash(profile.evaluation_price), cash(profile.activation_fee)
    calendar_sessions = replay_calendar_sessions(calendar)
    collector = SizingTrace(sizing)
    ledger, trace, attempts = [], [], []
    paid_evaluation = paid_activation = Decimal(0)
    attempt = None; purchase = first; passed_on = eligible = ready = None
    activation_paid = False; outcome = 'window_censored'
    def emit(day, event, amount='0', **extra):
        ledger.append(dict(sequence=len(ledger)+1, date=str(day), event=event,
            cash_delta=str(amount), time_basis='Modeled civil/session date; not an observed bank timestamp', **extra))
    for offset in range((cutoff-first).days):
        if offset % 32 == 0: checkpoint()
        day = first+timedelta(days=offset)
        trades = book.get(str(day))
        if passed_on is not None:
            if day == eligible:
                paid_activation += activation; activation_paid = True
                emit(day, 'activation_payment', -activation)
            if day == ready:
                outcome = 'funded_ready'; emit(day, 'funded_ready'); break
            if trades is not None:
                trace.append(dict(date=str(day), event='activation_wait', executed=0,
                    visited_source_trade_ids=[], unvisited_source_trade_ids=[t[4]['source_trade_id'] for t in trades]))
            continue
        if attempt is None and day >= purchase:
            if len(attempts) >= retry.max_attempts:
                outcome = 'attempt_guard_censored'; break
            attempt = dict(index=len(attempts)+1, purchase_date=str(day), first_session=None,
                sessions=0, equity=0., high=0., best=0., last_activity=0, outcome='open')
            attempts.append(attempt); paid_evaluation += fee
            emit(day, 'evaluation_purchase', -fee, attempt=attempt['index'])
        if attempt is None:
            if trades is not None:
                trace.append(dict(date=str(day), event='retry_wait', executed=0,
                    visited_source_trade_ids=[], unvisited_source_trade_ids=[t[4]['source_trade_id'] for t in trades]))
            continue
        if trades is None:
            # The same Lucid helper advances its inactivity clock on closed
            # dates without incrementing this attempt's eligible-session count.
            if lucid and attempt['first_session'] is not None:
                values = kernel.evaluation_session([], attempt['equity'], attempt['high'], attempt['best'],
                    attempt['last_activity'], (day-date.fromisoformat(attempt['first_session'])).days,
                    min(micros, max_micros, 40), 1200. if profile.daily_loss_limit else None)
                attempt['equity'], attempt['high'], attempt['best'], attempt['last_activity'], state, hit, used = values
                if state == 'inactive':
                    attempt.update(outcome=state, terminal_date=str(day))
                    emit(day, 'evaluation_failure', attempt=attempt['index'], reason=state)
                    purchase = next_evaluation_purchase(day, retry.retry_delay_calendar_days); attempt = None
            continue
        if attempt['first_session'] is None: attempt['first_session'] = str(day)
        attempt['sessions'] += 1
        before = dict(equity=attempt['equity'], high=attempt['high'], best_day=attempt['best'])
        decisions = []
        def capture(value): collector(value); decisions.append(value)
        kwargs = chronological_kernel_arguments(sizing, micros, capture, stage='outer_chronological',
            outer_fold_index=frozen_binding['outer_fold_index'], candidate_id=frozen_binding['candidate_id'],
            calendar_date=str(day), session_index=attempt['sessions'], attempt=attempt['index'])
        kwargs['max_micros'] = max_micros
        size = min(micros, max_micros, 40 if lucid else 60)
        if lucid:
            values = kernel.evaluation_session(trades, attempt['equity'], attempt['high'], attempt['best'],
                attempt['last_activity'], (day-date.fromisoformat(attempt['first_session'])).days, size,
                1200. if profile.daily_loss_limit else None, **kwargs)
            attempt['equity'], attempt['high'], attempt['best'], attempt['last_activity'], state, hit, used = values
        else:
            attempt['equity'], attempt['high'], state, hit, used = kernel.evaluation_session(
                trades, attempt['equity'], attempt['high'], size, **kwargs)
            if state == 'open' and attempt['sessions'] >= 21: state = 'expired'
        visited = [d['source_trade_id'] for d in decisions]
        visited_set = set(visited)
        trace.append(dict(date=str(day), event='evaluation_session', attempt=attempt['index'],
            state_before=before, equity_before=before['equity'], equity_after=attempt['equity'],
            state_after=dict(equity=attempt['equity'], high=attempt['high'], best_day=attempt['best']),
            decision_floor_state=decisions[0]['state_before'] if decisions else None,
            outcome=state, account_hit=hit, executed=used, skipped=sum(d['quantity'] == 0 for d in decisions),
            visited_source_trade_ids=visited,
            unvisited_source_trade_ids=[t[4]['source_trade_id'] for t in trades if t[4]['source_trade_id'] not in visited_set]))
        attempt['outcome'] = state
        if state == 'passed':
            attempt['terminal_date'] = str(day); passed_on = day
            emit(day, 'evaluation_passed', attempt=attempt['index'])
            eligible, ready = acquisition_schedule(day, calendar_sessions, retry.activation_delay_sessions, allow_pending=True)
            if eligible == day:
                paid_activation += activation; activation_paid = True; emit(day, 'activation_payment', -activation)
            outcome = 'activation_pending'; attempt = None
        elif state in ('blown', 'expired', 'inactive'):
            attempt['terminal_date'] = str(day)
            emit(day, 'evaluation_failure', attempt=attempt['index'], reason=state)
            purchase = next_evaluation_purchase(day, retry.retry_delay_calendar_days); attempt = None
    # The existing renewal forecast admits readiness exactly at its numerical
    # guard. It still forbids purchases, trading and activation charges there.
    # Keep the historical observation/cash cutoff independently exclusive.
    if ready == guard and guard < end and activation_paid and outcome == 'activation_pending':
        outcome = 'funded_ready'
        emit(guard, 'funded_ready')
    acquired = outcome == 'funded_ready'
    if not acquired and guard < end and outcome == 'window_censored': outcome = 'calendar_guard_censored'
    total_paid = paid_evaluation+paid_activation
    if sum((Decimal(row['cash_delta']) for row in ledger), Decimal(0)) != -total_paid:
        raise ValueError('Chronological acquisition cash conservation failed.')
    checkpoint()
    verify_phase_source(runs, source, snapshot)
    verify_frozen_replay(runs, source, 'evaluation', profile, micros, max_micros, costs, sizing,
        window, calendar, frozen_binding, retry=retry)
    sizing_result = collector.result()
    total_opportunities = sum(map(len, book.values()))
    return dict(mode='historical_chronological_replay', phase='evaluation', historical_paths=1,
        frozen_binding=frozen_binding, source=snapshot, input_manifest_sha256=sha256(canonical(snapshot).encode()).hexdigest(),
        source_book_sha256=sha256(canonical(book).encode()).hexdigest(),
        outcome=outcome, attempts=attempts, evaluation_passed=passed_on is not None,
        pass_date=str(passed_on) if passed_on else None, acquisition_completed=acquired,
        eligibility_date=str(eligible) if eligible else None, ready_date=str(ready) if ready else None,
        paid_evaluation_fees=str(paid_evaluation), paid_activation_fees=str(paid_activation),
        paid_fees=str(total_paid), net_cash=str(-total_paid), activation_paid=activation_paid,
        effective_observation_cutoff_exclusive=str(cutoff), calendar_guard_truncates_window=guard < end,
        readiness_guard_inclusive=True,
        pending_activation=str(activation if passed_on is not None and not activation_paid else Decimal(0)),
        calendar_days_to_funded=(ready-first).days if acquired else None, censored=not acquired,
        trace=trace, sizing=sizing_result, sizing_decisions=sizing_result['decisions'], cash_ledger=ledger,
        observations=dict(source_opportunities=total_opportunities, visited=sizing_result['summary']['decision_count'],
            unvisited=total_opportunities-sizing_result['summary']['decision_count']),
        conservation=dict(paid_fees=str(total_paid), cash_ledger_total=str(-total_paid), exact_decimal_cash=True),
        readiness='HISTORICAL_SCENARIO_ONLY', assumptions=[
            'Actual observed dates in original order; one chronological path, no resampling or reselection.',
            'Sequential evaluation retries consume only subsequent dates. Fees stay paid on failed and censored attempts; evaluation profit is not trader cash.',
            'The existing Apex model expires after 21 eligible sessions; current provider equivalence is unverified. Rule-version gaps are not deployment approval.',
            'Saved fixed-signal-path approximation: account pauses/skips are not a strategy rerun. No native execution or future profitability is certified.',
            'Calendar, activation and receipt timing are declared model assumptions. An unfinished acquisition has no fabricated finite funding-time estimate.'])
