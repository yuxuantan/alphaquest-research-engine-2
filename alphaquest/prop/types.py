"""Strict immutable values for prop rules and future simulation requests.

These types contain no replay, strategy, persistence, or account transitions.
Python constructors require Decimal/date/time values; wire readers require exact
decimal/date/time strings and reject unknown fields instead of coercing them.
"""

from dataclasses import dataclass, field, fields
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from types import UnionType
from typing import Literal, get_args, get_origin, get_type_hints
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

from ..decimal_math import add


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _decimal(name, value, *, minimum=None, maximum=None, positive=False):
    _require(type(value) is Decimal and value.is_finite(), f"{name} must be a finite Decimal.")
    if positive:
        _require(value > 0, f"{name} must be positive.")
    if minimum is not None:
        _require(value >= minimum, f"{name} must be >= {minimum}.")
    if maximum is not None:
        _require(value <= maximum, f"{name} must be <= {maximum}.")


def _integer(name, value, minimum=1):
    _require(type(value) is int and value >= minimum, f"{name} must be an integer >= {minimum}.")


def _text(name, value):
    _require(type(value) is str and bool(value.strip()) and value == value.strip(),
             f"{name} must be nonempty text without surrounding whitespace.")


def _url(name, value):
    _text(name, value)
    parsed = urlsplit(value)
    _require(parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password,
             f"{name} must be an HTTPS source URL.")


def _utc(name, value):
    _require(type(value) is datetime and value.tzinfo is not None and value.utcoffset() == timedelta(0),
             f"{name} must be an aware UTC datetime.")


def _hash(name, value):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             f"{name} must be a lowercase SHA-256 hex digest.")


def _canonical_decimal(value):
    # normalize() uses ambient precision and can round! Manipulate digits only.
    if not value:
        return "0"
    sign, digits, exponent = value.as_tuple()
    digits = list(digits)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    coefficient = ("-" if sign else "") + "".join(map(str, digits))
    return coefficient if exponent == 0 else f"{coefficient}e{exponent}"


def _encode(value):
    if isinstance(value, Value):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value)
                if not (f.metadata.get("omit_none") and getattr(value, f.name) is None)}
    if type(value) is Decimal:
        return _canonical_decimal(value)
    if type(value) is datetime:
        return value.isoformat().replace("+00:00", "Z")
    if type(value) in (date, time):
        return value.isoformat()
    if type(value) is tuple:
        return [_encode(item) for item in value]
    return value


