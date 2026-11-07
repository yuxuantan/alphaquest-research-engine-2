"""Checked native phase replay orchestration over the existing backtest engine.

No account transition, position sizing, fill arithmetic or selector lives here.
The phase owner controls admission; execute produces ordinary actual trades.
"""
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
import re
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from .adapter import canonical, source_record
from .phase_profiles import EvaluationProfile, FundedProfile, ResearchPeriod, SizingConfiguration, SourceCosts

MODEL_VERSION = 'native-phase-chronological-v1'


def defaults():
    from .automatic import profiles
    from .evaluation_optimization import SequentialRetry
    from .phase_profiles import rule_version
    result = dict(evaluation=[], funded=[])
    for profile_id, legacy in zip(('apex-50k-eod', 'lucidflex-50k'), profiles()):
        common = dict(profile_id=profile_id, rule_version=rule_version(profile_id), daily_loss_limit=True)
        result['evaluation'].append(asdict(EvaluationProfile(**common,
            evaluation_price=legacy['settings']['EVAL_PRICE'], activation_fee=legacy['settings']['ACTIVATION_FEE'])))
        result['funded'].append(asdict(FundedProfile(**common)))
    return dict(profiles=result, retry=asdict(SequentialRetry()), max_micros=40,
        receipt_delay_calendar_days=2, receipt_amount_convention='kernel_entitlement_unrounded',
        receipt_assumption='Unverified calendar-day model; review explicitly before running.')


class NativeReplayRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['native_phase_replay']
    phase: Literal['evaluation', 'funded']
    source_backtest_id: StrictStr = Field(pattern=r'^[0-9a-f]{32}$')
    profile: dict
    micros: int = Field(strict=True, ge=1, le=40)
    max_micros: int = Field(default=40, strict=True, ge=1, le=40)
    sizing: dict | None = None
    costs: dict = Field(default_factory=lambda:dict(mode='source', instrument='MNQ'))
    period: dict | None = None
    retry: dict | None = None
    receipt_delay_calendar_days: int | None = Field(default=None, strict=True, ge=0, le=365)
    receipt_amount_convention: Literal['kernel_entitlement_unrounded', 'usd_cents_half_up'] | None = None

    @model_validator(mode='after')
    def phase_contract(self):
        from .evaluation_optimization import SequentialRetry
        try:
            if self.micros > self.max_micros:
                raise ValueError('Native quantity cap cannot exceed max_micros.')
            (EvaluationProfile if self.phase == 'evaluation' else FundedProfile)(**self.profile)
            costs = SourceCosts(**self.costs)
            if costs.mode != 'source' or costs.instrument not in ('auto', 'MNQ') or costs.broker is not None or costs.per_side:
                raise ValueError('Native replay uses saved MNQ fill costs exactly once; cost replacement is unsupported.')
            if self.sizing is not None:
                SizingConfiguration(**self.sizing)
            if self.period is not None:
                period = ResearchPeriod(**self.period)
                for value in (period.first_session, period.last_session):
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError('Session dates must use YYYY-MM-DD.')
            if self.phase == 'evaluation':
                if self.receipt_delay_calendar_days is not None or self.receipt_amount_convention is not None:
                    raise ValueError('Evaluation replay does not accept Funded receipt inputs.')
                SequentialRetry(**(self.retry or {}))
            elif self.retry is not None or self.receipt_delay_calendar_days is None or self.receipt_amount_convention is None:
                raise ValueError('Funded replay requires explicit receipt delay and convention, and accepts no Evaluation retry inputs.')
        except (TypeError, KeyError) as exc:
            raise ValueError(f'Invalid native phase request: {exc}') from exc
        return self


