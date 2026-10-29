# Exhaustive optimization

Open **Strategies → New backtest** (`/#backtests/new`). All backtests use the
same exhaustive parameter grid; there is no separate mode selector. Select a
saved dataset and strategy, review the required IS/OOS declaration, review
instrument settings, and enter capital, slippage and commissions. Account and
execution settings are fixed across trials. Every strategy parameter has
**Start value**, **End value**, **Step** and **Step count** columns.

Keep start and end equal on every row to run one backtest. A grid generating one
combination opens its normal report with live progress. Widen ranges for more
combinations; the results open as a sortable batch table with links to individual
reports. The same grid drafts, costs, benchmark settings and saved-result reuse
control apply in both cases. There is no second parameter form to keep in sync.
Both submit to `/api/backtests`; the server's single-report request remains
available for integrations and selected manual OOS runs. Existing
`/#optimizations` bookmarks open this same grid.

**Step** is the editable increment between values. Equal endpoints set it to 0;
changing endpoints to different values defaults it to 1. You can then enter a
positive increment (a whole number for integer parameters, or a decimal for
Decimal parameters). Edited increments survive refresh/navigation while the
endpoints remain different. Returning endpoints to the same value resets step
to 0 and fixes that parameter.

**Step count** is read-only and calculated automatically:

`floor((end - start) / step) + 1`

Equal endpoints have count 1. Start is always tried, then step is added until
the next value would exceed end. End is included only when a step lands exactly
on it; no extra end value is appended. For example:

| Type | Start | End | Step | Step count | Values |
| --- | --- | --- | --- | --- | --- |
| Integer | 1 | 5 | 2 | 3 | 1, 3, 5 |
| Integer | 1 | 6 | 2 | 3 | 1, 3, 5 |
| Integer | 1 | 2 | 5 | 1 | 1 |
| Decimal | 0.1 | 0.3 | 0.1 | 3 | 0.1, 0.2, 0.3 |
| Decimal | 0 | 1 | 0.3 | 4 | 0, 0.3, 0.6, 0.9 |
| Boolean | false | true | 1 | 2 | false, true |
| Boolean | true | false | 1 | 2 | true, false |
| Fixed | 20 | 20 | 0 | 1 | 20 |

The **Total combinations** line below the table shows the product of all row
counts: **2 × 4 × 3 = 24 backtests**, one backtest for each distinct parameter set.
Fixed rows contribute a factor of 1 and are omitted from the displayed
multiplication. A fully fixed grid shows **1 = 1 backtest**. Invalid ranges show
an explanatory message instead of a misleading count.

Numeric start must be <= end. Equal endpoints require step 0; different numeric
endpoints require step > 0. Integer endpoints and steps must be JavaScript safe
integers. Decimal endpoints and steps are exact strings in API requests, at most
128 characters, within 100 decimal places/orders of magnitude. Frontend counts
use exact integer arithmetic for decimal digits, and the server independently
builds the grid using rational arithmetic. This avoids floating-point count errors.
Boolean endpoints are actual JSON booleans and can use either order; their step
is 0 for a fixed value or 1 for both values. All strategy parameters must appear,
with no extra names. The API accepts `start`, `end`, `step` and computes counts;
it does not accept a caller-supplied `step_count`.

Every combination passes the strategy's own validation before a job is created,
including valid HHMM times and coupled pivot/history settings. For example,
numeric stepping from 0950 through 1000 by 25 produces an invalid intermediate
0975 and is rejected; HHMM fields are numeric inputs, not elapsed minutes.

**Start backtests** runs the Cartesian product in definition order. The portal
shows the product of step counts before submission; jobs are limited to 10,000
combinations. Only Exhaustive is supported. Choose **Parallel backtests** below
the grid: **1** runs serially; higher values compute trials in separate Python
processes. The default is up to **4**, leaving at least one detected logical CPU
available when possible. The selectable maximum is the smaller of **8** and
logical CPU count minus one, with a minimum of 1. The actual worker count is
capped by the number of trials. More workers use more CPU, memory and disk
bandwidth; small grids can be slower because of process startup.

Worker options load independently of dataset/strategy choices. If loading fails
or exceeds 10 seconds, the selector shows **Worker options unavailable** with
**Retry worker options**. Retrying preserves the parameter grid and selected
dataset. Submission remains disabled until valid worker options load. An older
backend without this endpoint shows a specific restart message. Reloading the portal fetches matching, current
frontend assets so older cached scripts cannot leave a stale loading selector.

Saved retry evidence is under
`artifacts/optimization-worker-loading-review-20261027/`: screenshots and
`verification.json` show a simulated settings-only HTTP 503, successful retry
against the real API, preserved inputs, and a completed three-trial synthetic
optimization with independently expected net P&L 13, 26 and 39 CU. Its isolated
dataset and normal backtest reports are retained alongside the evidence.

