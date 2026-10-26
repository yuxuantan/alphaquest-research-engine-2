"""Sourced contract-unit profiles. Selection declares identity; it never converts a run."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal
import re

from .rules import _canonical_json, _digest, _read_json
from .types import RuleSource, Value, _canonical_decimal, _decimal, _require, _url


RETRIEVED_ON = date(2026, 10, 26)
INSTRUMENT_PROFILE_IDS = ("nq", "mnq")
APEX_WEIGHT_URL = "https://apextraderfunding.com/help-center/additional-helpful-items/position-sizing-evaluation/"


@dataclass(frozen=True, slots=True)
class InstrumentProfile(Value):
    id: str
    version: str
    name: str
    symbol: str
    currency: str
    tick_size: Decimal
    point_value: Decimal
    contract_limit_weight: Decimal
    contract_limit_source_url: str
    specification_source_url: str
    provider: str
    platforms: tuple[Literal["rithmic", "tradovate", "wealthcharts"], ...]
    sources: tuple[RuleSource, ...]

    def __post_init__(self):
        super(InstrumentProfile, self).__post_init__()
        _require(re.fullmatch(r"[a-z][a-z0-9_]*", self.id) is not None, "Invalid instrument profile ID.")
        _require(re.fullmatch(r"\d+\.\d+\.\d+", self.version) is not None, "Invalid instrument profile version.")
        _require(re.fullmatch(r"[A-Z]{3}", self.currency) is not None, "Invalid instrument profile currency.")
        for name in ("tick_size", "point_value", "contract_limit_weight"):
            _decimal(name, getattr(self, name), positive=True)
        for name in ("contract_limit_source_url", "specification_source_url"):
            _url(name, getattr(self, name))
            _require(getattr(self, name) in {source.url for source in self.sources}, "Missing instrument source evidence.")
        _require(bool(self.platforms) and len(set(self.platforms)) == len(self.platforms), "Instrument platforms must be unique.")
        _require(bool(self.sources) and len({s.id for s in self.sources}) == len(self.sources), "Instrument sources must be unique.")

    @property
    def basis(self):
        def number(name):
            return format(Decimal(_canonical_decimal(getattr(self, name))), "f")
        return (f"Selected {self.name} ({self.symbol}) profile {self.version}. Source contracts and P&L are declared "
                f"as {self.symbol} and {self.currency}: {number('point_value')} per index point per contract, "
                f"tick {number('tick_size')}, {number('contract_limit_weight')} Apex standard-contract units per contract. "
                "No FX conversion, mini/micro conversion, source fill changes or additional source commissions. "
                "Profile selection declares identity/currency if absent in source metadata; it does not certify data or broker routing.")


@dataclass(frozen=True, slots=True)
class ResolvedInstrumentProfile(Value):
    format_version: int
    profile: InstrumentProfile
    profile_sha256: str

    def __post_init__(self):
        super(ResolvedInstrumentProfile, self).__post_init__()
        _require(self.format_version == 1, "Unsupported instrument snapshot version.")
        _require(self.profile_sha256 == _digest(self.profile.to_dict()), "Instrument profile hash mismatch.")

    def to_json(self):
        return _canonical_json(self.to_dict())

    @classmethod
    def from_json(cls, value):
        return cls.from_dict(_read_json(value))


def resolve_instrument_profile(profile):
    _require(type(profile) is InstrumentProfile, "Expected an InstrumentProfile.")
    return ResolvedInstrumentProfile(1, profile, _digest(profile.to_dict()))


def get_instrument_profile(profile_id):
    _require(type(profile_id) is str and profile_id in INSTRUMENT_PROFILE_IDS, "Unknown instrument profile.")
    micro = profile_id == "mnq"
    spec = "https://www.cmegroup.com/markets/equities/nasdaq/" + (
        "micro-e-mini-nasdaq-100.contractSpecs.html" if micro else "e-mini-nasdaq-100.contractSpecs.html")
    sources = (("cme_contract", spec), ("apex_evaluation_weight", APEX_WEIGHT_URL),
               ("apex_funded_weight", "https://apextraderfunding.com/help-center/additional-helpful-items/scaling-levels-pa-explained/"),
               ("rithmic_instruments", "https://apextraderfunding.com/help-center/rithmic/rithmic-commissions-instruments/"),
               ("tradovate_instruments", "https://apextraderfunding.com/help-center/tradovate/tradovate-commission-instruments/"),
               ("wealthcharts_instruments", "https://apextraderfunding.com/help-center/wealthcharts/wealthcharts-commissions-instruments/"))
    return InstrumentProfile(profile_id, "1.0.0", "Micro E-mini Nasdaq-100" if micro else "E-mini Nasdaq-100",
                             "MNQ" if micro else "NQ", "USD", Decimal("0.25"), Decimal("2" if micro else "20"),
                             Decimal("0.1" if micro else "1"), APEX_WEIGHT_URL, spec, "Apex Trader Funding",
                             ("rithmic", "tradovate", "wealthcharts"),
                             tuple(RuleSource(key, url, RETRIEVED_ON) for key, url in sources))


def source_compatibility(profile, record):
    """Metadata preflight; execution still reconciles the actual source artifacts."""
    dataset = record["run_metadata"]["dataset"]
    settings = record["execution_settings"]
    issues = []
    for field in ("tick_size", "point_value"):
        raw = settings.get(field)
        try:
            matches = type(raw) is str and Decimal(raw).is_finite() and Decimal(raw) == getattr(profile, field)
        except InvalidOperation:
            matches = False
        if not matches:
            issues.append(f"Saved {field} {raw} does not match {profile.symbol} profile {getattr(profile, field):f}.")
    for field in ("symbol", "currency"):
        if dataset.get(field) and dataset[field] != getattr(profile, field):
            issues.append(f"Saved {field} {dataset[field]} conflicts with {profile.symbol} profile {getattr(profile, field)}.")
    return dict(compatible=not issues, issues=issues,
                identity_declared=not dataset.get("symbol") or not dataset.get("currency"))


def require_compatible_source(profile, record):
    compatibility = source_compatibility(profile, record)
    _require(compatibility["compatible"], " ".join(compatibility["issues"]))


def require_supported_account(profile, account):
    _require(profile.provider == account.provider and account.platform in profile.platforms,
             "Instrument profile does not support the selected account provider/platform.")
    _require(profile.currency == account.currency, "Instrument and account currencies do not match.")
