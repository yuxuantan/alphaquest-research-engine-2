"""Fresh-funded orchestration; acquisition inputs never enter these runners."""
import numpy as np

from .phase_profiles import (
    CONTRACT_VERSION, Censoring, FundedProfile, FundedProfileResult, ResearchPeriod,
    SamplingConfig, SavedTradeSource, SimulationConfig, SourceCosts, SizingConfiguration, SizingTrace,
    positive_integer, prepare_phase_source, provenance, verify_phase_source,
)


def simulate_funded_profile(
    runs, source: SavedTradeSource, profile: FundedProfile, micros: int,
    horizon_weekdays: int,
    simulation: SimulationConfig = SimulationConfig(),
    period: ResearchPeriod | None = None,
    sampling: SamplingConfig = SamplingConfig(),
    costs: SourceCosts = SourceCosts(),
    sizing: SizingConfiguration | None = None,
    observed_sessions=None,
) -> FundedProfileResult:
    """One fresh funded account per path, with no acquisition or replacement.

    Horizon is the existing inclusive session-count cap. Receipts follow the
    existing payout-time convention; they are not verified bank settlements.
    Open accounts are explicitly lifetime-censored even though horizon payout
    observations are complete. Full lifetime means are withheld in that case.
    """
    from dataclasses import asdict, replace
    from .native_analysis import Rules, account_backend, funded, summary
    if not isinstance(profile, FundedProfile):
        raise ValueError('Funded simulation requires a FundedProfile.')
    if type(sampling) is not SamplingConfig:
        raise ValueError('Funded simulation accepts only phase-neutral SamplingConfig.')
    positive_integer('horizon_weekdays', horizon_weekdays, 20000)
    snapshot, days, settings = prepare_phase_source(runs, source, profile, micros, simulation, period, costs, sizing,
        observed_sessions=observed_sessions)
    trace = SizingTrace(sizing) if sizing is not None else None
    if profile.profile_id == 'lucidflex-50k':
        from .lucid_backend import Rules as LucidRules
        rules = LucidRules(daily_loss=1200. if profile.daily_loss_limit else None)
    else:
        rules = replace(Rules(), approval_day_counts=profile.approval_day_counts)
    backend = account_backend(rules)
    accounts = (backend.funded if backend else funded)(days, micros, simulation.simulations,
        simulation.seed, sampling.block_weekdays, horizon=horizon_weekdays,
        rules=rules, max_micros=simulation.max_micros,
        **(dict(**sizing.kernel_arguments(stage='funded_session_sample'), trace=trace) if sizing is not None else {}))
    # Always sample the requested horizon, including analytical-zero-payout
    # cases: survival still needs the existing funded transitions.
    stats = summary(accounts, micros, len(rules.ladder))
    paths = [dict(outcome=a.outcome, observed_weekdays=a.day,
        trader_payouts=list(a.payouts), gross_account_deductions=list(getattr(a, 'withdrawals', a.payouts)),
        equity=a.equity, lifetime_censored=a.outcome == 'open') for a in accounts]
    receipts = np.array([sum(value for _, value in a.payouts) for a in accounts])
    open_paths = sum(a.outcome == 'open' for a in accounts)
    verify_phase_source(runs, source, snapshot)
    return FundedProfileResult(CONTRACT_VERSION,
        payouts=dict(legacy_summary=stats, mean_trader_payout=stats['E[payout]'],
            mean_se=stats['SE'], median=float(np.quantile(receipts, .5, method='inverted_cdf')),
            p10=float(np.quantile(receipts, .1, method='inverted_cdf')),
            probability_positive=float(np.mean(receipts > 0)), probability_zero=float(np.mean(receipts == 0)),
            mean_gross_account_deduction=float(np.mean([sum(v for _,v in p['gross_account_deductions']) for p in paths])),
            horizon_observations_complete=True),
        survival=dict(open_at_horizon=open_paths, probability_open_at_horizon=open_paths / simulation.simulations,
            restricted_mean_active_weekdays=stats['days alive'],
            mean_terminal_lifetime_weekdays=None if open_paths else stats['days alive'],
            lifetime_complete=not open_paths),
        downside=dict(probability_breach=stats['blown'], probability_inactive=stats['inactive'],
            probability_zero_payout=float(np.mean(receipts == 0)), payout_p10=float(np.quantile(receipts, .1, method='inverted_cdf'))),
        paths=paths,
        censoring=Censoring('censored' if open_paths else 'resolved', open_paths,
            'Open accounts have unobserved terminal lifetime beyond the requested horizon.' if open_paths else None),
        provenance=provenance('funded', snapshot, profile, micros, simulation, sampling,
            horizon_weekdays=horizon_weekdays, rules=asdict(rules),
            initial_state='One fresh funded account; no prior payouts, positions or replacement account',
            receipt_convention='Existing kernel trader payout at request/account deduction; bank settlement delay and pending bank receipts are not modeled',
            quantiles='Inverse empirical CDF (inverted_cdf)',
            selection='None; one requested source, profile and size',
            **({'sizing':trace.result()} if trace is not None else {})))


