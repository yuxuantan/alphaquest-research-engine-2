# Monte Carlo v2: diagnostics and immutable policy update

Current passing requirements are ≥100 observed dates, ≥100 closed trades, and
5th-percentile full-period net profit >0 under both 5-day and 20-day mean block
lengths. Mean/median profit and every drawdown metric are diagnostic only. The
95th-percentile drawdown ≤2× historical drawdown rule is no longer a gate.

## Actual product journey

1. In an existing completed campaign OOS assessment, inspect **Final Monte Carlo
   sanity check**. Newly created assessments use v2 automatically.
2. If its saved assessment uses v1, it is labeled **historical policy**. Click
   **Apply updated policy to saved paths**. This publishes a distinct v2 result
   using the original sealed outcomes, without rerunning backtests or Monte Carlo.
3. Inspect mean/median net profit, median/95th-percentile daily-close drawdown,
   historical drawdown, its simulated percentile and the drawdown multiple.
   All values display two decimal places. The percentile is descriptive and the
   mean is anchored to the sample; neither is an extra gate or proof of edge.
4. The historical drawdown percentile gives half weight to ties. All identical
   drawdowns give 50%, rather than misleadingly reporting an extreme percentile.
   The drawdown multiple displays N/A when historical drawdown is zero.
5. Download the current JSON/ZIP and exact input/path CSVs. **Original assessment
   JSON** retains the prior rules and verdict. Job history records the new
   assessment and returns to the campaign OOS page. Reload to reopen saved results.

The saved source and reports here are synthetic. The Chromium journey creates
and freezes real native IS/OOS reports through the ordinary product API. It runs
the current Monte Carlo from the OOS page, then represents that sealed population
in a test-only, internally consistent v1 schema to exercise the policy update.
The update occurs from the actual portal button, with simulation disabled by
the test to prove it uses saved outcomes. There is no fixture-only product route.

`original-v1-report.json` preserves that original schema and its measurements.
`report.json` references the original population. `daily.csv` and `paths.csv`
remain byte-identical across the update, and all original report/archive hashes
are unchanged. The archive is the ordinary sealed product download. Earlier
evidence in the parent folder remains intact.

## Independent expected values and boundaries

The native synthetic example has 120 IS + 60 OOS active dates, each earning
78 CU per contract after existing costs: **14,040 CU** at one contract and
**28,080 CU** at two contracts, with **1,080 closed trades** per candidate.
There are 184 observed source dates, including four inactive dates. All daily
increments are nonnegative, so historical, median and 95th-percentile daily-close
drawdown are zero, the historical drawdown percentile is 50%, and all four
candidates pass. Reassessment retains all **40,000** original path outcomes.

The focused arithmetic tests independently establish that alternating +10/−1
for 100 observations has original net +450 CU and drawdown 1 CU. Its seeded
5-day scenario has a 3 CU tail drawdown, exceeding the former 2 CU limit, but
qualifies under v2 because its lower-tail profit is positive. A fixture with
500 path profits of −100 and 4,500 of +1,000 has positive mean **890** and median
**1,000** but fails the −100 lower tail: attractive averages cannot override it.
For drawdowns 25% below the historical value and 50% equal, the historical
percentile is **50%**, confirming the midpoint-tie definition.

## Reproduce

```sh
.venv/bin/python -m pytest -q tests/test_monte_carlo.py tests/test_campaign_monte_carlo.py
ALPHAQUEST_MC_EVIDENCE_DIR=/tmp/alphaquest-mc-v2 .venv/bin/python -m pytest -q tests/test_campaign_monte_carlo_browser.py
```

Browser servers stop at fixture teardown. No persistent server is needed for
verification. These synthetic outputs establish mechanics and provenance, not
measured MultiCharts parity, a future edge, or readiness to trade.
