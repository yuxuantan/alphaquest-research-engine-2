"""Public phase-profile contracts and single-source admission, without selection.

These are Python component interfaces, not new portal modes or dated optimizers.
The existing sampler's unit is a trading weekday, including zero-trade weekdays.
"""
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from .adapter import canonical, digest, source_record
from .phase_lifecycle import instant, session_date, validate_phase_source

CONTRACT_VERSION = 'phase-profiles-v1'
ProfileId = Literal['apex-50k-eod', 'lucidflex-50k']


@dataclass(frozen=True)
class SavedTradeSource:
    source_backtest_id: str
    trade_file: str = ''  # Explicit only: no discovery of unrelated exports.
    export_timezone: str = 'America/Chicago'


@dataclass(frozen=True)
class SourceCosts:
    mode: Literal['auto', 'source', 'override'] = 'auto'
    broker: str | None = None
    per_side: str = ''
    instrument: Literal['auto', 'NQ', 'MNQ'] = 'auto'


@dataclass(frozen=True)
class SizingConfiguration:
    """An explicit policy and decision-time loss assumptions, never P&L costs."""
    policy: dict
    initial_configured_capital: str
    planning_execution: dict

    def __post_init__(self):
        from .sizing import SizingPolicy, PlanningExecution, amount
        policy = SizingPolicy.model_validate(self.policy)
        planning = PlanningExecution.model_validate(self.planning_execution)
        if amount(self.initial_configured_capital) != Decimal('50000'):
            raise ValueError('Supported 50K profiles require initial_configured_capital of 50000; source backtest equity is not the prop account balance.')
        if planning.tick_size != Decimal('0.25'):
            raise ValueError('MNQ sizing requires tick_size 0.25 and point_value 2.')
        object.__setattr__(self, 'policy', policy.model_dump(mode='json'))
        object.__setattr__(self, 'planning_execution', planning.model_dump(mode='json'))
        object.__setattr__(self, 'initial_configured_capital', '50000')

    @property
    def needs_stop(self):
        return (self.policy['kind'] != 'fixed_contracts' or self.policy['constrain_to_account_cushion']
                or self.policy['constrain_to_daily_cushion'])

    def kernel_arguments(self, **context):
        return dict(sizing_policy=self.policy, sizing_context=dict(
            initial_configured_capital=self.initial_configured_capital,
            planning_execution=self.planning_execution, trace_context=context))


class SizingTrace:
    """Aggregate every decision; bound only retained detail, never simulation."""
    def __init__(self, configuration, limit=10000):
        self.configuration, self.limit = configuration, limit
        self.decisions = []
        self.summary = dict(decision_count=0, trade_count=0, skipped_count=0,
            min_quantity=None, max_quantity=None, quantity_counts={}, reason_counts={})

    def __call__(self, decision):
        summary = self.summary
        q = int(decision['quantity'])
        summary['decision_count'] += 1
        summary['trade_count' if q else 'skipped_count'] += 1
        summary['min_quantity'] = q if summary['min_quantity'] is None else min(q, summary['min_quantity'])
        summary['max_quantity'] = q if summary['max_quantity'] is None else max(q, summary['max_quantity'])
        summary['quantity_counts'][str(q)] = summary['quantity_counts'].get(str(q), 0)+1
        for reason in decision['reasons']:
            summary['reason_counts'][reason] = summary['reason_counts'].get(reason, 0)+1
        if len(self.decisions) < self.limit:
            self.decisions.append(decision)

    def result(self):
        return dict(configuration=asdict(self.configuration) if self.configuration is not None else None, summary=self.summary,
            decisions=self.decisions, trace_limit=self.limit,
            trace_complete=self.summary['decision_count'] <= self.limit,
            interpretation='Every simulated opportunity is aggregated; only the first retained decisions are displayed. Planning costs size quantity and are not deducted from source P&L again. Future gaps and size-dependent execution remain unverified.')


@dataclass(frozen=True)
class ResearchPeriod:
    """Inclusive CME session dates within this saved source's research period."""
    first_session: str
    last_session: str

    def __post_init__(self):
        if date.fromisoformat(self.first_session) > date.fromisoformat(self.last_session):
            raise ValueError('Research period must be ordered.')