One optimization job runs at a time; later jobs queue. Within the active job,
only as many trials as workers are in flight, so the complete grid is never
submitted as an unbounded task queue. The API accepts a job immediately with HTTP 202, and the
portal opens its durable URL `/#optimizations/JOB_ID`. Navigating away or
refreshing does not stop a running job. Do not start the server with multiple
workers against the same data directory. Graceful shutdown waits for queued and
running jobs; an abrupt restart marks unfinished jobs **interrupted**, retaining
saved trials and never silently resuming or rerunning them.

The process pool uses Python's **spawn** start method, including on macOS. Every
combination uses a fresh strategy instance and the normal backtest engine and
report writer. Workers write temporary reports to separate directories; the
coordinator publishes compact backtest reports and optimization rows through the existing
run store. Child processes never open or write the dataset/results databases.
Only small manifests and progress messages cross process boundaries. When pending
trials exceed workers, one coordinator pass checks the original CSV byte count,
hash, schema, all rows and timestamps, applies the date selection, and writes a
shared prepared-bar stream. Workers read independent, bounded chunks containing
the original exact Decimals, UTC timestamps and CSV fields. Date selection does
not require another parse or temporary CSV. Jobs with at most one pending trial
per worker use the ordinary frozen-CSV reader to avoid added preparation cost.
Deleting the original after snapshot preparation does not change the job. The
captured dataset metadata, strategy source hash, resolved axes, execution settings
and requested dates remain inspectable. Each selected date range starts with fresh
strategy state and the existing end-of-data behavior. A job queued before its
source is deleted can fail during preparation.

Results show every strategy parameter and the existing performance metrics:
net/gross P&L, commissions, slippage cost, final equity, trade/win/loss/breakeven
counts, win rate, maximum drawdown amount/percentage and duration in seconds.
Money uses CU (unspecified account currency). Metrics retain normal engine
semantics, including trade-close drawdown. No metric is calculated in the browser.

Click **any column heading** to sort ascending, then click it again to reverse.
Headers stay visible while scrolling within the result table and while moving
down the page through the table. Horizontal scrolling keeps headers aligned
with their values. Parameters with more than one generated value have highlighted
headers/cells and a **Varies** badge regardless of whether they are frozen.
Highlighting uses the entire saved grid and remains consistent across sorting,
pagination and reopening. A range generating one value is treated as fixed.

### Choose visible columns, freezing and order

Expand **Columns** above the results. Every parameter, performance metric, Trial
and report-link column has separate **Show** and **Freeze** checkboxes. Only
columns checked under Show are displayed. A visible column with Freeze unchecked
scrolls normally; a checked Freeze box keeps it on the left. Hiding a frozen
column also unfreezes it. Use the search box to find names without changing the
selection. The collapsed summary shows how many columns are shown and frozen.

Use **↑ / ↓** beside a visible column to move it earlier/later. Frozen columns
stay together on the left, and each group can be reordered independently. Hidden
columns have disabled movement controls until shown. Movement skips hidden
columns, so each action changes the visible order. These native buttons work
with keyboard and touch as well as a mouse.

**Show all** selects all available columns while retaining the current order.
**Hide all** clears the view so a small selection can be built quickly. An empty
view displays a recovery message and retains the controls. **Reset layout**
restores all columns, their default order and only Trial frozen. **Unfreeze all**
clears freezing while retaining visibility and order. All columns are shown by
default. A sort note remains visible even if the sorted column is hidden.

Frozen columns together can occupy at most **40% of the visible table viewport**,
measured from their actual rendered widths. A box that would exceed the limit is
disabled with a Width limit label and an explanation to unfreeze another column
or widen the table. Checked columns remain available to uncheck. Resizing to a
narrower screen temporarily releases saved columns that no longer fit; they
return when sufficient width is available. Headers stay sticky independently of
freezing. A small set of columns uses its natural width rather than stretching
across the entire viewport.

Visibility, order and freezing are saved in this browser's local storage
separately for each strategy and survive refresh, sorting, result pages and
other batches of the same strategy. Existing freeze-only preferences migrate
with all columns shown. Saved numerical results, full CSV contents and report
links are retained; no backtest is rerun. If browser storage is unavailable,
preferences still work during the current page session. Unknown stored column
names are ignored. Newly introduced columns appear through Show or Show all
when using an explicitly selected subset.

For a reproducible synthetic review, use green bar count **3 / 3 / 0**, hold
minutes **20 / 25 / 5** and contracts **1 / 30 / 1** (start/end/step), with one
worker and the arithmetic dataset below. Expect 60 saved trials across two pages.
Hold minutes and Contracts are highlighted; only Trial is frozen by default.
Choose the columns to show and move them within their groups, then scroll/sort,
change pages and refresh. Expect the same column layout and highlights. Current
visibility/order evidence is in `artifacts/optimization-layout-20261029/`; the
previous freezing-only review remains in `artifacts/optimization-freeze-20261029/`.

