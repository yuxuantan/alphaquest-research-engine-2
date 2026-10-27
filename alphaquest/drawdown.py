"""Constant-memory drawdown statistics for complete trade-close equity."""

import csv
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN
import json
import gzip

from .decimal_math import multiply, subtract


class Drawdown:
    def __init__(self, initial_equity: Decimal, start: datetime):
        self.start = self.peak_time = self.last_time = start
        self.peak = initial_equity
        self.amount = Decimal(0)
        self.pct_loss = Decimal(0)
        self.pct_peak = initial_equity
        self.duration_us = 0
        self.underwater = False

    def _duration(self, timestamp):
        elapsed = timestamp - self.peak_time
        microseconds = (elapsed.days * 86400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds
        self.duration_us = max(self.duration_us, microseconds)

    def observe(self, timestamp: datetime, equity: Decimal):
        if timestamp < self.last_time:
            raise ValueError("Drawdown timestamps must be chronological.")
        self.last_time = timestamp
        if self.underwater:
            self._duration(timestamp)  # Includes the recovery observation.
        if equity >= self.peak:
            self.peak, self.peak_time = equity, timestamp
            self.underwater = False
        else:
            self.underwater = True
            self._duration(timestamp)
            loss = subtract(self.peak, equity)
            self.amount = max(self.amount, loss)
            # Compare exact ratios before rounding the final percentage.
            if multiply(loss, self.pct_peak) > multiply(self.pct_loss, self.peak):
                self.pct_loss, self.pct_peak = loss, self.peak

    def finish(self, end: datetime) -> dict:
        if end < self.last_time:
            raise ValueError("Drawdown period ends before its last equity observation.")
        if self.underwater:
            self._duration(end)
        whole, fraction = divmod(self.duration_us, 1_000_000)
        seconds = Decimal(f"{whole}.{fraction:06d}" if fraction else whole)
        pct = Context(prec=28, rounding=ROUND_HALF_EVEN).divide(
            multiply(self.pct_loss, Decimal(100)), self.pct_peak)
        return {"max_drawdown_amount": self.amount, "max_drawdown_pct": pct,
                "max_drawdown_duration_seconds": seconds}


def saved_period(path):
    """Read legacy reporter output one equity object per line, without arrays.

    Needed only once for old catalogue entries lacking explicit run bounds.
    Original report artifacts are preserved.
    """
    start = end = None
    opener = gzip.open if path.suffix == ".gz" else lambda path, mode, **kwargs: path.open(mode, **kwargs)
    with opener(path, "rt", encoding="utf-8") as source:
        for line in source:
            if line.startswith('"equity": ['):
                break  # Initial balance has a null timestamp; use first bar.
        else:
            raise ValueError("Saved report has no equity period.")
        for line in source:
            last = line.rstrip().endswith("]")
            point = json.loads(line.rstrip().removesuffix("]" if last else ","))
            timestamp = datetime.fromisoformat(point["timestamp_utc"])
            start = start or timestamp
            end = timestamp
            if last:
                break
        else:
            raise ValueError("Saved equity period is incomplete.")
    if start is None:
        raise ValueError("Saved report has no observed bars.")
    return start, end


def saved_drawdown(folder, record):
    """Derive legacy metrics from every saved trade-close row, never samples."""
    if "period_start_utc" in record and "period_end_utc" in record:
        start, end = (datetime.fromisoformat(record[key]) for key in ("period_start_utc", "period_end_utc"))
    else:
        start, end = saved_period(folder / record.get("artifacts", {}).get("report", "report.json"))
    tracker = Drawdown(Decimal(record["summary"]["initial_capital"]), start)
    count = 0
    with (folder / "equity.csv").open(encoding="utf-8", newline="") as source:
        for ordinal, point in enumerate(csv.DictReader(source)):
            if int(point["trade_number"]) != ordinal:
                raise ValueError("Saved trade-close equity is not contiguous.")
            if ordinal:
                tracker.observe(datetime.fromisoformat(point["exit_time_utc"]), Decimal(point["equity"]))
            elif Decimal(point["equity"]) != tracker.peak:
                raise ValueError("Saved starting equity does not match the run.")
            count += 1
    if count != record["summary"]["trades_taken"] + 1:
        raise ValueError("Saved trade-close equity count does not match the run.")
    return {"summary": {**record["summary"], **tracker.finish(end)},
            "period_start_utc": start, "period_end_utc": end}
