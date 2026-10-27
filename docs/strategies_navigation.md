# Strategies navigation

The main and mobile navigation contain Datasets and Strategies. Strategies opens
two equal desktop panes: unique instruments on the left and saved backtest
summaries on the right. The right pane waits for an instrument selection. Dates
appear in each backtest summary and do not split instrument groups. On narrow
screens the panes stack and the result table scrolls inside its own panel.

Each summary includes strategy, dataset, selected date range/timezone, net P&L,
trade count, drawdown and default prop Historical net. CU and USD are labelled
separately; unavailable values remain N/A. The arrow opens the normal durable
backtest report, including the existing configure/check/run prop workflow.
Sweep trials are ordinary backtests in the same instrument group.

The library uses the existing backtest catalogue and an expendable instrument
index. It never rewrites saved report files. New reports capture the instrument
symbol. Historical reports use their saved symbol or the surviving source
metadata; if identity is unavailable they are labelled Unspecified and separated
by original dataset, rather than guessing a ticker. Source deletion retains
indexed history; deleting a backtest removes its index entry through the normal
catalogue transaction. Instrument and result pages are bounded (50/25 rows).

`GET /api/strategies/groups` lists groups; append `/{id}/backtests` for summaries.
Both accept offset/limit. Unknown groups return 404; invalid limits return 422.

Inspect `artifacts/strategies-navigation/02-library-reviewed/` for screenshots,
saved actual reports and verification. The labelled synthetic MNQ source gives
one standalone report with net 13 CU and a three-trial sweep with net 13/26/39
CU, all four in the same MNQ group. This source has one session, so prop source
checking correctly leaves Historical net unavailable. Browser checks verify lazy
selection, two equal halves, report opening, reload, and a 390px mobile viewport.
API checks verify pagination, old metadata, source deletion, backtest deletion,
exact financial summaries and unchanged report hashes. Reproduce:

```bash
PYTHONPATH=. python -m pytest -q tests/test_strategy_library.py \
  tests/test_strategies_browser.py --basetemp artifacts/strategies-library-NEW
```

## Shared execution form

Use **Strategies → New backtest**, then choose **Single parameter set** or
**Parameter sweep · exhaustive** in Backtest mode. The selected dataset, strategy,
dates, capital, costs and both sets of parameter drafts stay in the same form.
A single set opens its normal report. A sweep opens the ordinary batch results
with sortable metrics, highlighted/frozen varying parameters, CSV export and a
report icon for each trial. Both creation modes POST to `/api/backtests`.
**Backtest activity** reopens queued, running, interrupted and completed batches.
Batch progress/results use `/api/backtests/batches/{id}`; old optimization URLs
and API aliases reopen the same records. Deleting a report returns to Strategies.

`03-shared-form/` retains actual shared-form and result screenshots plus request
payloads in `test_one_form_and_endpoint_run0/shared-form-verification.json`.
Independently expected one-contract net is 13 CU; contracts 1/2/3 give 13/26/39 CU.
The browser verifies both POST payloads use identical execution settings, mode
changes preserve drafts/capital, and the old saved job link reads the same job.
37 form/sweep/browser checks passed, including worker loading/retry, exact decimal
ranges, boolean ranges, sorting, frozen columns, resumption and mobile layout.

## Qualification and branch scope

The branch starts at remote main `976fdc1`; it contains only this request's API,
library and shared-form commits. Earlier unpublished runtime improvements stay
on their original branch and checkout. The isolated checkout is
`/Users/yx/alphaquest-research-engine-2-navigation`. No persistent preview server
is started. The original application and its datasets/results are preserved.

The broader product check passed 30 checks and exposed two stale assertions for
old return links; the correction run passed all nine selected checks, including
both cases, shared submission and selection-error recovery. Exact historical cash
and saved downloads are checked in the existing normal workflow. Full final
qualification is saved as `artifacts/strategies-navigation/full-suite.log` and
`08-full-suite-final/junit.xml`. Reproduce from the branch using a new artifact path:

```bash
PYTHONPATH=. python -m pytest -q --basetemp artifacts/strategies-full-NEW \
  --junitxml artifacts/strategies-full-NEW/junit.xml
```

The initial full run stopped after 73 passes on an obsolete six-bundle count.
The asset test now checks all script/style references share the same content
version, including the new Strategies module; all 18 asset/API checks passed.
The stopped-run evidence is retained in `06-full-suite/` and
`full-suite-initial.log`; the final full-suite log above records the complete
qualification against the committed branch.