def _instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def check_replay(datasets, runs, request):
    """Verify bytes, native identity, full observed sessions and immutable IS bounds."""
    from ..backtest_data import read_selected_bars
    from ..optimization_cache import artifacts, engine_identity, digest
    from ..reporting import json_value
    from ..research_folds import inventory_sessions, SessionDateRange
    from ..session_calendar import CT, load_calendar, resolve_calendar, session_date
    from ..strategies.registry import get_strategy
    from ..strategy import ExecutionConfig
    from .phase_profiles import profile_settings
    record = source_record(runs, request.source_backtest_id)
    meta = record['run_metadata']
    research = meta.get('research', {})
    if research.get('phase') != 'is' or record.get('native_account_control') or meta.get('source', {}).get('kind') == 'external_trade_export':
        raise ValueError('Native phase replay requires an ordinary saved native IS report, not imported trades, OOS or an account-controlled result.')
    if meta.get('execution_scenario') is not None:
        raise ValueError('Native phase replay currently requires baseline saved execution settings; stress-scenario reruns are not admitted.')
    dataset = datasets.get(meta['dataset']['id'])
    if dataset is None or any(dataset.get(k) != v for k, v in meta['dataset'].items()) or any(dataset.get(k) != v for k, v in meta['instrument'].items()):
        raise ValueError('Saved dataset or instrument identity changed; save a new IS report.')
    # Dated-contract expiration requires its own expiry calendar. Never label NQ
    # prices MNQ, or silently use the 16:00 continuous-session close on expiry.
    if not re.fullmatch(r'@?MNQ[!#12]*(?:[. ]CME)?', str(dataset.get('symbol', '')).strip().upper()):
        raise ValueError('Native replay currently requires explicit continuous/base MNQ. NQ scaling and dated-contract expiry sessions are unsupported.')
    # Normal uploads label inter-session maintenance gaps as irregular. The
    # complete per-session minute inventory below proves cadence without
    # replacing that honest dataset-wide spacing metadata.
    if dataset.get('interval_seconds') not in (None, 60):
        raise ValueError('Native replay requires one-minute bars; the saved regular interval is incompatible.')
    config = ExecutionConfig(**{k:Decimal(v) if k != 'slippage_ticks' else v for k,v in record['execution_settings'].items()})
    if config.tick_size != Decimal('.25') or config.point_value != Decimal('2') or any(Decimal(dataset['instrument_settings'][k]) != v for k,v in [('tick_size', config.tick_size), ('point_value', config.point_value)]):
        raise ValueError('Native MNQ replay requires actual MNQ tick_size=0.25 and point_value=2 in both dataset and execution settings.')
    strategy = meta['strategy']
    if strategy['id'] != 'vwap_pullback_risk_sizing':
        raise ValueError('Native account control currently supports the VWAP strategy admission hook only.')
    definition = get_strategy(strategy['id'])
    parameters = definition.parameters(strategy['parameters'])
    if not parameters.use_eod_flat or parameters.use_vol_sizing:
        raise ValueError('Native account control requires Use EOD Flat enabled and strategy-local Use Vol Sizing disabled.')
    expected = json.loads(json.dumps(definition.provenance(parameters), default=json_value))
    expected.pop('session_flattening', None)
    if any(strategy.get(k) != v for k,v in expected.items()):
        raise ValueError('Strategy implementation changed since this report; save a new IS source.')
    inventory = inventory_sessions(datasets, dataset['id'], minimum_sessions=1)
    bounds = inventory['bounds']
    first, last = _instant(record['period_start_utc']), _instant(record['period_end_utc'])
    eligible = [s for s in inventory['sessions'] if _instant(bounds[s]['first_utc']) >= first and _instant(bounds[s]['last_utc']) <= last]
    if not eligible:
        raise ValueError('The source IS report contains no complete observed CME sessions.')
    period = ResearchPeriod(**request.period) if request.period is not None else ResearchPeriod(eligible[0], eligible[-1])
    selected = [s for s in eligible if period.first_session <= s <= period.last_session]
    if not selected or selected[0] != period.first_session or selected[-1] != period.last_session:
        raise ValueError('Requested session endpoints must be whole observed sessions within the saved IS report.')
    calendar = load_calendar(symbol=dataset['symbol'])
    descriptor = resolve_calendar(dataset['symbol'])
    start, end = date.fromisoformat(period.first_session), date.fromisoformat(period.last_session)
    if (end-start).days > 366 or sum(inventory['counts'][s] for s in selected) > 510000:
        raise ValueError('Native chronological capture currently supports at most 366 calendar days and 510000 observed bars; narrow the explicit window.')
    opens, closures, plans = [], [], {}
    day = start
    while day <= end:
        plan = calendar.plan(day, parameters.eod_flat_time, parameters.close_buffer_minutes)
        if plan.close is not None:
            opens.append(str(day)); plans[day] = plan
        elif day.weekday() < 5:
            closures.append(str(day))
        day += timedelta(days=1)
    if selected != opens:
        raise ValueError('Observed sessions differ from the reviewed calendar; missing open sessions and bars on full closures cannot be fabricated.')
    # This first supported subset requires every close-labelled minute. No
    # missing bar is inferred as a venue close, no session is forward-filled.
    seen = {s:[] for s in selected}
    with read_selected_bars(datasets, dataset['id'], SessionDateRange.parse(period.first_session, period.last_session)) as source:
        for bar in source.bars:
            seen[str(session_date(bar.timestamp_utc))].append(bar.timestamp_utc)
    sessions = []
    for text in selected:
        day = date.fromisoformat(text); plan = plans[day]
        begin = datetime.combine(day-timedelta(days=1), time(17,1), CT).astimezone(timezone.utc)
        close = plan.close.astimezone(timezone.utc)
        count = int((close-begin).total_seconds()/60)+1
        stamps = seen[text]
        if len(stamps) != count or any(stamp != begin+timedelta(minutes=index) for index,stamp in enumerate(stamps)):
            raise ValueError(f'Native session {text} requires every observed minute from 17:01 Chicago through its scheduled close; incomplete/sparse sessions are unsupported.')
        sessions.append(dict(session=text, scheduled_close_utc=close.isoformat(), calendar_version=descriptor['id']+'-reviewed-csv-v1',
            calendar_sha256=calendar.sha256, observed_bar_count=count, fully_observed_or_flat_after_entry_cutoff=True))
    sizing = SizingConfiguration(**request.sizing) if request.sizing is not None else SizingConfiguration(
        policy=dict(kind='fixed_contracts', contracts=request.micros), initial_configured_capital='50000',
        planning_execution=dict(tick_size='0.25', point_value='2', entry_slippage_ticks=config.slippage_ticks,
            stop_exit_slippage_ticks=config.slippage_ticks, commission_per_contract_per_side=str(config.commission_per_contract_per_side)))
    planning = sizing.planning_execution
    if (Decimal(planning['tick_size']) != config.tick_size or Decimal(planning['point_value']) != config.point_value
            or Decimal(planning['commission_per_contract_per_side']) != config.commission_per_contract_per_side
            or planning['entry_slippage_ticks'] != config.slippage_ticks
            or planning['stop_exit_slippage_ticks'] != config.slippage_ticks):
        raise ValueError('Native planning costs must match the saved execution tick, point value, commission and entry/stop slippage. Planning sensitivity is unsupported.')
    profile = (EvaluationProfile if request.phase == 'evaluation' else FundedProfile)(**request.profile)
    profile_settings(profile, SourceCosts(mode='source', instrument='MNQ'))
    # Instantiate the owner before reservation so unsupported profile/retry
    # behavior fails during Check, not after a queued calculation.
    from .rule_provenance import profile_review
    result = dict(model_version=MODEL_VERSION, phase=request.phase, source=record, provider_rule_review=profile_review(profile, request.phase),
        source_manifest_sha256=digest(record), source_artifacts=artifacts(runs.root, record), engine_identity=engine_identity(),
        dataset=dataset, period=asdict(period), sessions=sessions, sizing=asdict(sizing),
        calendar=dict(start_dates=(str(start),), coverage_end=str(end), closures=tuple(closures),
            timezone='America/Chicago', version=descriptor['id']+'-'+calendar.sha256),
        calendar_mapping=descriptor, calendar_metadata=calendar.metadata(),
        source_check=dict(status='compatible', source_kind='native_strategy_rerun', actual_instrument='MNQ',
            observed_sessions=len(sessions), observed_bars=sum(s['observed_bar_count'] for s in sessions),
            sizing_uses_future_fill=False, costs_charged_once=True, cold_strategy_start=True,
            complete_minute_sessions=True, historical_paths=1, recommendation=False,
            limitations=['Continuous/base MNQ, one-minute complete sessions, VWAP EOD-flat only.',
                'Strategy starts cold at the first retained source bar; prior source results do not enter sizing.',
                'Historical scenario only; native Monte Carlo and policy selection are not implemented by this mode.',
                'Provider rules, OHLC ordering and payout settlement assumptions remain unverified.']))
    make_controller(request, result)
    return result


