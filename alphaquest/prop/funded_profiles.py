"""Fresh-funded orchestration; acquisition inputs never enter these runners."""
import numpy as np

from .phase_profiles import (
    CONTRACT_VERSION, Censoring, FundedProfile, FundedProfileResult, ResearchPeriod,
    SamplingConfig, SavedTradeSource, SimulationConfig, SourceCosts,
    positive_integer, prepare_phase_source, provenance, verify_phase_source,
)


def simulate_funded_profile(
    runs, source: SavedTradeSource, profile: FundedProfile, micros: int,
    horizon_weekdays: int,
    simulation: SimulationConfig = SimulationConfig(),
    period: ResearchPeriod | None = None,
    sampling: SamplingConfig = SamplingConfig(),
    costs: SourceCosts = SourceCosts(),
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
    snapshot, days, settings = prepare_phase_source(runs, source, profile, micros, simulation, period, costs)
    if profile.profile_id == 'lucidflex-50k':
        from .lucid_backend import Rules as LucidRules
        rules = LucidRules(daily_loss=1200. if profile.daily_loss_limit else None)
    else:
        rules = replace(Rules(), approval_day_counts=profile.approval_day_counts)
    backend = account_backend(rules)
    accounts = (backend.funded if backend else funded)(days, micros, simulation.simulations,
        simulation.seed, sampling.block_weekdays, horizon=horizon_weekdays,
        rules=rules, max_micros=simulation.max_micros)
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
            selection='None; one requested source, profile and size'))


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
        period=None, sampling=SamplingConfig(), costs=SourceCosts()):
    """Dated fresh-account paths using the same native funded transitions.

    The legacy weekday interface above remains unchanged. Dates are civil session
    labels, not inferred intraday execution/settlement timestamps. Each path has
    its own addressed RNG; termination never changes another path's schedule.
    """
    from dataclasses import asdict, replace
    from datetime import date, timedelta
    from hashlib import sha256
    from . import native_engine, lucid_engine
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
    snapshot, days, _ = prepare_phase_source(runs, source, profile, micros, simulation, period, costs)
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
                if lucid:
                    account.advance(days[index], micros, simulation.max_micros, calendar_day=offset)
                else:
                    account.advance(days[index], micros, simulation.max_micros)
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
    verify_phase_source(runs, source, snapshot)
    result = dict(paths=paths, schedule_sha256=schedule.hexdigest(),
        provenance=provenance('funded', snapshot, profile, micros, simulation, sampling,
            rules=asdict(rules), horizon_calendar_days=horizon_calendar_days,
            calendar=asdict(calendar), receipt_delay_calendar_days=receipt_delay_calendar_days,
            dated_kernel='Python reference FundedAccount.advance; identical native qualification/tier/drawdown/payout policy',
            dated_clock='Chicago civil session dates; daily resolution, event age is date minus start date; exclusive cutoff',
            dated_rng='MT19937 seeded by SeedSequence([seed,path_index]); circular source-session blocks; no paired inference claim',
            settlement='Automatic request/deduction on native eligibility date; entitlement paid after declared civil-day lag, including weekends and after account closure; unverified scenario',
            initial_state='Fresh funded account at t=0; no evaluation, acquisition or replacement'))
    result['provenance']['time_unit'] = 'Chicago civil calendar days, not session counts'
    result['provenance']['kernel'] = dict(name='python-reference', source='lucid_engine.py' if lucid else 'native_engine.py')
    return result
