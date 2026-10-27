"""One request boundary for a parameter set or an exhaustive batch."""
from decimal import Decimal,InvalidOperation
from typing import Any,Literal
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt,StrictStr
from .backtest_config import RunSettings
from .worker_limits import DEFAULT_WORKERS,MAX_WORKERS
from .research import SplitDeclaration


class ExecutionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    initial_capital: StrictStr
    slippage_ticks: StrictInt = Field(ge=0)
    commission_per_contract_per_side: StrictStr
    tick_size: StrictStr | None = Field(default=None, max_length=128)
    point_value: StrictStr | None = Field(default=None, max_length=128)

    def execution_config(self, dataset):
        try:
            return RunSettings(Decimal(self.initial_capital), self.slippage_ticks,
                               Decimal(self.commission_per_contract_per_side), self.tick_size, self.point_value).execution_config(dataset)
        except InvalidOperation:
            raise ValueError("Execution monetary values must be finite decimal strings.") from None


class ParameterRange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: StrictInt | StrictStr | StrictBool
    end: StrictInt | StrictStr | StrictBool
    step: StrictInt | StrictStr


class OptimizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: StrictStr = Field(min_length=1, max_length=128)
    strategy_id: StrictStr = Field(min_length=1, max_length=128)
    method: Literal["exhaustive"]
    parameter_ranges: dict[str, ParameterRange]
    workers: StrictInt = Field(default=DEFAULT_WORKERS, ge=1, le=MAX_WORKERS)
    reuse_results: StrictBool = True
    prepare_data: StrictBool = True
    execution_settings: ExecutionSettings
    sample_split: SplitDeclaration
    from_date: StrictStr | None = None
    to_date: StrictStr | None = None