The earlier automatically frozen-parameter implementation's evidence remains
unchanged under `artifacts/optimization-frozen-columns-review-20261027-verified/`,
`artifacts/optimization-table-review-20261027-verified/` and
`artifacts/optimization-frozen-columns-sort-review-20261027/`.
Repeat the current checks into a new directory to preserve saved evidence:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_optimization_columns_browser.py \
  tests/test_optimization_layout_browser.py tests/test_optimization_browser.py -q \
  --basetemp artifacts/optimization-layout-NEW
```

These checks own and stop their temporary servers and retain the isolated normal
reports, screenshots, expected metrics and verification JSON.

Sorting applies to all saved trials before pagination (50 rows per page), with
exact Decimal comparisons rather than lexical or floating-point money order.
Missing win rates from zero-trade runs display N/A and sort last in both directions;
equal values retain trial order. Trial numbers always identify the same Cartesian
parameter set, regardless of finish order. Finished trials appear immediately,
even if earlier trial numbers are still running. CSV/page snapshots follow
publication order internally so late completions cannot shift or duplicate rows.
Each row links to its saved Backtest report,
including trades, equity and normal downloads. **Results CSV** exports all saved
trials in the selected order. While a job runs, the export contains the number of
trials captured when the export starts. A failed/interrupted job retains completed
trials, is explicitly labelled, and never claims exhaustive completion. When a
trial fails, no more trials are launched; already running trials finish and
successful reports are retained. A crashed worker pool fails the job explicitly.
Temporary files and owned processes are cleaned up after completion or failure.
The job status shows saved trial count, worker count, elapsed seconds and the
active trials' bar progress. Completed rows retain their execution PID/timestamps
for inspectable concurrency evidence.

Results, statuses and saved job settings live in the existing `backtests.sqlite3`
catalogue (`optimizations` and `optimization_trials` tables). Full trial artifacts
use the existing `backtest_runs/RUN_ID` store and appear in completed backtest
history. Existing reports and datasets are unchanged. There is no automatic start-request
retry, job resumption, pruning or cancellation. If a start
request loses its connection, inspect **Saved optimizations** before starting again.

## Compact storage and optional full detail

New optimization trials use **compact** storage by default in both serial and
process-worker execution. They retain every performance metric and reconciliation
check, source/strategy hashes, execution settings, replay bounds, all `trades.csv`
fields and the complete initial/trade-close `equity.csv`. Every engine event is
still validated, including the per-bar accounting identities and final bar count.
The writer skips serializing the per-bar equity series and does not create
temporary JSON arrays. Its format-2 `report.json` contains the manifest only;
`report_storage` explicitly records that per-bar equity was not retained.
Trade/equity CSVs, charts, sorting, report links and prop analysis remain available.

Open a trial's Backtest report to see its storage notice and download **Report
JSON**. Click **Generate full detail** to replay only that parameter set, retaining
the exact source, dates, strategy and execution settings. It saves a separate
normal Backtest report with `report.json.gz`; the full arrays and their staging
files use streaming gzip. The original compact report remains unchanged. Before
publication, replay metrics and both CSV hashes must match the original. Missing
source, changed strategy, or different replay outputs reject; a duplicate active
request rejects. Repeating a completed request reopens the existing detailed run
instead of writing another copy. Its source run ID remains in provenance.

Ordinary standalone backtests retain their existing full JSON default. Existing
optimization reports are not automatically converted or deleted, and existing evidence remains
unchanged. Missing trials resumed after this update use compact reports; an old
job can therefore contain reports with different retention modes, explicitly
identified in each Backtest report. This reduces future storage and temporary
worker I/O; it does not reclaim space already occupied by old full reports.

Actual labeled synthetic evidence is saved under
`artifacts/optimization-compact-review-20261027/test_compact_storage_and_norma0/`.
Two weekday sessions contain 2,880 bars and one trade each. Entry 100.25, exit
101.75, monetary point value 10 and commissions 2 give net 13 CU per trade per
contract: the two trial rows independently expect **26** and **52 CU**. Compact
files for the one-contract result total **3,718 bytes**, versus **551,057 bytes**
for a normal full backtest of the same inputs: **99.33% smaller**. The compressed
full-detail JSON is **19,702 bytes**, retaining all **2,881 equity events**. Byte
counts are this measured example, not a universal reduction estimate.

The evidence includes source CSV, optimization/backtest catalogues and reports,
downloaded compact/full JSON, screenshots, and `verification.json` with expected
metrics, actual file sizes and unchanged compact-report hashes. It also follows
the compact result through Configure prop analysis → Check source → Run → saved
report/download → reload/reopen. Native source net P&L remains 26.00; measured MAE
count is zero and the realized-loss fallback is disclosed. See
`docs/prop_simulation_review.md` for the exact prop observations and rejection case.

Reproduce in a new evidence directory (the test owns/stops its temporary server):

```bash
.venv/bin/python -m pytest tests/test_optimization_compact_browser.py -q --basetemp artifacts/optimization-compact-review-NEW
```

Use the normal `ALPHAQUEST_DATA_DIR` command with the saved test directory to
reopen these durable reports. Test URLs use temporary ports; substitute the new
server address and retain the saved `#optimizations/ID`, `#backtests/report/ID`
or `#backtests/prop/job/ID` fragment from `verification.json`.

