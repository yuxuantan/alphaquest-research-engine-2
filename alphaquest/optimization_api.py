"""Local exhaustive optimization API; each trial is a normal saved backtest."""

import csv
import io
import sqlite3
from dataclasses import asdict
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr
from starlette.concurrency import run_in_threadpool

from .backtest_api import ExecutionSettings
from .backtest_data import DateRange
from .datasets import COLUMNS
from .optimization import grid, DEFAULT_WORKERS, MAX_WORKERS
from .strategies.registry import get_strategy


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
    from_date: StrictStr | None = None
    to_date: StrictStr | None = None


router = APIRouter()


@router.get("/api/optimizations/settings")
def settings():
    return {"default_workers": DEFAULT_WORKERS, "max_workers": MAX_WORKERS}


@router.post("/api/optimizations", status_code=202)
async def start(body: OptimizationRequest, request: Request):
    try:
        definition = get_strategy(body.strategy_id)
        axes, total = await run_in_threadpool(grid, definition, body.parameter_ranges)
        dates = DateRange.parse(body.from_date, body.to_date)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from None
    dataset = await run_in_threadpool(request.app.state.store.get, body.dataset_id)
    if dataset is None:
        raise HTTPException(404, "Dataset not found.")
    if dataset.get("columns") != COLUMNS:
        raise HTTPException(422, "Unsupported dataset schema.")
    try:
        config = body.execution_settings.execution_config(dataset)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from None
    store = request.app.state.optimizations
    job = await run_in_threadpool(store.create, body, dataset, definition, config, axes, total)
    store.executor.submit(store.run, job, request.app.state.store, definition, config, dates)
    return job


@router.get("/api/optimizations")
def history(request: Request, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    return request.app.state.optimizations.list(offset, limit)


def get_job(request, job_id):
    job = request.app.state.optimizations.get(job_id.hex)
    if job is None:
        raise HTTPException(404, "Optimization not found.")
    return job


@router.get("/api/optimizations/{job_id}")
def detail(job_id: UUID, request: Request):
    return get_job(request, job_id)


@router.post("/api/optimizations/{job_id}/resume", status_code=202)
def resume(job_id: UUID, request: Request):
    try:
        job = get_job(request, job_id)
    except sqlite3.OperationalError as exc:
        raise HTTPException(503, str(exc)) from None
    if job["status"] not in ("failed", "interrupted"):
        raise HTTPException(409, "Only failed or interrupted optimizations can be resumed.")
    try:
        body = OptimizationRequest.model_validate(job["request"])
        definition = get_strategy(body.strategy_id)
        from .optimization_cache import engine_identity
        if job.get("engine_identity") and engine_identity() != job["engine_identity"]:
            raise ValueError("Engine code has changed since this optimization. Start a new job to keep results consistent.")
        if definition.description()["source_sha256"] != job["strategy"]["source_sha256"]:
            raise ValueError("Strategy source has changed since this optimization. Start a new job to keep results consistent.")
        axes, total = grid(definition, body.parameter_ranges)
        if axes != job["axes"] or total != job["total_trials"]:
            raise ValueError("The saved parameter grid no longer matches this strategy. Start a new optimization.")
        dataset = request.app.state.store.get(body.dataset_id)
        if dataset is None:
            raise ValueError("The original dataset is missing. Restore it before resuming.")
        if any(dataset.get(key) != job["dataset"].get(key) for key in ("sha256", "source_timezone", "row_count", "columns")):
            raise ValueError("The dataset no longer matches the saved source. Start a new optimization.")
        # Resolve defaults against the original instrument metadata, retaining
        # the exact costs/capital/tick settings of already successful trials.
        config = body.execution_settings.execution_config(job["dataset"])
        settings = {key: str(value) if isinstance(value, Decimal) else value for key, value in asdict(config).items()}
        if settings != job["execution_settings"]:
            raise ValueError("Execution settings no longer match this job. Start a new optimization.")
        dates = DateRange.parse(body.from_date, body.to_date)
    except sqlite3.OperationalError as exc:
        raise HTTPException(503, str(exc)) from None
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from None
    store = request.app.state.optimizations
    try:
        job = store.resume(job_id.hex)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    except sqlite3.OperationalError as exc:
        raise HTTPException(503, str(exc)) from None
    store.executor.submit(store.run, job, request.app.state.store, definition, config, dates)
    return job


@router.get("/api/optimizations/{job_id}/results")
def results(job_id: UUID, request: Request, sort: str = "trial", direction: str = "asc",
            offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=1000)):
    job = get_job(request, job_id)
    try:
        return request.app.state.optimizations.page(job, sort, direction, offset, limit)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/api/optimizations/{job_id}/exports/results")
def export(job_id: UUID, request: Request, sort: str = "trial", direction: str = "asc"):
    job = get_job(request, job_id)
    store = request.app.state.optimizations
    try:
        store.page(job, sort, direction, 0, 1)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    def stream():
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        prop_columns = ["prop_analysis_id", "prop_status", "prop_reason"] if job.get("default_prop_profile") else []
        writer.writerow(["trial", "run_id", *job["axes"], *job["metric_columns"], *prop_columns])
        yield buffer.getvalue()
        for offset in range(0, job["completed_trials"], 1000):
            for row in store.page(job, sort, direction, offset, min(1000, job["completed_trials"] - offset))["items"]:
                buffer.seek(0)
                buffer.truncate(0)
                writer.writerow([row["trial"], row["run_id"], *(row["parameters"][name] for name in job["axes"]),
                                 *(row["metrics"].get(name) for name in job["metric_columns"]),
                                 *(row.get("prop_analysis", {}).get(name) for name in (("id", "status", "reason") if prop_columns else ()))])
                yield buffer.getvalue()
    return StreamingResponse(stream(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="optimization-{job["id"]}.csv"'})
