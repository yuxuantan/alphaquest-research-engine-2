"""HTTP boundary and worker orchestration; strategy/fill/report logic is reused."""

from decimal import Decimal, InvalidOperation
from contextlib import ExitStack
import hashlib
import json
import sqlite3
from tempfile import TemporaryDirectory
from time import monotonic
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse,JSONResponse,Response

from .backtest_data import DatasetReadError, DateRange, read_selected_bars
from .backtest_runs import RunStore
from .backtest_config import RunSettings, instrument_overrides
from .datasets import COLUMNS, InvalidDataset
from .execution import ExecutionError, execute
from .session_calendar import CalendarError
from .reporting import ReportError, generate_report, json_value
from .report_chart import equity_preview
from .strategies.registry import get_strategy, list_strategies
from .strategy_features import create_strategy
from .prop.automatic import descriptor, compute_default, publish_backtest
from .performance import Performance, save_performance
from .market_benchmark import VERSION as BENCHMARK_VERSION, BenchmarkSettings, MarketBenchmark, load_comparison, comparison_preview, file_hash


from .backtest_requests import ExecutionSettings,OptimizationRequest
from .research import SplitDeclaration, ResearchConflict, dates_for, metadata as research_metadata


class BacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: StrictStr = Field(min_length=1, max_length=128)
    strategy_id: StrictStr = Field(min_length=1, max_length=128)
    strategy_parameters: dict[str, Any]
    execution_settings: ExecutionSettings
    sample_split: SplitDeclaration
    market_benchmark: BenchmarkSettings = Field(default_factory=BenchmarkSettings)
    from_date: StrictStr | None = None
    to_date: StrictStr | None = None
    report_detail: Literal['compact','full'] = 'compact'
    reuse_prepared: bool = True
    reuse_results: bool = True
    reuse_calculations: bool = True


def prepare_backtest_report(store, output, dataset, definition, parameters, config, date_range, progress,
                            *, report_detail="full", compress_report=False, source_run_id=None,
                            prepared=None, feature_paths=None, automatic_prop=None, timings=None, research=None, risk_replay=False, market_benchmark=None,
                            execution_scenario=None, capture_decisions=True, account_control=None, control_metadata=None):
    from .execution_scenarios import resolve_execution_scenario, scenario_metadata
    saved_scenario = scenario_metadata(config, execution_scenario)
    config, fill_assumptions = resolve_execution_scenario(config, execution_scenario)
    if not getattr(definition.module, 'SUPPORTS_DECISION_CAPTURE', True):
        # Paired entry stops require a future multi-pending decision contract.
        # Retain ordinary trade/risk reports without inventing that evidence.
        capture_decisions = False
    timings = timings or Performance()
    processed = 0
    total = 0 if date_range and date_range.active else dataset["row_count"]

    def stage(name):
        progress(name, processed, total)

    stage("preparing")
    metadata = {"dataset": {key: dataset[key] for key in ("id", "name", "sha256", "source_timezone", "row_count", "instrument_settings")},
                "instrument": {key:dataset.get(key) for key in ("symbol","interval_seconds","interval_kind")},
                "strategy": definition.provenance(parameters),
                "instrument_overrides": instrument_overrides(dataset, config)}
    metadata["full_dataset"] = {key:dataset.get(key) for key in ("id","name","sha256","source_timezone","row_count","start","end","symbol")}
    if source_run_id:
        metadata["risk_from_run_id" if risk_replay else "detailed_from_run_id"] = source_run_id
    if research:
        metadata["research"] = research
    if automatic_prop:
        metadata["automatic_prop_analysis"] = automatic_prop
    if saved_scenario is not None:
        metadata['execution_scenario'] = saved_scenario
    if account_control is not None:
        if report_detail != 'compact' or compress_report or automatic_prop or not control_metadata:
            raise ValueError('Controlled native replay requires compact capture, explicit provenance and no automatic prop report.')
        metadata['native_account_control'] = control_metadata
    with ExitStack() as stack:
        with timings.span('source_loading'):
            selected = stack.enter_context(prepared.selected() if prepared else read_selected_bars(store, dataset["id"], date_range))
            strategy = stack.enter_context(create_strategy(definition, parameters, config, feature_paths or {}, instrument_symbol=dataset.get("symbol")))
        total = selected.row_count
        metadata["selection"] = selected.metadata
        if hasattr(strategy, "session_flattening"):
            metadata["strategy"]["session_flattening"] = strategy.session_flattening
        comparison = MarketBenchmark(config, market_benchmark, metadata, total, source_backtest_id=Path(output).name)
        # The source iterator advances here only after the engine's current
        # callback/fill. Final-bar count is visible before report publication.
        def counted_bars():
            nonlocal processed
            last_update=monotonic()
            for bar in timings.iterate(selected.bars, 'source_loading'):
                yield bar
                processed = bar.bar_number
                # Small replays retain per-bar responsiveness. Long replays
                # avoid a callback/lock/IPC attempt for every completed bar.
                # Check time only every 64 bars for expensive future strategies.
                if (total <= 1000 or processed == total or processed % 1000 == 0
                        or (processed % 64 == 0 and monotonic()-last_update >= .25)):
                    stage("replaying")
                    last_update=monotonic()

        stage("replaying")
        events = timings.iterate(execute(counted_bars(), strategy, config, capture_risk=True,
            observe_bar=comparison.set_bar, fill_assumptions=fill_assumptions, capture_decisions=capture_decisions,
            account_control=account_control, completion='require_flat' if account_control is not None else 'strategy_finish'), 'replay')
        with timings.span('report_writing'):
            manifest = generate_report(events, output, config,
                                       execution_assumption=definition.execution_assumption,
                                       metadata=metadata, expected_bar_count=total, on_saving=lambda: stage("saving_report"),
                                       detail=report_detail, compress=compress_report, capture_risk=True, market_benchmark=comparison, capture_decisions=capture_decisions)
    if account_control is not None:
        result = account_control.finish_replay()
        path = Path(output) / 'native_account_control.json'
        path.write_text(json.dumps(result, default=json_value, allow_nan=False, sort_keys=True), encoding='utf-8')
        if path.stat().st_size > 100 * 1024 * 1024:
            raise ValueError('Native control capture exceeds 100 MiB; narrow the declared session window.')
        manifest['artifacts']['native_account_control_json'] = path.name
        manifest['native_account_control'] = dict(version='native-account-control-v1', sha256=file_hash(path),
            analysis_id=control_metadata['analysis_id'], phase=account_control.phase)
        (Path(output) / 'report.json').write_text(json.dumps(manifest, default=json_value, allow_nan=False, indent=2) + '\n', encoding='utf-8')
    return manifest, processed, total