### Compress existing optimization reports

Explicit maintenance can losslessly gzip existing trial JSON without rerunning
backtests or discarding any per-bar detail:

```bash
.venv/bin/python -m alphaquest.compress_optimization_reports --data-dir data --evidence artifacts/optimization-existing-compression-NEW
```

The evidence directory must be new. Queued/running optimization jobs reject
before any report changes; completed trials from interrupted jobs are eligible.
Only report IDs indexed by `optimization_trials` are selected. Standalone
backtests, source datasets, trade/equity CSVs, optimization rows and earlier
saved evidence stay unchanged.

For every report the command streams `report.json` into gzip, verifies the full
decompressed byte count and SHA-256 against the original, and checks the source
identity has not changed. It publishes `report.json.gz` without overwriting an
existing archive, then atomically updates that report's catalogue metadata.
Only after the verified archive is published and both CSV hashes still match
does it remove the uncompressed duplicate. The archive contains the original
JSON bytes, including its original metadata; catalogue `report_archive` records
the original filename, both file sizes and both hashes. The Backtest page and
Report JSON.gz download use the new location. Legacy drawdown readers support gzip.

A database backup, original job/report metadata and per-report durable journal
are saved under the evidence directory. An interruption before cleanup leaves
two verified copies; rerun with a new evidence directory to finish safely.
Already compressed reports are verified and skipped. A conflicting/corrupt
archive, changed catalogue, or changed source leaves the original in place and
stops the command rather than overwriting data. An OS lock prevents concurrent
compression commands on the same library.

The explicit local maintenance run on 27 October 2026 compressed **21** existing
optimization reports from **13,192,075,669** to **419,415,544 bytes**, saving
**12,772,660,125 bytes (96.82%)**. All archives were independently decompressed
and checked against their original SHA-256 and byte count after conversion.
All optimization job states/trial rows and non-storage run metadata stayed exact;
70 protected dataset/CSV/standalone-report files and nine standalone run manifests
were unchanged. The existing 16-trial results page, chart, gzip notice and actual
browser download were verified against the archive hash.

Original catalogue backup, original metadata, publication journal, per-report
hashes/sizes, portal screenshot and download verification are saved under
`artifacts/optimization-existing-compression-20261027/`. Independent preservation
checks are under `artifacts/optimization-compression-protection-20261027/`.
Earlier evidence directories were left unchanged. This was lossless compression
of existing full JSON; no historical per-bar detail was removed or recalculated.

## Recover a failed optimization

Reopen its saved results page and click **Resume remaining N trials**. It queues
the same job with its original worker count and runs only missing trial IDs,
including gaps from out-of-order parallel completion. Successful rows, run IDs,
normal Backtest reports and CSVs are retained. The source dataset must still be
available with the same hash, timezone, schema and row count; the strategy source,
parameter grid and resolved execution settings must match. Changed inputs reject
before scheduling work. A second resume request while queued/running rejects.
Earlier attempt status/error/timing remains inspectable under **Saved grid,
source & execution settings**. Elapsed time displays the current attempt.
If every trial is already saved but final status failed, **Finalize saved results**
finishes the job without rerunning those trials.

SQLite paths are anchored to an absolute path at startup. A connection-open
`SQLITE_CANTOPEN` failure retries up to four times with bounded delays before SQL
runs. Transactions are never automatically replayed. Connection/transaction
errors identify the database path and SQLite error name; full failure tracebacks
are logged in the backend terminal. A database-open failure saving advisory
progress no longer aborts workers and discards their pending results. Persistent
publication failures still fail explicitly and leave saved trials available.
If access remains unavailable, check the data directory/mount and write access,
free disk space and the server's open-file limit, then resume after restoring access.
Do not delete/recreate the database to clear an error.

The reported local job `cc3d1f1241f54ff089f95d9429ebd269` was inspected read-only:
SQLite `quick_check` returned `ok`, all 12 saved reports/CSVs were present, and
trial IDs 13–16 were missing. Its original OS-level cause cannot be established
from the saved generic error without the old traceback. A backup, original job
and row JSON, CSV hashes and the actual ready-to-resume portal screenshot are
saved under `artifacts/optimization-database-recovery-20261027/`. Its remaining
four backtests have not been started by this review.

An independent synthetic portal demonstration is saved under
`artifacts/optimization-database-recovery-portal-20261027/`. Four real worker
processes execute the normal arithmetic backtests; a controlled inaccessible
publication database path causes a real SQLite `CANTOPEN` after twelve saved
trials. Clicking Resume completes exactly four missing trials. All twelve saved
rows and CSV hashes remain identical, there are exactly sixteen normal Backtest
reports, and net P&L is `[13, 26, 39, 52]` CU repeated four times. The dataset and
injected failure are explicitly labeled synthetic in its evidence. Repeat with:

