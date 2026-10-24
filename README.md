# AlphaQuest Research Engine 02

A small local research portal with CSV dataset management, a streaming backtest dataset reader, a strategy-agnostic execution engine, a consecutive-green-bars sample strategy, and JSON/CSV backtest reports. The Backtests screen configures runs and opens completed reports with exact metrics, a bounded trade-close equity chart, paginated trades, saved settings, and CSV downloads.

The Backtests selector also includes **Vwap pullback risk sizing**, a port of
the supplied MultiCharts PowerLanguage strategy, with ORB/VWAP latches, ADX
gates, pivot/pullback stops, risk sizing, optional shorts, next-bar market
orders, brackets, and EOD exits. See [the strategy guide](docs/strategies/vwap_pullback_risk_sizing.md)
for defaults, full-session one-minute data requirements, CLI use, and explicit
OHLC execution assumptions. The same-close descriptions below apply to the
original consecutive-green-bars sample; the VWAP strategy uses the execution
extension described in its guide. MultiCharts export parity remains unverified.

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

`alphaquest/strategy.py` defines immutable `Position`, `ExecutionConfig`, `EntryIntent`, and `CloseIntent` values and the `Strategy` protocol: `on_bar(bar, position)` returns an entry/close intent or `None`; `on_finish(last_bar, position)` returns a close intent or `None`. Flat is `position=None`. Callbacks receive no dataset handle or future-bar collection. Execution settings take explicit finite `Decimal` values, and integer quantities/ticks reject booleans and implicit coercion. See [the backtest contract](docs/backtest_contract.md).

## Backtest execution engine

`alphaquest.execution.execute(bars, strategy, config)` yields immutable `Trade` and `EquityPoint` events incrementally. It fills long entries and full closes at the observed Close with adverse slippage, charges commissions on both sides, and calculates cash and mark-to-market equity using exact Decimal monetary arithmetic. Quantity stays fixed for the life of each position. Entry time/price/quantity passed back to the strategy are actual simulated fills. No green-bar counting, holding period, sizing policy, or implicit liquidation sits in the engine.

Consume the execution stream within `read_bars`' context. Write each event to a chosen sink to keep result memory bounded:

```python
from alphaquest.execution import execute

with read_bars(store, dataset_id) as bars:
    for event in execute(bars, strategy, config):
        print(event)
```

Same-close execution and bar-close timestamps are explicit simulation assumptions. The stream starts with initial equity, then produces one equity point per bar. It retains one point until the next bar or EOF so the final point includes the strategy's `on_finish` close. An entry on the last bar may therefore close at the same timestamp, with both fills charged. A strategy that leaves exposure open raises an error; earlier emitted results remain provisional until the stream finishes successfully. Unsupported intents and non-chronological input are rejected.

`EntryIntent.exit_deadline_utc` is optional strategy-supplied trade metadata. The engine records it without scheduling an exit. Run the small saved-fixture review with predetermined **test-only** intents (no production strategy or portal changes):

```bash
.venv/bin/python tests/review_execution.py --output artifacts/execution_review.json
```

The command creates isolated temporary saved datasets, replays them through the existing reader, checks every trade field and equity point, and prints actual-versus-expected values. The JSON contains complete comparisons. The arithmetic fixture yields fills 100.25/101.75, gross P&L 30, commissions 4, net P&L 26, entry equity 9993, and final equity 10026. The final-bar-entry fixture yields net -14 and final equity 9986. The reviewed CSVs and expected results are unchanged.

## Consecutive-green-bars sample strategy

`alphaquest/strategies/consecutive_green_hold.py` contains strategy identity `consecutive_green_hold`, its description, all decisions, and exactly three tunable parameters. Defaults are `green_bar_count=3`, `hold_minutes=20`, and `contracts=1`; each requires an integer >= 1 and rejects booleans and implicit coercion. Instantiate a fresh strategy for each run:

```python
from alphaquest.strategies.consecutive_green_hold import ConsecutiveGreenHold, Parameters

strategy = ConsecutiveGreenHold(Parameters(green_bar_count=3, hold_minutes=20, contracts=1))
```

