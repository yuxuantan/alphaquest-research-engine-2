"""Evaluation-only orchestration over the existing provider kernels."""
import numpy as np
from .native_control import NativeControlBase

from .phase_profiles import (
    CONTRACT_VERSION, Censoring, EvaluationProfile, EvaluationProfileResult,
    EvaluationSamplingConfig, ResearchPeriod, SavedTradeSource, SimulationConfig,
    SourceCosts, SizingConfiguration, SizingTrace, prepare_phase_source, provenance, verify_phase_source,
)


class NativeEvaluationController(NativeControlBase):
    """Actual chronological acquisition, with fresh provider-account retries."""
    phase='evaluation'

    def __init__(self,profile,sizing,micros,*,max_micros=40,session_contexts,start_date,
            cutoff_date_exclusive,calendar,retry):
        from datetime import timedelta
        from decimal import Decimal
        from . import native_backend,lucid_backend
        from .cash_ledger import cash,replay_calendar_sessions
        from .evaluation_optimization import SequentialRetry
        from .phase_profiles import profile_settings
        if type(profile) is not EvaluationProfile or type(retry) is not SequentialRetry:
            raise ValueError('Native acquisition requires EvaluationProfile and SequentialRetry only.')
        profile_settings(profile,SourceCosts())
        super().__init__(sizing,micros,max_micros=max_micros,session_contexts=session_contexts,
            start_date=start_date,cutoff_date_exclusive=cutoff_date_exclusive)
        self.profile=profile;self.retry=retry;self.calendar=calendar
        self.calendar_sessions=replay_calendar_sessions(calendar)
        if any(day not in self.calendar_sessions for day in self.contexts):
            raise ValueError('An observed native session conflicts with the saved acquisition calendar.')
        self.lucid=profile.profile_id=='lucidflex-50k'
        self.kernel=(lucid_backend if self.lucid else native_backend).module()
        self.guard=self.start_date+timedelta(days=retry.max_calendar_days)
        self.effective_cutoff=min(self.cutoff,self.guard)
        self._equity=self.high=self.best_day=Decimal(0);self.last_activity=0
        self._account_status='not_purchased';self._current_attempt=None;self.attempts=[]
        self._calendar_cursor=self.start_date-timedelta(days=1);self._purchase_date=self.start_date
        self.fee,self.activation=cash(profile.evaluation_price),cash(profile.activation_fee)
        self.paid_evaluation=self.paid_activation=Decimal(0);self.cash_ledger=[]
        self.pass_date=self.eligibility_date=self.ready_date=None;self.activation_paid=False
        self.outcome='window_censored';self._active_session=False

    @property
    def equity(self):return self._equity
    @equity.setter
    def equity(self,value):self._equity=value
    @property
    def account_outcome(self):return self._account_status

    def _cash_event(self,day,event,amount=None,**values):
        self.cash_ledger.append(dict(sequence=len(self.cash_ledger)+1,date=str(day),event=event,
            cash_delta=str(amount) if amount is not None else '0',**values))

    def _buy(self,day):
        from decimal import Decimal
        from .native_money import money_add,money_sub
        if len(self.attempts)>=self.retry.max_attempts:
            self.outcome='attempt_guard_censored';self._account_status='attempt_guard_censored';return
        self.bridge.account_start_trading_net=money_sub(self._last_snapshot.engine_trade_cash,self._last_snapshot.engine_initial_capital)
        self.equity=self.high=self.best_day=Decimal(0);self.last_activity=0
        self._current_attempt=dict(index=len(self.attempts)+1,purchase_date=str(day),first_session=None,
            sessions=0,outcome='open',equity='0',high='0',best_day='0',
            prior_attempt_trading_net=str(self.bridge.account_start_trading_net))
        self.attempts.append(self._current_attempt);self._account_status='open'
        self.paid_evaluation=money_add(self.paid_evaluation,self.fee)
        self._cash_event(day,'evaluation_purchase',self.fee.copy_negate(),attempt=self._current_attempt['index'])

    def _fail(self,day,state):
        from .cash_ledger import next_evaluation_purchase
        if self._current_attempt is None:return
        self._current_attempt.update(outcome=state,terminal_date=str(day),equity=str(self.equity),high=str(self.high),best_day=str(self.best_day))
        self._cash_event(day,'evaluation_failure',attempt=self._current_attempt['index'],reason=state)
        self._current_attempt=None;self._purchase_date=next_evaluation_purchase(day,self.retry.retry_delay_calendar_days)
        self._account_status='retry_wait';self.can_trade=False

    def _activation_payment(self,day):
        from .native_money import money_add
        if self.activation_paid:return
        self.paid_activation=money_add(self.paid_activation,self.activation);self.activation_paid=True
        self._cash_event(day,'activation_payment',self.activation.copy_negate())

    def _advance_calendar(self,until,*,observed_session=None):
        from datetime import date,timedelta
        while self._calendar_cursor<until:
            self._calendar_cursor+=timedelta(days=1);day=self._calendar_cursor
            if day>=self.effective_cutoff:
                if day==self.guard and self.guard<self.cutoff and day==self.ready_date and self.activation_paid:
                    self.outcome='funded_ready';self._account_status='funded_ready';self._cash_event(day,'funded_ready')
                elif self.outcome=='window_censored' and self.guard<self.cutoff:
                    self.outcome='calendar_guard_censored';self._account_status='calendar_guard_censored'
                continue
            if self.pass_date is not None:
                if day==self.eligibility_date:self._activation_payment(day)
                if day==self.ready_date:
                    self.outcome='funded_ready';self._account_status='funded_ready';self._cash_event(day,'funded_ready')
                continue
            if self._current_attempt is None and day>=self._purchase_date and self.outcome!='attempt_guard_censored':self._buy(day)
            attempt=self._current_attempt
            if self.lucid and attempt is not None and attempt['first_session'] is not None and day!=observed_session:
                elapsed=(day-date.fromisoformat(attempt['first_session'])).days
                if elapsed-self.last_activity>=30:self._fail(day,'inactive')

    def _phase_begin(self,session,snapshot):
        from datetime import date
        from decimal import Decimal
        self._advance_calendar(session.session,observed_session=session.session)
        attempt=self._current_attempt
        self._active_session=attempt is not None and self._account_status=='open' and session.session<self.effective_cutoff
        self.can_trade=self._active_session
        if not self._active_session:return
        if attempt['first_session'] is None:attempt['first_session']=str(session.session)
        self._calendar_day=(session.session-date.fromisoformat(attempt['first_session'])).days
        daily=Decimal(1200) if self.profile.daily_loss_limit else None
        boundary=(self.kernel.evaluation_opening(self.equity,self.high,self.last_activity,self._calendar_day,daily)
            if self.lucid else self.kernel.evaluation_opening(self.equity,self.high))
        if boundary is None:
            self._fail(session.session,'inactive');self._active_session=False;return
        self._opening,self.account_floor,daily_floor=boundary
        self.daily_floor=None if self.lucid and daily is None else daily_floor
        self.provider_cap=40 if self.lucid else 60;attempt['sessions']+=1

    def _phase_close(self,trade,hit):
        if self.lucid and trade.net_pnl.copy_abs()>=1:self.last_activity=self._calendar_day
        if hit==2:self._account_status='blown';self.can_trade=False
        elif not self.lucid and self.equity>=3000:
            self._account_status='passed';self.can_trade=False

    def _phase_end(self,session,snapshot):
        from decimal import Decimal
        from .cash_ledger import acquisition_schedule
        if not self._active_session:return
        if self.lucid:
            self.equity,self.high,self.best_day,self.last_activity,self._account_status=self.kernel.evaluation_finish(
                self.equity,self.high,self.best_day,self._opening,self.last_activity,self._calendar_day,self._account_status,Decimal('.4'))
        else:
            self.equity,self.high,self._account_status=self.kernel.evaluation_finish(self.equity,self.high,self._account_status)
            if self._account_status=='open' and self._current_attempt['sessions']>=21:self._account_status='expired'
        attempt=self._current_attempt
        attempt.update(equity=str(self.equity),high=str(self.high),best_day=str(self.best_day),outcome=self._account_status)
        if self._account_status=='passed':
            attempt['terminal_date']=str(session.session);self.pass_date=session.session
            self._cash_event(session.session,'evaluation_passed',attempt=attempt['index'])
            self.eligibility_date,self.ready_date=acquisition_schedule(session.session,self.calendar_sessions,
                self.retry.activation_delay_sessions,allow_pending=True)
            if self.eligibility_date==session.session:self._activation_payment(session.session)
            self.outcome='activation_pending';self._account_status='activation_pending';self._current_attempt=None
        elif self._account_status in ('blown','inactive','expired'):
            self._fail(session.session,self._account_status)
        self.can_trade=False

    def _phase_finish(self):
        from datetime import timedelta
        self._advance_calendar(self.cutoff-timedelta(days=1))

    def _phase_result(self):
        from decimal import Decimal
        from .native_money import money_add,money_sum
        paid=money_add(self.paid_evaluation,self.paid_activation)
        actual=money_sum(Decimal(event['cash_delta']) for event in self.cash_ledger)
        if actual!=paid.copy_negate():raise ValueError('Native acquisition fee ledger does not reconcile.')
        acquired=self.outcome=='funded_ready'
        return dict(outcome=self.outcome,attempts=self.attempts,evaluation_passed=self.pass_date is not None,
            modeled_rules=dict(profile_id=self.profile.profile_id,rule_version=self.profile.rule_version,
                initial_configured_capital='50000',maximum_drawdown='2000',profit_target='3000',
                eod_floor_cap='100' if self.lucid else '3000',
                daily_loss=('1200' if self.profile.daily_loss_limit else None) if self.lucid else '1000',
                maximum_contracts=40 if self.lucid else 60,
                consistency_fraction='0.4' if self.lucid else None,
                consistency_test='best_day <= fraction * total_profit at session close' if self.lucid else None,
                provider_expiry_sessions=None if self.lucid else 21,
                inactivity_calendar_days=30 if self.lucid else None,
                activity_minimum_absolute_trade_net='1' if self.lucid else None,
                arithmetic='Exact Decimal state for native actual fills; legacy fixed-book float arithmetic is unchanged.'),
            pass_date=self.pass_date,eligibility_date=self.eligibility_date,ready_date=self.ready_date,
            acquisition_completed=acquired,activation_paid=self.activation_paid,
            paid_evaluation_fees=str(self.paid_evaluation),paid_activation_fees=str(self.paid_activation),
            paid_fees=str(paid),net_cash=str(paid.copy_negate()),cash_ledger=self.cash_ledger,
            pending_activation=str(self.activation if self.pass_date is not None and not self.activation_paid else Decimal(0)),
            calendar_days_to_funded=(self.ready_date-self.start_date).days if acquired else None,censored=not acquired,
            effective_observation_cutoff_exclusive=str(self.effective_cutoff),readiness_guard_inclusive=True,
            calendar_guard_truncates_window=self.guard<self.cutoff,
            strategy_state_on_retry='Continuous causal strategy features on original bars; only the provider account resets.',
            observed_sessions=len(self.session_trace))


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
