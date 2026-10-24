"""Resolve dataset defaults and optional run-specific instrument overrides."""

from dataclasses import dataclass
from decimal import Decimal

from .datasets import instrument_settings, saved_instrument_settings
from .strategy import ExecutionConfig


@dataclass(frozen=True)
class RunSettings:
    initial_capital: Decimal
    slippage_ticks: int
    commission_per_contract_per_side: Decimal
    tick_size: str | None = None
    point_value: str | None = None

    def execution_config(self, dataset: dict) -> ExecutionConfig:
        defaults = saved_instrument_settings(dataset)
        settings = instrument_settings(
            defaults["tick_size"] if self.tick_size is None else self.tick_size,
            defaults["point_value"] if self.point_value is None else self.point_value,
        )
        return ExecutionConfig(self.initial_capital, Decimal(settings["tick_size"]), Decimal(settings["point_value"]),
                               self.slippage_ticks, self.commission_per_contract_per_side)


def instrument_overrides(dataset: dict, config: ExecutionConfig) -> dict[str, str]:
    """Record only values that differ numerically from the captured defaults."""
    defaults = saved_instrument_settings(dataset)
    return {key: str(getattr(config, key)) for key, value in defaults.items()
            if getattr(config, key) != Decimal(value)}