def positive_integer(name, value, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f'{name} must be a whole integer from 1 to {maximum}.')


@dataclass(frozen=True)
class SimulationConfig:
    simulations: int = 20000
    seed: int = 42
    max_micros: int = 40

    def __post_init__(self):
        positive_integer('simulations', self.simulations, 20000)
        positive_integer('max_micros', self.max_micros, 60)
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise ValueError('seed must be a uint32 integer.')


@dataclass(frozen=True)
class SamplingConfig:
    block_weekdays: int = 5

    def __post_init__(self):
        if type(self.block_weekdays) is not int or self.block_weekdays not in (1, 5, 10):
            raise ValueError('Bootstrap block must be 1, 5 or 10 weekdays.')


@dataclass(frozen=True)
class EvaluationSamplingConfig(SamplingConfig):
    chain_simulations: int = 20000
    chain_seed: int = 45
    # Lucid only: a computational guard, never a provider evaluation deadline.
    computational_horizon_weekdays: int | None = None

    def __post_init__(self):
        super().__post_init__()
        SimulationConfig(self.chain_simulations, self.chain_seed)
        if self.chain_simulations < 2:
            raise ValueError('At least two funding chains are needed for the existing mean standard error.')
        if self.computational_horizon_weekdays is not None:
            positive_integer('computational_horizon_weekdays', self.computational_horizon_weekdays, 20000)


@dataclass(frozen=True)
class EvaluationProfile:
    profile_id: ProfileId
    rule_version: str
    evaluation_price: str
    activation_fee: str
    daily_loss_limit: bool = True


@dataclass(frozen=True)
class FundedProfile:
    profile_id: ProfileId
    rule_version: str
    daily_loss_limit: bool = True
    approval_day_counts: bool = True


@dataclass(frozen=True)
class Censoring:
    status: Literal['resolved', 'unresolved', 'censored']
    censored_paths: int | None
    reason: str | None
    # Acquisition chains can abort before returning per-path counts.
    chain_status: Literal['not_run', 'resolved', 'censored'] | None = None
    chain_censored_paths: int | None = None


@dataclass(frozen=True)
class EvaluationProfileResult:
    contract_version: str
    evaluation: dict[str, Any]
    acquisition: dict[str, Any]
    outcomes: list[str]
    duration_weekdays: list[int]
    censoring: Censoring
    provenance: dict[str, Any]


@dataclass(frozen=True)
class FundedProfileResult:
    contract_version: str
    payouts: dict[str, Any]
    survival: dict[str, Any]
    downside: dict[str, Any]
    paths: list[dict[str, Any]]
    censoring: Censoring
    provenance: dict[str, Any]


def rule_version(profile_id: ProfileId) -> str:
    """Current locally implemented rule version; no provider-policy refresh."""
    if profile_id == 'apex-50k-eod':
        from .native_analysis import MODEL_VERSION
        return MODEL_VERSION
    if profile_id == 'lucidflex-50k':
        from .lucid_rules import MODEL_VERSION
        return MODEL_VERSION
    raise ValueError('Unsupported phase account profile.')


