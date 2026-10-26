# Use and validate prop simulation setup

The product workflow is **completed backtest → configure prop simulation →
check source data → run simulation → results**. Configuration, saved setups,
source checking and historical evaluation execution are available now. Funded
execution and Monte Carlo remain unavailable and will extend this same workflow.

## Start the app

From the repository, using the existing environment:

```bash
.venv/bin/python -m pip install -e '.[dev,browser]' -c requirements.lock
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
4. Under **2. Select instrument**, choose **NQ · E-mini Nasdaq-100** or
   **MNQ · Micro E-mini Nasdaq-100** to fill the currency, tick/point values,
   Apex contract weight, source links and interpretation automatically. No
   manual unit fields are required. The profile is checked against saved
   execution settings and any explicit source symbol/currency. A mismatch blocks
   saving; it never converts an NQ run into MNQ or changes its original P&L.
   Selecting a profile explicitly declares identity/currency when missing from
   the source; numeric specifications or a dataset name alone do not prove them.
   Complete matching structured symbol/currency/specs can preselect a profile.
   For unsupported instruments and earlier declarations, choose **Custom / legacy
   declaration** and fill the original explicit fields. A generic CU report
   still needs a justified currency interpretation, not an FX conversion.
5. Under **3. Coverage check**, leave **Automatic · reuse dataset session profile**
   selected. On a dataset's first use, choose its intended export schedule:
   **CME equity US cash hours** or **CME equity overnight session**, with one- or
   five-minute bars. Click **Use and remember session profile**. Later backtests
   from this dataset identity inherit the choice; no repeated calendar, cadence
   or JSON entry is required. The interval detected from the saved report is
   only a suggestion. Choose what the exporter was configured to produce, not
   whichever schedule makes the current bars pass. Cash-hours close labels are
   09:31–16:00 or 09:35–16:00 New York. For a different window or cadence, choose
   **Custom export-session profile** and declare its intended labels once.
   Sunday evening belongs to Monday; timestamps are never silently discarded.
   Review covered sessions, zero-trade sessions, closures, holiday dates, early
   closes, missing/unexpected bars and partial boundaries. Missing coverage
   blocks saving. Defaults for account start/end follow the generated calendar.
6. The automatic model is pinned to **pandas_market_calendars 5.5.0 CME_Equity**
   for **2013–2026**. It is a schedule model, not live exchange certification.
   Its modeled holiday hours can differ from verified exporter/product notices;
   use **Advanced · explicit calendar override** for exceptions or unsupported years.
   A custom profile may explicitly choose a weekday-only approximation, without
   holidays, when that describes the source. Under the advanced override, choose
   **Explicit dates and windows** for your own holidays, early closes, multiple
   windows or missing dates. Supply an ordered JSON array declaring every
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
7. Click **Save setup** (the advanced override additionally requires its coverage
   basis). A saved setup gets its own URL and retains a complete account,
   instrument, export-profile/settings/calendar snapshot. Download `profile.json`,
   `simulation.json`, `calendar.json`, `instrument.json`, `coverage.json` or
   `setup.json` as applicable. Changing a dataset's default does not alter earlier
   setups/results. Reopening them uses the captured coverage. **Refresh coverage**
   explicitly reads the current source and dataset default for a new setup.
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

## Check the automatic coverage workflow yourself

This is a synthetic numerical example using the ordinary dataset, backtest and
prop pages. It does not claim historical NQ performance.

1. Upload [coverage_rth_5m.csv](../tests/fixtures/backtest_contract/coverage_rth_5m.csv)
   in **Datasets**. Name it **Synthetic NQ cash-hours coverage**, choose source
   timezone **UTC**, tick size **0.25** and point value **20**. Validate and save.
2. In **Backtests**, select that dataset and **Consecutive green hold**. Use
   green count **3**, hold **20 minutes**, **2 contracts**, capital **10,000**,
   **1 tick slippage**, commission **1 per contract per side**, blank date bounds.
   Run it. The one source trade has gross **60**, commissions **4**, net **56**;
   informational fill slippage **20** is already reflected in gross/net.
3. Open **Set up prop simulation**. Keep standard Rithmic evaluation, bar close,
   quantity **2**, profile fee **49**, and select **NQ**. Under **3. Coverage check**,
   choose **CME equity US cash hours · 5-minute bars**, then **Use and remember
   session profile**. Expect **1 covered session**, **0 zero-trade sessions**,
   **78 expected / 78 observed bars** on **2026-01-05**, and **0** missing,
   unexpected or partial sessions. Advanced fields stay hidden.
4. **Save setup → Check source data → Run simulation**. Expect
   **unresolved_data_end**, balance/equity **50,056**, one completed trade, no
   suspension, fees **49**, receipts **0**, net cash **−49**. Trading P&L is not a
   cash payout. Download `coverage.json` and `report.json`; compare their source,
   export-profile and calendar hashes. Reload and reopen through saved setups.
5. Create a second backtest from the same dataset. Its prop setup should already
   have the five-minute cash-hours profile and complete coverage. No schedule
   entry is needed. To test zero trading, set green count **100**: the 78 bars
   still cover the session, **zero-trade sessions = 1**, P&L **0**, balance
   **50,000** (currently displayed as `5E+4`), net cash **−49**, and outcome
   **unresolved_data_end**.
6. For a rejection, copy the CSV and delete one middle data row; upload it as a
   separate synthetic dataset and backtest with green count **100**. Choose the
   same expected profile. Expect **78 expected / 77 observed**, **1 missing bar**,
   **0 covered / zero-trade sessions**, and **Save setup disabled**. Deleting the
   first row instead also shows **1 partial session**. Neither becomes a zero
   session or gets silently trimmed. Choosing the one-minute profile for the
   complete five-minute dataset likewise fails coverage.
7. Change the remembered default to one minute, then reopen the original saved
   setup/result: its five-minute profile, 78-bar report and financial result must
   remain unchanged. Saved snapshots do not consult the new dataset preference.

Browser checks write actual downloaded outputs and screenshots under
[`artifacts/prop-coverage/`](../artifacts/prop-coverage/): `coverage.json`,
`report.json`, `zero-coverage.json`, `zero-report.json`, `coverage.png`,
`result.png`, `zero-trade-coverage.png`, `zero-trade-result.png`,
`missing-bar.png` and `partial-boundary.png`. IDs and creation timestamps vary.
These ignored artifacts supplement this reproducible product workflow; they are
not a separate feature or evidence store. Earlier demonstration files remain.

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
   bounds. Choose **Custom / legacy declaration**, then symbol **TEST**,
   currency **USD**, rule weight **1**, source
   URL `https://example.com/explicit-test-units`, and basis **Synthetic test:
   prices are USD 10 per point, tick .25, one rule unit per fixture contract**.
   The example.com URL documents the test declaration only; it establishes no
   real-instrument contract equivalence.
