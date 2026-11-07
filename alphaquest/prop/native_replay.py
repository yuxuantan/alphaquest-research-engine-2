"""Checked native phase replay orchestration over the existing backtest engine.

No account transition, position sizing, fill arithmetic or selector lives here.
The phase owner controls admission; execute produces ordinary actual trades.
"""
from dataclasses import asdict, dataclass
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
MAX_FORECAST_BAR_WORK = 10_000_000
MAX_FORECAST_SCHEDULE_BYTES = 16 * 1024 * 1024
MAX_FORECAST_CAPTURE_ESTIMATE = 100 * 1024 * 1024


@dataclass(frozen=True)
class DeclaredNativeCalendar:
    """Delegate close arithmetic while retaining honest modeled provenance."""
    calendar: object
    declaration_json: str

    @property
    def sha256(self):
        return self.calendar.sha256

    def plan(self, *args, **kwargs):
        return self.calendar.plan(*args, **kwargs)

    def metadata(self):
        return dict(kind='modeled', observed=False, exchange_verified=False,
            sha256=self.sha256, declaration=json.loads(self.declaration_json),
            coverage_start=str(self.calendar.start), coverage_end=str(self.calendar.end))


class NativeForecastRequest(BaseModel):
    """Explicit fitted source-block law, separate from the observed replay."""
    model_config = ConfigDict(extra='forbid', frozen=True)
    model: Literal['observed_contiguous_blocks_with_prior_prefix_v1']
    simulations: int = Field(strict=True, ge=2, le=512)
    seed: int = Field(strict=True, ge=0, le=2**32-1)
    block_sessions: int = Field(strict=True)
    calendar: dict
    early_closes: dict[StrictStr, StrictStr] = Field(default_factory=dict)
    horizon_calendar_days: int = Field(strict=True, ge=1, le=365)
    capture_paths: int = Field(strict=True, ge=1, le=20)

    @model_validator(mode='after')
    def declared_law(self):
        from .phase_search import PhaseCalendar
        if self.block_sessions not in (1, 5, 10):
            raise ValueError('Native source blocks must contain 1, 5 or 10 consecutive observed sessions.')
        try:
            raw = dict(self.calendar)
            if 'version' not in raw:
                raise ValueError('The modeled target calendar requires an explicit saved version label.')
            for field in ('start_dates', 'closures'):
                if field in raw:
                    if type(raw[field]) is not list or any(type(value) is not str for value in raw[field]):
                        raise ValueError(f'Modeled calendar {field} must be an array of canonical date strings.')
                    raw[field] = tuple(raw[field])
            calendar = PhaseCalendar(**raw)
        except (TypeError, KeyError) as exc:
            raise ValueError(f'Invalid modeled native calendar: {exc}') from exc
        if len(calendar.start_dates) > 16 or self.simulations % len(calendar.start_dates):
            raise ValueError('Declare at most 16 start dates and an equal number of paths per start cohort; simulations is the total path count.')
        try:
            cutoff = max(map(date.fromisoformat, calendar.start_dates))+timedelta(days=self.horizon_calendar_days)
        except OverflowError as exc:
            raise ValueError('Forecast horizon exceeds supported calendar dates.') from exc
        if cutoff > date.fromisoformat(calendar.coverage_end):
            raise ValueError('The modeled calendar must cover every exclusive forecast cutoff.')
        if self.capture_paths > self.simulations:
            raise ValueError('Retained detailed paths cannot exceed total simulations.')
        first = min(calendar.start_dates)
        for day, close in self.early_closes.items():
            if (date.fromisoformat(day).isoformat() != day or not first <= day <= calendar.coverage_end
                    or date.fromisoformat(day).weekday() > 4 or day in calendar.closures
                    or not re.fullmatch(r'(?:0[0-9]|1[0-5]):[0-5][0-9]', close)):
                raise ValueError('Declare unique weekday early closes before 16:00 Chicago, inside target calendar coverage and outside full closures.')
        return self

    def target_calendar(self):
        """Use shared close/cutoff semantics without claiming exchange review."""
        from types import MappingProxyType
        from ..session_calendar import SessionCalendar
        from ..optimization_cache import digest
        entries = {date.fromisoformat(day):MappingProxyType(dict(closure_type='full_close', close_time_local=''))
            for day in self.calendar.get('closures', [])}
        entries.update({date.fromisoformat(day):MappingProxyType(dict(closure_type='early_close', close_time_local=close))
            for day,close in self.early_closes.items()})
        declaration = dict(calendar=self.calendar, early_closes=self.early_closes,
            regular_close='16:00', timezone='America/Chicago', status='USER_DECLARED_UNVERIFIED')
        calendar = SessionCalendar(min(map(date.fromisoformat, self.calendar['start_dates'])),
            date.fromisoformat(self.calendar['coverage_end']), MappingProxyType(entries), digest(declaration), 'Modeled MNQ')
        return DeclaredNativeCalendar(calendar, canonical(declaration))


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
        receipt_assumption='Unverified calendar-day model; review explicitly before running.',
        native_forecast=dict(model='observed_contiguous_blocks_with_prior_prefix_v1', simulations=32,
            seed=1729, block_sessions=1, supported_block_sessions=[1,5,10], horizon_calendar_days=30,
            capture_paths=1, calendar_version='user-declared-native-weekdays-v1',
            limits=dict(bar_work=MAX_FORECAST_BAR_WORK, schedule_bytes=MAX_FORECAST_SCHEDULE_BYTES,
                estimated_capture_bytes=MAX_FORECAST_CAPTURE_ESTIMATE),
            weighting='Total paths divided equally across sorted start-date cohorts; every path enters the mean.',
            calendar_status='USER_DECLARED_UNVERIFIED'))


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
    native_forecast: NativeForecastRequest | None = None

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
                'The historical replay is one observed path. An optional native forecast is saved separately; native policy selection remains unsupported.',
                'Provider rules, OHLC ordering and payout settlement assumptions remain unverified.']))
    make_controller(request, result)
    if request.native_forecast is not None:
        result['native_forecast_plan'], _, _ = prepare_native_forecast(datasets, request, result)
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


