# Notebook integration workflow and evidence

The old strict workflow guide is recoverable from `recovery/prop-notebook-20261026T084948Z`
and the workspace patch. Earlier evidence under `artifacts/prop-*` remains intact.

Starting HEAD: `9457b00bf40e56d59e5372928e7536f271dd72ba`.
Recovery branch: `recovery/prop-notebook-20261026T084948Z`.
Workspace backup: `/Users/yx/.codex/workspace-backups/prop-notebook-20261026T084948Z/`
(`tracked-workspace.patch`, `index.patch`, `manifest.json`; no untracked files).
Working branch: `work/prop-notebook-20261026T084948Z`. No push or merge.

Cleanup removes the active strict engine and its intentionally retired tests.
Backtest, dataset, strategy, execution and reporting modules retain baseline
behavior. Native report integration follows in the implementation commits.

Cleanup validation: `.venv/bin/python -m pytest -q` → **521 passed**, one existing
Starlette/httpx deprecation warning, 87.66 seconds. This deliberately excludes
retired strict-engine tests. No user server was stopped or started.

## Increment 1 — native trades and main evaluation

Start: `.venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8000`.
Open `http://127.0.0.1:8000/#backtests/report/d63265dc923444c799c2dfc59e090e76`.
Click **Configure prop analysis**, keep Source execution costs, choose **$49 + $129**,
choose **Main evaluation**, set main simulations **256**, size **1**, engine
**Excursion**. Enter additional overrides:

```json
{"PROP_MC_SIMS":256,"N_SPAGHETTI":40,"PAYOUT_SIMS":256,"PAYOUT_SWEEP_SIMS":128,"LIFETIME_SIMS":256,"LIFETIME_SWEEP_SIMS":128}
```

These explicitly reduced demonstration counts are not production defaults.
Click **Check source**, inspect the reconciliation and resolved settings, then
**Run analysis**. Reload; return to the source report, re-enter configuration and
open the saved analysis. Use all four download links. Stop your server with Ctrl-C.

Independent source arithmetic: 80,355 reference gross − 2,793.96 commissions − 0
slippage = **77,561.04**, 702 trades. OOS from 2023-01-01 retains **466** trades:
71,275 − 1,854.68 = **69,420.32**. Cost overrides are **3.98 round trip**, zero
slippage. Notebook defaults remain 2.25 and 5. There are **914** weekdays and
**448** zero-trade weekdays; weekends are excluded using local entry dates.
Requested excursion falls back to trade, measured coverage **0%**. Full source
bars were neither required nor scanned.

Saved report `60f1952604a34eccbb3d4f69554519c9` has **156 pass, 40 DD, 60 deadline**,
pass rate **0.609375**, mean net trade **148.97064377682406**. Fresh notebook cells
2–7 and the numerical path portion of cell 9 match all compared counts,
aggregates, daily/trade canonical values and path arrays exactly. At this first
increment the path cell uses the full sample; later increments reproduce the
cell 8 switch to validation before drawing paths.

Actual durable output: `data/prop_analyses/60f1952604a34eccbb3d4f69554519c9/`.
Downloaded evidence: `artifacts/prop-notebook/increment1/{report.json,trades.csv,
daily.csv,analysis.zip,validation.json,source-check.png,report.png}`.
Reproduce automatically: `.venv/bin/python scripts/demo_prop_analysis.py --increment 1`.
It uses an ephemeral server and stops it on exit; creates a new saved report.

Focused validation: 14 API/numerical checks passed, plus one Chromium workflow
check. Tests independently verify the ordinary synthetic arithmetic backtest:
source reference gross 40, costs 4 + 10, net 26 at quantity 2 → normalized
**20 − 2 − 5 = 13**, bootstrap interval [13,13], all 32 paths hit deadline.
That seven-bar source needs no complete daily bar coverage or measured MAE.
Empty/OOS-filtered inputs reject without fabricated trades. Empty holdout rejects
with instructions to set VALIDATION_SPLIT=0. Invalid settings reject. Duplicate
active submissions share a job ID; operational failure cannot download a completed
report. Reload/reopen issue no POST and do not rerun Monte Carlo.

## Increment 2 — sizing, staged sizing and repeated attempts

Use the increment 1 UI steps and identical overrides, choosing **Evaluation +
sizing and attempts**. Or run
`.venv/bin/python scripts/demo_prop_analysis.py --increment 2`.
All nine original fractional size-grid rows are retained. The evaluation sweep
uses main count 256 (the notebook does not use SWEEP_SIMS there). Stage-1 sizes
are round(fraction × selected size, 2). Train and holdout weekday counts, selected
row, holdout metrics, CI-overlap rows, staged baseline/variants and sample labels
are saved. Paths now draw from validation, as in top-to-bottom cell execution.
Independent attempts use the main result; correlated attempts use the selected
size's validation result. The fee preset overrides ATTEMPT_FEE and EVAL_FEE
separately and preserves the notebook's different probability inputs.