Pass it to the existing `execute` iterator. While flat, adjacent observed bars with `Close > Open` count toward entry; red bars and dojis reset the streak. Gaps preserve adjacency. While holding, bars do not count toward new entries and no pyramiding occurs. The strategy requests an exit at the first observed UTC close at or after actual entry time plus `hold_minutes`. The exit bar cannot start a new streak. `on_finish` closes remaining exposure with reason `end_of_data`, including an entry on the final bar. Dataset access, fills, costs, and financial arithmetic remain outside the strategy script.

Run the actual strategy against all nine reviewed fixtures:

```bash
.venv/bin/python tests/review_strategy.py --output artifacts/strategy_review.json
```

The command checks every expected trade field and equity point using the saved-dataset reader and unchanged execution engine. It prints every entry and exit with its reason, writes complete comparisons to JSON, and saves the table to `artifacts/strategy_review.md`. Expected trade decisions are used only for comparison after the strategy runs.

## Backtest reports

Portal runs can select inclusive **From date / To date** bounds in the dataset's
saved source timezone. Blank bounds use the available data. The strategy starts
fresh and ends at the last selected bar; the report saves the range and selected
bar count. CLI runs accept the same `--from-date` and `--to-date` options.

Before running, open the saved dataset in **Datasets**, set **Tick size** and **Monetary point value**, and save the instrument settings. New uploads can include both values. Existing datasets have no inferred defaults and require configuration before backtesting. These values must be positive finite decimals; point value is money per 1.0 price point per contract. Editing settings preserves the CSV, hash and other dataset metadata. Completed reports retain their original settings.

The Backtests screen pre-fills these defaults into editable run fields. Use **Reset to dataset defaults** to restore them; selecting another dataset loads its defaults. Run-specific edits never update the dataset. Reports record the captured defaults, actual execution values and any overrides.

Run the sample strategy on an existing saved dataset ID using its saved instrument defaults:

```bash
.venv/bin/python -m alphaquest.run_backtest \
  --database data/datasets.sqlite3 --dataset-id YOUR_DATASET_ID \
  --output artifacts/my-backtest \
  --green-bar-count 3 --hold-minutes 20 --contracts 2 \
  --initial-capital 10000 \
  --slippage-ticks 1 --commission-per-contract-per-side 1
```

For the synthetic arithmetic fixture, save tick size **0.25** and monetary point value **10** on the dataset first. These are not NQ or other real instrument specifications. Capital and costs remain per-run inputs. Tick size and point value default to the dataset; optional `--tick-size` and/or `--point-value` flags override them for this run only. The command uses the dataset's saved timezone and preserves the source CSV/metadata. `--output` must name a new directory. It writes:

- `report.json`: summary, reconciliation checks, full trade records, and the complete equity curve. It records resolved execution/strategy settings, dataset ID/hash/source timezone, strategy ID/source hash, and the bar-close/same-close assumptions.
- `trades.csv`: every field from the engine's completed trades, including reference/fill prices, both commissions, gross/net P&L, holding time, deadline, and reasons. Zero trades produces headers only.
- `equity.csv`: starting equity followed by one row per completed trade, with columns `trade_number,exit_time_utc,net_pnl,equity`. The starting row uses trade number 0, a blank exit timestamp, and zero trade P&L. Each subsequent row records that trade's net P&L and the engine's equity immediately after closing, with all costs included. Breakeven and end-of-data exits each get a row; zero trades produces only the starting row. The full bar-close equity curve remains in `report.json`.

JSON monetary values and financial CSV cells use exact Decimal strings with no display rounding. JSON timestamps use UTC ISO 8601; null timestamps/deadlines become blank CSV cells. Win rate uses **net** winning trades divided by all completed trades, including breakevens. Zero trades produces JSON `null` and the command displays **N/A**. Recurring percentages use 28 significant Decimal digits; integer win/loss/breakeven counts remain authoritative.

The strategy-agnostic reporter consumes engine events once. It preserves engine fills, costs, and equity, aggregates trade values with exact arithmetic, and verifies final equity against initial capital plus summed net P&L. It does not replay a strategy or recalculate fills, costs, or unrealized P&L. JSON arrays and CSV rows stream through disk-backed staging files, so memory does not grow with result length. A successful complete replay and reconciliation atomically publish the new directory; failures leave no completed report. Existing reports are not overwritten.