def lifetime_profile(value):
    """One independent training stage, reused across all evaluation sizes."""
    from .joint_sizing import LIFETIME_HORIZON
    from .native_analysis import account_backend, funded, summary
    days,size,block,rules,max_micros,count,seed=value
    # Even taking every positive trade and skipping every loss cannot exceed
    # this session-profit bound. A payout requires qualifying days in both
    # supported models. This proves zero possible receipts without pretending
    # an indefinitely open account has a measured terminal lifetime.
    profit_bound=max(sum(max(0.,t[0]) for t in day) for day in days)*min(size,max_micros,max(level[1] for level in rules.levels))/10.
    if profit_bound < rules.qualifying_profit:
        return dict(micros=size,sims=0,requested_simulations=count,screening_simulations=3000,seed=seed,
            method='analytical_zero_payout_bound',**{'E[payout]':0.,'days alive':None,'SE':None},
            lifetime_complete=False,censored_paths=None,horizon_weekdays=LIFETIME_HORIZON,
            receipts_upper_bound=0.,qualifying_day_profit_upper_bound=profit_bound,
            reason='No sampled source session can meet the qualifying-day profit at this size; lifetime is unknown, payout potential is zero.')
    backend=account_backend(rules);runner=backend.funded if backend else funded
    accounts=runner(days,size,count,seed,block,horizon=LIFETIME_HORIZON,rules=rules,max_micros=max_micros)
    stats=summary(accounts,size,len(rules.ladder))
    receipts=np.array([sum(v for _,v in a.payouts) for a in accounts])
    lifetimes=np.array([a.day for a in accounts])
    censored=sum(a.outcome=='open' for a in accounts)
    maximum=sum(rules.ladder)*getattr(rules,'payout_share',1.)
    stats.update(method='monte_carlo',lifetime_complete=not censored,censored_paths=censored,horizon_weekdays=LIFETIME_HORIZON,seed=seed,
        screening_simulations=3000,lifetime_se=float(lifetimes.std(ddof=1)/np.sqrt(count)),
        receipts_lifetime_covariance=float(np.cov(receipts,lifetimes,ddof=1)[0,1]/count),
        receipts_upper_bound=float(np.mean([maximum if a.outcome=='open' else receipts[i] for i,a in enumerate(accounts)])))
    return stats



