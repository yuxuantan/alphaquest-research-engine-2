"""Chronological research windows over observed CME session dates.

This module plans windows; it does not fit a model, rank a strategy, inspect
prices or certify that a supplied purge duration covers every outcome horizon.
Each replay starts cold and must finish flat. A later fold may train on an
earlier fold's test sessions, once those sessions are in its past.

``purge_sessions`` and ``embargo_sessions`` are consecutive exclusion buffers
between the retained training window and its evaluation window. Both count
observed sessions, not calendar days. Purge protects a declared outcome horizon;
embargo adds a declared waiting interval. Neither is a post-test exclusion or a
substitute for checking event timestamps when importing precomputed outcomes.
"""

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .backtest_data import DateRange, DatasetReadError, read_bars
from .session_calendar import session_date


SESSION_CONVENTION = "cme_chicago_1700_v1"


class FoldSettings(BaseModel):
    """Predeclared window lengths, all measured in observed whole sessions."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    outer_train_sessions: int = Field(default=60, ge=1, le=100_000)
    outer_test_sessions: int = Field(default=20, ge=1, le=100_000)
    inner_train_sessions: int = Field(default=20, ge=1, le=100_000)
    inner_validation_sessions: int = Field(default=10, ge=1, le=100_000)
    mode: Literal["rolling", "expanding"] = "rolling"
    purge_sessions: int = Field(default=1, ge=0, le=100_000)
    embargo_sessions: int = Field(default=0, ge=0, le=100_000)
    minimum_inner_folds: int = Field(default=2, ge=1, le=10_000)
    minimum_outer_folds: int = Field(default=2, ge=1, le=10_000)

    @model_validator(mode="after")
    def inner_folds_fit(self):
        needed = (self.inner_train_sessions + self.purge_sessions
                  + self.embargo_sessions
                  + self.minimum_inner_folds * self.inner_validation_sessions)
        if needed > self.outer_train_sessions:
            raise ValueError(
                "The first outer training window cannot contain the declared "
                f"minimum inner folds: need {needed} observed sessions, "
                f"have {self.outer_train_sessions}."
            )
        return self


@dataclass(frozen=True)
class SessionDateRange(DateRange):
    """DateRange-compatible inclusive session labels, never source-local dates.

    ``convention`` is an instance field so dataclass serialization and the
    existing cache's string serialization cannot alias ordinary DateRange.
    Call ``to_dict`` when saving a JSON research declaration. The zone argument
    in ``contains`` is accepted for existing readers and intentionally ignored:
    session labels always use Chicago with its timezone transitions.
    """

    convention: str = SESSION_CONVENTION

    def __post_init__(self):
        super().__post_init__()
        if self.convention != SESSION_CONVENTION:
            raise ValueError(f"Unsupported session convention: {self.convention!r}.")

    def contains(self, timestamp, zone=None):
        if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
            raise ValueError("Session selection requires timezone-aware timestamps.")
        day = session_date(timestamp)
        return ((self.from_date is None or day >= self.from_date)
                and (self.to_date is None or day <= self.to_date))

    def to_dict(self):
        return dict(
            from_date=self.from_date.isoformat() if self.from_date else None,
            to_date=self.to_date.isoformat() if self.to_date else None,
            convention=self.convention,
        )


def _validated_dates(session_dates):
    if type(session_dates) is not list or not session_dates:
        raise ValueError("Supply a nonempty list of observed session dates.")
    previous = None
    for value in session_dates:
        if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Session dates must use YYYY-MM-DD strings.")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid session date: {value!r}.") from exc
        if previous is not None and value <= previous:
            raise ValueError("Session dates must be unique and strictly increasing; no sorting or deduplication is performed.")
        previous = value


def _window(days):
    return dict(first_session=days[0], last_session=days[-1], sessions=list(days))


def _splits(days, training, evaluation, settings):
    gap = settings.purge_sessions + settings.embargo_sessions
    evaluation_start = training + gap
    index = 1
    while evaluation_start + evaluation <= len(days):
        training_end = evaluation_start - gap
        training_start = 0 if settings.mode == "expanding" else training_end - training
        purge_end = training_end + settings.purge_sessions
        yield dict(
            index=index,
            train=_window(days[training_start:training_end]),
            evaluation=_window(days[evaluation_start:evaluation_start + evaluation]),
            excluded=dict(purge_sessions=list(days[training_end:purge_end]),
                          embargo_sessions=list(days[purge_end:evaluation_start])),
            information_cutoff_session=days[training_end - 1],
            convention=SESSION_CONVENTION,
            boundary_policy="cold_start_finish_flat",
        )
        evaluation_start += evaluation
        index += 1


def generate_folds(session_dates: list[str], settings: FoldSettings) -> list[dict]:
    """Plan only complete folds; return stable earlier folds when data is appended.

    No price or outcome input is accepted. Inner folds use the *retained* outer
    training sessions only. A short trailing evaluation window is not emitted;
    callers can derive that unused tail from the last test and input inventory.
    Insufficient history raises instead of silently weakening minimums.
    """
    _validated_dates(session_dates)
    if not isinstance(settings, FoldSettings):
        raise TypeError("settings must be a validated FoldSettings declaration.")
    required = (settings.outer_train_sessions + settings.purge_sessions
                + settings.embargo_sessions
                + settings.minimum_outer_folds * settings.outer_test_sessions)
    if len(session_dates) < required:
        raise ValueError(
            f"Insufficient session history: need at least {required} observed "
            f"sessions for {settings.minimum_outer_folds} complete outer folds; "
            f"have {len(session_dates)}."
        )
    folds = []
    for fold in _splits(session_dates, settings.outer_train_sessions,
                        settings.outer_test_sessions, settings):
        fold["test"] = fold.pop("evaluation")
        fold["inner"] = []
        for inner in _splits(fold["train"]["sessions"], settings.inner_train_sessions,
                             settings.inner_validation_sessions, settings):
            inner["validation"] = inner.pop("evaluation")
            fold["inner"].append(inner)
        folds.append(fold)
    return folds


def inventory_sessions(source, dataset_id: str, *, minimum_sessions: int = 2) -> dict:
    """Read validated saved bars once and return dates/counts, never outcomes.

    This inventory records observed sessions, including sessions with bars but
    no strategy trades. It does not invent absent sessions or establish calendar
    completeness. The shared reader validates all original bytes/rows; only
    timestamps and counts are retained here. No instrument-calendar entitlement
    or reviewed exchange-hours claim follows from this labeling convention.
    """
    if type(minimum_sessions) is not int or minimum_sessions < 1:
        raise ValueError("minimum_sessions must be a positive integer.")
    dataset = source.get(dataset_id)
    if dataset is None:
        raise DatasetReadError(f"Dataset {dataset_id!r} was not found.")
    counts, bounds = {}, {}
    previous = None
    with read_bars(source, dataset_id) as bars:
        for bar in bars:
            stamp = bar.timestamp_utc
            if stamp.utcoffset() is None or previous is not None and stamp <= previous:
                raise ValueError("Source timestamps must be aware and strictly increasing.")
            previous = stamp
            day = session_date(stamp).isoformat()
            counts[day] = counts.get(day, 0) + 1
            instant = stamp.isoformat().replace("+00:00", "Z")
            bounds.setdefault(day, dict(first_utc=instant, last_utc=instant))
            bounds[day]["last_utc"] = instant
    sessions = list(counts)
    _validated_dates(sessions)
    if len(sessions) < minimum_sessions:
        raise ValueError(f"Need at least {minimum_sessions} observed sessions; have {len(sessions)}.")
    return dict(
        convention=SESSION_CONVENTION,
        source=dict(dataset_id=dataset_id, sha256=dataset["sha256"],
                    source_timezone=dataset["source_timezone"], row_count=dataset["row_count"]),
        sessions=sessions,
        counts=counts,
        bounds=bounds,
        coverage="observed sessions only; missing market sessions are not inferred",
    )