def profile_settings(profile, costs):
    from .native_analysis import resolved_settings
    if profile.rule_version != rule_version(profile.profile_id):
        raise ValueError('Unsupported phase rule version; historical rules are not silently upgraded.')
    if type(profile.daily_loss_limit) is not bool:
        raise ValueError('daily_loss_limit must be boolean.')
    if isinstance(profile, FundedProfile) and type(profile.approval_day_counts) is not bool:
        raise ValueError('approval_day_counts must be boolean.')
    lucid = profile.profile_id == 'lucidflex-50k'
    if not lucid and not profile.daily_loss_limit:
        raise ValueError('Apex EOD requires the existing daily loss limit.')
    if lucid and isinstance(profile, FundedProfile) and not profile.approval_day_counts:
        raise ValueError('LucidFlex has no configurable approval-day exclusion.')
    overrides = dict(PROP_FIRM='Lucid' if lucid else 'Apex',
                     DAILY_LOSS_LIMIT='on' if profile.daily_loss_limit else 'off',
                     COMMISSION_MODE=costs.mode, SOURCE_INSTRUMENT=costs.instrument,
                     COMMISSION_PER_SIDE=costs.per_side)
    if costs.broker is not None:
        overrides['COMMISSION_BROKER'] = costs.broker
    if isinstance(profile, EvaluationProfile):
        for name, value in [('EVAL_PRICE', profile.evaluation_price), ('ACTIVATION_FEE', profile.activation_fee)]:
            try:
                amount = Decimal(value)
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError(f'Invalid {name}.') from exc
            if not isinstance(value, str) or not amount.is_finite() or not 0 <= amount <= 100000:
                raise ValueError(f'Invalid {name}.')
            overrides[name] = value
    else:
        overrides['APPROVAL_DAY_COUNTS'] = profile.approval_day_counts
    return resolved_settings(overrides)


def observed_session_grid(rows, period, observed_sessions):
    """Use an internally verified inventory without inventing absent sessions.

    This validates membership, not market-data completeness. The internal
    research context owns evidence that these dates belong to its saved source.
    Public callers retain the existing weekday convention by omitting it.
    """
    if observed_sessions is None:
        return pd.bdate_range(period.first_session, period.last_session)
    if type(observed_sessions) not in (list, tuple) or not observed_sessions:
        raise ValueError('Observed sessions require an explicit nonempty ordered inventory.')
    for value in observed_sessions:
        if (type(value) is not str or date.fromisoformat(value).isoformat() != value
                or not period.first_session <= value <= period.last_session):
            raise ValueError('Observed session dates must be canonical ISO dates within the research period.')
    if list(observed_sessions) != sorted(set(observed_sessions)):
        raise ValueError('Observed session dates must be ordered and unique.')
    allowed = set(observed_sessions)
    for row in rows:
        first = session_date(instant(row['entry_utc'])).isoformat()
        last = session_date(instant(row['exit_utc'])).isoformat()
        if (period.first_session <= first <= period.last_session
                or period.first_session <= last <= period.last_session):
            if first not in allowed or last not in allowed:
                raise ValueError('A source trade lies outside the verified observed session inventory.')
    return pd.DatetimeIndex(observed_sessions)


def prepare_phase_source(runs, source, profile, micros, simulation, period, costs, sizing=None,
                         observed_sessions=None, capture_metadata=False):
    """Reuse cost/risk reconciliation and dated fixed-path suitability once."""
    from .source import prepare_source
    from .commissions import adapt
    from .native_analysis import day_book
    settings = profile_settings(profile, costs)
    maximum = 60 if isinstance(profile, EvaluationProfile) and profile.profile_id == 'apex-50k-eod' else 40
    positive_integer('micros', micros, maximum)
    if micros > simulation.max_micros:
        raise ValueError('Position size exceeds the simulation exposure cap.')
    source_options = {'allow_empty': True} if observed_sessions is not None else {}
    snapshot, rows = prepare_source(runs, source.source_backtest_id, source.trade_file, source.export_timezone,
        **source_options)
    external = snapshot.get('source_kind') == 'external_trade_export'
    if sizing is not None and not isinstance(sizing, SizingConfiguration):
        raise ValueError('Sizing requires a validated SizingConfiguration.')
    adapt(snapshot, rows, settings)
    if external:
        snapshot['phase_suitability'] = dict(fixed_quantity=True,
            instrument=snapshot['commission_simulation']['source_instrument'], risk_covered_trades=len(rows),
            scaling='Exporter-declared invariant opportunity path with observed ordered mark jumps; size-dependent signals, fills and market impact are not independently verified.')
    else:
        validate_phase_source(snapshot, rows)
        if sizing is not None and sizing.needs_stop:
            raise ValueError('Native risk-based policies require a strategy rerun with account-state sizing; skipping/resizing a saved native trade path is not established as signal-invariant.')
    # Check all trades, including excluded dates: no hidden invalid source rows.
    if rows:
        source_grid, source_days, _ = day_book(rows, settings)
    elif observed_sessions is not None:
        source_grid, source_days = [], []
    else:
        raise ValueError('Empty source requires an explicit verified observed session inventory.')
    record = snapshot['backtest']
    if external:
        sessions = snapshot['canonical_manifest']['coverage']['sessions']
        first, last = map(date.fromisoformat, (sessions[0], sessions[-1]))
    else:
        first = session_date(instant(record['period_start_utc']))
        last = session_date(instant(record['period_end_utc']))
    if period is None:
        period = ResearchPeriod(first.isoformat(), last.isoformat())
    if not first.isoformat() <= period.first_session <= period.last_session <= last.isoformat():
        raise ValueError('Research period lies outside the saved backtest period.')
    grid = observed_session_grid(rows, period, observed_sessions)
    if not 1 <= len(grid) <= 20000:
        raise ValueError('Research period requires 1–20,000 session weekdays.')
    book = {stamp.date(): day for stamp, day in zip(source_grid, source_days)}
    days = [book.get(stamp.date(), []) for stamp in grid]
    if sizing is not None or capture_metadata:
        add_sizing_metadata(runs, snapshot, rows, grid, days, sizing)
    snapshot['profile_research_period'] = dict(**asdict(period), weekdays=len(grid),
        convention='CME Chicago session dates; zero-trade weekdays retained; no internal reselection or split')
    if observed_sessions is not None:
        snapshot['profile_research_period'].update(observed_sessions=list(observed_sessions),
            session_count=len(grid), convention='Exact internally verified observed CME session inventory; observed zero-trade sessions retained; absent dates are not synthesized')
    return snapshot, days, settings


