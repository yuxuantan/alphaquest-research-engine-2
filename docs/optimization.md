# Exhaustive optimization

Open **Optimizations** in the portal (`/#optimizations`). It shares the normal
Backtests configuration: select a saved dataset and strategy, optionally choose
inclusive source-timezone dates, review instrument settings, and enter capital,
slippage and commissions. Account and execution settings are fixed across trials;
every strategy parameter has **Start value**, **End value**, **Step** and
**Step count** columns.

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

**Start optimization** runs the Cartesian product in definition order. The portal
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
dataset. Optimization remains disabled until valid worker options load;
ordinary backtests remain usable. An older backend without this endpoint shows
a specific restart message. Reloading the portal fetches matching, current
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
coordinator publishes full backtests and optimization rows through the existing
run store. Child processes never open or write the dataset/results databases.
Only small manifests and progress messages cross process boundaries; full report
arrays stay on disk. One disk snapshot supplies the same original CSV
bytes to all trials, with the saved byte count/hash checked by the normal reader.
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
down the page through the table. Horizontal scrolling keeps each header aligned
with its values. Parameters with more than one generated value appear first,
before Trial, and remain frozen on the left during horizontal scrolling. They
have highlighted headers and cells, a **Varies** badge, and a legend above the table. Fixed
parameters and metrics keep their normal appearance. A range that generates
only one value (for example, 1 through 2 with step 5) is treated as fixed.
The highlight uses the whole saved grid, so it remains consistent across sort
orders, result pages and reopened reports. Existing saved jobs gain this display
on refresh without rerunning any backtests.

To reproduce the table review, use the synthetic arithmetic dataset below with
green bar count **3 / 3 / 0**, hold minutes **20 / 25 / 5**, and contracts
**1 / 30 / 1** (start / end / step), using one worker. Expect **60** saved trials
across two result pages. **Hold minutes** and **Contracts** are highlighted and
marked **Varies** and occupy the first two columns, followed by **Trial** and
**Green bar count**. Fixed parameters and metric columns are plain. Scroll the
page until the table's top moves above the viewport, then scroll within the
table and horizontally. The header remains visible and aligned; **Hold minutes**
and **Contracts** stay in place while the other columns scroll underneath. Sorting,
switching to the ten-row second page, and reloading retain the same highlights.
Desktop/mobile screenshots, measured frozen column positions before/after a
600px horizontal scroll, and actual reports are retained under
`artifacts/optimization-frozen-columns-review-20261027-verified/`. Earlier header
review evidence remains under `artifacts/optimization-table-review-20261027-verified/`.
Repeat the browser
check in a new evidence directory with:

```bash
.venv/bin/python -m pytest tests/test_optimization_browser.py -k 'headers_stay_visible or single_generated' -q --basetemp artifacts/optimization-frozen-columns-review-NEW
```

Use a new `--basetemp` directory to preserve earlier evidence. These checks own
and stop their temporary servers and retain the isolated normal reports.
The normal portal review also passed with the frozen column order: all 18
headings sorted both ways, CSV order and report links matched, and reopening
worked on desktop/mobile. Its outputs are saved separately under
`artifacts/optimization-frozen-columns-sort-review-20261027/`.

Sorting applies to all saved trials before pagination (50 rows per page), with
exact Decimal comparisons rather than lexical or floating-point money order.
Missing win rates from zero-trade runs display N/A and sort last in both directions;
equal values retain trial order. Trial numbers always identify the same Cartesian
parameter set, regardless of finish order. Finished trials appear immediately,
even if earlier trial numbers are still running. CSV/page snapshots follow
publication order internally so late completions cannot shift or duplicate rows.
Each row links to its full saved Backtest report,
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
