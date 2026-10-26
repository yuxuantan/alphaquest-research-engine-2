# Use and validate prop simulation setup

The product workflow is **completed backtest → configure prop simulation →
check source data → run simulation → results**. Configuration, saved setups and
source checking are available now. Account simulation and result analysis will
extend this same workflow. The **Run simulation** button explains why execution
is not yet available.

## Start the app

From the repository, using the existing environment:

```bash
.venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8000 --reload
```

Open **http://127.0.0.1:8000/#backtests**. Stop the server with **Ctrl+C** in
the terminal that launched it. Installation instructions are in
[README.md](../README.md#run).

## Use your completed backtest

1. Open **Backtests → Completed reports → your report → Set up prop simulation**.
   Confirm the source ID, dataset, strategy parameters, selected dates,
   execution assumptions and costs refer to the report you chose.
2. Choose the Apex 50K EOD platform, evaluation or funded starting phase,
   observation mode, fixed comparison quantity, explicit phase fee and UTC
   account/analysis bounds. Zero fees must be entered explicitly. Evaluation
   uses an attempt fee; funded uses an activation fee. Switching phase clears
   the fee so you can enter the appropriate amount.
3. Review applicable rules and the expandable source/evidence/assumption
   information. Rithmic/WealthCharts evaluation lock profit is 3,000; Tradovate
   evaluation has no lock. Funded lock profit is 100. Source retrieval dates are
   recorded review dates, not new checks of provider websites. The 5,999/6,000
   tier conflict stays disclosed. Effective dates remain unknown where null.
4. Explicitly declare the source symbol, source account currency, contract
   weight in rule units, a supporting HTTPS URL and the interpretation basis.
   The captured tick size and monetary point value are displayed and preserved.
   Currency and rule units are not inferred from the symbol. A report labeled
   CU requires an explicit interpretation; do not select USD without a basis.
5. Declare coverage for the full source session-date range shown on the form.
   Select **Weekday approximation** only if a recurring Monday–Friday window
   accurately describes your expected data and no holiday exceptions apply.
   Enter the first/last expected bar-close labels in **America/New_York** and
   cadence in seconds. Sunday evening labels belong to Monday. Weekends are
   explicitly closed under this policy. Coverage completeness is checked against
   your declared windows; it is not inferred from whichever bars happen to exist.
6. Choose **Explicit dates and windows** for holidays, early closes, multiple
   data windows or missing dates. Supply an ordered JSON array declaring every
   displayed source session date. For example:

   ```json
   [
     {
       "trading_date": "2026-01-05",
       "status": "covered",
       "windows": [
         {
           "first_utc": "2026-01-05T10:00:00Z",
           "last_utc": "2026-01-05T10:30:00Z",
           "bar_interval_seconds": 300
         }
       ]
     },
     {"trading_date": "2026-01-06", "status": "closed"},
     {"trading_date": "2026-01-07", "status": "missing"}
   ]
   ```

   Only use those example dates if they match your data. Covered windows have
   inclusive endpoints; closed/missing dates have no windows. An optional
   `close_time`, such as `"13:00"`, can declare an early New York close. A missing
   date is retained as missing and causes the source check to reject the input.
7. Enter your coverage basis, then click **Save setup**. A saved setup gets its
   own URL and retains a complete profile/settings/calendar snapshot. Download
   `profile.json`, `simulation.json`, `calendar.json` or `setup.json` as needed.
8. Click **Check source data**. The complete saved report is validated before
   any successful preview appears. A compatible check shows original and
   comparison quantities, source/scaled P&L, costs, covered zero-trade sessions,
   paginated session rows, and both observation streams. A rejection shows the
   actual reason and can be downloaded as `check.json`.

Compatibility concerns the source and setup only. The account rules have not
been applied. Trade-close samples use `equity.csv`; bar-close samples use the
full `report.json` equity series through bounded parsing. Trade-relative equity
changes are cumulative within each trade, not deltas to add across all bars.
Original absolute source equity is retained. Source net P&L already includes
commissions and adverse fill slippage; those costs are not charged again.

## Reproducible numerical check through the same workflow

Use the ordinary dataset and backtest screens to run this repository fixture.
It is synthetic data for checking arithmetic, not market-performance evidence.

1. In **Datasets**, upload
   [arithmetic_5m.csv](../tests/fixtures/backtest_contract/arithmetic_5m.csv).
   Name it **Synthetic arithmetic example**, set timezone **UTC**, symbol
   **TEST**, tick size **0.25**, and monetary point value **10**. Validate and save.
2. In **Backtests**, select that dataset and **Consecutive green hold**, with
   green-bar count **3**, holding minutes **20**, contracts **2**, initial capital
   **10,000**, slippage **1 tick per fill**, commission **1 per contract per
   side**, and blank date bounds. Run it and open its report. Expect gross P&L
   **30**, commissions **4**, net P&L **26**, and final source equity **10,026**.
3. Click **Set up prop simulation**. Select Rithmic, evaluation, bar close,
   comparison quantity **2**, attempt fee **0**, and keep the displayed UTC
   bounds. Declare symbol **TEST**, currency **USD**, rule weight **1**, source
   URL `https://example.com/explicit-test-units`, and basis **Synthetic test:
   prices are USD 10 per point, tick .25, one rule unit per fixture contract**.
   The example.com URL documents the test declaration only; it establishes no
   real-instrument contract equivalence.
4. Choose weekday approximation. Enter **05:00** through **05:30 New York**,
   cadence **300 seconds**, and coverage basis **Complete seven-bar synthetic
   fixture window on January 5, 2026**. These labels correspond to the file's
   UTC **10:00** through **10:30** timestamps. They are not a full exchange session.
5. **Save setup → Check source data**. Expect one covered session, seven source
   bars, one trade, original quantity **2**, comparison quantity **2**, gross
   **30**, commissions **4**, informational slippage **10**, net **26**.
   The bar-close preview has **7** observations. Switch its mode to trade close:
   expect **1** observation, net **26**, source final equity **10,026**.
6. Change comparison quantity to **1**. The prior compatibility result hides
   and **Check source data** becomes unavailable until you **Save new setup**.
   After saving/checking, expect gross **15**, commissions **2**, informational
   slippage **5**, and net **13**. Original quantity and source equity stay **2**
   and **10,026**. Informational slippage is already in fills, not another fee.
7. Reload. The saved setup and latest check should reappear. Return to the
   original backtest's setup entry and find both saved setups. Opening the first
   one must still show its original quantity and results. Changing only quantity
   preserves the profile hash but creates different simulation settings.
8. Change the declared last label to **05:35**, save another setup and check.
   Expect **rejected** with a coverage reason because the 05:35 bar is absent.
   This is missing coverage, not a zero-trade bar/session.

For an entirely flat run using the same file, set the strategy's green-bar count
to **100** and run normally. A source check with the same coverage should show
one covered session with seven bars, zero trades, zero net P&L and no invented
original source quantity. Trade-close preview is empty; bar-close has seven flat
observations. On multi-session sources, every covered zero-trade session remains.

## Deliverables by subtask

| Subtask | Final-product increment | User validation |
| --- | --- | --- |
| 1. Specification | [Implementation contract](prop_simulation.md) and relevant workflow help | Read phase/observation/calendar/cost scope and compare it with form behavior; no artificial design-checking page |
| 2. Rules/configuration | Actual report action, phase/platform setup, immutable saved snapshots, re-open/download | Switch platform/phase, save/reload, verify captured settings and phase fees, retain older setups |
| 3. Saved-input adapter | Real source compatibility, sessions, both observation previews and JSON/CSV exports | Reconcile source versus scaled quantities/P&L/costs, inspect zero-trade sessions, try an intentionally incorrect coverage declaration |

The specification separately documents notebook defects, incorporate/correct/
defer decisions, future engine boundaries and acceptance examples. Measured
excursions, variable source sizing and overnight exposure remain unsupported.
Source checks reject incompatible units, missing coverage, variable quantities,
session-crossing exposure and irreconcilable artifacts without changing source
backtests. No measured MAE/MFE or account result is fabricated.

## Storage and verification

Setups and immutable input checks use `data/prop_runs/` and
`data/prop_simulations.sqlite3` by default, following `ALPHAQUEST_DATA_DIR` if set.
Each new save creates a separate setup; checks reference the captured setup.
Source previews are staged incrementally into SQLite/CSV and paged at 50 rows
in the UI (100 maximum per API request). The user's original dataset and backtest
artifacts are unchanged. Old `prop_reviews/` files remain as historical evidence;
the dedicated review page, API and fixture generator have been retired.

Run the configuration, adapter, real API and Chromium workflow checks:

```bash
.venv/bin/python -m pytest -q tests/test_prop_configuration.py tests/test_prop_sessions.py tests/test_prop_api.py tests/test_prop_browser.py
```

Browser prerequisites, when not already installed:

```bash
.venv/bin/python -m pip install -e '.[dev,browser]' -c requirements.lock
.venv/bin/python -m playwright install chromium
```

Tests cover immutable settings after template edits and process restart,
normalized costs once, input rejection, coverage, Sunday/DST session boundaries,
zero-trade sessions, both previews, pagination/exports, mobile layout, and visible
request failure/retry behavior. Test web servers stop automatically.

Every future implementation must deliver a usable increment in this same final
workflow, inspectable actual outputs, and exact reproduction/check steps with
independent expectations. Tests supplement the product demonstration. Do not
introduce a separate page, API or storage solely to demonstrate a subtask.