```bash
.venv/bin/python -m pytest tests/test_optimization_browser.py -k resume_remaining -q --basetemp artifacts/optimization-database-recovery-portal-NEW
```

Use a new evidence directory. The check starts and stops its own temporary server.

## Reproduce the arithmetic example

1. In Datasets, upload `tests/fixtures/backtest_contract/arithmetic_5m.csv` as
   **SYNTHETIC optimization arithmetic review**, timezone UTC, tick size 0.25,
   point value 10. Validate and save it (or reuse its saved library entry).
2. Open Optimizations, select this dataset and **Consecutive green hold**.
   Set capital 10000, slippage 1 tick per fill and commission 1 per side.
3. Use green bar count **3 / 3 / 0**, hold minutes **20 / 25 / 5**, and
   contracts **1 / 3 / 1** (start / end / step). Expect read-only step counts
   **1, 2, 3**, and **Total combinations: 2 × 3 = 6 backtests** below the table.
4. Start. Expect **COMPLETE · 6 / 6 trials saved** and six rows: each hold value
   paired with each contract quantity. Every trial has one winning trade,
   100% win rate and zero drawdown.
5. Independently calculate entry 100.25 and exit 101.75. Per contract,
   `(101.75 − 100.25) × 10 − 2 × 1 = 13 CU`. Expect net P&L **13, 26, 39**,
   gross P&L **15, 30, 45**, commission **2, 4, 6**, slippage cost **5, 10, 15**,
   and final equity **10013, 10026, 10039**. Both holds exit on the final observed
   bar; no unseen bars are created.
6. Sort Net P&L descending: **39, 39, 26, 26, 13, 13**. Download Results CSV
   and compare the same order. Open a report link and inspect its fills and
   settings. Reload its optimization URL and find the same saved results.
7. Before starting another job, enter a negative contract step. Submission rejects
   it and saves no new job. A zero step with different endpoints also rejects.
   Restoring a positive step recalculates counts. A product exceeding 10,000
   rejects before any trial runs. VWAP grids also reject invalid interior HHMM
   values and insufficient max-bars-back combinations.
8. To reproduce **24 backtests**, set green bar count **2 / 3 / 1**, hold minutes
   **10 / 25 / 5**, and contracts **1 / 5 / 2**. Expect counts **2, 4, 3** and
   **Total combinations: 2 × 4 × 3 = 24 backtests**. Run it and observe
   **COMPLETE · 24 / 24 trials saved**. The values are green count 2/3,
   hold 10/15/20/25 and contracts 1/3/5, with every Cartesian combination present.

These are synthetic arithmetic examples, with no profitability or out-of-sample
claim. Optimization itself does not select or certify a strategy.

## Saved review evidence and automated checks

The completed local review is at `artifacts/optimization-step-review-20261027-verified/`:

- `verification.json`: independent expected/actual values for all six trials,
  all 18 column sorts, invalid-step rejection, CSV order and browser checks.
- `grid-24-verification.json`, `grid-24-configured.png`, `grid-24-results.png`:
  actual 24-trial product, independent expected parameter sets and saved outputs.
- `job.json`, `results-descending.csv`, screenshots of configuration, rejection,
  desktop/mobile results and an opened backtest report.
- `datasets.sqlite3`, `backtests.sqlite3` and `backtest_runs/`: actual isolated
  saved dataset, job, indexed results and full report/CSV artifacts.

Generate another review in a **new** directory:

```bash
.venv/bin/python tests/review_optimization_portal.py --output artifacts/optimization-review-NEW
```

The script uses the actual dataset-upload and optimization portal workflow,
checks independent arithmetic and the 2 × 4 × 3 grid, and starts/stops its own temporary server. It
never touches the normal data library or existing evidence. Reopen retained data:

```bash
ALPHAQUEST_DATA_DIR="$PWD/artifacts/optimization-step-review-20261027-verified" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/#optimizations` and the saved job. Stop this manually
started server with Ctrl-C. Use a different port if 8000 is already in use.

Focused checks:

```bash
.venv/bin/python -m pytest tests/test_optimization.py tests/test_optimization_browser.py tests/test_optimization_parallel.py tests/test_backtest_api.py tests/test_backtests_browser.py -q
```

They cover independent 24-trial Cartesian results, editable step/default handling,
read-only counts, exact decimal/boolean grids, typed and
coupled rejections, numeric sorting beyond floating-point precision, pagination,
null ordering, partial failures, source deletion, restart persistence/interruption,
duplicate form submission, CSVs, report links, browser refresh and mobile layout.
Real spawn-process checks additionally compare full trade/equity CSVs with serial
execution, preserve boolean/Decimal parameter types, force out-of-order finishes,
exercise failure/crash cleanup and verify distinct PIDs with overlapping work.

