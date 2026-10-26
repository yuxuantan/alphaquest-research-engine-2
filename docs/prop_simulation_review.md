# Use and validate prop simulation setup

The product workflow is **completed backtest → configure prop simulation →
check source data → run simulation → results**. Configuration, saved setups,
source checking and historical evaluation execution are available now. Funded
execution and Monte Carlo remain unavailable and will extend this same workflow.

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
   observation mode, fixed comparison quantity and UTC account/analysis bounds.
   Choose either **49 evaluation + 129 activation** or **109 evaluation / no
   activation fee**, available for each platform. These USD defaults were supplied
   by the user on 2026-10-26; they are not independently verified official prices.
   The selected profile supplies the phase fee automatically: evaluation uses
   its attempt fee; funded uses its activation fee. Under **Edit reusable account
   profile fees**, edit your defaults if needed and click **Save profile fees**. Defaults
   persist across setups and app restarts, separately for each platform. Leave
   an unknown phase blank; zero must be explicitly configured. No official price
   is guessed. For a discount or specific purchase price, enable **Override the
   profile fee for this simulation**. Changing phase/platform resets the override
   and uses that selection's default.
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

After a compatible source check, **Run simulation** executes an evaluation and
opens its durable result. It revalidates all source artifacts and their identity;
changed bytes require a new source check. The result shows outcome/reason,
balance/equity, trailing floor/high-water, suspensions, trade counts, fees,
a saved-trace chart and paginated events. Download `report.json`, `events.csv`
and source/config/profile/calendar snapshots. Return to the setup to reopen
its saved results. Reload reads saved data without re-executing the account.

Historical evaluation currently requires the first declared session open as
account start and a declared session reset as analysis end. Defaults already
satisfy this rule. End may select a complete prefix of the source calendar;
later source trades are not reached. Partial sessions, pre-purchase access and
uncovered future end dates are rejected. Closed dates still advance clocks.
An active account at the historical end is `unresolved_data_end`, without
inventing future sessions to reach expiration.

Compatibility concerns source coverage and normalization. Execution additionally
checks account contract limits and temporal bounds. Invalid inputs, storage
errors and failed reconciliation are operation errors, not financial losses;
no completed result is published for those failures.

Trade-close samples use `equity.csv`; bar-close samples use the
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
   comparison quantity **2**, enable the simulation fee override and enter **0**,
   and keep the displayed UTC
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
   Click **Run simulation**. Expect `unresolved_data_end`, account balance and
   equity **50,026**, high-water **50,026**, floor **48,026**, one processed/
   completed trade, no suspension, forced exit or skipped trade, and modeled
   net cash **0** for the explicitly supplied zero fee. Source capital **10,000**
   is a baseline to remove, not cash added to the prop account. Use
   **Back to saved setup** to continue.
6. Change comparison quantity to **1**. The prior compatibility result hides
   and **Check source data** becomes unavailable until you **Save new setup**.
   After saving/checking, expect gross **15**, commissions **2**, informational
   slippage **5**, and net **13**. Original quantity and source equity stay **2**
   and **10,026**. Informational slippage is already in fills, not another fee.
   **Run simulation** from the new setup. Expect `unresolved_data_end`, account
   balance/equity **50,013** and floor **48,013**. Return to the setup.
7. Reload. The saved setup and latest check should reappear. Return to the
   original backtest's setup entry and find both saved setups. Opening the first
   one must still show its original quantity and saved **50,026** result.
   Changing only quantity
   preserves the profile hash but creates different simulation settings.
8. Change the declared last label to **05:35**, save another setup and check.
   Expect **rejected** with a coverage reason because the 05:35 bar is absent.
   This is missing coverage, not a zero-trade bar/session.

Optional rejection check: with correct coverage, save comparison quantity **7**
at rule weight **1**. Source normalization can pass, but **Run simulation** must
reject the operation for exceeding the evaluation's six rule units. No completed
result or `failed_drawdown` account is saved. With an explicit attempt fee of
**35**, the valid quantity-2 example still ends at balance **50,026**; external
costs are **35**, receipts **0**, and modeled net cash **−35**. Fees do not
modify account trading P&L or balance.

## Validate reusable profile fees through the product

Use the synthetic arithmetic source and instrument/calendar declarations above.
The following **35/140/49/150 are test prices, not Apex price claims**. Changing
profile fees affects other future setups using that platform; record and restore
your own defaults after this check if necessary.

