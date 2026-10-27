"""Job-owned, bounded-memory replay streams. Never load user-supplied pickle files.

Only the coordinator writes these private temporary files. Workers open them
read-only; chunks retain Decimal values, UTC timestamps and original CSV fields.
They are deleted with the job workspace, rather than becoming another dataset.
"""

from contextlib import contextmanager
from dataclasses import dataclass, replace
from itertools import islice
from pathlib import Path
import hashlib
import pickle

from .backtest_data import SelectedBars

CHUNK_SIZE = 2048


def write_stream(path, values, progress=lambda count: None):
    count = 0
    values = iter(values)
    with Path(path).open("xb") as stream:
        while chunk := tuple(islice(values, CHUNK_SIZE)):
            pickle.dump(chunk, stream, protocol=5)
            count += len(chunk)
            progress(count)
    return count


def read_stream(path):
    with Path(path).open("rb") as stream:
        while True:
            try:
                chunk = pickle.load(stream)
            except EOFError:
                return
            yield from chunk


@dataclass(frozen=True)
class PreparedData:
    path: Path
    metadata: dict
    cache_key: str | None = None
    cache_hit: bool = False

    @contextmanager
    def selected(self):
        bars = read_stream(self.path)
        try:
            yield SelectedBars(bars, dict(self.metadata))
        finally:
            bars.close()


def prepare_data(source, dataset_id, dates, path, progress=lambda *args: None, *, cache=None):
    # Full original-source hash/schema/row validation runs before publication,
    # even when only a date slice is used. No second CSV parse for a slice.
    from .backtest_data import DateRange, DatasetReadError, read_bars
    from zoneinfo import ZoneInfo,TZPATH
    dataset = source.get(dataset_id)
    if dataset is None:raise DatasetReadError(f"Dataset {dataset_id!r} was not found.")
    dates = dates or DateRange()
    from .optimization_cache import digest,engine_identity
    key=None
    metadata = {"from_date": dates.from_date.isoformat() if dates.from_date else None,
                "to_date": dates.to_date.isoformat() if dates.to_date else None,
                "source_timezone": dataset.get("source_timezone"), "warmup": "none"}
    with read_bars(source, dataset_id) as bars:
        zone = ZoneInfo(dataset["source_timezone"])
        # Reuse the same verified snapshot for a miss; never hash/copy the
        # original twice just to discover that no derived stream exists.
        if cache:
            zone_file=next((Path(root)/dataset['source_timezone'] for root in TZPATH if (Path(root)/dataset['source_timezone']).is_file()),None)
            zone_hash=hashlib.sha256(zone_file.read_bytes()).hexdigest() if zone_file else 'package-tzdata'
            key=digest(dict(kind='bars-v1',dataset=dataset,dates=dates,timezone=zone_hash,engine=engine_identity()))
            cached=cache.restore(key,path)
            if cached is not None:
                progress('preparing_data',dataset['row_count'],dataset['row_count'])
                return PreparedData(Path(path),cached,key,True)
        def selected():
            count = 0
            for bar in bars:
                if bar.bar_number % CHUNK_SIZE == 0:
                    progress("preparing_data", bar.bar_number, dataset["row_count"])
                if dates.active and not dates.contains(bar.timestamp_utc, zone):
                    continue
                count += 1
                if count == 1:
                    metadata.update(start_utc=bar.timestamp_utc.isoformat().replace("+00:00", "Z"),
                                    first_source_bar_number=bar.bar_number)
                metadata.update(end_utc=bar.timestamp_utc.isoformat().replace("+00:00", "Z"),
                                last_source_bar_number=bar.bar_number)
                yield replace(bar, bar_number=count) if bar.bar_number != count else bar
        count = write_stream(path, selected())
    if not count:
        raise DatasetReadError("No bars fall within the selected date range in the dataset's source timezone.")
    metadata["row_count"] = count
    progress("preparing_data", dataset["row_count"], dataset["row_count"])
    if cache:cache.save(key,path,metadata)
    return PreparedData(Path(path), metadata,key)
