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

## Increment 4 — lifetime, economics and complete report

From the source report, choose **Complete lifetime and economics**. The report
combines all earlier sections, source-equity curve, outcome charts, full lifetime
size sweep, total-extraction/payout-count/account-lifetime distributions, sizing
funnel, economics and block robustness. Reopen from saved analyses, or navigate
directly to `/#backtests/prop/job/<id>`. Downloads read the published report;
reload and reopening never submit a new operation.

Reduced-count report `d06a3c6b9fdc448fbfa6a8c8c7f2a18f` uses the increment 1
settings and the full original lifetime horizon 2000, with 128 paths per lifetime
size. Its evidence is in
`artifacts/prop-notebook/increment4/reproduction-20261026T091207078850Z/`.
Earlier increment 4 snapshots remain in the base directory and durable store.
Later demo reruns create a new timestamped subdirectory, preserving prior evidence.
Expected selected lifetime size **2.0**, mean extraction **11200.1896875**, mean
payout count **5.1953125**, mean life **110.953125** weekdays, horizon rate **0**.
With explicit $49+$129 overrides, acquisition cost is
49 / .609375 + 129 = **209.4102564102564**, expected net **10990.779431089744**.
All raw lifetime totals/counts/lifetimes, selected sizes, formulas and block 1/5/10
results match the fresh original notebook exactly. The economic verdict is the
notebook's label, with its documented holdout reuse and acquisition shortcuts.

Independent positive fixture arithmetic: +600 per weekday, one trade, no costs,
no holdout. First request at day 5 withdraws 3000−2100=900. Later five-day cycles
withdraw 1500,2000,2500,2500,3000, totaling **12400** over **30** days, with six
payouts and ladder_done. Notebook-default acquisition cost is 100/1+140=240;
expected net **12160**. Tests verify those independent values. All-loss fixtures
verify both selection fallbacks and infinite acquisition-cost disclosure.

### Original-count native demonstration

Command actually run:
`.venv/bin/python scripts/demo_prop_analysis.py --increment 4 --full-counts`.
This uses source costs and the $49+$129 pricing preset, **no count overrides**.
The UI receives 20000 main/evaluation-sweep/staged paths, 20000 funded detail,
5000 funded sweep per size, 4000 lifetime sweep per size, 300 sample equity paths,
full original 9/16 size grids, 250/2000-day funded/lifetime guards and seed 42.
SWEEP_SIMS=5000 and LIFETIME_SIMS=10000 remain recorded but unused where the
original executable cells do not use them. Bootstrap statistics use fixed seed
42 and 10000 resamples. No requested count is reduced.

Actual complete report: `1b9480015b5a4670a2b98e05f37bf28b`.
Open `http://127.0.0.1:8000/#backtests/prop/job/1b9480015b5a4670a2b98e05f37bf28b`.
Durable files: `data/prop_analyses/1b9480015b5a4670a2b98e05f37bf28b/`.
Evidence: `artifacts/prop-notebook/increment4/full-counts/`, containing report JSON,
ordered trades/daily CSV, ZIP, independent validation.json, full report/source-check
screenshots and readable funded/lifetime/economics/robustness screenshots.

To reproduce manually, follow increment 1's source report link. Choose Complete,
Source execution costs, $49+$129, size 1, excursion, main count **20000**, and
additional overrides **{}**. Check source and run. Observe the exact saved values
below, reload, reopen and download. Keep original notebook pricing instead if you
want its literal 100/140 fee assumptions; those would change economics explicitly.

Fresh independent reference execution of the entire corresponding notebook prefix
matched every checked count, aggregate, normalized canonical trade/daily value,
bootstrap statistic, path, size selection, attempt probability, funded result,
lifetime total/payout-count/lifetime array, economic formula and robustness row
**exactly**. Python 3.12.5 / NumPy 2.5.4 / pandas 3.1.0; no float tolerance was needed.
The reference reads executable cells from the pinned source, never stored outputs.

Full-count expected observations: **11239 pass, 4367 DD, 4394 deadline** (pass 0.56195); evaluation-selected size **2.0**; funded **16906 qualified, 2922 blown, 172 inactive, 0 horizon**, expected first payout **1266.56399**. Lifetime-selected size **2.0**, mean extraction **10406.71656**, mean payout count **4.84075**, mean life **104.24825**, horizon rate **0.0**. Acquisition **216.1963697837886**, expected net **10190.520190216212**.

| Block | Evaluation pass | Funded qualify | Blown |
| --- | --- | --- | --- |
| 1 | 0.65035 | 0.835 | 0.1578 |
| 5 | 0.61925 | 0.7824 | 0.2048 |
| 10 | 0.5955 | 0.7444 | 0.2432 |

## Completion checks and retained boundaries

Cleanup commit: `947d519`. Implementation increments 1–3: `9330f68`, `a0ade09`,
`3c60e68`; increment 4 is the commit containing this completion record.
`.venv/bin/python -m pytest -q` completed **559 passed**, 24 warnings in 97.06s:
one existing Starlette/httpx deprecation, plus the original notebook loader's
pandas dayofweek deprecation warnings. `git diff --check` passed. Fresh notebook
comparisons, browser run/reload/reopen/download, synthetic funded boundaries and
original-count complete-report comparison all passed. Downloaded JSON/CSV/ZIP
are the same published files used by the report; source identity/cost arithmetic
and chart bins/arrays are inspectable. All temporary servers stopped normally;
no persistent server was started and no existing user server was stopped.

The workspace backup patch was independently tested with `git apply --check`
against an archive of the recovery ref and applies cleanly. Working branch is
local only; no push or merge. Original strategy, execution, backtest, dataset and
reporting source modules retain their baseline content; only portal integration
and app lifecycle orchestration change there. Original datasets/backtests,
legacy prop catalogues/results and prior evidence were retained, without conversion.
The strict URLs/readers listed in the specification are intentionally retired.

No unmatched numerical output remains in the comparisons run. Qualification is
for the pinned executable notebook, supported native saved trades, settings,
seeds and pinned runtime actually exercised. Chart styling is portal-native SVG;
its saved data matches the notebook calculations. Native saved trades have no
measured MAE/MFE, so native analysis uses the documented fallback. Known notebook
financial/model shortcuts remain limitations, including holdout reuse and
selection fallbacks; provider correctness and actual micro-contract execution
are not claims of this product. Operations over resource bounds reject explicitly.