def run_backtest(store, runs: RunStore, run_id, dataset, definition, parameters, config, date_range, progress,
                 *, compress_report=False, source_record=None, prop_analyses=None, report_detail='compact',reuse_prepared=True,reuse_results=True,reuse_calculations=True,research=None,risk_replay=False,market_benchmark=None,
                 execution_scenario=None, account_control=None, control_metadata=None):
    from . import backtest_cache
    from .research_access import guard_read, metadata_only
    guard_read(store,dataset['id'],date_range,kind='strategy_execution',origin='backtest:'+run_id)
    from .execution_scenarios import parse_execution_scenario, resolve_execution_scenario, restore_scenario_config
    execution_scenario = parse_execution_scenario(execution_scenario)
    if source_record and source_record.get('native_account_control'):
        raise ReportError('This report contains native account control. Use its saved full trades, decision capture and prop analysis; generic detail/risk replay cannot reproduce its account state.')
    if account_control is not None:
        if source_record or prop_analyses or execution_scenario is not None:
            raise ReportError('Native account replay requires its dedicated checked request and saved source execution costs.')
        reuse_results = False
    # New native runs retain decision provenance. Reproduction of an earlier
    # report keeps its capture contract; historical missing stops stay missing.
    capture_decisions = source_record is None or source_record.get('execution_decisions') is not None
    if source_record is not None and capture_decisions:
        from .decision_capture import VERSION as DECISION_VERSION, SIDE_CAR
        description = source_record['execution_decisions']
        original_path = runs.root / source_record['id'] / SIDE_CAR
        if (description.get('version') != DECISION_VERSION
                or source_record.get('artifacts', {}).get('execution_decisions_jsonl') != SIDE_CAR
                or original_path.is_symlink() or not original_path.is_file()
                or file_hash(original_path) != description.get('sha256')):
            raise ReportError('Saved native decision provenance is missing, changed or unsupported; no replay was published.')
    definition.validate_source(parameters, dataset)
    market_benchmark = BenchmarkSettings.model_validate(market_benchmark or {}).model_dump()
    if source_record:
        market_benchmark = source_record.get('market_benchmark', {}).get('settings', market_benchmark)
        saved_scenario = source_record['run_metadata'].get('execution_scenario')
        if saved_scenario is not None:
            baseline_config, inherited = restore_scenario_config(saved_scenario)
            if execution_scenario is not None and execution_scenario != inherited:
                raise ReportError('Detailed or risk replay cannot override the saved execution scenario.')
            if resolve_execution_scenario(baseline_config, inherited)[0] != config:
                raise ReportError('Saved scenario execution settings do not match the requested replay.')
            config, execution_scenario = baseline_config, inherited
        elif execution_scenario is not None:
            raise ReportError('Detailed or risk replay cannot add an execution scenario to an earlier source.')
    reuse_key=None
    if not source_record and account_control is None:
        reuse_key=backtest_cache.key(dataset,definition,parameters,config,date_range,report_detail,compress_report,bool(prop_analyses),research,market_benchmark,
                                    execution_scenario=execution_scenario)
        if reuse_results:
            reused=backtest_cache.lookup(runs,prop_analyses,reuse_key)
            if reused:
                from .backtest_data import read_bars
                with metadata_only(),read_bars(store,dataset['id']):pass
                count=reused['run_metadata']['selection']['row_count']
                progress('done',count,count)
                return reused
    with TemporaryDirectory(prefix=".pending-", dir=runs.root) as temporary:
        timings = Performance()
        output = Path(temporary) / run_id
        automatic = source_record["run_metadata"].get("automatic_prop_analysis") if source_record and not risk_replay else descriptor() if prop_analyses else None
        prepared,features=None,{}
        if reuse_prepared:
            from .prepared_data import prepare_data
            from .strategy_features import prepare_features
            with timings.span('source_loading'):
                prepared=prepare_data(store,dataset['id'],date_range,Path(temporary)/'bars.bin',progress,cache=runs.replay_cache)
                timings.details['source_cache_hit']=prepared.cache_hit
                values=json.loads(json.dumps(definition.provenance(parameters)['parameters'],default=json_value))
                features=prepare_features(definition,prepared,[values],Path(temporary),progress,workers=0,cache=runs.replay_cache)
                timings.details['prepared_feature_series']=len(features)
        manifest, processed, total = prepare_backtest_report(
            store, output, dataset, definition, parameters, config, date_range, progress,
            compress_report=compress_report, source_run_id=source_record["id"] if source_record else None,
            automatic_prop=automatic, timings=timings, report_detail='full' if source_record and not risk_replay else report_detail,prepared=prepared,feature_paths=features,research=research,risk_replay=risk_replay,market_benchmark=market_benchmark,
            execution_scenario=execution_scenario, capture_decisions=capture_decisions,
            account_control=account_control, control_metadata=control_metadata)
        if source_record:
            if json.loads(json.dumps(manifest["summary"], default=json_value)) != source_record["summary"]:
                raise ReportError("Detailed replay metrics differ from the saved report. No detailed report was published.")
            for name in ("trades.csv", "equity.csv"):
                with (runs.root / source_record["id"] / name).open("rb") as original, (output / name).open("rb") as replay:
                    if hashlib.file_digest(original, "sha256").digest() != hashlib.file_digest(replay, "sha256").digest():
                        raise ReportError("Detailed replay trades/equity differ from the saved report. No detailed report was published.")
            if capture_decisions:
                from .decision_capture import SIDE_CAR
                if (manifest.get('execution_decisions') != source_record['execution_decisions']
                        or file_hash(output / SIDE_CAR) != source_record['execution_decisions']['sha256']):
                    raise ReportError('Detailed replay decision provenance differs from the saved report. No detailed report was published.')
        prop_result = None
        if (not source_record or risk_replay) and prop_analyses:
            with timings.span('prop_analysis'):
                prop_result = compute_default(Path(temporary), run_id, manifest, Path(temporary)/"prop", automatic,
                                              lambda message: progress("prop_simulation: " + message, processed, total), runtime=prop_analyses.runtime,calculation_cache=prop_analyses.calculation_snapshot() if reuse_calculations else None)
            timings.details['prop_backend']=prop_result.get('native_kernel',{}).get('name','source incompatible')
            timings.details['prop_execution']=prop_result.get('prop_execution',{})
            timings.details['prop_calculation_reused_from']=prop_result.get('calculation_reused_from')
        progress("saving_results", processed, total)
        with timings.span('publication'):
            record = publish_backtest(runs, prop_analyses, run_id, output, manifest, prop_result, Path(temporary)/"prop")
        save_performance(runs.root/run_id, timings.snapshot())
    if reuse_key:backtest_cache.save(runs,prop_analyses,reuse_key,record)
    progress("done", processed, total)
    return record


