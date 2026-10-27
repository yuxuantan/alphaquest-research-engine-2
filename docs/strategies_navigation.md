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
