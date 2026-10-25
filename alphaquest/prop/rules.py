"""Sourced Apex product templates and self-contained, hash-checked snapshots."""

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from hashlib import sha256
import json

from .types import (
    DrawdownRules, EvaluationRules, FundedRules, InactivityRules, LimitTier,
    ModelingAssumptions, PayoutRules, RuleEvidence, RuleProfile, RuleSource,
    SessionPolicy, SimulationConfig, TradingLimits, Value, _hash, _require,
)


RETRIEVED_ON = date(2026, 10, 25)
PROFILE_VERSION = "1.0.0"
DEFAULT_PROFILE_ID = "apex_50k_eod_rithmic"
SOURCE_URLS = (
    ("evaluation", "https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-evaluations/"),
    ("drawdown", "https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-drawdown-explained/"),
    ("dll", "https://apextraderfunding.com/help-center/additional-helpful-items/daily-loss-limit-explained/"),
    ("payouts", "https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-payouts/"),
    ("inactivity", "https://apextraderfunding.com/help-center/billing/inactivity-policy-on-performance-accounts-pa/"),
    ("access", "https://apextraderfunding.com/help-center/billing/evaluation-plan-fees-and-access-explained/"),
    ("scaling", "https://apextraderfunding.com/help-center/additional-helpful-items/scaling-levels-pa-explained/"),
    ("position", "https://apextraderfunding.com/help-center/additional-helpful-items/position-sizing-evaluation/"),
)


def get_profile(profile_id: str = DEFAULT_PROFILE_ID) -> RuleProfile:
    """One Apex 50K EOD product, explicitly named by supported platform.

    Returns fresh immutable values, with no mutable catalog or network access.
    The source conflict at the top tier is carried in every resolved snapshot.
    """
    supported = {f"apex_50k_eod_{platform}": platform for platform in ("rithmic", "tradovate", "wealthcharts")}
    _require(type(profile_id) is str and profile_id in supported, "Unknown Apex 50K EOD profile ID.")
    platform = supported[profile_id]
    d = Decimal
    sources = tuple(RuleSource(key, url, RETRIEVED_ON) for key, url in SOURCE_URLS)
    evidence = (
        RuleEvidence("evaluation", "verified", ("evaluation", "access", "position"),
                     "Evaluation product parameters and calendar access, not account conduct approval."),
        RuleEvidence("evaluation.drawdown", "verified", ("drawdown",),
                     "Rithmic/WealthCharts lock at target balance; Tradovate evaluation has no lock."),
        RuleEvidence("funded.drawdown", "verified", ("drawdown", "payouts"),
                     "50K funded drawdown is 2000; locked floor is initial balance plus 100."),
        RuleEvidence("funded.tiers", "source_conflict", ("dll", "scaling"),
                     "DLL article starts top 50K tier at 6000; scaling article says 5999 & Up, overlapping "
                     "its preceding range. Explicit modeling resolution: use DLL article disjoint boundaries "
                     "0/1500/3000/6000; 5999 remains in the 2000-DLL tier. Provider clarification is not claimed."),
        RuleEvidence("funded.payouts", "verified", ("payouts",),
                     "Qualifying sessions, strict consistency, request/safety balances, ladder and split."),
        RuleEvidence("funded.inactivity", "verified", ("inactivity",),
                     "Inclusive rolling calendar dates and initial purchase-date grace; session-close profits."),
        RuleEvidence("session", "verified", ("drawdown", "evaluation", "inactivity"),
                     "Eastern session reset and closing-date assignment; holiday exceptions belong to the run calendar."),
        RuleEvidence("assumptions.target_policy", "modeling_assumption", ("evaluation", "access"),
                     "Stop after a flat target observation, then model EOD review; actual approval is external."),
        RuleEvidence("assumptions.payout_processing", "modeling_assumption", ("payouts",),
                     "Immediate approval/payment is a simplification; official payouts can be denied or delayed."),
        RuleEvidence("assumptions.tier_balance", "modeling_assumption", ("scaling", "payouts"),
                     "Use balance after immediate modeled withdrawal for next-session tier; withdrawal timing unconfirmed."),
        RuleEvidence("assumptions.incompatible_size", "modeling_assumption", ("position", "scaling"),
                     "Official excess orders are rejected without account penalty. This overlay rejects an "
                     "incompatible simulation rather than silently deleting or resizing source trades."),
        RuleEvidence("assumptions.liquidation", "modeling_assumption", ("dll",),
                     "Sampled-equity liquidation plus remaining exit costs; never a guaranteed threshold fill."),
        RuleEvidence("assumptions.source_signals", "modeling_assumption", ("evaluation",),
                     "Reuse frozen source signals after suspensions; no strategy rerun."),
        RuleEvidence("assumptions.overnight_exposure", "modeling_assumption", ("evaluation",),
                     "First release rejects overnight exposure; this is an implementation scope restriction."),
    )
    evaluation = EvaluationRules(
        initial_balance=d("50000"), profit_target=d("3000"),
        drawdown=DrawdownRules(d("2000"), None if platform == "tradovate" else d("3000")),
        limits=TradingLimits(6, d("1000")), access_calendar_days=30,
        expiry_time=time(18), review_time=time(16, 59, 59), recognition_not_before=time(18),
    )
    funded = FundedRules(
        initial_balance=d("50000"), drawdown=DrawdownRules(d("2000"), d("100")),
        tiers=tuple(LimitTier(d(bound), TradingLimits(quantity, d(dll))) for bound, quantity, dll in (
            ("0", 2, "1000"), ("1500", 3, "1000"), ("3000", 4, "2000"), ("6000", 4, "3000"))),
        payouts=PayoutRules(5, d("250"), d("0.50"), d("52600"), d("52100"), d("500"),
                           tuple(map(d, ("1500", "1500", "2000", "2500", "2500", "3000"))), d("1")),
        inactivity=InactivityRules(30, 2, d("50"), 30),
    )
    return RuleProfile(profile_id, PROFILE_VERSION, "Apex Trader Funding", platform, "USD",
                       SessionPolicy("America/New_York", time(18), time(16, 59, 59), time(18)),
                       evaluation, funded, ModelingAssumptions(), sources, evidence)


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(value):
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _read_json(value):
    _require(type(value) is str, "Snapshot JSON must be text.")

    def pairs(items):
        result = {}
        for key, item in items:
            _require(key not in result, f"Duplicate JSON field: {key}.")
            result[key] = item
        return result

    def invalid_constant(token):
        raise ValueError(f"Invalid JSON constant: {token}.")

    try:
        return json.loads(value, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"Invalid snapshot JSON: {exc}") from None