def simulate_dated_funded_profile(runs, source, profile, micros, horizon_calendar_days,
        calendar, receipt_delay_calendar_days, simulation=SimulationConfig(),
        period=None, sampling=SamplingConfig(), costs=SourceCosts(), sizing=None, observed_sessions=None):
    """Dated fresh-account paths using the same native funded transitions.

    The legacy weekday interface above remains unchanged. Dates are civil session
    labels, not inferred intraday execution/settlement timestamps. Each path has
    its own addressed RNG; termination never changes another path's schedule.
    """
    from dataclasses import asdict
    from datetime import date, timedelta
    if not isinstance(profile, FundedProfile) or type(sampling) is not SamplingConfig:
        raise ValueError('Dated funded simulation requires funded-only inputs.')
    positive_integer('horizon_calendar_days', horizon_calendar_days, 3650)
    if type(receipt_delay_calendar_days) is not int or not 0 <= receipt_delay_calendar_days <= 365:
        raise ValueError('Receipt delay must be 0–365 calendar days.')
    if simulation.simulations % len(calendar.start_dates):
        raise ValueError('Simulation count must be divisible by start cohort size.')
    if any(date.fromisoformat(s)+timedelta(days=horizon_calendar_days) > date.fromisoformat(calendar.coverage_end)
           for s in calendar.start_dates):
        raise ValueError('Calendar must cover every horizon cutoff.')
    snapshot, days, _ = prepare_phase_source(runs, source, profile, micros, simulation, period, costs, sizing,
        observed_sessions=observed_sessions)
    trace = SizingTrace(sizing) if sizing is not None else None
    paths, schedule_sha256, rules = _dated_funded_paths(days, profile, micros, horizon_calendar_days,
        calendar, receipt_delay_calendar_days, simulation, sampling, sizing, trace)
    verify_phase_source(runs, source, snapshot)
    result = dict(paths=paths, schedule_sha256=schedule_sha256,
        provenance=provenance('funded', snapshot, profile, micros, simulation, sampling,
            rules=asdict(rules), horizon_calendar_days=horizon_calendar_days,
            calendar=asdict(calendar), receipt_delay_calendar_days=receipt_delay_calendar_days,
            dated_kernel='Python reference FundedAccount.advance; identical native qualification/tier/drawdown/payout policy',
            dated_clock='Chicago civil session dates; daily resolution, event age is date minus start date; exclusive cutoff',
            dated_rng='MT19937 seeded by SeedSequence([seed,path_index]); circular source-session blocks; no paired inference claim',
            settlement='Automatic request/deduction on native eligibility date; entitlement paid after declared civil-day lag, including weekends and after account closure; unverified scenario',
            initial_state='Fresh funded account at t=0; no evaluation, acquisition or replacement',
            **({'sizing':trace.result()} if trace is not None else {})))
    result['provenance']['time_unit'] = 'Chicago civil calendar days, not session counts'
    result['provenance']['kernel'] = dict(name='python-reference', source='lucid_engine.py' if profile.profile_id == 'lucidflex-50k' else 'native_engine.py')
    return result


def _dated_funded_paths(days, profile, micros, horizon_calendar_days, calendar,
        receipt_delay_calendar_days, simulation, sampling, sizing=None, trace=None):
    """The same fresh-account dated kernel for original and resampled histories."""
    from dataclasses import replace
    from datetime import date, timedelta
    from hashlib import sha256
    from . import native_engine, lucid_engine
    lucid = profile.profile_id == 'lucidflex-50k'
    rules = (lucid_engine.Rules(daily_loss=1200. if profile.daily_loss_limit else None) if lucid
             else replace(native_engine.Rules(), approval_day_counts=profile.approval_day_counts))
    account_class = lucid_engine.FundedAccount if lucid else native_engine.FundedAccount
    paths = []
    schedule = sha256()
    closed = set(calendar.closures)
    starts = sorted(calendar.start_dates)
    for i in range(simulation.simulations):
        start = date.fromisoformat(starts[i % len(starts)])
        cutoff = start + timedelta(days=horizon_calendar_days)
        rng = np.random.RandomState(np.random.SeedSequence([simulation.seed, i]).generate_state(1)[0])
        stream = native_engine.sampled_days(rng, len(days), sampling.block_weekdays)
        account = account_class(rules)
        events = []
        terminal_date = None
        for offset in range(horizon_calendar_days):
            day = start + timedelta(days=offset)
            is_session = day.weekday() < 5 and day.isoformat() not in closed
            if not is_session:
                # Reuse the native calendar expiry check even across weekends or
                # declared closures; never increment the account's session count.
                if lucid:
                    account.expire_inactive(offset)
            else:
                index = next(stream)
                schedule.update(f'{i}:{day.isoformat()}:{index};'.encode())
                before = len(account.payouts)
                dynamic = (dict(**sizing.kernel_arguments(stage='funded_calendar_sample', path_index=i,
                    source_session_index=index, calendar_date=day.isoformat()), trace=trace) if sizing is not None else {})
                if lucid:
                    account.advance(days[index], micros, simulation.max_micros, calendar_day=offset, **dynamic)
                else:
                    account.advance(days[index], micros, simulation.max_micros, **dynamic)
                if len(account.payouts) > before:
                    entitlement = account.payouts[-1][1]
                    gross = account.withdrawals[-1][1] if lucid else entitlement
                    due = day + timedelta(days=receipt_delay_calendar_days)
                    events.append(dict(eligibility_date=day.isoformat(), request_date=day.isoformat(),
                        deduction_date=day.isoformat(), receipt_date=due.isoformat(),
                        gross_account_deduction=gross, trader_cash_entitlement=entitlement,
                        received_within_horizon=due < cutoff,
                        trader_cash_received=entitlement if due < cutoff else 0.))
            if account.outcome != 'open':
                terminal_date = day
                break
        receipts = [e for e in events if e['received_within_horizon']]
        paths.append(dict(path=i, start_date=start.isoformat(), cutoff_exclusive=cutoff.isoformat(),
            outcome=account.outcome, observed_sessions=account.day,
            terminal_date=terminal_date.isoformat() if terminal_date else None,
            observed_calendar_days=(terminal_date-start).days if terminal_date else horizon_calendar_days,
            lifetime_censored=terminal_date is None, horizon_observations_complete=True,
            unresolved=False, payout_events=events, equity=account.equity,
            trading_profit=account.equity+sum(e['gross_account_deduction'] for e in events),
            gross_account_deductions=sum(e['gross_account_deduction'] for e in events),
            cash_received=sum(e['trader_cash_received'] for e in events),
            pending_cash=sum(e['trader_cash_entitlement'] for e in events if not e['received_within_horizon']),
            number_of_payouts=len(receipts),
            days_to_first_payout=(date.fromisoformat(receipts[0]['receipt_date'])-start).days if receipts else None))
    return paths, schedule.hexdigest(), rules