def make_controller(request, check):
    from .native_control import SessionContext
    from .phase_search import PhaseCalendar
    from .evaluation_optimization import SequentialRetry
    from .phase_dispatch import module_for
    module_for(request.phase)
    contexts = {date.fromisoformat(s['session']):SessionContext(**{**s, 'session':date.fromisoformat(s['session']),
        'scheduled_close_utc':_instant(s['scheduled_close_utc'])}) for s in check['sessions']}
    common = dict(max_micros=request.max_micros, session_contexts=contexts,
        start_date=check['period']['first_session'],
        cutoff_date_exclusive=str(date.fromisoformat(check['period']['last_session'])+timedelta(days=1)))
    # Dispatch resolves optimizer contracts; simulation owners remain explicit.
    if request.phase == 'evaluation':
        from .evaluation_profiles import NativeEvaluationController
        return NativeEvaluationController(EvaluationProfile(**request.profile), SizingConfiguration(**check['sizing']), request.micros,
            **common, calendar=PhaseCalendar(**check['calendar']), retry=SequentialRetry(**(request.retry or {})))
    from .funded_profiles import NativeFundedController
    return NativeFundedController(FundedProfile(**request.profile), SizingConfiguration(**check['sizing']), request.micros,
        **common, receipt_delay_calendar_days=request.receipt_delay_calendar_days, receipt_amount_convention=request.receipt_amount_convention)


