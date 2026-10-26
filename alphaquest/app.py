"""One local server: static portal and dataset API."""

import hashlib
import os
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryFile
from threading import Lock
from uuid import UUID
from zoneinfo import available_timezones

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .datasets import MAX_BYTES, DatasetStore, DuplicateDataset, InvalidDataset, instrument_settings, validate_csv_file
from .backtest_api import router as backtest_router
from .backtest_runs import RunStore
from .optimization import OptimizationStore
from .optimization_api import router as optimization_router
from .prop_api import router as prop_router
from .prop.store import AnalysisStore

WEB = Path(__file__).parent / "web"


class InstrumentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tick_size: StrictStr = Field(max_length=128)
    point_value: StrictStr = Field(max_length=128)


class ProgressTracker:
    """Small in-memory snapshots for the current portal's requests."""

    def __init__(self):
        self.states = OrderedDict()
        self.lock = Lock()

    def start(self, operation_id, initial=None):
        with self.lock:
            if operation_id in self.states:
                raise HTTPException(409, "This progress identifier has already been used.")
            self.states[operation_id] = initial if initial is not None else {"stage": "uploading", "completed_bytes": 0, "total_bytes": None, "rows_checked": 0}
            while len(self.states) > 128:
                self.states.popitem(last=False)

    def update(self, operation_id, stage, completed_bytes=0, total_bytes=None, rows_checked=0):
        now = time.monotonic()
        with self.lock:
            previous = self.states.get(operation_id)
            if previous is None:
                return
            if previous["stage"] == stage and now - previous.get("updated_at", 0) < .2 and completed_bytes != total_bytes:
                return
            self.states[operation_id] = {"stage": stage, "completed_bytes": completed_bytes, "total_bytes": total_bytes, "rows_checked": rows_checked, "updated_at": now}

    def get(self, operation_id):
        with self.lock:
            state = self.states.get(operation_id)
            return {key: value for key, value in state.items() if key != "updated_at"} if state else None

    def update_backtest(self, operation_id, run_id, stage, processed, total):
        with self.lock:
            previous = self.states.get(operation_id)
            if previous is not None and previous.get("run_id") == run_id:
                self.states[operation_id] = {"stage": stage, "bars_processed": processed,
                                             "total_bars": total, "run_id": previous["run_id"]}

    def fail_backtest(self, operation_id, run_id, error):
        with self.lock:
            previous = self.states.get(operation_id)
            if previous is not None and previous.get("run_id") == run_id:
                self.states[operation_id] = {**previous, "stage": "failed", "error": error}