4. Choose **Advanced · explicit calendar override**, then weekday approximation. Enter **05:00** through **05:30 New York**,
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

## Validate reusable instrument selection

For your existing NQ report, open **Set up prop simulation → 2. Select
instrument → NQ · E-mini Nasdaq-100**. The table fills **USD**, tick **0.25**,
point value **20**, and Apex weight **1**. There are no required manual symbol,
currency, weight, URL or interpretation fields. The expanded profile details
contain CME/Apex sources, retrieval dates, version and SHA-256. Complete the
calendar as usual, then save/check/run. Missing formal symbol/currency metadata
is explicitly declared by your choice; a file name alone does not select NQ.

For a reproducible arithmetic check, use the existing synthetic
[`arithmetic_5m.csv`](../tests/fixtures/backtest_contract/arithmetic_5m.csv):

1. In **Datasets**, set tick **0.25** and point value **20**, then create a new
   backtest using the strategy/settings in the earlier arithmetic example
   (quantity **2**, commission **1 per contract per side**, one slippage tick).
   If the CSV is already in the library, edit its instrument settings; do not
   upload a duplicate. Existing completed backtests keep their original settings.
   Label this as a synthetic NQ-unit example, not real market performance.
2. Expect source gross P&L **60**, commissions **4**, net **56**. From its report,
   select **NQ** and the standard Rithmic evaluation, with the fee override off.
   Keep the same declared New York **05:00–05:30**, **300-second** window as the
   earlier example. Save/check/run. Expect `unresolved_data_end`, balance/equity
   **50,056**, external fee **49** and net cash **−49** (unless you changed your
   profile fee defaults). Source commissions remain **4**, not the commission
   quoted on today's provider instrument page; they are not charged again.
