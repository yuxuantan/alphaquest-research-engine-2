"""Bounded previews of saved trade-close equity with an exact peak annotation."""

import csv
from decimal import Decimal

from .reporting import EQUITY_FIELDS


def equity_records(path):
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != EQUITY_FIELDS:
            raise ValueError("Saved equity CSV has an unsupported schema.")
        for point in reader:
            if None in point or any(value is None for value in point.values()):
                raise ValueError("Saved equity CSV has an incomplete row.")
            point["trade_number"] = int(point["trade_number"])
            point["exit_time_utc"] = point["exit_time_utc"] or None
            yield point


def equity_preview(path, total, limit):
    """Keep endpoints and chronological min/max per equal trade-count bucket."""
    points = []
    buckets = max(1, (limit - 2) // 2)
    low = high = None
    current = None
    seen = 0
    peak = None

    def flush():
        if low is not None:
            points.extend(sorted({low["trade_number"]: low, high["trade_number"]: high}.values(),
                                 key=lambda point: point["trade_number"]))

    for point in equity_records(path):
        if point["trade_number"] != seen:
            raise ValueError("Saved equity trade numbers are not contiguous.")
        seen += 1
        if peak is None or Decimal(point["equity"]) > Decimal(peak["equity"]):
            peak = point
        if total <= limit or point["trade_number"] in (0, total - 1):
            if point["trade_number"] == total - 1:
                flush()
                low = high = None
            points.append(point)
            continue
        bucket = (point["trade_number"] - 1) * buckets // (total - 2)
        if bucket != current:
            flush()
            low = high = point
            current = bucket
        if Decimal(point["equity"]) < Decimal(low["equity"]):
            low = point
        if Decimal(point["equity"]) > Decimal(high["equity"]):
            high = point
    if seen != total:
        raise ValueError("Saved equity count does not match the completed report.")
    return {"items": points, "peak": peak, "total": total, "limit": limit, "sampled": total > limit,
            "method": "trade_bucket_min_max", "currency": "CU (account currency unspecified)",
            "meaning": "Initial equity and equity after each completed trade, including all trading costs; no unrealized P&L."}
