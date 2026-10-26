"""Product configuration and source-compatibility workflow for completed runs."""

from dataclasses import asdict, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import re
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, TZPATH
from hashlib import sha256

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from .prop.calendar import CalendarDay, DataWindow, SessionCalendar, local_utc
from .prop.rules import PROFILE_IDS, get_profile, resolve_profile, resolve_simulation
from .prop.runs import catalog_record
from .prop.sessions import InstrumentDeclaration
from .prop.sessions import InputError
from .prop.engine import SimulationError
from .prop.types import ProfileFees, SimulationConfig, UserFees


router = APIRouter(prefix="/api/prop-simulations", tags=["Prop simulation setup"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WindowDeclaration(StrictModel):
    first_utc: StrictStr = Field(max_length=40)
    last_utc: StrictStr = Field(max_length=40)
    bar_interval_seconds: StrictInt = Field(ge=1, le=86400)


class DayDeclaration(StrictModel):
    trading_date: StrictStr = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: Literal["covered", "closed", "missing"]
    windows: list[WindowDeclaration] = Field(default_factory=list, max_length=24)
    close_time: StrictStr | None = Field(default=None, max_length=8)


class CalendarDeclaration(StrictModel):
    mode: Literal["weekday_approximation", "explicit"]
    coverage_assumption: StrictStr = Field(min_length=8, max_length=2000)
    start_time: StrictStr | None = Field(default=None, max_length=8)
    end_time: StrictStr | None = Field(default=None, max_length=8)
    bar_interval_seconds: StrictInt | None = Field(default=None, ge=1, le=86400)
    days: list[DayDeclaration] | None = Field(default=None, min_length=1, max_length=10000)

    @model_validator(mode="after")
    def separate_modes(self):
        if self.mode == "explicit":
            if self.days is None or any(v is not None for v in (self.start_time, self.end_time, self.bar_interval_seconds)):
                raise ValueError("Explicit mode requires days and no recurring-window fields.")
        elif self.days is not None or any(v is None for v in (self.start_time, self.end_time, self.bar_interval_seconds)):
            raise ValueError("Weekday mode requires start/end/cadence and no explicit days.")
        return self


class SetupRequest(StrictModel):
    source_backtest_id: StrictStr = Field(pattern=r"^[0-9a-f]{32}$")
    profile_id: StrictStr = Field(max_length=80)
    phase: Literal["evaluation", "funded"]
    observation_mode: Literal["trade_close", "bar_close"]
    quantity: StrictInt = Field(ge=1, le=10000)
    fee: StrictStr | None = Field(default=None, max_length=128)
    account_start_utc: StrictStr = Field(max_length=40)
    end_utc: StrictStr = Field(max_length=40)
    instrument_symbol: StrictStr = Field(min_length=1, max_length=80)
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")
    contract_limit_weight: StrictStr = Field(max_length=128)
    contract_limit_source_url: StrictStr = Field(max_length=2000)
    instrument_basis: StrictStr = Field(min_length=8, max_length=2000)
    calendar: CalendarDeclaration


class ProfileFeesRequest(StrictModel):
    attempt_fee: StrictStr | None = Field(default=None, max_length=128)
    activation_fee: StrictStr | None = Field(default=None, max_length=128)


def utc(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value):
        raise ValueError("UTC timestamps must use YYYY-MM-DDTHH:MM:SSZ.")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def clock(value):
    if not re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", value):
        raise ValueError("Local times must use HH:MM or HH:MM:SS.")
    return time.fromisoformat(value)


def decimal(value):
    if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value):
        raise ValueError("Money and contract weights must be exact decimal strings.")
    result = Decimal(value)
    if not result.is_finite() or abs(result) > Decimal("1e12") or result.as_tuple().exponent < -18:
        raise ValueError("Decimal inputs support magnitude at most 1e12 and at most 18 fractional places.")
    return result


def timezone_version():
    for directory in TZPATH:
        source = Path(directory) / "America" / "New_York"
        if source.is_file():
            return "America/New_York sha256:" + sha256(source.read_bytes()).hexdigest()
    from importlib.metadata import version
    return "tzdata " + version("tzdata")


def source_dates(record, policy):
    selection = record["run_metadata"]["selection"]
    zone = ZoneInfo(policy.timezone)
    labels = []
    for key in ("start_utc", "end_utc"):
        stamp = utc(selection[key]).astimezone(zone)
        labels.append(stamp.date() + timedelta(days=stamp.time() >= policy.open_time))
    if not 0 <= (labels[1] - labels[0]).days < 10000:
        raise ValueError("Source calendars support at most 10,000 consecutive dates.")
    return labels


def build_calendar(declaration, record, policy):
    first, last = source_dates(record, policy)
    if declaration.mode == "explicit":
        days = tuple(CalendarDay(date.fromisoformat(day.trading_date), day.status,
                                 tuple(DataWindow(utc(w.first_utc), utc(w.last_utc), w.bar_interval_seconds) for w in day.windows),
                                 clock(day.close_time) if day.close_time else None) for day in declaration.days)
        if days[0].trading_date != first or days[-1].trading_date != last:
            raise ValueError(f"Declare every source session date from {first} through {last}, including closed dates.")
    else:
        start, end = clock(declaration.start_time), clock(declaration.end_time)
        zone = ZoneInfo(policy.timezone)
        days = []
        for delta in range((last - first).days + 1):
            day = first + timedelta(days=delta)
            if day.weekday() >= 5:
                days.append(CalendarDay(day, "closed"))
            else:
                stamps = [local_utc(day - timedelta(days=t >= policy.open_time), t, zone) for t in (start, end)]
                days.append(CalendarDay(day, "covered", (DataWindow(*stamps, declaration.bar_interval_seconds),)))
        days = tuple(days)
    return SessionCalendar("user-declared-source-calendar", policy, timezone_version(), declaration.mode,
                           declaration.coverage_assumption, days)


def display(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: display(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [display(item) for item in value]
    return value


def profile_view(resolved):
    return dict(snapshot=resolved.to_dict(), display=display(asdict(resolved.profile)))


def require_source(request, run_id):
    try:
        record = catalog_record(request.app.state.runs, run_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if record is None:
        raise HTTPException(404, "Completed backtest not found.")
    if record.get("status") != "complete":
        raise HTTPException(422, "Only completed backtests can be configured.")
    return record


def configured_profile(profile_id, store):
    profile = get_profile(profile_id)
    fees = store.get_profile_fees(profile_id)
    return replace(profile, fee_defaults=fees) if fees is not None else profile


@router.get("/profiles")
def profiles(request: Request):
    return [profile_view(resolve_profile(configured_profile(profile_id, request.app.state.prop_runs)))
            for profile_id in PROFILE_IDS]


@router.put("/profiles/{profile_id}/fees")
def update_profile_fees(profile_id: str, body: ProfileFeesRequest, request: Request):
    try:
        profile = get_profile(profile_id)
        fees = ProfileFees(profile.currency, datetime.now(timezone.utc).date(),
                           None if body.attempt_fee is None else decimal(body.attempt_fee),
                           None if body.activation_fee is None else decimal(body.activation_fee))
        resolved = resolve_profile(replace(profile, fee_defaults=fees))
        request.app.state.prop_runs.save_profile_fees(profile_id, fees)
        return profile_view(resolved)
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/sources/{run_id}")
def source_context(run_id: UUID, request: Request):
    record = require_source(request, run_id.hex)
    return context_for(record, get_profile().session, request.app.state.prop_runs)


def context_for(record, policy, store):
    try:
        first, last = source_dates(record, policy)
        calendar = SessionCalendar("context", policy, timezone_version(), "explicit", "Date bounds only; coverage not established.",
                                   tuple(CalendarDay(first + timedelta(days=i), "missing") for i in range((last - first).days + 1)))
        return dict(source=record, first_session_date=first.isoformat(), last_session_date=last.isoformat(),
                    account_start_utc=calendar.bounds(calendar.days[0])[0].isoformat().replace("+00:00", "Z"),
                    end_utc=calendar.bounds(calendar.days[-1])[2].isoformat().replace("+00:00", "Z"),
                    setups=store.list_setups(record["id"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"This saved backtest lacks supported source metadata: {exc}") from None


@router.post("/setups", status_code=201)
def save_setup(body: SetupRequest, request: Request):
    record = require_source(request, body.source_backtest_id)
    try:
        profile = configured_profile(body.profile_id, request.app.state.prop_runs)
        calendar = build_calendar(body.calendar, record, profile.session)
        settings = record["execution_settings"]
        instrument = InstrumentDeclaration(body.instrument_symbol, body.currency, Decimal(settings["tick_size"]),
                                           Decimal(settings["point_value"]), decimal(body.contract_limit_weight),
                                           body.contract_limit_source_url, body.instrument_basis)
        fee_name = "attempt_fee" if body.phase == "evaluation" else "activation_fee"
        amount = decimal(body.fee) if body.fee is not None else (
            getattr(profile.fee_defaults, fee_name) if profile.fee_defaults is not None else None)
        if amount is None:
            raise ValueError("Set the selected phase fee in the account profile once, or supply an explicit simulation override (including zero).")
        fees = UserFees(body.currency, **{fee_name: amount}, origin="profile_default" if body.fee is None else "user_supplied")
        config = SimulationConfig(source_backtest_id=body.source_backtest_id, phase=body.phase, analysis="historical",
                                  observation_mode=body.observation_mode, account_start_utc=utc(body.account_start_utc), end_utc=utc(body.end_utc),
                                  instrument=body.instrument_symbol, currency=body.currency,
                                  contract_limit_weight=instrument.contract_limit_weight,
                                  contract_limit_source_url=instrument.contract_limit_source_url, quantity=body.quantity,
                                  calendar_id=calendar.id, calendar_sha256=calendar.sha256, calendar_mode=calendar.mode,
                                  timezone_data_version=calendar.timezone_data_version, coverage_assumption=calendar.coverage_assumption, fees=fees)
        return request.app.state.prop_runs.save_setup(resolve_simulation(config, profile), calendar, instrument, body.model_dump(mode="json"))
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/setups")
def list_setups(request: Request, source_backtest_id: UUID, offset: int = Query(0, ge=0, le=1000000000), limit: int = Query(25, ge=1, le=100)):
    return request.app.state.prop_runs.list_setups(source_backtest_id.hex, offset, limit)


@router.get("/setups/{setup_id}")
def saved_setup(setup_id: UUID, request: Request):
    try:
        record = request.app.state.prop_runs.get_setup(setup_id.hex)
    except ValueError as exc:
        raise HTTPException(409, f"Saved setup failed integrity checks: {exc}") from None
    if record is None:
        raise HTTPException(404, "Saved prop setup not found.")
    from .prop.rules import ResolvedSimulation
    resolved = ResolvedSimulation.from_dict(record["resolved"])
    context = context_for(require_source(request, record["source_backtest_id"]), resolved.rules.profile.session,
                          request.app.state.prop_runs)
    return JSONResponse({**record, "profile_view": profile_view(resolved.rules), "source_context": context}, headers={"Cache-Control": "no-store"})


@router.post("/setups/{setup_id}/check", status_code=201)
def check_source(setup_id: UUID, request: Request):
    try:
        return request.app.state.prop_runs.check_source(setup_id.hex, request.app.state.runs)
    except KeyError:
        raise HTTPException(404, "Saved prop setup not found.") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/checks/{check_id}/{kind}")
def preview(check_id: UUID, kind: Literal["sessions", "observations"], request: Request,
            offset: int = Query(0, ge=0, le=1000000000), limit: int = Query(50, ge=1, le=100),
            mode: Literal["bar_close", "trade_close"] = "bar_close", trading_date: date | None = None):
    try:
        return request.app.state.prop_runs.page(check_id.hex, kind, offset, limit, mode, trading_date.isoformat() if trading_date else None)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/setups/{setup_id}/exports/{filename}")
def setup_export(setup_id: UUID, filename: str, request: Request):
    if filename not in {"setup.json", "profile.json", "simulation.json", "calendar.json"}:
        raise HTTPException(404, "Export not found.")
    saved_setup(setup_id, request)
    return FileResponse(request.app.state.prop_runs.root / setup_id.hex / filename, media_type="application/json", filename=filename)


@router.get("/checks/{check_id}/exports/{filename}")
def check_export(check_id: UUID, filename: str, request: Request):
    record = request.app.state.prop_runs.get_check(check_id.hex)
    if record is None or filename not in {"check.json", "source.json", "sessions.csv", "observations.csv"}:
        raise HTTPException(404, "Export not found.")
    path = request.app.state.prop_runs.root / check_id.hex / filename
    if not path.is_file():
        raise HTTPException(404, "This check has no such output.")
    return FileResponse(path, media_type="text/csv" if filename.endswith(".csv") else "application/json", filename=filename)


@router.post("/setups/{setup_id}/run", status_code=201)
def run_evaluation(setup_id: UUID, request: Request):
    try:
        return request.app.state.prop_runs.execute(setup_id.hex, request.app.state.runs)
    except KeyError:
        raise HTTPException(404, "Saved setup not found.") from None
    except (SimulationError, InputError) as exc:
        raise HTTPException(422, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/results")
def results(request: Request, setup_id: UUID, offset: int = Query(0, ge=0, le=1000000000), limit: int = Query(25, ge=1, le=100)):
    return request.app.state.prop_runs.list_results(setup_id.hex, offset, limit)


@router.get("/results/{result_id}")
def result_detail(result_id: UUID, request: Request):
    result = request.app.state.prop_runs.get_result(result_id.hex)
    if result is None:
        raise HTTPException(404, "Saved simulation result not found.")
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.get("/results/{result_id}/events")
def account_events(result_id: UUID, request: Request, offset: int = Query(0, ge=0, le=1000000000), limit: int = Query(50, ge=1, le=100)):
    try:
        return request.app.state.prop_runs.events(result_id.hex, offset, limit)
    except KeyError:
        raise HTTPException(404, "Saved simulation result not found.") from None


@router.get("/results/{result_id}/chart")
def account_chart(result_id: UUID, request: Request, max_points: int = Query(500, ge=20, le=2000)):
    try:
        return request.app.state.prop_runs.chart(result_id.hex, max_points)
    except KeyError:
        raise HTTPException(404, "Saved simulation result not found.") from None


@router.get("/results/{result_id}/exports/{filename}")
def result_export(result_id: UUID, filename: str, request: Request):
    result_detail(result_id, request)
    if filename not in {"report.json", "events.csv", "source.json", "simulation.json", "profile.json", "calendar.json"}:
        raise HTTPException(404, "Result export not found.")
    return FileResponse(request.app.state.prop_runs.root / result_id.hex / filename,
                        media_type="text/csv" if filename.endswith(".csv") else "application/json", filename=filename)