Earlier arithmetic reviews under `artifacts/optimization-review-20261027*` use
the original count-driven configuration. Their saved reports/evidence remain
unchanged. New jobs record input steps and computed `step_counts`.

Boolean regression evidence is retained at
`artifacts/optimization-boolean-fix-20261027/test_adx_boolean_endpoints_aut0/`:
`adx-boolean-verification.json` contains the saved job and both typed parameter
sets, alongside configuration/results screenshots and the normal saved reports.
To reproduce, use the synthetic dataset above, choose **Vwap pullback risk sizing**,
and set **Use adx elev** start to **True** and end to **False**. Leave other
parameters fixed. Expect the read-only step count to become **2**, two combinations,
and a completed report with one trial for each boolean value. Matching endpoints
automatically return the count to **1**. Refresh and reopen the saved job to
confirm both trials persist. The same behavior applies to every boolean input.

## Parallel timing and parity review

Saved local evidence:
`artifacts/optimization-parallel-review-20261027-verified/verification.json`.
Eight full VWAP backtests over 12,000 synthetic bars each took **15.519 seconds
with 1 worker** and **8.510 seconds with 4 worker processes**, an observed
**1.82×** speedup on this eight-logical-CPU machine. These times include process
startup and report publication. All parameter sets, performance metrics and
trade/equity CSV hashes matched exactly. Worker PID/timestamps confirm real
overlap in distinct child processes. Both jobs, their normal reports, browser
screenshots and downloaded CSVs are retained in that directory. The review's
temporary server, process pool and progress manager stopped after the run.

Run the same synthetic workload through the normal portal with **1** worker and
then the desired parallel count, retaining a new isolated library:

```bash
.venv/bin/python tests/review_optimization_parallel.py --output artifacts/optimization-parallel-NEW --bars 12000 --trials 8 --workers 4
```

Choose workers within this server's displayed limit. The script uploads a labeled
synthetic dataset through Datasets, configures VWAP inputs and workers in
Optimizations, executes both jobs, downloads results, and reloads saved reports.
It saves `verification.json`, serial/parallel CSVs, screenshots, source CSV, full
normal reports, actual job timings, per-trial worker PID/timestamps and progress
snapshots. It verifies exact parameter/metric/CSV equality and overlapping work
in distinct child processes. The source closes remain inside the opening range;
independently expected results are zero trades, net P&L 0 and final equity 10000
for every parameter set. This is an execution benchmark, not trading evidence.

Timing includes dataset preparation, process startup, replay, report writing and
publication. Actual speedup depends on dataset size, strategy, storage and other
work on the computer. The benchmark reports a measured local pair, not a general
speedup guarantee. It starts/stops its own server and leaves earlier evidence
unchanged. Use the normal `ALPHAQUEST_DATA_DIR` command above with its output path
to reopen both durable jobs.

