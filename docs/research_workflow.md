# Declared IS / OOS research workflow

Every new portal/API or CLI backtest requires a chronological split before it
runs. Single parameter sets and exhaustive grids share this requirement. Dates
are inclusive in the dataset's saved source timezone, with `IS start <= IS end
< OOS start <= OOS end`. Both periods must contain bars and lie within the source.
Gaps outside the two declared windows are excluded. There is no cross-period
indicator warm-up; positions close at the selected period's final bar.

Choose explicit IS start/end and OOS start/end dates, or an IS percentage strictly
between 0 and 100. The portal fills OOS % as `100 - IS %`. Percentage mode counts
observed trading dates, sorts them chronologically, and assigns
`floor(IS% * distinct date count / 100)` complete dates to IS and the remaining
complete dates to OOS. It does not randomly shuffle or split a trading date.
At least two dates are required. The review displays the resolved dates and
actual bar counts; unequal bars per date mean bar percentages may differ.

Reviewing a split does not lock it or spend an OOS attempt. The first accepted IS
submission permanently locks the resolved split for that strategy and source CSV
SHA-256. Equivalent explicit/percentage declarations resolve to the same plan.
Later IS requests cannot move OOS dates into IS, change the holdout, or use old
`from_date` / `to_date` fields. The standard CLI has the same restriction. The
source date index inspects dates/counts only, without evaluating OOS performance.
The actual replay and all prop calculations receive only the chosen period.

## Running and inspecting results

1. Open Strategies -> New backtest. Select the dataset and strategy.
2. Choose a split method, complete its inputs and click Review IS/OOS split.
   Initial execution remains disabled until the review succeeds.
3. Select a single parameter set or an exhaustive sweep and run. Every result
   is labelled IS, including the default Apex 50K EOD analysis with activation
   fees. The batch summary states the held-out period. No OOS job is scheduled.
4. Open a saved IS report, including an individual trial from a sorted batch.
   Inspect its parameters, execution costs, IS results and remaining OOS budget.
5. Click Run OOS with these parameters and explicitly confirm. The server copies
   the saved strategy parameters and execution settings; the request cannot
   substitute either. It runs one ordinary backtest and the default Apex analysis
   on the locked OOS dates and saves a normal durable OOS report.
6. Reopen that report or use Open saved OOS report from its IS parent. Saved
   metrics, source checks, charts and original downloads remain available without
   a new OOS replay. Configure -> check -> run can reopen the same verified prop
   calculation for the same saved trade source.

The hardcoded budget is **3 attempted OOS tests per strategy ID and source CSV
SHA-256**, across all parameters, IS reports, batches and sessions. Each attempt
is reserved in one SQLite transaction *before* computation. Concurrent requests
cannot exceed three. Failed and interrupted attempts remain counted. A client
request UUID makes a network retry idempotent: it returns the existing report or
attempt, rather than spending another slot. A genuinely new attempt needs a new
UUID and explicit selection. The fourth request gets HTTP 409; the portal warns
that the budget is exhausted and disables OOS execution. IS research still works.

Budget and plan records use the existing backtest catalogue, with no deletion
cascade. Deleting a report, deleting/re-uploading identical CSV bytes, changing
costs/parameters, updating code or restarting cannot reset the budget. Another
strategy has its own budget. This is an application-level limit, not protection
against an operator editing the SQLite database or deliberately altering source
CSV bytes to create a different source identity.

OOS reports cannot trigger a sweep or another OOS action. Generating per-bar
full detail is available for declared IS reports only, so the detail endpoint
cannot silently replay held-out data outside the budget. An OOS report retains
all trades, metrics and trade-close equity in its normal compact report.
The manual prop check/submit endpoints can reopen the verified automatic OOS
analysis with exactly its recorded source and settings. Changed settings/exports,
missing/corrupt artifacts or fresh OOS prop calculations are blocked (HTTP 409);
select another budgeted OOS attempt from IS instead. Viewing original saved
downloads remains available. This closes a separate prop-only tuning bypass.

Historical reports are preserved unchanged and labelled Legacy. They cannot
launch OOS tests or full-detail replays. A historical optimisation without a
split can be read/downloaded but cannot resume under the new policy. Legacy
reports for a strategy/source are disclosed in the declaration/budget display:
previously viewed data cannot become an untouched holdout simply by declaring a
new split. Historical exposures are not fabricated as newly budgeted attempts. Once a plan
is locked, fresh manual prop calculations on a legacy report containing data
outside its IS window are also blocked; that report cannot become a prop-only
holdout tuning bypass. Original saved reports and downloads remain readable.

The prop model's own training/validation split remains internal to the selected
IS or OOS trade source. It never reads the research holdout during an IS run.
Its reported Historical net describes the selected period only. Standard model,
fees, counts, close-only excursion disclosure and account arithmetic are unchanged.

## API and CLI

`POST /api/backtests` requires `sample_split` on both request shapes. The existing
`POST /api/optimizations` alias enforces the same policy. Examples:

```json
{"sample_split":{"mode":"percentage","is_percent":70}}
```

```json
{"sample_split":{"mode":"dates","is_start":"2020-01-01","is_end":"2023-12-31","oos_start":"2024-01-01","oos_end":"2025-12-31"}}
```

`GET /api/backtests/research-plan?dataset_id=...&strategy_id=...` returns the
locked plan, used/remaining budget, attempt statuses and legacy report count.
`POST /api/backtests/research-plan/preview` takes those IDs and `sample_split`,
and returns `proposed_plan` without locking or running a calculation.
`GET /api/backtests/{IS-or-OOS-id}/oos` returns its plan and budget.
`POST /api/backtests/{IS-id}/oos` takes only `{"request_id":"<UUID>"}` plus an
optional `progress_id` query UUID. It returns 201 on completion, 200 for a saved
idempotent retry, 202 for an already-running attempt, or 409 for an exhausted
budget, disallowed source or previously failed/interrupted request. Extra
parameter/date/cost fields are rejected. Poll normal `/api/progress/{id}` during
execution. A changed strategy implementation or missing/mismatched source is
rejected before reserving an attempt.

CLI: add `--is-percent 70` or all four `--is-start`, `--is-end`, `--oos-start`,
`--oos-end` flags to the normal CLI command. CLI execution is IS only; use the
saved IS report/API for an explicitly budgeted OOS selection.

## Reproducible qualification

Run from a fresh artifact path (never overwrite prior saved evidence):

```bash
PYTHONPATH=. python -m pytest -q tests/test_research_workflow.py \
  tests/test_research_browser.py --basetemp artifacts/research-review-NEW