def historical_funded_mean(runs, source, profile, micros, horizon_calendar_days,
        calendar, receipt_delay_calendar_days, simulation, period, sampling, costs,
        *, configuration, family_size, sizing=None, observed_sessions=None,
        progress=lambda message: None):
    """Re-estimate funded mean cash after resampling observed historical blocks.

    This is a nominal percentile calculation under a stationary empirical
    history model. Its inner Monte Carlo noise is measured and gated; neither
    that noise nor historical resampling covers total future uncertainty.
    """
    from dataclasses import asdict, replace
    from decimal import Decimal, localcontext
    from hashlib import sha256
    from .adapter import canonical
    from .native_engine import sampled_days
    from .funded_optimization import FundedHistoricalMean
    if type(configuration) is not FundedHistoricalMean:
        raise ValueError('Historical funded mean requires its explicit configuration.')
    positive_integer('family_size', family_size, 100000)
    cfg = configuration
    snapshot, days, _ = prepare_phase_source(runs, source, profile, micros, simulation,
        period, costs, sizing, observed_sessions=observed_sessions)
    labels = list(observed_sessions) if observed_sessions is not None else None
    evidence = 'internally_verified_observed_sessions' if labels is not None else 'unavailable'
    if labels is None and snapshot.get('source_kind') == 'external_trade_export':
        bounds = snapshot['profile_research_period']
        labels = [stamp for stamp in snapshot['canonical_manifest']['coverage']['sessions']
                  if bounds['first_session'] <= stamp <= bounds['last_session']]
        snapshot, days, _ = prepare_phase_source(runs, source, profile, micros, simulation,
            period, costs, sizing, observed_sessions=labels)
        evidence = 'exporter_declared_observed_sessions_not_independently_certified'
    # Integer ratios avoid moving an exact rank boundary when a Bonferroni
    # probability recurs in decimal (for example .1/7 with 350 replicates).
    confidence_numerator, confidence_denominator = Decimal(str(cfg.confidence_level)).as_integer_ratio()
    tail_numerator = confidence_denominator-confidence_numerator
    tail_denominator = confidence_denominator*family_size
    replicate_tail_numerator = cfg.replicates*tail_numerator
    rank = (replicate_tail_numerator+tail_denominator-1)//tail_denominator
    with localcontext() as context:
        context.prec = 80
        alpha = Decimal(tail_numerator)/Decimal(tail_denominator)
        expected_tail = Decimal(replicate_tail_numerator)/Decimal(tail_denominator)
    count = len(labels) if labels is not None else 0
    if labels is not None and len(days) != count:
        raise ValueError('Historical session inventory differs from the admitted source book.')
    reasons = []
    if labels is None: reasons.append('verified_observed_session_inventory_required')
    if count < cfg.minimum_history_sessions: reasons.append('minimum_history_sessions')
    if count//cfg.block_sessions < cfg.minimum_history_blocks: reasons.append('minimum_history_blocks')
    if replicate_tail_numerator < 5*tail_denominator: reasons.append('insufficient_family_tail_replicates')
    starts = sorted(calendar.start_dates)
    if cfg.simulations_per_replicate % len(starts) or cfg.simulations_per_replicate//len(starts) < 2:
        reasons.append('minimum_two_inner_paths_per_start_cohort')
    result = dict(configuration=asdict(cfg), status='insufficient_evidence', reasons=reasons,
        cash_unit='USD trader cash received within the saved horizon',
        estimation_target='Expected receipts conditional on a fresh funded account and the declared historical model',
        lower_mean_cash=None, confidence_level=cfg.confidence_level, family_size=family_size,
        tail_probability=str(alpha), tail_rank=rank, expected_tail_replicates=str(expected_tail),
        tail_probability_fraction=dict(numerator=tail_numerator, denominator=tail_denominator),
        history_session_count=count, history_block_count=count//cfg.block_sessions,
        history_session_labels=labels, history_evidence=evidence, replicates=[],
        mc_noise=dict(maximum_allowed_standard_error=cfg.maximum_mc_standard_error,
            maximum_observed_standard_error=None, median_observed_standard_error=None,
            same_addressed_simulation_stream_across_histories=True),
        family_coverage='Nominal one-sided Bonferroni percentile tail across every declared candidate; no simultaneous finite-sample guarantee',
        method='Circular historical session-block resampling to the original history length, followed by the same dated fresh-funded-account simulation',
        quantile='Inverse empirical CDF, sorted mean at ceil(replicates * (1-confidence) / family_size)',
        random_streams='History MT19937 SeedSequence([history_seed,replicate]); inner paths MT19937 SeedSequence([simulation_seed,path_index])',
        limitations=[
            'Resampling units are historical sessions/blocks, not the number of Monte Carlo paths. Blocks are not asserted independent.',
            'Stationarity and the declared block length are modeling assumptions; regime change, unobserved losses, provider rules and execution errors are not covered.',
            'Account simulations retain the admitted saved signal-path assumption; historical resampling is not a native strategy rerun after account pauses or size changes.',
            'The percentile concerns an estimated expected cash mean, not a single account payout percentile.',
            'Replicate means retain finite Monte Carlo error. A standard-error ceiling and common streams reduce numerical noise but do not remove it or certify rare-event accuracy.',
            'Nominal bootstrap coverage is approximate; neither the confidence label nor additional replicates guarantees future trading cash.'])
    if reasons:
        verify_phase_source(runs, source, snapshot)
        return result
    if cfg.replicates*count > 1_000_000:
        raise ValueError('Historical bootstrap source-index capture exceeds one million indices.')
    if cfg.replicates*cfg.simulations_per_replicate*horizon_calendar_days > 50_000_000:
        raise ValueError('Historical bootstrap exceeds 50 million inner path calendar days.')
    inner = replace(simulation, simulations=cfg.simulations_per_replicate, seed=cfg.simulation_seed)
    for number in range(cfg.replicates):
        progress(f'Historical funded mean replicate {number+1} / {cfg.replicates}')
        seed = int(np.random.SeedSequence([cfg.history_seed, number]).generate_state(1)[0])
        stream = sampled_days(np.random.RandomState(seed), count, cfg.block_sessions)
        indices = [next(stream) for _ in range(count)]
        paths, schedule, _ = _dated_funded_paths([days[index] for index in indices], profile,
            micros, horizon_calendar_days, calendar, receipt_delay_calendar_days, inner, sampling, sizing)
        cash = np.array([path['cash_received'] for path in paths], dtype=float)
        groups = [cash[[path['start_date'] == start for path in paths]] for start in starts]
        se = float(np.sqrt(sum(np.var(group, ddof=1)/len(group) for group in groups))/len(groups))
        mean = float(cash.mean())
        if not np.isfinite(mean) or not np.isfinite(se):
            raise ValueError('Historical funded mean calculation produced nonfinite cash or Monte Carlo error.')
        result['replicates'].append(dict(replicate=number, history_seed=seed, source_indices=indices,
            indices_sha256=sha256(canonical(indices).encode()).hexdigest(), simulation_seed=inner.seed,
            mean_cash=mean, mean_monte_carlo_se=se, schedule_sha256=schedule))
    verify_phase_source(runs, source, snapshot)
    errors = [row['mean_monte_carlo_se'] for row in result['replicates']]
    result['mc_noise'].update(maximum_observed_standard_error=max(errors),
        median_observed_standard_error=float(np.median(errors)))
    if max(errors) > cfg.maximum_mc_standard_error:
        result['reasons'].append('inner_monte_carlo_standard_error_exceeds_declared_limit')
    else:
        result.update(status='estimated', lower_mean_cash=sorted(row['mean_cash'] for row in result['replicates'])[rank-1])
    return result


