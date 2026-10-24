"""Small code-owned allowlist; clients cannot supply import paths or scripts."""

from dataclasses import asdict, dataclass, fields
import hashlib
from pathlib import Path
from types import ModuleType
from decimal import Decimal, InvalidOperation

from . import consecutive_green_hold, vwap_pullback_risk_sizing


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    module: ModuleType
    factory: type

    def parameters(self, values: dict):
        names = {field.name for field in fields(self.module.Parameters)}
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

    def create(self, parameters, config):
        if self.module is vwap_pullback_risk_sizing:
            return self.factory(parameters, execution_config=config)
        return self.factory(parameters)

    def description(self) -> dict:
        return {
            "id": self.module.STRATEGY_ID, "description": self.module.DESCRIPTION,
            "source_sha256": hashlib.sha256(Path(self.module.__file__).read_bytes()).hexdigest(),
            "execution_assumption": self.execution_assumption,
            "parameters": [{"name": field.name, "type": field.type.__name__, "default": str(field.default) if field.type is Decimal else field.default,
                            **field.metadata} for field in fields(self.module.Parameters)],
        }

    def provenance(self, parameters) -> dict:
        description = self.description()
        description["parameters"] = asdict(parameters)
        return description


STRATEGIES = {
    consecutive_green_hold.STRATEGY_ID: StrategyDefinition(consecutive_green_hold, consecutive_green_hold.ConsecutiveGreenHold),
    vwap_pullback_risk_sizing.STRATEGY_ID: StrategyDefinition(vwap_pullback_risk_sizing, vwap_pullback_risk_sizing.VwapPullbackRiskSizing),
}


def get_strategy(strategy_id: str) -> StrategyDefinition:
    try:
        return STRATEGIES[strategy_id]
    except KeyError:
        raise ValueError(f"Unknown strategy {strategy_id!r}. Available strategies: {', '.join(STRATEGIES)}.") from None


def list_strategies() -> list[dict]:
    return [definition.description() for definition in STRATEGIES.values()]
