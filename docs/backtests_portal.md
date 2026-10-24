# Backtests screen review

Start the existing local server from this checkout:

```bash
.venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/` and select **Backtests**, or go directly to
`http://127.0.0.1:8000/#backtests`. Mobile navigation is in the top bar.

## Run the arithmetic fixture

1. In **Datasets**, choose `tests/fixtures/backtest_contract/arithmetic_5m.csv`.
   Keep the source timezone **UTC**, validate the CSV, then save it. If already
   saved, use its existing library entry. Open the dataset, set **Tick size 0.25** and **Monetary point value 10**, then click **Save instrument settings**. These values may also be supplied during upload.
2. Open **Backtests** and select that saved dataset. Its seven bars, filename,
   UTC range, and saved source timezone appear beneath the controls.
3. Select **Consecutive green hold**. This is selected automatically when it is
   the only available strategy. Read its description. Exactly three strategy
   fields come from the backend definitions:

   | Field | Fixture value |
   | --- | ---: |
   | Green bar count | 3 |
   | Hold minutes | 20 |
   | Number of contracts | 2 |

4. Check **Tick size for this run** and **Monetary point value for this run**. They start at the dataset defaults (**0.25** and **10** for this fixture). You may edit either for this run, or click **Reset to dataset defaults**. Then enter these account/cost settings:

   | Field | Fixture value |
   | --- | ---: |
   | Initial capital | 10000 |
   | Adverse slippage, ticks per fill | 1 |
   | Commission, per contract per side | 1 |

   These are synthetic fixture settings, not specifications for NQ or another
   real instrument. Contracts is the number traded. Point value converts a
   1.0 price-point move into money **per contract**. Tick size and point value
   are saved as defaults in Datasets and editable for each run in Backtests. Run
   edits leave dataset defaults unchanged. Switching datasets loads the new
   dataset’s defaults; navigation and Refresh choices preserve edits for the same
   dataset. They are never inferred from a filename or symbol. A dataset without settings cannot start a backtest.
   Monetary values stay as decimal strings when sent to the API.
5. Review **Timestamps label bar closes**. The saved timezone converts to UTC;
   signals and simulated fills use the same completed close with configured
   slippage. Holds measure elapsed time, including gaps.
6. Click **Start backtest**. Inputs, refresh, and the start button are disabled
   while the POST remains active. Progress displays preparation, replay, report
   saving, processed/total bars, and elapsed time. The seven-bar fixture may
   finish before an intermediate poll; larger runs show live replay progress.
7. The completed report opens automatically. Check net P&L **26**, gross P&L
   **30**, commissions **4**, **1** trade, **100%** win rate, final equity
   **10026**, entry fill **100.25**, and exit fill **101.75**. Expand **Dataset,
   strategy & settings used** to inspect the saved parameters, costs, dataset
   and source hashes, timezone, and timestamp convention.
8. Hover over the equity chart or focus it and use arrow keys. It shows only
   **10000 → 10026**: the initial balance and equity after the one completed
   trade, including all costs. No entry-bar or open-position fluctuations are
   plotted. Values use synthetic currency units **CU**; no currency code is
   stored or inferred.
9. Download both CSVs. Equity CSV retains the previously reviewed format:
   initial equity plus equity after each completed trade. The chart uses the
   same values and excludes unrealized P&L while a position is open.
10. Refresh: the report URL `/#backtests/report/RUN_ID` reopens the saved run.
    Return to **Backtests**, find it in **Completed reports**, and reopen it.
    History is paginated, 25 reports at a time. Reports remain available after
    the original dataset is deleted.