@dataclass(frozen=True, slots=True)
class ResolvedProfile(Value):
    """Full content and verified hash; readers never resolve current templates."""

    format_version: int
    profile: RuleProfile
    profile_sha256: str

    def __post_init__(self):
        super(ResolvedProfile, self).__post_init__()
        _require(self.format_version == 1, "Unsupported profile snapshot format_version.")
        _hash("profile_sha256", self.profile_sha256)
        _require(self.profile_sha256 == _digest(self.profile.to_dict()), "Profile snapshot hash mismatch.")

    def to_json(self):
        return _canonical_json(self.to_dict())

    @classmethod
    def from_json(cls, value):
        return cls.from_dict(_read_json(value))


def resolve_profile(profile: RuleProfile) -> ResolvedProfile:
    _require(type(profile) is RuleProfile, "profile must be a RuleProfile.")
    return ResolvedProfile(1, profile, _digest(profile.to_dict()))


@dataclass(frozen=True, slots=True)
class ResolvedSimulation(Value):
    """Attach this complete immutable envelope to each future saved simulation."""

    format_version: int
    rules: ResolvedProfile
    config: SimulationConfig
    settings_sha256: str

    def __post_init__(self):
        super(ResolvedSimulation, self).__post_init__()
        _require(self.format_version == 1, "Unsupported simulation snapshot format_version.")
        _require(self.config.currency == self.rules.profile.currency, "Profile and simulation currency must match.")
        _hash("settings_sha256", self.settings_sha256)
        _require(self.settings_sha256 == _digest({"rules": self.rules.to_dict(), "config": self.config.to_dict()}),
                 "Simulation settings hash mismatch.")

    def to_json(self):
        return _canonical_json(self.to_dict())

    @classmethod
    def from_json(cls, value):
        return cls.from_dict(_read_json(value))


def resolve_simulation(config: SimulationConfig, profile: RuleProfile) -> ResolvedSimulation:
    _require(type(config) is SimulationConfig, "config must be a SimulationConfig.")
    rules = resolve_profile(profile)
    payload = {"rules": rules.to_dict(), "config": config.to_dict()}
    return ResolvedSimulation(1, rules, config, _digest(payload))
