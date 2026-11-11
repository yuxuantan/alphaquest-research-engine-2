# Frozen-family OOS product evidence

This folder contains actual native executions through the ordinary campaign
portal, using a labeled synthetic source. It demonstrates execution and gate
arithmetic, not a measured trading edge, MultiCharts parity, or provider approval.
All test servers stop at teardown. Earlier evidence folders remain unchanged.

## Saved outputs

- `SYNTHETIC-source.csv`: stable source uploaded through the normal dataset API.
- `oos-assessment.json`: downloaded policy, frozen family, source/engine hashes,
  prior-access snapshot, native measurements, and all four acceptance results.
- `oos-results.csv`: normal product comparison/criteria download.
- `oos-portal.png`: actual OOS page with the single comparison table.
- `journey.json`: generated dataset/workflow/job IDs and independent expectations.
- `degraded/`: separately labeled source and genuine failing OOS assessment;
  one candidate's IS, OOS and cost-stress report/trade/equity downloads allow
  independent inspection and net-P&L reconciliation.

## Exact reproduction

From the repository, recreate the stable normal-product journey in an isolated
temporary app:

```sh
ALPHAQUEST_OOS_EVIDENCE_DIR=/tmp/alphaquest-oos-evidence \
  .venv/bin/python -m pytest -q tests/test_campaign_oos_browser.py
```

Recreate the failing native assessment and check its published measurements:

```sh
ALPHAQUEST_OOS_EVIDENCE_DIR=/tmp/alphaquest-oos-evidence \
  .venv/bin/python -m pytest -q \
  'tests/test_campaign_oos.py::test_native_oos_exact_frozen_membership_measurements_and_history[True]'
```

The fast independent gate/capture checks are in `tests/test_oos_criteria.py`.
The remaining focused API cases in `tests/test_campaign_oos.py` cover repeated
history, closed phases, exact family membership, idempotence, tamper rejection,
deletion safety and resuming after a real first candidate completes. Parallel
execution and Chromium need ordinary local process/socket permissions.

## Manual product journey

Use a fresh data directory so the demonstration does not affect real reports:

```sh
ALPHAQUEST_DATA_DIR="$(mktemp -d /tmp/alphaquest-oos.XXXXXX)" \
  .venv/bin/uvicorn alphaquest.app:app --host 127.0.0.1 --port 8012
```

1. Open `http://127.0.0.1:8012/`. Upload the stable CSV as UTC, tick size 0.25,
   point value 10, symbol SYNTHETIC. It contains 2024–2026 data.
2. Create a Consecutive Green Hold campaign workflow. Declare IS 2024-01-01
   through 2025-12-31 and OOS 2026-01-01 through 2026-12-31. Use initial capital
   10,000, one baseline slippage tick, and one CU commission per contract/side.
3. Run mechanics on IS, inspect the results, and complete the labeled synthetic
   checklist. This manual attestation exercise does not establish external parity.
4. In Broad, fix green count 3 and hold minutes 20; vary contracts 1..2, step 1.
   Run and confirm both passing Broad rows.
5. In the first Narrow branch, fix green count 3 and contracts 1; vary hold
   minutes 14..20, step 2. Confirm hold values **16 and 18**.
6. In the second Narrow branch, keep contracts 2 fixed and vary green count
   2..3, step 1, and hold minutes 14..20, step 2. Confirm green=3 / hold=14 and
   green=3 / hold=20 (trials **5 and 8**). These are valid one-sided corners
   under the tested-grid plateau policy. All IS choices are now frozen.
7. Open OOS. Expect four pending rows and four parallel backtests by default.
   Opening the page does not run a backtest. Click **Run all frozen OOS
   configurations**. The worker runs exactly those four dictionaries, plus
   their four cost-stress replays. It does not execute the eight combinations
   implied by crossing four hold values with two quantities.
8. Expect all four stable candidates to pass seven checks. Expand Eligibility
   for each threshold and its measured value. Show/hide/freeze columns, sort by
   OOS profit, and inspect linked IS, OOS and stress native reports.
9. Download JSON and CSV. Visit Job history, click **Open OOS**, then reload:
   the same reports and verdicts reopen without replay. The OOS phase becomes
   passed when the complete batch has at least one passing candidate; the
   individual count is always shown. Multiple configurations may pass.
10. To inspect the negative case, repeat this fixed IS-selection recipe with
    `degraded/SYNTHETIC-source.csv` in a fresh workflow. All four OOS rows fail
    retention, despite positive baseline and extra-slippage net profit.
11. An explicit **Run another manual OOS assessment** appends another history
    entry; it does not alter IS choices or erase prior access. Active jobs
    continue when navigating away. Stop retains completed reports; Resume runs
    remaining candidates under the same saved engine identity. A changed
    implementation requires another explicit assessment and retains old history.

Stop the manual server with Ctrl-C. No persistent test server is started.

## Independent numerical expectations

The synthetic design produces six trades per active date. IS has 120 active
dates; OOS has 60. At green count 3, stable close-price changes sum to 12 points
per date: 120 CU before costs. Twelve fills × 0.25 × 10 CU gives 30 CU baseline
slippage; twelve contract-sides × 1 CU gives 12 CU commissions. Thus stable net
is **78 CU/date**, giving IS **9,360 CU**, OOS **4,680 CU**, and net/trade **13 CU**
at one contract. One extra tick per fill costs another 30 CU/date, leaving
**2,880 CU** OOS. Two-contract candidates double those currency amounts.

Annualization uses 365.2425 days/year, divided by elapsed declared calendar
duration. IS includes the leap year 2024, so stable annual profit retention is
slightly above 100%; net/trade retention is exactly 100%. Source months are
all profitable, and repeated native bar-close risk patterns preserve MTM depth.

The degraded OOS closes sum to 7.8 points per date. Subtracting the same 30 CU
baseline slippage and 12 CU commissions leaves **36 CU/date**: **2,160 CU** OOS
and **360 CU** after extra slippage. Net/trade is **6 CU**, retaining
**46.15%** of IS's 13 CU, below the 50% threshold. Two contracts give **4,320 CU**
and **720 CU** respectively. Trade CSV `net_pnl` already includes actual costs;
sum it directly rather than deducting reported slippage again.

Policy details, including insufficient-evidence and zero-IS-drawdown handling,
are in `docs/workflow_screening.md`. Thresholds are a local historical screen,
not a universal statistical standard or a guarantee of future performance.
