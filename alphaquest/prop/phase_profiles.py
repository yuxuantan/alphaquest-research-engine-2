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


def prepare_phase_source(runs, source, profile, micros, simulation, period, costs):
    """Reuse cost/risk reconciliation and dated fixed-path suitability once."""
    from .source import prepare_source
    from .commissions import adapt
    from .native_analysis import day_book
    settings = profile_settings(profile, costs)
    maximum = 60 if isinstance(profile, EvaluationProfile) and profile.profile_id == 'apex-50k-eod' else 40
    positive_integer('micros', micros, maximum)
    if micros > simulation.max_micros:
        raise ValueError('Position size exceeds the simulation exposure cap.')
    snapshot, rows = prepare_source(runs, source.source_backtest_id, source.trade_file, source.export_timezone)
    adapt(snapshot, rows, settings)
    validate_phase_source(snapshot, rows)
    # Check all trades, including excluded dates: no hidden invalid source rows.
    source_grid, source_days, _ = day_book(rows, settings)
    record = snapshot['backtest']
    first = session_date(instant(record['period_start_utc']))
    last = session_date(instant(record['period_end_utc']))
    if period is None:
        period = ResearchPeriod(first.isoformat(), last.isoformat())
    if not first.isoformat() <= period.first_session <= period.last_session <= last.isoformat():
        raise ValueError('Research period lies outside the saved backtest period.')
    grid = pd.bdate_range(period.first_session, period.last_session)
    if not 1 <= len(grid) <= 20000:
        raise ValueError('Research period requires 1–20,000 session weekdays.')
    book = {stamp.date(): day for stamp, day in zip(source_grid, source_days)}
    days = [book.get(stamp.date(), []) for stamp in grid]
    snapshot['profile_research_period'] = dict(**asdict(period), weekdays=len(grid),
        convention='CME Chicago session dates; zero-trade weekdays retained; no internal reselection or split')
    return snapshot, days, settings


def verify_phase_source(runs, source, snapshot):
    """Fail closed if saved inputs mutate or disappear during calculation."""
    from hashlib import sha256
    if sha256(canonical(source_record(runs, source.source_backtest_id)).encode()).hexdigest() != snapshot['manifest_sha256']:
        raise ValueError('Source manifest changed during phase simulation.')
    paths = [(runs.root / source.source_backtest_id / 'trades.csv', snapshot['trades_sha256'])]
    if snapshot.get('native_risk'):
        paths.append((runs.root / source.source_backtest_id / 'intratrade_risk.csv', snapshot['native_risk']['sha256']))
    export = snapshot['excursion_input']
    if export['path']:
        paths.append((Path(export['path']), export['sha256']))
    if any(digest(path) != expected for path, expected in paths):
        raise ValueError('Source trades/risk/export changed during phase simulation.')


def provenance(phase, snapshot, profile, micros, simulation, sampling, **extra):
    from hashlib import sha256
    from .native_analysis import kernel_identity
    files = ['phase_profiles.py', phase + '_profiles.py', 'native_analysis.py',
             'source.py', 'commissions.py', 'phase_lifecycle.py', 'native_engine.py']
    if profile.profile_id == 'lucidflex-50k':
        files += ['lucid_engine.py', 'lucid_rules.py']
    kernel_file = 'lucid_engine.py' if profile.profile_id == 'lucidflex-50k' else 'native_engine.py'
    rule_identity = dict(profile=asdict(profile), rules=extra.get('rules'),
                         kernel_source=digest(Path(__file__).with_name(kernel_file)))
    return dict(phase=phase, source=snapshot, profile=asdict(profile), micros=micros,
        simulation=asdict(simulation), sampling=asdict(sampling),
        account_rule_sha256=sha256(canonical(rule_identity).encode()).hexdigest(),
        kernel=kernel_identity({'ACCOUNT_TYPE':'LucidFlex' if profile.profile_id == 'lucidflex-50k' else 'Apex EOD'}),
        implementation_sha256={name:digest(Path(__file__).with_name(name)) for name in files},
        rng='MT19937 / RandomState bounded integers; circular weekday blocks',
        time_unit='trading weekdays, not elapsed calendar days',
        uncertainty='Conditional Monte Carlo sampling error, not future uncertainty or verified provider parity',
        **extra)