def add_sizing_metadata(runs, snapshot, rows, grid, days, sizing):
    """Bind known causal facts to each source opportunity before sampling."""
    from ..trade_imports import verify_import
    from .sizing import choose_quantity, AccountSizingState
    from .sizing_runtime import decision_risk_from_metadata
    record = snapshot['backtest']
    external = snapshot.get('source_kind') == 'external_trade_export'
    canonical_source = verify_import(runs, record) if external else None
    original = {t['trade_id']: t for t in canonical_source['trades']} if external else {}
    metadata = {}
    previous_exit = None
    needs_stop = sizing is not None and sizing.needs_stop
    for row in sorted(rows, key=lambda r:(r['entry_utc'], int(r['trade_id']))):
        t = original.get(row.get('external_trade_id'))
        item = dict(source_trade_id=t['trade_id'] if t else str(row['trade_id']),
            side=t['side'] if t else None, entry_time_utc=row['entry_utc'],
            sizing_decision=t['sizing_decision'] if t else None,
            initial_stop=t['initial_stop'] if t else None,
            previous_source_exit_utc=previous_exit)
        if needs_stop:
            if not item['sizing_decision'] or not item['initial_stop']:
                raise ValueError('Risk-based sizing requires a causal decision reference and initial stop for every source trade.')
            risk = decision_risk_from_metadata(item)
            # Validate ticks/denominator/cost arithmetic even for excluded dates.
            choose_quantity(sizing.policy, AccountSizingState(initial_configured_capital='50000',
                equity_change_from_initial='0', account_floor_from_initial='-2000',
                provider_max_contracts=60, user_max_contracts=60), risk, sizing.planning_execution)
        metadata.setdefault(session_date(instant(row['entry_utc'])), []).append(item)
        previous_exit = row['exit_utc']
    for stamp, day in zip(grid, days):
        items = metadata.get(stamp.date(), [])
        if len(items) != len(day):
            raise ValueError('Sizing metadata does not match source opportunity membership.')
        # An empty frontier preserves the legacy extrema fallback when metadata
        # adds tuple fields; it does not invent an ordered path from MAE.
        day[:] = [(trade[0], trade[1], (trade[2] or ()) if len(trade)>2 else (),
                   trade[3] if len(trade)>3 else True, item) for trade, item in zip(day, items)]
    snapshot['sizing_source_check'] = dict(configuration=asdict(sizing) if sizing is not None else None,
        source_opportunities=len(rows), complete_causal_stops=needs_stop,
        actual_entry_fills_used_for_sizing=False,
        path_assumption='exporter_declared_invariant' if external else 'existing_fixed_quantity_path',
        status='compatible', native_rerun_required=False if external else needs_stop)


