"""Long entries after consecutive green closes, followed by a timed full exit."""

from dataclasses import dataclass, field
from datetime import timedelta

from ..strategy import Bar, CloseIntent, EntryIntent, Position


STRATEGY_ID = "consecutive_green_hold"
DESCRIPTION = (
    "Enter long at the close of N adjacent observed green bars while flat. "
    "Hold for elapsed UTC minutes, exit at the first available close at or after "
    "the deadline, and close remaining exposure at end of data. No pyramiding."
)


@dataclass(frozen=True, slots=True)
class Parameters:
    """The strategy's only tunable parameters; each is a strict positive integer."""

    green_bar_count: int = field(default=3, metadata={
        "description": "Consecutive observed bars with Close > Open required while flat.",
    })
    hold_minutes: int = field(default=20, metadata={
        "description": "Elapsed UTC minutes from the actual entry time to the target exit.",
    })
    contracts: int = field(default=1, metadata={
        "description": "Fixed contract quantity requested for each long entry.",
    })

    def __post_init__(self):
        for name in ("green_bar_count", "hold_minutes", "contracts"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be an integer >= 1; booleans and coercion are not accepted.")


class ConsecutiveGreenHold:
    """One strategy instance per run; callbacks use only the current bar/position.

    Timestamps label bar closes under the reviewed same-close execution model.
    Gaps neither fabricate bars nor reset the flat-position green streak.
    """

    def __init__(self, parameters: Parameters | None = None):
        if parameters is not None and not isinstance(parameters, Parameters):
            raise TypeError("parameters must be a Parameters instance.")
        self.parameters = parameters if parameters is not None else Parameters()
        self._green_count = 0

    def on_bar(self, bar: Bar, position: Position | None) -> EntryIntent | CloseIntent | None:
        if position is not None:
            # Holding bars never contribute to a new entry, including the exit bar.
            self._green_count = 0
            deadline = position.entry_time_utc + timedelta(minutes=self.parameters.hold_minutes)
            if bar.timestamp_utc >= deadline:
                return CloseIntent(reason="hold_elapsed")
            return None

        self._green_count = self._green_count + 1 if bar.close > bar.open else 0
        if self._green_count == self.parameters.green_bar_count:
            self._green_count = 0
            return EntryIntent(
                contracts=self.parameters.contracts,
                reason="consecutive_green",
                exit_deadline_utc=bar.timestamp_utc + timedelta(minutes=self.parameters.hold_minutes),
            )
        return None

    def on_finish(self, last_bar: Bar, position: Position | None) -> CloseIntent | None:
        self._green_count = 0
        return CloseIntent(reason="end_of_data") if position is not None else None
