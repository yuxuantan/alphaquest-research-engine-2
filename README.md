# AlphaQuest Research Engine 02

A small local research portal with CSV dataset management, a streaming backtest dataset reader, a strategy-agnostic execution engine, a consecutive-green-bars sample strategy, and JSON/CSV backtest reports. The Backtests screen configures runs and opens completed reports with exact metrics, a bounded trade-close equity chart, paginated trades, saved settings, and CSV downloads.

New reports also include a **Market benchmark**: fixed long holding versus the
strategy, aligned mark-to-market equity/drawdowns, monthly/yearly results and
durable JSON/CSV downloads. Choose holding contracts before IS; manual OOS
inherits that quantity. These are explicitly price-series comparisons; executable
futures roll performance remains unverified. See [the guide and reproducible
synthetic example](docs/market_benchmark.md).

**Optimizations** runs exhaustive parameter combinations through the same engine.
Set start, end and an editable step for every strategy parameter; the read-only
step counts and total backtests update automatically. Inspect saved
performance rows, sort any column in either direction, open full trial reports,
or download the sorted CSV. Values advance by step through the end limit; jobs allow up to
10,000 combinations. Independent trials use a configurable process pool (up to
4 workers by default); select 1 for serial execution. See [the optimization guide](docs/optimization.md) for
examples, API details and reproducible browser evidence.

The Backtests selector also includes **Vwap pullback risk sizing**, a port of
the supplied MultiCharts PowerLanguage strategy, with ORB/VWAP latches, ADX
gates, pivot/pullback stops, risk sizing, optional shorts, next-bar market
orders, brackets, and EOD exits. See [the strategy guide](docs/strategies/vwap_pullback_risk_sizing.md)
for defaults, full-session one-minute data requirements, CLI use, and explicit
OHLC execution assumptions. The same-close descriptions below apply to the
original consecutive-green-bars sample; the VWAP strategy uses the execution
extension described in its guide. MultiCharts export parity remains unverified.

## Independent phase research

[Guided prop configuration](docs/prop_setup.md) starts from a saved report with
a goal choice, relevant source/design/account steps and a review/check/run stage.
Previous analyses and legacy tools remain separate and available.

