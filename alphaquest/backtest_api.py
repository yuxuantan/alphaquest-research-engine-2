"""HTTP boundary and worker orchestration; strategy/fill/report logic is reused."""

from decimal import Decimal, InvalidOperation
from tempfile import TemporaryDirectory
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from .backtest_data import DatasetReadError, read_bars
from .backtest_runs import RunStore
from .datasets import COLUMNS, InvalidDataset
from .execution import ExecutionError, execute
from .reporting import ReportError, generate_report
from .report_chart import equity_preview
from .strategies.registry import get_strategy, list_strategies
from .strategy import ExecutionConfig


class ExecutionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    initial_capital: StrictStr
    tick_size: StrictStr
    point_value: StrictStr
    slippage_ticks: StrictInt = Field(ge=0)
    commission_per_contract_per_side: StrictStr

    def execution_config(self) -> ExecutionConfig:
        try:
            return ExecutionConfig(Decimal(self.initial_capital), Decimal(self.tick_size), Decimal(self.point_value),
                                   self.slippage_ticks, Decimal(self.commission_per_contract_per_side))
        except InvalidOperation:
            raise ValueError("Execution monetary values must be finite decimal strings.") from None


class BacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: StrictStr = Field(min_length=1, max_length=128)
    strategy_id: StrictStr = Field(min_length=1, max_length=128)
    strategy_parameters: dict[str, Any]
    execution_settings: ExecutionSettings


def run_backtest(store, runs: RunStore, run_id, dataset, definition, parameters, config, progress):
    processed = 0
    total = dataset["row_count"]

    def stage(name):
        progress(name, processed, total)

    stage("preparing")
    metadata = {"dataset": {key: dataset[key] for key in ("id", "name", "sha256", "source_timezone", "row_count")},
                "strategy": definition.provenance(parameters)}
    with TemporaryDirectory(prefix=".pending-", dir=runs.root) as temporary:
        output = Path(temporary) / "report"
        with read_bars(store, dataset["id"]) as bars:
            # The source iterator advances here only after the engine's current
            # callback/fill. Final-bar count is visible before report publication.
            def counted_bars():
                nonlocal processed
                for bar in bars:
                    yield bar
                    processed = bar.bar_number
                    stage("replaying")

            stage("replaying")
            manifest = generate_report(execute(counted_bars(), definition.factory(parameters), config), output, config,
                                       metadata=metadata, expected_bar_count=total, on_saving=lambda: stage("saving_report"))
        stage("saving_results")
        record = runs.complete(run_id, output, manifest)
    stage("done")
    return record


router = APIRouter()


@router.get("/api/strategies")
def strategies():
    return list_strategies()


@router.post("/api/backtests", status_code=201)
async def start_backtest(body: BacktestRequest, request: Request, progress_id: UUID | None = None):
    try:
        definition = get_strategy(body.strategy_id)
        parameters = definition.parameters(body.strategy_parameters)
        config = body.execution_settings.execution_config()
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from None
    dataset = await run_in_threadpool(request.app.state.store.get, body.dataset_id)
    if dataset is None:
        raise HTTPException(404, "Dataset not found.")
    if dataset.get("columns") != COLUMNS:
        raise HTTPException(422, "Unsupported dataset schema. Backtests require: " + ",".join(COLUMNS))
    run_id = uuid4().hex
    tracker = request.app.state.progress
    operation_id = str(progress_id) if progress_id else None
    if operation_id:
        tracker.start(operation_id, {"stage": "preparing", "bars_processed": 0,
                                     "total_bars": dataset["row_count"], "run_id": run_id})

    def progress(stage, processed, total):
        if operation_id:
            tracker.update_backtest(operation_id, run_id, stage, processed, total)

    try:
        return await run_in_threadpool(run_backtest, request.app.state.store, request.app.state.runs, run_id,
                                       dataset, definition, parameters, config, progress)
    except Exception as exc:
        if operation_id:
            tracker.fail_backtest(operation_id, run_id, str(exc))
        if isinstance(exc, (DatasetReadError, InvalidDataset, ExecutionError, ReportError)):
            raise HTTPException(422, str(exc)) from None
        raise HTTPException(500, "Backtest failed; no completed run was saved.") from exc


@router.get("/api/backtests")
def completed_runs(request: Request, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000)):
    return request.app.state.runs.list(offset, limit)


@router.get("/api/backtests/{run_id}")
def completed_run(run_id: UUID, request: Request):
    record = request.app.state.runs.get(run_id.hex)
    if record is None:
        raise HTTPException(404, "Completed backtest not found.")
    return record


def result_page(request, run_id, kind, offset, limit):
    page = request.app.state.runs.page(run_id.hex, kind, offset, limit)
    if page is None:
        raise HTTPException(404, "Completed backtest not found.")
    return page


@router.get("/api/backtests/{run_id}/trades")
def trade_page(run_id: UUID, request: Request, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000)):
    return result_page(request, run_id, "trades", offset, limit)


@router.get("/api/backtests/{run_id}/equity")
def equity_page(run_id: UUID, request: Request, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000)):
    return result_page(request, run_id, "equity", offset, limit)


@router.get("/api/backtests/{run_id}/chart")
def chart(run_id: UUID, request: Request, max_points: int = Query(1000, ge=16, le=2000)):
    runs = request.app.state.runs
    record = runs.get(run_id.hex)
    if record is None:
        raise HTTPException(404, "Completed backtest not found.")
    try:
        return equity_preview(runs.root / run_id.hex / "equity.csv",
                              record["summary"]["trades_taken"] + 1, max_points)
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(500, "Saved equity chart could not be read.") from exc


@router.get("/api/backtests/{run_id}/exports/{kind}")
def download(run_id: UUID, kind: str, request: Request):
    runs = request.app.state.runs
    if kind not in ("trades", "equity") or runs.get(run_id.hex) is None:
        raise HTTPException(404, "Completed backtest export not found.")
    path = runs.root / run_id.hex / f"{kind}.csv"
    if not path.is_file():
        raise HTTPException(404, "Saved CSV not found.")
    return FileResponse(path, media_type="text/csv", filename=f"{run_id.hex}-{kind}.csv")
