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
   saved, use its existing library entry.
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

4. Enter these separate account/instrument/cost settings:

   | Field | Fixture value |
   | --- | ---: |
   | Initial capital | 10000 |
   | Tick size | 0.25 |
   | Monetary point value | 10 |
   | Adverse slippage, ticks per fill | 1 |
   | Commission, per contract per side | 1 |

   These are synthetic fixture settings, not specifications for NQ or another
   real instrument. Contracts is the number traded. Point value converts a
   1.0 price-point move into money **per contract**. Tick size and point value
   start blank and are never inferred from a filename or symbol. Monetary
   values stay as decimal strings when sent to the API.
5. Review **Timestamps label bar closes**. The saved timezone converts to UTC;
   signals and simulated fills use the same completed close with configured
   slippage. Holds measure elapsed time, including gaps.
6. Click **Start backtest**. Inputs, refresh, and the start button are disabled
   while the POST remains active. Progress displays preparation, replay, report
   saving, processed/total bars, and elapsed time. The seven-bar fixture may
   finish before an intermediate poll; larger runs show live replay progress.
7. On completion, inspect the run ID and the **Strategy parameters used** and
   **Execution settings used** sections. These values come from the saved
   backend response. The fixture should have green count 3, hold 20, contracts 2,
   and all five execution settings above. Full performance/trade/report screens
   remain a separate subtask.

The saved result for this fixture has net P&L 26 and final equity 10026. These
values can be checked in the API response; this screen deliberately focuses on
run configuration and saved-run confirmation.

## Check the submitted settings

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
`run_metadata.strategy.parameters`, and `execution_settings` should match the
request. `timestamp_convention` must be `bar_close`. The displayed run ID can
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
request; completed records remain available through the backend APIs.

## Browser checks

Optional browser tooling is separate from runtime dependencies; no frontend
framework or build step is added:

```bash
.venv/bin/python -m pip install -e '.[dev,browser]' -c requirements.lock
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest tests/test_backtests_browser.py -q
```

Real Chromium checks cover dataset and strategy selection, backend-defined
parameter changes, exact submitted configuration and saved settings, live
replay/saving progress, elapsed time, duplicate submission, client/server/network
errors, empty/loading states, mobile navigation, and the existing dataset
upload/preview/download/delete flow. Tests use isolated temporary databases and
owned local servers. The extra backend definition used to exercise strategy
switching exists only in the browser test response; production keeps its tested
allowlist.