**Strategies → Import trades** accepts complete, versioned trade/risk
exports and saves an ordinary report with original bytes, provenance and exact
cost reconciliation. Eligible ordered-mark sources can continue through
**Configure prop analysis → Check source → Run analysis** for the existing
annualized model. No market bars or native strategy replay are invented. See the
[export contract](docs/designs/trade_export_v1.md),
[import steps](docs/research_workflow.md#external-trade-imports) and
[saved demonstration](docs/prop_simulation_review.md#canonical-external-trades-and-local-prop-analysis--2026-11-08).
Eligible exported IS sources also support independent phase campaigns with
fixed-contract, fixed-dollar and percentage-risk policies. Every percentage
policy names its capital/balance/cushion base. Native risk-based resizing requires
a strategy rerun; captured stops alone do not establish an invariant signal path.

The same saved report's **Configure prop analysis** screen now includes
**Nested research**: preview rolling/expanding session windows, declare inner
qualification criteria, run ordinary isolated backtests, and reopen/download
every candidate's evidence. Named execution scenarios rerun real fills; causal
market-condition evidence exposes unknown labels and optional versus required
conditions. Signal neighborhoods exclude quantity/display settings. Optional
**Economic validation** hands every qualified configuration to independent phase
searches, freezes the selected family before outer evaluation, and saves modeled
cash on the actual chronological outer sequence. Forecasts, pending receipts and
provider-rule gaps remain separate. Predeclared references now run through the
same phase reports, and consolidated reliability retains every fold, family,
missing outcome and acquisition censoring. Funded studies may explicitly select
a historical lower estimate of mean received cash, with history and Monte Carlo
precision requirements. **Native account-state replay** now reruns complete
one-minute MNQ/VWAP historical sessions with causal quantity decisions, actual
fills and separate provider/cash ledgers. Its optional native Monte Carlo forecast
replays observed contiguous blocks with prior-only feature warmup and a separately
declared modeled calendar. Independent campaigns and nested studies can use this
native execution mode for fixed contracts, fixed dollars or percentage risk;
the selected policies rerun the actual later bars with account control.
Native Evaluation supports Apex EOD and LucidFlex; Lucid's modeled activation
fee is zero. The saved-trade-path Evaluation method remains Apex-only. Profile
choices, fees and timing survive draft reloads and execution-mode changes;
unsupported combinations require an explicit correction before running.
Complete research procedures can also be frozen, assessed against a protected
final window, and rerun on eligible development history for a current research
candidate. Final assessment cannot select a replacement winner. Metadata-only
uploads and durable local access history distinguish protected, already accessed
and unknown-history data. **Research** gathers saved campaigns and
editable drafts with search, filters and the next available action. Drafts
preserve source-bound settings; reusable templates require fresh source selection
and preview. Reports include observed-session fold timelines, parameter
qualification plots and matched forecast/actual receipt plots with full tables.
Optional explicit frozen Evaluation/Funded pairs now run on a common finite
calendar window with separate fees, receipts and pending cash. Current-policy
reports can launch independent supplied forward observations, reconciliation and
advisory pause/recovery. These records do not place broker orders. Prospectively
declared complete Funded observations can show a descriptive forecast/cash
difference with exact coverage and calendar assumptions. Supplied causal sizing
contexts are checked against the frozen sizing law. Missing evidence withholds
comparison; neither check verifies an external platform. Local research qualification passed on 8 November 2026: **2,315 tests**, including
176 browser cases, with no failures or skips. Provider and live-execution
qualification remain separate; see the saved acceptance record.
See the [complete workflow](docs/research_workflow.md#first-complete-campaign-a-practical-walkthrough)
and [implementation checklist](docs/robust_research_plan.md).

From **Strategies → New backtest**, save an IS grid, open a trial report, then
**Configure prop analysis → Create Evaluation campaign / Create Funded campaign**.
Evaluation minimizes acquisition cost and calendar time with a complete estimated
Pareto frontier; it does not choose a weighted winner. Funded maximizes modeled
trader cash received before a saved horizon, conditional on a fresh funded
account. Each phase selects independently from saved IS trials across jobs and
strategies. Check sources, run, inspect/download results, freeze named IS choices,
then manually launch frozen OOS assessment. Assessment never reselects.

For grids feeding these campaigns, uncheck **Calculate automatic legacy Apex and
Lucid prop reports** to skip expensive joint calculations. It stays checked by
default for compatibility; saved reports still support manual prop configuration.
[Campaign steps](docs/research_campaign_api.md) ·
[Grids and resource limits](docs/optimization.md) ·
[Freeze/OOS policy](docs/research_workflow.md) ·
[Current module ownership](docs/architecture.md#final-module-ownership-and-retention)

## Documentation

- [Architecture guide](docs/architecture.md): requirements, workflow, code components and design trade-offs.
- [Documentation index](docs/README.md): product guides, contracts, strategy
  references and reproducible evidence.
- [Phase research campaigns](docs/research_campaign_api.md): compare saved IS trials across strategies/jobs, bound size searches, run independent Evaluation/Funded objectives, and freeze/export results with manual frozen OOS assessments in the prop workflow.
- [Independent phase optimization plan](docs/phase_optimization_plan.md): implemented phase backends, portal campaigns and frozen OOS assessment; adaptive refinement and new-grid generation remain planned.
- [Prop portfolio plan](docs/prop_portfolio_plan.md): completed dated phase and
  cash-ledger increments, with optional portfolio optimization still planned.

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

Open a completed **Backtest report → Configure prop analysis**, inspect the
source and optional measured-excursion export, **Check source**, then **Run
analysis**. AlphaQuest calculates evaluation outcomes, funded payouts, sizing,
lifetime economics, historical slot cash and charts locally in Python/NumPy.
New calculations use no external engine or generated reference-report outputs.
Results and input/provenance records persist as JSON/CSV/SVG/ZIP downloads.

For the supplied VWAP backtest, the matching MultiCharts XLSX is selected after
all trade IDs, directions, UTC entry times, quantities and net costs reconcile.
Its measured excursions supplement native trade storage. Without a matching
export, captured native risk supplies conservative held-OHLC excursion bounds
when available; otherwise the report discloses a close-only fallback. Bar bounds
are not measured tick MAE/MFE.
The retained legacy annualized default uses one source with nonoverlapping trades,
Apex 50K EOD,
$49 evaluation + $129 activation, 30% holdout, block 5, 20 slots and standard
simulation counts. Set prices to $109 and $0 for the alternative choice.
Saved reports reopen without rerunning. Prior notebook and external-engine
reports remain immutable and display historical notices.

See [the model specification](docs/prop_simulation.md) and
[reproduction and independent parity evidence](docs/prop_simulation_review.md).

To change a saved dataset's tick size or monetary point value, click **Edit defaults** in its library row, edit the values, then click **Save instrument settings**. The updated defaults persist and pre-fill future backtest configurations. Run-specific overrides and completed reports remain separate from these saved defaults.

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

`alphaquest.execution.execute(bars, strategy, config)` yields immutable `Trade` and `EquityPoint` events incrementally. The engine supports long and short positions, strategy-declared same-close or next-open market entries/full closes, and next-bar stop/target brackets under explicit OHLC fill assumptions. Market fills apply adverse slippage; commissions are charged on both sides, and cash and mark-to-market equity use exact Decimal arithmetic. Quantity stays fixed for each position; pyramiding and partial closes are unsupported. The strategy receives actual simulated fills. Signals and holding periods remain strategy-owned. Optional native account control admits quantities and enforces account barriers through these same fills and accounting routines.

Consume the execution stream within `read_bars`' context. Write each event to a chosen sink to keep result memory bounded:

```python
from alphaquest.execution import execute

with read_bars(store, dataset_id) as bars:
    for event in execute(bars, strategy, config):
        print(event)
```

The sample `consecutive_green_hold` strategy uses long, same-close execution; VWAP declares next-open entries and protective brackets. Recorded fill times use the containing bar's close label, not a measured intrabar timestamp. The stream starts with initial equity and produces one equity point per bar. Under default `strategy_finish` completion, the final point includes an explicit strategy `on_finish` close; a last-bar entry can therefore close at the same timestamp with both fills charged. Native `require_flat` completion rejects open exposure or pending orders without inventing EOF liquidation. Earlier emitted events remain provisional until successful exhaustion. Unsupported intents and non-chronological input reject.

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
  --output artifacts/my-backtest --is-percent 70 \
  --green-bar-count 3 --hold-minutes 20 --contracts 2 \
  --initial-capital 10000 \
  --slippage-ticks 1 --commission-per-contract-per-side 1
```

For the synthetic arithmetic fixture, save tick size **0.25** and monetary point value **10** on the dataset first. These are not NQ or other real instrument specifications. Capital and costs remain per-run inputs. Tick size and point value default to the dataset; optional `--tick-size` and/or `--point-value` flags override them for this run only. The command uses the dataset's saved timezone and preserves the source CSV/metadata. `--output` must name a new path. It becomes a shortcut to the normal saved Backtest directory, containing:

- `report.json`: summary, reconciliation checks, full trade records, and the complete equity curve. It records resolved execution/strategy settings, dataset ID/hash/source timezone, strategy ID/source hash, and the bar-close/same-close assumptions.
- `trades.csv`: every field from the engine's completed trades, including reference/fill prices, both commissions, gross/net P&L, holding time, deadline, and reasons. Zero trades produces headers only.
- `equity.csv`: starting equity followed by one row per completed trade, with columns `trade_number,exit_time_utc,net_pnl,equity`. The starting row uses trade number 0, a blank exit timestamp, and zero trade P&L. Each subsequent row records that trade's net P&L and the engine's equity immediately after closing, with all costs included. Breakeven and end-of-data exits each get a row; zero trades produces only the starting row. The full bar-close equity curve remains in `report.json`.

The CLI also registers this run in the existing Backtests catalogue and saves its
default Apex 50K EOD prop analysis ($49 evaluation, $129 activation, 20 slots).
Its JSON output includes `backtest_id` and `default_prop_analysis_id`; open the
same library in the portal to inspect Historical net and downloads. The output
shortcut shares the saved files, and removing the shortcut preserves the saved
report. Unsupported prop sources show an explicit N/A reason while retaining
the backtest. Portal/API single backtests and new optimization trials enable
legacy reports by default; grids may explicitly set `automatic_prop: false`.
Standard simulation counts add runtime when enabled.

JSON monetary values and financial CSV cells use exact Decimal strings with no display rounding. JSON timestamps use UTC ISO 8601; null timestamps/deadlines become blank CSV cells. Win rate uses **net** winning trades divided by all completed trades, including breakevens. Zero trades produces JSON `null` and the command displays **N/A**. Recurring percentages use 28 significant Decimal digits; integer win/loss/breakeven counts remain authoritative.

The strategy-agnostic reporter consumes engine events once. It preserves engine fills, costs, and equity, aggregates trade values with exact arithmetic, and verifies final equity against initial capital plus summed net P&L. It does not replay a strategy or recalculate fills, costs, or unrealized P&L. JSON arrays and CSV rows stream through disk-backed staging files, so memory does not grow with result length. A successful complete replay and reconciliation atomically publish the new directory; failures leave no completed report. Existing reports are not overwritten.

Other strategies can use `alphaquest.reporting.generate_report(events, output_directory, config, metadata=..., expected_bar_count=...)`. Consume the complete engine iterator inside the dataset reader's context; pass the saved row count so a truncated flat stream cannot masquerade as a full run. The returned manifest contains the summary/checks; the on-disk JSON additionally contains full trade/equity arrays.

Generate and independently check all nine reviewed fixtures, retaining isolated saved datasets and each report for inspection:

```bash
.venv/bin/python tests/review_reports.py --output artifacts/report-review
```

## Backtest API

The existing server exposes allowlisted strategy discovery, explicit-config backtest execution, live progress, and durable paginated results. See [backtest API commands and behavior](docs/backtest_api.md) for a reproducible saved-fixture run. `POST /api/backtests` accepts a single parameter set (HTTP 201 after worker-thread processing) or an exhaustive grid (HTTP 202 with a background batch). Poll `/api/progress/UUID` for single replay progress or `/api/backtests/batches/{id}` for a batch. Completed results live in `backtests.sqlite3` and `backtest_runs/` beside the dataset database. The equity endpoint returns starting equity plus one point per completed trade.

## Strategies and backtests

New standalone runs default to compact reports: all trades, metrics, trade-close
equity and prop analysis are retained. **Generate full detail** saves a separately
verified compressed per-bar report when needed. The API accepts
`report_detail: "full"`; the CLI accepts `--report-detail full`. Expand **Runtime
breakdown** on a saved report for phase times and their original JSON download.

Installation optionally compiles AlphaQuest's local prop model with Cython. A
matching build is selected automatically; the Python reference remains available
when no matching binary exists. Rebuild an editable checkout with
`.venv/bin/python setup.py build_ext --inplace` after editing the model source.
Runtime breakdown and saved prop report metadata identify the chosen backend.

The form defaults to **Reopen identical saved results**. Source, settings, engine
and saved artifacts are verified before reopening the original report. Uncheck
to create a new backtest. Identical trade histories may reuse verified local prop
calculations while preserving the new report's source identity. Runtime breakdown
identifies source/calculation reuse. CLI `--fresh` bypasses all three caches.
Independent prop sweeps share a bounded process pool; `ALPHAQUEST_PROP_WORKERS=1`
selects serial execution. Parsed bars and declared pure indicators use a bounded
disposable cache (`ALPHAQUEST_REPLAY_CACHE_MB`, default 2048 MiB).

The main navigation contains Datasets and Strategies. The Strategies view has
two equal desktop panes: instruments and their saved backtest summaries. A row
arrow opens the full report. Date ranges do not split instrument groups. See
[the navigation workflow and evidence](docs/strategies_navigation.md).

Open a completed report and use **Delete backtest**
to permanently remove that selected backtest and its report/CSV files after
confirmation. The source dataset, saved prop analyses and optimization metrics
are kept. Optimization rows identify deleted backtests and retain their results;
the deleted report is excluded from future trial reuse. Wait for any prop analysis
or full-detail replay using that source to finish before deleting it.

Select **Strategies** in the portal, choose an instrument to browse saved backtests, or use **New backtest** (`http://127.0.0.1:8000/#backtests/new`). Choose **Single parameter set** or **Parameter sweep · exhaustive** in the same form. Choose a saved dataset and a backend-listed strategy. The sample shows exactly its three strategy parameters; account, instrument, slippage, and commissions are separate. Review the bar-close timestamp assumption and source timezone, then run with live processed/total bars and elapsed time. The form prevents duplicate submissions while active and shows the saved run ID and the exact settings used after completion. Reports include max drawdown amount, percentage, and duration from full trade-close equity, plus paginated trades, the equity chart and CSV downloads. Dataset management remains available. See [the fixture walkthrough and submitted-setting checks](docs/backtests_portal.md).

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

## Required IS/OOS declaration

Before a new backtest or parameter sweep, declare IS/OOS dates or an IS percentage
and review the resolved split. Initial backtests and prop analyses use only IS.
Open one saved IS result and explicitly select its parameters to run OOS later.
Splits remain editable for new IS runs; each saved report retains its own split.
Manual OOS attempts are unlimited, with failed/interrupted attempts retained in
access history. Frozen phase campaigns apply saved parameters/sizes without OOS
reselection. Previously accessed data is never relabelled untouched. See
[the workflow, API, CLI and reproducible evidence](docs/research_workflow.md).

## Independent phase campaigns in the portal

1. **Datasets → Strategies → New backtest**: declare IS/OOS and save IS trials.
2. Open a completed backtest/trial → **Configure prop analysis** → **Create
   Evaluation campaign** or **Create Funded campaign**. Add saved trials/jobs
   from other strategies with matching source/split/cost protocols.
3. Choose the profile, explicit MNQ size/policy lists, IS window and
   simulation/calendar settings. Checking counts the complete membership; searches
   above 128 candidates require confirmation of that exact count. Evaluation compares acquisition cost/time;
   Funded compares received cash over its declared horizon with risk limits.
4. **Save and check candidates → Run campaign**. Inspect progress, all candidate
   metrics, source links, filters and charts. Evaluation shows a Pareto frontier
   and marginal acceleration costs without a single automatic winner.
5. Name/check the chosen resolved frontier point(s) or feasible funded
   configuration(s), enter a rationale, and **Freeze selected candidates**.
6. **Launch OOS with frozen settings** manually. Open the appended assessment:
   Evaluation validates acquisition cost/time; Funded validates payouts/risk.
   OOS cannot change the frozen IS family or rank a new winner. Download CSV,
   JSON, the frozen package and report ZIPs; reloading never recalculates.

Legacy business-level joint sizing remains accessible below campaign creation,
with its original annualized calculations and saved download links. See the
[complete controls/API and limits](docs/research_campaign_api.md) and
[reproducible portal evidence](docs/prop_simulation_review.md#phase-campaign-portal-and-frozen-oos--2026-11-06).