3. Download **instrument.json** and **report.json**. The instrument export has
   root `symbol="NQ"`, `currency="USD"`, point value numerically **20**, weight
   **1**, generated interpretation, and `profile` containing the full immutable
   sourced instrument snapshot/hash. The report's
   `resolved.config.instrument_profile_sha256` matches
   `instrument.profile.profile_sha256`. Decimal strings can use canonical
   scientific notation in downloads. Reload/reopen: the captured profile stays.
4. In a fresh setup for that NQ backtest select **MNQ**. Expect a **point_value
   20 does not match MNQ profile 2** message and disabled **Save setup**. Selecting
   NQ restores compatibility. The API independently rejects the conflicting
   selection with 422 and publishes no setup; it does not resize/reprice source
   P&L or convert mini fills to micro fills.
5. For an independent synthetic MNQ-unit example, set dataset point value **2**,
   then create another completed backtest (same prices/strategy/cost settings).
   Expect gross **6**, commissions **4**, net **2**. Select **MNQ** in prop setup:
   it fills **USD**, tick **0.25**, point value **2**, weight **0.1**. Save/check/run
   ends at **50,002**, `unresolved_data_end`, external fee **49**, net cash **−49**.
   This fixture reuse is an arithmetic check, not a claim of NQ/MNQ execution parity.
6. Reopen the earlier NQ result after creating the MNQ example. It must still
   show **50,056** and its original instrument/source snapshots. Catalog edits
   affect future setups only. Saved setups can still check/run from their
   captured profile if the current instrument catalog cannot be loaded; saving
   edits waits for the catalog. Custom/legacy saved declarations still reopen
   under **Custom / legacy declaration** with their original fields.

Saved evidence from the actual workflow is in
[`artifacts/prop-instrument-profiles/`](../artifacts/prop-instrument-profiles/):
`nq-setup.png`, `nq-result.png`, `nq-instrument.json`, `nq-report.json`, and the
corresponding `mnq-*` outputs. Temporary browser-test servers/stores are stopped
and removed after validation; these downloaded outputs remain inspectable.

Instrument profiles are **1.0.0**, reviewed **2026-10-26**, with unspecified
effective dates. CME supplies the contract specs; Apex supplies the standard/
micro equivalence and platform instrument lists. This increment covers NQ/MNQ
root contracts, not symbol alias guessing, FX conversion, contract rolling,
broker routing or funded execution. For another instrument use the existing
explicit custom declaration or add a separately reviewed sourced profile.

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
.venv/bin/python -m pytest -q tests/test_prop_configuration.py tests/test_prop_sessions.py tests/test_prop_engine.py tests/test_prop_api.py tests/test_prop_results_api.py tests/test_prop_browser.py tests/test_prop_results_browser.py tests/test_prop_profile_fees.py tests/test_prop_profile_fees_browser.py tests/test_prop_instruments.py tests/test_prop_instruments_browser.py tests/test_prop_coverage.py tests/test_prop_coverage_browser.py
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