def verify_phase_source(runs, source, snapshot):
    """Fail closed if saved inputs mutate or disappear during calculation."""
    from hashlib import sha256
    if snapshot.get('source_kind') == 'external_trade_export':
        from ..trade_imports import verify_import
        verify_import(runs, source_record(runs, source.source_backtest_id))
    if sha256(canonical(source_record(runs, source.source_backtest_id)).encode()).hexdigest() != snapshot['manifest_sha256']:
        raise ValueError('Source manifest changed during phase simulation.')
    paths = [(runs.root / source.source_backtest_id / 'trades.csv', snapshot['trades_sha256'])]
    if snapshot.get('native_risk'):
        paths.append((runs.root / source.source_backtest_id / 'intratrade_risk.csv', snapshot['native_risk']['sha256']))
    decisions = snapshot['backtest'].get('execution_decisions')
    if decisions:
        paths.append((runs.root / source.source_backtest_id / 'execution_decisions.jsonl', decisions['sha256']))
    export = snapshot['excursion_input']
    if export['path']:
        paths.append((Path(export['path']), export['sha256']))
    if any(digest(path) != expected for path, expected in paths):
        raise ValueError('Source trades/risk/export changed during phase simulation.')


@dataclass(frozen=True)
class ReplayWindow:
    """Whole CME sessions and an exclusive civil-date cash horizon."""
    first_session: str
    cutoff_date_exclusive: str

    def __post_init__(self):
        start, end = map(date.fromisoformat, (self.first_session, self.cutoff_date_exclusive))
        if (start.isoformat() != self.first_session or end.isoformat() != self.cutoff_date_exclusive
                or not 0 < (end-start).days <= 20000):
            raise ValueError('Replay requires an ordered finite exclusive date window.')


