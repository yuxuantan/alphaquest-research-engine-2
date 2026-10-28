# Editable IS / OOS research workflow

Every new portal/API/CLI backtest or optimisation requires a chronological split.
Choose explicit inclusive dates in the saved source timezone, or an IS percentage
strictly between 0 and 100. Percentage mode assigns complete chronological trading
dates with floor(IS% × date count) dates to IS. Both windows must contain bars;
IS end must precede OOS start, and all dates must lie within the dataset.

Split settings remain editable after a run. The latest submitted split is a form
prefill for the next IS run. Editing any split input requires Review IS/OOS split
again. A new submission saves its own split snapshot; earlier reports and active
optimisation jobs retain their recorded dates, settings and results. Previously
viewed data is not made untouched by changing a split.

## Manual OOS execution

1. Select dataset, strategy, split and settings, review the split and run IS.
   Initial backtests, exhaustive grids and their automatic prop analyses use IS
   only. No OOS job is scheduled automatically.
2. Open a completed IS report, including an individual optimisation trial.
3. Select **Run OOS with these parameters** and confirm. The server uses that
   report's saved OOS window, parameters and execution costs, even if a later IS
   run changed the form's split. To change them, run a new IS backtest first.
4. Inspect the ordinary durable OOS backtest and its automatic prop report.
   Configure → check source → run can reopen the saved prop analysis or use new
   prop settings on this manually executed OOS source.

There is **no OOS attempt limit**. Failed/interrupted requests stay in execution
history and do not prevent new requests. A request UUID remains idempotent:
network retries return the same saved result/status instead of duplicating work.
Legacy reports and OOS reports cannot launch an OOS backtest; select completed IS.
Full-detail and risk replays remain IS actions; another OOS replay requires manual
selection from IS. Source identity and strategy implementation checks remain.

Research metadata and execution history use the existing backtest catalogue.
Existing datasets, report files and historical attempts are preserved. No migration
or reset is needed: old three-attempt histories cease to enforce any limit.
Legacy full-history prop sources outside the latest declared IS window require
an explicitly declared IS/OOS backtest; saved downloads remain readable.
The prop model's internal training/validation split stays inside the selected
research period and never reads OOS during an IS run.

## API and CLI

`POST /api/backtests` and `POST /api/optimizations` require `sample_split`:

```json
{"sample_split":{"mode":"percentage","is_percent":70}}
```

```json
{"sample_split":{"mode":"dates","is_start":"2020-01-01","is_end":"2023-12-31","oos_start":"2024-01-01","oos_end":"2025-12-31"}}
```

`GET /api/backtests/research-plan?dataset_id=...&strategy_id=...` returns the
latest submitted split, execution history and legacy report count. Compatibility
fields are `budget: null`, `remaining: null`, `exhausted: false`; `used` is a
history count only. Preview validates without running or saving a declaration.
`GET /api/backtests/{id}/oos` returns the selected report's own saved split.
`POST /api/backtests/{IS-id}/oos` accepts only `{"request_id":"<UUID>"}` and an
optional progress_id query UUID. Responses are 201 for completion, 200 for a saved
retry, 202 while running, or 409 for an invalid source or a failed/interrupted
request UUID. Start a new explicit request to retry a failed operation. It does
not accept parameter/date/cost overrides. CLI remains IS-only; use the saved IS
report/API for manual OOS execution. CLI split settings are editable on each run.

## Current qualification

See `docs/prop_simulation_review.md`, Editable declarations and manual unlimited
OOS (2026-10-29), for saved product evidence and exact reproduction steps.

## Historical qualification of the retired lock and three-attempt policy

The following records describe the former behavior and preserve earlier evidence.
They do not specify the current editable/unlimited policy above.

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