def run_replay(analyses, datasets, runs, id, request, expected, staged):
    from ..backtest_api import run_backtest
    from ..optimization_cache import digest
    from ..research_folds import SessionDateRange
    from ..strategies.registry import get_strategy
    from ..strategy import ExecutionConfig
    check = check_replay(datasets, runs, request)
    if canonical(check) != canonical(expected):
        raise ValueError('Native source or engine changed after submission.')
    source = check['source']; strategy = source['run_metadata']['strategy']
    definition = get_strategy(strategy['id'])
    config = ExecutionConfig(**{k:Decimal(v) if k != 'slippage_ticks' else v for k,v in source['execution_settings'].items()})
    controller = make_controller(request, check)
    run_id = uuid4().hex
    with analyses.lock, analyses.connect() as db:
        db.execute('INSERT INTO analysis_sources VALUES (?,?)', (id, run_id))
    control_metadata = dict(version=MODEL_VERSION, analysis_id=id, source_backtest_id=source['id'],
        request=request.model_dump(), source_check_sha256=digest(check), engine_identity=check['engine_identity'])
    try:
        record = run_backtest(datasets, runs, run_id, check['dataset'], definition, definition.parameters(strategy['parameters']), config,
            SessionDateRange.parse(check['period']['first_session'], check['period']['last_session']),
            lambda stage,processed,total:analyses._update(id, 'running', f'Native {request.phase}: {stage} {processed}/{total}'),
            reuse_results=False, prop_analyses=None, account_control=controller, control_metadata=control_metadata,
            research=dict(phase='native_phase_replay', role='account_controlled_historical_scenario',
                source_backtest_id=source['id'], analysis_id=id, period=check['period'], recommendation=False))
    except Exception:
        if runs.get(run_id) is None:
            with analyses.connect() as db:
                db.execute('DELETE FROM analysis_sources WHERE analysis_id=? AND source_id=?', (id, run_id))
        raise
    if canonical(check_replay(datasets, runs, request)) != canonical(expected):
        raise ValueError('Native source or engine changed during execution; child report is retained for inspection, no phase report published.')
    result = controller.finish_replay()
    from .rule_provenance import VERSION as REVIEW_VERSION, readiness
    rule_review = dict(version=REVIEW_VERSION, status='UNVERIFIED', production_qualified=False,
        profiles=[check['provider_rule_review']])
    import shutil
    for name in ('trades.csv', 'equity.csv', 'intratrade_risk.csv', 'execution_decisions.jsonl'):
        shutil.copyfile(runs.root/run_id/name, staged/name)
    for name,value in [('request.json', request.model_dump()), ('source_check.json', check),
        ('native_result.json', result), ('control_events.json', result['control_events']),
        ('sizing_decisions.json', result['sizing_decisions']), ('session_trace.json', result['trace']), ('cash_ledger.json', result['cash_ledger'])]:
        (staged/name).write_text(canonical(value), encoding='utf-8')
    return dict(format_version=6, model_version=MODEL_VERSION, engine='AlphaQuest local native strategy and phase controllers',
        settings=dict(ANALYSIS_MODE=request.mode, PHASE=request.phase), request=request.model_dump(), source=check,
        native_backtest_id=run_id, native_backtest=record, calculations=result,
        provider_rules=rule_review, deployment_readiness=readiness(rule_review),
        production_qualified=False, engine_identity=check['engine_identity'])
