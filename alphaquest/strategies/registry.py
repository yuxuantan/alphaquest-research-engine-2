"""Small code-owned allowlist; clients cannot supply import paths or scripts."""

from dataclasses import asdict, dataclass, fields
import hashlib
from pathlib import Path
from types import ModuleType
from decimal import Decimal, InvalidOperation

from . import consecutive_green_hold, noise, overnight_bias_orb, relative_strength, vwap_pullback_risk_sizing, vwap_features, twin_continuation


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    module: ModuleType
    factory: type
    acceleration: object = None
    accepts_execution_config: bool = False
    accepts_instrument: bool = False

    def __post_init__(self):
        from ..strategy_sizing import SizingSupport
        if not isinstance(getattr(self.module, 'SIZING_SUPPORT', None), SizingSupport):
            raise ValueError('Every registered strategy must declare its sizing contract, including unsupported modes.')
        support=self.module.SIZING_SUPPORT
        if support.describe(self.module.Parameters())['percentage_risk']['supported'] and (
                not callable(getattr(self.factory,'on_bar_controlled',None)) or support.session_settings is None or support.holding_start is None):
            raise ValueError('Native sizing requires controlled entry admission and explicit session/holding coverage hooks.')

    @property
    def sizing(self):
        return self.module.SIZING_SUPPORT

    def parameters(self, values: dict):
        names = {field.name for field in fields(self.module.Parameters)}
        if self.module is vwap_pullback_risk_sizing:
            defaults=self.module.Parameters()
            added={'use_order_flow','minimum_delta_pct','maximum_unknown_volume_pct','minimum_trade_records',
                   'use_external_calendar'}
            values={**{k:(str(getattr(defaults,k)) if isinstance(getattr(defaults,k),Decimal) else getattr(defaults,k)) for k in added if k not in values},**values}
        if values.keys() != names:
            raise ValueError(f"strategy_parameters must contain exactly: {', '.join(sorted(names))}.")
        converted = dict(values)
        for item in fields(self.module.Parameters):
            if item.type is Decimal:
                if not isinstance(converted[item.name], str):
                    raise ValueError(f"{item.name} must be a decimal string.")
                try:
                    converted[item.name] = Decimal(converted[item.name])
                except InvalidOperation:
                    raise ValueError(f"{item.name} must be a decimal string.") from None
        return self.module.Parameters(**converted)

    @property
    def execution_assumption(self):
        return getattr(self.module, "EXECUTION_ASSUMPTION", "same_close_full_fill")

    def validate_instrument(self, parameters, symbol):
        validate = getattr(self.module, "validate_instrument", None)
        if validate is not None:
            validate(parameters, symbol)

    def validate_source(self, parameters, dataset):
        self.validate_instrument(parameters, dataset.get("symbol"))
        if getattr(parameters,'use_order_flow',False) and not dataset.get('tick_data'):
            raise ValueError('Order-flow entries require an ordered trade tick dataset.')
        validate = getattr(self.module, "validate_dataset", None)
        if validate is not None:
            validate(dataset)

    def create(self, parameters, config, *, instrument_symbol="NQ"):
        if self.accepts_instrument:
            return self.factory(parameters, execution_config=config, instrument_symbol=instrument_symbol)
        if self.accepts_execution_config:
            return self.factory(parameters, execution_config=config)
        return self.factory(parameters)

    def description(self) -> dict:
        return {
            "id": self.module.STRATEGY_ID, "description": self.module.DESCRIPTION,
            "source_sha256": (self.module.source_fingerprint() if hasattr(self.module, "source_fingerprint")
                              else hashlib.sha256(Path(self.module.__file__).read_bytes()).hexdigest()),
            "execution_assumption": self.execution_assumption,
            "sizing_support": self.sizing.describe(self.module.Parameters()),
            **({"session_calendar": dict(self.module.SESSION_CALENDAR)} if hasattr(self.module, "SESSION_CALENDAR") else {}),
            "parameters": [{"name": field.name, "type": field.type.__name__, "default": str(field.default) if field.type is Decimal else field.default,
                            **field.metadata} for field in fields(self.module.Parameters)],
        }

    def provenance(self, parameters) -> dict:
        description = self.description()
        description.pop('sizing_support', None)  # Admission belongs to the versioned prop package.
        description["parameters"] = asdict(parameters)
        assumptions = getattr(self.module, "backtest_assumptions", None)
        if assumptions is not None:
            description["session_flattening"] = assumptions(parameters)
        return description


STRATEGIES = {
    consecutive_green_hold.STRATEGY_ID: StrategyDefinition(consecutive_green_hold, consecutive_green_hold.ConsecutiveGreenHold),
    vwap_pullback_risk_sizing.STRATEGY_ID: StrategyDefinition(vwap_pullback_risk_sizing, vwap_pullback_risk_sizing.VwapPullbackRiskSizing,
                                                          acceleration=vwap_features, accepts_execution_config=True, accepts_instrument=True),
    twin_continuation.STRATEGY_ID: StrategyDefinition(twin_continuation, twin_continuation.TwinContinuation, accepts_instrument=True),
    overnight_bias_orb.STRATEGY_ID: StrategyDefinition(overnight_bias_orb, overnight_bias_orb.OvernightBiasORB,
                                                     accepts_execution_config=True, accepts_instrument=True),
    noise.STRATEGY_ID: StrategyDefinition(noise, noise.Noise, accepts_execution_config=True),
    relative_strength.STRATEGY_ID: StrategyDefinition(relative_strength, relative_strength.RelativeStrength),
}


def get_strategy(strategy_id: str) -> StrategyDefinition:
    try:
        return STRATEGIES[strategy_id]
    except KeyError:
        raise ValueError(f"Unknown strategy {strategy_id!r}. Available strategies: {', '.join(STRATEGIES)}.") from None


def list_strategies() -> list[dict]:
    return [definition.description() for definition in STRATEGIES.values()]