def create_app(db_path: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = DatasetStore(db_path or Path(os.environ.get("ALPHAQUEST_DATA_DIR", "data")) / "datasets.sqlite3")
        app.state.runs = RunStore(app.state.store.path.parent)
        app.state.optimizations = OptimizationStore(app.state.runs)
        app.state.prop_analyses = AnalysisStore(app.state.store.path.parent)
        app.state.progress = ProgressTracker()
        yield
        await run_in_threadpool(app.state.optimizations.close)
        app.state.prop_analyses.close()

    app = FastAPI(title="AlphaQuest dataset portal", lifespan=lifespan)
    app.include_router(backtest_router)
    app.include_router(optimization_router)
    app.include_router(prop_router)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_browser_requests(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin changes are not allowed."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.url.path.startswith("/static/") and request.url.path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.exception_handler(InvalidDataset)
    async def invalid_dataset(request, exc):
        return JSONResponse({"detail": "CSV validation failed.", "errors": exc.errors, "truncated": exc.truncated}, status_code=422)

    @app.exception_handler(DuplicateDataset)
    async def duplicate_dataset(request, exc):
        return JSONResponse({"detail": "This exact CSV with this timezone is already saved. Open it in the library.", "dataset_id": exc.dataset_id}, status_code=409)

    @asynccontextmanager
    async def uploaded_csv(request: Request, progress=None):
        # Disk-backed staging avoids several gigabytes of copies for a large upload.
        with TemporaryFile(mode="w+b") as source:
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "The CSV exceeds the 1 GB limit.")
                await run_in_threadpool(source.write, chunk)
                if progress:
                    progress("uploading", size, None, 0)
            yield source

    def track(request, progress_id):
        if progress_id is None:
            return None
        operation_id = str(progress_id)
        request.app.state.progress.start(operation_id)
        return lambda *args: request.app.state.progress.update(operation_id, *args)

    @app.get("/", include_in_schema=False)
    def index():
        digest = hashlib.sha256()
        for asset in sorted([*WEB.glob("*.js"), *WEB.glob("*.css")]):
            digest.update(asset.name.encode() + asset.read_bytes())
        markup = (WEB / "index.html").read_text().replace("ASSET_VERSION", digest.hexdigest()[:16])
        return HTMLResponse(markup, headers={"Cache-Control": "no-cache"})

    @app.get("/api/datasets")
    def list_datasets(request: Request):
        return request.app.state.store.list()

    @app.get("/api/timezones")
    def list_timezones():
        return sorted(available_timezones() | {"UTC"})

    @app.get("/api/progress/{progress_id}")
    async def get_progress(progress_id: UUID, request: Request):
        state = request.app.state.progress.get(str(progress_id))
        if state is None:
            raise HTTPException(404, "Progress not found. The server may have restarted.")
        return JSONResponse(state, headers={"Cache-Control": "no-store"})

    @app.post("/api/datasets/validate")
    async def validate(request: Request, filename: str = Query(max_length=1024), source_timezone: str = Query(default="UTC", max_length=100), progress_id: UUID | None = None):
        progress = track(request, progress_id)
        try:
            async with uploaded_csv(request, progress) as source:
                result = await run_in_threadpool(validate_csv_file, source, filename, source_timezone, progress)
            if progress:
                progress("done", result["bytes"], result["bytes"], result["row_count"])
            return result
        except Exception:
            if progress:
                progress("failed")
            raise

    @app.post("/api/datasets", status_code=201)
    async def save(request: Request, filename: str = Query(max_length=1024), name: str = Query(min_length=1, max_length=120), symbol: str = Query(default="", max_length=40), source_timezone: str = Query(default="UTC", max_length=100), progress_id: UUID | None = None,
                   tick_size: str | None = Query(default=None, max_length=128), point_value: str | None = Query(default=None, max_length=128)):
        if not name.strip():
            raise HTTPException(422, "Give the dataset a name.")
        settings = None
        if tick_size is not None or point_value is not None:
            try:
                settings = instrument_settings(tick_size, point_value)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
        progress = track(request, progress_id)
        try:
            async with uploaded_csv(request, progress) as source:
                # Saving always revalidates the complete bytes; client state is not trusted.
                metadata = await run_in_threadpool(validate_csv_file, source, filename, source_timezone, progress)
                if settings is not None:
                    metadata["instrument_settings"] = settings
                result = await run_in_threadpool(request.app.state.store.save_file, source, metadata, name.strip(), symbol.strip(), progress)
            if progress:
                progress("done", result["bytes"], result["bytes"], result["row_count"])
            return result
        except Exception:
            if progress:
                progress("failed")
            raise

    @app.get("/api/datasets/{dataset_id}")
    def get_dataset(dataset_id: str, request: Request):
        dataset = request.app.state.store.get(dataset_id)
        if dataset is None:
            raise HTTPException(404, "Dataset not found.")
        return dataset

    @app.patch("/api/datasets/{dataset_id}/instrument-settings")
    def update_instrument_settings(dataset_id: str, body: InstrumentSettings, request: Request):
        try:
            dataset = request.app.state.store.set_instrument_settings(dataset_id, body.tick_size, body.point_value)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        if dataset is None:
            raise HTTPException(404, "Dataset not found.")
        return dataset

    @app.get("/api/datasets/{dataset_id}/csv")
    def download_dataset(dataset_id: str, request: Request):
        dataset = request.app.state.store.get(dataset_id)
        if dataset is None:
            raise HTTPException(404, "Dataset not found.")
        return StreamingResponse(request.app.state.store.iter_csv(dataset_id), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="dataset-{dataset_id}.csv"', "Content-Length": str(dataset["bytes"])})

    @app.delete("/api/datasets/{dataset_id}", status_code=204, response_class=Response)
    def delete_dataset(dataset_id: str, request: Request):
        if not request.app.state.store.delete(dataset_id):
            raise HTTPException(404, "Dataset not found.")
        return Response(status_code=204)

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app


app = create_app()