def verify_frozen_replay(runs, source, phase, profile, micros, max_micros, costs, sizing,
                         window, calendar, binding, *, retry=None,
                         receipt_delay_calendar_days=None, receipt_amount_convention=None):
    """Verify actual frozen training artifacts and their exact outer mapping.

    The coordinator separately verifies its durable pre-access selection seal.
    A self-hashed caller dictionary alone is not accepted as a frozen choice:
    the training report, candidate manifest, inputs and implementation must agree.
    """
    from copy import deepcopy
    from hashlib import sha256
    import json
    from uuid import UUID
    from .phase_dispatch import module_for
    def fingerprint(value): return sha256(canonical(value).encode()).hexdigest()
    if type(binding) is not dict or binding.get('schema_version') != 'nested-phase-freeze-v1':
        raise ValueError('Chronological replay requires a sealed nested phase binding.')
    payload = deepcopy(binding)
    package_hash = payload.pop('package_sha256', None)
    if package_hash != fingerprint(payload) or binding.get('phase') != phase:
        raise ValueError('Frozen replay package hash or phase differs.')
    if type(window) is not ReplayWindow:
        raise ValueError('Chronological replay requires a ReplayWindow.')
    expected_window = binding['outer_window']
    if (window.first_session != expected_window['first_session']
            or window.cutoff_date_exclusive != expected_window['cutoff_date_exclusive']
            or canonical(asdict(calendar)) != canonical(binding['calendar'])):
        raise ValueError('Outer replay dates and calendar are frozen.')
    analysis_id = binding['training_analysis_id']
    if not isinstance(analysis_id, str) or UUID(analysis_id).hex != analysis_id:
        raise ValueError('Invalid frozen training analysis identifier.')
    directory = runs.root.parent/'prop_analyses'/analysis_id
    if digest(directory/'report.json') != binding['training_report_sha256']:
        raise ValueError('Frozen training report changed before outer replay.')
    report = json.loads((directory/'report.json').read_text())
    for name, info in report['files'].items():
        path = (directory/name).resolve()
        if not path.is_relative_to(directory.resolve()) or digest(path) != info['sha256']:
            raise ValueError('Frozen training report artifact changed before outer replay.')
    if (report.get('training_context', {}).get('context_sha256') != binding['training_context_sha256']
            or report['implementation'] != binding['implementation']
            or module_for(phase).implementation_identity() != binding['implementation']):
        raise ValueError('Frozen training context or numerical implementation changed.')
    selected = [row for row in report['calculations']['candidates'] if row['candidate_id'] == binding['candidate_id']]
    if len(selected) != 1:
        raise ValueError('Frozen candidate is absent or ambiguous in its actual training report.')
    manifest = selected[0]['manifest']
    config = binding['configuration']
    if (fingerprint(manifest) != binding['training_candidate_manifest_sha256']
            or canonical(manifest['configuration']) != canonical(config)
            or canonical(manifest['strategy']) != canonical(binding['strategy'])):
        raise ValueError('Frozen strategy or complete candidate configuration changed.')
    expected = dict(profile=asdict(profile), micros=micros, costs=asdict(costs),
        sizing=asdict(sizing) if sizing is not None else None)
    if any(canonical(config.get(key)) != canonical(value) for key, value in expected.items()):
        raise ValueError('Outer replay profile, quantity, costs and sizing must match the frozen choice.')
    if config['simulation']['max_micros'] != max_micros:
        raise ValueError('Outer replay exposure ceiling is frozen.')
    if phase == 'evaluation':
        if retry is None or canonical(asdict(retry)) != canonical(config['retry']):
            raise ValueError('Outer acquisition retry and activation policy is frozen.')
    elif (receipt_delay_calendar_days != report['request']['receipt_delay_calendar_days']
            or receipt_amount_convention != binding.get('receipt_amount_convention', 'kernel_entitlement_unrounded')):
        raise ValueError('Outer receipt lag and amount convention are frozen.')
    if phase == 'funded' and (date.fromisoformat(window.cutoff_date_exclusive)-date.fromisoformat(window.first_session)).days != report['request']['horizon_calendar_days']:
        raise ValueError('Outer funded cash horizon must exactly match its frozen forecast horizon.')
    record = source_record(runs, source.source_backtest_id)
    training = manifest['source']['backtest']
    if record['run_metadata'].get('source', {}).get('kind') == 'external_trade_export':
        raise ValueError('Nested native outer replay cannot invent an external OOS mapping; a separately verified external frozen-source binding is required.')
    research = record['run_metadata'].get('research', {})
    required = dict(phase='outer', role='outer_test', campaign_id=binding['campaign_id'],
        outer_fold=binding['outer_fold_index'], frozen_package_sha256=package_hash,
        training_source_id=config['source']['source_backtest_id'], selected_candidate_id=binding['candidate_id'])
    if any(research.get(key) != value for key, value in required.items()):
        raise ValueError('Outer source is outside the sealed campaign/fold/policy mapping.')
    stable_strategy = lambda value: {key:item for key,item in value.items() if key != 'session_flattening'}
    if (source.trade_file or config['source']['trade_file']
            or record['execution_settings'] != training['execution_settings']
            or stable_strategy(record['run_metadata']['strategy']) != stable_strategy(training['run_metadata']['strategy'])
            or record['run_metadata']['dataset'] != training['run_metadata']['dataset']):
        raise ValueError('Outer strategy parameters, dataset and execution must retain the frozen training identity.')
    if any(research.get('window', {}).get(key) != expected_window[key]
           for key in ('first_session', 'last_session', 'sessions')):
        raise ValueError('Outer source session membership differs from its frozen window.')
    verify_phase_source(runs, SavedTradeSource(config['source']['source_backtest_id'],
        config['source']['trade_file'], config['source']['export_timezone']), manifest['source'])
    return manifest