router = APIRouter()


async def _import_bytes(request):
    from .canonical_trades import MAX_EXPORT_BYTES
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_EXPORT_BYTES:
            raise HTTPException(422, 'Trade export exceeds the 32 MiB input limit.')
    return bytes(content)


@router.post('/api/backtests/imports/check')
async def check_trade_import(request: Request, filename: str = Query('trade-export.json', min_length=1, max_length=255)):
    from .trade_imports import preview_import
    from .canonical_trades import parse_trade_export
    raw = await _import_bytes(request)
    try:
        normalized=await run_in_threadpool(parse_trade_export,raw)
        await run_in_threadpool(request.app.state.research_access.observe_external,normalized,origin='external_import_check')
        return await run_in_threadpool(preview_import, raw, filename)
    except ResearchConflict as exc:
        raise HTTPException(409,str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post('/api/backtests/imports')
async def import_trades(request: Request, filename: str = Query('trade-export.json', min_length=1, max_length=255)):
    from .trade_imports import ImportConflict, save_import
    from .canonical_trades import parse_trade_export
    raw = await _import_bytes(request)
    try:
        normalized=await run_in_threadpool(parse_trade_export,raw)
        await run_in_threadpool(request.app.state.research_access.observe_external,normalized,origin='external_import_save')
        record, created = await run_in_threadpool(save_import, request.app.state.runs, raw, filename)
        return JSONResponse(record, status_code=201 if created else 200)
    except ImportConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except ResearchConflict as exc:
        raise HTTPException(409,str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


def _verify_external(request, record):
    from .trade_imports import external, verify_import_artifacts
    if external(record):
        try:
            verify_import_artifacts(request.app.state.runs, record)
        except (ValueError, OSError) as exc:
            raise HTTPException(409, str(exc)) from None


def _native_replay_only(record):
    from .trade_imports import external
    if external(record):
        raise HTTPException(409, 'Imported trades have no local strategy/price replay. Supply a new external export; no bars or missing risk observations are fabricated.')


@router.get("/api/strategies")
def strategies():
    return list_strategies()


@router.post("/api/backtests", status_code=201)
async def start_backtest(body: BacktestRequest | OptimizationRequest, request: Request, progress_id: UUID | None = None):
    if isinstance(body,OptimizationRequest):
        from .optimization_api import start
        from starlette.responses import JSONResponse
        return JSONResponse(await start(body,request),status_code=202)
    try:
        definition = get_strategy(body.strategy_id)
        parameters = definition.parameters(body.strategy_parameters)
        if body.from_date is not None or body.to_date is not None:
            raise ValueError('Declare IS/OOS with sample_split instead of from_date/to_date.')
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from None
    dataset = await run_in_threadpool(request.app.state.store.get, body.dataset_id)
    if dataset is None:
        raise HTTPException(404, "Dataset not found.")
    if dataset.get("columns") != COLUMNS:
        raise HTTPException(422, "Unsupported dataset schema. Backtests require: " + ",".join(COLUMNS))
    try:
        definition.validate_source(parameters, dataset)
        config = body.execution_settings.execution_config(dataset)
        plan = await run_in_threadpool(request.app.state.research.resolve, request.app.state.store, dataset, body.strategy_id, body.sample_split)
        await run_in_threadpool(request.app.state.research.claim, plan)
        date_range = dates_for(plan)
    except ResearchConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from None
    return await execute_backtest(request, dataset, definition, parameters, config, date_range, progress_id,report_detail=body.report_detail,reuse_prepared=body.reuse_prepared,reuse_results=body.reuse_results,reuse_calculations=body.reuse_calculations,research=research_metadata(plan),market_benchmark=body.market_benchmark.model_dump())


async def execute_backtest(request, dataset, definition, parameters, config, date_range, progress_id,
                           *, compress_report=False, source_record=None, report_detail='compact',reuse_prepared=True,reuse_results=True,reuse_calculations=True,research=None,run_id_override=None,risk_replay=False,market_benchmark=None,
                           execution_scenario=None,automatic_prop=True):
    run_id = run_id_override or uuid4().hex
    tracker = request.app.state.progress
    operation_id = str(progress_id) if progress_id else None
    if operation_id:
        tracker.start(operation_id, {"stage": "preparing", "bars_processed": 0,
                                     "total_bars": 0 if date_range.active else dataset["row_count"], "run_id": run_id})

    def progress(stage, processed, total):
        if operation_id:
            tracker.update_backtest(operation_id, run_id, stage, processed, total)

    try:
        record = await run_in_threadpool(run_backtest, request.app.state.store, request.app.state.runs, run_id,
                                       dataset, definition, parameters, config, date_range, progress,
                                       compress_report=compress_report, source_record=source_record,
                                       prop_analyses=request.app.state.prop_analyses if automatic_prop else None, report_detail=report_detail,reuse_prepared=reuse_prepared,reuse_results=reuse_results,reuse_calculations=reuse_calculations,research=research,risk_replay=risk_replay,market_benchmark=market_benchmark,
                                       execution_scenario=execution_scenario)
        if record['id']!=run_id:
            if operation_id:
                count=record['run_metadata']['selection']['row_count']
                tracker.update_backtest(operation_id,run_id,'done',count,count,resolved_run_id=record['id'])
            return JSONResponse(record,status_code=200,headers={'X-AlphaQuest-Reused':'true'})
        return record
    except Exception as exc:
        if operation_id:
            tracker.fail_backtest(operation_id, run_id, str(exc))
        if isinstance(exc, (DatasetReadError, InvalidDataset, ExecutionError, ReportError, CalendarError)):
            raise HTTPException(422, str(exc)) from None
        raise HTTPException(500, "Backtest failed; no completed run was saved.") from exc


@router.post("/api/backtests/{run_id}/detailed", status_code=201)
async def detailed(run_id: UUID, request: Request, progress_id: UUID | None = None):
    record = await run_in_threadpool(request.app.state.runs.get, run_id.hex)
    if record is None:
        raise HTTPException(404, "Completed backtest not found.")
    _native_replay_only(record)
    if record.get('run_metadata',{}).get('research',{}).get('phase') != 'is':
        raise HTTPException(409, 'Only declared IS reports can be replayed for detail. OOS replays require a manual OOS request from IS; legacy reports remain read-only.')
    if record.get("report_storage", {}).get("detail") != "compact":
        raise HTTPException(409, "This report already retains full detail.")
    runs = request.app.state.runs
    try:
        cached = await run_in_threadpool(runs.claim_detail, record["id"])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    if cached:
        return cached
    try:
        return await generate_detail(request, record, progress_id)
    finally:
        runs.release_detail(record["id"])


@router.post('/api/backtests/{run_id}/risk', status_code=201)
async def capture_risk(run_id: UUID, request: Request, progress_id: UUID | None = None):
    """Verified compact IS replay; preserves the source and its saved analysis."""
    runs = request.app.state.runs
    record = await run_in_threadpool(runs.get, run_id.hex)
    if record is None:
        raise HTTPException(404, 'Completed backtest not found.')
    _native_replay_only(record)
    if record.get('run_metadata', {}).get('research', {}).get('phase') != 'is':
        raise HTTPException(409, 'Risk capture replay requires declared IS. OOS needs a new explicit manual OOS run from IS; legacy reports remain read-only.')
    if record.get('intratrade_risk'):
        return record
    try:
        cached = await run_in_threadpool(runs.claim_detail, record['id'], 'risk')
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    if cached:
        return cached
    try:
        return await generate_detail(request, record, progress_id, risk_replay=True)
    finally:
        runs.release_detail(record['id'])


async def generate_detail(request, record, progress_id, *, risk_replay=False):
    _native_replay_only(record)
    metadata = record["run_metadata"]
    dataset = await run_in_threadpool(request.app.state.store.get, metadata["dataset"]["id"])
    if dataset is None:
        raise HTTPException(422, "The original dataset is missing; it is required to generate per-bar detail.")
    try:
        if any(dataset[key] != metadata["dataset"][key] for key in ("sha256", "source_timezone", "row_count")):
            raise ValueError("The dataset no longer matches the saved report.")
        definition = get_strategy(metadata["strategy"]["id"])
        if definition.description()["source_sha256"] != metadata["strategy"]["source_sha256"]:
            raise ValueError("Strategy source has changed; detailed replay requires the original strategy.")
        if record.get('market_benchmark', {}).get('version', BENCHMARK_VERSION) != BENCHMARK_VERSION:
            raise ValueError('The saved benchmark model version is no longer supported for replay. Run a new IS backtest; the saved comparison remains readable.')
        parameters = definition.parameters(metadata["strategy"]["parameters"])
        config = ExecutionSettings.model_validate(record["execution_settings"]).execution_config(dataset)
        selection = metadata["selection"]
        dates = DateRange.parse(selection.get("from_date"), selection.get("to_date"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from None
    return await execute_backtest(request, dataset, definition, parameters, config, dates, progress_id,
                                   compress_report=True, source_record=record,research=metadata['research'],risk_replay=risk_replay)


@router.get("/api/backtests")
def completed_runs(request: Request, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000)):
    return request.app.state.runs.list(offset, limit)


@router.get("/api/backtests/{run_id}")
def completed_run(run_id: UUID, request: Request):
    record = request.app.state.runs.get(run_id.hex)
    if record is None:
        raise HTTPException(404, "Completed backtest not found.")
    _verify_external(request, record)
    return record


@router.delete('/api/backtests/{run_id}',status_code=204)
def delete_run(run_id: UUID,request: Request):
    analyses=request.app.state.prop_analyses
    try:
        with analyses.lock:
            busy=run_id.hex in analyses.active_sources()
            if busy:
                refs=analyses.source_references(run_id.hex)
                owners='; '.join(f"{r['kind'].replace('_',' ')} {r['id']}" for r in refs)
                raise ValueError('This backtest is referenced by a research campaign or a running prop analysis; it cannot be deleted. '
                    'Retained references: '+owners)
            deleted=request.app.state.runs.delete(run_id.hex)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from None
    except OSError as exc:
        raise HTTPException(500,str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(500,'Could not update the backtest catalogue. No deletion was committed; try again.') from exc
    if not deleted:raise HTTPException(404,'Completed backtest not found.')


def result_page(request, run_id, kind, offset, limit):
    record = request.app.state.runs.get(run_id.hex)
    if record is not None:
        _verify_external(request, record)
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
    _verify_external(request, record)
    try:
        result = equity_preview(runs.root / run_id.hex / "equity.csv",
                                record["summary"]["trades_taken"] + 1, max_points)
        from .trade_imports import external
        if external(record):
            result['currency'] = record['run_metadata']['instrument']['currency']
        return result
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(500, "Saved equity chart could not be read.") from exc


@router.get('/api/backtests/{run_id}/performance')
def performance(run_id: UUID, request: Request):
    runs=request.app.state.runs
    if runs.get(run_id.hex) is None:raise HTTPException(404,'Completed backtest not found.')
    path=runs.root/run_id.hex/'performance.json'
    if not path.is_file():return dict(version=1,unavailable='Timing diagnostics were not captured for this historical report.')
    return json.loads(path.read_text())


@router.get('/api/backtests/{run_id}/market-benchmark')
def market_comparison(run_id: UUID, request: Request, max_points: int = Query(1000, ge=16, le=2000)):
    runs = request.app.state.runs
    record = runs.get(run_id.hex)
    if record is None:
        raise HTTPException(404, 'Completed backtest not found.')
    descriptor = record.get('market_benchmark')
    if descriptor is None:
        from .trade_imports import external
        if external(record):
            return dict(unavailable='This imported trade source has no local price bars. No market benchmark or per-bar equity was fabricated.')
        return dict(unavailable='This saved report predates market comparisons. Its results are preserved. Run a new IS backtest to capture a comparison; OOS execution remains a manual action.')
    try:
        folder = runs.root / run_id.hex
        return dict(**load_comparison(folder, descriptor), chart=comparison_preview(folder, descriptor, max_points))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(500, 'Saved market comparison could not be verified. No comparison was recalculated.') from exc


@router.get("/api/backtests/{run_id}/exports/{kind}")
def download(run_id: UUID, kind: str, request: Request):
    runs = request.app.state.runs
    record = runs.get(run_id.hex)
    if kind not in ("trades", "equity", "report", "performance", "intratrade_risk", "market_benchmark", "market_equity", "source", "canonical_source", "execution_decisions", "native_account_control", "is_screening") or record is None:
        raise HTTPException(404, "Completed backtest export not found.")
    _verify_external(request, record)
    if kind == 'is_screening':
        from .workflow_criteria import FILE, verified_screening
        try:
            verified_screening(runs, record)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return FileResponse(runs.root / run_id.hex / FILE, media_type='application/json', filename=f'{run_id.hex}-{FILE}')
    if kind == 'native_account_control':
        description = record.get('native_account_control')
        path = runs.root / run_id.hex / 'native_account_control.json'
        if not description:
            raise HTTPException(404, 'This report has no native account-control capture.')
        if path.is_symlink() or not path.is_file() or file_hash(path) != description.get('sha256'):
            raise HTTPException(409, 'Saved native account-control capture is missing or changed.')
        return FileResponse(path, media_type='application/json', filename=f'{run_id.hex}-native_account_control.json')
    if kind == 'execution_decisions':
        from .decision_capture import SIDE_CAR, VERSION as DECISION_VERSION
        description = record.get('execution_decisions')
        path = runs.root / run_id.hex / SIDE_CAR
        if description is None:
            raise HTTPException(404, 'This historical report has no captured native decision evidence.')
        if (description.get('version') != DECISION_VERSION
                or record.get('artifacts', {}).get('execution_decisions_jsonl') != SIDE_CAR
                or path.is_symlink() or not path.is_file()
                or file_hash(path) != description.get('sha256')):
            raise HTTPException(409, 'Saved native decision evidence is missing, changed or unsupported.')
        return FileResponse(path, media_type='application/x-ndjson', filename=f'{run_id.hex}-{SIDE_CAR}')
    if kind in ('source', 'canonical_source'):
        from .trade_imports import external, SOURCE_FILES
        if not external(record):
            raise HTTPException(404, 'This report has no preserved external trade export.')
        return FileResponse(runs.root/run_id.hex/SOURCE_FILES[kind], media_type='application/json',
                            filename=f'{run_id.hex}-{SOURCE_FILES[kind]}')
    if kind == 'market_equity' and record.get('market_benchmark', {}).get('storage'):
        from .market_equity import equity_csv
        try:
            folder = runs.root / run_id.hex
            load_comparison(folder, record['market_benchmark'])
            content = equity_csv(folder, record['market_benchmark'])
            if hashlib.sha256(content).hexdigest() != record['market_benchmark']['equity_sha256']:
                raise ValueError('Saved daily export integrity check failed.')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(500, 'Saved daily comparison could not be verified. No comparison was recalculated.') from exc
        return Response(content, media_type='text/csv', headers={
            'Content-Disposition': f'attachment; filename="{run_id.hex}-market_equity_day.csv"'})
    name = record["artifacts"]["report"] if kind == "report" else f'{kind}.json' if kind in ('performance', 'market_benchmark') else f"{kind}.csv"
    if name not in ("report.json", "report.json.gz", "trades.csv", "equity.csv", "performance.json", "intratrade_risk.csv", "market_benchmark.json", "market_equity.csv"):
        raise HTTPException(404, "Unknown report artifact.")
    path = runs.root / run_id.hex / name
    if not path.is_file():
        raise HTTPException(404, "Saved CSV not found.")
    if kind in ('market_benchmark', 'market_equity'):
        descriptor = record.get('market_benchmark')
        if not descriptor:
            raise HTTPException(404, 'This report has no saved market comparison.')
        if file_hash(path) != descriptor['sha256' if kind == 'market_benchmark' else 'equity_sha256']:
            raise HTTPException(500, 'Saved market comparison integrity check failed.')
    media_type = "application/gzip" if name.endswith(".gz") else "application/json" if name.endswith('.json') else "text/csv"
    return FileResponse(path, media_type=media_type, filename=f"{run_id.hex}-{name}")