## API

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/optimizations/settings` | Default and maximum process-worker counts. |
| POST | `/api/optimizations` | Validate grid, save queued job, return HTTP 202. |
| GET | `/api/optimizations?offset=0&limit=25` | Saved jobs (limit 1–100). |
| GET | `/api/optimizations/JOB_ID` | Durable job status, grid, settings and progress. |
| POST | `/api/optimizations/JOB_ID/resume` | Explicitly resume failed/interrupted jobs, skipping saved trials; rejects changed inputs or active jobs. |
| GET | `/api/optimizations/JOB_ID/results?sort=total_net_pnl&direction=desc&offset=0&limit=50` | Globally sorted saved trials (limit 1–1000). |
| GET | `/api/optimizations/JOB_ID/exports/results?sort=total_net_pnl&direction=desc` | CSV in the same order. |

Sort keys are `trial`, `run_id`, `param.PARAMETER_NAME`, or a metric name from
`metric_columns`. Directions are `asc` and `desc`. Unknown keys/directions reject.

Example body (replace the saved dataset ID):

```json
{
  "dataset_id": "YOUR_SAVED_DATASET_ID",
  "strategy_id": "consecutive_green_hold",
  "method": "exhaustive",
  "workers": 4,
  "parameter_ranges": {
    "green_bar_count": {"start": 3, "end": 3, "step": 0},
    "hold_minutes": {"start": 20, "end": 25, "step": 5},
    "contracts": {"start": 1, "end": 3, "step": 1}
  },
  "execution_settings": {
    "initial_capital": "10000", "tick_size": "0.25", "point_value": "10",
    "slippage_ticks": 1, "commission_per_contract_per_side": "1"
  }
}
```

`workers` is an optional strict integer within the server's configured limit;
omitting it uses the server default. `worker_count` in the saved job is the
resolved count, capped by total trials. Saved jobs created before this feature
reopen as serial without rewriting their reports.

Optional `from_date` and `to_date` use the normal inclusive source-timezone date
semantics. Invalid requests create no job or backtest; runtime failures retain
an explicitly failed job and any earlier saved trials.

## Reusable acceleration

New jobs enable shared data preparation and **Reuse identical completed trials**
by default. This engine path applies to every registered strategy, including
strategies without cached features. Every computed trial still gets fresh
strategy/account state, the ordinary execution engine and all event/report
validation. Exact arithmetic now reuses bounded, thread-local Decimal contexts;
precision remains operand-derived and monetary calculations never use floats.

The optional feature interface additionally shares pure calculations between
trials. The VWAP adapter currently caches ADX and confirmed stop/target pivots.
The signal's executable source, defaults, VWAP calculation, latches, positions,
orders, sizing and fills retain their existing behavior. There are no strategy-ID
branches in the optimizer. A new strategy can use the generic benefits immediately
and register its own feature adapter later; see `docs/strategy_features.md`.

Only dependency sets used more often than the worker count are precomputed.
All selected feature streams build in one input pass with bounded buffering;
at most four streams and 512 MiB plus their current chunks are prepared. Over-budget
features fall back to ordinary strategy computation. The parsed bars themselves
also use temporary disk space, proportional to the selected dataset; this may
exceed the CSV size. They replace per-trial parsing rather than retaining a
second permanent dataset. The raw snapshot is removed after preparation, and
prepared bars/features disappear when the job finishes or fails normally.
Workers retain chunks, not the whole dataset. Abrupt process termination can
leave an abandoned `.optimization-*` workspace; these are never saved reports.

Completed-trial reuse requires the same saved dataset metadata/hash/timezone,
date bounds, strategy source/default metadata, exact parameter values, resolved
execution settings, Python/package versions, and all engine Python source files.
Scheduling choices such as worker count do not change trial identity. Legacy
reports without a recorded identity are never guessed to match. Changing a
strategy dependency or engine file invalidates reuse conservatively. New jobs
also capture this identity; resume rejects changed engine code. Legacy interrupted
jobs retain their prior source/grid/settings checks.

Before reuse, the coordinator verifies the catalogue manifest and SHA-256 hashes
of the report and both CSVs. Missing/modified artifacts cause fresh computation.
Only successfully published trials enter the cache, including successful trials
from an otherwise failed job. A reused row points to the original durable
Backtest report: it creates no duplicate report files or trade/equity indexes.
The portal displays **N reused · M computed**, and reused report links show
**Reused saved trial**. Partial grid overlap computes only the new combinations.
Uncheck **Reuse identical completed trials** to force fresh computation; this
also bypasses cache publication for that job. Sorting, highlighted/frozen varying
parameters, report downloads and full-detail replay remain available.

The API adds strict boolean `reuse_results` and `prepare_data`, both defaulting
to `true`. `prepare_data: false` uses the ordinary per-trial CSV reader and skips
feature preparation, useful as a reference path. Explicitly set
`reuse_results: false` for timing comparisons. Saved settings expose the engine
identity, prepared-data usage, feature-stream count, preparation seconds and
temporary bytes. The worker cap/default remain unchanged; more workers do not
always help.

### Benchmark your strategy and worker count

Save the normal optimization POST body as `request.json`, with an existing
saved dataset ID and a representative grid/date range. Start while the portal
is idle and choose counts within `/api/optimizations/settings`:

```bash
.venv/bin/python -m alphaquest.benchmark_optimization \
  --url http://127.0.0.1:8000 --request request.json \
  --workers 1,4,6,7 --repeats 2 --output artifacts/my-worker-benchmark-NEW
```

This command creates normal durable optimization jobs and Backtest reports in
that portal. It forces fresh computation, compares the ordinary CSV reader and
prepared path at **each** worker count, and verifies every metric, parameter set
and trade/equity CSV hash against the first CSV-reader run. Any mismatch stops
with inspectable evidence. The new output directory retains request/measurements,
per-job result CSVs and verification JSON. Timings include preparation, process
startup, computation and publication; queue wait is excluded. Median timings and
the fastest measured count are reported without changing the server default.
These are measurements for that workload and host, not a universal speed claim.

A reproducible synthetic workload and portal reuse review can be run without
touching the normal library:

```bash
.venv/bin/python tests/review_optimization_acceleration.py \
  --output artifacts/optimization-speed-NEW --bars 20000 --repeats 2
```

It starts/stops its own server. The source has changing highs/lows but closes
inside every opening range: independently expect **zero trades**, net P&L **0**
and final equity **10000** for all eight VWAP parameter sets. Other automated
checks compare all equity/trade events with nonzero long/short trades and
stop-first exits, exercise exact date/Decimal/source handling, prove a separately
registered synthetic strategy can declare features without optimizer edits,
and verify partial reuse, corrupt/missing artifacts and forced fresh runs.

For nonzero portal results, use the arithmetic reproduction above. Run the same
three-contract grid twice with reuse checked: expect the original report IDs,
**3 reused · 0 computed**, net **13 / 26 / 39 CU**, and three reports total.
Uncheck reuse and rerun: expect **0 reused · 3 computed** and six reports total.
Reload/reopen both jobs and download the same results. The browser check retains
screenshots and actual outputs with:

```bash
.venv/bin/python -m pytest tests/test_optimization_browser.py \
  -k reuse_toggle -q --basetemp artifacts/optimization-reuse-NEW