def prepare_chronological_source(runs, source, phase, profile, micros, max_micros, costs, sizing,
        window, calendar, frozen_binding, *, retry=None, receipt_delay_calendar_days=None,
        receipt_amount_convention=None):
    """Check a frozen native outer mapping and build its actual-date session book."""
    from datetime import timedelta
    from .cash_ledger import replay_calendar_sessions
    verify_frozen_replay(runs, source, phase, profile, micros, max_micros, costs, sizing,
        window, calendar, frozen_binding, retry=retry, receipt_delay_calendar_days=receipt_delay_calendar_days,
        receipt_amount_convention=receipt_amount_convention)
    start, cutoff = date.fromisoformat(window.first_session), date.fromisoformat(window.cutoff_date_exclusive)
    if tuple(calendar.start_dates) != (window.first_session,) or date.fromisoformat(calendar.coverage_end) < cutoff:
        raise ValueError('Chronological replay needs one exact start and complete frozen calendar coverage.')
    sessions = frozen_binding['outer_window']['sessions']
    if type(sessions) is not list or not sessions:
        raise ValueError('Chronological replay needs an explicit nonempty observed session inventory.')
    expected = [str(day) for day in replay_calendar_sessions(calendar) if start <= day < cutoff]
    if sessions != expected:
        raise ValueError('Outer observed inventory omits a declared open date; unknown gaps cannot become zero-trade sessions.')
    period = ResearchPeriod(window.first_session, str(cutoff-timedelta(days=1)))
    # The saved report can end before a weekend cash cutoff; only its actual
    # final observed session belongs in source adaptation.
    period = ResearchPeriod(period.first_session, sessions[-1])
    snapshot, days, settings = prepare_phase_source(runs, source, profile, micros,
        SimulationConfig(simulations=1, max_micros=max_micros), period, costs,
        sizing, observed_sessions=sessions, capture_metadata=True)
    snapshot['chronological_replay'] = dict(frozen_package_sha256=frozen_binding['package_sha256'],
        historical_paths=1, cutoff_date_exclusive=window.cutoff_date_exclusive,
        fixed_trace_policy_derived=sizing is None,
        assumptions='Saved fixed-signal-path historical scenario; account pauses and skips are not a strategy rerun or certified execution. No resampling or policy reselection.')
    return snapshot, dict(zip(sessions, days)), settings


def chronological_kernel_arguments(sizing, micros, callback, **tags):
    """Trace the proven equivalent fixed policy without inventing risk costs."""
    if sizing is not None:
        return dict(**sizing.kernel_arguments(**tags), trace=callback)
    return dict(sizing_policy=dict(kind='fixed_contracts', contracts=micros),
        sizing_context=dict(initial_configured_capital='50000', trace_context=tags), trace=callback)


def provenance(phase, snapshot, profile, micros, simulation, sampling, **extra):
    from hashlib import sha256
    from .native_analysis import kernel_identity
    files = ['phase_profiles.py', phase + '_profiles.py', 'native_analysis.py',
             'source.py', 'commissions.py', 'phase_lifecycle.py', 'native_engine.py',
             'sizing.py', 'sizing_runtime.py', 'cash_ledger.py', 'external_source.py', '../canonical_trades.py', '../trade_imports.py']
    if profile.profile_id == 'lucidflex-50k':
        files += ['lucid_engine.py', 'lucid_rules.py']
    kernel_file = 'lucid_engine.py' if profile.profile_id == 'lucidflex-50k' else 'native_engine.py'
    rule_identity = dict(profile=asdict(profile), rules=extra.get('rules'),
                         kernel_source=digest(Path(__file__).with_name(kernel_file)))
    return dict(phase=phase, source=snapshot, profile=asdict(profile), micros=micros,
        simulation=asdict(simulation), sampling=asdict(sampling),
        account_rule_sha256=sha256(canonical(rule_identity).encode()).hexdigest(),
        kernel=kernel_identity({'ACCOUNT_TYPE':'LucidFlex' if profile.profile_id == 'lucidflex-50k' else 'Apex EOD'}),
        implementation_sha256={name:digest(Path(__file__).parent/name) for name in files},
        rng='MT19937 / RandomState bounded integers; circular weekday blocks',
        time_unit='trading weekdays, not elapsed calendar days',
        uncertainty='Conditional Monte Carlo sampling error, not future uncertainty or verified provider parity',
        **extra)
