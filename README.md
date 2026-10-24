# AlphaQuest Research Engine 02

A small local research portal. This first increment implements the web interface and CSV dataset management. Strategy execution, slippage, commissions, trades, and performance reports belong to the next component, after review.

## Run

Requires Python 3.12 or newer. From this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]' -c requirements.lock
python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8000 --reload
```

Open **http://127.0.0.1:8000**. Choose a CSV (or download the example), set the dataset name and source timezone, click **Validate CSV**, inspect the preview, then **Save dataset**. Saved datasets can be reopened and downloaded from the library. Use **Delete** in a dataset row or its details to remove its saved CSV and metadata after confirmation. Deletion is permanent; the original file on your computer is unaffected and can be uploaded again. Reloading the page or restarting the server retains the library.

This is a single-user application bound to your own computer, without a login or public hosting setup.

## CSV contract

UTF-8, optionally with a BOM; comma-separated with these exact headers, capitalization, and column order:

```csv
Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol
05/21/2017,18:01,5652.75,5654.50,5651.25,5654.00,182,83,99
05/21/2017,18:02,5654.00,5655.25,5653.50,5654.75,210,120,90
```

- At least one data row; nine non-empty fields per row; maximum file size 1 GB (1,000,000,000 bytes).
- `Date` uses `MM/DD/YYYY` and `Time` uses 24-hour `HH:MM`. Dates are always month first; other date/time formats are rejected rather than guessed.
- Choose the IANA source timezone of those columns, such as `UTC`, `America/New_York`, or `Asia/Singapore`. Date and Time are combined and converted to UTC for validation and metadata. Ambiguous/nonexistent local times at daylight-saving changes are rejected; export in an unambiguous timezone such as UTC to resolve them.
- Timestamps must be unique and strictly increasing **after conversion to UTC**.
- Prices and volumes must be finite decimal numbers. Require `Low ≤ Open/Close ≤ High` and non-negative `Volume`, `UpVol`, and `DownVol`. Zero and negative prices are allowed when OHLC is consistent; fractional volume is allowed. `UpVol` and `DownVol` are preserved as supplied; no equality between their sum and `Volume` is assumed.
- Extra columns, missing values, malformed CSV, blank rows, NaN, and infinity are rejected. Leading/trailing whitespace in data cells is ignored for validation; headers must match exactly.
- No sorting, resampling, deduplication, or gap filling. Irregular spacing is reported. Regular spacing describes observed timestamp deltas; it does not establish a trading calendar or rule out missing bars.

Validation checks the complete file and shows up to 20 errors with CSV line/column information. The save endpoint independently revalidates the file, so bypassing the UI cannot save an invalid CSV. Previews preserve all nine source columns and decimal strings, with an additional computed `datetime (UTC)` column; downloads return the original bytes. Previously saved six-column datasets remain viewable and downloadable; new uploads must use the nine-column format above.

During validation and saving, the portal shows upload bytes, file scan progress, rows checked, database write progress, and elapsed time. Percentages describe the current stage. A save completes only after the database transaction commits. Progress snapshots for the latest 128 requests are held in server memory and reset on restart; they do not launch background jobs or automatically retry requests.

## Storage and metadata

`data/datasets.sqlite3` stores the original CSV in chunks and its metadata in one transaction. Uploads are staged in temporary files; validation and downloads stream through the data. Temporary uploads are removed after the request. Existing datasets saved as single blobs remain readable. The library is local to this checkout by default. Set `ALPHAQUEST_DATA_DIR` to an absolute directory to choose another location. Uploaded data, databases, virtual environments, and test artifacts are ignored by Git.

Metadata includes dataset ID, name, optional symbol, original filename, byte size, SHA-256, row count, UTC start/end, timestamp timezone, observed spacing, first eight rows, warnings, and save time. Duplicate CSV bytes with the same timezone interpretation are rejected; different interpretations of naive timestamps are separate datasets. Symbol is user supplied, not inferred from prices or filenames. This component does not determine venue, trading calendar, price adjustment, or whether timestamps label bar opens or closes.

## Backtest dataset reader

The backtest reader and strategy interface are available for review. The reader resolves an existing saved dataset ID, snapshots its CSV to a temporary file using bounded chunks, checks the saved byte count/hash, closes the database connection, and then yields bars incrementally. Full iteration verifies the saved row count. It reuses the upload parser and fails at the first invalid row rather than skipping or sorting data.

Print three bars from a small fixture saved into an isolated temporary database:

```bash
.venv/bin/python -m alphaquest.backtest_data --demo --limit 3
```

The demo uses the `gap_deadline` fixture's saved `America/New_York` timezone: source `01/05/2026 14:00` becomes `2026-01-05T19:00:00Z`. It removes its temporary database on exit and does not add anything to the portal library. Print from an existing library instead (IDs are available through the existing `/api/datasets` endpoint):

```bash
.venv/bin/python -m alphaquest.backtest_data --database data/datasets.sqlite3 --dataset-id YOUR_DATASET_ID --limit 5
```

Python callers use the iterator within its resource context:

```python
from pathlib import Path
from alphaquest.datasets import DatasetStore
from alphaquest.backtest_data import read_bars

store = DatasetStore(Path("data/datasets.sqlite3"))
with read_bars(store, dataset_id) as bars:
    for bar in bars:
        print(bar.timestamp_utc, bar.close)
```

Each immutable `Bar` carries its 1-based data-record number, UTC close timestamp, original Date/Time strings, seven numeric `Decimal` fields, and `source_fields`, an immutable tuple of all nine decoded CSV cell strings including whitespace and original numeric spelling. Original CSV bytes and saved metadata are unchanged. A partial consumer parses only requested rows; a future complete backtest must exhaust the iterator before finishing. Legacy six-column schemas are rejected with an explicit error. A legacy single-blob record with the supported nine-column schema can still be read in chunks.

`alphaquest/strategy.py` defines immutable `Position`, `ExecutionConfig`, `EntryIntent`, and `CloseIntent` values and the `Strategy` protocol: `on_bar(bar, position)` returns an entry/close intent or `None`; `on_finish(last_bar, position)` returns a close intent or `None`. Flat is `position=None`. Callbacks receive no dataset handle or future-bar collection. Execution settings take explicit finite `Decimal` values, and integer quantities/ticks reject booleans and implicit coercion. There is no execution loop, sample strategy, monetary calculation, or new portal/API feature in this increment. See [the backtest contract](docs/backtest_contract.md).

## Verify

```bash
python -m pytest
```

Tests cover invalid datasets, timezone/DST boundaries, UTC ordering, gap reporting, exact-byte persistence across store restarts, concurrent duplicate saves, API validation enforcement, upload size limits, and the validate/save/download workflow.

## Structure

- `alphaquest/datasets.py`: CSV validation and SQLite storage.
- `alphaquest/backtest_data.py`: saved-dataset snapshot reader and normalized-bar review command.
- `alphaquest/strategy.py`: immutable strategy inputs, intents, execution settings, and callback protocol.
- `alphaquest/app.py`: API and local web server.
- `alphaquest/web/`: HTML, CSS, JavaScript, and example CSV; no frontend build step or CDN.
- `tests/`: dataset and API checks using isolated temporary databases.

The original [AlphaQuest repository](https://github.com/yuxuantan/alphaquest-research-engine) was consulted for context. This increment uses a small new implementation, with no imported governance, campaign, or backtest framework.