Saved report: `5b6c4105cfd744a484c8463d2bbf7070`.
Durable directory: `data/prop_analyses/5b6c4105cfd744a484c8463d2bbf7070/`.
Evidence/downloads/screenshots: `artifacts/prop-notebook/increment2/` (same filenames
as increment 1). The fresh reference prefix through cells 8/8b/9/10/10b matches
all sweep rows, selected size/holdout metrics, staged probabilities and retained
paths **exactly**. Automated fixture checks also compare every correlated-attempt
row. Independent arithmetic: p=.5 gives P(pass within 2)=.75 under independence,
and .625 at rho=.5. Twenty-two focused checks passed including real Chromium
run/reload/reopen/download. The temporary demo/test servers stopped normally.

Expected saved observations: selected size 2.0 minis; train pass 0.8046875; validation pass 0.83203125; staged flat 0.56640625; staged rows [[0.5, 0.37109375, 0.3142282955244983, 0.4317708054662592], [1.0, 0.48046875, 0.42000768037908615, 0.5415073349225438], [1.5, 0.53515625, 0.4739891850542932, 0.595283787402773]]. Sample: validation (held out).

## Increment 3 — funded first payout

Repeat increment 1's source/settings/counts, selecting **Through funded first
payout**. Inspect the funded detail, size sweep, payout distribution and time-to-
qualify charts. Reopen from the source's saved analysis list and download JSON/ZIP.
Automatic reproduction: `.venv/bin/python scripts/demo_prop_analysis.py --increment 3`.

Actual saved report `d5b6354bfd4e4941a608b2a8692b0f25`, durable directory
`data/prop_analyses/d5b6354bfd4e4941a608b2a8692b0f25/`, downloaded evidence and screenshots
`artifacts/prop-notebook/increment3/`. Expected observations: selected **2.0** minis;
256 detail paths → **226 qualified, 29 blown, 1 inactive, 0 horizon**; qualify
probability **0.8828125**, expected first payout **1321.42296875**, median qualifying
day **18**. Funded and staged selections reuse validation, deliberately.
Fresh notebook prefix through cells 11–13 matches every sweep row, selected size,
all detail metrics and raw payout/drawdown/qualifying-day arrays exactly.

Deterministic product examples use normal dataset upload and backtest APIs, then
the real report/configure/check/run/download UI. Their saved dataset names and CSV
filenames say **SYNTHETIC**; none represents market performance. Each has seven
5-minute bars, one quantity-two trade, zero commission/slippage and point value 1.
Entry price 10000; exit price = 10000 + declared per-contract profit. Source net
therefore equals twice that profit. The analysis normalizes to one mini. Use
OOS_START_DATE=null, VALIDATION_SPLIT=0, SWEEP_CONTRACTS=[1], PAYOUT_CONTRACTS=[1],
PAYOUT_MAX_HORIZON=30, and the same reduced counts as above.

| Command suffix after `scripts/demo_prop_analysis.py --increment 3` | Saved analysis | Independent expected funded detail |
| --- | --- | --- |
| `--fixture payout` | `f2c5ad9c56424d9eb62f0f0553cc7feb` | +600/day; all 256 qualify day 5; equity 3000, safety net 2100 → payout 900 |
| `--fixture blown` | `e63fae9c00534795acbd7be5510dc915` | −1100/day; DLL clips day 1 to −1000, day 2 reaches account floor; all 256 blown |
| `--fixture inactive` | `dbc83686466047a79ddcbc1134447875` | zero-profit trades; all 256 inactive, none qualified |
| `--fixture horizon` | `5b1fa88bfe494aaaa295d4221215320e` | +100/day; meets activity but never +250 qualifying threshold; all 256 open at day-30 horizon |

Each fixture directory `artifacts/prop-notebook/increment3/<fixture>/` contains
`synthetic-source.csv`, `source-backtest.json`, all downloads, validation.json and
two screenshots. To reproduce manually, upload that CSV with UTC, tick/point 1,
run Consecutive green hold with 3 green bars, 20-minute hold, 2 contracts, initial
50000, zero slippage and commission. Open its report and use the settings above.
The small source intentionally has no full-session coverage and no measured MAE.
All four portal demonstrations and fresh notebook comparisons passed; each server
was stopped on exit. Adapter tests independently cover Sunday-local exclusion,
zero-trade Tuesday, variable-quantity default rejection and opt-in, cost corruption
rejection and nominal-versus-observed slippage reconciliation.