def prepare_native_forecast(datasets, request, check):
    """Build all addressed schedules before queueing; never execute a strategy."""
    from ..backtest_data import read_selected_bars
    from ..research_folds import SessionDateRange
    from ..session_calendar import CT
    from ..strategies.registry import get_strategy
    from ..optimization_cache import digest
    from .native_control import SessionContext, json_native
    from .native_draws import build_catalogue, build_schedule
    forecast = request.native_forecast
    if forecast is None:
        raise ValueError('An explicit native forecast declaration is required.')
    starts = sorted(forecast.calendar['start_dates'])
    if starts[0] <= check['period']['last_session']:
        raise ValueError('Every modeled forecast start must follow the last admitted source IS session.')
    source = check['source']; strategy = source['run_metadata']['strategy']
    parameters = get_strategy(strategy['id']).parameters(strategy['parameters'])
    source_contexts = {date.fromisoformat(row['session']):SessionContext(**{**row,
        'session':date.fromisoformat(row['session']), 'scheduled_close_utc':_instant(row['scheduled_close_utc'])})
        for row in check['sessions']}
    source_identity = dict(source_backtest_id=source['id'], source_manifest_sha256=check['source_manifest_sha256'],
        dataset_sha256=check['dataset']['sha256'], source_period=check['period'], strategy=strategy,
        execution=source['execution_settings'], source_calendar=check['calendar_metadata'],
        engine_identity=check['engine_identity'])
    with read_selected_bars(datasets, check['dataset']['id'],
            SessionDateRange.parse(check['period']['first_session'], check['period']['last_session'])) as selected:
        catalogue = build_catalogue(selected.bars, source_contexts, parameters,
            block_sessions=forecast.block_sessions, source_identity=source_identity)
    calendar = forecast.target_calendar()
    cohorts, cohort_rows = {}, []
    for text in starts:
        start = date.fromisoformat(text); cutoff = start+timedelta(days=forecast.horizon_calendar_days)
        contexts = {}; day = start
        while day < cutoff:
            plan = calendar.plan(day, parameters.eod_flat_time, parameters.close_buffer_minutes)
            if plan.close is not None:
                close = plan.close.astimezone(timezone.utc)
                begin = datetime.combine(day-timedelta(days=1), time(17,1), CT).astimezone(timezone.utc)
                expected = int((close-begin).total_seconds()/60)+1
                contexts[day] = SessionContext(day, close, forecast.calendar['version'], calendar.sha256,
                    0, False, kind='modeled', expected_bar_count=expected)
            day += timedelta(days=1)
        if not contexts:
            raise ValueError('Native forecast currently requires at least one modeled open session per cohort; no target bars or zero-session account outcome are invented.')
        cohorts[text] = contexts
        cohort_rows.append(dict(start_date=text, cutoff_date_exclusive=str(cutoff),
            modeled_open_sessions=len(contexts), paths=forecast.simulations//len(starts),
            context_kind='modeled', observed_target_bars=0,
            contexts=[json_native(asdict(row)) for row in contexts.values()]))
    schedules = []; warmup = executed = validation = schedule_bytes = captured_bars = 0
    for index in range(forecast.simulations):
        start = starts[index % len(starts)]
        schedule = build_schedule(catalogue, cohorts[start], parameters, phase=request.phase,
            seed=forecast.seed, path_index=index, start_date=start,
            cutoff_date_exclusive=str(date.fromisoformat(start)+timedelta(days=forecast.horizon_calendar_days)))
        warmup += schedule['estimated_warmup_bars']; executed += schedule['estimated_executed_bars']
        validation += len(catalogue.bars)
        schedule_bytes += len(canonical(json_native(schedule)).encode())
        if index < forecast.capture_paths:
            captured_bars += schedule['estimated_executed_bars']
        if warmup+executed+validation > MAX_FORECAST_BAR_WORK:
            raise ValueError(f'Native forecast exceeds {MAX_FORECAST_BAR_WORK} declared source-validation, warmup and execution bar work. Reduce paths, source window, target horizon or block resets; no paths were truncated.')
        if schedule_bytes > MAX_FORECAST_SCHEDULE_BYTES:
            raise ValueError('Native forecast schedules exceed 16 MiB; reduce the declared work. No pool members or schedules were omitted.')
        if captured_bars * 2048 > MAX_FORECAST_CAPTURE_ESTIMATE:
            raise ValueError('Native detailed-path capture estimate exceeds 100 MiB; reduce capture_paths or target horizon. Every path still belongs in the aggregate.')
        schedules.append(schedule)
    plan = dict(schema_version='native-forecast-plan-v1', request=forecast.model_dump(mode='json'),
        catalogue=catalogue.metadata(), target_calendar=calendar.metadata(), cohorts=cohort_rows,
        simulations=forecast.simulations, paths_per_cohort=forecast.simulations//len(starts),
        cohort_assignment='path_index modulo sorted start-date count; equal path/cohort weights',
        schedules=json_native(schedules), retained_path_indices=list(range(forecast.capture_paths)),
        work=dict(source_validation_bars=validation, warmup_bars=warmup, executed_bars=executed,
            total_bar_work=validation+warmup+executed, schedule_bytes=schedule_bytes,
            retained_path_executed_bars=captured_bars, estimated_capture_bytes=captured_bars*2048,
            capture_estimate='Preflight allowance, not a promise of encoded size; publication also enforces the existing 128 MiB artifact limit.',
            bar_work_limit=MAX_FORECAST_BAR_WORK, schedule_bytes_limit=MAX_FORECAST_SCHEDULE_BYTES),
        limitations=['Modeled future dates have no observed bars and are not a verified exchange calendar.',
            'Actual source prices/timestamps are preserved. Signal state resets once per block with prior-only original-source feature warmup.',
            'Provider state and original trading cash continue across blocks; no redraw is allowed after an execution failure.',
            'Monte Carlo error conditions on this fitted block law and excludes historical-law, execution, provider and future uncertainty.',
            'Native policy selection, historical-mean refitting and final procedure qualification remain separate unfinished work.'])
    plan['plan_sha256'] = digest(plan)
    return plan, catalogue, cohorts


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
    result = controller.finish_replay()
    forecast_result = None
    if request.native_forecast is not None:
        plan, catalogue, cohorts = prepare_native_forecast(datasets, request, check)
        if canonical(plan) != canonical(expected['native_forecast_plan']):
            raise ValueError('Native forecast schedule or source changed after its preflight.')
        parameters = definition.parameters(strategy['parameters'])
        factory = lambda:definition.create(parameters, config, instrument_symbol=check['dataset']['symbol'])
        common = dict(forecast=request.native_forecast, max_micros=request.max_micros,
            progress=lambda message:analyses._update(id, 'running', message))
        if request.phase == 'evaluation':
            from .evaluation_profiles import forecast_native_evaluation
            from .evaluation_optimization import SequentialRetry
            forecast_result = forecast_native_evaluation(catalogue, cohorts, factory, config,
                EvaluationProfile(**request.profile), SizingConfiguration(**check['sizing']), request.micros,
                retry=SequentialRetry(**(request.retry or {})), **common)
        else:
            from .funded_profiles import forecast_native_funded
            forecast_result = forecast_native_funded(catalogue, cohorts, factory, config,
                FundedProfile(**request.profile), SizingConfiguration(**check['sizing']), request.micros,
                receipt_delay_calendar_days=request.receipt_delay_calendar_days,
                receipt_amount_convention=request.receipt_amount_convention, **common)
        if canonical(forecast_result['schedules']) != canonical(plan['schedules']):
            raise ValueError('Native forecast execution did not use the complete checked schedules.')
        forecast_result['plan_sha256'] = plan['plan_sha256']
        forecast_result['target_calendar'] = plan['target_calendar']
        forecast_result['work'] = plan['work']
        for name,value in [('native_forecast_plan.json', plan), ('native_forecast.json', forecast_result),
                ('native_forecast_paths.json', forecast_result['paths']),
                ('native_forecast_schedules.json', forecast_result['schedules']),
                ('native_forecast_captures.json', forecast_result['captures'])]:
            (staged/name).write_text(canonical(value), encoding='utf-8')
    if canonical(check_replay(datasets, runs, request)) != canonical(expected):
        raise ValueError('Native source or engine changed during execution; child report is retained for inspection, no phase report published.')
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
    report = dict(format_version=6, model_version=MODEL_VERSION, engine='AlphaQuest local native strategy and phase controllers',
        settings=dict(ANALYSIS_MODE=request.mode, PHASE=request.phase), request=request.model_dump(), source=check,
        native_backtest_id=run_id, native_backtest=record, calculations=result,
        provider_rules=rule_review, deployment_readiness=readiness(rule_review),
        production_qualified=False, engine_identity=check['engine_identity'])
    if forecast_result is not None:
        report['native_forecast'] = forecast_result
    return report