def _typed(name, value, annotation):
    """Validate Python values recursively, including all immutable containers."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is UnionType:
        for option in args:
            try:
                _typed(name, value, option)
                return
            except ValueError:
                pass
        raise ValueError(f"{name} has an unsupported type or value.")
    if origin is Literal:
        _require(any(type(value) is type(item) and value == item for item in args),
                 f"{name} must be one of {args}.")
    elif origin is tuple:
        _require(type(value) is tuple, f"{name} must be an immutable tuple.")
        for i, item in enumerate(value):
            _typed(f"{name}[{i}]", item, args[0])
    elif annotation is type(None):
        _require(value is None, f"{name} must be None.")
    else:
        _require(type(value) is annotation, f"{name} must be {annotation.__name__}.")
        if annotation is Decimal:
            _decimal(name, value)
        elif annotation is datetime:
            _utc(name, value)
        elif annotation is time:
            _require(value.tzinfo is None and value.fold == 0, f"{name} must be a naive local wall time.")
        elif annotation is str:
            _text(name, value)


def _decode(name, value, annotation):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is UnionType:
        for option in args:
            try:
                return _decode(name, value, option)
            except ValueError:
                pass
        raise ValueError(f"{name} has an unsupported wire value.")
    if origin is tuple:
        _require(type(value) is list, f"{name} must be a JSON array.")
        return tuple(_decode(f"{name}[{i}]", item, args[0]) for i, item in enumerate(value))
    if isinstance(annotation, type) and issubclass(annotation, Value):
        return annotation.from_dict(value)
    if annotation in (Decimal, date, time, datetime):
        _require(type(value) is str, f"{name} must be an exact string.")
        try:
            if annotation is Decimal:
                _require(re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value) is not None,
                         f"{name} must be a decimal string.")
                result = Decimal(value)
            elif annotation is date:
                _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None, f"{name} must use YYYY-MM-DD.")
                result = date.fromisoformat(value)
            elif annotation is time:
                _require(re.fullmatch(r"\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?", value) is not None,
                         f"{name} must use HH:MM:SS.")
                result = time.fromisoformat(value)
            else:
                _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value) is not None,
                         f"{name} must use a UTC ISO timestamp ending in Z.")
                result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, ArithmeticError) as exc:
            raise ValueError(f"Invalid {name}: {exc}") from None
        _typed(name, result, annotation)
        return result
    _typed(name, value, annotation)
    return value


class Value:
    __slots__ = ()

    def __post_init__(self):
        for name, annotation in get_type_hints(type(self)).items():
            _typed(name, getattr(self, name), annotation)

    def to_dict(self):
        """Return a detached JSON-compatible copy, never internal mutable state."""
        return _encode(self)

    @classmethod
    def from_dict(cls, payload):
        _require(type(payload) is dict, f"{cls.__name__} must be an object.")
        annotations = get_type_hints(cls)
        _require(payload.keys() == annotations.keys(),
                 f"{cls.__name__} must contain exactly: {', '.join(annotations)}.")
        return cls(**{name: _decode(name, payload[name], annotation) for name, annotation in annotations.items()})


@dataclass(frozen=True, slots=True)
class RuleSource(Value):
    id: str
    url: str
    retrieved_on: date
    effective_on: date | None = None

    def __post_init__(self):
        super(RuleSource, self).__post_init__()
        _url("url", self.url)
        if self.effective_on is not None:
            _require(self.effective_on <= self.retrieved_on, "effective_on cannot follow retrieved_on.")


@dataclass(frozen=True, slots=True)
class RuleEvidence(Value):
    """Scope and interpretation are included in the hashed profile snapshot."""

    scope: str
    status: Literal["verified", "modeling_assumption", "source_conflict"]
    source_ids: tuple[str, ...]
    note: str

    def __post_init__(self):
        super(RuleEvidence, self).__post_init__()
        _require(bool(self.source_ids), "Evidence must reference at least one source.")
        _require(len(set(self.source_ids)) == len(self.source_ids), "Duplicate evidence source IDs.")


@dataclass(frozen=True, slots=True)
class SessionPolicy(Value):
    timezone: str
    open_time: time
    close_time: time
    reset_time: time
    trading_date: Literal["session_close_date"] = "session_close_date"

    def __post_init__(self):
        super(SessionPolicy, self).__post_init__()
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("timezone must name an available IANA zone.") from None
        _require(self.close_time < self.open_time == self.reset_time,
                 "Session must close before its next open/reset, with a maintenance break.")


@dataclass(frozen=True, slots=True)
class DrawdownRules(Value):
    amount: Decimal
    lock_profit: Decimal | None
    update: Literal["end_of_session"] = "end_of_session"
    breach: Literal["touch_or_below"] = "touch_or_below"
    never_decreases: Literal[True] = True

    def __post_init__(self):
        super(DrawdownRules, self).__post_init__()
        _decimal("amount", self.amount, positive=True)
        if self.lock_profit is not None:
            _decimal("lock_profit", self.lock_profit, minimum=0)


@dataclass(frozen=True, slots=True)
class TradingLimits(Value):
    max_contracts: int
    daily_loss_limit: Decimal | None
    daily_action: Literal["liquidate_and_suspend_session"] = "liquidate_and_suspend_session"
    excess_size_action: Literal["reject_order"] = "reject_order"

    def __post_init__(self):
        super(TradingLimits, self).__post_init__()
        _integer("max_contracts", self.max_contracts)
        if self.daily_loss_limit is not None:
            _decimal("daily_loss_limit", self.daily_loss_limit, positive=True)


@dataclass(frozen=True, slots=True)
class LimitTier(Value):
    """Inclusive lower bound; the following tier supplies the exclusive upper."""

    minimum_profit: Decimal
    limits: TradingLimits

    def __post_init__(self):
        super(LimitTier, self).__post_init__()
        _decimal("minimum_profit", self.minimum_profit, minimum=0)


@dataclass(frozen=True, slots=True)
class EvaluationRules(Value):
    initial_balance: Decimal
    profit_target: Decimal
    drawdown: DrawdownRules
    limits: TradingLimits
    access_calendar_days: int
    expiry_time: time
    review_time: time
    recognition_not_before: time
    minimum_trading_days: int = 0

    def __post_init__(self):
        super(EvaluationRules, self).__post_init__()
        _decimal("initial_balance", self.initial_balance, positive=True)
        _decimal("profit_target", self.profit_target, positive=True)
        _integer("access_calendar_days", self.access_calendar_days)
        _integer("minimum_trading_days", self.minimum_trading_days, 0)
        _require(self.minimum_trading_days <= self.access_calendar_days, "minimum_trading_days exceeds access period.")
        _require(self.drawdown.amount < self.initial_balance, "drawdown must be below initial_balance.")
        _require(self.review_time < self.recognition_not_before <= self.expiry_time,
                 "Review must precede recognition, no later than expiry.")


@dataclass(frozen=True, slots=True)
class PayoutRules(Value):
    qualifying_days: int
    qualifying_day_profit: Decimal
    consistency_limit: Decimal
    minimum_request_balance: Decimal
    safety_net_balance: Decimal
    minimum_withdrawal: Decimal
    ladder: tuple[Decimal, ...]
    profit_split: Decimal
    consistency_comparison: Literal["strictly_less"] = "strictly_less"
    cycle_reset: Literal["approved_payout"] = "approved_payout"
    close_after_ladder: Literal[True] = True

    def __post_init__(self):
        super(PayoutRules, self).__post_init__()
        _integer("qualifying_days", self.qualifying_days)
        for name in ("qualifying_day_profit", "minimum_request_balance", "safety_net_balance", "minimum_withdrawal"):
            _decimal(name, getattr(self, name), positive=True)
        _decimal("consistency_limit", self.consistency_limit, positive=True)
        _require(self.consistency_limit < 1, "consistency_limit must be below one.")
        _decimal("profit_split", self.profit_split, positive=True, maximum=1)
        _require(bool(self.ladder), "payout ladder cannot be empty.")
        for cap in self.ladder:
            _decimal("payout cap", cap, positive=True)
            _require(cap >= self.minimum_withdrawal, "payout cap is below minimum withdrawal.")
        _require(all(a <= b for a, b in zip(self.ladder, self.ladder[1:])), "payout ladder must not decrease.")
        _require(self.minimum_request_balance >= add(self.safety_net_balance, self.minimum_withdrawal),
                 "minimum_request_balance cannot fund the minimum withdrawal above the safety net.")


@dataclass(frozen=True, slots=True)
class InactivityRules(Value):
    calendar_days: int
    qualifying_days: int
    qualifying_day_profit: Decimal
    initial_grace_calendar_days: int
    date_basis: Literal["session_close_date"] = "session_close_date"
    window: Literal["inclusive_calendar_dates"] = "inclusive_calendar_dates"

    def __post_init__(self):
        super(InactivityRules, self).__post_init__()
        _integer("calendar_days", self.calendar_days)
        _integer("qualifying_days", self.qualifying_days)
        _integer("initial_grace_calendar_days", self.initial_grace_calendar_days)
        _decimal("qualifying_day_profit", self.qualifying_day_profit, positive=True)
        _require(self.qualifying_days <= self.calendar_days, "Inactivity qualifying_days exceeds window.")
        _require(self.initial_grace_calendar_days == self.calendar_days,
                 "Initial inactivity grace must equal the first full calendar window.")


@dataclass(frozen=True, slots=True)
class FundedRules(Value):
    initial_balance: Decimal
    drawdown: DrawdownRules
    tiers: tuple[LimitTier, ...]
    payouts: PayoutRules
    inactivity: InactivityRules
    access_calendar_days: None = None
    tier_update: Literal["prior_session_close"] = "prior_session_close"

    def __post_init__(self):
        super(FundedRules, self).__post_init__()
        _decimal("initial_balance", self.initial_balance, positive=True)
        _require(self.drawdown.amount < self.initial_balance, "drawdown must be below initial_balance.")
        _require(bool(self.tiers) and self.tiers[0].minimum_profit == 0, "tiers must start at zero (negative profits use first tier).")
        for previous, current in zip(self.tiers, self.tiers[1:]):
            _require(previous.minimum_profit < current.minimum_profit, "tier boundaries must be strictly increasing.")
            _require(previous.limits.max_contracts <= current.limits.max_contracts, "tier contract limits cannot decrease.")
            a, b = previous.limits.daily_loss_limit, current.limits.daily_loss_limit
            _require(a is not None and b is not None and a <= b, "tier DLL must be enabled and nondecreasing.")
        _require(all(t.limits.daily_loss_limit is not None for t in self.tiers), "funded tier DLL must be enabled.")
        _require(self.payouts.safety_net_balance > self.initial_balance, "safety net must exceed initial_balance.")
        if self.drawdown.lock_profit is not None:
            _require(self.payouts.safety_net_balance > add(self.initial_balance, self.drawdown.lock_profit),
                     "safety net must stay above the locked failure floor.")
    def tier_for_profit(self, prior_session_profit: Decimal) -> LimitTier:
        """Resolve inclusive boundaries only; this does not advance account state."""
        _decimal("prior_session_profit", prior_session_profit)
        return next((tier for tier in reversed(self.tiers) if prior_session_profit >= tier.minimum_profit), self.tiers[0])


@dataclass(frozen=True, slots=True)
class ModelingAssumptions(Value):
    target_policy: Literal["stop_at_flat_target_then_eod_review"] = "stop_at_flat_target_then_eod_review"
    payout_processing: Literal["immediate_approval_and_payment"] = "immediate_approval_and_payment"
    tier_balance: Literal["after_immediate_withdrawal"] = "after_immediate_withdrawal"
    incompatible_size: Literal["reject_simulation"] = "reject_simulation"
    liquidation: Literal["observed_equity_plus_remaining_exit_costs"] = "observed_equity_plus_remaining_exit_costs"
    source_signals: Literal["frozen_trade_stream"] = "frozen_trade_stream"
    overnight_exposure: Literal["unsupported"] = "unsupported"


@dataclass(frozen=True, slots=True)
class ProfileFees(Value):
    """Reusable user-supplied prices, separate from verified trading rules."""

    currency: str
    configured_on: date
    attempt_fee: Decimal | None = None
    activation_fee: Decimal | None = None
    origin: Literal["user_supplied"] = "user_supplied"

    def __post_init__(self):
        super(ProfileFees, self).__post_init__()
        _require(re.fullmatch(r"[A-Z]{3}", self.currency) is not None, "Invalid profile fee currency.")
        _require(self.attempt_fee is not None or self.activation_fee is not None, "Set at least one profile fee.")
        for name in ("attempt_fee", "activation_fee"):
            if getattr(self, name) is not None:
                _decimal(name, getattr(self, name), minimum=0)


@dataclass(frozen=True, slots=True)
class RuleProfile(Value):
    id: str
    version: str
    provider: str
    platform: Literal["rithmic", "tradovate", "wealthcharts"]
    currency: str
    session: SessionPolicy
    evaluation: EvaluationRules
    funded: FundedRules
    assumptions: ModelingAssumptions
    sources: tuple[RuleSource, ...]
    evidence: tuple[RuleEvidence, ...]
    fee_defaults: ProfileFees | None = field(default=None, metadata={"omit_none": True})

    @classmethod
    def from_dict(cls, payload):
        # Preserve the exact content/hash of pre-fee snapshots. Never inject
        # current defaults into an earlier saved profile.
        if type(payload) is dict and "fee_defaults" not in payload:
            payload = {**payload, "fee_defaults": None}
        return super(RuleProfile, cls).from_dict(payload)

    def __post_init__(self):
        super(RuleProfile, self).__post_init__()
        _require(re.fullmatch(r"[a-z][a-z0-9_]*", self.id) is not None, "Invalid profile id.")
        _require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.version) is not None, "version must use major.minor.patch.")
        _require(re.fullmatch(r"[A-Z]{3}", self.currency) is not None, "currency must be a three-letter uppercase code.")
        _require(self.fee_defaults is None or self.fee_defaults.currency == self.currency,
                 "Profile fee currency must match account currency.")
        if self.id.endswith("_no_activation"):
            _require(self.fee_defaults is not None and self.fee_defaults.activation_fee == 0,
                     "No-activation profiles require an explicit zero activation fee.")
        _require(self.evaluation.initial_balance == self.funded.initial_balance, "Phase initial balances must match for this product.")
        _require(self.session.close_time == self.evaluation.review_time, "review_time must match session close.")
        _require(self.session.reset_time == self.evaluation.expiry_time, "expiry_time must match session reset.")
        if self.provider == "Apex Trader Funding":
            lock = self.evaluation.drawdown.lock_profit
            _require(lock == self.evaluation.profit_target if self.platform in ("rithmic", "wealthcharts") else lock is None,
                     "Evaluation drawdown lock conflicts with the Apex platform.")
        ids = {source.id for source in self.sources}
        _require(bool(ids) and len(ids) == len(self.sources), "sources must have unique IDs.")
        _require(bool(self.evidence), "Profile evidence cannot be empty.")
        for claim in self.evidence:
            _require(set(claim.source_ids) <= ids, "Evidence references an unknown source ID.")
            value = self
            for component in claim.scope.split("."):
                _require(isinstance(value, Value) and component in {f.name for f in fields(value)},
                         f"Unknown evidence scope: {claim.scope}.")
                value = getattr(value, component)


@dataclass(frozen=True, slots=True)
class DatedFee(Value):
    name: str
    amount: Decimal
    at_utc: datetime

    def __post_init__(self):
        super(DatedFee, self).__post_init__()
        _decimal("amount", self.amount, minimum=0)


@dataclass(frozen=True, slots=True)
class UserFees(Value):
    currency: str
    attempt_fee: Decimal | None = None
    activation_fee: Decimal | None = None
    scheduled: tuple[DatedFee, ...] = ()
    origin: Literal["user_supplied", "profile_default"] = "user_supplied"

    def __post_init__(self):
        super(UserFees, self).__post_init__()
        _require(re.fullmatch(r"[A-Z]{3}", self.currency) is not None, "Invalid fee currency.")
        for name in ("attempt_fee", "activation_fee"):
            if getattr(self, name) is not None:
                _decimal(name, getattr(self, name), minimum=0)
        _require(all(a.at_utc <= b.at_utc for a, b in zip(self.scheduled, self.scheduled[1:])),
                 "Scheduled fees must be chronological.")


@dataclass(frozen=True, slots=True)
class MonteCarloConfig(Value):
    simulations: int
    seed: int
    block_length: int = 1
    retained_traces: int = 20
    rng: Literal["python_random_mt19937_v1"] = "python_random_mt19937_v1"

    def __post_init__(self):
        super(MonteCarloConfig, self).__post_init__()
        for name, minimum in (("simulations", 1), ("seed", 0), ("block_length", 1), ("retained_traces", 0)):
            _integer(name, getattr(self, name), minimum)
        _require(self.retained_traces <= self.simulations, "retained_traces exceeds simulations.")


@dataclass(frozen=True, slots=True)
class SizingConfig(Value):
    quantities: tuple[int, ...]
    validation_fraction: Decimal = Decimal("0.30")
    maximum_failure_rate: Decimal = Decimal("0.50")
    maximum_drawdown: Decimal | None = None

    def __post_init__(self):
        super(SizingConfig, self).__post_init__()
        _require(bool(self.quantities), "Sizing quantities cannot be empty.")
        for quantity in self.quantities:
            _integer("quantity", quantity)
        _require(len(set(self.quantities)) == len(self.quantities), "Sizing quantities must be unique.")
        _decimal("validation_fraction", self.validation_fraction, minimum=0)
        _require(self.validation_fraction < 1, "validation_fraction must be below one.")
        _decimal("maximum_failure_rate", self.maximum_failure_rate, minimum=0, maximum=1)
        if self.maximum_drawdown is not None:
            _decimal("maximum_drawdown", self.maximum_drawdown, positive=True)


@dataclass(frozen=True, slots=True)
class StressConfig(Value):
    additional_commission_per_contract_per_side: Decimal = Decimal("0")
    additional_slippage_ticks: int = 0
    exit_profit_reduction: Decimal = Decimal("0")

    def __post_init__(self):
        super(StressConfig, self).__post_init__()
        _decimal("additional_commission_per_contract_per_side", self.additional_commission_per_contract_per_side, minimum=0)
        _integer("additional_slippage_ticks", self.additional_slippage_ticks, 0)
        _decimal("exit_profit_reduction", self.exit_profit_reduction, minimum=0, maximum=1)


@dataclass(frozen=True, slots=True)
class SimulationConfig(Value):
    """Input settings only; resolve_simulation() embeds the full profile snapshot.

    Calendar contents and source artifacts are validated by the future adapter.
    This request binds their declared identities rather than inventing sessions.
    """

    source_backtest_id: str
    phase: Literal["evaluation", "funded"]
    analysis: Literal["historical", "monte_carlo"]
    observation_mode: Literal["trade_close", "bar_close"]
    account_start_utc: datetime
    end_utc: datetime
    instrument: str
    currency: str
    contract_limit_weight: Decimal
    contract_limit_source_url: str
    quantity: int
    calendar_id: str
    calendar_sha256: str
    timezone_data_version: str
    coverage_assumption: str
    fees: UserFees
    calendar_mode: Literal["explicit", "weekday_approximation"] = "explicit"
    monte_carlo: MonteCarloConfig | None = None
    sizing: SizingConfig | None = None
    stress: StressConfig = StressConfig()

    def __post_init__(self):
        super(SimulationConfig, self).__post_init__()
        _require(self.end_utc > self.account_start_utc, "end_utc must follow account_start_utc.")
        _require(re.fullmatch(r"[A-Z]{3}", self.currency) is not None, "Invalid simulation currency.")
        _decimal("contract_limit_weight", self.contract_limit_weight, positive=True)
        _url("contract_limit_source_url", self.contract_limit_source_url)
        _integer("quantity", self.quantity)
        _hash("calendar_sha256", self.calendar_sha256)
        _require(self.fees.currency == self.currency, "Fee currency must match simulation currency.")
        if self.phase == "evaluation":
            _require(self.fees.attempt_fee is not None and self.fees.activation_fee is None,
                     "Evaluation requires an explicit attempt_fee (including zero), and no activation_fee.")
        else:
            _require(self.fees.activation_fee is not None and self.fees.attempt_fee is None,
                     "Funded requires an explicit activation_fee (including zero), and no attempt_fee.")
        _require(all(self.account_start_utc <= fee.at_utc <= self.end_utc for fee in self.fees.scheduled),
                 "Scheduled fee falls outside the requested period.")
        _require((self.analysis == "monte_carlo") == (self.monte_carlo is not None),
                 "monte_carlo settings are required only for Monte Carlo analysis.")
        _require(self.sizing is None or self.analysis == "monte_carlo", "Sizing requires Monte Carlo analysis.")