def replay_funded_profile(runs, source, profile, micros, window, calendar, *,
        receipt_delay_calendar_days, receipt_amount_convention='kernel_entitlement_unrounded',
        max_micros=40, costs=SourceCosts(), sizing=None, frozen_binding, checkpoint=lambda: None):
    """One fresh funded account on its frozen actual historical session sequence."""
    from dataclasses import asdict, replace
    from datetime import date, timedelta
    from decimal import Decimal
    from hashlib import sha256
    from . import native_engine, lucid_engine
    from .adapter import canonical
    from .cash_ledger import dated_settlement
    from .phase_profiles import prepare_chronological_source, verify_frozen_replay, chronological_kernel_arguments
    if type(profile) is not FundedProfile:
        raise ValueError('Chronological funded replay accepts a funded profile only.')
    if type(receipt_delay_calendar_days) is not int or not 0 <= receipt_delay_calendar_days <= 365:
        raise ValueError('Receipt lag must be an explicit whole calendar-day value.')
    snapshot, book, settings = prepare_chronological_source(runs, source, 'funded', profile, micros,
        max_micros, costs, sizing, window, calendar, frozen_binding,
        receipt_delay_calendar_days=receipt_delay_calendar_days, receipt_amount_convention=receipt_amount_convention)
    lucid = profile.profile_id == 'lucidflex-50k'
    kernel = lucid_engine if lucid else native_engine
    rules = lucid_engine.Rules(daily_loss=1200. if profile.daily_loss_limit else None) if lucid else replace(native_engine.Rules(), approval_day_counts=profile.approval_day_counts)
    account = kernel.FundedAccount(rules)
    first, cutoff = date.fromisoformat(window.first_session), date.fromisoformat(window.cutoff_date_exclusive)
    collector = SizingTrace(sizing)
    trace, events, ledger = [], [], []
    terminal = None; trading_profit = Decimal(0)
    def decimal(value): return Decimal(str(value))
    for offset in range((cutoff-first).days):
        if offset % 32 == 0: checkpoint()
        day = first+timedelta(days=offset)
        if account.outcome != 'open': continue
        trades = book.get(str(day))
        if trades is None:
            if lucid: account.expire_inactive(offset)
        else:
            before = dict(equity=account.equity, high=account.high, locked=account.locked,
                qualifying=account.qualifying, sessions=account.day)
            payout_count = len(account.payouts); decisions = []
            def capture(value): collector(value); decisions.append(value)
            kwargs = chronological_kernel_arguments(sizing, micros, capture, stage='outer_chronological',
                outer_fold_index=frozen_binding['outer_fold_index'], candidate_id=frozen_binding['candidate_id'],
                calendar_date=str(day), session_index=account.day+1)
            if lucid: kwargs['calendar_day'] = offset
            account.advance(trades, micros, max_micros, **kwargs)
            deduction = 0.
            if len(account.payouts) > payout_count:
                receipt = account.payouts[-1][1]
                deduction = account.withdrawals[-1][1] if lucid else receipt
                events.append(dated_settlement(day, receipt, deduction, receipt_delay_calendar_days,
                    cutoff, receipt_amount_convention))
            trading_profit += decimal(account.equity)-decimal(before['equity'])+decimal(deduction)
            visited = [decision['source_trade_id'] for decision in decisions]
            visited_set = set(visited)
            trace.append(dict(date=str(day), event='funded_session', state_before=before,
                state_after=dict(equity=account.equity, high=account.high, locked=account.locked,
                    qualifying=account.qualifying, sessions=account.day),
                equity_before=before['equity'], equity_after=account.equity,
                decision_floor_state=decisions[0]['state_before'] if decisions else None,
                account_hit=account.last_hit, outcome=account.outcome, executed=account.trades_consumed,
                skipped=sum(decision['quantity'] == 0 for decision in decisions),
                visited_source_trade_ids=visited,
                unvisited_source_trade_ids=[trade[4]['source_trade_id'] for trade in trades if trade[4]['source_trade_id'] not in visited_set]))
        if account.outcome != 'open': terminal = str(day)
    gross = sum((Decimal(event['gross_account_deduction']) for event in events), Decimal(0))
    received = sum((Decimal(event['trader_amount']) for event in events if event['received_within_horizon']), Decimal(0))
    pending = sum((Decimal(event['trader_amount']) for event in events if not event['received_within_horizon']), Decimal(0))
    raw = sum((Decimal(event['raw_trader_entitlement']) for event in events), Decimal(0))
    share = sum((Decimal(event['provider_retained_share']) for event in events), Decimal(0))
    rounding = sum((Decimal(event['rounding_delta']) for event in events), Decimal(0))
    if decimal(account.equity)+gross != trading_profit or gross != raw+share or received+pending != raw+rounding:
        raise ValueError('Chronological funded cash/account conservation failed.')
    for number, event in enumerate(events, 1):
        ledger.extend([dict(date=event['request_date'], event='payout_request', payout_id=number, cash_delta='0'),
            dict(date=event['deduction_date'], event='account_deduction', payout_id=number,
                cash_delta='0', account_equity_delta=str(-Decimal(event['gross_account_deduction'])))])
        if event['received_within_horizon']:
            ledger.append(dict(date=event['receipt_date'], event='trader_receipt', payout_id=number,
                cash_delta=event['trader_amount']))
    order = {'payout_request': 0, 'account_deduction': 1, 'trader_receipt': 2}
    ledger.sort(key=lambda row: (row['date'], order[row['event']], row['payout_id']))
    for number, row in enumerate(ledger, 1): row['sequence'] = number
    if sum((Decimal(row['cash_delta']) for row in ledger), Decimal(0)) != received:
        raise ValueError('Chronological funded receipt ledger does not reconcile.')
    checkpoint()
    verify_phase_source(runs, source, snapshot)
    verify_frozen_replay(runs, source, 'funded', profile, micros, max_micros, costs, sizing, window, calendar,
        frozen_binding, receipt_delay_calendar_days=receipt_delay_calendar_days,
        receipt_amount_convention=receipt_amount_convention)
    sizing_result = collector.result(); total_opportunities = sum(map(len, book.values()))
    return dict(mode='historical_chronological_replay', phase='funded', historical_paths=1,
        frozen_binding=frozen_binding, source=snapshot, rules=asdict(rules),
        input_manifest_sha256=sha256(canonical(snapshot).encode()).hexdigest(),
        source_book_sha256=sha256(canonical(book).encode()).hexdigest(),
        outcome=account.outcome, terminal_date=terminal, lifetime_censored=terminal is None,
        horizon_observations_complete=True, observed_sessions=account.day,
        equity=str(account.equity), trading_profit=str(trading_profit), gross_account_deductions=str(gross),
        raw_trader_entitlement=str(raw), provider_retained_share=str(share), receipt_rounding_delta=str(rounding),
        receipt_amount_convention=receipt_amount_convention,
        cash_received=str(received), pending_cash=str(pending), net_cash=str(received),
        payout_events=events, trace=trace, sizing=sizing_result, sizing_decisions=sizing_result['decisions'], cash_ledger=ledger,
        observations=dict(source_opportunities=total_opportunities, visited=sizing_result['summary']['decision_count'],
            unvisited=total_opportunities-sizing_result['summary']['decision_count']),
        conservation=dict(ending_equity_plus_deductions=str(decimal(account.equity)+gross),
            trading_profit=str(trading_profit), received_plus_pending=str(received+pending),
            modeled_entitlement=str(raw+rounding), exact_decimal_cash=True),
        readiness='HISTORICAL_SCENARIO_ONLY', assumptions=[
            'Actual observed dates in original order; one fresh funded account, no resampling, replacement or reselection.',
            'Evaluation pass probability, acquisition fees and evaluation strategies do not enter funded cash.',
            'Requests, gross account deductions and trader receipts are separate. Account equity and pending entitlements are not received cash.',
            'Receipts exactly at the exclusive cutoff remain pending; modeled settlement can occur after account termination.',
            'Saved fixed-signal-path approximation: account pauses/skips are not a strategy rerun. Provider rules, settlement, liquidity and future performance are not certified.'])