Other strategies can use `alphaquest.reporting.generate_report(events, output_directory, config, metadata=..., expected_bar_count=...)`. Consume the complete engine iterator inside the dataset reader's context; pass the saved row count so a truncated flat stream cannot masquerade as a full run. The returned manifest contains the summary/checks; the on-disk JSON additionally contains full trade/equity arrays.

Generate and independently check all nine reviewed fixtures, retaining isolated saved datasets and each report for inspection:

```bash
.venv/bin/python tests/review_reports.py --output artifacts/report-review
```

## Backtest API

The existing server exposes allowlisted strategy discovery, explicit-config backtest execution, live progress, and durable paginated results. See [backtest API commands and behavior](docs/backtest_api.md) for a reproducible saved-fixture run. `POST /api/backtests` stays open while worker-thread processing runs; poll the existing `/api/progress/UUID` endpoint from a separate request. Completed results live in `backtests.sqlite3` and `backtest_runs/` beside the dataset database. The equity endpoint returns starting equity plus one point per completed trade.

## Backtests screen

Select **Backtests** in the portal, or open `http://127.0.0.1:8000/#backtests`. Choose a saved dataset and a backend-listed strategy. The sample shows exactly its three strategy parameters; account, instrument, slippage, and commissions are separate. Review the bar-close timestamp assumption and source timezone, then run with live processed/total bars and elapsed time. The form prevents duplicate submissions while active and shows the saved run ID and the exact settings used after completion. Reports include max drawdown amount, percentage, and duration from full trade-close equity, plus paginated trades, the equity chart and CSV downloads. Dataset management remains available. See [the fixture walkthrough and submitted-setting checks](docs/backtests_portal.md).

## Verify

```bash
python -m pytest
```

Chromium browser checks are optional: install `.[dev,browser]` with `requirements.lock` constraints, run `python -m playwright install chromium`, then `python -m pytest tests/test_backtests_browser.py -q`.

Tests cover datasets and the portal, reader snapshots and incremental parsing, exact execution/cost arithmetic, all reviewed trade/equity fixtures, causal callbacks, final-bar handling, explicit invalid-intent errors, and bounded memory for streamed execution results. Sample strategy checks cover green/reset behavior, no pyramiding, elapsed-time exits across bar intervals and gaps, re-entry rules, end-of-data handling, and changes/validation for each parameter. Report checks compare every summary/trade/equity field and CSV row with independent expectations, verify reconciliations and precision, and exercise failure cleanup and bounded-memory export.

## Structure

- `alphaquest/datasets.py`: CSV validation and SQLite storage.
- `alphaquest/backtest_data.py`: saved-dataset snapshot reader and normalized-bar review command.
- `alphaquest/strategy.py`: immutable strategy inputs, intents, execution settings, and callback protocol.
- `alphaquest/execution.py`: streaming long-only fills, trade records, cash, and equity.
- `alphaquest/decimal_math.py`: exact shared Decimal addition, subtraction, and multiplication.
- `alphaquest/strategies/consecutive_green_hold.py`: sample strategy identity, parameter definitions, and all entry/exit decisions.
- `alphaquest/reporting.py`: strategy-agnostic summary, reconciliation, and streamed JSON/CSV exports.
- `alphaquest/run_backtest.py`: sample-strategy command using a saved dataset ID.
- `alphaquest/backtest_api.py`: validated backtest endpoints and worker orchestration.
- `alphaquest/backtest_runs.py`: completed-run persistence and indexed result pages.
- `alphaquest/strategies/registry.py`: code-owned allowlist and script-owned parameter discovery.
- `alphaquest/app.py`: API and local web server.
- `alphaquest/web/`: HTML, CSS, JavaScript, and example CSV; no frontend build step or CDN.
- `tests/`: dataset, API, reader, execution, and strategy checks; runnable fixture reviews.

The original [AlphaQuest repository](https://github.com/yuxuantan/alphaquest-research-engine) was consulted for context. This increment uses a small new implementation, with no imported governance, campaign, or backtest framework.
