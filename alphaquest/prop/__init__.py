"""Prop configuration and saved-source adaptation; no account simulator yet."""

from .rules import (
    DEFAULT_PROFILE_ID, ResolvedProfile, ResolvedSimulation, get_profile,
    resolve_profile, resolve_simulation,
)
from .types import SimulationConfig
from .calendar import CalendarDay, DataWindow, SessionCalendar
from .sessions import InputError, InstrumentDeclaration, SourceSnapshot, prepare_backtest

__all__ = [
    "DEFAULT_PROFILE_ID", "ResolvedProfile", "ResolvedSimulation", "SimulationConfig",
    "get_profile", "resolve_profile", "resolve_simulation",
    "CalendarDay", "DataWindow", "SessionCalendar", "InputError", "InstrumentDeclaration",
    "SourceSnapshot", "prepare_backtest",
]