```

### Measured review on 27 October 2026

Final evidence is saved at
`artifacts/optimization-speed-20261027-final/benchmark/verification.json`,
with normal source/catalogue/reports in its parent directory. Two fresh runs
per configuration, eight trials over 20,000 labeled synthetic bars:

| Workers | Ordinary CSV median | Prepared/features median |
| --- | --- | --- |
| 1 | 8.846 s | 6.247 s |
| 4 | 8.912 s | 8.523 s |
| 6 | 10.060 s | 6.823 s |
| 7 | 7.564 s | 7.027 s |

The serial improvement was **1.42×**; the same four-worker comparison improved
about **4%**. This small workload ran fastest with one worker, demonstrating why
worker count is benchmarked rather than increased automatically. All sixteen
measured jobs matched every parameter set, metric and both CSV hashes exactly.
The all-hit rerun in `reuse.json` took **0.048 s**, reused all eight original
report IDs, launched no workers and created no duplicate Backtest reports.
`reused-results.png` shows the actual portal table and it was reloaded successfully.
Its temporary server stopped after verification. Earlier preliminary timing
artifacts remain preserved; use this `-final` directory for the review.

Reopen the retained normal library with an unused port:

```bash
ALPHAQUEST_DATA_DIR="$PWD/artifacts/optimization-speed-20261027-final" \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8011
```

Open `http://127.0.0.1:8011/#optimizations`, or the final reuse job
`/#optimizations/24ba24a8eead43cfb0ed3954369fd27a`. Expect eight rows, eight reuse
badges, **8 reused · 0 computed**, no trades and final equity 10000. Report links
open the original computed reports. Stop this manually started server with Ctrl-C.
The command is a reproduction instruction; no persistent server was started by
the review.

Final regression check: **691 tests passed** (249.10 s). Validation metadata and
preservation checks are at
`artifacts/optimization-speed-20261027-final/validation.json` and
`preservation.json`. Final browser/reuse/prop outputs are retained under
`artifacts/optimization-acceleration-final-suite-20261027/`. All 70 protected files,
21 original compressed optimization reports and the original job/trial payloads
remain unchanged. No reports were pushed or published externally.

## Automatic Apex Historical net

Every trial in a new optimization now runs the default local Apex 50K EOD prop
analysis after replay, inside the same worker. Defaults are **$49 evaluation +
$129 activation, 20 slots**, block 5, a 70/30 weekday split and the existing
standard counts (3,000 sizing paths and 20,000 final evaluations/accounts). The
captured profile is strategy-independent and appears in saved settings. Automatic
runs use native fills and disclose the existing close-only excursion fallback;
no trade export, vendor software or VM is required.

**Historical net · USD** appears immediately after Trial, before fixed parameters.
Click its heading for ascending/descending sorting; N/A remains last in either
direction. Click its value for the ordinary durable prop report. This is the
report's `calculations.history.totals.net`, including acquisition costs and
activation fees across all slots over that trial's full observed trade history.
It is distinct from backtest Net P&L in CU. The model normalizes native quantities
and chooses evaluation/funded sizes using the existing calculation contract.
All slots share one sequence, and training history influenced size selection.

Results CSVs append `historical_net`, `prop_analysis_id`, `prop_status` and
`prop_reason`. The `historical_net` numeric value lives in each result's `metrics`;
`prop_analysis` carries the report ID, status and unavailable/error reason. New
jobs capture `default_prop_profile`, `prop_unavailable_trials` and
`prop_error_trials`; the portal identifies calculation errors. Source-check
rejections, too-short/empty histories and zero validation passes show N/A with
an explanation, rather than zero profit. Operation errors remain errors and
are excluded from completed-trial reuse. Every successful backtest stays usable.

Only the coordinator opens the result databases. Worker prop artifacts publish
through the existing `data/prop_analyses` catalogue; there is no optimizer-only
prop store or duplicate Backtest. Both backtest and prop artifacts must verify
before trial reuse. Completed analyses are also reusable through the ordinary
configure/check/run path for identical source/settings. Standard counts are not
reduced, so new complete trials include the prop calculation's runtime. Existing
jobs retain their saved metric columns and CSV schema; start a new job to obtain
this objective for every trial. Earlier reports/evidence are preserved.

The new automatic workflow and independently calculated cash example are
reproduced in `docs/prop_simulation_review.md` under **Automatic default Apex
analysis**. Its actual source, native reports, CSVs, screenshots and saved
catalogues are under `artifacts/automatic-apex-prop-portal-20261027/` and the final
full-suite evidence directory. This is a synthetic software check, not a return
forecast.
