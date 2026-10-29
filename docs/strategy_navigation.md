# Strategy and dataset report browser

The sidebar contains Datasets and Strategies. Strategies opens a two-column
picker: strategy names on the left, then instruments and the full periods of the
datasets used by the selected strategy on the right. Saved run metrics are
requested only after selecting an instrument/dataset entry.

The dataset period is the original source's first/last timestamps converted to
its saved timezone, including dates outside IS. It is not the run's selected IS
period or the prop model's internal training/validation interval. For example,
UTC `2026-07-08T00:00:00Z` is July 7 in America/New_York. Different dataset contents
and source timezones remain distinct even when their instrument symbols match.
Reuploads of identical content/timezone/instrument share a saved group. New runs
capture full dataset metadata, and the disposable catalogue index retains it
when a source is deleted. A legacy source deleted before metadata capture shows
“Full dataset dates unavailable”; dates are never inferred from an IS run.

Selecting a dataset opens the saved-run table. Each primary row is a saved IS,
legacy or unpaired OOS report, retaining its exact strategy parameters. All
matching OOS attempts are available through a selector; the latest saved attempt
is the default for display/sorting. Pairing requires the explicit parent ID,
same strategy/dataset group, matching strategy source, parameters, execution
settings and research declaration. It never infers an OOS result by similar
parameters. Deleting a parent leaves its independently saved OOS reports visible
as OOS-only rows; undeclared historical reports are labeled legacy.

The table shows IS/OOS trading net P&L, drawdown, trades, win rate and Historical
net from the run's saved **default** prop analysis. Hover the prop link for its
recorded model. Later manual analyses remain available inside Configure prop
analysis; navigating does not replace the default or recalculate any result.
Parameters which vary across saved reports are highlighted; all parameters are
inspectable in each row. The parameter cell and table headers remain visible
while scrolling. Sort by metrics or any parameter, ascending/descending, with
unavailable values last. Run links open the exact saved report; Back to
Strategies returns to the selected dataset/run table. Listing and opening results
never submit an OOS test. OOS has no attempt limit and requires manual selection
from a completed IS report; split settings remain editable for each new IS run.

## Report deletion

Delete controls are available in the strategy run table, individual backtest
reports, saved prop-report lists and completed prop reports. Each deletion asks
for confirmation identifying the selected report. Backtest deletion keeps the
source dataset, saved prop analyses, optimization metrics and OOS attempts. Prop
report deletion removes that analysis and its downloads/calculation-reuse index;
it keeps backtest reports, datasets, optimization metrics and OOS attempts.
Execution history remains intact; there is no OOS attempt cap to reset.
Optimization results retain their recorded metrics and mark removed report links.

To remove a stale backtest, open Strategies → choose the strategy → choose its
instrument/dataset period. Use **Delete** beside the particular IS, OOS or legacy
report, or open it and select **Delete backtest**. Confirm the report ID shown.
To remove a stale prop result, open that completed result and select **Delete prop
report**, or use its Delete button in **Configure prop analysis → Saved analyses**.
Backtest and prop reports are deleted separately so either can be retained.

Queued/running prop analyses cannot be deleted. Backtest deletion is also blocked
while its source is in use or being replayed. Files are staged before catalogue
mutation, restored if the SQL transaction fails, and cleanup failures can be
retried by report ID. A symbolic-link report directory is rejected. Reading or
opening reports does not delete anything.

## API and compatibility

- `GET /api/strategies/library`: registered and saved historical strategies.
- `GET /api/strategies/{strategy_id}/datasets`: paged source groups.
- `GET /api/strategies/{strategy_id}/datasets/{group_id}/backtests`: paged saved
  IS/OOS rows, parameters and metric summaries. `sort=created_at_utc`,
  `sort=param.contracts`, or `sort=is.total_net_pnl` / `oos.total_net_pnl`, etc.;
  `direction=asc|desc`, `offset`, `limit` (maximum 100).
- Existing `DELETE /api/backtests/{run_id}` deletes one backtest report.
- `DELETE /api/prop-analyses/{id}` deletes one inactive prop analysis.

Old instrument-group API endpoints remain readable. Existing instrument-only
bookmarks resolve to the latest matching strategy/dataset where available.
`#backtests` and sweep URLs retain their compatibility readers and the shared
exhaustive parameter-grid form. Equal endpoints on every row run one backtest;
ranges run every combination, without a mode selector. The new hierarchy uses
`#strategies/{strategy_id}/datasets/{group_id}`. The lightweight `library_*`
tables are disposable indexes; authoritative reports, datasets and execution history
remain in their original stores. No new calculation engine or report store is
introduced.