1. Open the arithmetic report's **Set up prop simulation** action. Select
   **Rithmic → Evaluation**. Expand **Edit reusable account profile fees**, set
   evaluation attempt fee **35** and funded activation fee **140**, and click
   **Save profile fees**. Expect **35 USD from the selected profile**, with the
   simulation override unchecked and its amount input hidden.
2. Complete the instrument/coverage fields as above, using quantity **2**. Save
   the setup, check source data, then run. Expect `unresolved_data_end`, balance
   and equity **50,026**, external fees **35**, receipts **0**, net cash **−35**.
   Download `report.json`: `resolved.rules.profile.fee_defaults.attempt_fee`
   resolves to 35, `config.fees.attempt_fee` resolves to 35, and
   `config.fees.origin` is `profile_default` (the config is under `resolved`).
3. Return to the saved setup and change profile defaults to **49/150**. Click
   **Save profile fees → Save new setup**. The new setup captures **49**.
   Reopen the earlier result: it still shows **35** in external fees, balance
   **50,026**, net cash **−35**, and its original hashes/downloads. Reopening an
   earlier setup likewise displays its captured profile, not today's defaults.
4. Return to the report and create a fresh setup. Expect **49 USD** automatically.
   Switch to funded: expect **150 USD**, without an evaluation fee. Switch back
   to evaluation: expect **49 USD**. Funded execution remains unavailable.
5. Enable the simulation override, enter **0**, save and reload. The override
   remains zero, while the reusable profile still has **49/150**. Its downloaded
   config records `fees.origin="user_supplied"`. Creating another fresh setup
   continues to inherit **49**.
6. A negative price must show **Profile fees not saved** and retain the previous
   profile defaults. Clearing a phase means unknown, not zero; saving a setup
   for that phase without an override must fail with a fee configuration reason.
   Tradovate/WealthCharts defaults are separate from Rithmic's.

Saved evidence generated through this workflow is in
[`artifacts/prop-profile-fees/`](../artifacts/prop-profile-fees/):
`profile-fees.png`, `evaluation-result.png`, and the actual saved `report.json`.
Its source is the synthetic fixture, not market-performance evidence. The
browser tests use temporary stores/servers and stop them after testing.

Reusable pricing is user supplied with a UTC `configured_on` date and matching
currency. On 2026-10-26 the user supplied **49 + 129 activation**, or **109 with
no activation fee**. Both options are preconfigured separately for all three
supported platforms. Existing saved setups/results and custom profile fee
settings are preserved. The no-activation option requires an explicit zero
activation price; its activation editor is read-only, and contradictory nonzero
default/override values are rejected before publishing a setup or saving defaults.

