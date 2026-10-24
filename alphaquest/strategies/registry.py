"""Small code-owned allowlist; clients cannot supply import paths or scripts."""

from dataclasses import asdict, dataclass, fields
import hashlib
from pathlib import Path
from types import ModuleType

from . import consecutive_green_hold


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    module: ModuleType
    factory: type

    def parameters(self, values: dict):
        names = {field.name for field in fields(self.module.Parameters)}
        if values.keys() != names:
            raise ValueError(f"strategy_parameters must contain exactly: {', '.join(sorted(names))}.")
        return self.module.Parameters(**values)

    def description(self) -> dict:
        return {
            "id": self.module.STRATEGY_ID, "description": self.module.DESCRIPTION,
            "source_sha256": hashlib.sha256(Path(self.module.__file__).read_bytes()).hexdigest(),
            "parameters": [{"name": field.name, "type": field.type.__name__, "default": field.default,
                            **field.metadata} for field in fields(self.module.Parameters)],
        }

    def provenance(self, parameters) -> dict:
        description = self.description()
        description["parameters"] = asdict(parameters)
        return description


STRATEGIES = {
    consecutive_green_hold.STRATEGY_ID: StrategyDefinition(consecutive_green_hold, consecutive_green_hold.ConsecutiveGreenHold),
}


def get_strategy(strategy_id: str) -> StrategyDefinition:
    try:
        return STRATEGIES[strategy_id]
    except KeyError:
        raise ValueError(f"Unknown strategy {strategy_id!r}. Available strategies: {', '.join(STRATEGIES)}.") from None


def list_strategies() -> list[dict]:
    return [definition.description() for definition in STRATEGIES.values()]
