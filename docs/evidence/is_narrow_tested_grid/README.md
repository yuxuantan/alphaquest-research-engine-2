# IS Narrow plateau using existing grid results

Actual normal-portal outputs for `is-narrow-v4`, using a labeled synthetic
dataset. This verifies gate arithmetic and workflow behavior; it does not
establish a measured trading edge or MultiCharts parity. Temporary servers
are stopped by the browser fixtures.

The root folder contains the uploaded source CSV, native result assessments,
downloaded confirmed package, screenshot, and journey IDs. `boundary/` contains
a separate two-axis corner example, its actual results, screenshot, and job
counts before/after assessment. Earlier evidence folders are preserved.

Reproduce with the ordinary application running in isolated temporary storage:

```sh
ALPHAQUEST_NARROW_EVIDENCE_DIR=/tmp/alphaquest-tested-grid-evidence \
  .venv/bin/python -m pytest -q \
  tests/test_campaign_narrow_browser.py::test_narrow_portal_two_broad_branches_columns_and_oos_handoff \
  tests/test_campaign_narrow_browser.py::test_tested_grid_corner_qualifies_without_additional_backtests
```

For manual reproduction, start a fresh normal app, then stop it with Ctrl-C:

```sh
ALPHAQUEST_DATA_DIR="$(mktemp -d /tmp/alphaquest-tested-grid.XXXXXX)" \
  .venv/bin/uvicorn alphaquest.app:app --host 127.0.0.1 --port 8012
```

1. Visit `http://127.0.0.1:8012/` and upload `SYNTHETIC-source.csv` as UTC,
   tick size 0.25, point value 10, symbol SYNTHETIC.
2. Create a Consecutive Green Hold workflow. Use IS 2024-01-01 through
   2025-12-31, OOS 2026-01-01, initial capital 10,000, one tick baseline slippage,
   and one CU commission per contract per side. Run mechanics and inspect its
   evidence before completing the labeled synthetic attestation.
3. In Broad, fix green-bar count 3 and hold minutes 20; vary contracts 1..2,
   step 1. Run and confirm both rows.
4. In each Narrow branch, fix green-bar count 3 and its selected contracts.
   Set hold minutes 14..20, step 2. There is no separate local plateau step.
   Preview and run four configurations per branch.
5. Expand Eligibility. Expect hold 16 and 18 to qualify with 100% retention.
   Hold 14 and 20 each have only one available numeric neighbor, so display
   insufficient evidence and a one-sided assessment. Confirm the two interior
   rows per branch and download the saved package. OOS navigation becomes ready
   after both branches are confirmed; this does not execute OOS.
6. To reproduce the separate corner example, use a fresh workflow with the same
   Broad settings. In its first Narrow branch, vary green-bar count 2..3,
   step 1, and hold minutes 14..20, step 2; contracts stay fixed at 1. This is
   eight configurations. Green=3 / hold=14 qualifies using green=2 / hold=14
   and green=3 / hold=16. Both axes are one-sided, clearly labeled in the page.
   Loading or sorting results does not create another job or backtest.

Independent expected values: the one-contract source has 120 active days, six
trades/day, and 78 CU net/day at green count 3, giving **9,360 CU**. One extra
tick per fill costs 12 fills/day × 0.25 × 10 × 120 = 3,600 CU, leaving
**5,760 CU**. Two contracts double both amounts. Green count 2 enters one point
earlier in each synthetic trade, adding 6 × 10 × 120 = 7,200 CU and giving
**16,560 CU**, with **12,960 CU** after extra slippage. The qualifying corner
therefore sees **176.92%** and **100%** neighbor retention. Green count 2 rows
fail because their green count 3 neighbor retains only **56.52%**, despite both
settings remaining profitable.

Focused API checks also assess and confirm genuine older coarse v2/v3 native
grids with replay/job creation forbidden, verify unchanged report hashes, and
preserve confirmed v1/v2/v3 admission snapshots. Missing internal evidence and
nonpositive extra-slippage results fail closed.