On 2026-10-26 the official [Apex product selector](https://apextraderfunding.com/)
was reachable in indexed form, but the EOD 50K selector and direct/browser
requests were blocked. No evaluation or activation amount was verified or added
as an official default, and no pricing effective date is inferred. User-provided
prices remain separate from verified rule evidence. The official
[activation guide](https://apextraderfunding.com/help-center/billing/pa-activation-process-deadline-explained/)
describes a one-time fee but did not expose a numeric price in the retrieved
text. You can edit your actual prices in the profile, rather than per simulation.

## Validate the supplied pricing options

1. From the arithmetic report, open **Set up prop simulation**. The profile
   selector offers each platform with **49 evaluation + 129 activation**, and
   **109 evaluation / no activation fee**. No fee entry is required for either.
   Existing custom prices take precedence over these defaults.
2. Select Rithmic's standard option, evaluation, quantity **2**, with the same
   synthetic instrument/calendar declarations above and the fee override **off**.
   Save, check and run. Expect balance/equity **50,026**, external fees **49**,
   net cash **−49**, and `unresolved_data_end`. The evaluation does not charge
   the separate funded activation fee.
3. Create a new setup from the same report and select Rithmic's no-activation
   option, quantity **2**, leaving the override **off**. Save, check and run.
   Expect the same **50,026** balance/equity and outcome, external fees **109**,
   net cash **−109**. Reload and reopen the standard result: it still records
   **49**. Results/downloads identify the selected profile, with different hashes.
4. In a fresh setup, switch phase to funded. Standard shows **129 USD**;
   no-activation shows **0 USD**, preserved on save/reload. Funded execution
   remains unavailable. These are conditional funded configurations; this
   increment does not simulate an evaluation-to-funded campaign.

Actual saved outputs from the normal workflow are in
[`artifacts/prop-pricing-options/`](../artifacts/prop-pricing-options/):
`standard-report.json`, `no-activation-report.json`, and their result screenshots.
The strategy source is the synthetic arithmetic fixture; fees are the values
supplied in the conversation, not a provider-pricing verification.

For an entirely flat run using the same file, set the strategy's green-bar count
to **100** and run normally. A source check with the same coverage should show
one covered session with seven bars, zero trades, zero net P&L and no invented
original source quantity. Trade-close preview is empty; bar-close has seven flat
observations. On multi-session sources, every covered zero-trade session remains.
Running this short flat evaluation ends at **50,000** with
`unresolved_data_end`; no day-30 expiration is invented.

## Deliverables by subtask

| Subtask | Final-product increment | User validation |
| --- | --- | --- |
| 1. Specification | [Implementation contract](prop_simulation.md) and relevant workflow help | Read phase/observation/calendar/cost scope and compare it with form behavior; no artificial design-checking page |
| 2. Rules/configuration | Actual report action, phase/platform setup, immutable saved snapshots, re-open/download | Switch platform/phase, save/reload, verify captured settings and phase fees, retain older setups |
| 3. Saved-input adapter | Real source compatibility, sessions, both observation previews and JSON/CSV exports | Reconcile source versus scaled quantities/P&L/costs, inspect zero-trade sessions, try an intentionally incorrect coverage declaration |
| 4. Historical evaluation | Evaluation execution, durable results, saved-trace chart, paged events and exports | Run quantities 2/1 and verify 50,026/50,013, fees separate from balance, and reload/reopen earlier results |

The specification separately documents notebook defects, incorporate/correct/
defer decisions, future engine boundaries and acceptance examples. Measured
excursions, variable source sizing and overnight exposure remain unsupported.
Source checks reject incompatible units, missing coverage, variable quantities,
session-crossing exposure and irreconcilable artifacts without changing source
backtests. No measured MAE/MFE or unobserved threshold fill is fabricated.

## Storage and verification

Setups and immutable input checks use `data/prop_runs/` and
`data/prop_simulations.sqlite3` by default, following `ALPHAQUEST_DATA_DIR` if set.
Each new save creates a separate setup; checks and simulations reference the
captured setup. Evaluation results publish atomically only after source
validation, engine execution and monetary/count reconciliation. An interrupted
or invalid operation publishes no result. A financial account failure is a
completed operation with account outcome `failed_drawdown`.
Source previews are staged incrementally into SQLite/CSV and paged at 50 rows
in the UI (100 maximum per API request). The user's original dataset and backtest
artifacts are unchanged. Old `prop_reviews/` files remain as historical evidence;
the dedicated review page, API and fixture generator have been retired.

Run the configuration, adapter, real API and Chromium workflow checks:

```bash
.venv/bin/python -m pytest -q tests/test_prop_configuration.py tests/test_prop_sessions.py tests/test_prop_engine.py tests/test_prop_api.py tests/test_prop_results_api.py tests/test_prop_browser.py tests/test_prop_results_browser.py tests/test_prop_profile_fees.py tests/test_prop_profile_fees_browser.py
```

Browser prerequisites, when not already installed:

```bash
.venv/bin/python -m pip install -e '.[dev,browser]' -c requirements.lock
.venv/bin/python -m playwright install chromium
```

Tests cover immutable settings after template edits and process restart,
normalized costs once, input rejection, coverage, Sunday/DST session boundaries,
zero-trade sessions, both previews, pagination/exports, mobile layout, and visible
request failure/retry behavior. Evaluation checks cover threshold touches and
overshoots, forced-close costs, next-session resumption, target recognition,
platform locks, expiry, fees, chart/ledger equality, stale inputs and failed
reconciliation/publication. Test web servers stop automatically. HTML/JS/CSS
revalidate on reload to avoid mismatched cached scripts after updates.

Every future implementation must deliver a usable increment in this same final
workflow, inspectable actual outputs, and exact reproduction/check steps with
independent expectations. Tests supplement the product demonstration. Do not
introduce a separate page, API or storage solely to demonstrate a subtask.
