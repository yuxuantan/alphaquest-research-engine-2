"""Declared deterministic execution alternatives for ordinary backtest reruns.

These assumptions change real fills and the positions delivered to strategy
callbacks. They are sensitivity scenarios, not measured broker execution models.
"""
from dataclasses import asdict, dataclass, replace
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from .decimal_math import add
from .strategy import ExecutionConfig


VERSION = 'deterministic-execution-scenarios-v1'


@dataclass(frozen=True, slots=True)
class FillAssumptions:
    stop_extra_slippage_ticks: int = 0
    limit_penetration_ticks: int = 0
    limit_price_improvement: bool = True

    def __post_init__(self):
        for name in ('stop_extra_slippage_ticks', 'limit_penetration_ticks'):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f'{name} must be a nonnegative whole number; booleans and coercion are not accepted.')
        if type(self.limit_price_improvement) is not bool:
            raise ValueError('limit_price_improvement must be boolean.')


class ExecutionScenario(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    name: StrictStr = Field(min_length=1, max_length=100)
    additional_commission_per_contract_per_side: Decimal = Decimal('0')
    additional_slippage_ticks: StrictInt = Field(default=0, ge=0)
    stop_extra_slippage_ticks: StrictInt = Field(default=0, ge=0)
    limit_penetration_ticks: StrictInt = Field(default=0, ge=0)
    limit_price_improvement: StrictBool = True

    @field_validator('name')
    @classmethod
    def nonempty_name(cls, name):
        if not name.strip():
            raise ValueError('Scenario name must contain non-whitespace characters.')
        return name

    @field_validator('additional_commission_per_contract_per_side', mode='before')
    @classmethod
    def finite_nonnegative_cost(cls, value):
        if not isinstance(value, (str, Decimal)):
            raise ValueError('Additional commission must be a decimal string or Decimal.')
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError('Additional commission must be a finite nonnegative decimal.') from exc
        if not number.is_finite() or number < 0:
            raise ValueError('Additional commission must be a finite nonnegative decimal.')
        return number


def parse_execution_scenario(scenario):
    if scenario is None or isinstance(scenario, ExecutionScenario):
        return scenario
    return ExecutionScenario.model_validate(scenario)


def resolve_execution_scenario(config, scenario=None):
    """Resolve baseline costs once, separately from stop/limit fill assumptions."""
    if type(config) is not ExecutionConfig:
        raise ValueError('Scenario baseline must be an ExecutionConfig.')
    scenario = parse_execution_scenario(scenario)
    if scenario is None:
        return config, FillAssumptions()
    resolved = replace(config,
        slippage_ticks=config.slippage_ticks+scenario.additional_slippage_ticks,
        commission_per_contract_per_side=add(config.commission_per_contract_per_side,
                                             scenario.additional_commission_per_contract_per_side))
    assumptions = FillAssumptions(scenario.stop_extra_slippage_ticks,
                                  scenario.limit_penetration_ticks,
                                  scenario.limit_price_improvement)
    return resolved, assumptions


def execution_config_record(config):
    """The existing saved execution-settings schema, with exact Decimal strings."""
    return {key: str(value) if isinstance(value, Decimal) else value for key, value in asdict(config).items()}


def scenario_metadata(config, scenario):
    """Saved baseline and actual settings make additional costs auditable once."""
    scenario = parse_execution_scenario(scenario)
    if scenario is None:
        return None
    resolved, assumptions = resolve_execution_scenario(config, scenario)
    return dict(version=VERSION, declaration=scenario.model_dump(mode='json'),
        baseline_execution_settings=execution_config_record(config),
        resolved_execution_settings=execution_config_record(resolved),
        fill_assumptions=asdict(assumptions),
        interpretation='Actual ordinary-engine rerun with declared deterministic fill/cost assumptions; not P&L scaling or observed execution evidence.',
        limitations=[
            'OHLC bars do not reveal queue position, tick order, available depth or partial fills. Penetration is a deterministic fill hurdle, not a calibrated fill probability.',
            'Stop exits include the configured market slippage plus extra stop ticks, including opening gaps; liquidity and market impact remain unverified.',
            'Opening events precede intrabar events. If both stop and eligible target can be reached intrabar, the stop executes first; no favorable tick sequence is invented.',
            'Additional commissions apply per contract per side. Additional market slippage applies to market entries/exits; limit exits retain their price constraint.',
            'Strategy callbacks receive the actual scenario position and fill price. Changed fills can change later signals and trades.'])


def restore_scenario_config(saved_metadata):
    """Reconstruct the original baseline for a saved detailed/risk replay."""
    if saved_metadata.get('version') != VERSION:
        raise ValueError('Saved execution scenario version is unsupported; historical reports remain readable.')
    declaration = parse_execution_scenario(saved_metadata['declaration'])
    values = dict(saved_metadata['baseline_execution_settings'])
    for key in ('initial_capital', 'tick_size', 'point_value', 'commission_per_contract_per_side'):
        values[key] = Decimal(values[key])
    baseline = ExecutionConfig(**values)
    if scenario_metadata(baseline, declaration) != saved_metadata:
        raise ValueError('Saved execution scenario metadata does not reconcile.')
    return baseline, declaration