```

`artifacts/is-oos-20261028/browser-01/` contains actual browser outputs. In
`test_percentage_is_sweep_selec0/`, the labelled synthetic CSV has 120 weekdays,
three bars per weekday, one contract and no trading costs. The 50/50 split gives
60 trades and 180,000 CU net separately in each period. Independent default prop
expectation in each period: 360,000 payouts - 7,120 evaluation/activation fees =
352,880 Historical net, with normal simulation counts. Both native source checks,
IS/OOS report JSON, prop downloads, cash screenshots, batch rows and source-bound
budget are saved. The configured prop analysis reopens without recomputation.

The explicit-date browser case uses two weekdays. Each period has exactly one
trade earning (103 - 100) * 10 = 30 CU. Its prop source is correctly incompatible
because each period has only one session weekday. It confirms cancellation spends
nothing, three attempts exhaust the shared budget, the fourth request is blocked,
and IS remains available. Unit/API cases independently cover chronology, empty
windows, invalid/missing declarations, concurrent requests, duplicate UUIDs,
parameter freezing, deletion/re-upload, recovery and failed attempts.

Existing fill/report fixture oracles retain every original source row as IS and
append a labelled synthetic reserved date through `tests/research_fixtures.py`.
There is no production bypass or reduced simulation count. New research checks
use ordinary clients and genuine multi-date sources. Browser fixture servers stop
through their normal cleanup; no additional persistent demo server is needed.

Final qualification against code commit `bafa7b0`: **801 checks passed**, with no
failures/errors/skips (24 existing dependency/notebook warnings). The complete
log and JUnit record are `artifacts/is-oos-20261028/final-suite.log` and
`final-suite.xml`. The final product journey, original reports, source checks,
downloads and budget proof are in `final-suite/test_percentage_is_sweep_selec0/`;
the exhaustion/cancellation proof is in `final-suite/test_explicit_dates_required_b0/`.
`qualification.json` records the independent per-period values and immutable code
commit. The running checkout retains its own read-only live verification and
before/after preservation evidence under `artifacts/is-oos-20261028/`.