Reports also show **Max drawdown (CU)**, **Max drawdown (%)**, and **Max drawdown
duration**. These use every post-cost trade-close equity value, including initial
capital, and exclude open-position fluctuations. Amount and percentage are
maximized independently; percentage uses the corresponding prior peak. Duration
is the longest elapsed UTC time from a peak to recovery, or dataset end when
unrecovered (initial capital uses the first bar's timestamp). The arithmetic,
no-pyramiding and zero-trade fixtures show **0 / 0% / 0s**. The `end_of_data`
fixture shows **20 CU / 0.2% / 4m**; `last_bar_entry` shows
**14 CU / 0.14% / 2m**. Existing saved reports gain these metrics on first access
without rerunning trades; the enriched catalogue is retained across restarts.

The trade table displays entry/exit times in each run's saved dataset source
timezone, with that timezone in both column headers. Trade-close equity tooltips
use the same timezone. Date and daylight-saving conversions follow the saved
IANA zone, independent of the browser's local timezone. Hover over a trade time
to inspect its stored UTC value. API results and CSV exports retain UTC timestamps;
fills, P&L and elapsed holding times are unchanged. Older reports use their saved
source timezone when reopened; no backtest rerun is required.

## Check the submitted settings

To replay a subset, set **From date** and/or **To date** beneath the dataset
selector. Both include the entire date in the displayed saved source timezone;
they are not browser-timezone or UTC date boundaries. Leave one blank for an
open end or both blank for the full dataset. Invalid reversed dates are blocked
before submission; a range with no bars shows a server error and saves no run.

The strategy starts with fresh signal/indicator state on the first selected bar,
and its end-of-data policy applies to the last selected bar. Progress counts only
selected bars once preparation finishes. Report settings show requested dates,
**Bars used**, **Source dataset bars**, original source rows and actual replay
timestamps in UTC. These settings survive report reopening. The source CSV and
its metadata are unchanged, and existing reports remain viewable.

CLI runs accept the same optional `--from-date YYYY-MM-DD` and
`--to-date YYYY-MM-DD` flags.

Open browser developer tools and select **Network** before starting the run.
Filter for `api/backtests` and inspect the POST's request payload:

```json
{
  "dataset_id": "YOUR_SAVED_DATASET_ID",
  "strategy_id": "consecutive_green_hold",
  "strategy_parameters": {"green_bar_count": 3, "hold_minutes": 20, "contracts": 2},
  "execution_settings": {
    "initial_capital": "10000", "tick_size": "0.25", "point_value": "10",
    "slippage_ticks": 1, "commission_per_contract_per_side": "1"
  }
}
```

The strategy parameters and slippage ticks are integers. All monetary inputs
are strings, preserving their entered precision. The response must be HTTP 201
with `status="complete"`. Its `run_metadata.dataset.id`,
`run_metadata.strategy.parameters` and the capital/cost settings should match the
request. The response’s `execution_settings` contains the actual tick size and
point value used. `run_metadata.dataset.instrument_settings` retains the captured
dataset defaults, and `run_metadata.instrument_overrides` identifies values that
differ numerically from those defaults. Expand the report settings to inspect
**Instrument overrides**. The untouched fixture should show **None (dataset
defaults)**. As a separate check, overriding tick size to **0.5** and point value
to **20** should yield net P&L **36** (gross **40**, commissions **4**) while the
dataset keeps defaults **0.25** and **10**. Refresh the completed report and check
the same overrides remain recorded.
Editing those dataset settings affects future runs only; completed reports keep
the settings captured when they started. `timestamp_convention` must be `bar_close`. The displayed run ID can
also be retrieved with `GET /api/backtests/RUN_ID`.

During a longer run, the Network panel should show one backtest POST and
separate `/api/progress/UUID` polls. Repeated clicks or form-submit events while
that POST is active cannot send another run. The button remains disabled during
report saving even when the bar count reaches its total.

## Existing behavior and errors

Dataset upload, validation, source-timezone selection, previews, saving,
downloads, and deletion remain on the Datasets screen. Switching screens keeps
the current backtest inputs. Entering Backtests refreshes dataset/strategy
choices; **Refresh choices** can also pick up changes from another tab. Legacy
unsupported schemas are shown as unavailable for backtesting.

Client validation identifies missing/invalid values before submitting. Server
validation and execution errors appear in an alert, with field details when the
API supplies them. Choice-loading errors can be retried with **Refresh choices**.
Temporary progress-poll failures do not turn the run into a failure; the active
POST still determines the result. A lost run connection is shown as unconfirmed
and is never retried automatically. Reloading the page does not resume a pending
request; completed records remain available in **Completed reports**.

## Browser checks

Optional browser tooling is separate from runtime dependencies; no frontend
framework or build step is added:

```bash
.venv/bin/python -m pip install -e '.[dev,browser]' -c requirements.lock
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest tests/test_backtests_browser.py tests/test_reports_browser.py tests/test_report_screen_api.py -q
```

Real Chromium checks cover dataset and strategy selection, backend-defined
parameter changes, exact submitted configuration and saved settings, live
replay/saving progress, elapsed time, duplicate submission, client/server/network
errors, empty/loading states, mobile navigation, and the existing dataset
upload/preview/download/delete flow. Tests use isolated temporary databases and
owned local servers. The extra backend definition used to exercise strategy
switching exists only in the browser test response; production keeps its tested
allowlist.

## Repeatable report review and screenshots

```bash
.venv/bin/python tests/review_report_portal.py --output artifacts/report-screen-review-new
```

Use a new output directory. The command owns and stops its preview server,
saves isolated datasets and completed reports, drives all nine reviewed fixtures
through Chromium, compares every trade and trade-close equity point, tests CSV downloads
and refreshing/reopening, and retains screenshots and `verification.json`.
It also runs a 20,002-bar synthetic dataset: 10,001 breakeven trades, net P&L 0,
final equity 10000, no more than 1,000 browser chart points, and 50 trades per
table page. The automated browser suite separately pauses replay to check live
progress and server responsiveness deterministically, and checks dataset
upload/validation/download/deletion and history/error states.

Open the retained data for manual review (replace the path if needed):

```bash
ALPHAQUEST_DATA_DIR="$PWD/artifacts/report-screen-review-new" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8000
```

The chart requests at most 1,000 records. The server streams the saved
trade-close equity CSV and retains endpoints plus chronological minimum/maximum
equity per equal trade-count bucket. This preserves bucket extremes but
connecting lines omit intermediate trades. X spacing is by completed trade
count; hover timestamps use the dataset's saved source timezone. A zero-trade run shows only its
initial balance. The two-trade no-pyramiding fixture shows exactly
**10000 → 10020 → 10040**. Exact Decimal strings supply all table values, metrics and downloads;
only SVG geometry and approximate axis tick labels use browser floating point.
No metric is computed from sampled data. The full-resolution results and CSVs
are unchanged, and earlier saved portal runs can be opened without rerunning.
