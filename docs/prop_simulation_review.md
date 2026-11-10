# Prop simulation review and evidence

Current [acceptance record](robust_research_plan.md#final-acceptance-record) ·
[Final acceptance repairs](#8-november-2026--final-acceptance-repairs-and-readable-sizing-explanations) ·
[Complete product walkthrough](research_workflow.md#first-complete-campaign-a-practical-walkthrough) ·
Historical [architecture cleanup and regression qualification](#final-architecture-cleanup--2026-11-06) ·
[Phase campaigns](#phase-research-campaigns--2026-11-06) ·
[Portal / frozen OOS](#phase-campaign-portal-and-frozen-oos--2026-11-06) ·
[Current contracts](prop_simulation.md) · [Module ownership](architecture.md#final-module-ownership-and-retention).

All earlier dated review records below are preserved. Their model versions,
numerical findings and scope are historical evidence, not claims of current
provider accuracy. New qualification uses its own artifact directory.

# Funded simulation UI/UX review — 27 October 2026

The previous report gave source internals, long tables and funded outcomes the
same weight. Its desktop report content was 7,253 px tall, with the main funded
insight below evaluation detail. Raw field names, decimals and mixed account/slot
units made the positive mean easy to misread. The assessment and before/after
screenshots are saved in `artifacts/funded-ui-review-20261026T175950Z/`.

The normal saved-result page now opens with an Overview. It leads with the
no-payout takeaway and puts mean, median, payout chance and drawdown failure
together. Labelled probability bars distinguish mutually exclusive payout groups
from overlapping failure outcomes. First-payout timing states its paid-account
denominator. Separate Evaluation, Sizing, Historical replay and Source & model
views expose their own units, costs, samples and assumptions. The sizing table
highlights the selected size and sorts by annual slot net, size, payout or failure.
Technical details and the full account trace expand on demand. Mobile tables
scroll within the page with a pinned size/year column and a visible scroll hint.
Tabs support arrow keys, Home and End; exact saved values remain downloadable.

## Inspect through the existing portal

1. Open the completed source backtest:
   `http://127.0.0.1:8000/#backtests/report/d63265dc923444c799c2dfc59e090e76`.
   Click **Configure prop analysis**, then open saved local result
   `77721af3a12941a6a534030541213f1c`. Direct link:
   `http://127.0.0.1:8000/#backtests/prop/job/77721af3a12941a6a534030541213f1c`.
2. **Overview**: expect **$2,005.43 average**, **$0.00 median**, **32.0% receiving
   a payout**, **83.7% drawdown failures**, and **68.0% receiving no payout**.
   Payouts are before acquisition costs. The failure rate overlaps paid accounts;
   it must not be added to the three payout groups. First-payout timing is
   **20 / 28 / 37 trading days**, conditional on receiving a payout.
3. **Evaluation**: expect **25 MNQ**, **34.1% pass rate**, **$272.74** average
   acquisition cost and **19.5 trading days** average funding time. Expand the
   cost formula or full-precision values to inspect the saved inputs.
4. **Sizing**: expect **9 MNQ Selected** first under annual-net sorting. Its
   training annual net is **$6,414.85 per slot**. The visible selection assumptions
   are **52.5% pass / 5 replacement days**. Sorting by size puts **1 MNQ** first;
   it changes row order only. These are training results, distinct from the
   holdout overview. All sizing columns remain in CSV and full-precision details.
5. **Historical replay**: expect **20 slots**, full-window **$770,000 payouts**,
   **$114,549 acquisition costs**, **$655,451 net**. This is one shared observed
   trade path, not an annual forecast. Expand the trace to inspect **21 accounts**.
6. **Source & model**: inspect training/holdout ranges, **702 measured MAE trades**,
   source reconciliation, account rules, seeds, model identity and downloads.
   **Report data (JSON)** retains the exact mean **2005.425** and pass rate
   **0.3409**; the UI rounds display values only. Reload or reopen the saved job:
   the Overview returns without submitting another simulation.
7. At 390 px or 320 px width, the page fits the viewport; scroll the tab strip
   and tables horizontally. Arrow keys/Home/End keep the focused tab visible.

## Actual workflow evidence and checks

Run from the repository root:

```sh
.venv/bin/python scripts/demo_native_prop.py
.venv/bin/python -m pytest -q
```

The first command follows the real backtest → configure → check → run → saved
report journey on an isolated temporary server. It uses the original real source,
normal API and local calculation worker, downloads JSON/ZIP, reloads and reopens,
then compares the independently generated calculations with the supplied reference.
The server stops automatically. It leaves the user's port-8000 server alone.

Actual new run: `artifacts/native-prop-parity-20261026T181809Z/`, job
`a325d3f154bb4bcd8345b06d0efa5f82` in that isolated snapshot. `source-check.png`,
`report.png`, `report.json`, `analysis.zip`, `production-io.json` and
`validation.json` show **637 exact comparisons passed**, no browser errors and
reload/reopen without a POST. The production worker's only subprocess was
read-only Git provenance; it did not access external generated results.

`artifacts/funded-ui-review-20261026T175950Z/` contains:

- `assessment.md`, `before-desktop.png`, `before-mobile.png`, plus final
  `after-overview-{desktop,mobile,narrow-mobile}.png`, `after-top-*.png`, and
  `after-{evaluation,sizing,history,model}-{desktop,mobile}.png`.
- `ui-validation.json`: all five views fit 1440/390/320 px, visible independently
  expected values, sorting and keyboard navigation, exact JSON download, no
  browser errors or POSTs during tab/reload inspection, and temporary server stop.
- `original-report.json` / `after-report.json`: byte-identical existing portal
  report. All **13** saved manifest-file hashes still match. The financial
  source tree is unchanged, and fresh calculations equal the existing saved run.
- `capture_review.py`: reproduce the screenshot/immutability inspection with
  `PYTHONPATH=. .venv/bin/python artifacts/funded-ui-review-20261026T175950Z/capture_review.py`.
  It uses the saved isolated run above and stops its temporary server afterward.
- `full-tests.txt`: **571 passed**, 24 existing dependency warnings, 91.51 seconds.
  Browser checks include the real synthetic-source zero-pass workflow (funded
  outputs unavailable), missing cost/time values, disclosed close-only fallback,
  negative historical cash, sorting, keyboard navigation and exact downloads.
  Synthetic response fixtures are confined to presentation tests; the product
  demonstration and saved screenshots above use the actual source calculation.
  `final-browser-tests.txt` records the focused browser rerun after the final
  table scroll hint and wording adjustment.

Starting HEAD: `abc65f4`; recovery ref: `recovery/funded-ui-20261027`;
working branch: `work/funded-ui-20261027`. Earlier evidence and saved results are
preserved. No persistent server was started for this increment.

---

# Current workflow: AlphaQuest calculates the prop simulation locally

The external-engine integration was the wrong implementation and is retired.
AlphaQuest now owns source adaptation, account state transitions, Monte Carlo,
sizing, payouts, economics, historical account replay and chart generation.
New reports are format 3 / `alphaquest-apex50k-eod-v1`. No vendor executable,
DLL, Windows/Parallels dependency or generated external report is used to produce
a result. Reference files are read only by the independent comparison harness.
Prior saved reports, datasets, backtests and evidence remain unchanged.

Open the independently generated report:
`http://127.0.0.1:8000/#backtests/prop/job/77721af3a12941a6a534030541213f1c`.
Its evaluation, funded accounts, sweeps, cash totals and charts come entirely
from the local implementation. Earlier result IDs remain historical snapshots.

## Reproduce through the actual portal

1. Open completed backtest
   `http://127.0.0.1:8000/#backtests/report/d63265dc923444c799c2dfc59e090e76`.
2. Click **Configure prop analysis**. The fully matching original MultiCharts
   XLSX in Downloads is selected automatically. Keep Chicago export timestamps,
   $49 evaluation, $129 activation, block 5, 20 slots, max NQ 4 and blank holdout.
3. **Check source**: expect 702 matched trades, 702 measured MAE/MFE, source net
   77561.04, 1004 training and 431 holdout weekdays. Source reference gross
   80355 - commission 2793.96 - slippage 0 = 77561.04. Original UTC identities
   match every export row; the dataset's saved New York timezone is preserved.
4. **Run analysis**. Progress reports local calculation stages. Standard counts
   remain 3,000 per sweep point, 20,000 final evaluations and 20,000 accounts per
   funded horizon. The real source takes approximately 20–40 seconds locally.
5. Use the Overview, Evaluation, Sizing, Historical replay and Source & model
   views. Inspect account traces and yearly slot cash; three local SVG charts
   remain in downloads. Download report.json, calculations.json,
   source trades, size sweeps, quarterly/yearly cash, chart-data JSON and ZIP.
6. Reload, return to the backtest/configuration and reopen the saved result.
   No simulation is submitted again. Source/backtest/report inputs are immutable.

Independent expected values from the supplied reference:

| Output | Expected |
| --- | --- |
| Evaluation size / simulations | 25 MNQ / 20000 |
| Passed / DD failures / timeout | 6818 / 13037 / 145 |
| Pass probability | 0.3409 |
| Wilson interval | [0.3343616454112101, 0.34749946270714255] |
| Acquisition cost | 49 / 0.3409 + 129 = 272.7371663244353 |
| Days to funding, mean / median | 19.519 / 14 |
| Funded chosen size | 9 MNQ |
| First-year mean / median | 1889.6 / 0 |
| Lifetime mean / median | 2005.425 / 0 |
| Blown / all-six probabilities | 0.8373 / 0.0974 |
| First-payout median day | 20 |
| Account trace | 21 accounts, identical start/end/outcome/payout dates |
| Slot payouts / acquisition costs / net | 770000 / 114549 / 655451 |

Important reproducibility details: retain the matched original Excel float
representation of reconciled net amounts, keep sampled blocks continuous across
failed attempts within a chain, use independent first-year/lifetime runs, and
sum rounded quarters to obtain yearly cash. Fixed training selection economics
(52.5% pass / five replacement days) remain distinct from holdout acquisition
metrics, and are exposed on the report. These are preserved analytical model
assumptions, not provider-rule certification.

## Validation commands and actual evidence

```sh
.venv/bin/python scripts/demo_native_prop.py --publish-url http://127.0.0.1:8000
.venv/bin/python scripts/verify_native_prop.py <native-report.json> /Users/yx/Downloads/20261026_171955
.venv/bin/python -m pytest -q
```

The reproduction script uses an isolated APFS copy of the source backtest and
SQLite backups on a temporary server, follows the actual browser journey, checks
reload/reopen/downloads, then optionally submits a separate real local run to the
existing portal. Its production-thread audit rejects external executable/DLL
reads, generated report.html/results.json reads, and all subprocesses except
read-only Git provenance. It saves screenshots, downloaded JSON/ZIP, production
I/O, and field-by-field reference comparisons. The existing user server and VM
are left alone; temporary servers stop in finally.

Actual complete workflow evidence:
`artifacts/native-prop-parity-20261026T142456Z/`:

- `source-check.png`, `report.png`, downloaded `report.json` and `analysis.zip`.
- `validation.json`: **637 exact comparisons passed** for both the isolated
  browser job `a5f546499e31463b8f77d5858da35700` and separately published portal job
  `77721af3a12941a6a534030541213f1c`. No floating tolerance or overlapping-CI
  substitution is used: all compared values are equal. This includes every
  reference sizing-row metric, evaluation counts/probabilities/CI/acquisition
  values, funded means/medians/probabilities, 21 historical account traces,
  annual cash rows/totals and chart values.
- `production-io.json`: worker file/process audit. No executable/DLL or generated
  external results were accessed. The sole subprocess was `git rev-parse HEAD`
  for provenance. Runtime calculations used native fills and the original
  measured-excursion export; external reference files are opened only afterward
  by the independent comparator.
- `published-report.json`: separately saved real local result from port 8000.
  `actual-portal-report.png`, `actual-portal-summary.png` and
  `actual-portal-validation.json` verify the final published report in Chromium,
  including three locally generated SVGs, no POSTs/errors/external result assets,
  and unchanged qualified calculation-source hashes. `reference-identity.json`
  pins the original HTML/JSON/CSV/chart files and confirms its displayed values.
- Browser errors: none. Reload/reopen caused no new POST. Historical report JSON
  matches the preserved snapshot. The temporary server stopped successfully.
- Full suite: **569 passed**, 24 existing dependency warnings, 80.81 seconds.
  Full output: `artifacts/native-prop-parity-20261026/full-tests.txt`.

Earlier prototype comparisons remain under `artifacts/native-prop-parity-20261026/`
and are not qualification evidence: one intentionally retained failed comparison
identified the export/native floating-representation discrepancy subsequently
resolved by preserving the reconciled original export representation.

Deterministic unit checks independently establish full-cap payout amounts and
approval-day boundaries, DLL vs account-floor ordering, inactivity boundaries,
consistency equality, prior-close tiers, MT19937 circular blocks, activation-day
counting, quarter rounding, and calculation without file/process access. API and
browser checks use the real local engine on a labelled two-session synthetic
backtest (80 gross - 8 commissions - 20 slippage = 52 net). It has zero evaluation
passes, so funded/acquisition-dependent outputs are explicitly unavailable.
Corrupted/mismatched export, unknown settings, wrong timezone, unsupported model
choices, duplicate active submissions and failed operation downloads are tested.
Native-only sources disclose the close-only excursion fallback; no measured
excursions or history are manufactured. Unsupported overlapping trades reject.

Starting HEAD: `4388e48`. Recovery ref:
`recovery/native-prop-parity-20261026T135740Z`.
Backup: `/Users/yx/.codex/workspace-backups/native-prop-parity-20261026T135740Z/`.
Working branch: `work/native-prop-parity-20261026T135740Z`. No push or merge.

---

# Historical external-engine replay record (retired)

The record below describes the rejected external runner, not the current local
calculation workflow. Earlier successful replays are not independent-engine
qualification. All associated saved artifacts remain preserved.

# Current workflow: The Bridge report parity

New prop analyses now invoke the **licensed The Bridge Funded Lab CLI**. This
supersedes the old notebook for new runs and reproduces the user's reference
`/Users/yx/Downloads/20261026_171955/report.html`. Financial calculations are not
reverse-engineered or fitted to expected values. The previous reports and saved
evidence below remain historical snapshots and have not been rewritten.

## Use the matching report

Open `http://127.0.0.1:8000/#backtests/prop/job/2a2f17774703424cb28aef3a24a97728`.
This is a new Bridge run. The earlier job
`863ef30f413b4b32a38cb1a59a543fa3` retains its original notebook numbers and now
shows a **Historical notebook report** notice. Use the new report link when
comparing with the supplied Funded Lab HTML.

## Reproduce from the native backtest

1. Keep the existing Windows 11 VM running with The Bridge licensed. No license
   credentials are copied or bypassed. The installer is not executed.
2. Open the completed backtest:
   `http://127.0.0.1:8000/#backtests/report/d63265dc923444c799c2dfc59e090e76`.
3. Click **Configure prop analysis**. The matching original MultiCharts XLSX in
   `/Users/yx/Downloads/` is automatically selected after full reconciliation.
   Export timestamps: **Chicago (exchange)**. The native dataset's saved timezone
   remains New York; comparisons use original UTC instants.
4. Keep **$49** evaluation, **$129** activation, **block 5**, **20 slots**,
   **max NQ 4**, holdout start blank and additional overrides **{}**. Blank means
   the final 30% of the full historical day grid, not a 2023 date filter.
5. Click **Check source**. Observe **702** matching trades, **702 measured MAE**,
   **702 measured MFE**, source net **77561.04**. Net P&L already includes source
   commissions/slippage. Source reference gross 80355 − commissions 2793.96 −
   slippage 0 = 77561.04; no duplicate trading-cost deduction.
6. Click **Run analysis**. Progress follows the actual Bridge run.log sections.
   Standard counts are preserved: 20000 final simulations, 3000 sweep simulations
   as resolved by The Bridge. Wait for the durable report.
7. Reload, return to the backtest/configuration and reopen the saved report.
   No operation is resubmitted. Saved reports, charts and downloads work without
   running The Bridge or the VM. Download report.json, trades.csv, analysis.zip,
   and the individual captured Bridge files listed below the report.

Independent expected observations from the supplied HTML and adjacent JSON/CSV:

| Output | Expected |
| --- | --- |
| Evaluation size | 25 MNQ |
| Evaluation pass | 0.3409; displayed 34.1% |
| Evaluation 95% interval | [0.3343616454112101, 0.34749946270714255] |
| Evaluation DD / timeout | 0.65185 / 0.00725 |
| Acquisition cost | 49 / 0.3409 + 129 = 272.7371663244353; displayed $273 |
| Trading days to funded | 19.519; displayed 19.5 |
| Funded selected size | 9 MNQ |
| First-year expected payouts | 1889.6; displayed $1,890 |
| Lifetime expected payouts | 2005.425; displayed $2,005 |
| Lifetime median | 0; displayed $0 |
| Lifetime blown probability | 0.8373; displayed 83.7% |
| First payout median day | 20 |
| Train / holdout | 2021-01-05–2024-11-08 / 2024-11-11–2026-07-06 |
| Day grid | 1004 train + 431 validation = 1435 weekdays |
| Yearly slot net total | displayed $655,451 (Bridge's own rounded table) |

The portal renders Bridge's formatted table strings and original chart PNGs.
It does not recompute or substitute the older notebook's statistics, payout policy,
DLL clipping or acquisition pass probability.

## Actual evidence and exact comparisons

Initial direct CLI replay: `artifacts/bridge-blackbox-parity-20261026/`, including
original settings form, explicit invocation, logs and all newly generated outputs.
Command: installed `TheBridge-Hosted.exe funded-lab --files ... --settings ... --out ...`
through Parallels current-user execution. This returned a successful real-data run.

Actual portal demonstration and publication:
`artifacts/bridge-portal-parity-20261026T114403Z/`:

- source-check.png and report.png from real Chromium on a temporary server.
- report.json and analysis.zip downloaded by clicking normal product links.
- validation.json with **20 exact comparison groups**: complete account/settings,
  file/date metadata, part1, part2, warnings/session note, all eight CSV tables,
  and all three chart PNG byte hashes.
- published-report.json for the new job in the user's existing portal, separately
  compared to the supplied reference. The output itself is freshly calculated.
- An isolated APFS copy-on-write backtest/data snapshot for the temporary server.
  The source catalogue and original files were preserved; the temporary server
  was stopped in finally. The existing user server/VM were not stopped.

A repeat on the final implementation is saved at
`artifacts/bridge-portal-parity-20261026T120145Z/`. Its temporary and published
runs again pass all 20 groups. Additional `display-validation.json` verifies
**23 groups** including every displayed report section, chart data and chart
metadata against the reference. Only the Saved files section is excluded from
section equality because each real run has new timestamped output filenames.
The published repeat is job `2a2f17774703424cb28aef3a24a97728`.
The full suite passed **567 tests** (24 existing dependency warnings); the final
focused Bridge/API/browser checks passed **12 tests**. The repeat also includes
`actual-portal-report.png` and `actual-portal-validation.json`: Chromium opened the
published job on port 8000, checked the visible financial values, observed no
browser errors or POST submissions, and verified that the historical report JSON
still matches the preserved snapshot.

Earlier repeat attempts at `...T114955Z` and `...T115530Z` failed on Parallels
guest RPC before publication; their catalogue errors remain inspectable. The
runner retries only its read-only identity probe and reports analysis transport
errors without automatically submitting another run. The final repeat passed
on both the isolated server and the existing portal. Temporary servers stopped.

Reproduce the complete browser journey and comparisons from the repo root:

```sh
.venv/bin/python scripts/demo_bridge_parity.py
```

To additionally create a fresh durable report through the user's already-running
portal API after the isolated-server checks pass:

```sh
.venv/bin/python scripts/demo_bridge_parity.py --publish-url http://127.0.0.1:8000
```

Every rerun uses a new timestamped evidence directory and new result ID. Creation
timestamps, staging/output paths and timestamped filenames differ naturally;
financial values, tables and chart bytes match the reference. Original report
HTML is saved unaltered as a downloadable attachment, alongside results.json and
all native CSV exports. The ZIP also captures input XLSX, form settings, executable
identity and input/settings/native-source hashes.

## Rejections, limits and dependency

API/unit/browser checks cover source/UTC/cost reconciliation, corrupted XLSX,
wrong timezone, unknown settings, unsupported product/count choices, invalid
prices, explicit alternate 109+0 pricing, duplicate active submissions, missing/
failed/demo Bridge results, unqualified executable hash, immutable reopening,
manifest-only file downloads and completed ZIP consistency. Source cost math is
independent of caller Decimal precision. Fake runners are test transport stubs;
the actual product demonstration and parity comparisons use the licensed engine.

The supported first Bridge integration fixes Apex 50K EOD, standard simulation
size, slot-year sizing objective and full-cap payout requests to this reference.
Other native sources currently need a fully matching MultiCharts export; missing
excursions are not manufactured to make a backtest eligible. Windows/Parallels,
macOS Home sharing and an active Bridge license are execution dependencies.
The executable is pinned to version 2.9.5.0 / SHA-256
`4b0032d156072fc3aa290c2ac21a644b449e7ccf64335f918a02729250495a61`.
A vendor update needs fresh qualification before changing the expected build.
The closed-source engine's internal correctness has not been independently
proved; this delivery establishes parity with its actual qualified behavior.

Starting HEAD was `0940747f892614bf122c479cec0dbb39b76f717d` with a clean workspace.
Recovery ref: `recovery/bridge-parity-20261026T113459Z`.
Backup: `/Users/yx/.codex/workspace-backups/bridge-parity-20261026T113459Z/`.
Working branch: `work/bridge-parity-20261026T113459Z`. No push or merge.

---

## Historical notebook delivery record

The following earlier commands and UI instructions refer to checkout `0940747`
and the former notebook model. New operations use the Bridge workflow above.
The original notebook qualification modules/tests remain historical references;
they are not a second active portal simulator.

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

## Compact optimization source compatibility — 27 October 2026

New optimization trials retain compact Backtest reports: all metrics, original
trade CSV fields and trade-close equity remain. Source identity, exact cost
reconciliation and native prop calculations use the same inputs as before.
The omitted per-bar equity JSON is not an input to prop analysis. No measured
MAE/MFE is removed or fabricated; native-only sources retain the disclosed
realized-loss fallback. Earlier saved results and reference evidence remain unchanged.

The demonstration uses the actual Datasets → Optimizations → Backtest report →
Configure prop analysis → Check source → Run → durable result workflow. Evidence:
`artifacts/optimization-compact-review-20261027/test_compact_storage_and_norma0/`.
It contains the labeled synthetic source CSV, normal catalogues/reports, report
downloads, full-detail replay, source-check/results screenshots and independent
expected observations in `verification.json`. The owned test server stopped.

Reproduce with a new evidence directory:

```bash
.venv/bin/python -m pytest tests/test_optimization_compact_browser.py -q --basetemp artifacts/optimization-compact-review-NEW
```

Manual steps and expected observations:

1. Upload the saved `SYNTHETIC-compact-report.csv` through Datasets as a synthetic
   source, UTC, tick size 0.25 and monetary point value 10. It contains 2,880
   minute bars over 5–6 January 2026, with exactly one trade per weekday.
2. In Optimizations, fix green count at 3 and hold minutes at 20. Try contracts
   1–2 with step 1; slippage 1 tick per fill, commission 1 per contract per side.
   Expect two rows with **26.00** and **52.00 CU** net. Independently: each day
   enters at 100.25, exits at 101.75, gross 15 minus commission 2 = net 13 per
   contract. No second charge for slippage is applied to the saved net value.
3. Open the one-contract Backtest report. Its compact notice, chart, trades and
   downloads work. **Generate full detail** produces a separate gzip report;
   all 2,881 equity events are retained and both CSVs exactly match. The original
   compact files remain byte-identical.
4. Return to the compact report and click Configure prop analysis. Enter
   `{"unsupported_storage_test":1}` in additional overrides and Check source:
   expect an explicit unknown-setting rejection and disabled Run. Restore `{}`
   and check again: expect two trades, source net **26.00**, measured MAE count
   **0**, and the native fallback disclosure. Do not supply a fabricated export.
5. Run with standard defaults. Expect validation evaluation pass rate **0** and
   funded outcomes explicitly unavailable: repeating this small daily return
   cannot reach the evaluation target within its deadline at the supported sizes.
   These are actual local calculations, not invented future outcomes. Download
   Report data JSON, reload, return through Backtest/configuration and reopen
   the saved analysis. The source identity, net costs and unavailable funded
   result remain unchanged, with no recomputation on reload/reopen.

The saved one-contract files total 3,718 bytes versus 551,057 bytes for a full
ordinary backtest of identical inputs (99.33% reduction in this example). The
compressed detailed JSON is 19,702 bytes. Automated checks also cover corrupt
events/truncated streams, zero-trade reports, missing/changed replay inputs,
replay mismatch rejection, duplicate detail generation, serial/process parity,
and direct read-only snapshot hashing without a per-worker input copy.

## Reusable optimization acceleration — 27 October 2026

Optimization now prepares selected bars once for multi-wave jobs, supports
optional pure-feature streams and reuses verified identical completed trials.
The production prop calculations and source adaptation stay local. The normal
optimization result still opens a durable Backtest report, which supplies the
existing Configure → Check source → Run → saved analysis journey.

That complete journey was rechecked under
`artifacts/optimization-acceleration-portal-20261027/test_compact_storage_and_norma0/`.
Its actual source, saved catalogues, report/analysis downloads and screenshots
remain inspectable. Use the compact-review reproduction steps above and expect
net **26 / 52 CU**, one-contract source net **26 CU**, zero measured MAE trades
with the existing fallback disclosure, unsupported-setting rejection, evaluation
pass rate **0** and funded outcomes unavailable. The report reopens without
rerunning. This result verifies integration; it makes no new profitability or
notebook-parity claim. That review's temporary server has stopped.

Reuse is separately demonstrated at
`artifacts/optimization-acceleration-portal-20261027/test_reuse_toggle_badges_reope0/`.
Run the three-contract arithmetic grid twice with reuse enabled: expect net
**13 / 26 / 39 CU**, the same report IDs, **3 reused · 0 computed**, and three
Backtest reports total. The reused report still opens normally. Uncheck reuse
and run again: expect **0 reused · 3 computed** and six reports total. The saved
`reuse-verification.json` and screenshot record these observations. Earlier
reports/evidence and the user's datasets/results were preserved.

Repeat both checks with a new evidence directory:

```bash
.venv/bin/python -m pytest tests/test_optimization_compact_browser.py \
  tests/test_optimization_browser.py -k 'compact_storage or reuse_toggle' \
  -q --basetemp artifacts/optimization-acceleration-prop-NEW
```

These tests own and stop their temporary servers. General worker/feature timing
and exact replay checks are documented in `docs/optimization.md` and
`docs/strategy_features.md`; they are research-engine capabilities rather than
strategy-specific prop calculations.

The final source also passed the complete **691-test** suite, with the same
normal report → configure → reject unsupported setting → check source → run →
durable-result journey retained under
`artifacts/optimization-acceleration-final-suite-20261027/test_compact_storage_and_norma0/`.
The companion `test_reuse_toggle_badges_reope0/` contains the final reuse UI
verification. These final runs confirm the observations above after the shared
feature pass and bounded bar serialization improvements. All owned test servers
stopped; the user's existing server/processes and stored results were preserved.

## Automatic default Apex analysis — 27 October 2026

New portal/API backtests, CLI backtests and trials in new optimization jobs now
perform the default source check and full local analysis automatically. Profile:
Apex 50K EOD, $49 evaluation, $129 activation, 20 slots, block 5, ordinary 70/30
weekday split and standard counts. Every saved backtest links to the existing
prop report, and optimization rows show sortable **Historical net · USD** near
the left of the table. Native fills retain their net costs; the absence of
measured excursions remains explicit. No external engine/VM is invoked.

The actual product demonstration is retained at
`artifacts/automatic-apex-prop-verified-suite-20261027/test_automatic_apex_backtest_o0/`:

- `SYNTHETIC-automatic-apex-cash.csv`, normal dataset/backtest/prop catalogues and
  report files; `verification.json` records actual IDs, expected cash and checks.
- `automatic-backtest.png`, `historical-cash-and-fees.png`, `source-check.png`,
  `configured-optimization.png`, `optimization-historical-net.png`,
  `optimization-reused.png`, `mobile-results.png`.
- `default-prop-report.json`, `optimization-results.csv`, complete source/trade,
  account, quarter/year, sizing and chart downloads in the normal report folders.

The earlier demonstration under `artifacts/automatic-apex-prop-portal-20261027/`
is preserved. The final screenshots above show the completed automatic report,
separate evaluation/activation fees, linked Historical net column and its N/A
explanation, highlighted frozen parameter columns and mobile scrolling.

All numbers below come from an actual default-count calculation with independent
arithmetic expectations. The source is explicitly synthetic, contains 60
weekdays beginning 5 January 2026 and has three bars at 18:00–18:02 UTC each day.
The first bar goes 99→100; the second 100→103; the third is a 103 doji. Tick size
is 0.25 and the artificial monetary point value is 1,000, labelled synthetic.
With green count 1, hold 1 minute, one contract, zero commission/slippage, exactly
one trade earns `(103−100)×1,000 = 3,000` each day: source net **180,000**.

Independent default-model expectations:

1. Every evaluation path passes at every sizing point. Grid ties choose **1 MNQ**,
   earning 300 per day, reaching 3,000 on day 10. Funding delay adds one activation
   day: **11 weekdays**. Acquisition cost is `49 / 1 + 129 = 178`.
2. The fastest full-ladder training tie begins at **3 MNQ**. It earns 900 per day;
   six payouts occur after 30 weekdays and total **13,000**. All larger tied
   sizes retain the earlier size. Final funded simulations retain **20,000**
   accounts, and each sizing row retains **3,000** paths.
3. Historical account 1 uses 30 sessions. After an 11-session replacement wait,
   account 2 has 19 sessions remaining and pays 1,500 + 1,500 + 2,000 = **5,000**.
   Across 20 slots, payouts are `(13,000+5,000)×20 = 360,000`, acquisition costs
   are `2 starts×20 slots×(49+129) = 7,120`, and **Historical net = 352,880**.
   There are 40 funded starts across all slots. These are deterministic outcomes
   of this synthetic input/model, not fabricated future returns.
4. Green count 2 instead enters at 103 and closes at the same price. It retains
   a completed default analysis with zero validation passes, unavailable funded
   outcomes and Historical net **N/A**. N/A sorts after 352,880 in either sort
   direction. A one-session source rejects before calculation and also shows
   N/A with its source-check reason. Neither case becomes a fake zero cash result.

Reproduce through the real portal:

1. Upload the saved synthetic CSV in Datasets as a synthetic source, UTC, tick
   0.25 and point value 1,000. Validate and save it.
2. In Backtests choose Consecutive green hold, green count 1, hold 1, contracts 1,
   capital 10,000, slippage 0 and commission 0. Run and wait through the Apex
   calculation stages. Expect source net 180,000 and the new **$352,880 Historical
   net** card. Open its default prop analysis; Historical replay shows payouts
   360,000, costs 7,120 and 20 slots. Download its report data.
3. Return to the Backtest and Configure prop analysis. The activation field is
   129. Enter `{"unsupported_automatic_test":1}` in additional overrides and
   Check source: expect rejection and disabled Run. Restore `{}`, check again:
   expect source net 180,000, 60 trades and no measured MAE. Run with default
   settings to reopen the already completed automatic analysis, without another
   simulation or duplicate report.
4. Open Optimizations with the same source/costs. Green count start 1/end 2/step
   1; hold 1 fixed; contracts 1 fixed; choose two workers if available. Expect
   two rows with Historical net **352,880 / N/A**, each linking to its own
   ordinary prop report. Inspect the unavailable row's actual explanation.
5. Sort Historical net ascending and descending; 352,880 remains before N/A.
   Results CSV contains the same values, prop IDs, statuses and reasons. Open a
   linked report, reload and reopen the job. Rerun with identical inputs and reuse
   checked: expect **2 reused · 0 computed**, the original report IDs and three
   total Backtest reports (one standalone plus the original two trials).
6. Inspect fees, samples, source identity, CSVs and JSON at full precision. The
   original standalone report remains byte-identical after every operation.
   On mobile, the table scrolls inside the page and stepped parameters remain
   frozen. The owned browser test server is stopped on exit.

Generate a fresh retained demonstration:

```bash
.venv/bin/python -m pytest tests/test_automatic_prop_browser.py -q \
  --basetemp artifacts/automatic-apex-prop-review-NEW
```

Backend qualification, including exact cash, full counts, parallel trials,
reuse, rejected/failed sources, report corruption, CLI/catalogue integration,
legacy readers and safe publication rollback:

```bash
.venv/bin/python -m pytest tests/test_automatic_prop.py tests/test_native_prop_engine.py -q
```

Read-only independent inspection of the actual saved product outputs and prior
user files, without importing production calculation code:

```bash
.venv/bin/python artifacts/automatic-apex-prop-delivery-20261027/verify_delivery.py
```

Expect source net 180,000; payouts 360,000; acquisition fees 7,120; Historical
net 352,880; standard simulation counts retained; 70 protected files and 21
compressed backtest archives unchanged; original optimization job/trial
payloads unchanged; 72 existing prop artifact hashes matching their saved
manifests. The script saves `independent-verification.json` alongside itself.

Final validation on `work/automatic-apex-prop-20261027` (starting HEAD `604cd9f`):
**705 passed**, 24 dependency/notebook deprecation warnings, **516.57 seconds**.
Command: `.venv/bin/python -m pytest -q --basetemp artifacts/automatic-apex-prop-verified-suite-20261027`.
The full run includes the actual browser workflow above, the single-snapshot
polling regression, engine/settings reuse invalidation, and neutral-trade
equivalence checks. `artifacts/automatic-apex-prop-delivery-20261027/validation.json`
pins the production engine identity and independent evidence. No persistent
test server was started; fixture-owned servers stopped. Existing user processes
were left running. The increment is local and has not been pushed.

The neutral-trade optimization keeps the first exact-floor check in each
consecutive zero-net/zero-adverse run, leaving all original source rows in their
exports. Independent comparisons against the ordinary uncompressed evaluation
and funded calls match every outcome, account state and seeded draw sequence,
including an account beginning at its exact floor. No simulation count is
silently reduced. This increment changes orchestration/reporting and removes
redundant checks; it does not claim a new provider-rule or external-model parity
qualification beyond the locally qualified numerical model.

## Prop summary inside the backtest report — 27 October 2026

Open an ordinary completed backtest report. **Prop analysis summary** now follows
**Trade-close equity**, before **Every completed trade**, without navigation to
configuration or a particular analysis. It selects the recorded default analysis
for new backtests and the most recent completed saved analysis for older ones.
The selected analysis ID and its settings are visible. Viewing a report reads its
existing results and does not run analysis, change saved reports or discover
exports. The equity chart and trades remain usable if the prop request fails.

Actual product evidence is retained at
`artifacts/inline-prop-summary-final-20261027/test_automatic_apex_backtest_o0/`.
The labelled synthetic source goes through the normal upload/backtest workflow,
then configure/check/run/reopen, a parallel optimization and durable reports.
Independent expectations are the cash arithmetic in the previous section:
**360,000 payouts − 7,120 evaluation/activation costs = 352,880 Historical net**,
evaluation pass rate **100%**, and acquisition cost **178.00** per funded start.

1. Upload `SYNTHETIC-automatic-apex-cash.csv` from that folder with UTC, tick 0.25
   and point value 1,000. Run Consecutive green hold with green count 1, hold 1,
   contracts 1 and zero commission/slippage.
2. Scroll directly below Trade-close equity. Expect Historical net **$352,880**,
   historical payouts **$360,000**, acquisition costs **$7,120**, 20 slots, $49
   evaluation and $129 activation. Evaluation passes **100%** and average
   acquisition cost is **$178.00**. Funded-account payouts are labelled separately
   from historical slot cash; the close-only excursion fallback is disclosed.
3. Download **Report data (JSON)** from this summary. Its bytes equal the existing
   saved report. **Open full analysis** goes directly to that analysis. Returning
   or reloading shows the same saved values, with no new calculation POST.
4. The two-trial optimization from the prior instructions produces a second
   zero-P&L trial. Open its Backtest report: expect Historical net/payouts/costs
   **N/A**, evaluation pass **0%**, no funded payout cards, and the actual
   no-validation-pass explanation. Unsupported one-session sources show their
   rejection reason. An older report without a saved analysis shows instructions
   to configure one, without an invented zero result.

`inline-prop-summary.png`, `inline-mobile.png` and `inline-no-pass.png` capture
these actual result states. `default-prop-report.json`, `optimization-results.csv`
and normal dataset/backtest/analysis folders retain inspectable outputs.
`verification.json` records exact values, placement, byte-identical downloads,
reload without calculation, source-check rejection and mobile checks. The older
metadata lookup is exercised using a browser-only adaptation of the synthetic
record's metadata; the original record and saved report stay unchanged. Separate
presentation checks cover no saved analysis and a controlled HTTP 503, keeping
the equity chart usable in both cases.

Reproduce with a new evidence directory (existing evidence remains unchanged):

```bash
.venv/bin/python -m pytest -q tests/test_automatic_prop_browser.py \
  tests/test_automatic_prop.py::test_saved_analysis_lookup_skips_export_discovery \
  --basetemp artifacts/inline-prop-summary-review-NEW
```

The browser fixtures start temporary servers and assert their shutdown. No
persistent server is started. Calculations, simulation counts, fees and stored
financial results are unchanged by this presentation increment.

Validation: **3 workflow/lookup checks passed** in 72.06 seconds; **43 existing
report/browser/API regression checks passed** in 99.34 seconds. Final results,
commands and implementation hashes are saved in
`artifacts/inline-prop-summary-final-20261027/validation.json`. Its
`preservation.json` verifies the same 70 protected files, 21 compressed archives,
72 saved prop artifact hashes and original optimization records remain intact.
Earlier workflow screenshots and qualification evidence are preserved.

## Delete a backtest through the portal — 27 October 2026

Completed reports now have **Delete** controls in their list, and each report has
**Delete backtest**. The confirmation identifies the dataset and exact run ID.
Cancel sends no deletion request. Confirm removes only that selected backtest's
catalogue/trade/equity rows and report directory. Its source dataset, other
backtests, completed prop reports and optimization trial metrics are retained.
Saved prop reports remain readable from their own snapshots; calculating a new
analysis requires a source backtest that still exists.

A queued/running prop calculation or active full-detail replay returns a visible
409 explanation and leaves the backtest untouched. Catalogue errors roll back
indexed changes and restore staged report files. If final file cleanup fails
after catalogue removal, the portal reports it explicitly; retrying the same
Delete completes cleanup. No source dataset is deleted. Removing the last report
on a results page returns to the preceding page. An optimization's deleted
Backtest cell shows **Backtest deleted**, with original metrics and prop links
retained. Future optimization reuse recomputes that trial rather than returning
a deleted report.

Reproduce with labelled synthetic inputs through the normal portal:

1. Create two backtests using the same synthetic fixture dataset. Open Backtests
   and press Delete beside one report. Cancel: both reports remain, no DELETE
   is sent and every original file remains.
2. Open that report, press Delete backtest and confirm. Expect navigation to the
   completed reports, one remaining report and an explicit success message.
   The source dataset and the other report remain byte-identical. Reload to
   verify durable removal; the deleted report and exports return 404.
3. Delete the remaining report from the list. Expect **No completed reports yet**,
   with the dataset still available for another backtest.
4. Delete a backtest belonging to an optimization. Reopen the optimization:
   expect its original metrics and prop link, plus **Backtest deleted** in place
   of the report link. Running the same grid reuses unaffected trials and
   recomputes the deleted trial.

Actual retained portal outputs:
`artifacts/delete-backtests-final-20261027/workflow/` contains
`test_delete_from_list_and_repo0/verification.json`, confirmation messages and
`delete-controls-list.png`, `delete-control-report.png`,
`selected-backtest-deleted.png`; `test_busy_analysis_error_and_l0/` contains the
mobile/pagination screenshot; `test_deleted_trial_keeps_optim0/` contains
`optimization-keeps-metrics.png`. These tests delete only fixture-owned reports
in isolated catalogues. Existing user data and earlier evidence are untouched.

```bash
.venv/bin/python -m pytest -q tests/test_delete_backtests.py
.venv/bin/python -m pytest -q tests/test_delete_backtests_browser.py \
  --basetemp artifacts/delete-backtests-review-NEW
```

Backend checks also inject catalogue, rename and cleanup failures, verify
completed prop report bytes after source deletion, and verify per-trial cache
invalidation. Temporary browser servers stop in fixture cleanup; no persistent
server is started by these checks.

Final verification: **11 deletion/API/browser checks passed in 33.33 seconds**,
with production engine identity unchanged throughout. The broader regression run
passed **126** checks; one optimizer-input test was interrupted by concurrent
production-code edits and correctly stopped at its engine-code guard before any
trial. That affected case then passed independently in **3.47 seconds**. No
deletion behavior failed. Commands, file hashes and outcomes are retained in
`artifacts/delete-backtests-final-20261027/validation.json`, with read-only
existing-data checks in `preservation.json`. Earlier test outputs remain intact.

## Backtest runtime improvements — timing instrumentation (increment 1)

New backtests and optimization trial reports include a durable `performance.json`.
Open the normal Backtest report and expand **Runtime breakdown**, below the prop
summary, to inspect source loading, chronological replay, report writing, prop
analysis and publication. Nested work is subtracted from its enclosing phase;
phase totals are not double counted. Download the original timing JSON there.
Historical reports display an explicit unavailable message rather than invented
timings. Diagnostic-file failures do not invalidate completed financial results.

The actual upload -> backtest -> configure -> source-check -> run -> durable
report demonstration is retained in
`artifacts/backtest-runtime-20261027/01-timings/test_automatic_apex_backtest_o0/`.
`runtime-breakdown.png` and `runtime-breakdown.json` show 19.2324 seconds elapsed,
including 19.1044 seconds of prop analysis, 0.0179 source loading, 0.0136 replay,
0.0406 report writing and 0.0550 publication on this labelled synthetic workload.
These are observations for this input and host, not general speed guarantees.
Independent cash expectations remain 360,000 payouts - 7,120 acquisition fees =
352,880 Historical net, with all default counts and exact original downloads.
The same workflow covers unsupported/no-pass sources, unknown-setting rejection,
reopen, sorting, native cost conservation and no recalculation on reload.

Reproduce with a fresh directory:

```bash
.venv/bin/python -m pytest -q tests/test_backtest_runtime.py \
  tests/test_automatic_prop_browser.py \
  --basetemp artifacts/backtest-runtime-review-timings-NEW
```

For function-level profiling of a normal CLI run, use
`python -m cProfile -o <new-file.pstats> -m alphaquest.run_backtest <normal arguments>`.
Compare unprofiled end-to-end runs for speed claims. Timings and profiling do not
enter financial calculations. Test servers stop through their normal fixtures.

### Increment 2 — compact standalone reports

Portal/API and CLI backtests now default to compact reports, retaining every
trade, trade-close equity row, metric, prop result and source check. The existing
**Generate full detail** action replays the exact source, verifies trade/equity
CSV hashes and saves a separate compressed full report; it retains the original
prop analysis. API `report_detail: "full"` and CLI `--report-detail full` explicitly
request per-bar JSON at first execution. Existing reports remain unchanged.

Actual cash/source-check/browser evidence:
`artifacts/backtest-runtime-20261027/02-compact-verified/test_automatic_apex_backtest_o0/`.
Upload the prior synthetic cash source, run normally, inspect the compact-report
notice, expand Runtime breakdown, then inspect/configure/check/reopen its prop
analysis. Historical net remains **352,880**, payouts **360,000**, fees **7,120**.
The dedicated runtime check requests full detail and independently verifies equal
summaries, original prop ID and byte-identical trade/equity downloads.

`artifacts/backtest-runtime-20261027/02-report-benchmark/verification.json` retains
two fresh full/compact pairs over 20,000 explicitly synthetic flat bars through
the normal APIs. Independent expectations: zero entries/P&L, final equity 10,000,
and incompatible prop input with no fabricated statistic. All CSV hashes match.
Median wall times: **3.2732 s full / 1.3970 s compact (2.34x)**; report bytes:
**3,612,626 / 3,728**. This isolated I/O workload is not trading evidence or a
general speed guarantee. Source loading and calculation still run normally.

Reproduce the retained benchmark with a new directory:

```bash
PYTHONPATH=tests:. .venv/bin/python tests/review_backtest_runtime.py \
  --output artifacts/backtest-runtime-reports-NEW --bars 20000 --repeats 2
```

Validation: **155 checks passed**, covering runtime/CLI, exact independent
financial fixtures, API, dates, VWAP, compact/full replay and the normal browser
workflow. Full-array fixture oracles explicitly request full reports. Servers
stop in their normal fixtures; prior reports and evidence remain preserved.

### Increment 3 — compiled prop arithmetic with exact reference qualification

Normal installation builds an optional AlphaQuest-owned Cython extension from
the **same `native_engine.py` source** used by the interpreted reference. Typed
numeric locals remove Python arithmetic overhead in evaluation and account-day
loops. Compiler flags disable fast math and fused floating contraction. The
original NumPy MT19937 calls and stopping/draw order remain unchanged. No vendor
executable, generated external result or Windows VM participates. A missing or
stale binary selects the Python reference; a matching source hash is required.
The compiled binary fingerprint enters reuse identity and the saved report.

Open a normal new Backtest report and expand Runtime breakdown: expect **Prop
engine: compiled** after building. Historical net, cost arithmetic and the normal
configure/check/reopen workflow remain identical. `ALPHAQUEST_PROP_BACKEND=python`
selects the reference for qualification; `compiled` refuses a missing/stale build.

Actual standard-count financial comparison and product evidence:
`artifacts/backtest-runtime-20261027/03-compiled/`. In
`test_standard_count_portal_cal0/compiled-verification.json`, both runs used the
same labelled 60-weekday source, normal APIs, default 3,000/20,000 counts and
independent expected net **352,880**. Every calculation field and distribution
matches exactly. Observed prop times were **17.9153 s Python / 11.0983 s compiled**
(about **1.61x**) on this workload. These observations do not guarantee other
workloads' speed. Browser evidence in `test_automatic_apex_backtest_o0/` includes
the durable runtime display, native source checks, downloads and unchanged cash.

```bash
.venv/bin/python -m pip install -e '.[dev,browser]' -c requirements.lock
# Or rebuild an editable checkout after changing the model source:
.venv/bin/python setup.py build_ext --inplace
.venv/bin/python -m pytest -q tests/test_native_prop_compiled.py \
  tests/test_native_prop_engine.py tests/test_automatic_prop_browser.py \
  --basetemp artifacts/backtest-runtime-review-compiled-NEW
```

Validation: **18 checks passed**, including multiple seeds, block lengths,
account sizes, rules, exact-floor hits, repeated funding attempts, every account
state, complete standard-count calculations and the full browser journey. Earlier
reports and benchmark evidence are preserved; fixture servers stopped.

### Increment 4 — bounded parallel native prop sweeps

Independent size sweeps and lifetime/annual validation now share a bounded,
reusable process pool. Seeds, per-size draw order, tie order, standard simulation
counts and chronological historical replay remain unchanged. Optimization workers
execute their prop tasks serially; the coordinator reserves their CPU slots so
standalone prop tasks cannot oversubscribe that budget. Workers never open the
catalogue database. `ALPHAQUEST_PROP_WORKERS=1` selects serial qualification;
the default permits up to four workers, bounded by available capacity.

Run a normal backtest, open Runtime breakdown and inspect Prop workers. Continue
through Configure prop analysis, source checks, run and durable results as in
the preceding browser journey. Results remain reopenable without computation.
Actual evidence: `artifacts/backtest-runtime-20261027/04-parallel/`, including
`test_normal_backtest_runs_stan0/parallel-verification.json` and the separate
`prior-reference-comparison.json`. A labelled 600-trade, 60-weekday source has
independent source net 180,000 and Historical net **352,880**. Every calculation
and distribution matches serial execution and the earlier interpreted reference.
Observed prop runtime: **15.9573 s serial / 10.6502 s two workers (1.50x)**,
including cold worker startup. This is workload-specific, not a promised speedup.

```bash
.venv/bin/python -m pytest -q tests/test_prop_parallel_runtime.py \
  tests/test_native_prop_engine.py tests/test_automatic_prop_browser.py \
  --basetemp artifacts/backtest-runtime-parallel-NEW
```

Validation: **14 checks passed**, including bounded reservations, deterministic
order, child-process refusal to nest pools, exact normal API results, and the
full existing browser journey. Temporary servers and pools stopped normally;
original datasets and earlier evidence are preserved.

### Increment 5 — persistent verified replay and pure-feature streams

Standalone backtests and optimization preparation now share a disposable bounded
cache in `.replay_cache` beside the normal catalogues (default 2 GiB;
`ALPHAQUEST_REPLAY_CACHE_MB` sets its bound). Keys include original metadata,
source checksum, selected dates, timezone bytes and engine/dependency identity.
Every hit revalidates the original CSV checksum/schema/timezone. A cache entry
is copied into the private job workspace and checked against its indexed SHA-256
before decoding. Corrupt or missing entries rebuild from source. Eviction removes
only disposable streams. No positions, orders, fills or account state are cached.
Future strategies can use the existing declared-pure-feature interface; strategies
without declarations still reuse parsed bars without strategy changes.

Run the same source/dates twice through the normal Backtests form. Open Runtime
breakdown on the second report: expect **Parsed source reused**. Trade/equity
CSV downloads and summaries must match the fresh run exactly. Configure/check/
run/reopen the saved default prop analysis as before: source reconciliation and
fees still apply. The API option `reuse_prepared:false` forces ordinary source
reading for qualification. Evidence under
`artifacts/backtest-runtime-20261027/05-replay-cache-verified/` retains a normal
API comparison in `test_normal_backtest_warm_cach0/prepared-cache-verification.json`
and the full existing browser cash-source journey. Boundary checks exercise a
changed original CSV, poisoned cached bytes, bounded eviction and pure-feature
reuse in a new workspace without running feature builders.

Validation: the combined runtime/API/optimization/date/browser run passed 93
checks; two new test setup mistakes were corrected (lazy-generator probe and
registered default construction), then all 25 replay/runtime/date checks passed
under `artifacts/backtest-runtime-20261027/05-replay-cache-final/`. This final
directory contains the corrected warm-cache verification. The browser journey
in the earlier directory passed with exact Historical net and saved downloads.
Reproduce with a new `--basetemp` directory:

```bash
.venv/bin/python -m pytest -q tests/test_replay_cache.py \
  tests/test_backtest_runtime.py tests/test_optimization_acceleration.py \
  tests/test_backtest_api.py tests/test_backtest_date_range.py \
  tests/test_automatic_prop_browser.py --basetemp artifacts/replay-cache-NEW
```

### Increment 6 — verified completed-result and pure calculation reuse

The normal Backtests form now offers **Reopen identical saved results** (checked
by default). Original source integrity, dates, strategy, costs, detail, engine/
dependencies, report/CSV hashes and automatic prop report fingerprints must all
match. A hit reopens the original durable report, without modifying it or
creating a second result store. Uncheck for a new backtest. Deleted/damaged
reports are excluded. Reused API responses are 200 with
`X-AlphaQuest-Reused:true`; fresh responses remain 201. Progress resolves to the
actual reopened ID. CLI shortcuts point to the actual result; `--fresh` bypasses
completed results, prepared streams and prop calculation reuse.

Fresh backtests may reuse pure calculations from another verified local prop
report. Their complete adapted rows, native CSV checksum, excursion identity,
timezone, session grid, settings and engine fingerprint must match. Every new
source is independently adapted, cost-reconciled and checked before reuse.
Workers receive bounded references/checksums, never database connections. New
reports retain their own source backtest ID, captured inputs and downloads;
`runtime.calculation_reused_from` identifies the original calculation. A corrupt
calculation file or changed fee/settings forces fresh arithmetic. No external
report or engine is used. API qualification controls are `reuse_results:false`,
`reuse_prepared:false` and `reuse_calculations:false`.

Actual evidence: `artifacts/backtest-runtime-20261027/06-reuse/` and
`06-reuse-product/`. The normal 60-weekday cash-source comparison in
`test_pure_prop_calculation_reu0/reuse-verification.json` independently checks
Historical net **352,880**, source net **180,000**, payouts **360,000**, fees
**7,120**, all standard counts and every calculation/distribution. Two fresh
backtest IDs preserve their distinct source identities. Measured request wall
times were **11.8478 s cold / 0.4279 s with verified calculation reuse**; the
second still replays the strategy. A third checked request reopens the exact
second report and creates no run. This is an identical-input reuse observation,
not a speed guarantee for new inputs.

User reproduction: upload the labelled synthetic source from the retained
browser directory; set green count/hold/contracts to 1, point value 1000, zero
costs; run, inspect inline cash and Runtime breakdown. Use Configure prop
analysis, verify the invalid-setting rejection, restore valid settings, check
source net and reopen the saved report. Return to Backtests with the same inputs
and the reuse checkbox checked: expect the exact original report ID and cash.
Uncheck and rerun: expect a new ID, **Verified prop calculations reused** and
unchanged cash. Download JSON to inspect the new source ID and reuse reference.
The browser also creates an optimization whose matching trial reuses the first
prop calculation while preserving its own source ID.

```bash
.venv/bin/python -m pytest -q tests/test_backtest_reuse.py \
  tests/test_backtest_api.py tests/test_replay_cache.py \
  tests/test_optimization_acceleration.py tests/test_automatic_prop.py \
  tests/test_backtest_runtime.py --basetemp artifacts/reuse-core-NEW
.venv/bin/python -m pytest -q tests/test_automatic_prop_browser.py \
  tests/test_backtest_reuse.py tests/test_vwap_pullback.py \
  --basetemp artifacts/reuse-product-NEW
```

Validation: **91 core checks and 31 product/VWAP checks passed**. Actual browser
screenshots/downloads include `verified-backtest-reopened.png`, source checking,
rejection, configure/run/reopen, historical cash and optimization results. Earlier
reports remain byte-identical. Temporary servers and pools stopped normally.

### Increment 7 — batched replay progress

Long replays emit progress each 1,000 completed bars, at the final bar, or at a
quarter-second checkpoint checked every 64 bars for expensive strategies. Small
replays retain per-bar updates. Stage transitions and final publication remain
immediate. This avoids a callback, lock and possible IPC attempt for every bar;
financial events, fills, reporting and source checks are unchanged.

Retained normal API benchmark:
`artifacts/backtest-runtime-20261027/07-progress-before/verification.json` and
`07-progress-after/verification.json`. The labelled 20,000-bar flat source has
independent expectations of no entries, zero P&L and unchanged 10,000 equity;
its default prop analysis explicitly has no compatible trade source. Replay
updates fell from **20,001 to 21**, with identical trade/equity SHA-256 hashes,
summary and final processed/total counts. Request times were **1.7064 / 1.6966 s**;
this run demonstrates the callback reduction, not a significant measured wall
speedup. The normal browser cash workflow remains the prop product demonstration.

```bash
PYTHONPATH=tests:. .venv/bin/python tests/review_progress_runtime.py \
  --output artifacts/progress-runtime-NEW --bars 20000
.venv/bin/python -m pytest -q tests/test_backtest_runtime.py \
  tests/test_backtest_api.py tests/test_backtest_reuse.py \
  tests/test_optimization_acceleration.py --basetemp artifacts/progress-tests-NEW
```

Validation: **75 checks passed**, including responsive paused replay, failure/
save boundaries, exact final progress, result reuse and optimization preparation.
Additional worker-budget qualification under `04-budget-qualified/` passed four
checks: standard-count serial/parallel cash equality, concurrent serial-slot
transfer without deadlock, one-worker optimization refusing a nested pool, and
spawned child refusal to nest pools. Serial validation occupies the same shared
budget as parallel tasks. All prior evidence and datasets are preserved.

The final source preparation check also verifies exactly one original-byte read
on both cold and warm preparation and rejects missing/invalid saved timezones
before cache access (`05-source-boundaries/`: seven checks passed). Cold misses
use that same verified snapshot for parsing. Final integrated qualification is
saved as `artifacts/backtest-runtime-20261027/full-suite-final.log` and
`10-full-suite-final/junit.xml`. Reproduce all checks with:

```bash
.venv/bin/python -m pytest -q --basetemp artifacts/runtime-full-NEW \
  --junitxml artifacts/runtime-full-NEW/junit.xml
```

The first complete integration run passed 765 checks and found two obsolete
browser expectations: the submitted payload lacked the new reuse flag, and the
storage comparison relied on the former full-report default. Both now assert
the explicit product settings; the focused browser rerun passed both checks
(`09-browser-expectations/`). Their corrections belong to the corresponding
compact-report and reuse commits. Prior failing-run evidence remains under
`08-full-suite-verified/` and `full-suite-initial.log`; the final log/XML above
records the complete rerun against the committed feature branch.

### Progress display correction — 2026-10-28

Source preparation and pure-indicator preparation each scan bars before strategy
replay. Their independent counters previously filled the same percentage bar,
which then appeared to restart when the next phase began. The normal Backtests
screen now labels both preparation phases explicitly, shows their own counts
without a replay percentage, and starts the percentage bar when strategy replay
begins. The Apex stage explains that replay finished and prop analysis is running
before saving. A 100% replay reading describes bars, not total job completion.

Actual portal evidence is saved under
`artifacts/backtest-progress-labelled-verified-20261028/test_real_preparation_then_rep0/`: source,
indicator and replay screenshots plus `verification.json`. The real registered
VWAP strategy prepares its declared indicators and executes once through the
normal API. Independent expectations on the seven-bar arithmetic source: zero
entries, zero P&L and final equity 10,000. A single POST is observed. Source and
indicator counts reach 7/7 without a percentage; replay then starts once at 0%.
The report remains usable. Additional product evidence under
`artifacts/backtest-progress-workflow-20261028/` covers selected-date completion
and the standard cash-source configure/check/run/reopen/download journey, with
independently expected Historical net 352,880 and source net 180,000.

Reproduce in the portal: choose a dataset and the VWAP strategy, uncheck **Reopen
identical saved results**, then run. During preparation expect **checking source
bars** and **calculating indicators** (the latter can be skipped on a warm cache).
The preparation count describes scanned bars. **Running backtest** introduces
the actual replay percentage; the subsequent Apex/save stages retain completed
replay counts and describe their remaining work. For inspectable paused stages:

```bash
.venv/bin/python -m pytest -q tests/test_backtest_preparation_browser.py \
  tests/test_backtests_browser.py tests/test_backtest_runtime.py \
  --basetemp artifacts/backtest-progress-NEW
.venv/bin/python -m pytest -q tests/test_backtest_date_range_browser.py \
  tests/test_automatic_prop_browser.py --basetemp artifacts/progress-workflow-NEW
```

Validation passed 20 checks across both groups; the paused-stage demonstration
was also rerun with an explicitly labelled SYNTHETIC dataset. Temporary browser
servers are fixture-owned and shut down after validation; the existing
application server is left running.

### Strategies navigation and shared backtest execution — 2026-10-28

The main navigation is Datasets and Strategies. Choose an instrument in the left
half of Strategies to populate the right half with actual saved backtests and
short summaries. Date ranges remain per-report context; they do not split
instrument groups. The row arrow opens the original full backtest-report page,
including inline default prop cash and the existing Configure -> Check -> Run ->
durable result journey. The summary's Historical net is read from the original
saved default prop report; unavailable/error cases remain N/A. Existing report
files and downloads are preserved. Instrument grouping uses a disposable index
of the existing catalogue, not duplicate result storage.

Use Strategies -> New backtest for either a single set or exhaustive sweep in
the same form and `/api/backtests` endpoint. Each sweep trial remains an ordinary
backtest with its default Apex 50K EOD analysis (49 evaluation, 129 activation,
20 slots, standard simulation counts). No production calculation engine changes
are made. Existing optimization links remain readable, with normal resume guards.

Review `docs/strategies_navigation.md` for exact product steps. Actual labelled
synthetic demonstrations live under `artifacts/strategies-navigation/`: the
`02-library-reviewed/` seven-bar source has independently expected net 13 CU
and three trial nets 13/26/39; its single session is correctly rejected as too
short for prop analysis. `03-shared-form/` captures the identical execution
settings submitted for both modes. `04-product-regression/` preserves the normal
60-weekday cash-source workflow, checking source net 180,000, historical payouts
360,000, acquisition fees 7,120 and Historical net 352,880. It includes source
checking, invalid-setting rejection, configure/run/reopen, downloads and stable
original-report hashes. All servers used for demonstrations are temporary test
fixtures and stop after the checks. The user's existing checkout/server and
Windows VM are untouched; only this request's branch is published.

## Declared IS/OOS research and budgeted holdout execution

The normal product now requires an explicit date or percentage declaration before
a single backtest or exhaustive batch. Only IS trades reach the default native
Apex calculation. The normal saved IS report exposes its exact parameters, locked
OOS dates and shared remaining budget. Explicit confirmation runs that one set
on OOS and publishes a normal source-bound backtest and prop report. Three atomic
reservations are allowed per strategy/source, including failed/interrupted work.
A fourth is blocked across parameters, deleted reports, restarts and identical
CSV re-uploads. Old reports remain immutable and are labelled Legacy.

Actual saved product journey and independent expectations are documented in
[research_workflow.md](research_workflow.md), with original evidence under
`artifacts/is-oos-20261028/browser-01/`. The labelled 120-weekday, 50/50 cash
source yields **60 trades / 180,000 CU trading net / 352,880 USD Historical net**
in each independent 60-weekday period. Expected payouts are 360,000 and acquisition
fees are 7,120, including activation. The saved JSON and screenshots cover upload,
split review, IS execution, configure/source check/run/reopen/download, an IS
parameter sweep, explicit one-trial OOS selection and the same durable OOS prop
journey. Standard counts and the local model remain unchanged.

The two-weekday boundary journey independently expects one 30 CU trade per period
and incompatible prop input for one weekday, never a fabricated cash zero. Its
cancelled OOS confirmation spends nothing, its first three confirmed attempts
consume the budget, and both UI and API reject the fourth. IS remains available.
New API checks cover malformed/empty/overlapping declarations, immutable plans,
IS/OOS trade separation, frozen costs/parameters, concurrent limits, idempotent
UUID retries, failures, restart recovery and budget persistence after deletion.
Fixture servers are temporary and stop normally. Existing data/report preservation
and local-server activation are recorded separately in the running checkout's
`artifacts/is-oos-20261028/` when deployed locally.

The same budget boundary applies to manual prop calculations: verified saved OOS
results can reopen freely, while changed settings, exports and fresh calculations
are rejected outside a budgeted IS selection. OOS configuration shows the saved
defaults without editable tuning controls. Legacy full-period reports spanning a
locked holdout cannot launch fresh prop calculations either. Original reports
remain readable. The product browser case checks HTTP 409 for both check/submit
with altered OOS activation fees, then successfully source-checks/reopens/downloads
the original default report with its source and fees unchanged.

Final combined validation: **801 passed**, including the original engine/prop
parity oracles, API and CLI contracts, real Chromium flows, locked declarations,
concurrent budgets, future strategy registration and prop-only bypass guards.
The final immutable code is `bafa7b0`; qualification, full log/JUnit and actual
product outputs are under `artifacts/is-oos-20261028/final-suite/` and its parent.
This includes the exact default simulation counts, fees and independent cash
values above. Fixture servers stopped through their normal cleanup.

## Saved funded-sizing audit — 2026-10-28

The actual report `fed437c6d2944703b94eb45484a7039d` was independently inspected
through its normal portal Sizing view and its captured native source. See
[the audit and exact reproduction steps](reviews/prop-sizing-fed437c6-20261028.md).
The saved 1–20 sweep is truncated below its configured/tier-eligible 40 MNQ limit.
Training-only extension with the original 3,000 paths per point raises the
unchanged model's score from **4,625.97 at 20 to 6,985.55 at 40**. This is a
diagnostic, not qualified real-account sizing. Original points 1/10/19/20 match
exactly, 400 independent ledger cases match, and all 14 saved report files remain
byte-identical. No research OOS or production analysis was submitted.

Nonmonotone drawdown rates are explainable by inactivity, successful six-payout
closure and model stop/lock rules; they do not establish that leverage is safer.
Current-rule qualification remains incomplete: 21-weekday inactivity with a
qualifying-day exception differs from the 30-calendar-day policy; exact-50%
consistency is accepted locally; all 771 trades lack measured excursions; DLL
fills are clipped exactly; and annualized selection uses fixed 52.5%/five-day
replacement assumptions. The audit saves actual UI screenshots, full diagnostic
CSV/JSON, independent boundary examples, primary provider links and commands.
No simulator code, earlier numerical report or server was modified.

## Complete permitted sizing and native intratrade risk — 2026-10-28

This increment uses the normal report/configure/check/run/durable-report workflow
on the actual audited source, without an external calculation engine or a new
storage system. The original IS backtest `404e70186bde41df90f2c4a4912a8013` and prop
report `fed437c6d2944703b94eb45484a7039d` remain unchanged. The actual replay is
`4a88a36e50fd431aa337939f65e3d2c0`, with new prop report
`bc8b22b5d1294064b69556366ac8058f`. All original catalogued backtest manifests,
dataset metadata and analysis IDs were preserved; the audited original backtest
and prop files remain byte-identical. The existing OOS budget remains **1 used,
2 remaining**. No OOS operation was submitted.

To reproduce the saved product journey on the local portal:

1. Open `/#backtests/report/404e70186bde41df90f2c4a4912a8013` and click
   **Capture intratrade risk**. Its completed verified IS replay reopens the new
   backtest above. A future pre-capture IS report runs the same verification and
   publishes its own compact replay. Original parameters, fees and IS dates are
   retained. OOS and undeclared legacy risk replays return HTTP 409.
2. Expect **771 trades**, unchanged **211.42 CU net trading P&L**, identical
   trade/equity CSV bytes, and **771 held-OHLC risk rows**. Download
   **Intratrade risk CSV**. It is **186,399 bytes** (182 KiB), not per-bar equity
   storage; its SHA-256 is
   `3c4b3e13e2e8886002e1515e472c785915683b197a9fa22291681d7341eb1332`.
3. Use **Configure prop analysis**, leave the optional export empty and click
   **Check source**. Expect native OHLC coverage **771**, measured tick/export
   MAE/MFE **0**, **6** ambiguous adverse bounds, and the conserved source net
   **211.42**. All trade IDs/times/quantities/net costs match. The source is IS
   2017-05-21 through 2023-10-10; no declared external OOS dates are included.
4. Click **Run analysis**. Identical settings reopen the verified automatic v2
   report above. In **Sizing**, choose size ascending: **40 rows, 1–40 MNQ**, unit
   increment, with size **40 MNQ** at the bottom and tier caps **20/30/40**.
   Internal training remains 2017-05-22 through 2021-11-08, validation
   2021-11-09 through 2023-10-10. The selected funded size is **17 MNQ**; its
   internal holdout drawdown-failure estimate is **95.005%**, lifetime expected
   payout **$597.60**. Evaluation selects **36 MNQ**, pass rate **21.745%**.
   These are saved model estimates, not future outcomes or a sizing endorsement.
5. In **Historical replay**, expect payouts **$270,000**, acquisition costs
   **$184,262** including activation, and **Historical net $85,738** over the
   supplied IS history. Both the search range and risk inputs changed, so this
   comparison does not isolate the contribution of each change.
6. Download the report JSON, full ZIP and funded/evaluation sizing CSVs. The ZIP
   includes `inputs/intratrade_risk.csv`, source reconciliation, settings and all
   original-count results. Reload/reopen the saved report: no new simulation or
   OOS attempt is submitted. The funded sweep retains **3,000 paths per size**,
   holdout evaluation/funded lifetime/funded first year retain **20,000 each**.

Evidence is saved in `artifacts/prop-risk-20261028/`: product-verification JSON,
before/after preservation manifests, four actual portal screenshots, source
check, backtest/prop report, risk CSV, complete sizing CSVs, calculations, ZIP and
an exact browser-download copy. `reproduce-product.py.txt` records the normal
portal journey; it uses a temporary server on 8001 and asserts its shutdown.
`reproduce-ohlc-oracle.py.txt` independently scans saved source bars and computes
all four price/cost bounds for all 771 source trades, without using RiskCapture
or the prop account engine. Run it from the implementation checkout with
`PYTHONPATH=. /path/to/venv/bin/python /path/to/reproduce-ohlc-oracle.py.txt`.
The source's actual scope is all long, next-open entries and no same-bar exits;
other fill modes are covered by independent synthetic boundary fixtures in tests.

Automated rejection/boundary checks include profitable trades breaching the
account before recovery, exact floor touches, long/short held extremes,
same-close entry exclusion, next-open entry inclusion, next-open/gap exit
exclusion, stop exits versus later lows, ambiguous target exits, entry/exit costs
once, low Decimal precision, corrupt/missing risk artifacts and mismatched costs,
overnight rejection and unchanged OOS budgets. An independent expanded-mark
ledger checks 400 valid synthetic account cases against compressed frontiers in
both Python and the rebuilt compiled engine. A gap through both limits closes
the account at the observed mark; an earlier DLL stop ignores later gaps.

OHLC bounds are explicitly distinguished from tick measurements. Conservative
adverse ordering can count a possible target-bar breach. Unobserved tick gaps and
liquidity still cannot be inferred, and cross-session native inputs reject rather
than silently using close-only risk. Earlier notebook/ledger oracles remain
unchanged; v2 risk-input changes are intentional and do not claim parity with
old close-only outcomes or complete current-provider-rule certification. The
existing deadline/inactivity/consistency and fixed training-selection economics
remain disclosed model limitations outside this increment.

Independent actual-source qualification completed: **771 trades × four bounds =
3,084 exact Decimal comparisons**, including **500 profitable trades with nonzero
adverse equity excursion** and the same **6 ambiguous target-exit bounds** shown
in the product source check. `independent-ohlc-oracle.json` saves every expected
and observed bound. `implementation-source-sha256.json`, `implementation.diff`
and `implementation-source.zip` preserve the exact local code behind the actual
report; all captured prop-module hashes and the compiled-kernel identity match
its saved runtime metadata. The later commit ID does not alter those code hashes.

Final complete regression gate: **823 passed, 24 existing dependency warnings**
in 436.19 seconds. The full log and JUnit are `final-suite.log` and
`final-suite.xml` under the evidence directory. Run from the intended checkout
with `PYTHONPATH=. /path/to/venv/bin/python -m pytest -q` so subprocesses use that
checkout too. Financial fixture oracles remain unchanged; file-list assertions
now include the risk CSV. The property/actual-source checks above accompany the
full suite; tests alone are not the product demonstration. The temporary product
browser server on 8001 shut down normally.

Local activation completed on branch `fix/prop-intratrade-risk` in the original
checkout. Implementation commit: `490ebbf`; the earlier audit is `51c2bd3`.
The idle old reloader was stopped before switching tracked code. Existing audit
notes were preserved both in the committed audit and recovery stash
`61885de62e4620553821a0bd9aed5b293aa18b5e`; the former compiled kernel is retained
as `previous-native-kernel.so` in the evidence directory. All activated source
hashes and the copied qualified compiled binary match the actual saved report.

The primary portal is serving port **8000**, PID **98400**, from
`/Users/yx/alphaquest-research-engine-2`, with the original `data` directory and
without automatic reload. Stop it with **`kill 98400`**. Its PID/log and startup
record are in `artifacts/prop-risk-20261028/portal-server.pid`,
`portal-server.log` and `restart.json`. Temporary browser servers have stopped.
`verify-live.py.txt` and `live-verification.json` record the final port-8000
journey: old-model label visible, native source check passed, all 40 sizes visible,
the same saved v2 analysis reopened without a new analysis row, exact JSON bytes,
no browser errors, original file hashes and OOS budget unchanged. No commits were
pushed. This activation record changes documentation only.

## Training-derived acquisition calibration — v3, 2026-10-28

This increment replaces the fixed 52.5%/five-day sizing assumptions with
training-only calibration and explicitly prevents holdout feedback. The normal
product journey used the existing IS backtest
`4a88a36e50fd431aa337939f65e3d2c0`: report → Configure prop analysis → native source
check → Run analysis → saved v3 report
`e4d3b403f6e04a57a3ee994257b8c68e`. No backtest replay or OOS run was submitted.
The v2 report `bc8b22b5d1294064b69556366ac8058f` and earlier v1 report remain
unchanged. Existing backtest manifests, dataset metadata, analysis rows and all
files of the audited original reports remain identical. The OOS budget remains
**1 used, 2 remaining**. No external engine or vendor-generated results were used.

Reproduce the actual saved product workflow:

1. Open `/#backtests/report/4a88a36e50fd431aa337939f65e3d2c0`, select
   **Configure prop analysis**, leave the export empty and **Check source**.
   Expect 771 native held-OHLC trade matches and the original net **211.42 CU**.
2. **Run analysis** with the default settings. The current completed v3 analysis
   above reopens; before it exists, the same action creates a normal durable job.
   New backtests/optimization trials use the same v3 calibration automatically.
3. In **Sizing**, expect every size **1–40 MNQ**, with training calibration:
   training window **2017-05-22 through 2021-11-08**, evaluation size **36 MNQ**,
   **745 / 3,000 passes = 24.833333333333332%**, acquisition cost
   **$326.31543624161077**, and **41.90495 replacement trading days** including
   activation. Replacement timing uses **20,000 chains, seed 45**. The funded
   size remains **17 MNQ**. This is an observed model result, not an assertion
   that calibration must change the winning size.
4. The **Evaluation** view separates those training inputs from the unchanged
   holdout estimates: **21.745%**, acquisition cost **$354.3391584272247**,
   **31.2671 days**. Every holdout evaluation field and every training evaluation
   sweep row exactly match v2 because the underlying samples/model/seeds did not
   change. These holdout outcomes cannot choose, rescore or gate a valid fit.
5. **Historical replay** uses the frozen training cost and replacement delay.
   Expect payouts **$270,000**, acquisition costs **$130,521**, **400 funded
   starts**, and **Historical net $139,479** over the supplied IS history. This
   historical total changes because acquisition costs/delays now come from
   training; different renewal start dates can change which observed periods
   are traded. It remains a modelled historical replay, not a future forecast.
6. Download **Training calibration (JSON)** from Evaluation or Source & model,
   complete funded-sizing CSV and the standard ZIP. Each CSV row saves its
   acquisition cost, replacement time and evaluation pass rate. Its annual score
   is independently reproducible as 261 × (mean payout − training acquisition
   cost) / (mean lifetime + training replacement days). Reload/reopen the report:
   saved values and JSON bytes remain identical, without another computation.

Inspectable evidence is `artifacts/prop-training-economics-20261028/`: actual
source-check JSON, four portal screenshots, complete report, training JSON,
sweeps, trades, calculations, normal ZIP, browser-downloaded calibration and
before/after preservation snapshots. `reproduce-product.py.txt` records this
normal product journey using a temporary port-8001 server, which shut down.
`implementation-source-sha256.json`, source ZIP and patch preserve the exact
production source; its prop module hashes and compiled kernel match the report.

Independent validation uses `reproduce-oracle.py.txt` without importing any
AlphaQuest calculation functions. It independently groups the native trade/risk
inputs into **1,166 training weekdays / 541 trades**, performs MT19937 circular
block sampling, reconstructs evaluation account transitions, and reproduces
**745 / 3,000** training passes and the mean of **20,000** repeated chains,
**41.90495** days. Decimal arithmetic reproduces acquisition cost and all **40**
funded-size scores. Expected/actual results and duration histogram are retained
in `independent-calibration-oracle.json`. Run the saved script with the project
venv Python; it reads the captured report/trades and uses NumPy for MT19937 only.

Meaningful automated checks also perturb holdout data from profitable to slower
and zero-return histories, keeping the training fit byte-identical; verify that
funded fitting occurs before the first holdout call; and check an independent
numeric example where acquisition costs reverse the size ranking. Zero training
passes cannot be rescued by a profitable holdout. Training chain bound failures
never substitute a delay; holdout chain failures do not erase a training fit.
No-passes/bounded-chain outputs explicitly record unavailable calibration and no
completed training chain batch, rather than claiming 20,000 successful runs.
Normal API/browser synthetic fixtures demonstrate positive/zero training cases
and retain their expected values in tests. No fixture oracle is shown as a
production validation dashboard or fabricated measured excursion.

Final complete regression gate: **832 passed, 24 existing dependency warnings**
in **479.88 seconds**. The full log/JUnit are `full-suite.log`/`full-suite.xml` in
this increment's evidence directory. Run from the intended checkout with
`PYTHONPATH=. /path/to/venv/bin/python -m pytest -q`.

`boundary-evidence/known-cash/` preserves an actual normal-workflow synthetic
report and screenshot: pass rate **100%**, training acquisition cost **$178**,
replacement time **11 days**, funded size **3 MNQ**, and independently known
Historical net **$352,880**. `boundary-evidence/zero-training/` preserves the
labeled source CSV, actual report and screenshot for seven zero-return training
days followed by three profitable holdout days: training pass rate **0%**,
holdout pass rate **100%**, funded sizing/history unavailable. Reproduce through
`tests/test_prop_training_economics_browser.py`; both cases use the existing
upload/backtest/configure/check/run/report routes, temporary fixture servers and
normal storage. Saved downloads complement the actual 771-trade product report.

Local activation completed on `fix/prop-training-economics`, implementation
commit `11e9dab`, in `/Users/yx/alphaquest-research-engine-2`. The idle v2 portal
was stopped before switching code. All activated source hashes and the unchanged
compiled kernel match the saved v3 report. Port **8000** now serves v3 with the
original data directory, PID **4947**, without automatic reload. Stop it with
**`kill 4947`**. PID/log/startup details are in this increment's
`portal-server.pid`, `portal-server.log`, `pre-activation.json` and `restart.json`.
The temporary port-8001 product server has stopped.

`live-verification.json`, `verify-live.py.txt` and the two live screenshots confirm
the actual port-8000 workflow: old report keeps its 52.5%/five-day values and
shows its earlier-model label; the new report shows training calibration and
separate holdout figures; checking/running from the existing IS source reopens
`e4d3b403f6e04a57a3ee994257b8c68e` without creating another analysis row; all 40
sizes and exact saved JSON remain available; original hashes and OOS budget are
unchanged; no browser errors occurred. Nothing was pushed. This final activation
record changes documentation only.

## Selected prop report deletion — 2026-10-28

The existing saved-report/configuration workflow now includes Delete on completed
prop reports and in the saved-analysis list. Confirmation names the exact report;
active jobs return HTTP 409. Backtests, source datasets, optimization metrics and
spent OOS attempts remain intact. Removing an OOS analysis never permits an
unbudgeted replacement calculation. Catalogue failures restore staged files;
cleanup failures support a second Delete attempt. Symbolic-link directories are
rejected. Optimization tables retain metrics and mark removed report links.

Normal API/browser synthetic fixtures verify cancellation without a request,
confirmed deletion of only the selected analysis, other-report preservation,
backtest preservation, and both header/list controls. Evidence is retained under
`artifacts/strategy-browser-20261028/fixture-evidence/prop-deletion/`; independent
financial fixture oracles remain unchanged. On actual saved report
`e4d3b403f6e04a57a3ee994257b8c68e`, the new confirmation was opened and cancelled;
no actual user report was deleted. No simulation arithmetic or sampling changed.


## Saved-report hierarchy and deletion — 2026-10-28

The portal now opens Strategies as strategy names on the left and the selected
strategy's instrument/full dataset periods on the right. Selecting the dataset
opens saved parameter runs with IS/OOS trading P&L, drawdown, trades, win rate and
saved default-prop Historical net. Parameter differences are highlighted, full
parameter values are inspectable, and sorting/pagination/report links use saved
catalogue values. No backtest or prop calculation runs when browsing. See
[strategy navigation and management](strategy_navigation.md) for API contracts.

On the actual NQ source, the full period is **2017-05-21 through 2026-07-07** in
America/New_York, even though the selected IS backtest ends **2023-10-10**.
The dataset group contains **115 reports: 97 IS, one OOS and 17 legacy**. The table
has **114 primary rows** because the explicit matching OOS child is displayed
beside its parent. The recorded parent is
`404e70186bde41df90f2c4a4912a8013`; its OOS child is
`b3d47b3147aa4c12a8281abb681355e0`. Their net trading P&L values are respectively
**211.42 CU** and **62,316.18 CU**, read exactly from the saved reports.

The actual product browser journey was Strategies → VWAP strategy → NQ/full
period → runs → individual report → Back to the same dataset table. It also
checked reload and a 390-pixel viewport. A read-only actual-data check opened
both the backtest Delete confirmation and the completed prop report Delete
confirmation for `e4d3b403f6e04a57a3ee994257b8c68e`, then cancelled both. **No
mutating HTTP request was sent.** All authoritative run manifests, dataset
metadata, analysis rows, OOS-attempt rows and inspected report/download hashes
remain identical. Budget remains **1 used, 2 remaining**. A temporary port-8001
server provided this check and shut down normally.

Actual evidence and reproduction are saved under
`artifacts/strategy-browser-20261028/`: six screenshots, run-table and dataset
JSON, exact source periods, product-verification JSON, before/after preservation
snapshots, and `reproduce-product.py.txt`. This product check uses the existing
portal/report routes, not a demo API or new calculation store. The `library_*`
tables are disposable metadata indexes; original numerical files remain intact.

Confirmed deletion is demonstrated only on labeled synthetic fixtures through
the normal product. `fixture-evidence/hierarchy/` preserves the expected
13/26/39 CU saved-report values and opening/reload/mobile journey.
`fixture-evidence/is-oos-deletion/` shows IS 13 CU paired with OOS 0 CU, selecting
between two saved OOS attempts, cancelling without a DELETE request, deleting
only selected IS reports and retaining their OOS reports as OOS-only rows.
Its OOS budget remains **2 used** after parent deletion.
`fixture-evidence/prop-deletion/` records cancellation, prop-header deletion and
saved-analysis-list deletion, with independent backtest/dataset/other-report
preservation before those reports themselves were selected. Fixture oracles
remain in the API/browser tests and are not presented as a production test page.

Automated checks cover dataset/strategy separation, source-timezone full dates,
retained full metadata after source deletion/restart, honest missing legacy dates,
matching parent/parameters/costs, absent or mismatched IS parents, all OOS attempts,
exact numeric sorting with N/A last, deleted-prop cache invalidation, no OOS-budget
refund or recalculation bypass, active-analysis rejection, transaction rollback,
retryable staged cleanup, symbolic-link rejection, and preserved optimization
metrics with removed links. Strategy parameters remain recorded exactly; numeric
spellings `2` and `2.0` compare equal for highlighting, while a difference at the
28th decimal place remains visible and sortable.

The complete regression gate passed **850 tests, 24 existing dependency warnings**
in **524.60 seconds**. Its final log/JUnit are `final-suite.log` and
`final-suite.xml`; the earlier 849-test pass is retained separately. After the
last UI-only dataset-shortcut refinement, **14 focused browser tests passed**
(`final-browser-checks.log`), including a new check that switching to another
source restores that dataset's tick-size/point-value defaults instead of carrying
old instrument overrides. Calculation code was unchanged by that refinement.

Run checks from the intended checkout with
`PYTHONPATH=. /path/to/venv/bin/python -m pytest -q`. Temporary fixture servers
shut down through their normal cleanup. The source patch/ZIP and SHA-256 inventory
in this increment's evidence directory identify the exact final implementation;
financial fixture oracles and saved user results remain unchanged.

### Local activation and final product verification

The original checkout now uses `feat/strategy-dataset-navigation`. Implementation
commits are `4ab04f4` (selected prop report deletion) and
`ca99e99a3a48799c5829311dce6939cfea593939` (strategy/dataset navigation).
Nothing was pushed. After checking that no optimization, prop or OOS job was
active, the previous portal was restarted with the original data directory.
The persistent server is PID **13477**, listening at `http://127.0.0.1:8000`
without autoreload; stop it with `kill 13477`. The PID, restart record and server
log are `portal-server.pid`, `restart.json` and `portal-server.log` in the evidence
directory. The temporary port-8001 verification server has stopped.

To reproduce in the active portal, open `http://127.0.0.1:8000/#strategies`, select
VWAP Pullback Risk Sizing, and select NQ with full dates **2017-05-21 through
2026-07-07**. In the parameter table, open run
`404e70186bde41df90f2c4a4912a8013`; its paired IS/OOS net P&L must be **211.42 CU**
and **62,316.18 CU**. Back to Strategies returns to this dataset table. For a
non-destructive deletion check, open Delete on that backtest, verify the exact
report ID, and cancel. Open prop report `e4d3b403f6e04a57a3ee994257b8c68e` through
its saved-analysis link and cancel its Delete confirmation as well. Confirmed
deletions and their rejection boundaries are demonstrated by the preserved
synthetic product fixtures rather than by removing actual user results.

Final verification on port 8000 passed: full source dates, exact paired metrics,
equal numeric spellings not highlighted, return navigation, both deletion
controls and preservation of every checked original record, file and budget.
There were no mutating requests or browser errors. Inspect `live-verification.json`,
`final-run-table.json`, `live-strategy-datasets.png`, `live-is-oos-table.png` and
`verify-live.py.txt` under `artifacts/strategy-browser-20261028/`. The active
production/static source hashes match `implementation-source-sha256.json`.

## Editable Apex instrument commissions — 29 October 2026

Implementation: `alphaquest-apex50k-eod-v4-instrument-commissions`. The existing
backtest report → Configure prop analysis → Check source → Run analysis → saved
report journey now exposes broker, source instrument, and MNQ per-side commission.
The Rithmic schedule is a dated, centrally maintained catalog; account arithmetic
does not hardcode the fee. New reports replace the actual saved source commission
once and retain source slippage. The current model orders MNQ for both evaluation
and funded, including when a candidate quantity is a multiple of ten. Its NQ/MNQ
scope is unchanged; the wider commission catalog does not imply support for other
account/instrument models.

Inspectable evidence is under
`artifacts/prop-commissions-20261029/final-browser/test_actual_instrument_commiss0/`.
This is a normal isolated product datastore containing an explicitly labeled
**synthetic** dataset/backtest and durable reports, not observed market outcomes.
The original user datastore, existing reports, datasets, backtests, Windows VM and
other processes were not modified. Earlier harness attempts and the first successful browser run are retained
separately in `browser.xml`/`browser-run1.xml`/`browser-run2.xml` and their directories.

- Source backtest: `e9b5819499f94aa78876dc191a1df246`, 60 synthetic trades.
- Automatic Rithmic report: `6ffae6ec3faf461fa73641adc51a03ec`.
- Custom $0.70/side report: `3c1d4ccaacec4ac5a69d1e83181c7727`.
- Downloads: `analysis.zip`, `report.json`, `default-report.json`, and
  `commission_reconciliation.json`. The standard ZIP contains source trade
  reconciliation, simulated per-MNQ net/commission, all 40 evaluation and funded
  sizing points, run settings, captured risk, charts and immutable report data.
- `source-check.png` shows editable rates and the successful source check;
  `source-model.png` shows the saved cost assumptions and download.
- `validation.json` records source SHA-256 preservation, expected/actual net values,
  full simulation counts and reopen/reload without calculation POSTs.
  `rejections.json` captures actual HTTP 422 results for negative commission,
  conflicting NQ/MNQ identity and a custom broker without a rate.

Independent expected arithmetic: each source NQ trade makes $3,000 before $10
slippage and $3.98 commission, leaving **$2,986.02**. One simulated MNQ retains
$1 slippage and pays $1.02 Rithmic round turn, leaving **$297.98**. At custom
$0.70/side, it pays $1.40 round turn and leaves **$297.60**. At 10 MNQ these become
$2,979.80 and $2,976.00; the contracts still pay ten micro commissions. The old
scaled-source result would have been $298.602 per MNQ. Inspect these values in the
normal `trades.csv` download (`simulation_net_per_mnq` and
`simulation_commission_per_mnq`). Raw source net/commission columns remain intact.
The custom report selects 1 MNQ evaluation and 3 MNQ funded on this synthetic
history; its historical replay records $360,000 payouts less $7,120 acquisition
costs, $352,880 net across 20 correlated slots. These are synthetic replay outputs,
not future returns or a claim that commission changes must alter selected sizes.

Captured/measured source excursions remain preserved. Simulation risk uses a
conservative commission-adjusted bound, explicitly disclosed in the check/report;
it is not newly measured MAE/MFE or exact repriced tick risk. Unit checks include
fee changes at 1/10/25/40 MNQ, zero/custom fees, source quantity normalization,
MNQ sources, unchanged measured values, conservative gap frontiers, and an account
floor boundary where replacing commission changes survival to failure. V4
intentionally changes earlier cost-scaling semantics and does not claim external
numerical parity.

To reopen this saved demonstration without calculations, from the repository run:

```sh
ALPHAQUEST_DATA_DIR=artifacts/prop-commissions-20261029/final-browser/test_actual_instrument_commiss0 \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8011
```

1. Open `http://127.0.0.1:8011/#backtests/report/e9b5819499f94aa78876dc191a1df246`
   and choose **Configure prop analysis**. Expect detected NQ, Rithmic broker and
   MNQ $0.51/side. Source NQ costs remain the actual $1.99/side saved by the backtest.
2. Check the source. Expect 60 matched trades, source net $179,161.20, explicit
   NQ → MNQ commission replacement and $1.02 round turn. Run analysis; identical
   unchanged requests can reopen the saved default report.
3. Configure **Custom broker**, MNQ **0.7**, then check and run. Expect $1.40 round
   turn. Editing any input disables Run until another source check succeeds.
   Open Source & model and download the commission reconciliation and trade CSV.
4. Reopen saved custom report
   `http://127.0.0.1:8011/#backtests/prop/job/3c1d4ccaacec4ac5a69d1e83181c7727`.
   Expect the same rate, results and downloads without a new analysis POST.
5. Negative fees, a selected MNQ source conflicting with the saved NQ symbol, or a
   different broker with an empty rate reject during source checking. An unknown
   symbol displays a source-cost notice and requires explicit NQ/MNQ identification
   before a commission override can apply. Zero is a valid override.
6. Stop this optional user-started server with Ctrl-C.

To reproduce the automated product journey in a new isolated datastore, use a
**new, unused** basetemp directory (pytest clears its basetemp). For example:

```sh
.venv/bin/python -m pytest -q tests/test_prop_commissions_browser.py \
  --basetemp /tmp/alphaquest-commission-review-NEW
```

The browser test uses the normal dataset/backtest/report APIs, standard 3,000-path
size sweeps and 20,000-path final simulations. Its temporary server shuts down in
fixture cleanup; no persistent server was started for this increment.

The existing port-8000 server was left running. It does not autoreload Python;
restart that backend before using the new commission form against the main
datastore. The isolated server above loads the updated backend without touching
that process or its jobs.

The final commission unit/browser run passed **24 checks**; its log and JUnit
are `artifacts/prop-commissions-20261029/focused-final.log` and
`focused-final.xml`. The existing backend/API/automatic suite also passed
**56 checks** before the final source-provenance wording refinement.
The older automatic backtest/configuration/reuse browser flow passed its isolated
rerun (`automatic-rerun.log`/`automatic-rerun.xml`).

The broad run finished **872 passed, 3 failed, 24 warnings** in 763.72 seconds
(`regression.log`/`regression.xml`). All three failures occurred while creating
fixture backtests (HTTP 500 / no completed run), before their financial checks.
The affected automatic browser flow passed in `automatic-rerun.xml`; compiled
portal parity and the legacy source-rejection workflow both passed in
`regression-rerun.xml` (**2 passed**). Other research/OOS files were edited and
restored concurrently while the broad suite was running. Their effect on those
failures was not established; this is **not a green full-suite baseline**.
The commission unit/API arithmetic and actual commission browser journey all
passed in that run as well as the final focused run. No tests or servers remain
running from this increment. `implementation-sha256.json` records the qualified
commission files; unrelated concurrent edits were preserved.

## Recheck of fixed sizing assumptions and MAE risk — 2026-10-29

The reported 52.5% evaluation pass rate and five replacement trading days are
present in preserved v1/v2 results. They were already removed from new
calculations by `11e9dab`. The running port-8000 backend serves v3 training
economics. No further production calculation change is needed for this finding.
Existing uncommitted v4 commission work was preserved.

Reproduce through the actual saved product workflow:

1. Open `/#backtests/prop/job/fed437c6d2944703b94eb45484a7039d`, then **Sizing**.
   Its saved fixed assumptions remain visible with an earlier-model notice.
2. Open backtest `/#backtests/report/4a88a36e50fd431aa337939f65e3d2c0`, select
   **Configure prop analysis**, leave the export empty, and **Check source**.
   Expect 771 captured held-OHLC trades and zero measured export MAE trades.
   Select the saved completed analysis
   `e4d3b403f6e04a57a3ee994257b8c68e` (v3) to inspect the already corrected
   report without submitting a new calculation.
3. In **Sizing**, expect 40 sizes, training evaluation passes **745/3,000**
   (**24.833333333333332%**), replacement time **41.90495 trading days**, and
   acquisition cost **$326.31543624161077**. The UI rounds these for display;
   download **Training acquisition calibration (JSON)** or report JSON for full
   precision. Every funded score uses these frozen training inputs. Holdout
   evaluation results remain separate.
4. In **Source & model**, inspect the risk provenance and captured risk download.
   Native adverse bounds include movement before a profitable close: **500**
   of the **771** trades have both positive realized net P&L and nonzero adverse
   excursion. MAE/adverse bounds check intratrade account/DLL breaches; they
   are not planned stop distances or predictions of future maximum losses.
   OHLC bounds are not exact tick paths. Legacy sources without capture still
   disclose their realized-loss fallback; use **Capture intratrade risk** on
   an eligible IS backtest to obtain captured bounds in a new report.

Fresh evidence is `artifacts/prop-bug-check-20261029/`. Run
`.venv/bin/python artifacts/prop-bug-check-20261029/verify_saved.py` to check
the actual saved calibration, independently recompute every funded score with
Decimal arithmetic, count profitable trades with adverse movement, verify the
live download, and hash all three historical reports before/after. It writes
only new audit evidence. `verify_portal.py` opens the actual historical/corrected
Sizing views, saves screenshots/text, and asserts that no POST was submitted.
These scripts use the existing port-8000 server and do not start or stop it.

The existing browser qualification exercises dataset upload → backtest →
configuration → source check → run → saved results → downloads → reload/reopen
with labeled synthetic inputs. Reproduce using
`PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_prop_training_economics_browser.py`.
Its independent positive oracle is **100%**, **11 days**, **$178 acquisition**,
and **$352,880 historical net**. Its boundary oracle is zero training passes
with profitable holdout: funded sizing/history must remain unavailable.
Fixture servers shut down on teardown; no persistent server was started.

The user's clarified second concern is missing adverse movement before trade
close when enforcing drawdown rules. This is covered by the existing native
capture and first-adverse-hit engine from `490ebbf`: both Python and compiled
accounts fail when a winning trade crosses the account floor before recovering.
Exact floor touches, daily-loss stops, ordered opening gaps, entry/exit costs,
and 400 independent expanded-equity-ledger cases passed in the fresh recheck.

Final focused result: **34 passed, 1 deselected** (the slower full Python/compiled
portal parity test), plus **2 browser workflow tests passed**. Logs/JUnit are
`focused.log`/`focused.xml` and `browser-rerun.log`/`browser-rerun.xml` in the new
evidence directory. The first attempts had HTTP 500 failures while creating
fixture backtests, before the financial assertions; an isolated retry and the
complete focused/browser reruns passed. The original browser failure remains in
`browser.log`/`browser.xml`; its cause was not established. No full-suite result
is claimed for this audit. Saved actual portal screenshots and the hash audit
also passed without calculation POSTs or any changes to existing reports.
## Editable declarations and manual unlimited OOS — 2026-10-29

The declaration lock and three-attempt cap are removed from form and backend.
The latest accepted split is a prefill for the next IS run, with enabled date
and percentage fields. Editing requires another split review. Each saved run
retains its own split, parameters and execution costs; changing the next run's
split does not rewrite an earlier result. Existing attempt rows remain history,
with no limit, remaining count or exhausted state. No data reset is required.

Initial single runs and optimisation grids still execute IS and its automatic
prop analysis only. OOS requires opening a completed IS report, selecting **Run
OOS with these parameters**, and confirming. The server uses that IS report's
recorded OOS window, even after a newer split was submitted. OOS and legacy
reports cannot launch OOS. Request UUIDs remain idempotent under concurrency;
failed/interrupted requests can be followed by a new explicit request. Manually
executed OOS sources can configure/check/run prop analyses with new settings.
All production calculations remain local; no account arithmetic changed here.

Normal product reproduction:

1. Open Strategies → New backtest and choose dataset/strategy. A saved split
   now prefills editable controls. Choose dates or percentage, change the
   declaration, and click **Review IS/OOS split**. Invalid chronology, empty
   windows and missing dates still prevent execution.
2. Run IS with the selected parameters. Open its backtest report and configure
   prop analysis → check source → run → durable result. The source and report
   contain only IS data. No OOS is queued by any of these steps.
3. From a completed IS report select **Run OOS with these parameters**. Cancel
   once: no request is submitted. Confirm: OOS runs with its saved split and
   parameters, then saves the ordinary backtest and automatic prop analysis.
   Configure/check/run can reopen that saved prop result and downloads.
4. Repeat the manual OOS action more than three times: it remains available.
   Return to New backtest and change the split. The earlier IS report and its
   saved OOS dates remain unchanged. An OOS request from that earlier IS still
   uses its original dates, rather than the latest form prefill.

Evidence is saved under `artifacts/editable-is-oos-20261029/`. The browser journey
uses labeled synthetic data through the normal upload/backtest/configure/check/
run/durable-report routes and standard simulation counts, with independent
fixture expectations kept in tests. The four-date boundary case produces
**30 CU** in the original one-day IS/OOS windows; four manual OOS runs succeed.
Editing IS to two days produces **60 CU** and does not launch another OOS run.
The 120-weekday positive case has 60 trades and **180,000 CU** per period; each
saved prop report has **$360,000 payouts − $7,120 acquisition = $352,880 net**.
Both periods' native source checks, JSON downloads and saved results are
inspectable in the normal isolated fixture datastore. Screenshots, verification
JSON and JUnit/logs accompany the saved reports. Existing user datasets and
financial reports are not modified by these synthetic demonstrations.

Reproduce with a fresh unused basetemp path (pytest clears it):

```sh
PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_research_workflow.py \
  tests/test_prop_risk_workflow.py tests/test_strategy_dataset_browser.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_research_browser.py \
  tests/test_backtest_date_range_browser.py --basetemp /tmp/alphaquest-editable-split-NEW
```

Temporary fixture servers shut down in teardown. Earlier lock/budget evidence
remains unchanged and describes the retired policy, not the current workflow.

Fresh qualification: **37 API checks and four browser workflows passed**, with
one existing dependency warning per test process. `api.log`/`api.xml` and
`browser.log`/`browser.xml` record these results. The completed positive journey
is in `browser/test_percentage_is_sweep_selec0/`: IS
`e744d3688fd04d19963e2d8d94d67b58`, OOS
`f06900b8b80d49058bf1eb544a91a162`, plus both prop-report downloads and the
underlying ordinary datastore. `browser/test_editable_dates_and_unlimi0/` holds
the four-OOS/edited-split demonstration. To inspect saved outputs without new
calculations, optionally serve either fixture directory with
`ALPHAQUEST_DATA_DIR=<absolute fixture directory> .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8011`,
open its saved report route, then stop that optional server with Ctrl-C.

Local activation replaced the verified idle port-8000 backend PID 13477 with
**PID 28791**, using the same original `data` directory. It activates the other
chat's completed v4 commission changes alongside editable splits and unlimited
manual OOS. Stop the persistent replacement portal with **`kill 28791`**.
`activate-local.py.txt`, `activation.json`, server log/PID and before/after
snapshots are in this evidence directory. All dataset/backtest/prop catalogue
rows, research plans, OOS history, optimisation jobs/trials and the original
v1/v2/v3 audited report-file hashes matched across activation. No user financial
run, OOS request or deletion was submitted. `verify-live.py.txt` edits/reviews the
actual source's split without saving it, checks 771 held-OHLC trades, verifies the
manual OOS button and cancels both actual delete dialogs. Live screenshots,
source-check JSON and `live-verification.json` retain those observations.

## Portal deletion of stale reports — reverified 2026-10-29

The existing final-product controls already support this request. No additional
deletion API/store or automatic cleanup is needed. Use Strategies → strategy →
instrument/full dataset period → **Delete** beside the selected report, or open
it and select **Delete backtest**. Open a completed prop result and select
**Delete prop report**, or delete it from the saved-analysis configuration list.
Each confirmation identifies the exact selected report. Source datasets remain;
backtest and prop results are independently selectable. No existing user report
was deleted during verification. See `docs/strategy_navigation.md` for the steps.

**21 deletion API/browser checks passed** with one existing dependency warning.
Evidence is `artifacts/portal-report-deletion-20261029/`: results log/JUnit and
saved screenshots/verification JSON under `verification/`. It covers cancellation
without a DELETE, actual selected synthetic report deletion, source/unselected
report preservation, both prop deletion locations, backtest header/table controls,
busy-source rejection, file/catalogue rollback checks, saved optimisation metrics
and reload/pagination. Normal fixture servers shut down after the tests.

Reproduce in a fresh unused basetemp directory:

```sh
PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_delete_backtests.py \
  tests/test_delete_prop_reports.py tests/test_strategy_run_management_browser.py \
  tests/test_delete_backtests_browser.py --basetemp /tmp/alphaquest-report-delete-NEW
```
# One parameter grid for all new backtests — 2026-10-29

The new-backtest form no longer offers a Backtest mode selector or a separate
single-parameter form. Its exhaustive grid is always visible. Equal start/end
values on every row give step 0, count 1 and **Total combinations: 1 = 1
backtest**. Wider ranges generate every combination, using the same parameter
drafts, costs, IS/OOS declaration, benchmark settings and reuse checkbox.
One generated combination opens the ordinary backtest report with its existing
live preparation/replay/saving progress. Multiple combinations open the saved
batch table and individual report links. Both submit to `/api/backtests`; the
single-report API remains an execution primitive for integrations, replays and
manually selected OOS. No production calculation, prop sizing or sampling changed.

The normal-product arithmetic demonstration is saved under
`artifacts/unified-backtest-grid-20261029/fixtures/test_one_form_and_endpoint_run0/`.
Its `shared-form-verification.json` and screenshots show the same form running
one contract for **13 CU** and then contracts 1–3 for **13/26/39 CU** net. The
independent arithmetic is 1.5 fill-price points × 10 CU/point/contract minus
2 CU commission/contract = 13 CU/contract. Costs and capital remain identical
between submissions; the old saved batch URL reopens those exact results.
Another boundary check sets contracts 1→2 with step 5: only 1 is generated, so
exactly one report is saved with 13 CU net. Fractional integer endpoints/steps
remain rejected before execution, and boolean/Decimal values retain their types
and precision through report saving.

To reproduce manually, follow the labeled arithmetic upload/declaration in
[Backtests screen review](backtests_portal.md), then set both endpoints of green
bar count to 3, hold minutes to 20 and contracts to 1, with tick size 0.25,
point value 10, slippage 1 and commission 1. Expect count 1 and net 13 CU.
Return to New backtest, change only contracts end to 3, and expect count 3 and
the three net values above. No mode change is required. In an existing report,
Configure prop analysis → Check source → Run still uses the normal durable
analysis workflow; selected manual OOS remains a separate report action.

The live portal was checked read-only through Strategies → New backtest:
no selector/duplicate inputs, default one-combination grid, recalculated three
combinations, navigation preserving drafts, VWAP boolean defaults and a 390-pixel
layout without page overflow. `live-verification.json`, three `live-*.png`
screenshots and `verify-live.py.txt` preserve the observations and exact source
hashes. There were no browser errors or mutating requests; actual dataset and
backtest catalogue responses stayed identical. Existing port 8000 serves the
updated assets on refresh; no persistent server was started or restarted.

The automatic-prop browser fixture uses the same new grid through upload,
IS declaration, backtest, inline prop summary, configuration/source checking,
analysis reuse, downloads, batch results and reopen. Saved outputs remain
**360,000 USD** payouts minus **7,120 USD** acquisition costs = **352,880 USD**
Historical net, matching its unchanged arithmetic oracle. Evidence is in
`workflow-fixtures/test_automatic_apex_backtest_o0/` beneath this increment's
artifact directory, including `verification.json`, report JSON and CSV downloads.
All fixture servers shut down after their checks. Reproduce into a new evidence
directory, preserving these original outputs:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_strategies_browser.py \
  tests/test_automatic_prop_browser.py tests/test_optimization_browser.py \
  --basetemp artifacts/unified-grid-NEW
```

Qualification: **39 form/grid/navigation checks** and **31 workflow/report checks**
passed (70 total), with one existing dependency deprecation warning per run.
Logs and JUnit files are `browser-results.*` and `workflow-results.*` in this
increment's evidence directory. Checks include source-timezone declarations,
parameter type/precision validation, preparation/replay progress, duplicate-submit
protection, worker retry, mobile overflow, sorting, reuse, prop configuration and
downloads, benchmark comparison, manual OOS and durable report reopening.
JavaScript syntax and patch whitespace checks also passed.

# Selectable frozen optimization columns — 2026-10-29

The normal saved batch results now include a collapsible **Freeze columns**
section with searchable checkboxes for every parameter, metric, Trial and report
link. Only Trial is frozen by default. Checked columns move to the left; unchecked
columns scroll. Reset to Trial and Unfreeze all are provided. Varied parameters
remain highlighted regardless of freezing. Selections are stored per strategy in
this browser, separately from server calculations and saved reports.

Actual rendered frozen widths are limited to 40% of the table viewport. Additional
boxes are disabled with a Width limit label and an explanation. Checked columns
remain available to uncheck. Narrow screens temporarily release selections that
no longer fit, restoring them when widened. Sticky headers work even when no
columns are frozen. Window scrolling updates header positioning without
reprocessing every result cell. No production backtest/prop arithmetic, source
adaptation, sizing, sampling or economics changed.

Actual product evidence is under
`artifacts/optimization-freeze-20261029/live-final/`. Saved job
`ad0b3cec75864d7897c6c855160c0fa9` has **128 trials and seven varied parameters**.
The browser demonstrated the existing page with only Trial frozen, then Trial +
Min rr + Use adx elev (375.30 px of a 1,266 px viewport), enforcing the maximum
at 495.05 px, below the 506.4 px allowance. A Trial + Historical net selection
used 254.08 px. At a 356 px mobile table width, only Trial remained frozen
(73.59 px); widening restored both saved selections. Screenshots capture the
controls, width rejection, two-axis scrolling and mobile behavior. Sorting,
pagination and refresh all retained the choices. All 128 saved result rows,
job metadata and the full CSV remained identical, with **no mutating requests,
new simulations or browser errors**. These are existing saved outcomes, not
newly calculated or forecast performance. No persistent server was started or
restarted; the existing portal serves the updated assets on refresh.

To reproduce without submitting any calculation:

1. Open `http://127.0.0.1:8000/#backtests/batches/ad0b3cec75864d7897c6c855160c0fa9`.
2. Expand Freeze columns and use Reset to Trial if this browser has prior choices.
   The table starts with Trial frozen; all seven varied parameters remain green.
3. On a wide desktop, check Min rr and Use adx elev. Their columns move to the
   frozen left area. Search filters the checkbox list without changing selections.
4. Select more available columns until others show Width limit. The displayed
   frozen width never exceeds 40%; unchecking a column frees space for others.
5. Reset to Trial and check Historical net · USD. Collapse the controls, scroll
   right/down, sort Historical net in both directions and change result pages.
   Trial/Historical net stay visible with aligned headers. Refresh retains them.
6. Narrow the viewport to 390 px. Historical net temporarily unfreezes; Trial
   remains. Widening restores the saved selection. Unfreeze all is also retained
   across refresh and leaves vertical headers sticky.

The saved `live-verification.json` contains measured widths and source SHA-256
values. `actual-job-before.json`, `actual-results-before.json` and
`actual-results-before.csv` preserve the original outputs; `verify-live.py.txt`
contains the exact non-mutating reproduction. Earlier verification attempts
remain separately inspectable in the parent evidence directory.

Automated qualification: **39 existing browser checks passed**, covering the
shared form, sweep execution, sorting, exports, report links, frozen/header
geometry on desktop/mobile, pagination, reuse and resumption. **Five new controls
checks passed** in `final-column-results.log/xml`: parameter/metric selections,
keyboard focus and Space activation, search/no matches, width rejection, resize
restoration, reset/unfreeze persistence, per-strategy isolation across ordinary
three-parameter and 32-parameter strategy results, malformed/blocked storage and
unchanged saved metrics/CSV access. The earlier bundle log records one newly
added fixture's rejected Decimal step; its corrected string-valued request passed
both the targeted rerun and final five-check suite. No product failure remains.
`qualification.json` resolves the final results by test case. Earlier logs and
fixture outputs are preserved. JavaScript syntax and patch whitespace checks
passed. Fixture oracles remain unchanged: one-/two-/three-contract arithmetic
runs produce **13/26/39 CU**, independent of freezing.

Run checks into a new directory to preserve the saved evidence:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_optimization_columns_browser.py \
  tests/test_optimization_browser.py tests/test_optimization_compact_browser.py \
  tests/test_strategies_browser.py tests/test_backtests_browser.py \
  --basetemp artifacts/optimization-freeze-NEW
```

Temporary fixture servers shut down through their normal test cleanup. The
existing report/configuration/prop-analysis routes and durable stores are reused;
there is no demo page, report recalculation or duplicate calculation store.

# Optimization column visibility and order — 2026-10-29

The saved batch's collapsible **Columns** panel now provides separate **Show**
and **Freeze** checkboxes, plus **↑ / ↓** controls. Only Show-selected columns
are displayed. Visible, unfrozen columns scroll normally. Hiding a frozen column
also unfreezes it; hidden columns cannot be frozen or moved until shown again.
Movement skips hidden columns and reorders each frozen/scrolling group separately,
keeping the frozen group on the left. All controls work with mouse, keyboard and
touch. A sort note identifies the active ordering even when its column is hidden.

Show all, Hide all, Reset layout and Unfreeze all support quick configuration.
An empty selection has a recovery message and retains the panel. Reset layout
shows all columns in their default order with only Trial frozen; Unfreeze all
preserves visibility and order. The previous 40% frozen-width limit, sticky headers
and varied-parameter highlighting remain. Small selections use their natural
width. Preferences are saved per strategy in this browser; valid earlier
freeze-only preferences migrate with all columns shown. Saved jobs, reports,
metrics and full CSV contents remain authoritative and no calculation is triggered
by layout changes. Production backtest/prop arithmetic, adaptation, sampling,
sizing and economics are unchanged.

Actual product evidence is saved in
`artifacts/optimization-layout-20261029/live-final/`. On existing job
`ad0b3cec75864d7897c6c855160c0fa9` (**128 saved trials, 48 available columns**), the
normal page was reduced to **11 selected columns**. The saved left-to-right order
begins Historical net, Trial, Total net P&L, then the selected parameters and other
metrics, with the report link last. Historical net and Trial were frozen in that
order. The frozen area measured **249.59 px / 1,266 px**, leaving roughly 80% of
the viewport for scrolling results. All other columns were absent from the
visible table. A 400 px horizontal scroll and vertical/page scrolling retained
aligned selected headers. Changing pages, refresh and opening backtest
`236973b9f07a491e9af0c64a57d6e840` then returning all retained the custom layout.
On a 390 px screen, Trial remained frozen at **73.59 px / 356 px** table viewport;
widening restored the saved frozen order. All 128 result rows, job metadata and
the complete CSV were identical before/after, with **no mutating requests or
browser errors**. No new historical or future performance was calculated.

Reproduce through the existing portal without running a backtest:

1. Refresh `http://127.0.0.1:8000/#backtests/batches/ad0b3cec75864d7897c6c855160c0fa9`.
2. Expand Columns, then Hide all. Expect the recovery message. Check Show for
   Trial, Historical net · USD, Total net pnl and Backtest report. Only those
   four columns appear; the other 44 remain hidden.
3. Check Freeze for Trial and Historical net · USD. Move Historical net earlier
   to place it before Trial within the frozen group. Use the movement controls
   for the scrolling fields to change their order independently. Hiding a frozen
   column removes its freeze selection as well.
4. Refresh and change result pages. Expect the same visibility/order/freezing.
   Open a selected report link and return to the job; its saved layout remains.
5. Use Show all to reveal all fields, or Reset layout to restore the default
   order and only Trial frozen. Narrowing the viewport releases frozen columns
   that no longer fit without losing the saved wide-screen preference.

The evidence includes four screenshots, the complete original job/results/CSV,
`live-verification.json` with measured geometry and exact source SHA-256 values,
and `verify-live.py.txt` for the automated read-only reproduction. Earlier
verification attempts remain separately inspectable. The existing port-8000
portal serves the updated static assets on refresh; no persistent server was
started or restarted.

**47 browser checks passed**, with one existing dependency deprecation warning.
`artifacts/optimization-layout-20261029/final-results.log` and `final-results.xml`
record the complete focused gate. Checks cover visibility, hiding frozen and
sorted columns, empty selections, bulk/reset actions, ordering both groups,
keyboard activation/focus, persisted layouts, migration from freeze-only storage,
per-strategy isolation, blocked/malformed storage, width limits, resize recovery,
mobile overflow, sorting, CSV downloads, pagination, report reopening, sweep
execution/reuse and resumption. Synthetic numerical oracles remain **13/26/39 CU**
for one/two/three-contract arithmetic reports, independent of layout. Normal
fixture stores, screenshots and verification JSON are retained under the same
evidence directory. JavaScript syntax and patch whitespace checks also passed.

Reproduce into a new directory to preserve earlier evidence:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_optimization_layout_browser.py \
  tests/test_optimization_columns_browser.py tests/test_optimization_browser.py \
  tests/test_optimization_compact_browser.py tests/test_strategies_browser.py \
  tests/test_backtests_browser.py --basetemp artifacts/optimization-layout-NEW
```

Temporary fixture servers stopped through their normal cleanup. The implementation
uses the existing batch/report workflow and storage; the only new persistence is
browser-local display preferences.
## Automatic LucidFlex 50K and Apex together — 2026-10-29

New ordinary backtests, CLI runs and optimisation trials run the existing Apex
50K EOD model **and** LucidFlex 50K, publishing two independent analyses into
the existing catalogue. `automatic_prop_analysis` remains the Apex compatibility
reference and its `companions` records Lucid. User datasets, prior reports,
archived evidence and manual-only OOS execution are preserved. No vendor
executable, DLL or generated report participates in either calculation.

Current provider pages were checked before implementation. The newer
[customization](https://support.lucidtrading.com/en/articles/16226050-lucidflex-customization)
and [consistency](https://support.lucidtrading.com/en/articles/12945805-lucidflex-consistency-percentage)
pages make **40%** the standard evaluation requirement, superseding the older
overview's 50%. The model defaults to this standard and DLL on, with the user's
**$80.50** evaluation price and zero activation fee. DLL off is configurable.
The 50% add-on/cushion is outside this version. The current
[commission schedule](https://support.lucidtrading.com/en/articles/11508978-approved-products-and-commissions)
specifies NQ $1.75 and MNQ $0.50 per side, separately from Apex's schedule.
The public checkout page returned security verification during a direct browser
check; the price is therefore recorded as user-supplied, not independently
verified checkout pricing. `official-plan-cards.txt/.png` retain that observation.

The local, dated `provider_rules.json` accompanies every Lucid report and ZIP.
It records the $3,000 evaluation target, $2,000 EOD trail and +$100 lock; five
$150+ winning days per payout cycle; 50%-of-total-profit gross requests with
$500 minimum / $2,000 maximum; 90/10 split; 20/30/40-MNQ scaling at profit
$0/$1,000/$2,000; and 30-calendar-day inactivity including qualifying losses.
Payout requests force the drawdown lock. The full gross amount reduces account
equity, while only the 90% trader payout contributes to economic results.

Limits are visible in the product: DLL-on holds a $1,200 daily stop fixed above
the trail as an explicit assumption because the official Flex help pages do not
specify that adjustment. DLL-on requests stop the session at the first eligible
observed trade close within 18:00–15:45 New York time; if none was made, eligibility
is checked at session close. DLL-off requests occur at session close. No unobserved
intratrade payout or bank-settlement timing is fabricated. The model ends at five
sim-funded payouts and excludes discretionary early live transitions/live returns.
No provider evaluation deadline is imposed; a 2,000-weekday computational guard
produces censored paths, not provider failures. Censored funding chains make
acquisition timing unavailable. No complete provider-rule parity is claimed.

Inspectable final product evidence is
`artifacts/lucidflex-50k-20261029/qualified-portal/test_both_automatic_models_act0/`.
This is a normal isolated datastore created through dataset upload → IS backtest
→ both automatic prop analyses, with an explicitly labeled synthetic source:

- Source backtest: `e5b6618b84674fe984621e1d3c818764`.
- Apex saved analysis: `3eb1886cad49415bb276c6ab28ab1937`.
- Lucid saved analysis: `2b412988896b41afb94b82e033f98b5b`.
- `backtest.json`, `apex-report.json`, `lucid-report.json`, `source-check.json`,
  `provider_rules.json`, standard `analysis.zip`, screenshots and
  `verification.json` preserve actual outputs. Normal `backtest_runs/`,
  `prop_analyses/` and SQLite catalogues remain available to reopen these reports.

The source has 60 weekdays, one $3,000 net reference-contract trade per day and
zero adverse bound. These are synthetic arithmetic inputs, not market outcomes.
Independent expected values:

1. Evaluation at 1 MNQ makes $300/day and passes after 10 days, with no additional
   activation weekday or fee. Training acquisition is $80.50 and replacement is
   10 weekdays. Every evaluation sizing point uses 3,000 paths.
2. At selected 3 MNQ, $900/day permits the $2,000 gross cap after each five-day
   cycle. Five requests withdraw $10,000, pay the trader **$9,000**, and finish
   the sim-funded stage after **25 days**. The final holdout uses 20,000 paths.
3. Two 25-day accounts separated by 10 replacement weekdays fit the 60-weekday
   observed history. Across five slots: **$90,000 trader payouts − $805 acquisition
   costs = $89,195 historical net**. The separate Apex oracle remains **$352,880**
   across its default 20 slots. These totals have different account models and
   slot counts and are not future forecasts or single-account lifetime payouts.

`independent-cash-oracle.py.txt` imports no AlphaQuest account/calculation code.
It reads the saved source trades, rebuilds the payout ledger with Decimal
arithmetic, independently ranks all 40 funded sizes, and matches every saved
score plus historical cash. Run it with the project Python to reproduce
`independent-cash-oracle.json` in the same evidence directory.

To inspect the saved final workflow without recomputing, optionally start:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/lucidflex-50k-20261029/qualified-portal/test_both_automatic_models_act0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8011
```

1. Open `http://127.0.0.1:8011/#backtests/report/e5b6618b84674fe984621e1d3c818764`.
   Expect distinct Apex **$352,880** and LucidFlex **$89,195** Historical net cards,
   provider labels, fees/slots and links to both saved analyses.
2. Select **Configure prop analysis**, then **LucidFlex 50K**. Expect price 80.5,
   activation 0, five slots, DLL on and MNQ commission 0.50/side. Leave export
   empty and **Check source**: expect 60 native held-OHLC trades, no fabricated
   measured MAE, and the Lucid model identity. Unknown instruments disclose that
   source costs are retained until explicit instrument identification.
3. Try six slots and check: expect rejection and disabled Run. Restore five,
   check and **Run**: the existing durable Lucid analysis reopens with the same ID.
   Inspect Historical replay, Source & model, official links and the rule snapshot.
4. Download the ZIP and JSON; reload/reopen. Expect identical bytes and no new
   calculation POST. The earlier Apex report and original source trade CSV remain
   byte-identical. Stop this optional user-started server with Ctrl-C.

Automated boundaries cover intratrade floor touches on winning trades, gap
overshoots, DLL pause, payout-forced lock, full gross deductions versus trader
receipts, the $500 gross minimum, scaling thresholds, five-payout termination,
DLL-on trade-close request stopping, DLL-off session-close behavior, activity
from losses, 30-calendar-day expiry, evaluation consistency, censoring, and
zero extra activation time. Batch results and scalar MT19937 draw consumption
match an independently advanced step ledger. Missing/deleted companion results
invalidate reuse; failed companion publication rolls back the primary analysis.
Every path count is retained; vectorized random-number prefetching consumes the
same scalar stream, rather than replacing requested paths with fewer simulations.

Rebuild and reproduce using fresh unused basetemp paths:

```sh
.venv/bin/python setup.py build_ext --inplace
PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_lucid_prop.py tests/test_lucid_prop_workflow.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_lucid_prop_browser.py \
  tests/test_prop_training_economics_browser.py tests/test_optimization_columns_browser.py \
  --basetemp /tmp/alphaquest-lucid-review-NEW
```

The first browser attempt identified a missing browser binary after a Playwright
upgrade; the matching Chromium was installed before rerunning. Early broad
qualification was interrupted to optimize long low-profit paths. Those logs
remain separate; final logs/JUnit are `final-browser.*` and
`final-integration.*`. Fixture servers shut down on teardown. Test counts are
reported separately from the saved product outputs and independent ledger.

Final source-hour refinements enforce the normal 18:00–16:45 New York trading
window, including DST and Sunday reopen, without fabricating a 16:45 liquidation
price for late source exits. Provider auto-flattening itself is not an account
breach. A normal synthetic backtest/API source check saves its actual HTTP 422
boundary response under `boundaries/test_late_source_exit_is_reject0/`; the
source still earns its independently known 60.00 CU and remains readable.
On-demand requests are limited to observed trade closes in 18:00–15:45 New York
time. Later eligibility waits until the session closes, so it cannot skip a
subsequent source loss. Holiday early closes require properly session-filtered
source data and are not independently validated here.

Qualification logs distinguish the gates: the broader API/reuse gate passed
**93 checks** and the browser/regression gate passed **eight workflows**. After
the clock refinements, **71 kernel/API checks** passed in
`qualified-kernel-rerun.log/.xml`, **four API/step-ledger boundaries** passed in
`boundaries.log/.xml`, and the final saved portal workflow passed in
`qualified-portal.log/.xml`. One boundary oracle initially expected a hard breach
from a continuous loss; the correct first limit is the soft DLL at
2,000 − 1,200 = 800. That expected value was corrected without changing the
account engine, and the original failed log is retained. The all-40-size
independent Decimal oracle also passes on this final qualified report. A full
repository suite is not claimed; the costly standard-count full Python/compiled
portal parity test was deselected, while kernel/state/draw-stream comparisons
and the normal compiled-count product demonstration passed.

Local activation replaced the verified idle PID 54529 with persistent portal
**PID 98138**, using the same original `data` directory. Stop it with
**`kill 98138`**. All catalogue rows, current dataset contents, the 128-trial
completed optimisation and all files of the existing **129 backtests / 129 prop
analyses** matched before/after. No synthetic source was added to the user store.
`activate-local.py.txt`, `activation.json`, server log/PID, source ZIP/hashes,
before/after preservation snapshots and live screenshots are in the evidence
directory. The live form exposes both providers and the confirmed Lucid settings:
80.5 evaluation, zero activation, DLL on, 40% consistency, 0.50 MNQ/side.

`live-verification.json` and `live-source-check.json` record a genuine boundary
on the user's latest saved source `e78d012fa73f491699002a98d2dc213e`: it holds a
position beyond Lucid's regular 16:45 New York cutoff, so its Lucid source check
returns **422 incompatible**, rather than an invented liquidation or a provider
account failure. Rerun a new backtest with an earlier source flatten time to
obtain a compatible Lucid calculation. Existing Apex results remain unchanged;
new compatible backtests create both reports automatically. No financial run,
OOS request or deletion was submitted during live verification.

For that VWAP strategy, time parameters use **Chicago** time, separately from
the dataset's New York timestamps. Its existing `eod_flat_time=1555` means
16:55 New York on a normal full session. For a compatible next IS backtest, use
`use_eod_flat=true` and a cutoff such as **`eod_flat_time=1540`** (16:40 New York),
then review and run the new parameter set. The original strategy defaults,
parameter sets and prior results were not changed. Early-close inference can
move its exit earlier and remains a disclosed backtest research assumption.

A second, provider-priced product fixture verifies actual NQ → MNQ commission
replacement through the full portal workflow:
`artifacts/lucidflex-50k-20261029/priced-portal/test_known_nq_source_provider_0/`.
Its labeled synthetic NQ trade earns $3,000 before $10 slippage and $3.98 source
commission, leaving $2,986.02. Lucid simulation restores that source commission
once, retains slippage, scales to MNQ and charges two $0.50 sides, yielding
**$298.00 per MNQ**. Evaluation at one micro needs **11 days** (ten earn only
$2,980), with no added activation day. At three micros, five capped payouts still
pay the trader $9,000 in 25 days. The 11-day replacement leaves only 24 days for
the second account: four further payouts. Across five slots, this gives
**$81,000 payouts − $805 costs = $80,195 net**. The separate Apex result stays
$352,880. These remain synthetic arithmetic results, not market outcomes.

That ordinary backtest is `0ec901deff7248588941fad4991ea0fb`; its Lucid analysis
is `478cfe76939047b8ad3c7433572034a8`. Inspect `backtest.json`, `lucid-report.json`,
`trades.csv`, `analysis.zip`, the two screenshots and `verification.json` in that
directory. This additional browser workflow passed (`priced-portal.log/.xml`).
The standalone Decimal oracle now independently reconciles its source commission,
all 40 size scores, 11-day acquisition timing and $80,195 cash outcome too;
`independent-priced-cash-oracle.json` saves those results. The earlier $89,195
fixture deliberately has unidentified synthetic instrument units and retains
zero source trading costs with the product's visible notice. It qualifies the
account ledger; this second fixture additionally qualifies provider repricing.


## Daily shared market comparisons (2026-10-30)

Market comparisons now save DAY observations and share the buy-and-hold series
across matching optimization trials. This changes comparison storage and exports;
prop calculations continue to use their saved trade/intratrade-risk sources.

User journey: run an optimization from the existing New backtest form, open each
completed report, inspect Market benchmark, and download Daily comparison CSV.
The initial balance and each observed source-local date appear once. Each run
has its own strategy series and the same shared holding reference when dataset,
dates, quantity, execution settings and calculation version match. Summary
drawdowns still use all replay bars. The ordinary report-to-prop configuration,
source checking, analysis and durable-report workflow remains covered by
`tests/test_optimization_compact_browser.py`.

Reproduction and independent arithmetic are in `docs/market_benchmark.md`.
The synthetic two-day compact-optimization browser journey expects holding
equity `10000, 10026.50, 10023.00` and strategy net profits `26, 52` for
one/two contracts, with one shared holding file. The four-bar qualification
fixture expects daily strategy `10000, 10168, 10168`, holding
`10000, 10194, 10188`, and unchanged all-bar drawdowns `226, 220`. Changing
holding quantity, costs, capital or dates creates a different holding reference.
Corrupted shared data rejects display/download/reuse rather than overwriting
it. Deleting one run preserves other reports and their downloads.

Saved evidence: `artifacts/market-equity-day-20261030/` contains the independent
existing-run daily selection, browser downloads/screenshots, automated checks,
and the existing-report conversion catalogue backup/journal/verification.
Earlier qualification evidence remains unchanged. Temporary browser servers
are stopped by their fixtures; no persistent demonstration server is required.

## Architecture documentation increment — 31 October 2026

Historical layout and validation record. The simplified guide and current
navigation are described in the following documentation increment. Its
layout-specific checks apply to the saved snapshots, not the current overview.

This increment documents the existing product and proposed campaign/execution
extensions in [architecture.md](architecture.md). It introduces no production
calculation, schema parser, API, storage or UI behavior. Existing reports and
qualification evidence remain unchanged. The standard product journey remains
completed backtest → Configure prop analysis → Check source → Run analysis →
durable report/downloads; the guides linked from the architecture describe it.

To inspect and reproduce the documentation review:

1. On GitHub, open the repository README → **Architecture decisions**. Use its
   section links for **Current implementation**, **System and data flows**,
   **Export contract**, **Acceptance gates** and **Evidence register**. Follow
   **Documentation index** and **Repository home** to return. Relative links
   retain the branch/commit being viewed; local edits must be published before
   they appear on GitHub.
2. Expect Python backtesting and local prop reports to be marked implemented;
   standalone MultiCharts ingestion, the v1 exchange schema, general portfolio
   allocation and live route qualification remain proposed/pending. The diagram
   keeps external generated results in development qualification.
3. Inspect the export contract. The synthetic worked example has source net
   USD 36 unchanged and simulated one-MNQ net USD 1.00 with an explicit USD 0.50
   per-side override. Export net 36.00000001 meets the existing tolerance;
   36.00000002 rejects. Duplicate identity, quantity or UTC-entry mismatches
   reject; missing MAE/MFE is not represented as a measured zero. Fixtures remain
   in tests; this documentation does not add product test controls.
4. Expect all 13 ADRs to have proposed, unassigned accountable roles and next
   validation actions. Missing campaign values and installed-system evidence
   remain explicit. Annual slot sizing is distinguished from a future fixed-date
   received-cash objective; no campaign PASS or new parity claim is made.
5. Run the saved documentation/arithmetic check from the repository root:

   ```bash
   .venv/bin/python artifacts/architecture-documentation-20261031-01/validate.py
   .venv/bin/python -m pytest -q tests/test_prop_commissions.py tests/test_prop_analysis_api.py
   ```

   Expect all relative links/anchors in the four changed Markdown files to
   resolve, 13 decision/owner/review rows, both Mermaid blocks to be present,
   consistent budget arithmetic and the independently expected cost example.
   The focused tests exercise existing source checks, cost replacement and
   durable downloads in temporary storage; they do not qualify a live route.

Evidence is saved in `artifacts/architecture-documentation-20261031-01/`:
`validation.json`, `focused-tests.txt`, `mermaid-validation.json` and `snapshots/`.
The Mermaid record reports parser results separately from visual rendering.
To repeat the parser check, follow `mermaid-reproduction.md` in that directory.
These are local inspectable artifacts; GitHub navigation uses the tracked guides
rather than links to ignored artifacts. No browser or persistent server was
started for this documentation increment.

## Architecture simplification — 31 October 2026

Historical layout record. The following increment restores alternatives and
review conditions; the earlier size checks apply to its saved snapshots.

The [architecture guide](architecture.md) is now a 93-line overview with one
workflow diagram, a compact decisions table and five next steps. Technical
contracts, storage, ownership, acceptance gates, evidence and budget sources are
in the linked [architecture reference](architecture_reference.md). Repeated
decision/review tables and the second workflow diagram were removed.

On GitHub, follow repository README → **Architecture guide**. Expect the current
system and proposed extensions to be clear without opening the reference. Use
**Detailed references** for a specific question, then **Architecture overview**
in the reference to return. The docs index links both pages. Missing campaign
values, numerical examples, qualification limits and dated price assumptions
retain their earlier meaning. The product workflow and stored results are unchanged.

Reproduce the link, size, ADR and detail-preservation checks from the repository root:

```bash
python3 artifacts/architecture-simplification-20261031-01/validate.py
```

Expect all local links/anchors to resolve, all 13 decision IDs to remain, the
overview to stay below 100 lines/800 words, and the moved technical sections to
match their prior contents. Inspect `validation.json`, `before/` and `after/`
in that fresh artifact directory. Earlier evidence remains unchanged. No
application tests or servers are needed for this documentation reorganization.

## Architecture decision rationale — 31 October 2026

Historical wording; the language edit below retains these decisions and checks.

The [architecture guide](architecture.md#decisions) now records the preferred
approach and rationale, deferred alternatives and specific reconsideration
conditions for each of the 13 ADRs. The short system overview, single workflow
diagram and next steps remain; technical requirements stay in the unchanged
[architecture reference](architecture_reference.md).

On GitHub, open repository README → **Architecture guide** → **Decisions**.
Expect to find, for example, MultiCharts versus TradingView/Sierra/Python visual
references, optional Sheets versus a custom tracker, and manual versus automated
reconciliation, with reasons and review triggers beside each choice. Owners and
adoption dates remain unset. The diagram now says **Run prop simulation** and
the accompanying sentence explains its inputs, purpose and local execution.

Run the saved documentation check from the repository root:

```bash
python3 artifacts/architecture-decisions-20261031-01/validate.py
```

Expect all local links/anchors to resolve, all 13 ADRs to include alternatives
and reconsideration conditions, the supporting reference to match its prior
hash, and the diagram structure to be unchanged apart from the clearer label.
Inspect `validation.json`, `before/` and `after/` in that fresh artifact directory.
Earlier snapshots and evidence are preserved. This is a documentation edit;
no application tests or servers were started.

## Architecture language edit — 31 October 2026

Shortened the [guide](architecture.md), [reference](architecture_reference.md)
and [docs index](README.md). All 13 choices retain alternatives, reasons and
review triggers. Technical limits, model gaps and dated price assumptions remain.
The product workflow is unchanged; earlier evidence is preserved.

From GitHub's repository README, follow **Architecture guide**, then **Details**.
Expect shorter wording and working return links. Reproduce the word-count,
link and key-detail checks from the repository root:

```bash
python3 artifacts/architecture-language-20261031-01/validate.py
```

Inspect `validation.json` and `before/`/`after/` there. Application tests, live
checks and servers were not needed for this wording edit.

## Architecture ownership removal — 31 October 2026

Removed the placeholder ownership table and its links. From repository README →
Architecture guide → Details, expect no ownership section or dead ownership link.
Requirements, model limits and decision trade-offs remain. Earlier layout checks
describe their saved snapshots; those records are unchanged.

Check current navigation with:

```bash
python3 artifacts/architecture-onboarding-20261031-01/validate.py
```

Expected: all links resolve, the ownership section is absent and all 13 decisions
remain. Before/after documents and `validation.json` are in that artifact folder.
No product behavior changed or server started.

## Architecture for new readers — 31 October 2026

The [architecture](architecture.md) now has four sections: requirements, the
end-to-end product workflow, a component diagram/code map and the unchanged 13
decision rows. The code map explains the boundaries between UI/API, data,
strategies/execution, jobs, prop calculations, reports and reuse.

Follow repository README → Architecture guide → Workflow → Code. Expect direct
source links and a diagram connecting browser, API, jobs, calculations and
SQLite/report files. Workflow steps include automatic prop results, manual
configure/check/run and manual OOS from a saved IS report.

Campaign forms/checks moved to the [research guide](research_workflow.md#campaign-checks),
prices to [planning](planning.md), and the unimplemented export design to its
[proposal](designs/trade_export_v1.md). The [technical reference](architecture_reference.md)
keeps current storage/export limits and worked rejection/cost examples. Numbered
evidence/gate registers were removed from the reading path; existing dated
results remain in this guide and their saved artifacts. Earlier layout checks
describe their snapshots, not the current organization.

Reproduce navigation, relocation, decision and source-preservation checks:

```bash
python3 artifacts/architecture-onboarding-restructure-20261031-01/validate.py
```

Expected: all links resolve, all 13 decision rows match, moved technical limits
and planning values remain, no ownership/evidence register returns, and production
source hashes match the saved pre-edit record. Inspect `validation.json`,
`before/` and `after/`. `mermaid-final-validation.json` records parsing and local
browser rendering; SVG/PNG output and reproduction steps are saved alongside it.
GitHub rendering itself was not tested. No production
calculation, application test or persistent server was started for this edit.

## ADR meaning audit — 31 October 2026

Earlier shortening checks preserved the 13 rows but missed some decision
reasons and caveats. Compared every ADR with the saved full register, including
its rationale, costs, acceptance notes and review triggers. Restored weakened
points in the [decision table](architecture.md#decisions),
[research checks](research_workflow.md#campaign-checks) and
[data/cost assumptions](planning.md#market-data-access). The code diagram is unchanged.

From repository README → Architecture guide → Decisions, expect the included-feed
cost rationale, the paid MBO/L3 alternative, shared licence costs, simulator upkeep,
independent specification checks, data limits and recovery caveats to be explicit.
Lucid depth availability does not prove free L2 for every account; Databento is
the chosen planned MBO option, not the only possible provider. Sources are linked
in the planning notes; no account permissions or live feed was tested.

Inspect the item-by-item manual audit in
`artifacts/architecture-adr-audit-20261031-01/adr-audit.md` and `adr-audit.json`.
They retain the full pre-shortening rows and map their decision points to current
text. Original administrative placeholders stay removed; outdated Python/C#
timing and blanket platform-capability claims are recorded as corrections.

Reproduce the link, coverage-anchor, diagram and source-preservation checks:

```bash
python3 artifacts/architecture-adr-audit-20261031-01/validate.py
```

Expect all 13 manual coverage records and their quoted text/anchors to resolve,
the diagram and production code to remain unchanged, and prior evidence to stay
intact. `validation.json`, `before/` and `after/` save the checks and documents.
Automated text checks support the manual meaning review; they do not prove
semantic completeness. No application tests or servers were started.

## Lucid funding calibration continues long paths — 2026-10-31

The reported message came from Lucid model v1's computational guard. One
unresolved evaluation attempt at 2,000 sessions raised out of the whole
20,000-chain training calibration. Funded sizing and replay were therefore
unavailable even with a 94.76% holdout evaluation pass rate. An unresolved path
is distinct from a drawdown failure. The previous UI explanation called this a
failed evaluation, which was misleading.

The local v2 model continues those paths, retaining equity, trailing floor,
consistency, activity and bootstrap state, up to a documented 20,000-session
limit per attempt. Any paths still unresolved there remain explicitly censored;
there is no survivor-only timing average, dropped path, reset at session 2,000,
invented pass rate or fallback delay. Standard simulation counts and training
selection before holdout are retained. Existing model-v1 reports remain byte
identical, carry an earlier-model notice and offer the normal reconfiguration
flow with their saved Lucid settings copied.

### Actual affected report and real product journey

The user's source is backtest `af13f6ea47304ffe9ec578a9a5ea4157`, with 472 trades
and source net P&L **42,281.44**. Its earlier Lucid analysis
`f9a5eb5af94649ce8faad4475fde4b1c` had no funded outcomes. The containing
16-trial activity was complete and no prop analyses were queued/running before
source changes. An inventory of **600 existing source/report files** was saved
before this increment.

Using the ordinary report **Configure new analysis → Check source → Run
analysis** flow published Lucid analysis **`8dbec3c4ed4340baa5ae56329ecd1f4b`**.
No backtest POST was sent. The source snapshot and every resolved setting match
the earlier report. Expected observations from its saved outputs:

- Training evaluation size remains **1 MNQ**. With the longer evaluation
  horizon, training pass rate is **2603 / 3000**, acquisition cost is
  **80.50 / (2603 / 3000) = 92.77756434882828**.
- All **20,000** training funding chains resolve. **226** include an attempt
  beyond 2,000 sessions; the longest attempt is **4,256** sessions. Mean total
  replacement time is **889.7503** weekdays; median is **778**. There are **zero**
  censored training chains at the extended limit.
- Holdout evaluation passes **18,976 / 20,000 = 94.88%**, with zero censored
  paths. **21** single evaluations continue beyond 2,000 sessions, with a longest
  attempt of **2,893** sessions. The separate holdout funding chains include
  **10** continued paths, longest attempt **2,399**, and mean funding time
  **608.0654** weekdays.
- Funded sizing selects **1 MNQ**. Overview, Sizing and Historical replay are
  available. Historical net is **$8,237**, using frozen training acquisition
  economics. This is a saved research-model replay, without a future-outcome
  guarantee or new provider-rule parity claim.
- Reload reads the saved result. Earlier report JSON/ZIPs, source trades and
  existing Apex results remain unchanged. Original optimization trial snapshots
  retain their original automatic report IDs/metrics; no saved table rows are
  rewritten by presentation or by this manual Lucid recalculation.

Open the fixed report on the existing server:

```text
http://localhost:8000/#backtests/prop/job/8dbec3c4ed4340baa5ae56329ecd1f4b
```

To reproduce without running the strategy again, open the earlier report,
select **Configure new analysis**, verify LucidFlex 50K and the copied settings,
then **Check source** and **Run analysis**. On unchanged source/settings/current
engine, the existing v2 analysis reopens. Evaluation shows the continuation
counts and computational limit; its calibration JSON includes exact values.
Source & model offers the rule snapshot, calculations, sizing CSVs and ZIP.
The complete existing-source journey is also runnable as:

```bash
.venv/bin/python tests/review_lucid_funding_continuation.py \
  --old-id f9a5eb5af94649ce8faad4475fde4b1c \
  --output artifacts/lucid-funding-recheck-NEW
```

This command uses the existing local portal and deliberately requests a new
prop calculation only if no identical current-model result exists. It starts no
server and closes its Chromium instance. The user's existing server was used;
no persistent server was started by this increment.

Evidence is under `artifacts/lucid-funding-continuation-20261031/`:
`actual-training-chain.json`, `affected-report-before.json`,
`preservation-before.json`, and `actual-portal-verified/` containing source-check
JSON, old/new reports, calibration JSON, result ZIP, verification JSON and five
screenshots (earlier report, source check, funded outcomes, calibration,
historical net). The earlier `actual-portal/` attempt preserved the same
completed report but stopped at a review-script download-label mismatch; the
verified journey reopens that report without recomputing it.

### Independent numerical checks and synthetic product example

The tests' standalone arithmetic supplies **10 NQ currency units / 10 = $1 per
MNQ per session**, with no costs/adverse movement. Its $3,000 evaluation target
requires exactly **3,000** sessions; its largest-day consistency share is 1/3000.
At session 2,000 it is still open. The new model passes at exactly session 3,000
without resetting, adding a fee or changing the sampling stream. Limits of
2,999/3,000 sessions independently reject/accept the boundary. A deliberately
short 10-session guard still rejects an unresolved funding chain.

A separate scalar MT19937 block sampler and independent cash ledger checks long
failed attempts plus long successful attempts against both Python and compiled
kernels. The full calculation test resolves all 20,000 training and holdout
chains at 3,000 sessions. At one MNQ, $1 daily cannot meet a $150 qualifying day;
funded payouts correctly stay zero. Four slots cost **4 × $80.50 = $322**, so the
short historical replay correctly reports **−$322**. A valid funded result does
not require a positive payout or profit.

The Chromium example uploads a labeled SYNTHETIC eight-day dataset through the
normal dataset endpoint, creates a regular backtest, then selects Lucid,
explicit source commissions, 0.1 total NQ and four slots in the real form.
The source has a 0.5-point move at $20/point, yielding the same $10 per NQ / $1
per MNQ arithmetic. Source check, run, downloads, reconfiguration with copied
settings and reload are checked. Evidence is in `browser-corrected/`.

Reproduce with new temporary/evidence directories:

```bash
.venv/bin/python setup.py build_ext --inplace
.venv/bin/python -m pytest tests/test_lucid_funding_continuation.py \
  tests/test_lucid_prop.py tests/test_lucid_prop_workflow.py \
  tests/test_prop_training_economics.py -q
.venv/bin/python -m pytest tests/test_lucid_funding_continuation_browser.py \
  tests/test_lucid_prop_browser.py tests/test_prop_training_economics_browser.py \
  -q --basetemp artifacts/lucid-funding-browser-NEW
```

The browser fixtures own temporary servers and shut them down after testing.
Earlier browser diagnostics used an invalid NQ point value; source checking
correctly rejected it. The delivered synthetic example uses $20/point and keeps
that rejection evidence unchanged.

Final validation: **41 backend checks and 5 browser checks passed**. The
independent scalar reference also regenerated **every one of the 20,000 actual
training funding chains**, matching the compiled engine's total days, attempt
count and longest attempt exactly. It independently reproduced the 889.7503-day
mean, 778-day median, 226 continued chains and 4,256-session longest attempt.
Its output is `independent-actual-chains.json`; reproduce it read-only with:

```bash
.venv/bin/python tests/review_lucid_funding_reference.py \
  --old-report artifacts/lucid-funding-continuation-20261031/affected-report-before.json \
  --output artifacts/lucid-funding-reference-NEW.json
```

`preservation-after.json` confirms all **600** inventoried files remain byte
identical, the original 16 optimization trial snapshots are unchanged and no
strategy backtest was executed. Syntax/compilation and whitespace checks passed.
All temporary test servers and review browsers were closed. The existing user
server remains available; its process was not replaced or manually restarted.

## Refresh unavailable Lucid results in the saved batch — 2026-11-01

The continuation fix initially created a separate corrected Lucid report; the
optimization table still pointed at its original automatic reports. The user's
completed activity `342ceb7eee0345a4b0bb108d3f4e360c` therefore still showed only
**4 of 16** Lucid values, with **12** original reports unavailable because of
the earlier 2,000-session guard. The corrected report
`8dbec3c4ed4340baa5ae56329ecd1f4b` existed independently and was not yet linked
to its trial.

The real batch view now has **Refresh unavailable Lucid results**. It checks
sources using the saved Lucid settings, reuses verified current reports, and
submits the remaining Lucid-only requests through the ordinary AnalysisStore
worker. Pending/complete/error/source-rejection states survive reload. Each
updated table cell links to its durable report and identifies the updated
analysis; original model versions remain available in tooltips/CSV provenance.
No strategy backtest is run and no automatic source/Apex report is rewritten.

`optimization_prop_links` is an append-only link/index table in the existing
backtest catalogue, keyed to the existing trial. It holds the saved analysis
reference, checked identity and indexed historical-net value for exact sorting.
It is not a second report store. All calculations/charts/downloads stay in the
ordinary analysis catalogue. The original `optimization_trials.payload` JSON is
unchanged. Effective table sorting and Results CSV use the same link revision;
**Original results CSV** / `prop_revision=0` retrieves the original values.
Export fixes its revision before streaming; future revision inputs clamp to the
current revision. GET requests only read saved state.

The explicit refresh action can finish a failed publication link using the
already completed report. Startup likewise reconciles pending links with saved
analysis statuses, without running numerical work. Duplicate clicks preserve
queued jobs. Ordinary active-analysis source protection prevents source/activity
deletion during calculation. Deleting an inactive activity cascades its link
metadata while preserving independent prop reports.

Both job and pure-calculation keys now include the explicit model version.
Cached calculation JSON must declare that same model; the refresh also checks
that its report and numerical payload versions agree. Numerical source hashes,
exact native kernel identity, source/settings equality and artifact hashes
qualify a pre-existing report for reuse. A fresh prior v2 report can be reused
across storage/UI changes; an old report that reused calculations additionally
requires a matching calculation-cache implementation. These checks prevent
reusing an old unavailable calculation under a newer report label.

### Product demonstration and independent expectations

The synthetic test starts from a labeled ordinary dataset/backtest batch and a
controlled historical-engine oracle **inside tests**. Both original trials
show the earlier-model unavailable state. With source daily profit 3,000 per
NQ and zero source costs, one MNQ earns 300; evaluation takes **10 sessions**.
Funded selection at three MNQ pays all five 1,800 trader receipts in **25**
sessions. Over 60 historical weekdays, two funded cycles separated by ten
replacement sessions yield **2 × 9,000 × 5 − 2 × 80.50 × 5 = 89,195** net.
Both refreshed trials must independently produce that value. Original Apex
metrics and original result snapshots must remain unchanged.

Backend checks cover verified manual-report reuse, mismatched source/settings/
model/kernel rejection, exact current/original CSV values and report IDs,
stable Lucid sorting, a frozen pending revision, duplicate requests, source and
activity deletion rejection while queued, completed-link recovery without
resimulation, missing jobs, running jobs and explicit incompatible-source
reasons. Browser evidence checks pending work across reload, duplicate clicks,
updated sorting/CSV, original CSV, report navigation, configuration/source check/
run reopening the saved report, and a reload that submits no POST.

Reproduce using new evidence directories:

```bash
.venv/bin/python -m pytest tests/test_lucid_batch_refresh.py -q
.venv/bin/python -m pytest tests/test_lucid_batch_refresh_browser.py -q \
  --basetemp artifacts/lucid-batch-refresh-browser-NEW
```

To explicitly refresh a real completed batch through the existing portal and
save table/CSV/report-link verification:

```bash
.venv/bin/python tests/review_lucid_batch_refresh.py \
  --batch-id 342ceb7eee0345a4b0bb108d3f4e360c \
  --output artifacts/lucid-batch-refresh-review-NEW
```

This script uses the existing server, starts no server, and closes its owned
Chromium instance. Its action reuses matching completed analyses or requests
Lucid-only calculation; it never submits a backtest. The batch page itself
provides the same action without a script. Temporary browser-test servers are
owned and shut down by their fixtures. Provider rules, numerical transitions,
sampling counts and provider-parity status are unchanged by this increment.

### Actual saved batch delivery

The action was executed against the user's existing activity through Chromium.
It **reused one** verified previously corrected analysis and queued **11** new
Lucid-only jobs. All completed successfully. The table now has **16 / 16** Lucid
values, **12** updated report links, **0** pending and **0** unavailable/failed.
The original four available values remain unchanged, labeled with their saved
model version. The refreshed values include a genuine negative result; nothing
was replaced with a fabricated zero or forced positive outcome.

| Trial | Refreshed Lucid historical net (USD) |
| --- | ---: |
| 3 | 1,744 |
| 4 | 13,899 |
| 6 | 7,899 |
| 7 | 1,740 |
| 8 | 14,245 |
| 10 | 7,911 |
| 11 | 1,699 |
| 12 | 8,237 |
| 13 | -1,172 |
| 14 | 5,781 |
| 15 | 8,171 |
| 16 | 12,169 |

Open `http://localhost:8000/#backtests/batches/342ceb7eee0345a4b0bb108d3f4e360c`.
Expected observations: **16 / 16 Lucid values available**, no pending/failed/
unavailable values; Lucid column sorts using the actual linked net values;
updated cells open the matching saved analyses. **Results CSV** matches the
sorted table and records analysis IDs/model versions. **Original results CSV**
retains the four original values and twelve original empty fields. Reloading
reads saved results and does not submit a new calculation. The completed link
state also survived the existing development server's ordinary idle reload.

Evidence: `artifacts/lucid-batch-refresh-20261101/actual-portal/` contains
before/after table screenshots, refresh-start/progress totals, original and
updated trial JSON/CSV, and `verification.json`. Every updated table value was
reconciled with its own saved report's history; source snapshots and settings
were compared with the original analyses. SQL sorting was independently checked
against Python sorting and CSV values. The earlier independently validated
trial-12 analysis is reused unchanged at $8,237.

`preservation-after.json` verifies **618** existing source/report files remain
byte identical, including the previously corrected report. All **16** original
trial JSON snapshots are unchanged. The normal analysis catalogue increased
from **290 to 301** completed analyses, exactly the eleven requested new jobs;
128 prior incompatible records remain. No strategy backtest was submitted or
rerun. `optimization_prop_links` has 23 index entries: twelve initial links
(including one immediately reused result) and eleven publication completions.
Original Apex reports, backtests, source data and saved prior evidence remain
unchanged. No new persistent server was started.

Final checks: **86 focused automated checks passed** (83 backend and 3 browser),
including the ordinary result/pure-calculation reuse suite and explicit rejection
of valid-checksum caches carrying older or missing model versions. The prior
minimal cache-test fixture was updated to declare its current model version,
matching the strengthened production contract. Desktop/mobile read-only checks
also verified 16 report links, separate updated-result labels, no page-width
overflow, no JavaScript errors and no POST during presentation. Screenshots are
in `presentation/`. Syntax and whitespace checks passed.

Repeating the refresh on the completed real batch returned zero queued/reused/
blocked requests and kept revision **23** unchanged. No additional calculation
or link entry was created. The actual all-trial source/report reconciliation,
CSV checks and 618-file preservation audit are saved alongside these results.

## Compact batch table columns and unlimited freezing — 2026-11-01

This presentation increment removes Varies badges, narrows highlighted columns,
hides fixed parameters by default, shows all metrics by default and removes the
40% frozen-width restriction. Existing Show/Freeze/reorder controls and explicit
custom layouts are preserved. Reset layout restores the new automatic defaults.
A frozen group wider than the viewport pans horizontally without unchecking any
column. No report, calculation, source data, saved metric or OOS budget changes.

On the existing activity `342ceb7eee0345a4b0bb108d3f4e360c`, the fresh default
view shows 21 columns (four varied parameters, 15 metrics, Trial and report link)
and hides 28 fixed parameters. Independent browser measurements found each
varied header about 75 px narrower than a reconstruction of its previous badge/
padding decoration. The actual product allowed all 49 columns to be shown and
frozen, retained all selections on mobile/reload, reached the last column by
horizontal panning and restored defaults on Reset layout. Data JSON and CSV
were byte identical before/after, with zero modifying browser requests.

Evidence and four screenshots: `artifacts/compact-batch-columns-20261101/actual-portal/`.
Exact reproduction is documented in `docs/optimization.md`, using
`tests/review_compact_batch_columns.py`. It uses the existing server, owns/closes
its private browser and creates no numerical runs. Earlier saved evidence and
reports are preserved. Temporary browser-check servers are owned by their
fixtures and stopped after testing; no persistent server was started.

The layout increment's **13 browser checks passed**, including frozen groups
beyond the former width budget, all-visible-column freezing/panning, responsive
retention, automatic visibility across different grids of the same strategy,
legacy/custom preference migration, keyboard controls, sticky headers, sorting,
pagination, downloads and report navigation. Node syntax and whitespace checks
also passed. Only table presentation and local browser preferences changed.

## 2026-11-02 — VWAP EOD next-open execution and requested real rerun

The VWAP strategy now submits flattening at its resolved order cutoff and fills
at the next observed bar Open, using the existing execution engine and costs.
Entry restrictions and inferred early-close rules remain. New reports identify
`eod_next_open_inferred_session_close` and `order_timing=next_open`; the UI labels
older immutable cutoff-Close reports as an earlier model. The actual fill retains
its containing bar's close-labelled timestamp, with no fabricated tick time.

The normal backtest API reran all 32 requested parameters (stop 10, target 5,
ADX threshold 0, decay on, fixed one NQ, EOD order cutoff 1545) on the original
2021–2024 IS source, costs and declaration. New durable report:
http://localhost:8000/#backtests/report/2685e56b3bb24f05a643bbd7fa876cb7

Actual and independently expected result: **486 trades, $28,155.00 gross,
$1,934.28 commission, $26,220.72 net**, an increase of $110. All entries and
non-EOD trades are unchanged. Exactly 16 EOD fills match independent repricing
from saved raw next-bar Opens; their captured held-OHLC risk records have exit
phase `open`. The seven original report files remain byte-identical.

Against the corrected MC export, the 14 ordinary EOD differences now match.
484 complete trades match; a $35 gross difference remains across four known
shortened-session dates, including two blocked entries. This is not full MC
parity. No external executable or table was used as a production calculator.

The actual product journey was exercised from the new report through Trade CSV
download/reload, **Configure prop analysis → Check source → Run analysis** with
the normal Apex defaults, and durable result reopening. The run action reused
its already completed automatic Apex report
`d7412aae812644639c3365adb82d04f7`; settings/source identity matched, with no
duplicate analysis. The desktop/mobile browser checks had no JS errors.

Boundary observation: switching to LucidFlex and checking this exact source
returns HTTP 422, and Run remains disabled. Its regular next-open exits are
labelled 16:46 New York, beyond the unchanged strict source validator's 16:45
cutoff. The automatic Lucid companion `51f216f44446492e85aeaa0c1974c217` is
saved as incompatible. The requested 1545 configuration was not silently
changed, earlier exit prices were not invented, and timestamps were not
backdated. The bar label alone does not establish the actual fill tick time.

Evidence and exact reproduction:
`artifacts/eod-next-open-20261102/README.md`, including actual reports/downloads,
independent expected fills, source checks, old-report hashes, screenshots and
`verification.json` / `product-review.json`. Run:

```sh
.venv/bin/python artifacts/eod-next-open-20261102/verify-rerun.py.txt
.venv/bin/python artifacts/eod-next-open-20261102/review-product.py.txt
```

Automated validation: 96 focused checks passed, one unrelated browser case
deselected; Node syntax and whitespace checks passed. Long/short costs, DST,
missing bars, gap entry cancellation, bracket precedence, next-open risk
boundaries, cached/uncached replay equivalence and durable normal API/browser
workflows are covered. The separate existing-product synthetic review passed
normal, noon and 12:15 closes, each with independently expected net 88 CU.
Its outputs are at `artifacts/eod-next-open-synthetic-review-20261102/` and its
owned temporary server stopped. No persistent server was started; the real
report review used the existing port-8000 server. Earlier evidence/results,
datasets and the user's VM were preserved.

### Publication validation: legacy primary-summary discovery

The complete automatic-prop browser journey also verifies a legacy backtest
whose automatic-analysis metadata is absent while both Apex and newer Lucid
reports are saved. Discovery now prefers its completed Apex report for the
primary summary and labels any fallback using the saved account model. It
does not display a Lucid result under an Apex heading. The observed Apex
historical net remains $352,880 through report reopen, downloads, configuration,
source checking, run reuse, optimization and mobile legacy discovery.

The existing regression now targets the intended report ID when downloading,
keeps the automatically saved companion when checking reuse, and scopes Apex
sorting to its actual column. Both automatic-prop browser cases passed.
Saved observations and screenshots are retained at
`artifacts/push-main-validation-20261102/`; reproduce with
`.venv/bin/python -m pytest tests/test_automatic_prop_browser.py -q`.

### Publication validation: oversized frozen-group alignment

Repeated browser checks reproduced header/body misalignment while panning a
frozen group wider than the viewport. Oversized groups now use native
horizontal scrolling, while retaining every freeze selection and the vertical
sticky header. Groups that fit resume ordinary left pinning. This avoids
scroll-event-driven negative sticky offsets; no count or width limit is added.

All 10 column-layout/default browser checks passed, and the formerly
intermittent panning case passed eight consecutive independent runs. A real
read-only review of batch `342ceb7eee0345a4b0bb108d3f4e360c` froze all 49
columns, reached the final column, retained selections on mobile/reload and
verified unchanged result JSON and CSV. Screenshots and observations are at
`artifacts/native-wide-freeze-review-20261102/`. Reproduce using
`tests/review_compact_batch_columns.py` with that batch ID and a new output
directory. Only a private browser was opened/closed; no server or numerical
run was started by this review, and all existing reports/data were preserved.

### Publication validation: asynchronous IS/OOS report checks

The existing manual OOS browser checks now wait for completed backtest requests
and the returned report URL before reading edited IS values. This prevents a
previous hidden report heading from satisfying the same-heading assertion
while the new automatic analyses are still running. Simulation completion uses
the existing 180-second browser budget; counts and numerical assertions are
unchanged. Catalog assertions retain the declared Apex and Lucid companions
and still reject extra duplicate analyses.

Both research browser journeys passed after correction: four explicit manual
OOS executions remain in history when a new edited IS earns the independently
expected 60 CU, and the 120-weekday IS/OOS fixture retains 60 trades / 180,000
source net / 352,880 Apex historical net in each selected period, with normal
configuration/check/run reuse, downloads and reopening. The saved observation
files are `artifacts/push-main-validation-20261102/manual-oos-verification.json`
and `percentage-oos-verification.json`. These are explicitly synthetic normal
product workflows in isolated test libraries; their owned servers stopped.

### Final publication validation scope

The complete 982-test run finished with 977 passing cases, five browser
failures and one teardown error associated with the early-read OOS failure.
All five reported cases were corrected and passed focused reruns: automatic
Apex/legacy discovery (two browser cases passed), oversized frozen-group
alignment (10 column checks plus eight consecutive panning runs), both research
browser journeys, and prop-report deletion with its independent Lucid companion
retained. The OOS completion correction also removed its teardown error.

The prop deletion check now verifies the exact remaining companion links rather
than assuming deleting one Apex report clears every saved account analysis.
Backtest identity and the other saved report's bytes remain protected. Actual
workflow observations, screenshots and the original full-suite output are
retained under `artifacts/push-main-validation-20261102/`. The full suite was
not rerun from scratch after these corrections; the validation scope is the
completed full run plus the focused corrected-case reruns. JavaScript syntax
and Git whitespace checks passed. No production data or generated evidence is
included in the source commits.

## 2026-11-02 — Historical NQ closure reference and manual maintenance

Added `calendars/cme_nq_closures.csv`: 116 sourced session exceptions for the
last ten complete calendar years, 2016–2025, with 89 early closes and 27 full
session closures. Each row records its Chicago session-ending date, scheduled
close (empty for full closures), event, source, review note and review date.
CME notices, dated broker-republished CME tables and DTN notices distinguish
Globex equity hours from stock-exchange/floor, settlement and margin deadlines.
The README explains source limitations and point-in-time provenance explicitly.

This is a reference-data/documentation increment; strategy integration follows
separately. Existing reports, datasets, backtests, prop analyses and earlier
saved evidence remain unchanged. There is no additional page or API. The
existing report → configure → check → run → durable-report journey continues
to use the existing strategy until the calendar integration is implemented.

User journey: open `calendars/README.md`, inspect the linked CSV, filter to
2021-01-18, 2021-09-06, 2024-01-15 and 2024-09-02, and follow each source URL.
Expected: each is a 12:00 CT early halt, yielding an 11:55 order cutoff under a
separately applied five-minute buffer. Thanksgiving Friday and Christmas Eve
can instead close at 12:15. Good Friday 2021/2023 closes at 08:15; the 2018/2025
mourning sessions close at 08:30 rather than being full closures. The maintenance
guide explains that a holiday's evening reopening belongs to the next session,
that weekends are separate, and that absent dates outside reviewed coverage
are unknown. It contains exact editing, validation, snapshot and Windows-copy
checksum instructions. `verified_on` is not an exchange announcement timestamp.

Run `.venv/bin/python scripts/validate_market_calendar.py` from the repository
root. Expected structural result: 116 rows, 89/27 split, no missing exception
years. Source accuracy/completeness remains a manual notice review; the checker
does not certify either. Actual validation is saved at
`artifacts/cme-calendar-review-20261102/validation.json`; sampled independent
notice expectations and boundary observations are in `checked-cases.json`.
Eighteen dated source cases matched; seven explicitly regular dates were absent.
Nine malformed/boundary files were rejected, including duplicate dates, invalid
times/status/timezone, missing sources and dates outside coverage. UTF-8 BOM and
quoted CSV fields were accepted. Syntax and whitespace checks passed. No server,
VM operation, trade submission, source-data mutation or recalculation was run.

### Calendar coverage prerequisite for causal strategy integration

The original 2016–2025 snapshot remains in commit `107c533`. The working CSV
now adds eight verified 2026 exceptions through 2026-11-02 so the existing
source dataset through July 2026 is covered. Counts are 124 dates: 96 early
closes, 28 full closures. The Good Friday 2026 CME table explicitly closes
Equities at 08:15 CT. Future 2026 holiday outcomes are not guessed.

Every row now carries identical `coverage_start`/`coverage_end` fields. This
keeps coverage explicit inside the single CSV that AQ and C# will read; no
additional service or metadata-file dependency is introduced. Updating the
end date requires reviewing the entire added interval, including regular dates.
The validator checks consistent bounds and optional requested-bound assertions.
Actual updated validation is `artifacts/cme-calendar-review-20261102/validation-with-2026.json`.
The prior validation and calendar commit are preserved. No simulation changed.

## 2026-11-02 — Causal AQ session calendar in the existing report workflow

The Python VWAP strategy now loads the shared CSV once, derives the current
Chicago session-ending date from each current bar, and uses the earlier of the
configured EOD time and scheduled close minus five minutes. The production
last-observed-session-bar inference was removed. Both entry submission and
pending-entry fills enforce the cutoff; a pending entry cannot cross sessions.
The executor validates a held position before applying old orders so an evening
bracket/market fill cannot disguise missing pre-close liquidation data. Unknown
coverage and unavailable liquidation prices return 422 without a completed run.
The calendar SHA and coverage are saved in reports and included in calculation
identity. The wheel bundles the same CSV bytes. Earlier reports stay immutable.

Actual product journey: the normal backtest API created new IS report
`030f3b33449b43b2b31d1b140be29267` from the existing NQ source for 2021–2024,
using the prior qualified request and explicitly disabling result reuse. The
independent, previously reconciled reference was fixed before execution:
486 trades, 28,155.00 gross, 1,934.28 commissions, 26,220.72 net. Every exported
trade byte matches that reference. This verifies AQ's calendar replacement on
the complete source; it is not a newly measured C# MultiCharts comparison.

In the existing UI the report's settings show **Calendar-based session exits ·
no bar lookahead**, coverage and checksum. Open its Configure prop dialog,
choose the existing default Apex companion, click Check source, then Run. Source
checking passes and Run reuses the completed companion
`b3df542ae0cf4dcb9cf5aa2a984cb36a`; the durable prop report reopens after reload.
Downloads, mobile layout, and the older inferred-session report were inspected.
Seven original report files were hash-checked unchanged. No OOS was executed.

Inspectable actual outputs are in `artifacts/calendar-causal-real-20261102/`:
`independent-expected.json`, `new-report.json`, exported trades/equity/risk,
`apex-source-check.json`, `apex-report.json`, screenshots, preserved-file hashes,
`verification.json` and `wheel-verification.json`. To inspect without creating
another report, restart the usual app with the updated code and open
`/#backtests/report/030f3b33449b43b2b31d1b140be29267`. To reproduce execution:

```sh
.venv/bin/python tests/review_calendar_real.py \
  --output artifacts/calendar-causal-real-NEW
```

This deliberately creates a new report in the existing library; it requires the
existing dataset and earlier reference artifacts. It owns a temporary server
and stops it automatically. The isolated synthetic review is independently
reproducible with `tests/review_vwap_session_flatten.py --output` as documented
in the strategy guide. Actual synthetic outputs are in
`artifacts/calendar-causal-synthetic-20261102/`: all three scheduled closes
(16:00, 12:00, 12:15) produce 15:55/11:55/12:10 order cutoffs and independently
expected net 88 CU. These sparse fixtures fill on the next observed Open at
the session close; they are not tick-level demonstrations of liquidation time.

Boundary checks cover missing cutoff bars without backdating, pending entries
at cutoff/across sessions, full closures, DST, truncation, malformed files,
coverage rejection and missing pre-close prices. The combined calendar/updated
session suite passed 54 cases, and the report browser case passed. The earlier
95-case focused strategy/execution/calendar run also passed. The full-suite
gate is recorded separately after completion. The wheel built successfully;
an isolated extracted install loaded a byte-identical bundled CSV. Temporary
review servers stopped and no persistent server or VM was started.

## 2026-11-02 — Maintained C# MultiCharts strategy using the shared calendar

Added the active `multicharts/ORB_VWAP_CONT__NQ_1M_PIVOT_V01.cs` alongside the
AQ Python implementation. The attached original is retained byte-identically
under `multicharts/reference/` (SHA recorded in its README). The new string Input
`SessionCalendarFile` points at the Windows copy of the exact shared CSV.
StartCalc validates and snapshots it, logging coverage and SHA. CalcBar resolves
the current Chicago session, blocks late/closed-session submissions and submits
the original next-bar market exit at the shared scheduled cutoff. Original
signal, ADX, sizing and bracket mechanics remain intact.

The usable installation/reconciliation journey is in `multicharts/README.md`:
copy/checksum CSV, load the whole C# file in the existing MC signal, compile
with the installed SDK, match Chicago timezone/history/Inputs/costs, recalculate
the existing 2021–2024 IS, inspect the two shortened exits and two blocked-entry
dates, then export/reconcile trades against AQ's saved 486-trade report. This
is an extension of the same backtest source/report qualification, not a new
prop page, calculation service or report store. The AQ report → configure →
check → run → durable report evidence is retained in the previous increment.

Actual compiled calendar evidence is in
`artifacts/calendar-csharp-review-20261102/`: build log (zero errors/warnings),
all plans and verification JSON. The check compiles the real helper embedded
in the active C# file, using C# 5 syntax and .NET 8 outside MC. All 7,918
date/cutoff combinations match Python across the complete declared coverage;
31,672 cutoff-boundary assertions pass. Nine malformed/uncovered cases reject
and quoted/BOM/newline CSV parsing passes. Reproduce with
`tests/review_multicharts_calendar.py --output artifacts/calendar-csharp-review-NEW`
and a .NET 8 SDK (`--dotnet` accepts its path).

This evidence does not compile the full signal against the user's MC SDK,
measure a fresh MC backtest or qualify live automation. The user's VM and
processes were untouched. In bar-close MC execution a pending order can fill
before CalcBar observes a gap; the signal rejects observed late fills and
positions crossing close, including late brackets, but cannot undo a fill.
The README distinguishes these rejection guards from AQ's pre-fill cancellation
and from broker-side live protection. No fabricated MC results are supplied.
Calendar/strategy updates must preserve the checks and obtain fresh actual MC
exports before asserting platform parity. Coverage beyond 2026-11-02 remains
unknown until manually reviewed and extended; no future outcomes are inferred.

### Final validation and calendar snapshot metadata

AQ's per-instance report metadata now comes from the same immutable calendar
snapshot used for its decisions, avoiding a second read that could describe a
concurrent file replacement. A boundary check replaces the CSV immediately
after the initial read and verifies the report still identifies the original
trading snapshot. The independently checked real report/trades above remain
preserved; this follow-up changes snapshot binding, not the cutoff arithmetic.

The final relevant gate passed **163 tests** across VWAP, next-bar execution,
calendar/session boundaries, strategy registration, prepared/replay cache,
completed-result/calculation reuse and backtest API behavior. The final report
browser check also passed (one case, ten unrelated cases deselected). Logs are
`artifacts/calendar-causal-real-20261102/focused-pytest.txt` and
`browser-pytest.txt`. The compiled C# calendar, wheel and actual product
demonstrations are recorded above; JavaScript syntax and Git whitespace passed.

A broader repository run was deliberately interrupted to apply the snapshot
fix and finish the relevant gate. It recorded **362 passed**, no failures,
in 415.79 seconds before interruption. Its partial output is retained in
`full-pytest.txt`. The previous whole-suite run took about 56 minutes and
included unrelated account simulations. **No complete current whole-suite pass
is claimed.** There is also no claim of a measured fresh MC platform result.

The four original discrepancies were additionally inspected in the saved AQ
trade export, independently of aggregate totals. No trades occur on
2021-01-18 or 2024-09-02. On 2021-09-06 and 2024-01-15 the exit deadline is
11:55 CT, the next-Open containing label is 11:56, and gross P&L is respectively
10.00 and 80.00. Those exact observations are saved as
`artifacts/calendar-causal-real-20261102/four-discrepancy-observations.json`.
All owned review/test servers stopped; the user's existing server/VM and
previous report files remain untouched. Source commits exclude generated data
and evidence; no remote push was performed.

## 2026-11-02 — Editable close buffer and automatic NQ calendar selection

The existing Backtests form now exposes **Close buffer minutes**, default 5,
as one normal strategy parameter. Set start=end for a fixed run; it also works
as an ordinary optimization axis. Positive whole minutes 1–1440 are supported.
`EOD Flat Time` still caps the scheduled cutoff. Calendar selection follows the
saved instrument symbol: NQ and explicit supported NQ aliases select
`cme_nq_closures.csv`; the resolved calendar appears before Run. Missing symbols,
other instruments and filenames containing NQ do not receive this calendar.
Unknown instruments block calendar-enabled API/UI/CLI runs and mixed EOD-on/off
optimization grids before publication/queueing. EOD-off runs remain available.
There is no calendar picker or additional report store/page/API.

Implementation artifacts are the existing Python strategy, session helper,
registry, report/API/CLI and form integration. Reports retain the buffer,
original instrument symbol, selected calendar ID/file, checksum and coverage.
Calculation identity includes the new parameter; optimization workers receive
the actual dataset symbol and retain the normal prepared-feature path. Earlier
reports, calendars, evidence and source datasets remain unchanged.

User journey: select the saved **ofb_bars_NQ** dataset and **Vwap pullback risk
sizing** in Backtests. Expect **Session calendar: Auto → NQ futures ·
cme_nq_closures.csv**. Review **Close buffer minutes** (start 5, end 5, step 0),
or edit both endpoints to 10. With EOD Flat Time 15:45, regular 16:00 sessions
cap at 15:45 for either buffer; noon sessions use 11:55 or 11:50 respectively.
Run the declared IS, inspect the saved settings/downloads, then follow the
existing Configure prop → Check source → Run → reopen durable report path.

Actual default-5 execution created IS report
`c841a716f8f14dbe8b73b31ec0d28b08`, using the existing 2021–2024 source and
prior qualified request with the additional explicit buffer value. Independent
expected values were fixed before execution: **486 trades, 28,155.00 gross,
1,934.28 commissions and 26,220.72 net**. Exported trades are byte-identical to
the prior independent next-Open reference. The report displays automatic NQ
selection and buffer 5. Check source passed; Run reopened/reused the completed
Apex companion `1206136351064729a8fa6be461643ac9`; the durable prop report,
downloads, reload and mobile checks passed without browser errors. No OOS ran.

Actual outputs are in `artifacts/calendar-options-real-20261102/`, including
the request, expected values, report/trade/equity/risk exports, screenshots,
source check, Apex report and verification. Seven earlier inferred-model report
files and seven prior causal-calendar report files were hash-checked unchanged.
Open `/#backtests/report/c841a716f8f14dbe8b73b31ec0d28b08` in the usual updated
app to inspect the saved result. To reproduce a fresh actual IS execution:

```sh
.venv/bin/python tests/review_calendar_real.py \
  --output artifacts/calendar-options-real-NEW
```

The edited-buffer UI demonstration uses the normal upload/backtest/report
workflow in an isolated library with **SYNTHETIC** fixtures. Actual evidence is
`artifacts/calendar-options-synthetic-20261102/`. The three default-buffer
normal/noon/12:15 cases retain net **88 CU**. The fourth case changes the form
to buffer 10: cutoff **11:50 CT**, next-Open fill in the **11:51** labelled bar,
exit reference117 / adverse fill116.75. The independently fixed arithmetic is
`(116.75 - 115.25) * 20 - 2 commissions = 28 CU`. Its report/downloads/reload
match, with source bytes preserved. Reproduce:

```sh
.venv/bin/python tests/review_vwap_session_flatten.py \
  --output artifacts/calendar-options-synthetic-NEW
```

Automated validation initially completed with **237 passing cases and three
browser failures**, caused by old 32-parameter assertions and generic fixtures
with no instrument that implicitly enabled the NQ calendar. Those fixtures now
expect 33 parameters and explicitly disable EOD for unrelated controls checks;
dedicated NQ calendar tests keep it enabled. The final entire affected browser
set passed **42 cases** (Backtests, optimization and column preferences).
Logs are `initial-regression-pytest.txt` and `final-browser-pytest.txt` under
the real-evidence directory. Calendar/source/CLI checks were also rerun after
adding early CLI validation; **81 cases passed**, with their final log in
`final-calendar-cli-pytest.txt`.
No new whole-repository pass is claimed. JavaScript syntax and Git whitespace
checks passed. Owned temporary servers stopped; no persistent server, VM action,
remote push, trade submission or modification to earlier reports was performed.

### Matching MC Inputs and compiled calendar qualification

The maintained C# signal now exposes **CloseBufferMinutes**, default 5, using
the same 1–1440 validation and EOD-time cap as AQ. It selects the NQ CSV from
`Bars.Info.Name` instead of applying that calendar to every chart. The new
**SessionCalendarDirectory** Input (default `C:\AlphaQuest\calendars`) replaces
the earlier full-file-path Input; it locates the automatically selected
`cme_nq_closures.csv`, rather than selecting a different product's calendar.
The Output log retains symbol, file, buffer, coverage and checksum. Unknown
chart symbols reject when EOD flattening is enabled. The original attached
source and previous Git versions are preserved.

The reproducible installation/user journey remains `multicharts/README.md`:
copy identical CSV bytes, load the full active signal in MC, match explicit NQ
chart symbol/timezone/history/Inputs, set the containing directory and buffer,
then recalculate the existing IS and inspect/export the four discrepancy dates.
Default buffer 5 preserves noon cutoff11:55; buffer10 changes it to11:50.
Match AQ's buffer and EOD time when comparing those platform exports.

Actual standalone C# evidence is
`artifacts/calendar-options-csharp-20261102/`: the real embedded helper compiled
with C# 5 syntax, zero errors/warnings; **31,672 date/EOD/buffer plans** and
**126,688 boundary checks** match Python, including buffers1/5/10/1440.
**12** malformed/unknown-coverage/invalid-buffer probes reject, **16** symbol
selection probes agree, and BOM/quoted-comma/escaped-quote/newline parsing passes.
Reproduce with `tests/review_multicharts_calendar.py --output` as documented.
This compiles the helper, not the full signal against MC's installed SDK.
No fresh MC platform result or live protection is claimed. The existing
bar-close gap guards still reject observed invalid fills after execution;
they do not cancel or undo broker fills. The user's Windows VM was untouched.

## Lucid evaluation: AQ 75.1% versus Bridge 37.8% — 2026-11-02

This records the v2 comparison before joint sizing. The following joint-sizing
section specifies the current implementation and its new durable report.

The discrepancy is reproducible and explained. The reports are not using the
same evaluation policy, despite similar settings forms. AQ analysis
`9994b7072e2e46e19f6c6c28540041ce`, from backtest
`ca38522dd0794f6f9f49e4b7eb8b67d9`, is compared with the user's saved Bridge
export `/Users/yx/Downloads/20261102_173028`. No Bridge executable or DLL was
invoked. That export is a qualification oracle only; all new calculations below
were generated locally. Production rules, UI, stored backtests and reports are
unchanged by this investigation.

### Confirmed causes

1. **Different evaluation objective and size.** AQ chooses the highest training
   pass count (`max(evaluation_sweep, key=passed)`), selecting **4 MNQ**, with
   612/3,000 training passes. Bridge's captured settings specify
   `EVAL_PICK = 'fastest to funded'`: minimize training acquisition time including
   retries, with sizes within one standard error tied and higher pass rate
   preferred. Bridge selects **20 MNQ**. AQ's evaluation search allows 1–40;
   Bridge records a 25-MNQ evaluation search cap. The shared form choice
   **most net per year per slot** describes funded sizing; it does not make
   these two evaluation objectives equivalent.
2. **40% versus 52% evaluation consistency.** AQ's dated local contract uses
   0.40. The supplied Bridge `EVAL_ACCOUNT` explicitly uses **0.52**, also
   printed in its run log. This compares captured model behavior; it does not
   certify either threshold as today's provider rule. At 20 MNQ this difference
   materially changes both pass probability and the time required to pass.
3. **Different cost treatment.** Bridge retains costs already in the workbook.
   AQ replaces source NQ commission with the configured MNQ commission, once:
   $3.98 source round turn / 10 = **$0.398 per MNQ**, versus **$1.00 per MNQ**
   in AQ's Lucid default. The source's $25,400.72 net becomes $22,475.00 per
   NQ-equivalent when repriced for MNQ, a $2,925.72 difference over 486 trades.
   This is a cost replacement, not a duplicate charge. AQ **source costs** mode
   preserves the workbook cost convention for qualification.
4. **One weekday at the split boundary.** Both use the same 1,038 weekdays.
   AQ floors 70% into **726 training / 312 validation** days, with validation
   starting **2023-10-18**. Bridge has **727 / 311**, starting **2023-10-19**,
   consistent with flooring the 30% validation count instead. An explicit
   `OUT_OF_SAMPLE_FROM='2023-10-19'` aligns the sample.
5. **One funded-start day in the displayed time.** AQ's value is the total
   evaluation-chain length; its Lucid activation increment is zero. Bridge's
   report explicitly includes the next funded-start weekday. After aligning
   all calculation inputs, AQ gives **32.67555** evaluation weekdays; adding
   Bridge's counted start day gives exactly **33.67555**. This is a metric
   convention, not a $0 activation fee becoming a paid activation.

Both source inputs reconcile: the workbook contains the same **486 trades**,
IDs, entry UTC timestamps, directions, quantities and net costs. The adapter
checks every trade, not only aggregate P&L. Its MAE/MFE columns are accepted as
the companion export's supplied excursions; the original AQ report uses held
OHLC risk bounds. No measured excursions were fabricated. Preserving the exact
workbook floating representation changes the aligned chain mean by just
**0.00005 day**; this accounts for the final full-precision difference below.

### Controlled local calculations

Each row changes the previous row, in order. All rows use 20,000 single
evaluations (seed 43), 20,000 repeated-funding chains (seed 44), and five-day
blocks. These are deterministic conditional model experiments, not future
outcomes. The day column excludes the funded-start weekday until the last row.

| Local scenario | MNQ | Pass rate | Cost to funded | Mean evaluation-chain weekdays |
| --- | ---: | ---: | ---: | ---: |
| Saved AQ inputs | 4 | 75.145% | $107.126223 | 88.69665 |
| Change size only | 20 | 31.170% | $258.261149 | 49.64560 |
| Also use 52% consistency | 20 | 35.755% | $225.143337 | 33.85390 |
| Also retain source costs | 20 | 36.975% | $217.714672 | 33.34915 |
| Also align validation start | 20 | 37.840% | $212.737844 | 32.67550 |
| Also retain exact workbook floats | 20 | 37.840% | $212.737844 | 32.67555 |
| Add Bridge's counted funded-start day | 20 | 37.840% | $212.737844 | **33.67555** |

The final pass count is **7,568 / 20,000**. Independent acquisition arithmetic:
**$80.50 / (7,568 / 20,000) = $212.73784355179703**. The aligned chain median is
25 weekdays, or **26** including Bridge's start day; median successful attempt
is **12** weekdays. These also match the supplied Bridge export. The original
AQ cost is independently **$80.50 / (15,029 / 20,000) = $107.12622263623662**.

**Qualification status:** these evaluation pass/cost/time metrics match the
supplied reference exactly when conditions align. This does not establish
funded-account, historical-net, arbitrary-input or current provider-rule parity.
For example, the saved Bridge funded contract removes its DLL above +$2,100,
whereas AQ's current dated contract discloses a fixed-DLL assumption. That
funded-phase difference is outside the three evaluation metrics investigated.
Changing AQ's production objective to fastest funding, or introducing another
consistency profile, would be a separate behavior change requiring its own
normal-product configuration, calculation and durable-report increment.

### Inspect and reproduce in the existing product

1. Open `http://localhost:8000/#backtests/report/ca38522dd0794f6f9f49e4b7eb8b67d9`.
   Its source has 486 trades and $25,400.72 net. Select **Configure prop
   analysis**, then **LucidFlex 50K**. Leave the companion path blank to retain
   the saved report's native risk input.
2. Set six slots and **Check source**: expect rejection (**SLOTS must be an
   integer from 1 to 5**) and a disabled run button. Restore five slots and
   check again: expect 486 matched trades, 486 held-OHLC inputs, $0.50 per side
   MNQ commission and one recorded cost replacement.
3. With the original defaults/source, **Run analysis** reopens the existing
   saved report `9994b7072e2e46e19f6c6c28540041ce`. The delivered browser review
   verifies the exact request key before submitting and asserts that this same
   ID is reused. No new backtest or report is created.
4. In **Evaluation**, expect 4 MNQ, 75.1%, 88.7 trading days and the saved
   full-precision $107.1262 acquisition cost (the headline currency display
   rounds to whole dollars). Expand **Evaluation sizes tried on training
   days** and **Training calibration used for selection** to see why 4 won.
   Training's 20.4% / $394.61 / 429.8248 days use earlier days and must not be
   mistaken for the displayed holdout estimates.
5. **Source & model → Download all results (ZIP)** preserves the numerical
   output, source identity, rules and sizing CSVs. Reload reads that saved
   analysis. The Bridge-aligned 52%/20-MNQ cases are qualification experiments
   in the review script, not an exposed production configuration or a second
   product report store. Open the supplied Bridge `report.html` and compare its
   20-MNQ Evaluation row and captured `settings_20261102_1730.txt`.

Evidence: `artifacts/lucid-metric-discrepancy-20261102/` contains
`comparison.json`, original AQ/Bridge JSON snapshots, captured Bridge settings,
the reconciled workbook source identity, and compressed `chains-0.npz` /
`chains-5.npz` with actual and independently regenerated per-chain days,
attempts and longest attempt. All **40,000** independent chains match exactly.
`preservation-before.json` and `preservation-after.json` verify **44** original
source/report/reference files byte-for-byte. `portal/` contains three actual
workflow screenshots, rejected/accepted source checks, the original report/ZIP
and `verification.json` confirming reuse, reload and no backtest POST.

Reproduce with a fresh output directory (existing evidence is never overwritten):

```bash
.venv/bin/python tests/review_lucid_metric_discrepancy.py \
  --report data/prop_analyses/9994b7072e2e46e19f6c6c28540041ce/report.json \
  --bridge /Users/yx/Downloads/20261102_173028 \
  --workbook '/Users/yx/Downloads/Backtesting Strategy Performance Report _ NQ TIP - 1 Minute ORB_VWAP_CONT__NQ_1M_PIVOT_V01.xlsx' \
  --output artifacts/lucid-metric-discrepancy-RECHECK
.venv/bin/python artifacts/lucid-metric-discrepancy-20261102/review_portal.py \
  --output artifacts/lucid-metric-discrepancy-portal-RECHECK
.venv/bin/python -m pytest tests/test_lucid_prop.py \
  tests/test_lucid_funding_continuation.py -q
```

Validation: **31 automated checks passed**. The review additionally asserts the
exact supplied metrics and independent per-chain results. Independent boundary
arithmetic checks that $1,000/MNQ/session passes the $3,000 target on session 3,
that a two-session guard censors rather than fails, and that touching the
−$2,000 floor breaches even when the trade later wins. No censored evaluation
was omitted. Whitespace checks passed. The existing user server was used; no
server or Windows process was started, stopped or changed. The review browser
was closed.

## Joint evaluation/funded sizing in the product — 2026-11-02

New Apex v5 and LucidFlex v3 reports select the evaluation/funded pair with the
highest **training long-run annualized net per slot**. Evaluation pass rate is
an input to acquisition cost, not a separate first-stage selection objective.
All rules, source/cost adaptation, permitted sizes, payout mechanics and the
chronological internal split remain as configured. No Bridge executable, DLL
or generated results enter production calculations.

### Actual existing-source journey and observations

The user's existing 486-trade backtest
`ca38522dd0794f6f9f49e4b7eb8b67d9` and earlier Lucid report
`9994b7072e2e46e19f6c6c28540041ce` were used without executing a strategy
backtest. The ordinary report **Configure new analysis → Check source → Run
analysis** flow published **`c04a55c2c5de476da4e328eb29c52cbc`** into the existing
AnalysisStore. Every resolved setting and the source snapshot equal the earlier
report. The earlier report retains its original 75.145% evaluation result and
acquisition metrics, with the normal earlier-model notice.

Open the new durable result on the existing portal:

```text
http://localhost:8000/#backtests/prop/job/c04a55c2c5de476da4e328eb29c52cbc
```

Expected observations:

1. **Sizing → Evaluation and funded sizes chosen together** selects **12 MNQ
   evaluation / 20 MNQ funded**, comparing **1,600** pairs. The training sample
   remains 2021-01-05–2023-10-17; validation starts 2023-10-18. No comparison
   changes Lucid's saved 40% consistency or commission treatment.
2. The selected evaluation's refined training pass count is **3,883 / 20,000**.
   Its expected acquisition cost is independently
   `80.50 / (3883 / 20000) = 414.6278650527943`. All **20,000** seed-45 funding
   chains resolve, with mean **116.8156** weekdays. A separate scalar ledger
   regenerates every chain's days, attempts and longest attempt exactly.
3. Training funded receipts average **$762.7549078125**, with average lifetime
   **21.86875** weekdays. Independent arithmetic gives
   `261 * (762.7549078125 - 414.6278650527943) / (21.86875 + 116.8156)`
   = **$655.1651874222521 annualized net per slot**. Its conditional Monte Carlo
   standard error is **$25.722372652924186**. These simulation errors do not
   measure uncertainty about future strategy performance or provider rules.
4. The later holdout **validates the frozen 12/20 pair**. Evaluation passes
   **47.92%**, acquisition cost is **$167.98831385642737**, and acquisition time
   is **37.09685** weekdays. Holdout annualized net is **$6,411.724664697769 per
   slot**. These holdout values never rescore the pair or replace the training
   acquisition inputs used for historical replay.
5. **Historical replay** shows **$58,996 payouts − $16,584 acquisition costs =
   $42,412 net**, across five shared-trade slots over 1,038 observed weekdays.
   This full-history research replay includes training days, starts acquired
   funded accounts, and uses frozen expected acquisition fees/rounded-up mean
   delays. It is distinct from both annualized estimates and from first-year
   cash starting unfunded.
6. Choose another evaluation size in Sizing to inspect its funded-size rows.
   Download **all evaluation/funded pairs (CSV)** and **joint sizing and
   provenance (JSON)** there, or use **Source & model** / the existing ZIP.
   Reload reopens the saved result. Reconfiguring unchanged inputs reuses this
   new current-model analysis; it does not rewrite either report or a saved
   optimization trial's automatic analysis reference.

The two-stage screening uses 3,000 paths per size and 20,000 funding chains
per eligible evaluation size. On this source, **14 evaluation and 30 funded
contenders** were refined at 20,000 training paths, seed 46. Full screening and
final matrices, refinements, seeds, counts, source identity and tie-break are
saved. Every one of the final **1,600** scores was independently recomputed with
Decimal arithmetic; the maximum and documented tie ordering match the selected
pair. No funded profile in this actual-source matrix remained censored.

Evidence is in `artifacts/joint-sizing-20261102/actual-portal/`: source check,
old/new reports, submission/verification JSON, complete pair CSV/JSON, training
economics, result ZIP, independent-chain evidence, and five screenshots covering
the existing backtest, source check, pair selection, evaluation and replay.

Reproduce from the repository root with a fresh evidence directory:

```bash
.venv/bin/python tests/review_joint_prop_sizing.py \
  --old-id 9994b7072e2e46e19f6c6c28540041ce \
  --output artifacts/joint-sizing-actual-RECHECK
```

This review requires an idle backtest/prop catalogue, starts its own temporary
local server on a free port, uses the existing normal catalogue and API, closes
Chromium and stops its server. It requests only a prop analysis, reusing the
existing current result when source/settings/implementation match. The user's
existing server was not manually restarted or stopped; its reload-enabled
configuration now exposes both new model versions.

### Independent expected values and rejection boundaries

The synthetic product demonstration uses the normal labeled dataset/backtest
workflow. Every weekday's source trade makes **$3,000 per NQ**, without costs or
adverse movement; an MNQ therefore makes **$300**. Independent expectations:

- Lucid evaluation **4 MNQ** makes $1,200/day: three days reach $3,600 and the
  largest-day share is 1/3, satisfying 40%. Larger sizes cannot pass in fewer
  than three days under that consistency requirement, so the exact tie-break
  selects four. Funded **3 MNQ** makes $900/day, reaches all five full payout
  caps in 25 sessions and receives **$9,000** after the split. Training score:
  `261 * (9000 - 80.50) / (25 + 3) = 83142.48214285714`.
- Across the 60-day synthetic history, two full Lucid accounts pay **$90,000**
  across five slots. A third account is purchased late in the period, before
  any payout. Three purchases cost `3 * 5 * 80.50 = 1207.50`, rounded to **$1,208**
  by the existing quarterly convention; net is **$88,792**. This checks renewal
  timing and charges for an unpaid late-period purchase, not only payout totals.
- Apex selects **10 MNQ evaluation / 3 MNQ funded**: one $3,000 evaluation day
  plus one activation weekday, then six funded caps totaling $13,000 in 30 days.
  Its training annualized score is **$104,579.4375**. Over 60 observed days,
  20 slots receive `(13000 + 10000) * 20 = 460000`, pay `2 * 20 * 178 = 7120`,
  and net **$452,880**. Larger evaluation sizes tie on timing and the smaller
  exact-tied exposure wins.
- A separate Decimal fixture deliberately gives the highest pass probability,
  fastest funding, largest funded payout and best joint score to different
  candidates. The joint winner is independently **$5,481/year per slot**.
  Negative qualified scores remain negative rather than acquiring a positive
  fallback. Holdout changes cannot alter the saved training matrix or choice.
- A $149 maximum possible day at one MNQ cannot meet Lucid's $150 qualifying
  threshold. The analytical profile reports **zero paths actually simulated**,
  zero possible receipts and unknown lifetime; it does not invent an account
  closure. At exactly $150, this exclusion does not apply and all requested
  paths are simulated. Censored lifetime upper bounds can only be excluded when
  they cannot beat the qualified winner. Otherwise joint selection is unavailable.
- The earlier $1/day / 3,000-day evaluation example still resolves its full
  funding chains. Its funded account cannot produce a $150 qualifying day and
  has no known terminal lifetime; the new model correctly withholds a complete
  joint lifetime score and historical replay. The earlier v2 result and evidence
  remain unchanged. The ordinary Sizing/Evaluation views expose the bound and
  diagnostic evaluation result; no fabricated future outcome is substituted.
- The actual form rejects **six Lucid slots** and disables Run. Five slots pass
  source checking. Zero training evaluation passes and unresolved acquisition
  paths remain explicit unavailable outcomes; profitable holdout cannot rescue
  a failed training selection.

The synthetic browser evidence is under
`artifacts/joint-sizing-20261102/browser-final/test_joint_sizing_actual_backt0/`:
three screenshots, accepted source check, report/ZIP, 1,600 independently checked
CSV scores and verification JSON. Additional browser directories retain the
slow-evaluation rejection and saved-batch refresh/download/reopening journeys.
The boundary fixtures/oracles remain in tests; the UI shows normal source checks,
account results and selection explanations.

Reproduce the synthetic journey and independent checks with temporary fixtures:

```bash
.venv/bin/python -m pytest tests/test_joint_prop_sizing.py \
  tests/test_prop_training_economics.py tests/test_lucid_prop.py \
  tests/test_lucid_funding_continuation.py -q
.venv/bin/python -m pytest tests/test_joint_prop_sizing_browser.py \
  tests/test_lucid_prop_browser.py tests/test_prop_training_economics_browser.py \
  tests/test_automatic_prop_browser.py tests/test_lucid_funding_continuation_browser.py \
  tests/test_lucid_batch_refresh_browser.py \
  -q --basetemp artifacts/joint-sizing-browser-RECHECK
```

The browser fixtures own temporary servers and stop them after each test. The
actual-source review's `independent-verification.json` confirms its temporary
server stopped as well. No persistent server or Windows process was started.
The before/after inventory verifies **4,405** original report/source JSON, CSV
and ZIP files byte-identical. Original datasets, backtests, prior evidence,
optimization snapshots and saved Apex/Lucid reports are retained.

The supplied Bridge evaluation reference was also requalified in
`artifacts/joint-sizing-20261102/reference-recheck/`: when its fixed 20-MNQ,
52%, source-cost, validation-date and start-day conventions are aligned, local
calculations still match **37.84% / $212.73784355179703 / 33.67555 weekdays**
exactly, with **40,000** independently matching chains across original AQ and
aligned-reference scenarios. This qualifies those evaluation metrics only.
The new joint optimizer deliberately uses AQ's saved rules and joint objective;
no new full funded-account or provider parity is claimed.

Completed validation: the **75-test backend/integration gate**, **7-test joint
arithmetic/boundary suite** and **9-test kernel/parallel gate** passed, covering
**85 distinct targeted backend cases** after accounting for overlap. **Nine
browser cases** passed, including the final saved-batch refresh rerun. The
actual-source ledger independently matched **20,000** chains; the retained
AQ/Bridge qualification matched another **40,000**. Both actual and synthetic
1,600-pair matrices passed independent arithmetic checks. JavaScript syntax,
whitespace, current-report implementation/kernel compatibility, every published
artifact hash and all **4,405** preservation checks passed. Summaries are saved
in `artifacts/joint-sizing-20261102/validation.json`. These are targeted gates,
not a claim that every repository test was run. All owned review/test servers
and browser instances were closed; the existing user portal remains available.

## Apex joint-sizing unavailable diagnostics — 2026-11-03

Read-only inspection of the latest completed batch
`d69045ab437942618ec2afb54728c33c` finds **71 available / 57 unavailable** Apex
results across 128 trials. Every unavailable result is blocked by an evaluation
acquisition calibration, **not by a censored funded lifetime**. Blocking sizes
are 2–5 MNQ, with only 1–4 passes in 3,000 screening evaluations. At least one
of the requested 20,000 repeated-funding chains failed to pass within the
10,000-attempt computational guard. This is not the provider's 21-day deadline
for one Apex evaluation; each failed evaluation can be followed by another.

The new joint search's blanket veto (`joint_sizing.rank`) marks the whole search
blocked whenever any evaluation size has positive screening passes but unavailable
funding time. It does not first bound whether that candidate could beat a
complete pair. This is overly conservative for positive contenders: **44** of
the affected trials have positive complete candidate scores. The other **13**
have nonpositive best complete scores and require separate treatment; an
unresolved negative-return policy could still approach zero annualized loss
over a sufficiently long cycle, so the positive-winner argument cannot simply
be reused for those cases.

Concrete example: trial **4**, saved Apex analysis
`2f616c80f6d74bd4b01423af27eadcad`. Its 3-MNQ evaluation has **2 / 3,000**
screening passes. Its estimated acquisition cost is
`49 / (2 / 3000) + 129 = $73,629`, while the Apex model's entire six-payout ladder
totals at most **$13,000**. On those estimates this candidate cannot produce a
positive cycle net, regardless of acquisition time. The same report already has
a complete **40-MNQ evaluation / 8-MNQ funded** candidate with training annualized
net **$2,026.1412739755713 per slot**. Nevertheless the global veto suppresses the
selection and acquisition-dependent historical replay. This candidate score is
a saved training estimate, not an independently qualified replacement report or
a future outcome.

Inspect through the ordinary batch result link → **Sizing → joint sizing and
provenance JSON**. In `evaluation_profiles`, the affected sizes have reason
`No pass within the 10,000-attempt funding-time bound`; `funded_profiles` have no
incomplete lifetime. `pairs` still contains the complete candidate estimates,
but the global `selected` is null. The user-visible aggregate message does not
currently distinguish the specific blocker.

The appropriate repair is candidate-specific acquisition bounds/dominance
checks, with adequate probability refinement, and an explicit blocker reason.
Only candidates that cannot change the ranking may be excluded; genuinely
ambiguous cases must remain unavailable. No production code, report, batch,
source backtest or dataset was changed in this diagnostic turn; no calculations,
strategy backtests or servers were started. Saved inspection evidence is
`artifacts/apex-joint-unavailable-audit-20261103/diagnosis.json`, with original
affected-report hashes in `report-sha256.json`.

## Fix the blanket acquisition-calibration veto — 2026-11-03

Apex v6 / LucidFlex v4 retain the same account rules and numerical kernels but
replace the blanket unresolved-acquisition veto with candidate-specific economic
bounds. No external calculator is invoked or used to generate a production
result. This increment creates new normal prop reports; all original reports,
source backtests and optimization trial snapshots remain unchanged.

### Existing trial 4 now produces a durable result

From the latest completed 128-trial batch
`d69045ab437942618ec2afb54728c33c`, open trial 4's earlier Apex report
`2f616c80f6d74bd4b01423af27eadcad`. **Configure new analysis → Check source → Run
analysis** publishes new report **`74e35dc0382343fa85a56645d561f6d3`**. The
source remains backtest `decc3d06356d4ce18828b4ea63e870d2`, with **488** trades,
and every resolved setting/source snapshot matches the earlier report. No
strategy backtest POST or bar execution occurs.

```text
http://localhost:8000/#backtests/prop/job/74e35dc0382343fa85a56645d561f6d3
```

Expected observations in the existing product:

1. **Sizing** selects **40 MNQ evaluation / 8 MNQ funded**. Training annualized
   net is **$2,026.1412739755713 per slot**, matching the already complete
   candidate from the earlier withheld report. This is a conditional training
   estimate, not a new future-outcome or full provider-parity claim.
2. **Uncompetitive evaluation sizes excluded** lists **3 MNQ**. It originally
   passed **2 / 3,000** screening evaluations. Its independent refined training
   sample passes **7 / 20,000**. Across 40 evaluation sizes, the upper probability
   limit solves `Pr[Binomial(20000, p) <= 7] = 0.05 / 40` and equals
   **0.0009642092185256703**. This is a conditional Monte Carlo confidence bound;
   it does not assert a bound on future market behavior.
3. Independent cost arithmetic gives
   `49 / 0.0009642092185256703 + 129 = 50947.84621983156` dollars as the optimistic
   acquisition-cost floor. Even the entire **$13,000** funded payout ladder
   cannot produce a positive cycle net at that cost. Its annualized upper bound
   is therefore **$0**, below the complete pair's positive score.
4. Inspect evaluation size **3** in the pair filter: all **40** funded pairings
   are **excluded**, with upper bound zero and missing estimated acquisition
   days/annualized score. The size's calibration still says unavailable and
   retains the 10,000-attempt failure reason. The fix excludes that candidate;
   it does not pretend to have calibrated its funding time.
5. **Historical replay** is available: **$270,000 payouts − $93,362 acquisition
   costs = $176,638 net** across the configured **20** shared-trade slots over
   1,038 observed weekdays. The trace contains 15 starts per slot, **300** funded
   starts in aggregate. Fees are rounded by the existing calendar-quarter
   convention; this is not a flat round of the full-period fee sum.
6. The selected evaluation's training calibration remains **$311.22387504648566**
   acquisition cost and **24.47735** replacement weekdays. Funded training
   receipts average **$856.075**, with **45.70835** lifetime weekdays. Independently:
   `261 * (856.075 - 311.22387504648566) / (45.70835 + 24.47735)`
   = **$2,026.1412739755713**. These training inputs stay frozen for replay;
   holdout never chooses or rescues the pair.
7. Download **joint sizing and provenance (JSON)** / **all evaluation/funded
   pairs (CSV)** in Sizing, or the existing report ZIP in **Source & model**.
   Bounds, actual counts, exclusions and original failure reasons are saved in
   those existing AnalysisStore artifacts. Reload/reconfigure unchanged current
   inputs reuses the new report without a strategy backtest.

The batch's original rows still point to their immutable automatic analyses;
this manual prop reanalysis does not silently rewrite saved batch metrics.
The new report is also listed among the source backtest's saved analyses. Other
earlier reports can use the same Configure → Check → Run path. This increment
does not add an Apex batch-refresh action or claim that all 57 earlier N/A cells
were replaced.

### A genuinely ambiguous negative case stays unavailable

The same ordinary workflow on trial 21's earlier report
`2030900931bc4dde9dd7effaa1d919f4` publishes
**`26a5fa02a9bf4a4a8b9b7555a797c9cd`**. Its 4-MNQ acquisition profile has
**18 / 20,000** refined passes (originally 3/3,000), upper pass probability
**0.001745064903058286**, optimistic acquisition-cost floor
**$28,208.184856749922**, and annualized upper bound **$0**.

Its best complete candidate scores **−$79.68279908056084** per slot/year. Zero
is above that negative score, so the unknown acquisition duration could change the
ranking. The new report correctly retains unavailable funded selection/replay.
Its message identifies **evaluation size 4 MNQ**, and the Sizing provenance
shows the optimistic bound and best complete comparison. The unknown mean is
not filled with a fixed delay, a successful-chain-only average or a fake pass.

```text
http://localhost:8000/#backtests/prop/job/26a5fa02a9bf4a4a8b9b7555a797c9cd
```

### Independent verification, preservation and reproduction

The regression tests use trial 4's earlier saved candidate values as immutable
qualification oracles inside tests only. Separate tests verify binomial limits
against closed forms and exact Decimal probability sums, affordable unresolved
candidates that must block, zero/negative ties, censored evaluations counted as
possible passes, and zero refined passes retaining their original unresolved
status. Probability refinement cannot call/retry a funding chain or invent its
missing timing mean. Existing no-pass and funded-censoring cases remain covered.

The actual-source review independently recomputes all **2,920** rankable scores
across the two 1,600-pair matrices. Decimal binomial CDF sums verify the recorded
confidence limits and fee floors. It checks historical payout cash from each
account's payout dates and ladder, and purchase costs from starts/training fees,
rounded independently by calendar quarter. A separate scalar MT19937/first-adverse
ledger regenerates **all 20,000** training funding chains for the selected
40-MNQ evaluation, matching every day/attempt tuple and the **24.47735** mean.

Evidence: `artifacts/acquisition-bounds-20261103/actual-portal/` contains both
old/new reports, accepted source checks, CSV/JSON/ZIP downloads, normal workflow
screenshots, actual submission IDs, the independent chain arrays and verification
JSON. `preservation-before.json` / `preservation-after.json` verify **9,386**
original report/source JSON/CSV/ZIP files byte-identical. The **128** original
optimization-trial payloads also match `original-trials.json` exactly.

Reproduce actual source checking, analysis, durable results and the independent
checks from the repository root with a fresh output directory:

```bash
.venv/bin/python tests/review_acquisition_bounds.py \
  --output artifacts/acquisition-bounds-actual-RECHECK
```

The review requires idle local analysis/batch catalogues, starts a temporary
server on a free port, uses the existing normal catalogue, closes Chromium and
stops its server. It reuses current reports when inputs/implementation match.
The user's existing server is not manually restarted or stopped. No persistent
server, Windows process, dataset or strategy backtest is started/changed.

Automated gates:

```bash
.venv/bin/python -m pytest tests/test_joint_prop_sizing.py \
  tests/test_prop_training_economics.py tests/test_lucid_prop.py \
  tests/test_lucid_funding_continuation.py tests/test_lucid_batch_refresh.py -q
.venv/bin/python -m pytest tests/test_joint_prop_sizing_browser.py \
  tests/test_lucid_prop_browser.py tests/test_lucid_batch_refresh_browser.py \
  -q --basetemp artifacts/acquisition-bounds-browser-RECHECK
.venv/bin/python -m pytest tests/test_native_prop_compiled.py \
  -k 'not standard_count' tests/test_lucid_prop_workflow.py \
  tests/test_prop_commissions.py -q
```

Results: **55 backend checks**, **31 additional kernel/source/workflow checks**
and **4 browser checks** passed, alongside both actual-source review cases.
The kernel/source gate explicitly deselects its separate full standard-count
Python/compiled portal replay; these are targeted gates, not a full repository
suite claim. The dated earlier numerical qualification remains separate from
this selection repair; no new Bridge/funded-provider parity is claimed.

## Refresh all unavailable prop results in the saved batch — 3 November 2026

The existing batch page now refreshes unavailable Apex and Lucid results together.
The prior action refreshed Lucid only, so it could not replace the Apex N/A cells
after the acquisition-bound repair above. Both accounts use the normal local
AnalysisStore workers, source checks, durable reports and downloads. No strategy
backtest is rerun. Available values are skipped, identical current reports can be
reused, and repeated clicks do not submit duplicate pending analyses.

The existing append-only refresh index now distinguishes accounts. Earlier index
rows retain their Lucid meaning. Both account overlays, SQL sorting and CSV
exports share one pinned revision; revision zero still exposes the original
immutable trial values. Original reports remain directly accessible. This adds
no separate simulation page, API for demonstrations or result store.

### User journey and expected observations

1. Open the existing 128-trial batch:
   `http://localhost:8000/#backtests/batches/d69045ab437942618ec2afb54728c33c`.
   Its original snapshot has **71 / 128 Apex** and **126 / 128 Lucid** historical
   net values, leaving **57 Apex and 2 Lucid** unavailable analyses.
2. In the existing prop refresh area select **Refresh all unavailable
   prop results**. Progress identifies each account separately. Pending rows
   survive reload. A second submission while those jobs are pending queues zero
   duplicates. Current saved analyses that remain legitimately unavailable can
   be reused without another calculation.
3. Open an updated analysis from either historical-net column. Inspect its
   source checks, settings, sizing provenance and Historical replay through the
   ordinary saved report. Refresh retains the original source and settings;
   it does not change evaluation/funded constraints to manufacture a value.
   A completed analysis can still have N/A historical net when unresolved
   acquisition bounds or funded lifetimes prevent a defensible size selection.
4. Sort by either historical-net column and download the current results CSV.
   Its report IDs and metric values match the same pinned table revision.
   **Download original results CSV** retains the original 59 empty metric cells.
   Original datasets, source backtests and automatic reports remain unchanged.

The operational script uses the same API and saves a before/after manifest,
original/current CSV exports, per-trial outcomes and verification evidence:

```bash
.venv/bin/python scripts/rerun_batch_prop.py \
  --batch-id d69045ab437942618ec2afb54728c33c \
  --output artifacts/prop-na-rerun-RECHECK
```

Choose a new output directory. The script targets only currently unavailable
results; after the completed refresh, its expected outcome is reuse of current
unavailable reports rather than another strategy run or repeated size sweep.

### Independent expectations and automated checks

The labelled synthetic source goes through the ordinary dataset, backtest,
configuration, source checking and analysis routes in the isolated tests. Its
independent expected historical cash totals are **Apex $452,880** and **Lucid
$88,792**. Backend and actual Chromium checks verify both values, current and
original CSVs, independent account links, report navigation, pending reload,
duplicate submission, source-deletion protection, legacy index migration and
revision-pinned sorting. Expected fixture calculations stay in the tests.

```bash
.venv/bin/python -m pytest tests/test_batch_prop_refresh.py -q \
  --basetemp artifacts/prop-na-rerun-backend-RECHECK
.venv/bin/python -m pytest tests/test_lucid_batch_refresh.py -q \
  --basetemp artifacts/prop-na-rerun-lucid-RECHECK
.venv/bin/python -m pytest tests/test_batch_prop_refresh_browser.py \
  tests/test_lucid_batch_refresh_browser.py -q \
  --basetemp artifacts/prop-na-rerun-browser-RECHECK
```

These gates passed **7 backend checks and 2 browser checks**. Isolated browser
servers stop automatically. Evidence is under
`artifacts/prop-na-rerun-20261103/{backend,lucid-compatibility,browser}/`.
The numerical acquisition-bound model is unchanged by this refresh increment;
the preceding numerical qualification and its limitations remain applicable.

### Completed actual batch and saved evidence

The actual request processed all **59** unavailable analyses: **57** normal jobs
were submitted and **2** already-current verified reports were reused. All jobs
finished. **44** earlier N/A values now have historical net; **15** remain
unavailable. There are **zero execution errors, zero source rejections and zero
pending jobs** in this targeted refresh.

| Account | Original available | Updated available | Recovered | Still unavailable |
| --- | ---: | ---: | ---: | ---: |
| Apex | 71 / 128 | 115 / 128 | 44 | 13 |
| Lucid | 126 / 128 | 126 / 128 | 0 | 2 |

The remaining Apex trials are **21, 23, 41, 53, 55, 57, 65, 81, 85, 87, 89,
117 and 119**. Lucid trials **117 and 119** remain unavailable. These are
completed calculations with unresolved acquisition means, not source failures
or skipped larger sizes. Their best complete annual-net scores are negative;
the unresolved candidates' optimistic bounds can still outrank them. The saved
reasons identify the particular evaluation sizes (Apex 3–5 MNQ; Lucid 1 MNQ).
No unknown time is replaced with a fabricated mean or successful-path-only mean.

Independent Decimal calculations reproduce **86,400** rankable annual-net
scores across all **59** reports and verify every selected pair against the
saved matrix maximum and tie break. For unavailable reports, the saved bounds
are at least as high as the negative best complete score. The operational
verification reconstructs payout/acquisition cash by calendar quarter, checks
total net, compares every source and setting with its earlier report, and
matches both account values and sorting to a revision-pinned CSV. Every metric
that was already available is preserved. All **9,414** pre-existing report/source
JSON/CSV/ZIP files and all **128** original trial payloads remain unchanged.
All **44** restored historical replays match the independent quarterly payout,
cost and net reconstruction exactly (maximum observed rounding difference $0).

Expected actual spot check: trial **4** links to
`74e35dc0382343fa85a56645d561f6d3`, showing **$176,638** historical net and
the previously qualified **40-MNQ evaluation / 8-MNQ funded** selection. Trial
**21** still links to the explicit negative/ambiguous boundary report
`26a5fa02a9bf4a4a8b9b7555a797c9cd` described above.

Evidence under `artifacts/prop-na-rerun-20261103/`:

- `actual/`: original/current results, all **59** original/new analysis IDs in
  `outcomes.csv` and `outcomes.json`, queued/reused counts, progress and final
  `verification.json`. Its CSV snapshot uses revision **139**.
- `repeat-check/`: a second invocation of the exact operational command reuses
  all **15** current unavailable reports, queues **zero** calculations and
  preserves the original/current values. This also checks rerunning a batch
  whose report links have already been refreshed.
- `actual-browser-final/`: actual source-backtest/configuration/source-check
  screenshots and JSON, the real combined-refresh action, both downloaded CSVs,
  recovered/unavailable report screenshots, a normal report JSON/ZIP download,
  and `verification.json`. Its latest snapshot is revision **169**; values and
  analysis IDs match revision 139. Reloads submit no analysis; a repeat refresh
  queues zero and reuses 15. Both column sorts pass, no browser errors occur,
  and its temporary server is stopped.
- `independent-scores.json`, `preservation-before.json`,
  `preservation-after.json`, `original-trials.json`, `cash-reconciliation.json`
  and `validation.json` retain the independent score/cash checks, preservation
  hashes and automated-gate scope.

The initial optional browser probe attempted an unnecessary manual resubmission
from a stdin-based test server; Python process workers could not import that
temporary entrypoint. Only its newly created failed probe was removed through
the normal API. `actual-browser/initial-probe.json` records the issue and cleanup;
the final check above uses the requested batch refresh and creates no extra
analysis. No original report or targeted batch job was removed or affected.

The original port-8000 portal was used for the actual queue and left running.
No persistent server was started for this increment; all temporary browser
servers were stopped. The Windows VM, other processes, original datasets and
source backtests were left alone. This refresh does not make a new numerical
provider-parity claim.


## Batch result display units — 3 November 2026

The existing batch table now shows max drawdown percentage with two decimal
places and max drawdown duration in elapsed weekday trading days. **Apex
historical net /slot** and **Lucid historical net / slot** divide their respective
saved totals by each account profile's immutable slot count. Existing column
visibility, freezing, ordering and saved-report links continue to work.

This is a display increment. It does not execute a backtest or prop simulation,
change account sizing, rewrite saved reports or round stored financial values.
Raw CSV columns retain full percentages, account-total historical net and duration
seconds. The table status and hover text disclose these units. Prop report totals
still cover all slots. No numerical/provider-parity claim is added.

### Reproduce and inspect the actual result

1. Open `http://localhost:8000/#backtests/batches/d69045ab437942618ec2afb54728c33c`
   and reload the page. In **Columns**, show Trial, Max drawdown pct, Max drawdown
   duration, Apex historical net /slot and Lucid historical net / slot.
2. Trial **4** must show **11.38**, **199** trading days, **$8,832** Apex per slot
   and **$7,490** Lucid per slot. Independently, its saved totals are
   **176638 / 20 = 8831.9** and **37452 / 5 = 7490.4**; the table retains the
   existing whole-dollar currency rounding.
3. Click the duration header twice: sorting uses weekday durations across the
   entire batch before selecting a page, with unavailable values last. Both
   historical-net headers continue to sort and open ordinary saved reports.
4. Open trial 4's Apex analysis, then **Historical replay**: it still shows
   **$176,638** across **20 slots**. Return/reload the table: it remains per slot.
   **Results CSV** still contains raw `historical_net=176638`,
   `lucid_historical_net=37452`, `max_drawdown_duration_seconds=24096000` and the
   original full-precision drawdown percentage.

Duration is reconstructed from every saved trade-close peak/recovery and the
saved period end, not divided from seconds. A Friday-to-Monday recovery advances
one trading day; a same-session recovery advances zero. Zero-trade weekdays and
holidays remain in the clock. CME NQ/ES strategies use Chicago session-ending
dates (local timestamp plus seven hours); other strategies use source-local
dates. The longest weekday interval can differ from the longest calendar-time
interval. Missing/invalid equity produces N/A without inventing a duration.

Independent NumPy business-day counts over the actual saved peak intervals
match **all 128 trials**. Hand-calculated tests cover weekends, idle days,
unrecovered tails, equal-peak resets, same-session overnight CME trades,
different winning intervals under weekday/calendar clocks, and invalid equity.
API tests verify global sorting before pagination, N/A-last ordering, preserved
raw metrics and the original seconds-based API sort. Existing refresh/browser
checks verify the new per-slot values, names, pending/N/A cases, both downloads,
report navigation and reload without changing durable reports.

Run the real read-only product review from the repository root with a fresh
output directory (wait for any active analyses to finish first):

```bash
.venv/bin/python tests/review_batch_result_display.py \
  --output artifacts/batch-display-RECHECK
```

It starts a temporary server, inspects the actual saved batch, changes only its
private browser's column preferences, checks all four requested formats and
sorting, downloads the normal CSVs, opens the existing durable analysis and
reloads. It submits no POST/PUT/PATCH/DELETE requests and stops its browser/server.
No separate demonstration page, simulation API or result store is introduced.

Evidence is under `artifacts/batch-display-20261103/`: `actual-browser-final/`
contains the table/report screenshots, source result snapshot, CSV downloads and
`verification.json`; `independent-duration-check.json` contains all 128 independent
expected/actual durations. `preservation-before.json` and
`preservation-after.json` verify the original report/source files and original
128 trial payloads: **10,272 files** remain byte-identical, and both current and
original CSV downloads are byte-identical to the preceding saved versions.
Backend and browser fixture evidence is labelled synthetic
and retained under `backend/`, `browser/` and `final-sort-check/`.

Automated gates:

```bash
mkdir -p artifacts/batch-display-check
.venv/bin/python -m pytest tests/test_optimization_display.py \
  tests/test_batch_prop_refresh.py tests/test_lucid_batch_refresh.py -q \
  --basetemp artifacts/batch-display-check/backend
.venv/bin/python -m pytest tests/test_batch_prop_refresh_browser.py \
  tests/test_lucid_batch_refresh_browser.py tests/test_automatic_prop_browser.py \
  -q --basetemp artifacts/batch-display-check/browser
```

The focused gates passed **14 backend checks and 4 browser checks**. The final
trading-day sort API adjustment is independently rechecked by the seven display
checks and the actual saved-batch browser review. The user's existing portal is
left running; all temporary test/review servers stop automatically.


## Remove routine batch-result subtexts — 3 November 2026

Successful Apex and Lucid historical-net cells now show only their linked
per-slot amount. The Apex fallback **Default Apex 50K EOD** and both providers'
**Updated analysis** labels are removed. Original and refreshed successful rows
use the same presentation. Pending, rejected, failed and deleted states retain
their useful notices, and completed N/A results retain their calculation reason.
Model/slot hover details, saved refresh provenance, original reports, report
links, table units and downloads are preserved. This is a presentation change;
no financial calculations, backtests or prop analyses are rerun.

Reload the existing batch at
`http://localhost:8000/#backtests/batches/d69045ab437942618ec2afb54728c33c`.
Expect the first five Apex amounts (**$5,068, $13,916, $8,535, $8,832, $12,590**)
to have no routine subtexts, including refreshed trials 4 and 5. Their Lucid
amounts also have no routine subtexts. Trial 21's Apex N/A still explains its
unresolved acquisition-time comparison. Click an amount to inspect the same
saved analysis; reload and download the existing raw CSVs without resimulation.

Reproduce the read-only actual-product review with a fresh output directory:

```bash
.venv/bin/python tests/review_batch_result_display.py \
  --output artifacts/batch-result-cleanup-RECHECK
```

The review verifies successful cells have no subtexts while N/A cells retain
reasons, and retains the previously checked values, sorting, report navigation,
CSV units and reload checks. Evidence is saved under
`artifacts/batch-result-cleanup-20261103/actual-final/`. The temporary server
and browser stop automatically; no persistent server is started.

The existing combined-refresh and Lucid-refresh browser checks also verify
successful cells have no subtexts after completion while pending notices remain.
Run them with a fresh evidence directory:

```bash
mkdir -p artifacts/batch-result-cleanup-check
.venv/bin/python -m pytest tests/test_batch_prop_refresh_browser.py \
  tests/test_lucid_batch_refresh_browser.py -q \
  --basetemp artifacts/batch-result-cleanup-check/browser
```

Both focused browser checks and the actual saved-batch review passed. All
**10,272** original report/source files and **128** original trial payloads remain
unchanged; `preservation.json` and `validation.json` retain the verification.

## Portfolio milestone 1 — separate phase sources and dated lifecycle — 2026-11-04

The accepted scope and all five milestones are in
[prop_portfolio_plan.md](prop_portfolio_plan.md). Milestone 1 adds a fixed-source,
fixed-target dated replay to the ordinary **backtest → Configure prop analysis →
Check source → Run → saved report** workflow. It uses the existing AnalysisStore,
report routes and ZIP publication. There is no separate portfolio demo API/page,
second report store, external calculator or strategy resimulation during analysis.
Earlier datasets/backtests/reports/evidence and the Windows VM are preserved.

### Saved normal-product demonstration

All new demonstration sources are labelled **SYNTHETIC** and created by ordinary
dataset/backtest APIs. The usable library is:

`artifacts/prop-portfolio-m1-20261104/qualified-browser/test_phase_sources_configure_c0/`

It contains the normal dataset/backtest/prop catalogues, original source CSVs,
backtest trade/equity/risk exports, durable reports, JSON/CSV/ZIP downloads,
source-check responses and screenshots. Its `verification.json` indexes the initial
browser outcomes, preserved unchanged. `final-workflow/verification.json` beside
`qualified-browser/` indexes the current-code reports listed below and preserves
the earlier IDs. `final-presentation/` holds the final rendered reports and reuse
journey. Earlier `presentation-lucid/` evidence remains unchanged. These are actual
local model outputs, not predictions or manufactured future results.

| Case | Saved analysis ID | Independent expected observation |
| --- | --- | --- |
| Same evaluation/funded source | `c40f91549fb04f0ca60ca0579ee0be26` | Fixed 10/3 MNQ; pass Jan 5, eligible Jan 6, funded starts Jan 7; six payouts total $13,000 after 30 funded sessions. |
| Change only funded parameters/source | `7eb5e707cee240ce98a8ec625c722fd0` | Same evaluation and 10/3 sizes; first funded trade is source trade 3, not trade 1; $7,500 payouts and account still open after 33 funded sessions. |
| Different funded strategy: VWAP | `c32408551dab4f29a8d79ceb2e091f3d` | Same evaluation, sizes and switching dates; VWAP's own parameters/trades; $0 payouts, funded account remains open. |
| Recovering winner | `493f4f19183e4e6d8e98ebb60bed5a9e` | Source trades finish +$3,000, but the observed opening gap breaches at −$3,000 on Jan 5 before recovery; funded never starts. |
| Lucid same source | `985be8c96a0341798f5e0cf37bab8d30` | Fixed 10/3 MNQ; pass/eligible Jan 7, funded starts Jan 8; five payouts in 25 funded sessions, $10,000 gross withdrawals / $9,000 trader payouts. |

Evaluation source: `d943d010383d40828aa734a22ed0bd89`.
Different-parameter funded source: `b0beaac48f05467e85dd500eb08e8775`.
VWAP funded source: `80e2c8d4bb4d40d2b0aa0cbf1cad0aa0`.
Recovering source: `92ad9052447441619f44f3d0ad19607f`.
The one-session incompatible source is `97dcb7002d804c24ba2d8395386b4988`:
selecting it for funded returns **Funded source incompatible**, with Run disabled.
The source backtest itself stays available; this is not an account breach.

### Reopen without recalculation

Run from `/Users/yx/alphaquest-research-engine-2` in a terminal:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/prop-portfolio-m1-20261104/qualified-browser/test_phase_sources_configure_c0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8011
```

Open `http://127.0.0.1:8011/#backtests/report/d943d010383d40828aa734a22ed0bd89`.
The default automatic summaries retain their original annualized-model meaning.
Select **Configure prop analysis → Dated phase lifecycle · fixed sizes**, retain
10 evaluation / 3 funded MNQ, set commission treatment **Retain scaled source
costs**, and choose Same as evaluation or either saved funded source above.
Check both sources and the shared window, then run. The current matching request
reopens a verified saved result; a changed implementation/settings produces a
new durable analysis, leaving the earlier reports intact. The dated report can
also be opened directly at:

`http://127.0.0.1:8011/#backtests/prop/job/7eb5e707cee240ce98a8ec625c722fd0`

Substitute any saved analysis ID from the table. Inspect separate phase metrics,
activation dates, strategy/parameter snapshots and **Download transition trace
(CSV/JSON)**. Expand the trace: Jan 5 is evaluation, Jan 6 activation eligibility,
and Jan 7 starts funded using source trade 3. Download the normal ZIP; both phase
source/risk inputs and commission reconciliations are included. Reload reads
saved bytes without another POST/calculation. Stop this optional server with
**Ctrl-C**. No persistent server was started by the implementation or tests;
owned fixture/review servers stopped. The user's existing portal was left alone.

To generate a fresh normal-workflow demonstration (use an unused basetemp path;
pytest clears its basetemp), run:

```sh
.venv/bin/python -m pytest -q tests/test_prop_phases_browser.py \
  --basetemp artifacts/prop-portfolio-m1-browser-NEW
PYTHONPATH=tests:. .venv/bin/python tests/review_prop_phases.py \
  --library artifacts/prop-portfolio-m1-20261104/qualified-browser/test_phase_sources_configure_c0 \
  --output artifacts/prop-portfolio-m1-reopen-NEW
```

The second command owns/stops a temporary server/browser, reopens the four saved
Apex reports without POSTs, and configures/checks/runs Lucid through the normal UI
on the existing saved source. It reuses a current matching Lucid report, or adds
a new normal analysis when implementation identity changed. It never runs strategy
bars. It verifies unchanged prior library files, downloads, mobile layout, no
JavaScript errors and no recalculation during reload.

### Independent arithmetic and boundaries

The 35-weekday consecutive-green source has a 150-point winning NQ trade daily:
`150 × $20 = $3,000`. At one MNQ that is $300. Evaluation at ten micros reaches
$3,000 on Jan 5. One Apex waiting weekday is Jan 6, so the first funded source
observation is Jan 7, source trade 3. At three funded micros, $900/day supports
five new $250 qualifying days per cycle and all six full caps in 30 sessions:
`1500 + 1500 + 2000 + 2500 + 2500 + 3000 = $13,000`.

Changing only funded green count from 1 to 2 enters at 250 and exits at 300:
`50 × $20 / 10 × 3 = $300/day`. Its first full $1,500 cap requires equity
`$2,100 + $1,500 = $3,600`, reached on funded day 12, **Jan 22**. Subsequent caps
require 5, 7 and 8 more sessions; 32 of the available 33 sessions pay
`1500 + 1500 + 2000 + 2500 = $7,500`. The evaluation metrics and fixed sizes
remain identical between the two reports.

The VWAP synthetic path has a fixed one-NQ next-open entry at 115, target 130,
zero fees/slippage: `(130 − 115) × $20 = $300/NQ`, or $90 at three micros.
It cannot create a $250 qualifying day. $0 payouts with an open account is a valid
observed outcome, not an invented failure. Its explicit `day_reset_time=700`
resets on the fixture's observed morning bars; source parameters are captured.

Lucid's equal $3,000 evaluation days first satisfy 40% consistency on day 3
(`1/3 <= 0.4`). Zero extra activation weekdays still starts funded in the next
session, Jan 8. At $900/day each five-session funded cycle reaches the $2,000
gross cap; five requests deduct $10,000 and entitle the trader to 90%, $9,000.
The recorded payout dates do not assert bank receipt dates.

The recovering source enters at 100, next bar opens −50 and closes 250:
final source net is +$3,000, while the observed gap is −$3,000 at ten micros.
That jump crosses both the $1,000 daily floor and $2,000 account floor, so the
account closes before recovery. Ordered first-hit handling also checks a
continuous $1,500 adverse move: daily stop at −$1,000 first; a subsequent session
can breach the account floor. Later trades after a daily stop are not consumed.

API/unit cases independently cover Friday pass → Monday eligibility → Tuesday
funded start; targets constrained by mandatory 20/30/40 tiers; no history restart;
Apex 21-weekday expiry; unresolved evaluation and activation-pending endings;
Lucid zero wait and actual calendar activity; both-source active deletion
protection/catalogue membership; request reuse/source changes; unsupported
scaling, missing risk, mixed IS/OOS, invalid sizes and forbidden short activation
waits. Instrument repricing restores source fees once: a configured $1/side MNQ
fee changes a $1,000/NQ source to `$100 − $2 = $98/MNQ`, or **$294** at three.
Evaluation then needs two days, making funded start Jan 8. Fixture expectations
live in tests; product screens show only actual source checks and saved outcomes.

### Scope and remaining work

This is a chronological research replay of one evaluation and its subsequent
funded account. It does not retry purchases, multiply accounts by the old SLOTS
field, estimate annual income or optimize a portfolio. Source scaling is linear
on supported fixed-quantity saved paths; liquidity and size-sensitive fills are
not rerun. Weekday delays retain holidays, as the existing model specifies;
explicit conflicting source calendar snapshots reject. OHLC adverse upper bounds
remain conservative, not measured tick paths. Payouts are requests/deductions,
not settled receipts, and provider approval/live transitions are outside this
model. No additional Bridge or full provider-rule parity is claimed.

The exact monthly ledger and hard spending cap, synchronized separate-account
search, shared-account placement and frozen OOS recommendation/export remain
milestones 2–5. Annualized mode and all earlier reports retain their labelled
training, mean-acquisition-delay and acquired-funded-start assumptions.

The normal API request for dated phases uses the existing endpoint:

```json
{"source_backtest_id":"d943d010383d40828aa734a22ed0bd89","funded_source_backtest_id":"b0beaac48f05467e85dd500eb08e8775","trade_file":"","export_timezone":"UTC","settings":{"ANALYSIS_MODE":"dated_lifecycle","EVALUATION_MICROS":"10","FUNDED_MICROS":"3","ACTIVATION_WAIT_WEEKDAYS":"","COMMISSION_MODE":"source","SLOTS":"1"}}
```

POST this to `/api/prop-analyses/check`, then `/api/prop-analyses`. The funded ID
may be omitted for the same source. An optional `funded_trade_file` and
`funded_export_timezone` identify an independently reconciled measured export;
a same-source inherited export retains its original timestamp timezone. Phase
settings require explicit `ANALYSIS_MODE`; they cannot silently run annualized
calculations. `/sources/{id}` lists the analysis for either phase source.

### Completed qualification and preservation

**116 distinct targeted pytest cases passed**, with zero failures/errors/skips in
these completed gates (one calendar boundary is intentionally exercised twice):

- 61 phase/kernel/first-breach/compiled checks: `qualified-backend.xml`.
- 39 API/store/deletion/activity/reuse checks: `qualified-regression.xml`.
- One full-standard-count Python/compiled portal comparison: `standard-count.xml`.
- One current-code mixed NQ/MNQ workflow: `mixed-final.xml`.
- One complete original Chromium source/configure/check/run/download/reopen flow:
  `qualified-browser.xml`.
- 14 final admission/cache-identity/calendar/no-inherited-position and Lucid
  continuation checks: `admission-continuation.xml`.

The gates retain normal simulation counts; expensive unrelated legacy cases were
explicitly deselected in focused kernels. This is not a full repository-suite
claim. One existing dependency deprecation warning occurs per pytest process.
The optional local kernel build succeeded; its existing generated-C unreachable
code warning remains in `build-qualified.log`. JavaScript syntax, Python compilation
and Git whitespace checks passed.

The final-code UI journey in `final-workflow/` recreated all four Apex selections
and Lucid through configure/check/run on the existing saved backtests. It includes
current source checks, reports, CSV/JSON traces, ZIPs and desktop/mobile screenshots.
`final-presentation/` then repeated the journey, **reusing every same analysis ID**
without new calculations or report files. All **358** inventoried fixture JSON/CSV/ZIP/gzip files remained
unchanged. Both owned servers/browsers stopped, and no JavaScript errors occurred.
Unused annualized controls are hidden in dated configuration; their old profile
values remain in the saved settings for compatibility, without being used as
slot counts, cash forecasts or sampling controls in this replay.

The standalone Decimal/date oracle imports no production calculation code and
matches **every payout date and amount** for the five final reports. Run it
read-only against the saved outputs, with a new output filename:

```sh
.venv/bin/python tests/review_prop_phase_oracles.py \
  --library artifacts/prop-portfolio-m1-20261104/qualified-browser/test_phase_sources_configure_c0 \
  --lucid-report artifacts/prop-portfolio-m1-20261104/final-workflow/lucid-report.json \
  --manifest artifacts/prop-portfolio-m1-20261104/final-workflow/verification.json \
  --output artifacts/prop-portfolio-m1-oracles-NEW.json
```

Additional fast cases reject naive timestamps, conflicting explicit calendar
snapshots and disjoint windows. A source position already open at the common UTC
start is excluded; replay waits for subsequent entries. The trace's
`session_open_utc` is actually UTC, including Chicago DST conversion. Same-source
inherited exports keep their original timezone. Both source hashes, risk/export
identity, parameters, sizes and delay participate in the request key. Modified
or missing inputs cannot reuse a verified current report.

Repeat the completed gates in fresh evidence paths as needed:

```sh
.venv/bin/python setup.py build_ext --inplace
.venv/bin/python -m pytest -q tests/test_prop_phases.py tests/test_prop_phase_validation.py \
  tests/test_native_prop_engine.py tests/test_lucid_prop.py tests/test_intratrade_risk.py \
  tests/test_native_prop_compiled.py tests/test_lucid_funding_continuation.py -k 'not standard_count' \
  --basetemp artifacts/prop-portfolio-m1-backend-NEW
.venv/bin/python -m pytest -q tests/test_native_prop_compiled.py -k standard_count \
  --basetemp artifacts/prop-portfolio-m1-counts-NEW
.venv/bin/python -m pytest -q tests/test_prop_analysis_api.py tests/test_delete_prop_reports.py \
  tests/test_delete_backtests.py tests/test_delete_backtest_activities.py \
  tests/test_batch_prop_refresh.py tests/test_backtest_reuse.py \
  --basetemp artifacts/prop-portfolio-m1-regression-NEW
```

`validation.json` at the evidence root indexes the completed logs/XML, all five
current report IDs, source implementation hashes, artifact integrity and current
request identity checks. `independent-current.json` contains the independent
ledger. `changed-files.txt` lists the 18 source/document/test changes.
`preservation-before.json` / `preservation-after.json` verify **10,245** original
source/report JSON, CSV, ZIP and gzip files unchanged across the demonstrations.
All current captured artifact hashes and sealed report/ZIP hashes match. Older
failed/interrupted probe logs and snapshots remain separately inspectable;
qualification uses the completed gates listed above. No persistent test server,
original-data financial run, source deletion, Windows action, commit or push was
performed. The user's existing development portal process remains running.

## Portfolio milestone 2 — cash ledger and budget — 2026-11-04

This increment adds **Budgeted cash ledger · one unfunded slot** to the existing
backtest → Configure prop analysis → Check source → Run → durable report flow.
It uses the existing AnalysisStore, file endpoints and ZIP, both independently
checked milestone-1 sources, and existing Apex/Lucid trading kernels. No separate
page/API/store, external runtime, provider price lookup or strategy resimulation
is used to calculate cash. Prices in this demonstration are explicitly labeled
**SYNTHETIC $30 evaluation / $40 activation overrides**, not provider prices.

Before extending milestone 1, its independent standard-library Decimal/date
oracle matched all five saved reports and every payout date/amount. Its full
focused admission/API/lifecycle gate also completed **13 passed**. Its first test
invocation hit a missing parent evidence directory; that setup probe was corrected
before the completed gate (`m1-qualified.xml`). Original reports stayed intact.

### Independent expected cash and trading observations

The synthetic evaluation source uses the actual registered consecutive-green
strategy with fixed one NQ, zero source commission/slippage, then normal fixed
10-MNQ evaluation / 3-MNQ funded adaptation. It contains a recovering $3,000 source
winner on January 5 whose observed opening adverse jump is −$3,000 at evaluation
size. This fails before recovery under the existing rules. All later evaluation
sessions earn $3,000 at ten micros and can pass. A separate funded source earns
$900/session at three micros and has an observed adverse opening gap on January
15 that closes the account. Source net wins are never substituted for intratrade
risk. Both source datasets/backtests are labeled SYNTHETIC, created by normal
product APIs, with declared IS and separately reserved synthetic OOS dates.

Cap $100; budget zone America/Chicago; January 5 start; January 31 inclusive end;
activation minimum wait one weekday, modeled payment delay zero, modeled
inclusive deadline seven calendar days after eligibility; modeled trader receipt
30 calendar days after request. Required text descriptions and fee overrides are
saved with the result. The receipt/approval/deadline assumptions are unverified.

| Budget-local date/time | Independently expected ledger event | Paid fee | Trader receipt | Reservation change | Paid January to date |
| --- | --- | ---: | ---: | ---: | ---: |
| Jan 5 00:00 | Evaluation purchase, attempt 1 | $30 | $0 | $0 | $30 |
| Jan 5 00:00 | Reserve potential activation | $0 | $0 | +$40 | $30 |
| Jan 5 16:00 | Failed attempt; release reservation | $0 | $0 | −$40 | $30 |
| Jan 6 00:00 | Replacement evaluation purchase, attempt 2 | $30 | $0 | $0 | $60 |
| Jan 6 00:00 | Reserve potential activation | $0 | $0 | +$40 | $60 |
| Jan 6 16:00 | Evaluation passed; deadline Jan 14 16:00 | $0 | $0 | $0 | $60 |
| Jan 7 16:00 | Eligibility; release reservation, pay activation | $40 | $0 | −$40 | $100 |
| Jan 14 16:00 | Request $1,500 trader payout; separate $1,500 account deduction | $0 | $0 | $0 | $100 |
| Jan 15 16:00 | Funded account breach/closure | $0 | $0 | $0 | $100 |
| Jan 16–31 00:00 | Further evaluation purchase blocked/deferred | $0 | $0 | $0 | $100 |

Actual paid spending must be **$30 + $30 + $40 = exactly $100**. Reservations
contribute zero expense; failed attempts receive no refund. Five new funded
sessions January 8, 9, 12, 13, 14 earn `5 × $900 = $4,500`; this meets the existing
$2,100 safety net, five qualifying days, consistency and first $1,500 cap. January
14's request/account deduction is not received trader cash. Its conditional modeled
receipt is **February 13 16:00 Chicago (22:00 UTC)**, outside January's horizon.
January received cash is $0, paid evaluations $60, activation $40, net cash −$100,
multiple `0 / 60 = 0`, pending modeled receipts $1,500 and remaining allowance $0.
The receipt remains pending despite the modeled January 15 account closure;
this assumes no cancellation/reversal and is not verified provider settlement.

The saved boundary scenarios use the same normal source selections and fees:

- **Month reset:** extend the horizon to February 10. January paid $100. On
  February 1 00:00 Chicago (06:00 UTC), allowance resets to $100; buy evaluation 3
  for $30 and reserve $40. Pass February 2, activate February 3 for $40, funded
  starts February 4. February paid $70, remaining $30, total paid $170, received
  $0, net −$170. The funded account stays open at the horizon, with no invented
  terminal value. Another $1,500 request on February 10 remains a modeled pending
  receipt due March 12; no trading after the horizon is simulated to derive it.
- **Activation expiry:** retain January's horizon but delay payment eight
  calendar days after eligibility. Attempt 2 is eligible January 7; its unchanged
  seven-day deadline is January 14 16:00. The unpaid activation expires then and
  releases $40. The January 15 scheduled payment cannot pay an expired obligation.
  Evaluations paid $60; activation paid $0; remaining allowance $40, net −$60.
  A new purchase needs $30 + $40 reserved and remains blocked despite $40 unspent.
- **Pending obligation across reset:** start January 30, end February 5, payment
  delay eight days. Buy for $30 and reserve $40; pass January 30. Eligibility is
  February 2 and deadline February 9, unchanged by reset. January's **$70 unspent
  allowance expires**, including the $40 reservation. February 1 logs release
  −$40, reset spending to zero, then re-reservation +$40 against the new $100.
  February paid $0, remaining $100, reserved $40, available for purchases $60;
  slot remains occupied, so no extra account is bought. Pending obligation and
  original February 9 deadline remain at the horizon; total net −$30.
- **Receipt within horizon:** extend the main case to February 13. That day's
  $1,500 modeled receipt is now in the horizon. Total paid remains $170, net is
  **$1,500 − $90 − $80 = $1,330**; multiple is **$1,500 / $90 = 16.666666…**.
  Activation costs are reported separately and do not enter that denominator.
  The account remains open and its February 10 request stays pending.
- Missing required receipt description disables Run after source checking and
  returns its meaningful admission reason. Automated boundaries also reject
  missing/invalid dates/timezone/deadline, non-cent fees, multi-slot requests,
  cash controls in annualized mode and horizons outside observed coverage.
  Zero paid evaluation fees yield unavailable multiple, not infinity or zero.
  Payment exactly on the inclusive deadline succeeds; one day later expires.

### Reproduction and saved evidence

Run all commands from `/Users/yx/alphaquest-research-engine-2`. Use a fresh output
or basetemp path: pytest clears its basetemp; the independent verifier/reopening
script refuse to overwrite their output. The primary saved library is:

`artifacts/prop-portfolio-m2-20261104/qualified-browser/test_budget_configuration_cash0/`

It contains normal dataset/backtest/catalogue files plus source checks, submitted
requests, reports, CSV/JSON ledgers, original source/risk captures, ZIPs and desktop/
mobile screenshots. `final-workflow/` at the evidence root records the final-code
configure/check/run/reopen pass against these same saved backtests. Fixture oracles
remain in tests; the product only displays source checks, actual modeled ledger
results and their assumptions. No future receipt is presented as confirmed cash.

Create new synthetic sources and all five reports through the actual workflow:

```sh
mkdir -p artifacts/prop-cash-NEW
.venv/bin/python -m pytest -q tests/test_prop_cash_browser.py \
  --basetemp artifacts/prop-cash-NEW/browser
```

Reopen/recheck/re-run the saved selections through the real UI, without strategy
bars or new datasets, then run the independent verifier against downloaded files:

```sh
PYTHONPATH=tests:. .venv/bin/python tests/review_prop_cash.py \
  --library artifacts/prop-portfolio-m2-20261104/qualified-browser/test_budget_configuration_cash0 \
  --output artifacts/prop-cash-reopen-NEW
.venv/bin/python tests/review_prop_cash_oracles.py \
  --directory artifacts/prop-cash-reopen-NEW \
  --output artifacts/prop-cash-independent-NEW.json
```

The reopener owns/stops its temporary server/browser, checks saved settings copy,
source checks, execution, downloads, reload without POST, mobile overflow and no
JavaScript errors, and verifies prior library files unchanged. With identical
current implementation/settings, execution reuses the existing verified analysis
ID. Changed implementation produces a new durable report. The standard-library
verifier imports no production calculation code: it independently checks every
cash/reservation delta, chronological budget-zone month, each month's cap,
aggregate ratio, exact expected fee rows, late receipt, expiry/reset/open states,
CSV/JSON agreement and all captured ZIP hashes.

Start an optional inspection server on this library:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/prop-portfolio-m2-20261104/qualified-browser/test_budget_configuration_cash0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8012
```

Open the saved evaluation backtest, click **Configure prop analysis**, select
**Budgeted cash ledger · one unfunded slot**, select the saved funded source, use
10 / 3 MNQ, source-cost mode, $30 / $40 prices, cap $100, America/Chicago, January 5
to January 31 2026, receipt lag 30 days, activation deadline 7 and payment delay 0.
Enter explicit unverified modeling descriptions and the synthetic fee override
note. **Check source** must show both phase sources checked. **Run** opens the
normal durable ledger report. Inspect trader cash, monthly spending, reservations,
account deadlines and pending receipts. Download the cash/monthly CSV/JSON or ZIP;
reload without calculation. Stop this optional server with **Ctrl-C**.

Exact API request bodies are saved as `<case>-request.json` under final-workflow.
With the optional server running, check and execute the same normal request:

```sh
curl --fail-with-body -sS -H 'Content-Type: application/json' \
  --data-binary @artifacts/prop-portfolio-m2-20261104/final-workflow/exact_100-request.json \
  http://127.0.0.1:8012/api/prop-analyses/check
curl --fail-with-body -sS -H 'Content-Type: application/json' \
  --data-binary @artifacts/prop-portfolio-m2-20261104/final-workflow/exact_100-request.json \
  http://127.0.0.1:8012/api/prop-analyses
```

The returned ID identifies `/api/prop-analyses/{id}`, durable report download
`/api/prop-analyses/{id}/downloads/report.json`, and cash/monthly exports under
`/api/prop-analyses/{id}/files/cash_ledger.csv` and `monthly_ledger.csv`.

This is one observed path and one slot, not a probabilistic expected-income
forecast or portfolio recommendation. No multi-account/shared-account optimization,
settlement feed, refund/reversal model, provider approval confirmation or new
external/provider numerical parity is claimed. Holiday handling and conservative
OHLC versus measured intratrade-risk limits remain those of milestone 1. Saved
prices/deadlines/delays are assumptions; fee overrides do not change firm trading
rules. All open evaluations/accounts/pending obligations are preserved at the
horizon. Milestones 3–5 remain pending.

### Final saved report IDs and URLs

Evaluation source: `3d8aa5a8e5894bb6af25d91b613f812b`. Funded source: `a13ebd29071b4da6aebe458c18eec8b3`.
Open the evaluation backtest at `http://127.0.0.1:8012/#backtests/report/3d8aa5a8e5894bb6af25d91b613f812b` after starting the optional library server above.

| Case | Exact saved analysis ID | Durable report URL |
| --- | --- | --- |
| Exact $100 / late receipt | `41d6209c3a4d48bd97ab8681589f7112` | `http://127.0.0.1:8012/#backtests/prop/job/41d6209c3a4d48bd97ab8681589f7112` |
| Month reset / open account | `05755ccb7a544524b05dceb82a0e063d` | `http://127.0.0.1:8012/#backtests/prop/job/05755ccb7a544524b05dceb82a0e063d` |
| Activation expiry | `4be1e716223a48de8bb67f97196d10f5` | `http://127.0.0.1:8012/#backtests/prop/job/4be1e716223a48de8bb67f97196d10f5` |
| Pending obligation across reset | `1bd912b189814bf880bf6fdf8d449af5` | `http://127.0.0.1:8012/#backtests/prop/job/1bd912b189814bf880bf6fdf8d449af5` |
| Receipt inside horizon | `ca7d306a76ef45fbb4294c77cc90308f` | `http://127.0.0.1:8012/#backtests/prop/job/ca7d306a76ef45fbb4294c77cc90308f` |

All five final-workflow requests **reused these same saved IDs**, without a new calculation or report file. All **258** inventoried library JSON/CSV/ZIP/gzip files stayed byte-identical; no JavaScript errors or page overflow occurred. The owned server/browser stopped. The independent final verifier conserved **154 ledger rows**, confirmed all months within the cap, and verified **115 captured ZIP hashes**. Results are in `final-workflow/verification.json` and `independent-final.json`.

### Completed checks and preservation

**75 distinct focused pytest cases passed**, with zero failures/errors/skips:

- `qualified-backend.xml`: **71 passed** across cash, both phase sources,
  admission/identity, the normal API, prop/backtest/activity deletion and rollback.
- `cash-final.xml`: **27 passed**, including the two additional cost-preservation
  and all-budget-settings identity/admission cases; 25 overlap the broader gate.
- `qualified-browser.xml`: **2 passed**: all five budgeted scenarios plus the
  original milestone-1 source/strategy/configure/check/run/download/reopen journey.

Additional completed verification includes the pre-extension milestone-1 gate
(13 passed), independent milestone-1 payout/date oracle, final-code UI reuse of
all five cash IDs, and standalone independent checks on every cash/reservation
row, monthly cap, ratio, CSV and ZIP. Python compilation, JavaScript syntax and
Git whitespace checks passed. One existing Starlette/httpx deprecation warning
occurs per API/browser pytest process. This is a focused qualification, not a
full repository-suite or new provider-rule-parity claim. Standard automatic
simulation counts were retained; the cash mode itself is chronological replay.

Re-run the completed automated gates with a fresh evidence directory:

```sh
mkdir -p artifacts/prop-cash-check-NEW
.venv/bin/python -m pytest -q tests/test_prop_cash.py tests/test_prop_phases.py \
  tests/test_prop_phase_validation.py tests/test_prop_analysis_api.py \
  tests/test_delete_prop_reports.py tests/test_delete_backtests.py \
  tests/test_delete_backtest_activities.py \
  --basetemp artifacts/prop-cash-check-NEW/backend
.venv/bin/python -m pytest -q tests/test_prop_cash_browser.py \
  tests/test_prop_phases_browser.py --basetemp artifacts/prop-cash-check-NEW/browser
```

The current combined backend invocation collects 73 cases because it includes
the final two cash cases added after the original 71-case gate was collected.
Those two independently completed in the 27-case final cash gate. Automated
cash boundaries also include 32 independently generated deterministic paths,
full-cap enforcement despite immediate receipts, calendar-month timezone/DST
boundaries, inclusive deadline equality, unresolved evaluation/activation state,
zero evaluation-fee denominator, and fractional Lucid entitlement rounding while
preserving its raw account deduction and 90% share.

`artifacts/prop-portfolio-m2-20261104/validation.json` indexes the completed gates,
current implementation hashes, final IDs and independent/preservation results.
All **42,664** inventoried original source/report/evidence JSON/CSV/ZIP/gzip files
remain byte-identical, as recorded by `preservation-before.json` and
`preservation-after.json`. Earlier probe outputs remain inspectable separately;
the final evidence is in `qualified-browser/`, `final-workflow/` and
`independent-final.json`. All owned temporary servers and browsers stopped;
**no persistent server was started**. The user's existing portal, Windows VM,
other processes, datasets, backtests and earlier results were left intact.
No commit or remote push was performed.

## Simpler prop configuration and budget timezone dropdown — 2026-11-05

The reported 422 came from an empty free-text budget timezone: its grey
`America/Chicago` example was a placeholder. The form now has a real dropdown,
visibly defaulting to **Chicago · America/Chicago**, with New York, Singapore and
UTC choices. Copying a saved report with another valid IANA timezone adds and
selects that exact value, preserving its monthly boundaries. Backend timezone
validation and saved calculation semantics remain unchanged.

The prop form also reduces routine entry:

- Keep the account/method, fixed source sizes, budget, dates and saved fee choices
  visible. Collapse source search/optional exports and trading-cost/advanced
  controls, including commission overrides and JSON, until requested.
- **Use full shared observed period** fills both dates from the selected saved
  sources. The visible range follows source selection; date values only change
  when the user clicks that button. Custom dates remain editable.
- Receipt dropdown choices are same-day, five-day, thirty-day or Custom. An
  activation dropdown offers modeled payment at eligibility with a seven-calendar-
  day inclusive deadline, or Custom. Choosing a preset saves its explicit
  unverified assumption text. Neither timing choice is silently accepted by
  default. Copied reports open as Custom with their exact saved text/values.
- Missing routine values show an inline error beside Check source and focus the
  relevant field, rather than requiring the user to interpret FastAPI's 422 log.
  The fee summary explains the paid evaluation plus activation reservation needed
  for a purchase and warns when the selected cap blocks acquisitions. That cap
  remains valid as a deliberate zero-purchase baseline.
- Source checking shows a short identity/risk/cost summary and both phase checks;
  full snapshots and resolved settings remain expandable. Saved reports and their
  calculation, ledger and download contracts are unchanged.

### Main-library validation

Your existing real-data IS backtest remains available at:

`http://127.0.0.1:8000/#backtests/report/603138d438cc488bbe649c2fb1ac9798`

It uses `ofb_bars_NQ` and fixed-size VWAP observations within 2021–2024. The
read-only product review opened that backtest → Configure prop analysis →
Budgeted cash ledger, used the default Chicago dropdown, entered a $200 cap,
clicked **Use full shared observed period**, selected modeled five-day receipts
and immediate/seven-day activation, and clicked **Check source**. It retained
normal saved fee defaults and commission settings; no advanced section was opened.

Expected and observed: missing budget first produced a focused inline message
without a POST; choosing the above settings then produced **HTTP 200**, **771
trades checked**, both sources checked, dates **2021-01-04 → 2024-12-31**, and
**Run analysis enabled**. This review submitted **zero analyses and zero
backtests**; the user can now execute the saved-trade analysis normally. No
provider purchase, actual settlement or future performance is implied.

Evidence is under `artifacts/prop-form-ux-20261105/main-library/`:
`verification.json`, `request.json`, `source-check.json`, missing-budget inline
error, desktop-ready and mobile screenshots. The existing main server was left
running. To repeat this read-only review against your own running main server,
use a fresh output directory:

```sh
PYTHONPATH=tests:. .venv/bin/python tests/review_prop_config.py \
  --url http://127.0.0.1:8000 \
  --source 603138d438cc488bbe649c2fb1ac9798 \
  --output artifacts/prop-form-main-RECHECK
```

The script owns/closes only its private browser; it never starts/stops your server
or submits analysis/backtest creation. For the full normal product demonstration,
run the updated browser checks with a fresh basetemp:

```sh
mkdir -p artifacts/prop-form-RECHECK
.venv/bin/python -m pytest -q tests/test_prop_cash_browser.py \
  tests/test_prop_phases_browser.py tests/test_prop_analysis_browser.py \
  tests/test_prop_commissions_browser.py tests/test_lucid_prop_browser.py \
  --basetemp artifacts/prop-form-RECHECK/browser
```

These checks use normal saved synthetic sources/reports and owned temporary
servers, covering the five original $100/reset/expiry/late-receipt cases, the
preset-based path, saved-settings reuse, arbitrary saved timezone preservation,
check invalidation on timezone change, inline errors/focus, desktop/mobile layout,
and existing annualized/commission/Lucid workflows. Fixture expectations remain
in tests; there is no separate validation page, API or report store.

Completed UX checks: **34 backend boundary/admission checks passed**. The broader
browser run passed seven cases and found one pre-existing stale assertion that
expected no Sizing tab when funded outcomes were unavailable. The native report
renderer is byte-identical to HEAD and already retains joint-sizing rejection
diagnostics. The corrected focused annualized case passed, explicitly checking
“No training evaluation passed,” no selected pair and no historical replay.
Thus **eight distinct browser cases passed across the suite and focused rerun**;
this is not a full repository-suite claim. The initial failure remains in the
XML rather than being hidden. Evidence: `backend-boundaries.xml`,
`qualified-browser.xml`, `qualified-annual.xml`, and
`annual-diagnostics-baseline.json` under `artifacts/prop-form-ux-20261105/`.

The standalone Decimal/date oracle also rechecked the five durable cash scenarios:
all **154 ledger rows**, monthly caps, independent fee totals and **115 captured
ZIP hashes** still match. `independent-cash.json` retains those results. The normal
product library is `qualified-browser/test_budget_configuration_cash0/` under
that root; its verification manifest also records the new preset and saved-custom-
timezone report IDs. Earlier November 4 reports/evidence remain unchanged.
`validation.json` indexes the completed evidence and preservation results.

All **42,664** previously inventoried original source/report/evidence files remain
byte-identical. The original NQ dataset's **201,905,490 stored bytes** still match
its saved SHA-256. No production Python calculation/API contract changed, and the
main-library review created no analysis or backtest. Owned temporary servers and
private browsers stopped; the user's main port-8000 server was left running.
Refresh the main portal configuration page to load the updated static form.

## Retire the standalone lifecycle selector — 2026-11-05

The **Analysis method** selector now contains only **Annualized sizing · existing
single source** and **Budgeted cash ledger · one unfunded slot**. Annualized stays
the fresh-form default. Lifecycle calculations and earlier reports are retained;
this change does not modify financial calculations or the legacy API contract.

Earlier lifecycle reports expose **Configure budgeted analysis**. It copies both
saved sources, their fixed targets and other saved account settings. The monthly
cap, dates and timing choices remain empty until entered. Clicking **Check
source** before completing them shows a focused inline error and submits no POST.
No new method is selected through hidden JSON overrides: the visible method owns
the outgoing analysis mode.

### Saved product demonstration

Evidence is in `artifacts/prop-method-selector-20261105/`. The normal synthetic
product library is `browser/test_phase_sources_configure_c0/`, with:

- Evaluation source `3801164a791f4af59bf78aa10b1f7c3c`.
- Different-parameter funded source `d794f53dd6014380b66bc7f1cbb71e99`.
- Retained lifecycle report `901ef9a6cdbb4b35a6078138d44cd377`.
- New budgeted report `4d130e549fab453d98e5dd4f28cbe24b`.

Reopen this library without rerunning strategy bars or calculations:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/prop-method-selector-20261105/browser/test_phase_sources_configure_c0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory \
  --host 127.0.0.1 --port 8013
```

1. Open `http://127.0.0.1:8013/#backtests/report/3801164a791f4af59bf78aa10b1f7c3c`
   and choose **Configure prop analysis**. Expect exactly the two methods above.
2. Open `http://127.0.0.1:8013/#backtests/prop/job/901ef9a6cdbb4b35a6078138d44cd377`.
   Its saved dated lifecycle still shows $7,500 in modeled trader entitlements,
   an evaluation pass on January 5 and funded start on January 7. These are the
   previously independently derived synthetic outcomes, not a cash forecast.
3. Choose **Configure budgeted analysis**. Expect the same two sources, evaluation
   target 10 MNQ and funded target 3 MNQ, with empty cap/dates/timing choices.
   Click **Check source**: the missing monthly cap is identified and Run stays
   disabled. No request is submitted with inferred budget assumptions.
4. Set cap $100, evaluation price $30, activation price $40, and both observed
   dates to `2026-01-05`. Explicitly select same-day modeled receipts and modeled
   immediate activation payment/seven-day deadline. Check and run. Expect the
   saved budgeted report above to be reused. Independently: one evaluation costs
   $30, its $40 activation is only reserved, and eligibility is after the chosen
   horizon. Receipts and paid activation fees are $0; net cash is **-$30**,
   remaining allowance $70, reserved allowance $40. Reservations are not expenses.
5. Download the cash ledger/ZIP and reopen/reload the report. Expect unchanged
   saved outputs without recalculation. A one-session incompatible funded source
   is also exercised by the browser check and keeps Run disabled.
6. Stop the manually started server with Ctrl+C.

The browser check captures desktop/mobile screenshots, source checks, all four
retained lifecycle outcomes, budgeted downloads and `verification.json`. It
verifies all 16 retained report/trace/ZIP downloads remain byte-identical after
configuration and publication of the new budgeted result. Fixture expectations
remain in the test, not in a product validation screen.

The read-only `legacy-reopen/verification.json` additionally records four actual
November 4 lifecycle reports reopened against the current UI, both-source/size
copying, zero submitted POSTs, 358 unchanged original fixture files and shutdown
of its owned temporary server. Earlier evidence was not regenerated or rewritten.

To repeat checks, use a fresh output directory (pytest clears its basetemp):

```sh
mkdir -p artifacts/prop-method-selector-RECHECK
.venv/bin/python -m pytest -q tests/test_prop_phases_browser.py \
  tests/test_prop_cash_browser.py tests/test_prop_analysis_browser.py \
  --basetemp artifacts/prop-method-selector-RECHECK/browser \
  --junitxml artifacts/prop-method-selector-RECHECK/browser.xml
PYTHONPATH=tests:. .venv/bin/python tests/review_prop_phases.py \
  --library artifacts/prop-portfolio-m1-20261104/qualified-browser/test_phase_sources_configure_c0 \
  --output artifacts/prop-method-selector-RECHECK/legacy-reopen
```

Completed validation: **five focused browser checks passed** (241.39 seconds),
covering the retired-selector successor journey, the existing budgeted cash
demonstrations, and annualized report/configuration behavior. `browser.xml`
records the full run. JavaScript syntax and `git diff --check` passed. This is
not a full repository suite or a new numerical/provider qualification.
`preservation-after.json` confirms all 361 protected files are unchanged,
including the three existing calculation modules and 358 earlier fixture
artifacts. `validation.json` indexes the evidence; `task.patch` isolates this
change from the pre-existing uncommitted work. All owned temporary test servers
and browsers stopped; no persistent server was started, and the user's existing
server/processes were left alone. Refresh the portal to load the two-option form.

## Independent phase optimization specification — 2026-11-05

Documentation-only increment at inspected code baseline
`71f97a61e568b39b6bf17647078dcdb2364069cb`:
[phase optimization plan](phase_optimization_plan.md). No optimizer was implemented
or simulation run. No new numerical result, provider verification or parity claim
is made. Earlier product evidence and the completed portfolio milestones 1–2
remain unchanged; no server was started.

The specification defines independent Evaluation cost/calendar-time Pareto
selection and Funded horizon cash selection conditional on starting funded. It
maps the inspected source/API/UI/storage, defines candidate/result contracts,
calendar/settlement/censoring and uncertainty semantics, cross-job IS campaigns,
frozen manual OOS assessment and five implementation milestones. Annualized joint
sizing is classified as retained legacy business-level optimization. Its current
runtime behavior and reports are unchanged.

To review and reproduce this documentation increment from the repository root:

1. Follow **README → Independent phase optimization plan**, or **Docs → Planning
   and proposals → Independent phase optimization**. Expect a clear planned
   status, current-code gap table and links to the existing implementation.
2. Read the metric definitions and test-only examples. Independently check the
   IID example: `30 / 0.5 + 40 = 100`, `2 / 0.5 = 4` calendar days, median 2,
   P90 8, throughput 0.25/day. Check the two frontier points' marginal cost:
   `(140 - 100) / (10 - 6) = 10` USD/day. These are analytical fixture designs,
   not actual strategy results or verified provider rules.
3. Follow the architecture status table and portfolio prerequisite section.
   Expect completed source/ledger work to stay implemented, independent search
   to stay planned, and portfolio optimization to be optional downstream work.
4. Inspect `git diff -- AGENTS.md README.md docs/README.md docs/architecture.md
   docs/prop_portfolio_plan.md docs/prop_simulation.md docs/research_workflow.md
   docs/prop_simulation_review.md` and open the new
   `docs/phase_optimization_plan.md` (untracked new files do not appear in ordinary
   `git diff` before staging). Run `git diff --check`. Expect documentation-only
   changes with earlier evidence retained and no whitespace errors.

For future implementation, the required product journey is **saved IS backtest
report → Configure phase/candidates → Check source → Run → durable phase report
and downloads → Freeze → manual OOS assessment**. P1 first delivers a single
Evaluation candidate; P2 adds Pareto search; P3 independently adds Funded search;
P4 generates cross-strategy candidate grids; P5 enforces package freeze/assessment.
Each milestone must save real source checks, report IDs, expected/actual values,
rejection/censoring boundaries, ZIPs and exact user reproduction steps here.
This planning entry does not stand in for those future demonstrations.

Documentation validation passed: all 38 added local links/anchors resolve,
analytical example arithmetic/quantiles match, changes are limited to nine
documentation files, and previous AGENTS/review text is preserved. Navigation,
portfolio, model and research-workflow edits are additive; `git diff --check`
passes. Production tests and
browser checks are not required for this documentation-only change and were not
run. No persistent server, commit or GitHub push was made.

## Independent phase component extraction — 2026-11-05

This is the requested orchestration refactor, preceding optimizer milestone P1.
The public Python interfaces and frozen contracts are documented in
[the plan](phase_optimization_plan.md#implemented-precursor-independent-simulation-profiles)
and [API example](prop_simulation.md#independent-simulation-component-apis--2026-11-05).
Evaluation/acquisition and fresh-funded horizon simulations accept one saved
source each and run independently. Existing kernels, commission/risk checks and
sampling are reused. `native_analysis.training_economics` and `_funded_profile`
delegate to the extracted routines; the joint selector and report formats stay.
As explicitly requested, no portal controls or phase HTTP/report modes were added.

Saved evidence root: `artifacts/prop-phase-components-20261105/`.

- `baseline.json`, `apex-legacy-before.json`, `lucid-legacy-before.json`: complete
  deterministic calculation payloads captured before editing. SHA-256 values are
  `54e3c71eccb1236a31e2f2d47a3b790e4acfcb94c75f8069bbeb347c2e8e7e08` (Apex)
  and `3ebc4d1ee7836577dbb2637b38f81278a193f1cf07b562a91b9af2fe9ceb8c83`
  (Lucid). Tests reproduce both hashes after extraction, covering all calculation
  fields, selection, holdout distributions and history, not just selected scores.
- `qualified-components/test_inspectable_component_cap0/`: actual JSON component
  captures for evaluation, funded, zero-pass evaluation, funded without passes,
  censored evaluation/funded and recovering-price risk breach. These are development
  captures, not a second product report store. Their sources were created through
  normal dataset/backtest routes and labeled **SYNTHETIC**. `verification.json`
  records source IDs and **139 unchanged saved source/report files**.
- `final/test_joint_sizing_actual_backt0/`: the normal product demonstration,
  including `source-check.json`, three screenshots, `report.json`,
  `joint_sizing.csv`, `joint_sizing.json`, `analysis.zip` and `verification.json`.
  Source `0ab00c0a25da49bcbb622844f00868e5`; Lucid report
  `48454defc0eb4bd4a2e61a8f24fb8298`. The existing browser test now opens the
  existing Advanced section before editing slots; product UI code is unchanged.

Independent expectations are fixtures in tests, never runtime inputs. For the
saved $3000/NQ/day source, Apex evaluation at 10 MNQ passes in one weekday,
costs `49 + 129 = $178` and takes two replacement weekdays including activation.
At 3 funded MNQ, $900/day pays the six existing caps on weekdays
5/10/15/20/25/30, totaling **$13,000**. The $1000/NQ/day source at 1 evaluation
MNQ earns only $2100 in 21 weekdays: all attempts expire and acquisition remains
unresolved. Its independent funded run at 10 MNQ still pays **$13,000**.
A Lucid computational guard of two weekdays keeps all eight slow evaluation
paths censored, with pass-probability bounds `[0,1]`. Four funded weekdays at
1 MNQ give zero payout and eight open/censored lifetimes; unrestricted lifetime
is `null`. A gap to the drawdown floor breaches before the later profitable
source close. Missing/corrupt risk, inconsistent costs, unsupported scaling,
profiles/versions, sizes and mutated source manifests reject explicitly.

To reproduce the component calls from the saved normal backtests:

```sh
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from alphaquest.backtest_runs import RunStore
from alphaquest.prop.phase_profiles import (
    SavedTradeSource, EvaluationProfile, FundedProfile, SimulationConfig,
    EvaluationSamplingConfig, SourceCosts, rule_version,
)
from alphaquest.prop.evaluation_profiles import simulate_evaluation_profile
from alphaquest.prop.funded_profiles import simulate_funded_profile

root = Path('artifacts/prop-phase-components-20261105/qualified-components')
saved = json.loads((root/'test_inspectable_component_cap0/verification.json').read_text())
runs = RunStore(Path(saved['library']))
source = SavedTradeSource(saved['source_ids']['winner'])
version = rule_version('apex-50k-eod')
simulation = SimulationConfig(simulations=8)
evaluation = simulate_evaluation_profile(
    runs, source, EvaluationProfile('apex-50k-eod', version, '49', '129'), 10,
    simulation, sampling=EvaluationSamplingConfig(chain_simulations=8),
    costs=SourceCosts(mode='source'),
)
funded = simulate_funded_profile(
    runs, source, FundedProfile('apex-50k-eod', version), 3, 30,
    simulation, costs=SourceCosts(mode='source'),
)
print(evaluation.acquisition['cost_per_funded'], evaluation.acquisition['replacement_days'])
print(funded.payouts['mean_trader_payout'], funded.survival['lifetime_complete'])
PY
```

Expect `178.0 2.0` and `13000.0 True`. Each call is independently usable; remove
either call without affecting the other. Full provenance and boundary outputs
are inspectable in the captured JSON files.

To inspect the unchanged product journey, optionally start the saved browser
library (this command is for the user; no persistent server was started):

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/prop-phase-components-20261105/final/test_joint_sizing_actual_backt0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8011
```

Open `http://127.0.0.1:8011/#backtests/report/0ab00c0a25da49bcbb622844f00868e5`.
Choose **Configure prop analysis → LucidFlex → Advanced**. Six slots must reject;
five slots allow **Check source → Run**. Open the retained report's Sizing tab:
expect evaluation/funded sizes **4/3 MNQ**, acquisition **3 weekdays**, funded
lifetime **25 weekdays**, **1,600 pairs**, and
`261 * (9000 - 80.5) / 28 = $83,142.48214285714` per slot-year. Historical replay
shows payouts **$90,000**, costs **$1,208**, net **$88,792**. Download the CSV/JSON
and ZIP, then reload; the report reopens without changing source trades. This
is the retained legacy workflow, not the pending independent optimizer UI.
Stop this optional server with **Ctrl-C**.

Reproduce automated checks in a fresh directory; pytest clears its basetemp:

```sh
.venv/bin/python -m pytest -q tests/test_prop_phase_profiles.py \
  tests/test_joint_prop_sizing_browser.py \
  --basetemp artifacts/prop-phase-components-RECHECK \
  --junitxml artifacts/prop-phase-components-RECHECK.xml
.venv/bin/python -m pytest -q tests/test_prop_training_economics.py \
  tests/test_joint_prop_sizing.py tests/test_native_prop_engine.py tests/test_lucid_prop.py
```

The final component suite passed **30 tests**; the component/browser run passed
**31 tests**; the focused legacy/kernel gate passed **54 tests**. Full regression
details and any rechecks are indexed in the evidence root's `validation.json`.
The additional existing regression gate (`regression.xml`) finished with
**108 passed, 3 failed** across compiled/reference parity, parallel execution,
Lucid continuation, API/risk/commission checks, dated phases/cash, publication,
deletion and automatic/reuse reports. It overlapped edits to production files;
the three failures were generic backtest-publication HTTP 500 responses, whose
inner exceptions are not retained in those responses. All three passed with
final code held stable (`stable-recheck.xml`, **3 passed**) and on an isolated
original HEAD (`original-head-check.xml`, **3 passed**). Live code hashes enter
request/publication identity checks, so editing during that gate prevents using
it as a clean baseline; the exact underlying exceptions were not recovered.
No single fully green 111-test gate or full repository pass is claimed.
There are **196 distinct selected tests with passing outcomes across the
completed runs and targeted rechecks**, without counting duplicates.

The three targeted rechecks can be reproduced with:

```sh
.venv/bin/python -m pytest -q \
  tests/test_prop_parallel_runtime.py::test_normal_backtest_runs_standard_prop_sweeps_in_parallel \
  tests/test_prop_risk_workflow.py::test_native_risk_capture_default_source_hashes_downloads_and_fail_closed \
  tests/test_prop_risk_workflow.py::test_risk_snapshot_rejects_corrupt_costs_even_with_resigned_file
```

Browser fixture servers and browsers shut down after checking. No server remains
running from this task. Earlier evidence and the main data library were not
regenerated or edited. No GitHub push was made.

Limits remain explicit: weekday acquisition/horizons, the legacy fee/pass-rate
cost estimator, batch-aborted chain counts unavailable, and payout-time modeled
receipts without settlement/pending-cash forecasts. No independent selector,
calendar forecast, durable phase-mode report or provider parity is claimed.
Next is P1's dated single-evaluation acquisition sampling/metrics and the minimum
normal configure/check/run/report integration, composing these components while
keeping the joint path compatible. Funded P3 can proceed independently.

## Standalone Evaluation optimizer — 2026-11-06

Implemented `evaluation-optimization-empirical-iid-v1` in
`alphaquest/prop/evaluation_optimization.py`, with additive dispatch in the
existing prop check/run API and AnalysisStore. The current task explicitly
defers UI: the usable journey is an ordinary saved IS backtest/trial → an
Evaluation request → existing source check → existing analysis worker → durable
report/CSV/ZIP. No demo endpoint, second result database or legacy selector
change was added. The complete [metric and assumption contract](prop_simulation.md#standalone-evaluation-optimizer--2026-11-06)
and [milestone boundaries](phase_optimization_plan.md#implemented-standalone-evaluation-backend--2026-11-06)
distinguish the implemented backend from the remaining UI/campaign work.

### Saved normal-product demonstration

Evidence root: `artifacts/evaluation-optimizer-20261106-release/`.
All datasets and backtests were created through the ordinary API and labeled
**SYNTHETIC**. No existing user dataset/backtest/result or older evidence was
changed. These small deterministic examples use eight original attempts and
eight acquisition chains per candidate; they qualify arithmetic, not forecast
precision.

The main library is `evaluation-search-library0/`, with saved sources
`1d2434d6e38443a2b6a1d7e188ad7fff` and
`8008e0a8a3694bbc857e34be2803a82d`. Both use the registered
`consecutive_green_hold` strategy with different saved parameters, native risk,
explicit source costs and the same declared IS dataset/window. The source CSVs
independently earn 300 and 100 USD per MNQ per session respectively, with zero
costs/adverse price moves. The local evaluation target is 3,000 USD; therefore
the chosen sizes take exactly 1, 2, 3 and 6 sessions to pass.

The completed analysis is **`0ff87be07cd44da7899d2df9b7876d30`**, saved at
`evaluation-search-library0/prop_analyses/0ff87be07cd44da7899d2df9b7876d30/`.
With purchase Monday 2026-01-05, one activation-delay session, next-open-session
readiness and activation fee 40, actual and independently expected results are:

| Source daily USD/MNQ | MNQ | Evaluation fee | Acquisition cost | Calendar days to usable funded account | Pareto |
| --- | --- | --- | --- | --- | --- |
| 100 | 10 | 30 | 70 | 4 | Yes |
| 100 | 5 | 50 | 90 | 9 | No, dominated |
| 300 | 5 | 60 | 100 | 3 | Yes |
| 300 | 10 | 100 | 140 | 2 | Yes |

Every pass probability is 1, expected attempts is 1, and median/P90 equal the
listed duration. Both 30/60-day funding probabilities are 1. Inverse-duration
30-day rates are `30/4`, `30/9`, `30/3`, `30/2`; these are not finite-month counts.
The returned frontier is cost-sorted `(70,4),(100,3),(140,2)` with marginal
acceleration costs **30** and **40 USD/calendar day saved**. There is no winner.
The main demonstration checks poisoned funded/joint-selection dependencies,
input-order-invariant reuse, both-source catalogue membership, report/ZIP
downloads and reopening through a fresh AnalysisStore without calculation.
**92 pre-existing saved source/report files in that library remained byte-identical.**

`evaluation-search-request.json` is the exact submitted configuration;
`evaluation-search-verification.json` records source checks, expected/actual
points and preservation/reopen results. The saved report includes candidate
manifests, source/risk/cost identity, original attempt arrays, dated chain records,
uncertainty/censoring assumptions, raw source inputs and local code/kernel hashes.
`artifacts/evaluation-optimizer-20261106-release-code.json` captures qualified implementation
hashes. `artifacts/evaluation-optimizer-20261106-release-independent.json` records the
standard-library-only verifier's independent trade/fee/date/frontier calculations
and **13 ZIP member checks**, importing no production calculator or sampler.

The second library, `test_two_strategies_two_saved_0/`, creates ordinary saved
optimization jobs **`70d9e21576814d2ab2d263699808768c`** and
**`babb57ba8bcc4182963def7a5d2d6f8f`** for
`vwap_pullback_risk_sizing` and `consecutive_green_hold` on one synthetic dataset.
Their saved trials are `46f27729a4db45f78e70e2bf710be881` and
`abe7307b9d634f16af8f3a24486284bb`.
Analysis **`4963765a6f8242db92410f10becc04a4`** retains all four requested
source/size configurations. Deliberately huge held-bar adverse moves produce
zero evaluation passes despite positive source trades. Expect four unresolved
candidates, no finite cost/time means and an empty estimated frontier; none is
marked definitely dominated. `cross-job-verification.json` records complete
membership. The synthetic bars include closing observations so both actual
strategy paths remain intraday flat; saved trades were never rewritten.

### Exact reproduction and expected observations

Reproduce the whole dataset/backtest/check/run/download journey and rejection
checks with a **new** evidence directory (pytest clears its `--basetemp`):

```sh
.venv/bin/python -m pytest tests/test_evaluation_optimization.py -q \
  --basetemp artifacts/evaluation-optimizer-RECHECK \
  --junitxml artifacts/evaluation-optimizer-RECHECK.xml

.venv/bin/python tests/review_evaluation_optimizer.py \
  --library artifacts/evaluation-optimizer-RECHECK/evaluation-search-library0 \
  --output artifacts/evaluation-optimizer-RECHECK-independent.json
```

Expect **16 optimizer tests passing**, the three-point frontier above, all four
cross-job candidates preserved, and a verifier result with
`production_imports: false`, `checked_zip_files: 13`. New backtest/job/report IDs
will differ. The verifier refuses to overwrite its output and never writes into
the library.

To inspect/reuse the already saved request through the same APIs without opening
a network server, from the repository root:

```python
import json, time
from pathlib import Path
from fastapi.testclient import TestClient
from alphaquest.app import create_app

library = Path('artifacts/evaluation-optimizer-20261106-release/evaluation-search-library0')
body = json.loads((library/'evaluation-search-request.json').read_text())
with TestClient(create_app(library/'datasets.sqlite3')) as client:
    check = client.post('/api/prop-analyses/check', json=body)
    check.raise_for_status()
    assert len(check.json()['candidates']) == 4
    response = client.post('/api/prop-analyses', json=body)
    response.raise_for_status()
    analysis_id = response.json()['id']
    for _ in range(1800):
        state = client.get('/api/prop-analyses/'+analysis_id).json()
        if state['status'] not in ('queued', 'running'):
            break
        time.sleep(.1)
    assert state['status'] == 'complete', state
    report = client.get(f'/api/prop-analyses/{analysis_id}/downloads/report.json').json()
    print(analysis_id, report['calculations']['frontier'])
    print([(r['metrics']['cost_per_funded'], r['metrics']['expected_calendar_days_to_funded'],
            r['pareto_member']) for r in report['calculations']['candidates']])
```

With unchanged code/source/access identity, expect reuse of
`0ff87be07cd44da7899d2df9b7876d30`. A changed numerical identity creates a new
report; earlier saved files remain readable. Normal download paths are
`/api/prop-analyses/{id}/downloads/analysis.zip` and
`/api/prop-analyses/{id}/files/phase_metrics.csv`.
No persistent server or browser was started; TestClient workers close on exit.

### Boundary evidence and limitations

Independent tests cover nonconvex Pareto points, a dominated fourth point, exact
ties, equal-time/equal-cost cases and all 120 input permutations; geometric retry
fees with different failed durations and retry overhead; zero/full observed pass
probability; Friday/holiday and weekend/DST dates; inclusive day-30/day-60 events;
activation unpaid until eligibility; pending readiness after a paid activation;
censored chains without successful-only means; fixed start-cohort variance;
opposite-phase fields, bad IDs/sizes/versions, Lucid dated admission, OOS and
incompatible windows; canonical calendar-date rejection; cache dimensions,
funded administrative metadata independence, missing-artifact recovery and
active-job protection of every source.
The normal API demonstration fails immediately if funded profiles, payout
simulation, legacy joint selection or unrelated export discovery are called.

The initial model is empirical IID retries, not retained-block correlation or
finite-budget scheduling. It supports local Apex EOD and declared Chicago
weekday/closure scenarios; dated Lucid inactivity, verified exchange/settlement
calendars, early closes and more approval/reset policies remain unsupported.
Nominal pass/cost intervals and conditional calendar mean SE/CI do not establish
robust simultaneous dominance; every frontier remains explicitly estimated.
The UI, automated candidate generation, confirmation/refinement, frozen choice
packages and final-OOS assessment remain deferred. This backend increment does
not claim the full original P1/P2 exit criteria or provider/external numerical
parity. The legacy annualized workflow and prior phase-source/cash-ledger work
are preserved.

Files changed: `alphaquest/prop/evaluation_optimization.py`,
`alphaquest/prop/store.py`, `alphaquest/prop_api.py`,
`tests/test_evaluation_optimization.py`, `tests/review_evaluation_optimizer.py`,
`docs/phase_optimization_plan.md`, `docs/architecture.md`,
`docs/prop_simulation.md`, and this review log. No legacy account kernel,
joint-sizing implementation or UI file changed.

### Final validation scope

`artifacts/evaluation-optimizer-20261106-release.xml`: **17 passed in 85.61 s**,
comprising all **16** new optimizer tests and the final rerun of
`test_prop_analysis_api.py::test_duplicate_and_failed_operations_remain_errors`.
The independent verifier then passed against the final release report. The
preceding broad regression gate (`evaluation-optimizer-20261106-regression.xml`)
covered **131 cases: 130 passed, one failed** during backtest publication while
production source files were being edited. The failed case passed after edits
stopped in the final 17-case run. This is a broad gate plus targeted recovery,
not a claim that the entire repository suite or a fresh complete 131-case gate
ran green after the final edits. The only emitted warning in the final run is
the existing Starlette TestClient/httpx deprecation.

The broad gate includes independent phase components and frozen full legacy
Apex/Lucid calculation payloads, training economics, legacy joint sizing,
existing analysis API/deletion behavior, dated phases/source admission, cash
ledger, compiled/reference parity and research policy:

```sh
.venv/bin/python -m pytest \
  tests/test_prop_phase_profiles.py tests/test_prop_training_economics.py \
  tests/test_joint_prop_sizing.py tests/test_prop_analysis_api.py \
  tests/test_delete_prop_reports.py tests/test_prop_phases.py \
  tests/test_prop_phase_validation.py tests/test_prop_cash.py \
  tests/test_native_prop_compiled.py tests/test_research_workflow.py -q \
  --basetemp artifacts/evaluation-regression-RECHECK \
  --junitxml artifacts/evaluation-regression-RECHECK.xml
```

Earlier development/qualified artifact directories and saved reports remain
unchanged; the `release` paths above identify the final implementation evidence.
Documentation links and `git diff --check` also pass. All started test processes
finished; no server, browser or background test process was left running.

## Standalone Funded optimizer — 2026-11-06

Implemented the standalone **P3 backend** scope with normal saved IS sources,
funded-only API check/run, existing AnalysisStore publication and durable
reports/downloads. No UI or portfolio optimizer was added, as requested. This is
not completion of the original P3 UI/campaign/precision exit criteria and does
not claim provider or external-engine numerical parity. All production account
calculations remain local. No persistent or temporary HTTP server was started;
checks used the normal FastAPI application in-process and closed its workers.

The new `funded_optimization.py` ranks complete, feasible candidates by expected
received cash over a common calendar horizon. `funded_profiles.py` adds dated
orchestration around existing funded account transitions; `lucid_engine.py`
extracts its existing inactivity predicate for use on non-session dates.
`phase_search.py` shares source admission, calendars and captured inputs with
Evaluation. API/store dispatch and the three specification documents are updated;
legacy joint selection and UI files are unchanged.

### Saved normal-product journey and independently expected observations

Evidence root: `artifacts/funded-optimizer-20261106/`. The demonstration library is
`regression-final/funded-search-library0/` below that root. Two **SYNTHETIC**
datasets/backtests are generated through normal dataset import and declared IS
backtest APIs, using the real `consecutive_green_hold` strategy with saved
`green_bar_count` parameters 1 and 2. No trade/results tables are injected.

1. Open the ordinary saved backtest/report for source
   `1c8ec1298e524d03b76fc063b2d61492` (A), or
   `5889b3ed7c574cb3bdd5368598408739` (B). A earns $3,000 per NQ session;
   B earns $1,000; both have zero configured commissions/slippage and no adverse
   movement. These values are independently read from captured actual trades.
2. Configuration is saved as `funded-search-request.json`. It contains A and B
   at 1 and 3 MNQ, local Apex EOD rules, eight paths each, a Jan 5, 2026 target
   start, 14 **calendar** days, and four calendar days of modeled settlement.
   It has no evaluation source/probability/fee/size. Configuration is via the
   existing API in this backend-only increment; there is no new UI control.
3. `POST /api/prop-analyses/check` accepts all four candidates. Reconciled source,
   native risk, net costs, strategy/parameters and IS identity are saved in
   `source_checks.json`. `POST /api/prop-analyses` queues the normal worker.
4. Completed analysis **`5894c4928f8a44f786065e3ae93b30e4`** retains all four
   candidates. A at 3 MNQ wins with **$1,500 received**, **$1,500 pending**, and
   **$3,000 gross account deductions**. Other candidates receive zero. A3 earns
   $900/session: five qualifying days trigger a $1,500 request on Jan 9, received
   Jan 13; the Jan 16 request settles Jan 20, outside the Jan 19 exclusive cutoff.
   A1/B3 earn $300/day and need 12 sessions to reach $3,600 safety-plus-request
   equity; this horizon contains only ten sessions. B1's $100/day never qualifies.
5. Expect first receipt age **8 calendar days**, receipt count **1**, and
   survival **1** for the winner. It remains open: unrestricted expected lifetime
   is `null`, restricted lifetime is **14 calendar days**, and there are ten
   observed sessions. Equity and unpaid requests never enter the cash objective.
6. Fetch the normal `/{id}/downloads/report.json`, `/{id}/downloads/analysis.zip`
   and `/{id}/files/phase_metrics.csv` beneath `/api/prop-analyses`. The ZIP includes
   all candidates, metrics/ranking, sampling, event paths, source checks and
   captured trades/risk. Both source listings contain the analysis. Reversing
   candidate order reuses the same report; reopening with the optimizer poisoned
   performs no calculation. Reopened AnalysisStore integrity checks pass.

`independent-oracle.json` records the standard-library-only verifier's results:
receipts `[0, 0, 0, 1500]`, expected winner/pending/deductions, exact date events,
all **13** ZIP/file entries matching, and **92** original source/report files
unchanged by the demonstration. Earlier reports and qualification folders were
not overwritten. The oracle imports no production calculator, sampler, ranker
or storage module. It lives in tests, not in the product.

### Reproduce and inspect

From the repository root, inspect the existing evidence without recalculation:

```bash
.venv/bin/python tests/review_funded_optimizer.py \
  --library artifacts/funded-optimizer-20261106/regression-final/funded-search-library0 \
  --output /tmp/funded-independent-review-new.json
```

The output path must not already exist. To regenerate via normal product APIs,
use a **new** evidence directory; pytest clears its `--basetemp` directory:

```bash
mkdir -p artifacts/funded-optimizer-RECHECK
.venv/bin/python -m pytest -q tests/test_funded_optimization.py \
  --basetemp artifacts/funded-optimizer-RECHECK/product
.venv/bin/python tests/review_funded_optimizer.py \
  --library artifacts/funded-optimizer-RECHECK/product/funded-search-library0 \
  --output artifacts/funded-optimizer-RECHECK/oracle.json
```

To inspect the saved library through an HTTP client and the ordinary backtest
portal, optionally run the existing app yourself:

```bash
ALPHAQUEST_DATA_DIR="$PWD/artifacts/funded-optimizer-20261106/regression-final/funded-search-library0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8011
```

Stop that optional foreground server with Ctrl-C. Download
`http://127.0.0.1:8011/api/prop-analyses/5894c4928f8a44f786065e3ae93b30e4/downloads/analysis.zip`.
The saved request can be submitted with `curl --json @<funded-search-request.json>`
to `/api/prop-analyses/check` then `/api/prop-analyses`; inspect the returned ID
until `status: complete`. The existing UI does not yet render independent funded
ranking; inspect the saved JSON/CSV/ZIP. This procedure adds no alternate page or
API and requires no external engine.

### Boundary and regression scope

Automated funded checks exercise:

- No evaluation source, poisoned evaluation/joint dependencies, and a source with
  zero evaluation passes; irrelevant automatic evaluation metadata cannot change
  candidate/cache identity.
- Higher cash despite lower source win rate using real native sampled transitions;
  a hard breach cap excludes that candidate. Size, first-payout and P10 hard
  filters, exact ties, uncertainty ties, and no-feasible/unresolved winner states.
- A request at the cutoff never occurs; Jan 13 receipt with an eight-day cutoff
  is excluded/pending, while a nine-day cutoff includes it. Post-closure receipts,
  weekends, DST-date cohorts and declared closures retain the disclosed clock.
- 90/180/365-day horizons; full Apex ladder yields $13,000, six received payouts,
  terminal age 39 calendar days and zero breach probability on the monotone source.
- Matching-horizon Apex/Lucid payouts, deductions and equity equal the legacy
  component under matching assumptions; source and override commissions are
  charged exactly once. Lucid gross deductions differ from its 90% trader share.
- Open lifetimes remain censored; incomplete cash horizons are unresolved.
  Candidate order, stratified means, complete candidate membership across two
  strategies/two saved jobs, cache changes, damaged-artifact invalidation and
  all-source deletion protection are checked.

The saved boundary/API run and final regression totals are recorded below after
completion. Intervals remain conditional Monte Carlo approximations; real
settlement, future profitability, provider-rule currency, campaign freeze and
untouched final OOS are not qualified by these synthetic checks.


Additional saved boundary/API evidence is
`artifacts/funded-optimizer-20261106/funded-final/funded-search-library0/funded-boundary-verification.json`.
Each case includes its complete replayable request and normal analysis ID:

| Case | Analysis ID | Expected received / pending |
| --- | --- | --- |
| Receipt exactly at exclusive eight-day cutoff | `36e8818b4543428c9bc78da6c4319e94` | $0 / $1,500 |
| Same receipt before nine-day cutoff | `98544fd84d3d4d20a1fdb9e99320999e` | $1,500 / $0 |
| Maximum requested size 1 MNQ excludes highest-cash row | `943cd0e7cf3c4647bf8df5b7ea550831` | Winner $0 / $0; excluded 3-MNQ row still shows $1,500 received |

That file also captures the HTTP 422 rejection for an evaluation probability
field in a funded request. The separate final funded suite's main report is
`aa1c03a2c2be4bbca15a3d0048411d35`; its independent oracle is
`independent-oracle-final.json` at the evidence root. Both demonstration libraries
and their original reports are retained.

The final funded suite passed **21 tests** in 54.32 seconds
(`funded-final.log/.xml`). An earlier stochastic fixture incorrectly assumed
$300 losses would breach the native account; the fixed seed produced no breaches.
The fixture now supplies an explicit $3,000 adverse gap to test a genuine hard
breach exclusion. Production behavior was unchanged by that test correction.

The multi-strategy/multi-job funded report is
`5192a2fea49149028df9dce663c448b0`, in
`regression-final/test_two_strategies_two_saved_1/prop_analyses/`.
Its `cross-job-verification.json` records both originating job IDs and all four
candidate memberships. All 12 saved funded implementation-file hashes match the
current code. The cash-ledger, report-deletion and Lucid funding-continuation
regressions passed **41 tests** in 482.90 seconds (`cash-regression.log/.xml`).

Reproduce the relevant checks after building the matching optional kernels:

```bash
.venv/bin/python setup.py build_ext --inplace
.venv/bin/python -m pytest -q \
  tests/test_funded_optimization.py tests/test_evaluation_optimization.py \
  tests/test_prop_phase_profiles.py tests/test_native_prop_engine.py \
  tests/test_native_prop_compiled.py tests/test_lucid_prop.py \
  tests/test_joint_prop_sizing.py tests/test_prop_training_economics.py \
  tests/test_prop_phases.py tests/test_prop_phase_validation.py \
  tests/test_prop_analysis_api.py tests/test_prop_cash.py \
  tests/test_delete_prop_reports.py tests/test_lucid_funding_continuation.py
```

Changed implementation files: `alphaquest/prop/funded_optimization.py`,
`funded_profiles.py`, `phase_search.py`, `evaluation_optimization.py`,
`lucid_engine.py`, `store.py`, and `alphaquest/prop_api.py`. Checks/oracles:
`tests/test_funded_optimization.py`, `tests/review_funded_optimizer.py`, and
`tests/test_evaluation_optimization.py` (cross-job coverage for both phases).
Documentation: `docs/phase_optimization_plan.md`, `docs/architecture.md`,
`docs/prop_simulation.md`, and this review log.

Final relevant regression accounting: **124 non-funded tests** in
`regression-final.log/.xml` passed (Evaluation, phase components, native/compiled
kernels, Lucid rules, joint sizing, training economics, dated sources and APIs).
That 144-case run also included 20 funded tests and retained the single old
stochastic-fixture failure described above; its process exit was nonzero. The
subsequent complete funded run passed all **21** current tests, including the
corrected fixture and the added saved API boundaries. Together with the 41
cash/deletion/continuation checks, the final applicable evidence covers **186
distinct passing cases**, not a claim that the initial mixed command was green
or that the repository's full suite was run. `validation.json` records this
accounting, changed files and artifact links. Matching optional kernels built
successfully; `git diff --check` and local documentation link checks passed.

## Phase research campaigns — 2026-11-06

Implemented saved-backtest/optimization-trial campaigns in `research_campaigns.py`
and `campaign_api.py`, with controls in the existing prop configuration/report
screen. Both phases expand multiple saved strategies/jobs and per-source MNQ
sizes under a hard declared candidate count. Existing local phase optimizers,
source admission, worker and AnalysisStore publish the results. Campaign/freeze
records are small catalogue references; no campaign trade/report copy or external
engine is involved. [API, examples and exact scope](research_campaign_api.md).

### Saved actual product outputs

Evidence root: `artifacts/phase-campaigns-20261106/`. Each library below is isolated
from the user's existing data. All input datasets are explicitly labelled
**SYNTHETIC** and created through the normal dataset/backtest/optimization APIs.
Source reports, normal prop reports, source checks, CSV/JSON and ZIP remain in
those libraries. The production product contains no test oracle table.

| Library under `qualification/` | Campaign | Analysis | Actual independent observation |
| --- | --- | --- | --- |
| `campaign-library0` | `541bd0fd7b584d8391704d850d71263c` | `ffa04e49ae884f7fa011bb1565e14b67` | Evaluation: four points `(70 USD, 2 days)`, `(70, 4)`, `(70, 7)`, `(70, 15)`; only `(70,2)` is on the frontier. |
| `campaign-library0` | `ffd731ccbcc34ab0821c51cf62fff4b8` | `130cba36338a441587191b5879eb0cbf` | Funded: received cash `[0,0,0,1500]`; winning path has $3,000 deductions and $1,500 pending, with no acquisition inputs. |
| `test_campaign_multiple_strateg0` | `ecaee7921d374e1ba2987156f5610ba9` | `0f1cdad1ba914481927e6a7bb3e8e663` | Evaluation: VWAP + Consecutive Green Hold from two ordinary optimization jobs, sizes 1/3, exactly four candidates. Huge adverse synthetic swings leave acquisition unresolved; no fabricated finite winner. |
| `test_campaign_multiple_strateg1` | `85a28c88ad064a248e22ef394ce6ea8b` | `2da9cb6aabc947689d88015d40590ce3` | Funded: same two strategy/job types, independent four-candidate declaration; actual zero-cash paths remain in the full result table. |
| `test_campaign_configuration_re0` | `b3be4242f9c64e57b69011554577eb92` | `e35a53f3dad342bc8a5908e46fb02b95` | Real Chromium journey: budget 3 rejects four source × size candidates; budget 4 passes; received cash `[0,0,0,1500]`; freeze/download/reload succeeds with zero POSTs on reopen. |

The arithmetic fixture has eight IS weekdays with one monotone NQ trade per day.
Parameter A earns $3,000 per NQ day; B earns $1,000. Scaling to MNQ divides by ten
and multiplies by the declared whole-MNQ size. Costs are zero in these explicitly
synthetic sources, so there is no second deduction.

Evaluation compares A/B at 3 and 10 MNQ. The $3,000 target takes respectively
4/1 and 10/3 sessions. Starting Monday 5 January, one activation weekday and the
next usable session give 7/2 and 15/4 elapsed calendar days (weekends matter).
Every attempt passes, so one $30 purchase plus $40 activation gives $70. This
constant-price example has a single fastest frontier point; the existing
independent Pareto tests additionally check trade-offs, ties, nonconvex points
and marginal acceleration cost arithmetic.

Funded compares A/B at 1 and 3 MNQ over `[2026-01-05,2026-01-19)`, with four
calendar days between request and modeled receipt. Only A3 earns $900/session
and qualifies within ten sessions: $1,500 requests on January 9/16, modeled
receipts on January 13/20. The first receipt counts; the second remains pending.
The report keeps gross deductions, received cash and pending cash separate.
Unpaid account equity never enters the ranking. These are scenario calculations,
not future payouts or verified settlement/provider rules.

`independent-review.json` was produced by
`tests/review_research_campaigns.py`, which imports only the standard library.
It derives target sessions/readiness dates from the actual saved trades, checks
all candidate metrics and frontier/ranking membership, verifies freeze/report
hashes and checks 13 artifacts per phase including ZIP contents. The campaign
integration also preserved **92 earlier fixture report/input files** byte for
byte. This preservation count applies to the isolated evidence library, not an
unmeasured claim about every file in the user's working data directory.

### Reopen and reproduce manually

From the repository root, use an isolated saved library:

```bash
ALPHAQUEST_DATA_DIR="$PWD/artifacts/phase-campaigns-20261106/final-browser/test_campaign_configuration_re0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8011
```

Open:

- `http://127.0.0.1:8011/#backtests/prop/campaign/39185f9cde014aab81874c89613cd837`
- Original source report:
  `http://127.0.0.1:8011/#backtests/report/879af08b216044789f8054e6d559f4d1`
- Full download:
  `http://127.0.0.1:8011/api/research-campaigns/39185f9cde014aab81874c89613cd837/exports/analysis.zip`

Expect **Frozen IS selection**, four candidates with their parameters and source
links, the rank-1 A/3-MNQ row showing $1,500 received and $1,500 pending, the frozen
rationale, and CSV/JSON/ZIP downloads. Reload must issue only GETs and preserve
result bytes. `browser-verification.json` records export SHA-256 values;
`frozen-campaign.png`, `checked-campaign.png` and `budget-rejection.png` capture the
actual workflow. Stop this manually started server with **Ctrl-C**.

To reproduce the create/check/run journey, open the original source, configure
prop analysis, expand the campaign section and choose Funded. Keep first source
`879af08b216044789f8054e6d559f4d1`, add
`b5c358f702a6432fa09350b4e345992f`, and set sizes `1,3` for both. Set IS January
5–14, 8 paths, seed 42, block 1, scenario start January 5, coverage end January 1
2037, horizon 14 days, delay 4 days and breach cap 0. Budget 3 must reject and
leave Run disabled. Budget 4 must show four compatible candidates. Run, inspect
the expected cash rows, select rank 1, enter a rationale and freeze. A new campaign
with identical inputs may reuse the original immutable analysis.

For direct API reproduction, `campaign-library0/campaign-verification.json`
contains exact requests for both phases. Start a server with that library instead
and POST the saved request to `/api/research-campaigns`; its campaign ID is
idempotent. GET status/candidates/selection/exports; POST `/run` must return the
same analysis. Use a new campaign UUID for a deliberate changed declaration.
A funded evaluation-fee field, OOS source, duplicate source/size, incompatible
window/cost/risk, or candidate budget below the expanded total must reject.
Referenced sources, optimization jobs and analysis reports must return 409 on
normal deletion attempts. No final OOS is launched.

Automated reproduction uses a **new** artifact path (never reuse an earlier
`--basetemp`, which pytest clears):

```bash
.venv/bin/python -m pytest -q tests/test_research_campaigns.py \
  tests/test_research_campaigns_browser.py --basetemp artifacts/campaign-review-NEW
.venv/bin/python tests/review_research_campaigns.py \
  --library artifacts/campaign-review-NEW/campaign-library0 \
  --output artifacts/campaign-review-NEW/independent-review.json
```

The owned browser fixtures start temporary loopback servers and shut them down.
No persistent server was started for this delivery. Saved reports keep their own
implementation hashes; current UI/docs do not enter calculation identity.

Remaining scope: automatic new-grid launch, adaptive refinement/simultaneous
precision qualification and frozen-package OOS assessment dispatch/enforcement
are not implemented. Freeze is an immutable IS decision/provenance record;
existing manual OOS remains available and separate. Portfolio optimization and
provider/external numerical parity are not claimed.


Validation scope: the broader stable regression run passed **238 tests** with one
existing Starlette/httpx deprecation warning, in 1,184.61 seconds. Its exact output
and JUnit record are `qualification.log` and `qualification.xml`. It includes
campaign/API/browser, both phase optimizers/components, legacy joint sizing,
phase/cash replay, prop APIs, editable/manual OOS research, optimization and
source/report/activity deletion. This is the listed regression scope, not the
entire repository suite. Subsequent campaign-only hardening rejects equivalent
saved-report aliases and mixed measured/OHLC risk conventions, exposes attempt
history, and disables unrelated export discovery during initial portal
configuration. The first affected-surface run (`final-campaigns.log` / `.xml`) had 59 passes
and one fixture failure: an intended fresh backtest correctly returned a cached
HTTP 200, while the helper expected 201. The test now explicitly sets
`reuse_results=false`; no product workaround was added. The stable rerun passed
**60 tests** in 307.50 seconds (`verified.log` / `verified.xml`). Earlier evidence,
including the failure, is preserved.


Final browser verification passed **1 end-to-end test** in 52.82 seconds
(`final-browser.log` / `final-browser.xml`). It executes both campaign forms,
checks/freezes both phase results, verifies zero recalculation on reopen, and
checks a binding funded position constraint. The two 3-MNQ candidates remain
visible as **infeasible / Not ranked**, including the otherwise highest $1,500
cash estimate; the 1-MNQ candidates alone are ranked. No unrelated companion
export discovery is permitted by the browser check. Both temporary servers
(the affected-suite browser checks and final browser check) shut down normally.

The final browser library is
`final-browser/test_campaign_configuration_re0` under the evidence root. Its
funded campaign is `39185f9cde014aab81874c89613cd837`, evaluation campaign is
`f4da99241b70423794ebbf6bf519d676`, and constrained funded campaign is
`1349693c29774d9e8d42e13eea8c286b`. Use the same server command above and substitute
these IDs in `/#backtests/prop/campaign/<id>` to inspect each. Screenshots and
`browser-verification.json`, `evaluation-browser-verification.json` and
`constraint-browser-verification.json` record the final observed outputs.

`verified-independent-review.json` independently rechecks the final numerical
campaign library (`verified/campaign-library0`): evaluation campaign
`b65233cf640b477483232ef032ba3915`, analysis `f9f2f0cbd157474d86a99baa3edfcf25`;
funded campaign `197de62fea2643d6b624ad6e5eb5b1c2`, analysis
`54bc64bd31884316a72408cd2cfa7618`. All expected values above match again, 13
artifacts per phase verify, and the 92 original fixture files remain unchanged.
`delivery.json` records final changed-file hashes and the verification logs.


## Campaign source-type error correction — 2026-11-06

Submitting a demo backtest ID with **Optimization job** selected reproduced
the reported error. The original admission error conflated a missing job with an incomplete job.
`research_campaigns.py` now distinguishes a backtest ID used as a job, an unknown
job ID, and an existing incomplete job (including its actual saved status).
Source labels/help in the ordinary campaign form now change with the selected
type. Numerical calculations, candidate eligibility and existing reports are
unchanged. Completed individual trial reports remain usable as Backtest sources.

Reproduce from a saved IS report → Configure prop analysis → campaign form:
enter two valid backtest IDs and choose Optimization job for one of them. Save
and check must return 422 with **Set Saved source type to Backtest**, leaving Run
disabled. An unknown job ID must instead say **Optimization job not found in this
library**. Change the row back to Backtest and check/run normally; the existing
synthetic funded receipt values remain `[0,0,0,1500]`, and the evaluation durations
remain `[2,4,7,15]` at $70 each. Freeze/download/reopen and binding funded risk
constraints are exercised in the same normal-product browser journey.

Evidence is saved separately under `artifacts/campaign-source-type-20261106/`;
prior evidence is untouched. The browser fixture uses its own temporary server
and isolated dataset/report library, and stops that server on exit. The user's
existing server on port 8011 was read only and left running.

Validation: **1 browser end-to-end check passed** in 40.40 seconds (one existing
Starlette/httpx deprecation warning). `browser.log` and `browser.xml` retain the
result; `browser/test_campaign_configuration_re0/source-type-rejection.json`
and `.png` retain the actual 422 message, followed by successful saved results,
freezes and downloads in the same library. JavaScript syntax and diff checks pass.

## Campaign saved-source dropdown — 2026-11-06

The existing campaign configuration now selects saved reports/jobs through a
search field and dropdown. The opened backtest is preselected; added rows require
an explicit selection. Each choice shows strategy, parameters, dataset, date,
status and ID; full parameters, IS dates and a source link appear underneath.
Switching source type clears the selection. Search preserves an existing choice
and supports natural strategy names, parameter names, dataset, date and ID.
Pagination uses 50 matches and **Load more sources**.

The metadata-only endpoint `/api/research-campaigns/sources` queries the existing
catalogue. OOS/undeclared reports are excluded; incomplete IS jobs appear disabled.
The earlier manually typed wrong-type error can no longer be produced through
this UI, but direct API admission checks remain. Numerical calculation identity,
source compatibility checks and durable report storage retain their behavior.

New evidence root: `artifacts/campaign-source-dropdown-20261106/`. The stable run
passed **23 tests in 124.80 seconds**, with the existing Starlette/httpx deprecation
warning; `verified.log` and `verified.xml` contain actual output. This scope covers
the picker API, campaign regressions and two normal-product browser journeys.
An earlier run (`check-01.log`) had two passes and one failure in a test helper
that assumed an in-process client; it now reads the ordinary saved report API.
Both runs and all earlier campaign evidence are preserved.

- `verified/test_campaign_configuration_re0/` contains selected-backtest and
  empty-job screenshots, budget rejection, both phase reports, freezes and CSV,
  JSON and ZIP downloads. Source IDs are `1492b45ad3ec43b4901a9be7fbe54506` and
  `c15764b0fced467f8bbc7aead4c735ac`; funded campaign
  `06d6cd0968724de3a69658275e499bf5` has receipts `[0,0,0,1500]` and $1,500 pending
  for the winner. Reopen performs no POST or recalculation.
- `verified/test_campaign_optimization_job0/` contains the selected-job screenshot
  and normal downloads for campaign `177c7b26215b4e679254507a26964026`. Saved jobs
  `b227c3b60fab4ac9bbae76950d5e8b79` and `6d95c826f0a448bea94a91cec4cd7932`
  contribute VWAP and Consecutive Green Hold trials at 1/3 MNQ: four candidates.
  This separate labelled synthetic adverse-risk example pays zero for all four.
- The picker API test verifies 54 matches as pages of 50 and 4, search and stable
  membership, disabled incomplete jobs, excluded OOS/undeclared records and no
  outcome fields. Report readers, calculation expansion and prop summary access
  are forbidden during this test. Test-only catalogue rows are removed afterward.
- `independent-review.json` uses only the standard library to verify actual saved
  reports from `verified/campaign-library1`: evaluation costs $70 for durations
  `[2,4,7,15]` calendar days, funded receipts `[0,0,0,1500]`, frontier/ranking,
  freeze hashes and 13 artifacts per phase. All 92 prior fixture files are unchanged.

To inspect/reproduce using the saved backtest browser library, start a temporary
server on an unused port (restart an existing application server before expecting
the new endpoint):

```bash
cd /Users/yx/alphaquest-research-engine-2
ALPHAQUEST_DATA_DIR="$PWD/artifacts/campaign-source-dropdown-20261106/verified/test_campaign_configuration_re0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8012
```

1. Open `http://127.0.0.1:8012/#backtests/report/1492b45ad3ec43b4901a9be7fbe54506`,
   then **Configure prop analysis → Configure a phase campaign**. The first
   Backtest dropdown must already select this report.
2. **Add saved source**, search `consecutive green` and select the other report.
   Its full parameters include `green_bar_count=2`. Search an unmatched string:
   the message says no matches, while the selected report remains selected.
3. Leave sizes `1,3` on both sources. Maximum count **3** must reject four
   candidates; **4** must pass. One backtest with two sizes counts as two, so a
   budget of three correctly passes that smaller declaration.
4. Choose Funded / Apex 50K EOD, 8 paths, seed 42, block 1, start 2026-01-05,
   coverage end 2037-01-01, horizon 14, receipt delay 4 and breach maximum 1.
   Save/check, run, inspect all four receipt values above, freeze a feasible
   candidate, download results and reopen its campaign URL without recalculation.
5. In a fresh configuration, switching a source to Optimization job shows the
   empty-job message in this backtest-only library. Selection is required before
   checking. To inspect real job choices, stop with **Ctrl-C** and restart the
   same command using `verified/test_campaign_optimization_job0` as the data
   directory. Open report `1c79bc372367492080451b947bc548a7`, configure a campaign,
   add a source, and choose the two jobs above from Optimization job dropdowns.
   Repeat the funded settings with the saved source's IS start 2026-01-05 and
   end 2026-01-07; expect four candidates and zero receipts.

Stop the inspection server with **Ctrl-C**. Automated browser fixtures stopped
their own servers; no persistent server was started or existing server stopped
for this increment. To rerun automated checks, use a new artifact path:

```bash
.venv/bin/python -m pytest -q tests/test_campaign_source_picker.py \
  tests/test_research_campaigns.py tests/test_research_campaigns_browser.py \
  --basetemp artifacts/campaign-dropdown-NEW
.venv/bin/python tests/review_research_campaigns.py \
  --library artifacts/campaign-dropdown-NEW/campaign-library1 \
  --output artifacts/campaign-dropdown-NEW/independent-review.json
```

## Phase campaign portal and frozen OOS — 2026-11-06

The existing saved backtest → prop configuration → source checks → local worker
→ durable report workflow now has primary **Create Evaluation campaign** and
**Create Funded campaign** actions. Saved-trial/job selection and AnalysisStore
are reused. No second application, calculation engine, database or report store
was introduced. Legacy annualized joint sizing remains accessible and labelled;
its historical results and download meanings are preserved.

The phase screen displays the requested acquisition or payout/risk metrics,
conditional Monte Carlo error and censoring, strategy/size/profile filters,
original source links and CSV/JSON/ZIP. Evaluation plots all resolved points,
marks the saved Pareto frontier and shows marginal acceleration costs without
choosing a winner. Funded provides the saved ranking and all-start payout
histograms, including zero receipts. Filtering/inspection does not select/freeze.
Candidate names and IS decisions persist. Frozen OOS uses the ordinary manual OOS
backtest path, then runs phase metrics with both selectors bypassed. It cannot
change the immutable IS package or return a new OOS winner.

### Actual saved product outputs and independent expected values

Evidence root: `artifacts/phase-portal-20261106/`. These are labelled **SYNTHETIC**
normal datasets/backtests, not provider or future-performance observations.
`portal-release/` is the final UI capture; `browser-final/` also preserves the
cross-strategy/job, source-picker and constraint demonstrations. Earlier evidence
roots and the initial unsuccessful run are retained.

| Final portal library | Campaign | IS phase report | OOS assessment report |
| --- | --- | --- | --- |
| `portal-release/test_campaign_portal_frozen_oo0` | `447c08eeb4ae44f88a32a8fb0f8a43bc` (Evaluation) | `76ee8682d1bb46fe975074e0ed7da97f` | `421d64d7c8b94af59f0e7aaf4bfeabc6` |
| `portal-release/test_campaign_portal_frozen_oo1` | `71c461e3389c4798bb5f6eb8cff6f369` (Funded) | `567453cb16054cf28bb39e99fb3a9d11` | `9ff3053e07a3494a9711be944b4b7486` |

Both sources come from the same 24-session synthetic dataset and cost protocol:
IS January 5–14, OOS January 15–February 5, 2026. Green Hold parameters differ
only by green-bar count 1/2, producing constant $300/$100 per MNQ per session,
respectively. Captured source commissions/slippage are zero. Source A/B IDs:

- Evaluation: `ef384cadc0c84bef9e93de98b6f1e928` /
  `b8e7e0668a794d3f8b1e9e990f9d09f7`.
- Funded: `dfd5152d2dec47a8b27da3318855e5e0` /
  `42883bbb6765461aab330f541eecc789`.

Independent expectations, derived from the captured trades and local account
scenario rather than importing production functions:

- Evaluation A/B × sizes 3/10 gives acquisition pairs `(USD, calendar days)`
  `(70,7)`, `(70,2)`, `(70,15)`, `(70,4)`. Each attempt passes; $30 purchase +
  $40 activation = $70. Sessions required are `ceil(3000 / daily scaled net)`;
  the Monday start, one activation session and next-session readiness give the
  stated calendar days. Mean/median/P90 agree, pass and day-30/day-60 funding
  probabilities are 1, throughput is `30/days`, and no chain is censored.
  The IS frontier contains only A at 10 MNQ; there is no automatic winner.
  Freeze **evaluation frozen choice 1**; OOS uses 10 MNQ and gives $70/2 days,
  with no OOS frontier or winner.
- Funded A/B × sizes 1/3 gives expected received cash `[0,1500,0,0]` over the
  14-calendar-day scenario `[2026-01-05,2026-01-19)`, with four-day modeled receipt
  delay. Only A at 3 MNQ earns $900/session and reaches payout availability.
  Requests/deductions on January 9/16 are $1,500 each; modeled receipts are
  January 13/20. Exactly $1,500 is received in-horizon, $1,500 remains pending,
  and $3,000 was deducted from the account. Median/P10/P90 cash all equal $1,500,
  first-receipt probability is 1 and conditional first-receipt time is eight
  calendar days. Other rows receive zero. Breach probability is zero and horizon
  survival is 1. Freeze the explicitly named A size-1/size-3 family; OOS retains
  those sizes and returns `[0,1500]`, pending `[0,1500]`, and no ranking/winner.
  Open lifetimes are censored while these horizon receipts are complete.

`independent-release.json` is produced by `tests/review_campaign_portal.py`, which
imports only the standard library. It rederives these observations from captured
trades, checks all 50 report/ZIP artifacts across both IS/OOS pairs, CSV row counts,
rule-source/package hashes and zero POSTs on reload. `portal-evidence.json` in
each library records exact source/report IDs and frozen download hashes. Actual
JSON/CSV/ZIP downloads and screenshots are beside it; the complete reports stay
in that library's normal `prop_analyses/<id>/` directories.

A second normal-product four-point Evaluation report is captured under
`portal-release/test_pareto_plot_table_and_mar0/`. Its source-based scenario gives
`(70,4)`, `(90,9)`, `(100,3)`, `(140,2)`: three frontier points, one dominated
point, and adjacent acceleration costs $30/day and $40/day. The browser checks
that chart marker IDs exactly equal saved frontier membership, marginal table
values agree, and size filtering hides points without recomputing membership.
`pareto-and-marginal.png`, `mobile-pareto.png` and `chart-verification.json` retain
that evidence. Different per-candidate fee scenarios are declared through the
existing phase API; the campaign form uses one common profile/fee scenario.

### Reopen and reproduce Evaluation through the portal

Run from the repository root (port 8017 must be free):

```bash
ALPHAQUEST_DATA_DIR="$PWD/artifacts/phase-portal-20261106/portal-release/test_campaign_portal_frozen_oo0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory \
  --host 127.0.0.1 --port 8017
```

1. Open `http://127.0.0.1:8017/#backtests/prop/campaign/447c08eeb4ae44f88a32a8fb0f8a43bc`.
   Expect **Frozen IS selection**, four candidates, all costs $70, funding means
   2/4/7/15 days, one orange frontier ring and the persisted candidate name.
   Inspect metric cards, source/rule details and filter to size 3: two rows and
   two plotted points remain; the hidden 10-MNQ frontier does not get recomputed.
2. Open the saved OOS link. Expect **Frozen OOS assessment**, the chosen 10 MNQ,
   $70/2 days, no freeze control and no ranking/frontier winner. Reload both
   screens: saved files and frozen choices remain unchanged; no POST is sent.
3. To create a new campaign, open
   `http://127.0.0.1:8017/#backtests/report/ef384cadc0c84bef9e93de98b6f1e928` →
   **Configure prop analysis → Create Evaluation campaign**. Set sizes `3,10`;
   **Add saved source**, leave type **Backtest**, search/select source B above
   and give it sizes `3,10`. Use Apex EOD, $30/$40 fees, 8 paths, 8 acquisition
   chains, block 1, seeds 42/45, scenario start January 5, 2026, and the saved IS
   window. Counts of 8 are demonstration inputs, not precision qualification.
4. Set candidate budget 3 and **Save and check candidates**: expect rejection,
   with **Run campaign** disabled. Set budget 4 and recheck: four compatible
   definitions with strategy parameters, rules/version, sources and windows.
   **Run campaign** shows worker progress and completed counts, then the same
   independently expected acquisition results.
5. Check a resolved frontier point, name it and give a rationale; **Freeze
   selected candidates**. **Launch OOS with frozen settings** explicitly runs
   the existing OOS path and appends an assessment link. Parameters, size,
   account profile, costs, sampling, seeds and scenario calendar cannot be
   edited on this launch. Repeated manual launches append prior-access history;
   they never rerank IS or make accessed OOS untouched again.
6. Download campaign, source checks, CSV/JSON, analysis ZIP and frozen package.
   Stop this server with **Ctrl+C** before opening the Funded library below.

### Reopen and reproduce Funded through the portal

```bash
ALPHAQUEST_DATA_DIR="$PWD/artifacts/phase-portal-20261106/portal-release/test_campaign_portal_frozen_oo1" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory \
  --host 127.0.0.1 --port 8017
```

1. Open `http://127.0.0.1:8017/#backtests/prop/campaign/71c461e3389c4798bb5f6eb8cff6f369`.
   Expect four candidates, A at 3 MNQ ranked first with $1,500 received and
   $1,500 pending, three zero-cash rows, risk status and open-lifetime disclosure.
   Inspect distributions for both zero and positive receipt paths and filter
   by size; filtering never changes saved rank or frozen family membership.
2. Open the saved assessment link. Expect named size-1/size-3 configurations,
   `[0,1500]` received/pending cash and no OOS ranking or winner. The ordinary
   OOS backtest and its legacy automatic prop links remain separately available.
3. For a new run, open source A's normal report
   `http://127.0.0.1:8017/#backtests/report/dfd5152d2dec47a8b27da3318855e5e0` →
   **Configure prop analysis → Create Funded campaign**. Add source B above,
   both at sizes `1,3`; use budget 4, 8 paths, seed 42, block 1, horizon 14 days,
   receipt delay 4, start January 5, 2026, and the saved IS window. Check → Run
   → inspect cash/risk ranking → name/freeze the desired feasible configuration
   or predeclared family → manually launch frozen OOS → download both reports.
   No evaluation price, pass probability, acquisition time or annualized joint
   score is an input to this funded selection.
4. Stop the server with **Ctrl+C**. Test fixtures use temporary servers and
   enforce shutdown; no persistent server is required for this delivery.

### Boundaries, error states and limits

- `test_campaign_censored_error_a0/` captures zero-observed-pass/unresolved
  Evaluation (no finite acquisition mean/plot and freeze disabled), a deliberately
  failed worker, retained failure/retry and live/completed candidate counts.
  Resource/candidate caps reject instead of silently reducing the requested work.
- `browser-final/test_campaign_optimization_job0/` captures two completed saved
  jobs from VWAP and Green Hold in one campaign: all four source/size combinations
  remain present, both job origins are retained, and expected receipts are all
  zero for that scenario. The source-picker demonstration includes empty and
  no-match states, wrong-type/incomplete jobs, budget rejection and explicit
  infeasible rows without dropping them from the report.
- Backend checks reject OOS as an IS candidate, changed numerical implementations,
  and overrides to frozen size/profile/horizon/strategy/settings. Both selectors
  are poisoned during OOS tests; assessments still complete. Repeated requests
  reuse IDs; fresh manual requests append. IS/frozen bytes remain unchanged and
  referenced sources/reports are deletion protected.
- Launch supports captured native risk. A separate measured-excursion source
  needs an independently reconciled OOS export and currently rejects this launch
  before OOS execution. No measured MAE/MFE or cost settlement is fabricated.
- Evaluation currently admits Apex EOD; Funded admits local Apex EOD/LucidFlex.
  One campaign uses one common profile. The target weekday/closure calendar,
  prices, receipt delay and stationary resampling are declared local assumptions,
  not newly verified provider/exchange/settlement forecasts. OOS estimates use the
  frozen scenario cohort/calendar on OOS observations, not retrospective bank cash.
- New parameter grids still run through normal backtests first. Automatic grid
  generation, adaptive refinement and simultaneous/precision-certified frontier
  or optimum claims remain outside this increment. Conditional Monte Carlo error
  does not establish future uncertainty or provider/numerical parity.

### Automated reproduction

Use fresh, unused `NEW` paths; pytest resets its `--basetemp`. Preserve all saved
evidence roots above. From the repository root:

```bash
.venv/bin/python -m pytest -q tests/test_campaign_assessments.py \
  tests/test_research_campaigns.py tests/test_campaign_source_picker.py \
  tests/test_evaluation_optimization.py tests/test_funded_optimization.py \
  --basetemp /tmp/aq-phase-backend-NEW
.venv/bin/python -m pytest -q tests/test_campaign_portal_browser.py \
  tests/test_research_campaigns_browser.py --basetemp /tmp/aq-phase-browser-NEW
.venv/bin/python tests/review_campaign_portal.py \
  --browser-root artifacts/phase-portal-20261106/portal-release \
  --output /tmp/aq-phase-independent-NEW.json
```

Expected: both campaign types complete the normal saved-report journey and manual
OOS, all source/job membership is visible, rejected/empty/censored/failed states
remain explicit, and the independent audit reproduces both IS/OOS metric sets
and verifies 50 captured artifacts. The actual broader regression commands,
counts, failure reconciliation and preservation result are recorded below and in
this evidence root's validation summary.

### Final validation and preservation

- `regression-final.log`: **207 passed**, covering campaign/assessment/source
  picker APIs, both phase optimizers/components, legacy joint sizing, dated
  phases/cash, prop APIs, research, strategies and optimization.
- `kernel-source-regression.log`: **50 passed**, covering phase admission,
  native/compiled kernels, commissions and source/risk workflows.
- `browser-final.log`: **6 passed** (both campaign types, cross-strategy saved
  jobs, Pareto relationships, constraints, failure/retry and censoring).
  `portal-release.log`: **4 passed** after the candidate-name/download layout
  correction, with final IS/OOS screenshots and exact downloaded files.
  `rule-display.log`: **1 passed**, independently checking pre-run Evaluation,
  Apex funded and Lucid funded rule disclosures. Together these cover seven
  distinct campaign browser cases; repeated runs are not counted twice.
- `portal-regression.log`: **62 passed, 1 failed**. The existing percentage-split
  manual-OOS browser test still expected $352,880. The unchanged, pre-existing
  `test_automatic_prop.expected_cash` oracle already expects $452,880. Independent
  ledger arithmetic gives `(13,000 + 10,000) * 20 - 40 * (49+129) = 452,880`.
  `legacy-oracle-reconciliation.json` records that reconciliation and unchanged
  HEAD hashes of the legacy calculator, selector, account kernels and component
  wrappers. Only the stale browser literals/evidence expectations were corrected.
  `manual-oos-regression.log`: **2 passed** on the complete ordinary IS/grid/OOS
  workflows after that correction. Thus all 63 distinct existing browser cases
  are covered by passing results across the broad run and targeted rerun; the
  original broad run is not represented as wholly green.
- `browser-1.log` retains the earlier two ordinary-backtest publication failures
  encountered during live Python edits. Stable campaign runs above passed. The
  full repository suite was not run. The existing Starlette/httpx deprecation
  warning remains; no dependency migration was included.
- Independent standard-library reviews passed: `independent-release.json`
  verifies 50 IS/OOS artifacts, and `independent-campaign-regression.json`
  verifies the two campaign reports and 92 unchanged pre-existing fixture files.
  The reviewer now uses the runtime's ASCII-escaped canonical JSON convention,
  which matters for Unicode candidate names and captured rule source text.
- `preservation-before.json` / `preservation-after.json`: **70,083 existing data
  and prior-artifact files unchanged** across stable final validation. SQLite
  catalogues and this new evidence root are excluded from that global file
  comparison; isolated workflow checks separately verify source/report/freeze
  bytes. Original user datasets/backtests/results were not used as test fixtures.
- JavaScript syntax checks, `git diff --check`, and 174 local documentation
  links/anchors passed. All owned temporary servers stopped. No persistent
  server was started, no Windows VM/other application was controlled, and no
  changes were pushed to GitHub.

`artifacts/phase-portal-20261106/validation_summary.json` records the exact scope,
counts, reconciliation, limits and evidence filenames. This is 257 backend cases
and 70 distinct browser cases, with the rerun qualification stated above; it is
not a claim of full P1–P5 certification, provider parity or a green full baseline.


## Final architecture cleanup — 2026-11-06

Baseline `445c14030c0e060d5844cfaa3bcf6564dd13a981` plus the saved local cleanup
diff; no GitHub push. Evidence root:
`artifacts/phase-architecture-cleanup-20261106/`. All sources here are explicitly
SYNTHETIC; fee overrides $30/$40 are test scenarios, not provider prices.

### Implementation and retained ownership

- Shared lazy `prop/phase_dispatch.py` now resolves the requested backend for
  HTTP, campaigns and AnalysisStore. Unknown modes/phases reject before dispatch;
  no fallback into another objective. Simulation, numerical metrics, selection
  and phase-specific artifact formats remain owned by their existing phase modules.
- Strict grid field `automatic_prop` defaults true. False saves normal backtests
  without automatic legacy Apex/Lucid reports or their calculation-cache snapshot.
  The shared form exposes the choice, including a one-combination batch path.
  The saved profile/metric columns and existing trial key separate both modes.
  Manual configuration and independent campaigns still use those saved sources.
- Removed unused `prepare` from the HTTP imports and `csv`/`io` from the store.
  No kernel, phase estimator, sampling law, model/rule version, numeric identity,
  legacy score, report schema or historical reader was rewritten. No production
  module retired: notebook analysis/model/settings remain demo/parity dependencies.
- README, architecture, phase plan, model specification, research/grid workflows,
  portfolio status and AGENTS now distinguish implemented saved-candidate research
  from generated/adaptive search, statistical certification and future portfolios.
  Original ADRs, numerical findings and evidence remain. See the
  [module/dependency inventory](architecture.md#final-module-ownership-and-retention).

### Saved normal-product demonstration

Stable-code browser run: `stable-focused/`. Each case used a normal uploaded
SYNTHETIC dataset, reviewed IS/OOS declaration and the existing grid form; no
report/oracle was injected into runtime. The grid varies Green bar count 1–2,
holds one minute, one NQ contract, zero commission/slippage, UTC source, point
value 20, IS 2026-01-05 through 2026-01-14, reserved OOS 2026-01-15 through
2026-02-05. Each IS source has eight trades earning $3,000 or $1,000 per session.
Automatic reports are explicitly off; the ordinary report/configuration remains
usable. The two-trial grids took about 0.159 s and 0.101 s on this small fixture;
these are software timings, not representative throughput or a general speedup.

| Case | Saved grid / campaign / analysis |
| --- | --- |
| Evaluation | `2965dda7f17a4c3aacbe3a93229e6c4c` / `172f63012e0a4fc095d4f77302daf566` / `f075e876e0ae4006b3a1dc79202d7af5` |
| Funded | `0be0ce87a38b4660938bbc411a5ec35c` / `b7a2b265facd4f5da9706247c2340963` / `fefe4be21e314cf29c6aa6765edd6366` |

Open a grid's saved source report → Configure prop analysis → Create the relevant
phase campaign → select the complete saved job, explicit sizes and sampling →
Check → Run. Budget 3 rejects the four candidates and keeps Run disabled; budget
4 admits all. Evaluation uses 3/10 MNQ; Funded uses 1/3 MNQ. Both use 8 explicitly
requested paths, block 1, Monday 2026-01-05 start. Evaluation uses 8 acquisition
chains, $30 purchase/$40 activation and one activation session; Funded uses H=14
calendar days and a four-day modeled receipt delay. Synthetic paths are constant,
so these small ensembles give exact deterministic expectations, not useful
statistical precision for market research.

Independent expected/actual observations, derived from captured trade CSVs:

| Source / size | Evaluation cost and readiness | Funded cash by exclusive Jan 19 cutoff |
| --- | --- | --- |
| $300 per MNQ-session, 3 MNQ | $70, 7 calendar days | $1,500 at 3 MNQ; another $1,500 pending |
| $300 per MNQ-session, 10 MNQ | $70, 2 calendar days; only frontier point | Size 10 is not in this Funded campaign |
| $100 per MNQ-session, 3 MNQ | $70, 15 calendar days | $0 |
| $100 per MNQ-session, 10 MNQ | $70, 4 calendar days | Size 10 is not in this Funded campaign |
| Either source, 1 MNQ | Not in this Evaluation campaign | $0 |

Arithmetic: convert NQ P&L to per-MNQ by dividing by 10, multiply by the requested
whole size, then `ceil(3000/daily_profit)` passing sessions. A single purchase
plus activation costs $30+$40=$70. Add the saved activation session and next-open
readiness on the declared weekday calendar; costs tie, so the two-day point
strictly dominates the others. For the $900/day Funded path, the native scenario
qualifies $1,500 requests on Jan 9 and Jan 16; fixed delay yields Jan 13 and Jan 20
receipts. Only Jan 13 is before Jan 19. Gross deductions are $3,000; cash received
and pending are $1,500 each. No account equity, acquisition fee or double trading
cost enters this objective.

Each case saves `grid.json`, `workflow.json`, `source_checks.json`, results JSON/CSV,
`analysis.zip`, source-check/budget-rejection/results screenshots, and the normal
`backtest_runs`/`prop_analyses` library. Reopen emits no POST and returns identical
saved results. `stable-independent-audit.json` independently checks source-derived
cash/readiness, frontier/ranking, all report artifact hashes and ZIP bytes using
only standard-library Decimal/date code. The additional one-combination browser
case opens its ordinary report with exactly 26.00 CU net. Serial/parallel API tests
verify no automatic computation, strict boolean rejection, same-mode reuse and
zero cross-mode reuse; default automatic requests remain active.

### Reproduce and inspect manually

Use a **new** path for each pytest run; pytest clears its basetemp. From repo root:

```sh
PHASE_RECHECK="artifacts/phase-cleanup-recheck-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$PHASE_RECHECK"
.venv/bin/python -m pytest -q tests/test_phase_architecture.py \
  tests/test_phase_architecture_browser.py tests/test_backtest_preparation_browser.py \
  --basetemp "$PHASE_RECHECK/browser" --junitxml "$PHASE_RECHECK/browser.xml"
.venv/bin/python tests/review_phase_architecture.py \
  --browser-root "$PHASE_RECHECK/browser" --output "$PHASE_RECHECK/independent.json"
```

Expected: all eight checks pass; two complete source-derived campaign audits.
To reopen the saved Evaluation case without replay, start an owned temporary server:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/phase-architecture-cleanup-20261106/stable-focused/test_opt_out_grid_to_independe0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8016
```

Open `http://127.0.0.1:8016/#backtests/report/d2371d61f0704e91aa9ff50663df1899`
and inspect Configure prop analysis/source checks. Reopen the saved campaign at
`http://127.0.0.1:8016/#backtests/prop/campaign/172f63012e0a4fc095d4f77302daf566`;
expect four rows, all $70, readiness 2/4/7/15, a single frontier point and no
Evaluation winner. Download results JSON/CSV, source checks and ZIP. Stop with
Ctrl-C. For Funded use the sibling `test_opt_out_grid_to_independe1` data directory,
then campaign `b7a2b265facd4f5da9706247c2340963`; expect cash [0,0,0,1500] and explicit
pending/deduction fields. The ordinary `analysis.zip` and captured inputs remain
the authoritative outputs, without a second campaign result store.

The full suite's existing campaign portal cases cover named freeze → manual OOS
backtest → assessment-only report → repeated reopening/download, including IS
package hash immutability, no OOS ranking, prior access, model mismatch rejection,
unsupported sources, zero/censored outcomes and failed worker recovery. Their
fresh evidence is retained under `final-suite/`; qualification status below must
be read with the actual suite result.

### Qualification status and limitations

Stable focused checks: 8 passed (22.23 s); original phase regression pass: 44
passed (219.24 s). The first broad run was deliberately interrupted after 171
passes and one preparation-browser failure. That failure also occurred on the
untouched baseline (33.38 s): its symbol-less synthetic source correctly triggered
the existing calendar guard and disabled Start. The fixture now declares synthetic
NQ; all progress stages, counts and zero-trade/10,000-equity assertions are retained.
`baseline-preparation.log`, `preparation-investigation.log`, `full-suite.log` and
`stable-focused.log` preserve that investigation; no assertion was weakened.

The complete run subsequently exposed three stale deletion-browser assertions;
all three reproduce unchanged on baseline `445c140` in `baseline-deletion.log`.
Two expected pre-campaign rejection text while the backend correctly returned
campaign/running-analysis deletion protection. Their assertions now require the
current complete rejection reason and retain the preservation/deletion checks.
The report-link case previously used a one-session source with an incompatible
prop result, for which the UI correctly exposes no completed-report link. It now
creates a normal multi-session synthetic source, requires a completed prop report,
and additionally compares saved report JSON bytes after source deletion. All seven
checks in both deletion-browser modules pass (`deletion-corrected.xml`, 49.42 s).
No production deletion guard, incompatible-source rule or numerical test changed.

The full run also exposed the VWAP benchmark fixture's `SYNTHETIC` symbol,
which rejects with the same reviewed-calendar error on untouched baseline
(`baseline-benchmark.log`). That one case now explicitly uploads synthetic NQ;
Use EOD Flat, actual-equity alignment, all four observed bars, close values and
188 CU holding P&L assertions remain unchanged. Other benchmark fixtures retain
their generic symbol. All 23 benchmark checks pass (`benchmark-corrected.xml`,
5.29 s). No calendar, execution or benchmark formula changed.

Independent mathematical audits already completed:

- `independent-evaluation.json`: captured constant-day sources independently
  produce (cost, days) = (70,4), (90,9), (100,3), (140,2); frontier excludes only
  (90,9), adjacent acceleration costs are (100−70)/(4−3)=$30/day and
  (140−100)/(3−2)=$40/day. All 13 saved report/ZIP artifact checks pass.
- `independent-funded.json`: candidate all-start receipt means [0,0,0,1500], winning pending
  $1,500/gross deduction $3,000, native account equity and received-path events
  reconcile; all 13 report/ZIP artifact checks pass.
- `stable-independent-complete.json`: new opt-out grid workflows plus receipt
  boundaries. Jan 13 cash with H=8 (cutoff Jan 13) is $0 received/$1,500 pending;
  H=9 (cutoff Jan 14) is $1,500 received/$0 pending. Standard-library date/Decimal
  calculations consume event records, not a production selection helper.
- `final-independent-portal.json`: both normal browser freeze/manual OOS
  workflows passed independent source-derived arithmetic and 50 report/ZIP
  artifact checks, with frozen package/rule-source hashes and no reopen POST.
- `final-independent-cash.json`: all 154 ledger rows conserve exact cash and
  all monthly spending/reservations stay within cap; 115 ZIP artifact hashes
  verified. Paid purchases $30+$30 plus $40 activation consume the $100 cap;
  the receipt case has $1,500 modeled receipts − $90 evaluations − $80 activations
  = $1,330 net. Pending receipts, month resets and expiry remain separate events.
- `final-independent-grid.json`: fresh stable-suite opt-out grids feed both phase
  campaigns with unchanged source-derived expected values, 26 report/ZIP artifact
  checks and no reopen POST. Stored tiny-grid times were about 0.372 s / 0.178 s
  while two qualification groups ran; these are not controlled throughput estimates.

| Fresh full-suite portal case | Campaign | IS analysis | Frozen OOS assessment |
| --- | --- | --- | --- |
| `test_campaign_portal_frozen_oo0` (Evaluation) | `e559c78629514fc58e207ac0cdff53ce` | `26a4c9a06b2844f2983701a435f54184` | `9153463b0b7f46d6b757ab32780510d1` |
| `test_campaign_portal_frozen_oo1` (Funded) | `72da9871b06c492881d154a5cc924b5b` | `74f6cde20b764423a09c3c69d84a59a9` | `ac4116bef9b348bfa0a5cf23311566b1` |

For either fresh portal library, use the temporary-server command above with
`ALPHAQUEST_DATA_DIR` set to `.../final-suite/<case>`. Open
`/#backtests/prop/campaign/<campaign>` to inspect named frozen IS choices and
assessment links, or `/#backtests/prop/job/<assessment>` for saved OOS metrics.
Evaluation's frozen OOS result is $70 / 2 days; Funded's two frozen size results
are $0 and $1,500 received, with the winning $1,500 still pending separately.
Both assessment reports have no ranking/frontier and no winner. Stop the server
with Ctrl-C after inspection.

Reproduce the full regression suite and mathematical audits from fresh outputs
(reuse the new `PHASE_RECHECK` directory declared above):

```sh
.venv/bin/python -m pytest -q --basetemp "$PHASE_RECHECK/full" --junitxml "$PHASE_RECHECK/full.xml"
.venv/bin/python tests/review_evaluation_optimizer.py \
  --library "$PHASE_RECHECK/full/evaluation-search-library0" --output "$PHASE_RECHECK/evaluation-audit.json"
.venv/bin/python tests/review_funded_optimizer.py \
  --library "$PHASE_RECHECK/full/funded-search-library0" --output "$PHASE_RECHECK/funded-audit.json"
.venv/bin/python tests/review_phase_architecture.py \
  --browser-root "$PHASE_RECHECK/full" --funded-library "$PHASE_RECHECK/full/funded-search-library0" \
  --output "$PHASE_RECHECK/campaign-boundary-audit.json"
.venv/bin/python tests/review_prop_cash_oracles.py \
  --directory "$PHASE_RECHECK/full/test_budget_configuration_cash0" --output "$PHASE_RECHECK/cash-audit.json"
```

`final-suite.log` is the second **diagnostic**, interrupted after 809 passes and
four reproduced baseline assertion/fixture failures (38 min 26.86 s). Its
completed product reports remain valid inspectable evidence; it is not a green
full-suite claim. The fresh complete qualification is split into disjoint A–M
(627 checks) and N–Z (586 checks) groups. `stable-suite-manifest.json` records all
1,213 collected node IDs, file membership and exact test/production hashes;
`summarize_qualification.py` rejects omissions, duplicates, unaccounted failures,
skips or production/source drift. A changed test module must have a complete
replacement run with its own source hash; raw failed broad results stay recorded.
Standard path counts and worker limits are unchanged.

The A–M qualification group completed with **627 passed, no failures/errors/skips**
in 2,082.77 s (34 min 42 s), including all five corrected baseline cases. Its XML
matches every expected A–M node ID exactly once. One existing Starlette/httpx
compatibility deprecation warning is recorded; no counts were reduced.

Final N–Z result: **584 passed, two failures, no errors/skips** in 2,219.55 s
(36 min 59 s), with 24 existing dependency/notebook warnings. Both failures were
in `test_strategy_dataset_browser.py`: hierarchy separation and decimal spelling
requested default VWAP calendar flattening on generic `SYNTHETIC` sources.
The untouched baseline's decimal case reproduces the same 422 calendar rejection
in `baseline-strategy-decimals.log` (0.99 s); the hierarchy failure reaches that
same guard after ordinary setup. Its slow archived Python-only setup was stopped
rather than treated as completed baseline evidence.

Those two cases now upload explicitly labeled synthetic NQ data through the normal
dataset API. Default EOD flattening and every original grouping, OOS, deletion,
parameter precision and separation assertion remain. No shared fixture defaults or
production code changed. The **entire nine-test module passed** in 281.09 s
(4 min 41 s), recorded in `strategy-source-corrected.xml/.log` and its source-hash
manifest. The other seven cases in that module were rechecked too.

`qualification.json` records the exact scope: the broad snapshot has **1,211 passes
and two fixture failures**, followed by the complete **9/9 module recheck**. Final
source-version coverage is 627 A–M cases + 577 unchanged N–Z cases + all 9 corrected
module cases = **1,213 distinct collected cases**, with no omission or duplicate.
Every current case has a passing observation and production hashes are unchanged.
**No fresh, entirely green full-suite invocation was run after the last fixture
correction.** Do not relabel the raw N–Z snapshot or a focused pass as a green
baseline. Its failures/logs remain inspectable.

Final preservation verification: **87,618 earlier data/evidence files unchanged,
none missing**. `preservation-hash-check.json` contains the full SHA-256 comparison;
`qualification.json` confirms no subsequent size/mtime/ctime changes to those
verified files. Final Evaluation/Funded implementation identities exactly match
`phase-identities-before.json` (`phase-identities-after.json`). All 13 original ADR
rows, the entire prior review log and the pinned notebook checksum are preserved
(`identity-and-history-audit.json`). No calculation kernel or model/rule version
changed; no production module retired. There is no unresolved implementation
blocker from this cleanup; fresh-full-baseline status and the research/provider
limits below remain explicit.

The final independent audits are `qualified-independent-evaluation.json`,
`qualified-independent-funded.json`, `qualified-independent-portal.json`,
`qualified-independent-grid-and-cutoffs.json`, and `final-independent-cash.json`.
They inspect normal completed source/report/ZIP outputs from the qualification
libraries without importing a production calculator. Source-derived frontiers,
$30/$40 marginal acceleration, horizon cash/ranking, exclusive receipt cutoffs,
fee conservation and IS/frozen-OOS package identity all match their independent
expectations. Existing API/UI, strategy/grid, Apex/Lucid, legacy joint, risk/cost,
source reconciliation, persistence/deletion and historical reopening checks are
covered by the raw broad XML and the explicitly recorded module recheck.

Reproduce the evidence summary (read-only checks; choose a new output filename):

```sh
.venv/bin/python artifacts/phase-architecture-cleanup-20261106/summarize_qualification.py \
  artifacts/phase-architecture-cleanup-20261106/qualification-recheck-NEW.json
```

Final documentation checks cover all nine requested files: **194 local file and
heading links valid**, original ADR rows/prior review preserved, and
`git diff --check` clean (`documentation-links-final.json`).

The source/journey/download commands above reproduce new runs through the normal
product. All owned temporary servers and browsers stopped; no persistent server
or GitHub push was started.

Known research/provider limits remain: Apex-only dated Evaluation; stationary
empirical IID acquisition with unlimited capital; user-declared weekday calendars;
no verified holidays/early-close/settlement forecast; fixed civil-day receipt lag
and post-closure entitlement assumptions; native OHLC risk is not measured tick
MAE/MFE; no provider/Bridge numerical parity or live readiness claim. Point-estimate
frontiers/rankings and conditional Monte Carlo error are not certified future
optima. New-grid generation, adaptive confirmation and full simultaneous inference
remain pending. Original P2/P4 and broader certification exits are not marked
complete; the saved-candidate portal and freeze/OOS product path is implemented.

No portfolio optimizer is added. Next is portfolio milestone 3's bounded fixed-plan
separate-account comparison using frozen phase choices, synchronized sources,
exact fee/receipt timing, a zero-purchase baseline and the unchanged hard monthly
fee cap; then bounded separate-account search within milestone 3 and independent
portfolio-level OOS in milestone 5. Shared-account milestone 4 remains separate
and deferred pending combined exposure/risk evidence. Completed portfolio
milestones 1–2 remain preserved. All servers/browsers started by the
checks are fixture-owned and shut down; no persistent server was started.


## Automatic campaign calendar coverage — 2026-11-07

New Evaluation/Funded campaigns derive their generated weekday-calendar coverage
server-side when `coverage_end` is omitted. `research_campaigns.py` normalizes the
campaign before passing its concrete request to the unchanged phase backend.
The portal removes the manual coverage field and the hardcoded 2037 date,
submits only the scenario start, and shows the derived end after checking.

Evaluation adds the existing `SequentialRetry.max_calendar_days` (default 3,650)
to the latest scenario start. Funded adds its declared receipt horizon; pending
civil-day receipt dates do not extend the simulated trading horizon. Calendar
coverage does not change these limits, the IS window, samples, account rules,
selection, fee/cash accounting or numerical implementations. The exact resolved
calendar is saved in the existing manifest/report/request/ZIP paths. Existing
campaigns validate/run/freeze/OOS from their saved concrete requests. Explicit API
calendars keep their prior meaning and checks; other calendar version labels
require explicit coverage instead of automatic extrapolation.

### Actual saved journey and independent expectations

Evidence: `artifacts/campaign-calendar-auto-20261107/qualification/`.
Normal dataset upload → ordinary one-trial IS grid with automatic legacy reports
explicitly disabled → saved backtest report → Configure prop analysis → Create
Evaluation/Funded campaign → scenario start → Save/check → Run → durable results,
JSON/CSV/ZIP downloads and reopen. No new page/API/result store or injected report.
Sources are labeled **SYNTHETIC automatic calendar coverage**; $30/$40 evaluation/
activation overrides are software scenarios, not current provider prices.

The source stays on 2026-01-05…2026-01-14 IS, with reserved OOS through 2026-02-05.
It has eight flat one-NQ trades at $3,000 net each, zero commission/slippage and
captured native OHLC risk. The modeled target start is deliberately **2040-01-02**,
beyond the removed 2037 default. No future market bars are loaded or invented.
All paths are declared at 8, block 1 (and 8 Evaluation chains); the deterministic
constant-day example establishes arithmetic, not market precision/provider parity.

| Phase | Saved backtest | Campaign | Analysis | Derived coverage end |
| --- | --- | --- | --- | --- |
| Evaluation | `b2a9a508f2c54f40a955a9357fc42231` | `a6c5e2ff43b1484abaffc1b52e50750f` | `59b49ed4ca674d93ab9aa4af1e24fdfa` | `2049-12-30` |
| Funded | `ad451603dc5c451083ac0553cd4b855f` | `922618667eba4f18a8f66d0a6f221cef` | `2c2ebf4ab77a4c0394840acb19694827` | `2040-01-16` |

Evaluation uses 10 MNQ: $3,000 × 10/10 = $3,000 per sampled session, reaching the
local $3,000 target on Monday Jan 2, 2040. One activation session is Tuesday Jan 3;
the first usable session is Wednesday Jan 4. Independent expected acquisition is
**$30+$40=$70**, **2 calendar days**, with coverage **2049-12-30** from exact
3,650-day addition (leap days included). The 3,650-day chain limit is unchanged.

Funded uses 3 MNQ: $3,000 × 3/10 = $900 per session. Ten weekday sessions fall in
`[2040-01-02, 2040-01-16)`. Five-day qualification cycles request $1,500 on Jan 6
and Jan 13; the saved four-day lag yields Jan 10 and Jan 17 receipts. Independent
expected cash is **$1,500 received**, **$1,500 pending**, **$3,000 gross deductions**;
coverage is **2040-01-16**. An initial check at H=8 shows **2040-01-10**. Editing
H to 14 disables Run until rechecking and derives the new Jan 16 date.

Each browser case saves `workflow.json`, `campaign.json`, `source_checks.json`,
results JSON/CSV, `report.json`, `analysis.zip`, checked-form/results screenshots
and its ordinary dataset/backtest/AnalysisStore library. The browser request has
no `coverage_end`; the saved normalized request contains the exact required end.
Reload and repeated downloads emit no POST and return byte-identical data.
`independent-audit-final.json` uses standard-library CSV/Decimal/date arithmetic only,
checks both source-derived outcomes and 34 download/report/ZIP checks, and imports
no production calculator.

### Boundaries and reproducible verification

Date/API checks cover leap days, year boundaries, multiple starts (latest start
wins), custom Evaluation limits, fixed receipt-delay independence, explicit
calendar compatibility, equivalent explicit/automatic cache reuse, immutable
campaign-ID retries, saved concrete requests, invalid/missing dates, date overflow,
nonpositive/noninteger horizons and inadequate explicit coverage. Non-default
calendar versions without explicit coverage reject before a campaign is saved.
Normal source/research/profile validation and phase resource bounds still apply.

From the repository root, always choose a fresh pytest basetemp:

```sh
CALENDAR_RECHECK="artifacts/calendar-auto-recheck-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$CALENDAR_RECHECK"
.venv/bin/python -m pytest -q tests/test_campaign_calendar.py \
  tests/test_campaign_calendar_browser.py tests/test_research_campaigns.py \
  tests/test_campaign_assessments.py tests/test_campaign_portal_browser.py \
  --basetemp "$CALENDAR_RECHECK/run" --junitxml "$CALENDAR_RECHECK/results.xml"
.venv/bin/python tests/review_campaign_calendar.py \
  --browser-root "$CALENDAR_RECHECK/run" --output "$CALENDAR_RECHECK/independent.json"
```

To inspect the saved Evaluation library through the actual portal:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/campaign-calendar-auto-20261107/qualification/test_automatic_calendar_from_s0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8016
```

Open `/#backtests/report/b2a9a508f2c54f40a955a9357fc42231` at
`http://127.0.0.1:8016`, click Configure prop analysis → Create Evaluation campaign,
and expect no manual calendar-coverage field. Set scenario start 2040-01-02,
10 MNQ, 8 paths/chains and block 1; Save/check shows 2049-12-30 and enables Run.
The saved campaign is `/#backtests/prop/campaign/a6c5e2ff43b1484abaffc1b52e50750f`.
Expect $70 / 2 days and the resolved calendar in downloaded request/report files.
For Funded, use the sibling `test_automatic_calendar_from_s1` library, campaign
`922618667eba4f18a8f66d0a6f221cef`, 3 MNQ, H=14 and lag=4; expect the Jan 16
coverage and $1,500 received/$1,500 pending. Stop the owned server with Ctrl-C.
Reload/restart an existing app and refresh the browser to load both backend and
frontend changes; no user server was restarted by this task.

Qualification: **45 targeted tests passed** (359.38 seconds), including both new
real-browser workflows and existing campaign/freeze/OOS regressions. The only
warning was the existing FastAPI/Starlette TestClient deprecation. This is not a
full-repository suite claim. The final independent auditor passed both outcomes
and 34 download/report/ZIP checks; `git diff --check` and the new documentation
anchors passed. Evaluation/Funded implementation identities match exactly.

A full SHA256 rehash checked all **121,786** preexisting data/evidence files:
**121,785 are byte-identical**, none missing. The single exception is the mutable
`data/prop_analyses/catalog.sqlite3`, whose bytes changed during this session with
the preexisting reload server still running. Its SQLite quick-check is `ok`, with
698 complete and 131 incompatible entries. There is no pre-change logical dump,
so logical catalogue equality is not claimed. All preexisting saved report and
evidence files match their hashes; no catalogue was restored or overwritten.
See `qualification.json`, `preservation-validation.json` and both identity
snapshots in the new evidence root.

Earlier evidence is retained. Existing phase model/code identities are checked
against the pre-change snapshot. No numerical/provider parity, verified future
calendar, new sampling model, automatic final OOS or portfolio feature is claimed.
Temporary browser-test servers stop through fixture cleanup; no persistent server
or GitHub push was started.


## Automatic candidate count and large-search confirmation — 2026-11-07

The manual Maximum candidate count field and the fixed candidate-count ceiling
are removed. The server counts the complete saved-trial × MNQ-size set. Exactly
128 needs no confirmation; above 128 returns an HTTP 409 confirmation challenge
with the exact count before source calculation or campaign persistence. The
portal displays a native confirmation dialog. Cancel saves nothing and leaves
Run disabled; Confirm resubmits the same declaration with
`confirmed_candidate_count`. Configuration edits invalidate the check and discard
that acknowledgement. Source/profile/risk/cost/date checks still apply.

Sources, explicit trial lists, both phase searches/direct phase APIs and freeze
selections no longer impose a candidate-count ceiling. Legacy
`maximum_candidates` is accepted as deprecated metadata and no longer truncates
or rejects a new search. Old declarations/manifests remain readable and unchanged;
idempotent submission recognizes old declarations without new default fields.
Confirmation is saved in the existing campaign manifest/declaration/export and
is excluded from numerical requests/cache keys. Above-threshold standalone phase
API check/submit requests also require the exact confirmed count.

This is count admission, not unlimited compute capacity. Existing 100 MiB capture
preflight, 128 MiB exact report limit, funded 50-million path-calendar-day bound,
per-candidate path/size limits and queue limits remain. Confirmation does not
bypass them. No hidden pruning, new service, report store or synthetic UI was added.

### Actual product journey and independent expected values

Normal labeled dataset upload → normal 43-trial IS optimization with automatic
legacy reports disabled → saved backtest report → Configure prop analysis →
Create Evaluation/Funded campaign → choose saved optimization and three sizes →
Save/check → cancel 129 → edit to two sizes/check 86 without dialog → restore
three sizes → confirm 129 → full check/run → durable results/downloads/reopen.
Both real-browser cases save the dialog text/decision, screenshots, all six
ordinary campaign downloads and the existing dataset/backtest/AnalysisStore
library. The API tests additionally check 128 with no acknowledgement, missing/
wrong acknowledgement at 129, every source/size member, freezing all 129, source/
job deletion protection, equivalent-search reuse and workload rejection.

| Phase | Grid | Campaign | Analysis |
| --- | --- | --- | --- |
| evaluation | `f31deabe850c4065a3eed7b9a8ce7037` | `6f5d54cce463440dbff1aa42c3d787c8` | `608ce95b5ac948f6bf0935b82c0821d7` |
| funded | `5e153233918d4163aa24b6b7fa220d2c` | `486ea8530b9841f3b3fe4708041fd912` | `413218d0ec224e8ba9725f3d45c224eb` |

All sources are labeled **SYNTHETIC 43-trial candidate confirmation**. The saved
IS window is 2026-01-05…2026-01-14, reserved OOS 2026-01-15…2026-02-05. The ordinary
grid varies fixed NQ contracts C=1…43, with green count/hold minutes both 1,
initial backtest capital $10 million, and zero commission/slippage. Each source
has eight native-risk-covered intraday winners at $3,000 × C. Thus every scaled
MNQ earns $300 per sampled session: `$3,000 × C / (10 × C) = $300`.
These are deliberate arithmetic scenarios, not current provider prices or forecasts.

- Evaluation uses 10/11/12 MNQ: 43 × 3 = **129** candidates. Each reaches the
  local $3,000 target on Monday Jan 5, activates Tuesday Jan 6 and is usable
  Wednesday Jan 7. Expected acquisition is **$30+$40=$70** and **2 calendar days**
  for every candidate. All 129 objective ties remain on the saved frontier.
- Funded uses 3/4/5 MNQ: all earn at least $900 per session. Five-day qualification
  cycles request $1,500 on Jan 9 and Jan 16; a four-day lag gives Jan 13 and Jan 20
  receipts. The 14-day exclusive cutoff is Jan 19. Expected **$1,500 received**,
  **$1,500 pending**, **$3,000 gross account deductions** for every candidate.
  All 129 feasible candidates remain in the ranking.

`tests/review_candidate_confirmation.py` independently checks 258 candidate rows
from captured CSV/Decimal/date arithmetic, exact 43×3 source/size membership,
all 12 downloaded-file hashes and 190 ZIP/report artifacts, and both cancel/confirm
records. It imports no production calculator. The independent output is
`artifacts/candidate-confirmation-20261107/independent.json`.

### Reproduce and inspect

Use a fresh output directory with adequate free space (the original system disk
was nearly full; final tests used an owned temporary RAM disk):

```sh
RECHECK="artifacts/candidate-confirmation-recheck-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$RECHECK"
.venv/bin/python -m pytest -q tests/test_candidate_confirmation.py \
  tests/test_candidate_confirmation_browser.py --basetemp "$RECHECK/run" \
  --junitxml "$RECHECK/results.xml"
.venv/bin/python tests/review_candidate_confirmation.py \
  --browser-root "$RECHECK/run" --output "$RECHECK/independent.json"
```

The final qualification library is preserved losslessly as
`artifacts/candidate-confirmation-20261107/qualification.tar.gz`; original
resource-failed attempts are separately retained and do not count as passing.
Extract into a fresh directory (archive root is `qualification`) and start a
server against the saved Evaluation browser library:

```sh
INSPECT="artifacts/candidate-confirmation-inspect-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$INSPECT"
tar -xzf artifacts/candidate-confirmation-20261107/qualification.tar.gz -C "$INSPECT"
ALPHAQUEST_DATA_DIR="$PWD/$INSPECT/qualification/test_large_campaign_confirmati0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8016
```

Open `http://127.0.0.1:8016/#backtests/prop/campaign/6f5d54cce463440dbff1aa42c3d787c8`
for the saved 129-member result. To reproduce the form journey, open saved source
`/#backtests/report/30831de017534434a23184865e201218`, configure Evaluation, choose grid
`f31deabe850c4065a3eed7b9a8ce7037`, sizes `10,11,12`, paths/chains 8, block 1. Expect no manual maximum,
a 129-candidate confirmation at Save/check, no saved campaign on cancellation,
and $70 / 2 days for all 129 after confirmation/run. For Funded use sibling
`test_large_campaign_confirmati1`, sizes `3,4,5`, paths 8, block 1, horizon 14 and
lag 4; expect the receipt/pending amounts above. Stop the owned server with Ctrl-C.
Reload/restart the normal backend and refresh the browser to load both changes.

Qualification: **99 targeted tests passed** in 458.04 seconds, with one existing
FastAPI/Starlette TestClient deprecation warning. The final stable run covers both
phase math suites, all new confirmation cases, existing campaign/freeze/OOS and
portal regressions, calendar API/browser checks and the adjusted architecture
workflow. It is not a full-repository-suite claim. Initial disk-space failures
are retained separately; they are not counted as passes. Both independently
audited 129-member browser results and their downloads passed.

A full SHA256 rehash matched **all 123,489 preexisting data/evidence files**, with
none changed or missing. The final scratch library is losslessly archived and
file-by-file verified against its original (`archive-verification.json`). Earlier
reports/evidence were not compressed, deleted or rewritten. Temporary browser
servers stopped through fixture cleanup; the owned RAM volume was detached after
archival. No persistent server or GitHub push was started. See `qualification.json`
for the exact final command, scope, initial resource limitation and preservation
result.

The admission source edits necessarily advance both phase implementation hashes;
no hash inputs were excluded to force old-package reuse. All top-level numerical
functions in both phase optimizer modules are AST-identical to the pre-change
snapshot, and account kernels are unchanged (`identity-review.json`). Existing
reports/downloads reopen without recalculation; incompatible old campaign checks
and frozen launches still fail closed and require a new campaign. No change to
model equations, provider rules, fees/cash semantics or future parity is claimed.


## Valid IS window defaults — 2026-11-07

The campaign form now derives IS first/last sessions from the selected saved
backtests, intersecting each declared IS split with its actual saved bar-period
bounds in CME Chicago session dates. Multiple sources and selected optimization
trials use their common intersection. Dates are no longer initialized from the
wider split declaration. Observed zero-trade edge sessions are retained; dates
are not inferred from the first/last trade.

The existing campaign API adds a normal, read-only `/source-window` metadata
operation. Saved-source/job membership resolution is shared with campaign
creation, including complete/incomplete grid and explicit-trial checks. No trade
or dataset/OOS outcomes are loaded; no campaign is saved or simulation performed.
Source compatibility, costs, risk and explicit window validation still happen
through normal Save/check. Explicit API windows are never silently clipped.
Existing requests/reports and phase implementation identities are unchanged.

Manual date narrowing remains available within the displayed bounds. Other
simulation edits preserve it; Use full common IS window restores the defaults.
Changing sources or explicit trial lists rederives the window, disables checking
while pending and discards stale lookup results. Missing/invalid/OOS sources or
a disjoint common window leave checking/running disabled with an explanation.
Scenario start and automatic future calendar coverage remain separate controls.

### Actual product journey and independent expected values

Normal labeled dataset upload → ordinary two-trial IS grid (`automatic_prop:false`)
→ saved backtest report → Configure prop analysis → Evaluation/Funded campaign →
valid dates without editing → intentional narrower dates/reset → add/remove source
→ select a job trial with zero-trade edge sessions → valid observed defaults →
select the primary trial → Save/check → Run → durable report/downloads/reopen.
No separate page, demo API or duplicate result store is used.

| Phase | Grid | Campaign | Analysis |
| --- | --- | --- | --- |
| evaluation | `f58116bf7df04e6f90e9116e78933519` | `eb1a9a3507964739bd8dda8ef7709e34` | `19b78150ba474eccb341ef62cdba17c7` |
| funded | `1f695ff1990745e99b636efe3137bcb3` | `0d0d5e769cc140dc85f46886f0f4c0cc` | `3ffea22d7da34670a2f63af9b4296f69` |

Sources are labeled **SYNTHETIC declared versus observed IS coverage**. The normal
research declaration is **2021-01-01…2021-01-17**, with reserved civil-date OOS
2021-01-18…2021-02-04. Saved IS bar timestamps are exactly
`2021-01-03T23:01:00Z…2021-01-14T23:04:00Z`. Chicago session rollover converts
these to **2021-01-04…2021-01-15**, ten weekday sessions. That is the independently
expected form/request default. The old declared dates still reject when explicitly
submitted, proving the validation was not weakened to hide the bad default.

The grid uses green counts 1/2, one-minute holds, one NQ, zero costs/slippage and
$10,000 initial backtest capital. The primary source has ten $3,000 winners.
The second has eight $1,000 winners, with no trades on observed Jan 4/15; its first
and last trades belong to Jan 5/14. Both must default to Jan 4/15, not trade bounds.
Custom Jan 5…14 survives unrelated parameter edits and is preserved in explicitly
saved requests; resetting or changing source selection restores common coverage.
An explicit Jan 1 override is invalid in the browser and rejects through the API.

For the normal saved result, target scenario start is separately set to Monday
Jan 4. Eight paths (and eight Evaluation chains), block 1, use the primary source:

- Evaluation at 10 MNQ earns $3,000/session, passes Monday, activates Tuesday and
  becomes usable Wednesday Jan 6: independent expected **$30+$40=$70** and **2
  calendar days**. Fees are synthetic software overrides, not provider prices.
- Funded at 3 MNQ earns $900/session. Five-day cycles request $1,500 on Jan 8/15;
  four-day receipt lag gives Jan 12/19. A 14-day exclusive cutoff is Jan 18:
  independent expected **$1,500 received**, **$1,500 pending**, **$3,000 deducted**.

Each browser library saves initial/default, custom, zero-edge, checked and result
screenshots, `window-metadata.json`, `workflow.json` and the normal six campaign
JSON/CSV/ZIP downloads. Reopening emits no POST and repeated downloads are
byte-identical. `tests/review_campaign_window.py` independently checks actual
saved UTC bounds/CME dates, both source CSVs including the zero-trade edges,
source-derived fee/cash arithmetic, twelve download hashes and 22 ZIP/report
artifacts. It imports no production calculator. Results are in `independent.json`.

A read-only metadata check of the previously inspected real source
`739b88028ef846fdb8891ecb307ed574` now derives **2021-01-04…2024-12-31**;
`actual-source-metadata.json` records the declared and saved bounds. No analysis
of that user source was run and no user report was changed.

### Reproduce and inspect

Choose a fresh directory with adequate space; the original system disk was nearly
full, so final qualification used an owned temporary RAM volume and preserved the
library losslessly in `artifacts/campaign-is-window-20261107/qualification.tar.gz`.

```sh
RECHECK="artifacts/campaign-is-window-recheck-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$RECHECK"
.venv/bin/python -m pytest -q tests/test_campaign_window.py \
  tests/test_campaign_window_browser.py --basetemp "$RECHECK/run" \
  --junitxml "$RECHECK/results.xml"
.venv/bin/python tests/review_campaign_window.py \
  --browser-root "$RECHECK/run" --output "$RECHECK/independent.json"
```

To reopen the saved Evaluation library, extract the archive into a new directory:

```sh
INSPECT="artifacts/campaign-is-window-inspect-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$INSPECT"
tar -xzf artifacts/campaign-is-window-20261107/qualification.tar.gz -C "$INSPECT"
ALPHAQUEST_DATA_DIR="$PWD/$INSPECT/qualification/test_observed_is_default_in_pr0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8016
```

Open `http://127.0.0.1:8016/#backtests/report/5cb1fc8debb248058d108ca5212c6f00`, configure Evaluation and
expect IS **Jan 4…15 automatically**. To match the saved outcome set scenario
start Jan 4, 10 MNQ, paths/chains 8 and block 1; Save/check then Run gives $70/2 days.
The saved report is `/#backtests/prop/campaign/eb1a9a3507964739bd8dda8ef7709e34`. For Funded use sibling
`test_observed_is_default_in_pr1`, size 3, paths 8, block 1, scenario Jan 4, horizon
14 and lag 4; expect the receipt/pending figures above. Stop the owned server with
Ctrl-C. Refresh the normal app; restart its backend if it is not using reload.

Qualification: **62 targeted tests passed** in 100.33 seconds, with the existing
FastAPI/Starlette TestClient deprecation warning. This includes the new date/API
and both normal-product browser cases, existing campaign creation/cache/freeze
checks, automatic-calendar checks, all large-candidate confirmation tests and the
architecture browser workflow. It is not a full-repository suite claim. Initial
new-test fixture date/CSV-column assumptions were corrected before the final
stable run; their logs remain separately labeled.

The independent auditor passed both normal-product results and zero-trade-edge
checks. The archive was verified against all 2,043 original scratch files before
cleanup. Full SHA256 rehash matched all **123,522 preexisting data/evidence files**,
none changed or missing. Both complete phase implementation/kernel identities
match their pre-change snapshots exactly. No user source was resimulated or saved
report modified. Temporary browser servers stopped through fixture cleanup; the
owned RAM volume was detached after verified archival. No persistent server or
GitHub push was started. See `qualification.json`, `independent.json`,
`archive-verification.json`, identity snapshots and `preservation-after.json`.
# Robust research audit and execution plan — 2026-11-07

The new `feature/robust-research-workflow` branch starts at freshly fetched clean
`origin/main` commit `60dbccbda8e97373a3856ea6ee3fdd07313cad4f`. The
[audit, traceability matrix and milestone plan](robust_research_plan.md) map the
complete requested workflow to current owners and missing functionality.
This documentation-only increment has no artificial demo screen or new report.
Existing dated replay/cash accounting will be reused; existing Monte Carlo OOS
assessment is not historical chronological OOS. No new numerical/provider/live
qualification is claimed. All saved evidence below remains unchanged.

## Nested inner research product increment — 2026-11-07

Implemented: session-aware rolling/expanding nested plans, declared whole-session
purge/embargo, normal isolated inner backtests, full-set qualification, numerical
parameter neighborhoods (including typed Decimal parameters), additive cost
sensitivity and approximate session-block bootstrap intervals. All thresholds,
candidate membership and implementation/source identities are saved before
execution. The existing prop configuration and AnalysisStore provide check/run,
progress, cooperative stop/resume, durable reports and downloads. No new service,
database, backtest engine or demo-only screen was created.

This is an **inner research increment**, not complete nested economic validation.
Outer tests and policy selection are `not_run`; overall readiness is
`INCOMPLETE`. Required missing execution scenarios/regimes return
`INSUFFICIENT_EVIDENCE`; causal regime construction, alternative fill reruns,
variable prop sizing, frozen economic selection/replay, final recommendations
and forward monitoring remain pending. PASS means only the saved research
criteria passed. There is no numerical-provider parity or live-readiness claim.

Saved final product library (earlier attempts retained):
`artifacts/robust-research-m1-20261107/browser-release/test_nested_research_preview_q0/`.
It contains ordinary dataset/backtest catalogues and AnalysisStore artifacts,
`browser-evidence.json`, downloaded report/plan/qualification CSV/ZIP, and desktop
and 390px screenshots. Campaign `4542bf54a18541b5b1c52fcfd9780b65`, report
`3443ccfab48b4564a50a7125aab6f422`. The report JSON SHA-256 is
`94e9a8a338f8b3c10116d3378d99e761a7ef2fa7123f94ffcfae8a7cc043333e`.

Reopen the actual saved product from this checkout:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/robust-research-m1-20261107/browser-release/test_nested_research_preview_q0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory \
  --host 127.0.0.1 --port 8019
```

Open `http://127.0.0.1:8019/#backtests/report/090e0c2ee4d841f5a086b34bd345e1b5`.
Choose **Configure prop analysis → Nested research** and open the saved
“SYNTHETIC neighboring configurations · inner research” history row. Or open
`http://127.0.0.1:8019/#backtests/prop/job/3443ccfab48b4564a50a7125aab6f422`
directly. Expect three outer plans, three inner folds each, both configurations
qualified in every outer training window, and explicit pending outer testing.
Download report JSON/ZIP/qualification CSV; reload and observe no recalculation.
Stop this manually started server with **Ctrl+C**. All browser-test servers were
temporary and stopped by their fixtures; no persistent server was started.

To reproduce through the form, use the anchor above and select neighbor
`d867e69488104d7d8d962d14c611b0d9`. Set rolling outer training 10 sessions, outer
test 3, inner training 2, inner validation 2, purge 1, embargo 0, minimum inner
folds 2 and outer folds 2. In qualification requirements retain the saved
defaults except minimum sessions 6, minimum trades 6, minimum trades per fold 1
and bootstrap block 1. Preview must show **36 backtest tasks**: 3 outer plans ×
3 inner folds × 2 roles × 2 configurations. Review and run. The source is
explicitly synthetic and has been accessed before; never label it untouched.

Independent expected arithmetic: one source NQ contract has point value $20.
The green-count-1 trade earns 150 points × $20 = **$3,000** per session;
green-count-2 earns 50 points × $20 = **$1,000**, with zero baseline costs.
Each outer plan has six inner validation sessions, so means are $3,000/$1,000
and total validation net $18,000/$6,000. The deterministic constant-session
fixture has degenerate historical bootstrap intervals; this is an arithmetic
oracle, not credible empirical evidence of a real edge. All six candidate rows
pass the declared fixture criteria, while overall readiness remains incomplete.

Boundary checks: previewing default 60/20 windows against the short source
rejects with an insufficient-history reason and disables Run. Test-only fixtures
also verify partial UTC/Chicago boundary-session exclusion, changing future
prices without changing earlier admission, absent required regime/fill evidence,
OOS candidate rejection, actual VWAP Decimal provenance and no-trade insufficiency,
cross-kind ID collisions, source/code changes, artifact tampering, deletion during
publication, and cancellation/resumption without discarding completed work.

Executed new gates:

```sh
.venv/bin/python -m pytest -q tests/test_research_folds.py \
  tests/test_edge_qualification.py tests/test_robust_research_api.py \
  --basetemp artifacts/robust-research-m1-20261107/focused/data \
  --junitxml artifacts/robust-research-m1-20261107/focused/junit.xml
.venv/bin/python -m pytest -q tests/test_robust_research_browser.py \
  --basetemp artifacts/robust-research-m1-20261107/browser-release \
  --junitxml artifacts/robust-research-m1-20261107/browser-release.xml
```

Results: **90 focused tests passed** in 22.37 seconds; **1 browser test passed**
in 48.80 seconds. Both had the existing Starlette/httpx deprecation warning.
The browser gate needed local Chromium process access outside the filesystem
sandbox. Use a **new** `--basetemp` path when repeating: pytest clears its supplied
base directory. Do not overwrite these saved libraries. Full baseline/regression
qualification remains separately recorded in the active implementation checklist.

Regression scope: the existing mixed research/phase/browser gate finished with
82 passes and 17 shared campaign-fixture errors during concurrent source edits.
The failing surface was rerun on stable source: the entire existing campaign
module passed **19 tests** in 41.23 seconds. Logs retain both outcomes; this is not
a clean full-suite claim. See the [execution log](robust_research_plan.md#m1a-release-evidence-and-remaining-m1-work)
for the exact commands, diagnosis limits and still-pending full qualification.

## Execution stress and causal condition evidence — 2026-11-07

This additive M1b increment reruns declared execution scenarios through the
ordinary engine and saves each as a normal backtest. It fits market-condition
thresholds on inner training only and assigns validation trade labels using
strictly earlier bars. The existing prop configuration, campaign worker,
AnalysisStore report and downloads expose every outcome. Sizing/display knobs
cannot establish signal neighborhoods; descriptive complexity limits are optional
predeclared research criteria. Earlier M1a reports and libraries above remain
unchanged. No outer test, prop-policy selection or live qualification is claimed.

The normal-product browser library is
`artifacts/robust-research-m1b-20261107/browser-final/data/test_execution_scenarios_and_r0/`.
It contains the source dataset/backtest, 36 generated backtests, the analysis,
five downloaded artifacts, `browser-evidence.json` and desktop/narrow screenshots.
Campaign `47de5d87a5f04046b4d66437f4f3c458`, analysis
`f49cb21d87df4940a1b118cb31dc2a81`, report SHA-256
`4a948bb975a1d25e239f54d9611016ee012033a3a30d3f879aafc7cf78baf9a1`.
The preceding `browser-release/` library and its analysis
`065c000a43cb411fb780d2c1e47df6a2` remain preserved as earlier evidence.

Reopen this actual product library:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/robust-research-m1b-20261107/browser-final/data/test_execution_scenarios_and_r0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory \
  --host 127.0.0.1 --port 8019
```

Open `http://127.0.0.1:8019/#backtests/report/fb597ed91b304e128ce4f795897362d9`.
Choose **Configure prop analysis → Nested research** and open “SYNTHETIC execution
and causal regime checks”. Or open the saved report directly at
`http://127.0.0.1:8019/#backtests/prop/job/f49cb21d87df4940a1b118cb31dc2a81`.
Expand **Evidence** and **Training calibration and unknown validation observations**.
Reload and download JSON/ZIP/qualification CSV: no recalculation occurs and bytes
remain identical. Stop the manually started server with **Ctrl+C**. Browser
fixtures stopped their own temporary servers; no persistent server was started.

To reproduce from that source, use rolling outer train/test 10/3 sessions, inner
train/validation 2/2, purge 1, embargo 0, minimum inner/outer folds 2/2. Set minimum
sessions/trades 6/6, trades per fold 1, block length 1, minimum neighbors 0,
minimum regime sessions/trades 2/1. Enable maximum signal search dimensions 0.
Add these named scenarios:

| Setting | `higher-costs` | `unviable-costs` |
| --- | --- | --- |
| Additional commission per contract per side | 5 | 1500 |
| Additional market slippage ticks per fill | 1 | 1 |
| Extra stop slippage ticks | 0 | 1 |
| Limit penetration ticks | 0 | 1 |
| Allow opening limit price improvement | true | false |

Assess US clock window, trend and high volatility; require only US clock window.
Set condition lookback 2 bars and minimum training features 2. Preview shows
**36 tasks**: three outer plans × three inner folds × one candidate × (training,
validation and two scenario runs). Save and run.

Independent arithmetic: baseline one-contract NQ earns 150 points × $20 = $3000
per session. One tick costs .25 × $20 = $5. The first scenario subtracts two $5
commissions and two $5 market-fill slips: **$2980/session**. The second subtracts
two $1500 commissions and two $5 slips: **−$10/session**. All three candidate
rows therefore **FAIL** on `unviable-costs`; no configuration is admitted. These
source trades have timed exits, so configured stop/limit assumptions are saved
but not activated in this particular demonstration. Separate execution tests
cover stop gaps, both directions, target penetration, opening-price improvement,
callbacks and risk bounds with independent prices/costs.

US clock classification is complete and passes. The first trade in each inner
window lacks two strictly prior validation bars, so price-feature labels remain
unknown; trend/high-volatility evidence is **INSUFFICIENT_EVIDENCE** and optional.
Making trend required instead blocks admission. Training thresholds, cutoff,
sample counts and unknown reasons are inspectable, as are every scenario's
source report and resolved execution settings. Source volume is a liquidity
proxy only, and Chicago clock buckets are not verified exchange hours. The
reported regime means include all covered validation sessions; do not sum
overlapping conditions. Overall readiness remains **INCOMPLETE**.

The API library at
`artifacts/robust-research-m1b-20261107/api-release/verified-data/test_actual_cost_scenario_reru0/`
also saves `actual-robustness-report.json` and `independent-expectations.json`:
one-MNQ baseline means $300/$100 become **$297/$97**, because two $1 commissions
plus two .25-point × $2 slips cost $3. Its required US condition passes and its
optional trend remains insufficient. Additional API checks reject duplicate or
reserved scenario names, booleans used as tick counts, unknown condition names,
changed immutable declarations and OOS launch from inner/scenario sources.

Initial gates: 244 pure/calculation tests passed; nine existing nested API tests
passed; all three new robustness API tests passed after correcting a test to
exercise the OOS **launch POST** (the GET merely reports history). The first
artifact command lacked its parent directory and ran no tests; retained JUnit
shows that setup error. The first browser gate passed **2 tests in 69.16 seconds**, with
the existing Starlette/httpx deprecation warning. A subsequent review found
conditionally disabled knobs could create false signal neighbors; final
hardening and stable regression results are recorded with the release checklist.
This is focused evidence, not a full-suite pass or external execution parity.

Stable release gates after the inactive-parameter correction: **273 focused
tests passed in 40.35 seconds**, **132 existing backtest/reuse/risk/commission/
phase/campaign tests passed in 230.08 seconds**, and **both final browser journeys
passed in 73.13 seconds**. Logs/JUnit/libraries are respectively
`final-focused/`, `legacy-regression/` and `browser-final/` under the M1b artifact
directory. Disabled filter thresholds, display-only differences and equivalent
numeric spelling reject as duplicate effective configurations; varied source
quantities reject before signal qualification. A normal active signal axis still
forms neighbors. The final boundary review additionally rejects programmatic
scenario-bearing IS reports in nested/manual OOS routes rather than dropping
their fill assumptions; its targeted verification is recorded below. This last
admission guard does not alter the saved demonstrated calculations.
After that guard, **41 affected robustness, nested and manual IS/OOS tests passed
in 107.02 seconds**, with log/JUnit/library in `final-boundaries/`. This includes
the additional programmatic scenario-source regression. Compilation of
`alphaquest`, JavaScript syntax and `git diff --check` passed. These gate counts
overlap; they are not a combined distinct-test count or a full-suite claim.

Reproduction commands (use fresh output directories; never reuse these saved
`--basetemp` paths):

```sh
.venv/bin/python -m pytest -q tests/test_research_folds.py \
  tests/test_edge_qualification.py tests/test_execution_scenarios.py \
  tests/test_execution.py tests/test_next_bar_execution.py \
  tests/test_intratrade_risk.py tests/test_research_regimes.py \
  tests/test_robust_research_api.py tests/test_research_robustness_api.py
.venv/bin/python -m pytest -q tests/test_backtest_api.py \
  tests/test_backtest_reuse.py tests/test_prop_risk_workflow.py \
  tests/test_prop_commissions.py tests/test_prop_phase_profiles.py \
  tests/test_research_campaigns.py
.venv/bin/python -m pytest -q tests/test_robust_research_browser.py
```

## Canonical external trades and local prop analysis — 2026-11-08

M2a adds versioned external trade ingestion to the existing Backtests report and
strategy catalogue, followed by normal prop configuration, source checking,
analysis execution and durable downloads. It does not create market data or
invoke an external prop engine. The complete contract is in
[`designs/trade_export_v1.md`](designs/trade_export_v1.md). An import can be valid
while being ineligible for a particular simulation. External independent phases,
dated/budgeted replay and dynamic sizing remain pending. Earlier evidence and
reports above are preserved.

The final eligible synthetic product library is
`artifacts/trade-import-m2a-20261107/browser-final/data/test_supported_external_source0/`.
It contains the original synthetic JSON, ordinary saved source and analysis,
source-check JSON, downloaded report/ZIP/CSV, `browser-evidence.json` and desktop
and 390px screenshots. Source `42c0d5aba86f49b4a86cc1b3101e8187`, analysis
`fda22a17fa544222a39d75e49e241aec`. Original SHA-256
`fc5c179cd0acd64beb323320cac5ce362ec35d9ebb5ec61fd1eb6ce5117dba4f`;
report SHA-256
`59e55e5609f3dfc8b0a8fd9bfe42b41ff4e454e96540fcc2a404463a7bc2f58a`;
ZIP SHA-256
`7f4c80568e36485645bfc0c02547a48a6ab2dd8da6344cbc0fadf55cae3796d2`.
The first and second browser libraries remain unchanged; the first had one
assertion failure from checking option-disabled state without distinguishing its
disabled parent select. The corrected assertion inspects the option's own
disabled property. Both subsequent browser journeys passed.

Reopen the saved product library:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/trade-import-m2a-20261107/browser-final/data/test_supported_external_source0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory \
  --host 127.0.0.1 --port 8019
```

Open `http://127.0.0.1:8019/#backtests/report/42c0d5aba86f49b4a86cc1b3101e8187`.
Expected: source net **$4**, gross **$6**, commissions **$2**, slippage **$2**,
trade-close equity **$10000 → $10004**, original trade ID `mc-42`, and explicit
external-source provenance. No local dataset is created. The market benchmark
explains the lack of bars; native OOS/risk replay/detail controls are unavailable.
Original/canonical/trade/equity/report downloads remain inspectable.

For a fresh import, open `http://127.0.0.1:8019/#backtests/new?import=external`,
select `SYNTHETIC-supported-external-trades.json` from this library,
**Check import → Save imported report**. The same bytes reopen the same report
without duplication. From the report select **Configure prop analysis**. In
advanced settings choose source commissions, 1 slot, maximum total NQ 0.1 and
block length 1; retain annualized mode. **Check source** shows $4 source net and
**5 observed ordered marks across 1 trade**, plus two declared sessions with a
1/1 training/validation split. **Run analysis** publishes through the ordinary
AnalysisStore. Direct saved result:
`http://127.0.0.1:8019/#backtests/prop/job/fda22a17fa544222a39d75e49e241aec`.
Select **Source & model**, reload and download JSON/ZIP/trades CSV. Reopening
makes no POST and returns byte-identical downloads without recalculation.
`analysis.zip` includes original and normalized source inputs with hashes.
Stop the manually started server with **Ctrl+C**. All browser fixtures stopped
their temporary servers; no persistent server was started for this increment.

Independent arithmetic and expected results:

| Observation | Independent expectation |
| --- | --- |
| Two MNQ, reference 100 → 102, point value $2 | Reference gross $8 |
| Actual fills 100.25 → 101.75 | Actual gross $6; $2 slippage already reflected |
| Entry/exit commissions $1 each | Net $4; no second slippage or fee deduction |
| Ordered net marks −1, −6, −2, +6, +4 | Observed whole-trade MAE/MFE $6/$6; 5 events |
| Normalize to one MNQ | Net $2; observed MAE $3; fee $1 |
| Declared Jan 5 and Jan 6 sessions | Retain empty Jan 6; training/validation 1/1 |
| Tiny source cannot reach evaluation target | Pass rate 0; funded results unavailable, not invented zero-payout forecasts |
| Override fee $1 per MNQ per side | Net $1; adverse mark $3.50, charging only entry fee while open |
| Daily threshold −$2 crossed by observed adverse mark | Loss −$3 (or −$3.50 with override), preserving the observed jump |

The source labels its fixed-path invariance as an exporter declaration. This
synthetic arithmetic fixture is not market evidence, tick-completeness proof,
provider certification or a profitable-strategy recommendation. Observed marks
are not fabricated measured companion MAE/MFE. Independent tests distinguish an
observed jump from continuous threshold interpolation, which would erase the
overshoot. Planning/provider uncertainty remains explicit.

The second saved library
`browser-final/data/test_import_review_rejection_s0/` holds source
`a42547c267ad44429bdb09d3cb4966d7`, whose unverified path-invariance declaration
allows import but blocks prop analysis with a visible reason. Its browser
journey also rejects an incomplete export before Save, confirms the external
catalogue has no native dataset link or native rerun control, and verifies
duplicate import/reload/download integrity. API/unit checks cover duplicate keys,
decimal/time/hash/count/cost mismatch, late or impossible stop decisions, partial
positions, out-of-order event ownership, reported extrema beyond the observed
path, unsupported source calendars/currency/quantity, tampered artifacts, changed
export IDs and concurrent identical imports. Native-only routes return explicit
rejections instead of failing on a nonexistent dataset.

The prop API library
`artifacts/trade-import-m2a-20261107/prop-api/data/test_normal_import_check_analy0/`
saves `independent-expectations.json` and normal downloads. That 17-test gate
passed in 2.25 seconds after correcting two test expectations; the earlier
failures are retained in its log. The stable integrated regression passed
**233 tests in 283.58 seconds**, covering existing backtest/reuse/prop API/cost/
phase/campaign behavior plus canonical import/catalogue. After final report
contract wording, **38 import/prop boundary tests passed in 4.48 seconds**.
Both final import browser journeys passed in **12.54 seconds**. Logs/JUnit/data
are under `regression/`, `final-prop/` and `browser-final/` respectively. Existing
report, strategy catalogue, dataset navigation, exact submitted configuration
and mobile browser regression passed **29 tests in 323.84 seconds**, saved under
`browser-regression/`. Desktop and 390px screenshots were visually inspected.
Starlette/httpx deprecation warnings remain. These overlapping gates are not a
combined distinct-test count or a full-suite/provider-parity claim.

Reproduction commands (use fresh directories for `--basetemp`; pytest clears
the selected base, so never reuse the preserved evidence directories):

```sh
.venv/bin/python -m pytest -q tests/test_backtest_api.py \
  tests/test_backtest_reuse.py tests/test_prop_analysis_api.py \
  tests/test_prop_commissions.py tests/test_prop_phase_profiles.py \
  tests/test_research_campaigns.py tests/test_canonical_trades.py \
  tests/test_trade_imports.py tests/test_external_trade_library.py
.venv/bin/python -m pytest -q tests/test_external_prop_source.py tests/test_trade_imports.py
.venv/bin/python -m pytest -q tests/test_trade_import_browser.py
.venv/bin/python -m pytest -q tests/test_reports_browser.py \
  tests/test_strategies_browser.py tests/test_strategy_dataset_browser.py \
  tests/test_backtests_browser.py::test_exact_submitted_configuration_and_saved_completion_summary \
  tests/test_backtests_browser.py::test_mobile_navigation_and_layout
```

M2a source-snapshot clarification: its all-Python implementation identity also
captured the then-unintegrated `prop/sizing.py` contract, which was deliberately
left out of the import feature commit until M2b integration. The exact matching
bytes and SHA-256 are preserved at
`artifacts/trade-import-m2a-20261107/source-snapshot/` with a reconstruction note.
No saved report was rewritten. The M2b release incorporates that same pure
contract with its account/API/UI integration.

## Causal sizing and native decision capture — 2026-11-08

M2b uses the existing Evaluation/Funded account transitions, phase campaigns,
workers and AnalysisStore. Eligible canonical external IS sources can compare
fixed-contract, fixed-dollar and percentage-risk policies. Each percentage base,
planning cost, cap, skip and decision is explicit. Native fixed scenarios remain
supported; native risk-based resizing requires an account-state strategy rerun
and rejects. Captured native stops do not prove an invariant signal path. Outer
economic validation and M3–M6 remain incomplete; no production/provider readiness
or external numerical parity is claimed.

The final normal-product libraries are under
`artifacts/phase-sizing-m2b-20261108/browser-release/data/`:

| Phase / directory | Source | Campaign | Analysis |
| --- | --- | --- | --- |
| Evaluation / `test_imported_causal_sizing_ca0` | `4ebe9ad7fc124dcbbeffbb80d8ad4e17` | `98daecf33e204deb96b9f0124b67049f` | `76bde8b2790e4ad284c1f90ffd5a6f4d` |
| Funded / `test_imported_causal_sizing_ca1` | `97e0a0783629473c960a04d17662e180` | `dece279fb4b945c392aa157eed10371d` | `f8cb4467b3ac422d9adc0890dc67332d` |

Each includes the synthetic original export, campaign/report/ZIP/CSV downloads,
`browser-evidence.json`, and desktop/390px screenshots. Original source SHA-256
`bd30f9f0905b42af3dfecad4b964fb8cdbf0a3f30c95305e4cf0e6a0f886ef02`.
Evaluation report SHA-256
`f00a4ea3b6e289fae9d29134a929b66be6d84f356e8ed682d380d88abd2d7dfe`;
Funded report SHA-256
`9d31311d68fd41fd56fd11f4bdbeebba4437090015448749c35e31078c7082a6`.
ZIP hashes and every downloaded file hash are in each evidence JSON. Prior
`browser-first/` and `browser-final/` outputs remain preserved; the release run
also verifies corrected external IS date labels in the source picker.

Reopen the Evaluation library:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/phase-sizing-m2b-20261108/browser-release/data/test_imported_causal_sizing_ca0" \
  .venv/bin/python -m uvicorn alphaquest.app:create_app --factory \
  --host 127.0.0.1 --port 8019
```

Open `http://127.0.0.1:8019/#backtests/report/4ebe9ad7fc124dcbbeffbb80d8ad4e17`.
The source contains six trades across January 5–6, net $20 and explicitly zero
fees/slippage. Choose **Configure prop analysis → Create Evaluation campaign**,
or open the saved campaign at
`http://127.0.0.1:8019/#backtests/prop/campaign/98daecf33e204deb96b9f0124b67049f`.
For Funded, stop the server and substitute directory `test_imported_causal_sizing_ca1`,
then use source/campaign IDs from the table. Stop manually started servers with
**Ctrl+C**. Automated browser fixtures stopped their temporary servers.

To reproduce from the original export, use the ordinary import form and select
`SYNTHETIC-causal-sizing.json` from either library. Check/save, then open prop
configuration and create the chosen independent phase campaign. Keep the
derived IS window January 5–6. Set simulations 2 and block length 1; Evaluation
uses 2 chains, Funded uses a 3-calendar-day horizon. Choose **Compare sizing
policies**, hard MNQ caps `3,40`, and declare these three policies:

- Fixed dollar risk $100, minimum 1 / maximum 40 contracts.
- Percentage risk 0.2%, reference **current account balance**, minimum 1 / maximum 40.
- Fixed dollar risk $1, minimum 1 / maximum 40 contracts.

All three use $50,000 initial configured capital, tick size 0.25, MNQ point value
2, explicit zero planning commission/entry slip/stop-exit slip, and no cushion
guard. Choose source commissions for actual source P&L. **Save and check** shows
all **6 candidates** (two caps × three policies), including skipped policies;
**Run** publishes the ordinary phase report. Inspect each candidate's sizing
evidence, retained decisions, denominators and reasons. Download sizing summary,
decision CSV, report JSON, campaign/results CSV and ZIP. Reloading submits no
POST and all downloaded bytes remain identical. Funded settings can be frozen;
the imported package explicitly has no native automatic OOS launch.

Independent expectations for the first simulated session are based on three
one-MNQ returns `−10, +20, 0` and causal stop distances `5, 5, 10` points:

| Policy / limit | Expected quantity and state |
| --- | --- |
| $100 risk / cap 40 | Planned unit loss $10/$10/$20; quantities **10/10/5** |
| 0.2% current balance / cap 40 | Bases **$50000/$49900/$50080**; budgets $100/$99.80/$100.16; quantities **10/9/5** |
| $100 risk / cap 3 | Quantities **3/3/3**, each with user-cap reason |
| $1 risk | All opportunities skipped; no P&L/cost/activity charge, calendar still advances |

Later sampled sessions use the changed account state, not one constant multiplier.
Two repeated source sessions make first-session arithmetic independent of which
template is drawn. This tiny fixture demonstrates mechanics, not empirical edge
or future profitability. Evaluation can remain unresolved with no passes; funded
cash can be zero. Neither result is invented to make the demonstration favorable.
The API evidence under `artifacts/trade-sizing-m2b-20261108/phase-api/data/`
also proves explicit fixed policies match legacy metrics/paths, phase independence,
policy/cost/base/cap identity separation, invalid sources/decisions rejection,
bounded detail with complete aggregates, and distinct native fixed policies at
the same cap surviving freeze/manual OOS without reselection.

Native capture uses the ordinary uploaded CSV and real VWAP strategy, saved under
`artifacts/trade-sizing-m2b-20261108/native-api/`. The source has synthetic morning
sequences January 5–8, IS January 5–7 and reserved OOS January 8. The declared
07:00 strategy reset is crossed by the observed morning bars; no missing evening
bars are invented. Dataset `92f627f930104477bbed84b0ee28b634`, backtest
`c63385cd0628401784a18bf7391b5745`.

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/trade-sizing-m2b-20261108/native-api/state" \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8033
```

Open `http://127.0.0.1:8033/#backtests/report/c63385cd0628401784a18bf7391b5745`
and download **Execution decisions**. Per IS session: signal close **108** and
initial stop **90** at 15:01 UTC; next observed open **115**, actual fill
**115.25**, target exit **130**. One NQ earns `(130−115.25)×20−2 = $293`;
three trades total **$879**. The bracket is submitted after the fill and becomes
active next observed bar; the record does not claim entry-bar stop protection.
The sidecar SHA-256 is
`a75399eae78d116f629cbdbb7cf05ff4a99ddd53901a6f76480ee9aa69fe8877`.
Original trade/equity/risk CSV values are unchanged. No OOS was accessed.

Reproduce the normal fixed-compatible and risk-policy rejection checks:

```sh
curl --fail-with-body -H 'Content-Type: application/json' \
  --data-binary @artifacts/trade-sizing-m2b-20261108/native-api/fixed-policy-request.json \
  http://127.0.0.1:8033/api/prop-analyses/check
curl -i -H 'Content-Type: application/json' \
  --data-binary @artifacts/trade-sizing-m2b-20261108/native-api/risk-policy-request.json \
  http://127.0.0.1:8033/api/prop-analyses/check
```

Expect 200/compatible for fixed 10 MNQ and 422 with the native strategy-rerun
requirement for $100 risk. Reopen/download retains all **48** saved backtest and
automatic prop artifacts without executing the strategy. Changing sidecar bytes
rejects download/detail reproduction; historical missing stops stay missing.
Stop the manually started server with **Ctrl+C**. The API proof used no
persistent server and saves requests, responses, original CSV and evidence JSON.

Kernel validation: **144 tests passed in 8.25 seconds**, including exact fixed
output hashes pinned to `bdbfa7e`, Python/compiled dynamic parity, hand arithmetic,
provider/user/cushion limits, inactivity, skips and observed-gap thresholds. Build
log, hashes and compiled identities are in `trade-sizing-m2b-20261108/kernels/`.
The stable phase API gate passed **36 tests in 68.74 seconds**. Native capture,
canonical/execution/reporting and VWAP/next-bar gates passed, and the real native
API demonstration passed in 17.82 seconds. The final three browser journeys
passed in **38.01 seconds**, with screenshots visually inspected. Counts overlap;
full-suite and provider qualification remain separate work.

The exploratory legacy probe during source edits had 20 passes and 48 shared
fixture errors from a generic backtest HTTP 500. A subsequent stable isolated
source run succeeded; the generic response did not retain the original cause,
so no definitive attribution is made. The failed log/JUnit remain in
`trade-sizing-m2b-20261108/early-probe/`. Stable legacy/browser regression results
are recorded below; the exploratory gate is not called clean.

Reproduction checks (fresh basetemp directories only):

```sh
.venv/bin/python -m pytest -q tests/test_prop_sizing.py tests/test_prop_engine_sizing.py
.venv/bin/python -m pytest -q tests/test_phase_sizing.py tests/test_external_prop_source.py
.venv/bin/python -m pytest -q tests/test_native_decisions.py tests/test_native_decisions_api.py
.venv/bin/python -m pytest -q tests/test_phase_sizing_browser.py
```

Stable release regression: **125 existing phase/search/campaign/freeze/cache/
dated/cash tests passed in 541.00 seconds**, saved under
`trade-sizing-m2b-20261108/legacy-regression/`. The native browser gate had
**8 passes / 1 failure**: an older test expected the already removed manual
candidate-budget field. The corrected full affected file passed **2 tests in
62.64 seconds**, exercising the real 129-member confirmation/dismissal, original
four-candidate results, constraints, freeze and reopen. Both outcomes are retained
under `phase-sizing-m2b-20261108/browser-regression/` and
`browser-regression-updated/`; the mixed run is not labelled clean.

A final backend guard rejects prop `sizing_policies` in inner qualification,
which otherwise shares the campaign source selector. Its affected nested,
execution-stress, date-range, optimization-cache and backtest API gate had
**94 passes / 9 failures**. All nine failures were exact file-inventory assertions
that omitted the new decision sidecar; their independent trade, equity, metric
and provenance expectations still passed. The artifact assertion now includes
and verifies the sidecar hash/filled-trade count. The **entire affected backtest
API module passed 53 tests in 20.65 seconds** afterward. Logs retain both runs in
`final-boundaries/` and `backtest-api-final/`. No numerical expectation was relaxed.
Python compilation, changed JavaScript syntax and `git diff --check` passed.
No server remains running. These overlapping gates are not a full-suite claim.

Additional exact regression commands:

```sh
.venv/bin/python -m pytest -q tests/test_evaluation_optimization.py \
  tests/test_funded_optimization.py tests/test_prop_phase_profiles.py \
  tests/test_research_campaigns.py tests/test_campaign_assessments.py \
  tests/test_backtest_reuse.py tests/test_prop_phases.py tests/test_prop_cash.py
.venv/bin/python -m pytest -q tests/test_campaign_portal_browser.py \
  tests/test_campaign_window_browser.py tests/test_research_campaigns_browser.py
.venv/bin/python -m pytest -q tests/test_backtest_api.py \
  tests/test_backtest_date_range.py tests/test_optimization_acceleration.py \
  tests/test_robust_research_api.py tests/test_research_robustness_api.py
```


## Frozen phase selection and chronological outer replay — 2026-11-08

The normal nested workflow retains the full qualified set, runs independent
training forecasts, seals each selected family before outer evaluation, and
saves modeled cash on the ordered historical source path. The three release
browser journeys passed in 90.90 seconds. This is a supported fixed-signal-path
increment; consolidated reliability, final recommendation, native state-aware
reruns and provider/live qualification remain incomplete.

### Normal product exercise

1. Open the saved **SYNTHETIC dated phase arithmetic** native IS backtest report, then **Configure prop analysis** → **Nested research** → **Configure nested research**.
2. Add the other saved neighboring configuration (`green_bar_count=2`; the anchor uses 1). Both use one NQ in the original native source, zero commission/slippage and the same 30 observed weekday sessions. They produce $3,000 and $1,000 per original trade, or $300 and $100 per MNQ. The reserved synthetic holdout is separate and is not used here.
3. Set rolling outer training/test to **10 / 7 sessions**, inner training/validation **2 / 2**, purge **1**, embargo **0**, minimum inner/outer folds **2 / 2**. Qualification uses at least six validation sessions/trades, at least one trade per fold, one neighboring parameter configuration, and one-session bootstrap blocks.
4. Expand **Economic validation**. Enable independent **Evaluation** and **Funded**. These are separate studies, with all qualified signals entering each study; there is no second signal picker or combined score.
5. Evaluation: Apex 50K EOD; fixed MNQ **10, 20**; retain the complete cost/time Pareto family and all exact ties; evaluation fee **30**, activation **40**, activation delay **1 session**, retry delay **0**. Advanced: 64 paths/chains, block 1 weekday, maximum 30 attempts / 60 calendar days. Guards represent censored calculation limits, not a promise of acquisition.
6. Funded: Apex 50K EOD; fixed MNQ **3, 10**; maximize expected trader cash, retain exact ties; receipt delay **2 calendar days**. Advanced: 64 paths, block 1 weekday, bootstrap 100. Profile rules, account ceiling, source costs, seeds and declared calendar remain saved. Receipt amounts use explicit unrounded modeled entitlement in both forecast and replay.
7. **Preview dates and source checks** shows two folds, two independent phase studies, 16 maximum phase candidates and 44 worst-case backtest tasks (24 inner + 4 training + 16 possible outer). It shows the full material declaration and the resolved forecast dates/cutoffs; user-declared calendar is not presented as verified provider calendar data.
8. **Save and run research** executes qualification, earlier-only economic forecasts, an immutable selection seal, then each selected policy's ordinary outer backtest and historical chronological account replay. The user cannot choose a different family after seeing the outer outcomes.

### Independent expected observations to verify

- Outer fold 1: **2026-01-20 → 2026-01-28**, exclusive cutoff **2026-01-29**.
- Outer fold 2: **2026-01-29 → 2026-02-06**, exclusive cutoff **2026-02-07**.
- The $300/MNQ signal passes the $3,000 Evaluation target on the first session at both 10 and 20 MNQ. Both exact cost/time ties remain frozen. No arbitrary hidden winner is substituted.
- Each selected Evaluation pays **30 + 40 = 70**, net modeled trader cash **−70**, with one attempt. Pass occurs on the first outer session; activation is the second; funded readiness is the third: **Jan 22 / Feb 2**. Evaluation P&L is not trader cash; no funded trades enter this study.
- Each selected funded policy's first gross request/deduction is **1,500** on its fifth outer session (**Jan 26 / Feb 4**). With two civil days' receipt lag, cash **1,500** arrives on **Jan 28 / Feb 6**, before the exclusive cutoff; pending cash is **0**. This is one fresh funded account per frozen alternative, with no Evaluation/acquisition fees or replacement account.
- The ordered journal has a matching `selection_seal` before every `outer_access` reservation. This proves the current procedure's ordering, not that historical source bytes were never inspected. Normal inner/training/outer reports and model/source hashes remain inspectable.
- Captured provider review is **UNVERIFIED / production qualified false**. `VERIFIED_DOCUMENT` means published wording was reviewed, not model/provider numerical parity or account entitlement. Normal report links expose per-profile gaps, primary sources and the saved review file.
- Research readiness remains **INCOMPLETE**: consolidated outer reliability, baseline superiority and final verification/deployment work are pending.

### Boundary examples

- **Receipt exactly at cutoff:** one qualified signal, Funded 3 MNQ, otherwise the same fold settings, receipt delay **3 days**. Request/deduction stays 1,500, but receipt due date equals the exclusive cutoff; received cash is **0**, pending is **1,500**. It must never appear as received cash or equity valuation.
- **No qualifying strategy:** one source, neighbor requirement **0**, minimum mean net **4,000** per source validation session. Its actual mean 3,000 fails. The economic selection reports `NO_QUALIFIED_CONFIGURATION`; no phase child or outer account result is fabricated, and the event journal contains seals without outer-access events.
- Native dollar/percentage risk resizing is not offered in the nested native form. The API rejects these unsupported policies instead of reusing a saved path as a causal stateful strategy rerun.

### Durability and browser evidence

Save/open the ordinary AnalysisStore report, the report JSON and ZIP, qualification CSV, full research plan, `economic_selection.json`, `chronological_replay.json` and `research_journal.json`. Child phase reports and normal outer backtests remain linked in the saved library. Reopen and page reload must issue no calculation POST and preserve download bytes. Inspect desktop and 390px screenshots.

Observed final browser command:

```sh
mkdir -p artifacts/nested-economics-m3a-20261108/browser-release
.venv/bin/python -m pytest -q tests/test_nested_economics_browser.py \
  --basetemp artifacts/nested-economics-m3a-20261108/browser-release/data \
  --junitxml artifacts/nested-economics-m3a-20261108/browser-release/junit.xml \
  > artifacts/nested-economics-m3a-20261108/browser-release/pytest.log 2>&1
```

The portal fixture's owned ephemeral localhost servers stopped after the gate. No persistent server was started by the product agent. To inspect the main saved example without recomputing:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/nested-economics-m3a-20261108/browser-release/data/test_both_independent_studies_0" \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8012
```

Open `http://127.0.0.1:8012/#backtests/report/27bf403664fe4a518a697016b7f33200` and follow the normal Configure prop → Nested research saved-history button, or reopen `http://127.0.0.1:8012/#backtests/prop/job/0e5a8acb69354350ac329a6225fd0e65` directly. Stop the inspection server with **Ctrl-C**.

| Example | Saved library under `browser-release/data/` | Source IDs | Campaign ID | Analysis ID |
| --- | --- | --- | --- | --- |
| Both independent phases | `test_both_independent_studies_0` | `27bf403664fe4a518a697016b7f33200`, `1a3a07861f874ad6b3aeb9a333ad670c` | `b6f4490f66b64a0892d6daa96d35a148` | `0e5a8acb69354350ac329a6225fd0e65` |
| Exact-cutoff pending receipt | `test_receipt_at_outer_cutoff_r0` | `02e1c32fdbd84704a3eb81b5002234ac` | `e7c0393a95334570ba9b502fd8233a8e` | `822883ef2724410caeeb37ddc0bcd9f3` |
| No qualified strategy | `test_no_qualified_configuratio0` | `e5478d31e9514c8ab1e8782588c3bdf0` | `c1904b3736784ec5a741894f306a58a6` | `9d040e76bebc46b999be08597e190ce8` |

Each library contains `browser-evidence.json` with all download hashes. Main root report SHA-256: `f26b5c5e29bdac5dbfd50fb8494fba770dd35b91186d41ff32441461480bfc57`; ZIP: `bd5cfe40dcd298d013e35581616b5958e42e741d461c1d1d67517d0cf428b5e1`; chronological JSON: `ba82cc441d126cbb046a994ee52412e9ad4413ae5a0b71271e6008d046645d94`; journal: `fcb3a0a64c67d901de9536c29011801accd8f67beaf607afd5649c2b027ef9d2`.

Pending report SHA-256: `4a2249dab870c1bfb103ef44b70f9a9ac5b5deefcd421ac708e1364be9e62efd`; ZIP: `b1c0fb1645aecaebbef7318165383f89c0e4bef3e253949a9ffc2ecd4c1ae30d`.

Abstention report SHA-256: `aab9f1486dfc145b49f51c3ede71e652d4e9d5fe853057aa501af25538400eed`; ZIP: `9d43862c048a0c48c8dfe9e0f0fd128b499db48d124cc5a18c9e44ca14cee33d`.

Visually inspected final screenshots: `economic-preview-detail.png`, `outer-cash-summary-detail.png`, `ordered-freeze-journal-detail.png`, `provider-rule-gaps-detail.png`, `narrow-earlier-forecast-viewport.png`, `narrow-received-cash-viewport.png`, pending `receipt-at-cutoff-detail.png`, and `no-qualified-abstention.png`. These show readable matching outcomes and no mobile horizontal overflow. Full-page screenshots are also preserved, along with native source/backtest/report stores. Browser reload issued no calculation POST; saved report/download bytes remained unchanged.

Existing-browser regression command (4 passed; its owned servers also stopped):

```sh
mkdir -p artifacts/nested-economics-m3a-20261108/browser-regression
.venv/bin/python -m pytest -q tests/test_robust_research_browser.py tests/test_research_campaigns_browser.py \
  --basetemp artifacts/nested-economics-m3a-20261108/browser-regression/data \
  --junitxml artifacts/nested-economics-m3a-20261108/browser-regression/junit.xml \
  > artifacts/nested-economics-m3a-20261108/browser-regression/pytest.log 2>&1
```

Both gates reported only the existing Starlette/httpx deprecation warning. JS syntax, the new browser test's Python syntax and the scoped whitespace diff check passed. Production ownership: `alphaquest/web/research_workflow.js`, the compact shared provider-review renderer in `alphaquest/web/campaigns.js`, and `tests/test_nested_economics_browser.py`; no backend or documentation repository files were edited by the product agent.

Release source verification: all 24 downloaded artifacts match their saved SHA-256 values, and all three reports match the current engine identity `03870c3e5d243488520d9059a2f5426fdacce87a4b8678021c78ebfbd7c07a2d`. The final browser snapshot uses the repaired rule that readiness exactly at the numerical retry guard counts only when it remains strictly before the outer cutoff; no trading or fee is introduced at the guard. The chronological boundary suite covers that repair separately from these unchanged product examples.


### Additional short-horizon API evidence

Saved final evidence: `artifacts/nested-economics-m3a-20261108/api-release/evidence.json`. The earlier `api` and `api-final` directories are immutable earlier-gate snapshots, preserved across the public Evaluation request schema correction and the numerical retry-guard readiness boundary repair. They remain readable; `api-release` is the release-engine reproduction target.

Final campaign `65c84ffb8c5d43ac8796812dd9611d1c`, aggregate AnalysisStore report `c4e621e0d7674520b76ce8085d66711a`, source report anchor `0170654a49f549649a67eb9b61b2ec1b`. Source dataset `a1e408e8dd3449a79ff31ddbdbbaaf64`, source optimization job `7acadd2a0b7249aabbc56fea7985c132`. The two source reports remain unchanged (16 existing source artifacts checked). Full source identity before and after publication was `03870c3e5d243488520d9059a2f5426fdacce87a4b8678021c78ebfbd7c07a2d`. Four normal child phase reports and twelve normal outer backtests are captured, together with raw trade/decision downloads, provider-rule review, complete training contexts and ordered selection/access journal. No persistent server was started by the publisher.

Start the existing application with the saved isolated product state:

```sh
cd /Users/yx/alphaquest-research-engine-2
ALPHAQUEST_DATA_DIR="$PWD/artifacts/nested-economics-m3a-20261108/api-release/state" .venv/bin/uvicorn alphaquest.app:app --host 127.0.0.1 --port 8034
```

Open `http://127.0.0.1:8034/#backtests/report/0170654a49f549649a67eb9b61b2ec1b`. Choose **Configure prop analysis**, then **Nested research → Saved research**, and open the synthetic complete-qualified-set campaign. The normal AnalysisStore result can also be opened from its source's analysis list. Stop the temporary server with Ctrl-C when finished.

Expected observations:

- Both original signal configurations remain in the complete qualifying set in each of two outer folds. Source arithmetic is independently asserted in tests: one-MNQ daily net $300 or $100. Policies 10 and 20 MNQ form four declared candidates per phase/fold; no parameter search or hidden top-N cut occurs in the economic handoff.
- Each Evaluation training frontier keeps both exact fastest ties at modeled acquisition cost $70 ($30 evaluation + $40 activation). Each Funded short-horizon mean ties at $0 received cash, so all four policies remain. The figures are training model forecasts, displayed separately from historical replay.
- Actual chronological outer replay contains four Evaluation paths: each pays $70, passes its evaluation, but funded-ready lies outside its exclusive cutoff. Each stays `activation_pending`, censored, with net cash -$70; do not call this a failed attempt or completed acquired account. Eight Funded paths each receive $0, with no pending payout, and remain open at cutoff. Profit/account equity is not trader cash.
- The ordered journal shows each `selection_seal` before its matching `outer_access` reservations. These are new outer execution/assessment boundaries. The source history was already accessed; the report makes no untouched-history claim.
- Provider rules and deployment readiness are `UNVERIFIED`/not production qualified; model-rule gaps and settlement assumptions remain visible. Overall readiness is `INCOMPLETE`. No deployment winner or scalar family portfolio is invented.
- Manual OOS count is still zero. Existing unlimited manual OOS history remains separate from this nested procedure evaluation.

Inspect exact files directly, or download through the normal API:

```sh
curl -f http://127.0.0.1:8034/api/research-campaigns/robust/65c84ffb8c5d43ac8796812dd9611d1c/exports/research_journal.json
curl -f http://127.0.0.1:8034/api/research-campaigns/robust/65c84ffb8c5d43ac8796812dd9611d1c/exports/economic_selection.json
curl -f http://127.0.0.1:8034/api/research-campaigns/robust/65c84ffb8c5d43ac8796812dd9611d1c/exports/chronological_replay.json
curl -f http://127.0.0.1:8034/api/research-campaigns/robust/65c84ffb8c5d43ac8796812dd9611d1c/exports/analysis.zip -o /tmp/alphaquest-m3a-analysis.zip
```

Normal child report artifacts use `/api/prop-analyses/<analysis_id>/files/provider_rules.json` and `/files/training_context.json`; reports use `/downloads/report.json`. Child IDs are listed in evidence.json. Outer ordinary trades and causal decision sidecars use `/api/backtests/<outer_run_id>/exports/trades` and `/exports/execution_decisions`.

The saved rejection responses are under `api-release/rejections`: public requests cannot inject an internal training context; native fixed-dollar/risk sizing fails with `native_rerun_required`. Additional tests mutate self-hashed frozen quantity/profile/phase/fold/source mappings, remove a training artifact, change a source trade file, cancel after a complete inline child, and reopen reports with all backtest/selection/optimization functions forbidden. Relevant data files are restored in those tests; the published product evidence remains immutable.

For a fresh execution against this same frozen code and saved source state, copy `api-release/declaration.json`, assign a new lowercase UUID campaign_id, then use the existing form or POST `/api/research-campaigns/robust/preview`, POST `/api/research-campaigns/robust`, POST `/<new_id>/check`, and POST `/<new_id>/run`. The same counts/values above are expected. If code/rules/source identity has changed, use newly created source reports and a new campaign; never bypass a frozen-identity rejection.

Checks: 29 selection/handoff contract tests passed; final fresh seven normal API tests passed in 19.78s after the public request schema correction and numerical retry-guard readiness repair. The added ordinary zero-trade outer case retains eight observed doji bars, replays both phases, retains $30 Evaluation fees without activation, and records two Funded sessions with $0 receipts. A truly missing outer date rejects the declared-calendar check. The latter is captured in `artifacts/nested-economics-m3a-20261108/api-gate-release.txt`. Source publishing used real normal routes, no mocked calculations, and before/after engine identity matched. Broader regression/browser results are recorded below. Reliability, baseline superiority/conservative historical-mean selection, full-procedure holdout and final development recommendation remain subsequent work; this increment does not satisfy the whole goal.

### Verification scope and retained failed probes

| Gate | Observed result | Saved evidence |
| --- | --- | --- |
| Pure constraints/rule review/empty source, Evaluation math and cash ledger | 63 passed, 2.92s | `artifacts/nested-economics-m3a-20261108/root-unit/` |
| Selection/handoff contracts | 29 passed | `tests/test_research_phase_selection.py`; release API guide |
| Replay/cash/profile/empty-source regression | 74 passed, 50.95s | `artifacts/chronological-replay-m3a-20261108/kernels/stable/` |
| Phase optimizers/campaigns/manual assessment/inner API and root contracts | 95 passed, 268.16s | `artifacts/nested-economics-m3a-20261108/legacy-final/` |
| Subsequent retry-guard boundary repair | 18 passed, 1.10s | `artifacts/chronological-replay-m3a-20261108/kernels/guard-boundary/` |
| Released normal economic API | 7 passed, 19.78s | `artifacts/nested-economics-m3a-20261108/api-gate-release.txt` |
| Released new browser journeys | 3 passed, 90.90s | `artifacts/nested-economics-m3a-20261108/browser-release/` |
| Existing inner-research/phase-campaign browsers | 4 passed, 130.15s | `artifacts/nested-economics-m3a-20261108/browser-regression/` |

Counts overlap. The 95-test and 74-test regressions preceded the final narrowly
scoped chronological readiness correction. That correction preserves the legacy
forecast's inclusive numerical readiness guard while retaining the exclusive
outer cutoff. The 18 boundary tests and fresh seven-API/three-browser gates
qualify the corrected path. No full-suite, numerical provider-parity or live
readiness claim follows from these results.

The first phase/campaign regression was stopped after **52 passes / 5 failures**.
Four failures exposed the missing optional Evaluation `constraints` field in the
public request schema; that schema is corrected. The fifth was an analytical
source-book test stub that did not accept the new optional `observed_sessions`
argument. It now explicitly asserts that the legacy call uses `None`; all
original cash, breach and ranking expectations remain. The entire affected
95-test group then passed. Both logs remain under `legacy-regression/` and
`legacy-final/`.

An earlier mixed-edit cash/profile probe had **46 passes / 28 shared fixture
errors** from a backtest HTTP 500. The failure did not reproduce in isolated
sandboxed or escalated runs, and no definitive permission/root-cause claim is
made. The stable complete affected group passed 74 tests. Those probe logs and
isolated runs remain in the chronological kernel evidence directory. Two newly
added API fixtures initially supplied 11 observed sessions where their declared
8-training + 2-buffer + 2-test fold required 12; they were corrected without a
production change, then all seven API tests passed.

Earlier `browser-first`, `browser-final`, `api`, and `api-final` snapshots remain
unchanged. `browser-release` and `api-release` match the released implementation
identity `03870c3e5d243488520d9059a2f5426fdacce87a4b8678021c78ebfbd7c07a2d`.
Python compilation, both changed JavaScript syntax checks and `git diff --check`
pass. All temporary servers stopped; no persistent server was started.

Exact regression commands (use fresh temporary data roots for reruns):

```sh
.venv/bin/python -m pytest -q tests/test_research_phase_selection.py \
  tests/test_robust_economic_api.py tests/test_chronological_phase_profiles.py \
  tests/test_empty_phase_source.py tests/test_evaluation_constraints.py \
  tests/test_phase_tie_identity.py tests/test_rule_provenance.py
.venv/bin/python -m pytest -q tests/test_evaluation_optimization.py \
  tests/test_funded_optimization.py tests/test_research_campaigns.py \
  tests/test_campaign_assessments.py tests/test_robust_research_api.py
.venv/bin/python -m pytest -q tests/test_prop_cash.py tests/test_prop_phase_profiles.py
.venv/bin/python -m pytest -q tests/test_nested_economics_browser.py
.venv/bin/python -m pytest -q tests/test_robust_research_browser.py \
  tests/test_research_campaigns_browser.py
```


## Predeclared references and consolidated reliability — 2026-11-08

### M3b1 normal API evidence: predeclared references and outer reliability (2026-11-08)

This increment extends the existing IS report → robust configuration → source/plan check → normal AnalysisStore child reports → frozen outer backtests → durable research report workflow. References have explicit `baseline_train` and `baseline_outer_test` roles. They never acquire qualified membership or recommendation eligibility merely because they are measured. The coordinator saves the complete selected-family seal and all reference packages/seal before reserving any selected or reference outer strategy execution.

The final immutable normal-product library is `artifacts/reliability-baselines-m3b1-20261108/api-final/state`. Its `evidence.json` records 90 captured outputs and SHA-256 values. Before/after engine identity is `1f3f48e652be0fe1e4cd06eb0977850c02fddce93b4381d8c4a9e2c626baed27`. The two original IS sources' 16 artifacts remained byte-identical. Manual OOS history remained at zero. This history was already accessed; this demonstration makes no untouched-holdout claim.

To inspect the saved normal product (a temporary server; Ctrl-C shuts it down):

```sh
cd /Users/yx/alphaquest-research-engine-2
ALPHAQUEST_DATA_DIR="$PWD/artifacts/reliability-baselines-m3b1-20261108/api-final/state" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8042
```

Open `http://127.0.0.1:8042/#backtests/report/3dec009470f94cca89dc79a8d8aec9cc`. Expand the existing robust research panel and open either named saved research, or open the ordinary analysis links directly:

- Funded reference report: `http://127.0.0.1:8042/#backtests/prop/job/21e364d2587c4a1493638f0769c1dd8e`; campaign `9213a3c8711c4003bc52b4b54d5f9aaf`.
- Evaluation abstention/reference report: `http://127.0.0.1:8042/#backtests/prop/job/e0fe21002292495f914f13ee630e6609`; campaign `32f6cd32b3324666a4c42fd6535db66b`.

The inputs are explicitly synthetic ordinary uploaded OHLCV (`SYNTHETIC-observed-session-source.csv`). Four bars on each observed session give the one-MNQ consecutive-green strategies independently expected $300/session (one-green entry) and $100/session (two-green entry). The example has rolling eight-session training, two-session outer windows, two-session inner training/validation, and one-session purge plus one-session embargo. All calendar evidence comes from actual source sessions. This arithmetic API example explicitly lowers the required outer and calibration blocks to two and uses 400 historical replicates; those are demonstration assumptions, not recommended evidence thresholds. The browser example below retains the default five/twenty block requirements.

For Funded, the declared minimum inner mean is $200 and the neighbor gate is explicitly disabled for this narrow arithmetic example. Only the $300 configuration qualifies. Its declared optimizer sizes are 10/20 MNQ with a saved stable configuration tie policy. The predeclared reference is the failed-edge $100 configuration at one MNQ, outside that optimizer quantity grid. Both two-session outer paths yield $0 trader cash under the modeled payout rules. Expected observations: two historical outer blocks, four distinct outer sessions, one unique selected policy per fold, reference edge `FAIL`, two paired improvements of $0, paired mean $0, descriptive historical interval `[0,0]`, and `THRESHOLD_NOT_MET`. Overall reliability remains `INSUFFICIENT_EVIDENCE`; no future or live qualification is implied by a degenerate historical interval.

For Evaluation, the $1,000 minimum inner mean makes both configurations fail. Expected observations: `NO_QUALIFIED_CONFIGURATION`, no selected policy or selected outer execution, and two unmeasured abstentions. The separately predeclared one-MNQ reference is still saved and measured. Its training acquisition forecast is unresolved; its actual two-session outer replay pays exactly one $30 evaluation fee, does not activate a funded account, and remains censored. Each reference retains `recommendation_eligible:false`. No winner is forced and no acquisition mean is computed from completed-only paths.

Within each fold, inspect the selected/reference normal child links, reference edge status, frozen package and journal sequence, and ordinary outer backtest links. Download `baseline_results.json`, `reliability.json`, `reliability_folds.csv`, `baseline_comparison.csv`, `research_journal.json`, `report.json` or the analysis ZIP using the existing report links. For example:

```sh
curl -f 'http://127.0.0.1:8042/api/research-campaigns/robust/9213a3c8711c4003bc52b4b54d5f9aaf/exports/reliability.json'
curl -f 'http://127.0.0.1:8042/api/research-campaigns/robust/32f6cd32b3324666a4c42fd6535db66b/exports/baseline_results.json'
```

To reproduce a new run through the normal API, copy the saved `funded-reference/declaration.json` (or the Evaluation declaration), replace only `campaign_id` with a new `uuid4().hex`, POST it to `/api/research-campaigns/robust/preview`, review the complete profiles, policies, constraints, costs, calendar and work counts, POST it to `/api/research-campaigns/robust`, then POST `/api/research-campaigns/robust/{campaign_id}/check` and `/run`. The saved source/grid IDs remain valid in this library. Changed numerical engine identities correctly require a new declaration/review rather than launching an incompatible frozen package.

Saved rejection evidence is under each campaign example's `rejections/`: a public caller cannot inject the private reference context, a stale signal configuration ID and malformed reliability threshold reject, and an account-dependent native fixed-dollar reference rejects as unavailable instead of being silently converted to fixed size. The focused suite additionally checks duplicate definitions, bool quantities, workload bounds, altered reference package role/ID/hash/recommendation flags, source/child deletion protection, cancellation after a completed reference child with zero outer access, immutable resume, and report reopening with calculations forbidden.

The prior `api/` and `api-release/` snapshots remain unchanged. The final source uses exact integer inverse-CDF ranks for historical interval bounds, rejects malformed thresholds with HTTP422, and verifies explicit reference non-recommendation authority. `api-gate-final.txt` records four baseline API tests passed in 12.35 seconds on final source, including interval comparison, admission/role boundaries, cancel/resume and durable reopen. The broader unchanged integration paths were checked immediately before the rank repair: `api-gate-release.txt` records 20 tests passed in 45.21 seconds (`test_robust_research_api.py`, `test_robust_economic_api.py`, `test_robust_baselines_api.py`). Independent rank-boundary tests are in the final root pure gate. Separate helper tests cover conservative metric selection and explicit reference authority. The browser evidence covers positive $1,500-versus-$0 comparisons and conservative historical-mean behavior. Final full-procedure freeze/holdout access and native account-state strategy reruns remain subsequent work. No persistent server was started for API publication; TestClient lifespan shut down both normal app instances.

### Browser user journey and expected observations

The four-case final browser gate passed in 98.88 seconds after the malformed-input, reference-admission and exact percentile-rank boundary repairs. The preceding release gate passed in 98.99 seconds and remains preserved in `browser-release`. The earlier four-case gate passed in 97.32 seconds and remains preserved in `browser-final`. The first run (one fixture assertion failure, three passes in 102.47 seconds) remains preserved; its erroneous `summary.total_trades` test assertion was corrected to the native `summary.trades_taken` field. That first fixture correction required no production Python change. The browser tests use actual native DatasetStore / RunStore sources, existing prop configuration and ordinary AnalysisStore results. The calculations and journals are product outputs; independent arithmetic expectations remain in the test module.

#### Reference comparison through the existing report

1. Open the saved **SYNTHETIC dated phase arithmetic** IS backtest. Choose **Configure prop analysis → Nested research → Configure nested research**.
2. Include the saved native VWAP source on the same dataset. The anchor is `consecutive_green_hold`, green count 1 / hold 1 minute / one original NQ, with zero source commission and slippage. Four synthetic bars per weekday produce $3,000 per original NQ trade, or $300/MNQ. The VWAP source has no opening-range setup on these noon-Chicago bars, hence zero trades; it supplies meaningful multi-strategy insufficient-evidence admission, not a fabricated competing edge.
3. Set rolling outer train/test **10/7 sessions**, inner train/validation **2/2**, purge 1, embargo 0, minimum inner/outer folds 2/2. Qualification: minimum six validation sessions and trades, minimum one trade per inner fold, one-session bootstrap blocks, **zero required numeric parameter neighbors** (different strategies are not parameter neighbors).
4. Enable only **Funded**, Apex 50K EOD, fixed quantity **3 MNQ**, mean received-cash selector, receipt delay 2 calendar days. Advanced: 64 forecast paths and one-weekday sampling blocks. Keep the full captured calendar, rules, costs and seeds visible in preview.
5. Expand **Predeclared simple baselines**. Add is disabled until **Preview dates and source checks** expands the declared sources. After that first preview, add `One MNQ same-signal reference`, choose the green-count-1 signal configuration, Funded profile, fixed **1 MNQ**, required. Adding/editing the reference disables Save until a fresh complete preview. The baseline may be outside the optimizer quantity list; it remains an explicitly declared comparison.
6. Keep **Outer reliability** defaults: five required outer blocks, complete fold fraction 1, confidence .95, historical fold block 1, 1,000 bootstrap repetitions/seed 137, 20 calibration blocks, improvement threshold 0, required baseline evidence, unmeasured abstention. These are research assumptions, not universal certification.
7. Preview the full final declaration, reference membership and work totals: 36 worst-case backtests (24 inner + 6 training + 6 outer) and 6 phase forecasts including 2 references. Actual qualification can reduce that work. **Save and run research** retains the full selected-family seal and all-reference seal before each selected/reference outer-access reservation. Source inventory access has already occurred; the journal does not certify previously untouched data.

Expected observations:

- Two outer folds: Jan 20–28 and Jan 29–Feb 6, exclusive cutoffs Jan 29 and Feb 7. Green strategy PASS; native VWAP INSUFFICIENT_EVIDENCE with zero validation trades. Only the qualified signal enters the optimized study.
- At 3 MNQ, $900 per eligible day reaches the funded safety-net and first payout conditions by the fifth outer session. Gross deduction/request $1,500; lag 2 receipt dates Jan 28 / Feb 6; **received cash 1,500 per fold**, pending 0.
- At 1 MNQ, seven sessions earn 2,100, below the saved first-payout threshold; **received cash 0 per fold**. This reference is measured separately and never relabeled recommended.
- Paired received-cash improvement **1,500 per fold and mean $1,500**. Coverage is **2/5 required historical blocks**, so paired historical interval unavailable and decision **INSUFFICIENT_EVIDENCE**. Point arithmetic does not establish superiority or future cash.
- Earlier expected received cash and actual received cash are separately labeled; with this constant source their descriptive errors are 0. Payout calibration remains insufficient at 2/20 blocks, even if its displayed descriptive Brier score is 0. Independent block count is not claimed.
- Consolidated results count each outer fold once, show logical signal/size/profile stability, and distinguish conditional Monte Carlo precision, historical output variability and unquantified model/rule/execution/future uncertainty.

#### Conservative objective and exact-family boundary

Use one source and the same folds. Choose Funded fixed quantities **3, 10**, selector **Highest historical lower bound on expected trader cash**. Predeclare historical minimum 10 sessions, block 1, minimum 10 blocks, 200 historical repetitions, 8 account paths per repetition, maximum inner Monte Carlo SE 0. Default nominal confidence .90 and saved seeds remain explicit. This smaller historical requirement is a synthetic demonstration assumption, not a recommended production threshold.

Both quantities have constant earlier expected cash 1,500 in this fixture. Every resampled history therefore yields the same mean; the historical lower mean equals $1,500, account P10 happens also to equal $1,500, and inner Monte Carlo SE 0. The report explains these are distinct quantities even where numerical values coincide. Both exact policies remain frozen; no post-hoc winner or allocation is invented. Two alternatives in each of two folds still mean **two folds**, not four independent observations. Scalar aggregate, calibration and paired superiority are unavailable because the procedure retains a family with no unique action. No baseline was declared in this example, and that gap is visible.

Open the ordinary child phase report: its heading/rank criterion identifies the historical lower expected-cash mean; the same report retains point means/account distributions and the saved historical evidence requirements. Download `historical_mean_cash.json` to inspect all 200 re-estimations per candidate, source indices, seeds, addressed schedule identities, means and conditional Monte Carlo errors.

#### Insufficient history and abstention boundaries

Use the default conservative history requirement 60 sessions and 12 five-session blocks against the 10-session training window. The strategy passes edge criteria, but the economic objective cannot resolve. Both folds report **INSUFFICIENT_EVIDENCE**, no frozen policy and no outer-account execution.

- With predeclared **Unmeasured**, both fold actions remain `unmeasured_abstention`; scalar cash is unavailable.
- With explicitly predeclared **No account and no fee**, both actions are `no_account_no_fee` and procedure cash is 0. This is an explicit action convention, not an observed account performance result. No account/fees/payout/outer access is fabricated. Payout-probability calibration has zero historical pairs.

Both preserve the declared two-fold denominator, missing-baseline gap and deployment-not-qualified status. Additional Monte Carlo paths cannot manufacture historical information.

#### Downloads, preservation and inspection

Each ordinary saved research report links report JSON/ZIP, qualification CSV, full plan, economic selection, chronological replay and journal. This increment adds `baseline_results.json`, `reliability.json`, `reliability_folds.csv` and `baseline_comparison.csv`. References retain normal child phase reports and native outer backtest IDs. Reopening/reloading the saved report issues no calculation POST and preserves every downloaded byte. Desktop and 390 px evidence screenshots accompany the saved libraries.

Final holdout, deployment recommendation and native account-state strategy rerun controls are not delivered here. Provider/model parity and future performance remain unverified. Native dynamic risk policies continue to reject explicitly.

#### Saved final browser libraries and reproducible commands

All paths below are under `artifacts/research-reliability-m3b1-20261108/browser-final-exact/data/`.

| Example | Library | Source IDs | Campaign | Analysis |
| --- | --- | --- | --- | --- |
| Two-strategy/reference arithmetic | `test_predeclared_reference_com0` | `1db6796590224c46bdfc7c760535554c`, `9f7477212e164972af527658e176d95c` | `1f67421d2b55405cb28fb761aa1d5928` | `0d4e0c1c11e54fe9bc78cbaf805e60a1` |
| Conservative exact family | `test_conservative_mean_retains0` | `da6dbee78be64649975b27e0c9525819` | `281f6f9c313f4c3fb8d4216ac7bbb49c` | `587d8f7f238b46068e20c7875991e523` |
| Unresolved/unmeasured | `test_insufficient_historical_m0` | `85a06afdd3bf45059138030ec988d598` | `2fc63dbc17354ded86264c7830fac949` | `f6e752d3613343a49dc84f182105c45a` |
| Unresolved/no-account/no-fee | `test_insufficient_historical_m1` | `b147f8a732a3444d9887415dd8c6cd60` | `959e4efd30e04fddabd9612977ad8a8f` | `8fc0e56323274e279edca31c6cf1a89e` |

Each library has 12 downloaded artifacts and `browser-evidence.json` recording IDs, independent expected observations and SHA-256 values. All 48 root downloads and the additional historical-mean download were rehashed; every saved report matches the frozen engine identity `1f3f48e652be0fe1e4cd06eb0977850c02fddce93b4381d8c4a9e2c626baed27`.

| Example | Report JSON SHA-256 | Analysis ZIP SHA-256 |
| --- | --- | --- |
| Reference | `8b0492435718c9ccb49734792d8026985ff0e97787e1792c6c3156f122891bd8` | `3ac40d76a457bf0d8427d70760e22bed6155aa2f47b9164b91cc36662996b163` |
| Conservative family | `cc574a6ffa0d57db3870348d3befb09d952fd900d2c21e406942741a8ce259e7` | `dd29324d3548c47a005db46c08ac39a48afc2f8c5773db6c86da63f60f8dcd28` |
| Unmeasured | `357328e112bb5c483c2b48a7abf42f110c48578e6e0b2cf1f24a7704cabfd415` | `d839283cbb529be2554f8ba79abb7cc49781a66ac17444572e4324fed14b9832` |
| No account | `f53cb4db57f67e1f9e20a05479b6dd0722fbfbf372482309bfdd33d2c621faa2` | `ee86056ec6817628bd1e2608bb6117269e5278a6111538757ef5b450282fdfa3` |

Final run command (choose a new artifact directory to reproduce without overwriting evidence):

```sh
(
  set -e
  RELIABILITY_RUN_DIR="artifacts/reliability-recheck-$(date +%Y%m%d-%H%M%S)"
  mkdir "$RELIABILITY_RUN_DIR"
.venv/bin/python -m pytest -q tests/test_research_reliability_browser.py \
  --basetemp "$RELIABILITY_RUN_DIR/data" \
  --junitxml "$RELIABILITY_RUN_DIR/junit.xml" \
  > "$RELIABILITY_RUN_DIR/pytest.log" 2>&1
)
```

Inspect the saved reference case without recomputing:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/research-reliability-m3b1-20261108/browser-final-exact/data/test_predeclared_reference_com0" \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8012
```

Open `http://127.0.0.1:8012/#backtests/report/1db6796590224c46bdfc7c760535554c` and follow Configure prop → Nested research saved history, or directly reopen `http://127.0.0.1:8012/#backtests/prop/job/0d4e0c1c11e54fe9bc78cbaf805e60a1`. Stop this optional inspection server with **Ctrl-C**. The automated gate's owned temporary servers stopped; the product agent did not start a persistent server.

Screenshots include `predeclared-reference-preview.png`, `reference-forecast-and-observation.png`, `consolidated-outer-evidence.png`, `historical-mean-family.png`, `normal-conservative-phase-report.png`, narrow reliability/reference viewports and full-page reports. Reopen/reload generated no calculation POST and every downloaded byte stayed unchanged.

Nine existing/targeted browser checks passed in 263.69 seconds in `browser-regression`: two unresolved-history child report checks, three nested-economic cases, two inner-research cases and two phase-campaign cases. The child report correctly says historical mean evidence is unresolved, while its 64 account-path horizons are complete. It no longer confuses the new historical-evidence gate with an incomplete payout horizon. All owned temporary servers stopped. JS syntax, new test syntax and scoped whitespace checks passed. Only the existing Starlette/httpx deprecation warning appeared.

```sh
(
  set -e
  RELIABILITY_REGRESSION_DIR="artifacts/reliability-regression-$(date +%Y%m%d-%H%M%S)"
  mkdir "$RELIABILITY_REGRESSION_DIR"
.venv/bin/python -m pytest -q \
  tests/test_research_reliability_browser.py::test_insufficient_historical_mean_uses_only_predeclared_abstention \
  tests/test_nested_economics_browser.py tests/test_robust_research_browser.py tests/test_research_campaigns_browser.py \
  --basetemp "$RELIABILITY_REGRESSION_DIR/data" \
  --junitxml "$RELIABILITY_REGRESSION_DIR/junit.xml" \
  > "$RELIABILITY_REGRESSION_DIR/pytest.log" 2>&1
)
```

Release note: the nine regression cases passed before the final malformed-input/reference-admission/exact-rank boundary repairs. The four new release cases, including both unresolved child-report checks, passed against the final source after those repairs. Previous `browser-first`, `browser-final`, `browser-release` and `browser-regression` outputs remain unchanged. No broad full-suite or provider-parity claim is implied.

The extra conservative child artifact `historical_mean_cash.json` has SHA-256 `449034d4b7c3a2e08f8b81b018cdb30444f7927ecaa59bb4783afed8959f9dab`. Final screenshot review covered the reference mobile summary/comparison, reference forecast/outer observation, historical-mean family, and unresolved child report.

### Independent arithmetic and validation scope

The final pure/contract gate passes **116 tests in 5.64 seconds**. Its log and
JUnit are under `artifacts/reliability-m3b1-20261108/root-final/`. Independent
oracles include predicted cash `[100,200,300]` versus observed `[80,260,210]`
(mean error −50/3, MAE 170/3, RMSE √(12100/3)); reference cash `[60,220,200]`
(improvements `[20,40,10]`, mean 70/3, below a declared 30 threshold); and
probabilities `[.2,.7,.9]` with outcomes `[0,1,1]` (Brier .14/3, three historical
blocks, still insufficient). A completed 70-fee acquisition and censored 90-fee
attempt retain 160 total fees and no survivor-only acquisition mean. Missing
forecasts retain known cash. Selected families do not create implicit portfolios.

Exact inverse-CDF rank tests independently cover 200/1,000/10,000 repetitions:
at 95% with 1,000 ordered values `0…999`, the bounds are observations 25/975,
values 24/974. Integer ranks avoid moving the lower bound one observation because
of floating subtraction. High confidence without at least five expected draws
per tail yields insufficient evidence. The conservative Funded estimator uses
its own exact family-adjusted rank, recorded history indices and Monte Carlo
precision checks; its analytical example separates a positive lower estimated
mean from a zero single-account p10.

The stable existing Evaluation/Funded optimizer, campaign, frozen assessment,
profile and chronological-replay gate passes **107 tests in 314.84 seconds**:
`artifacts/reliability-m3b1-20261108/legacy-release/`. It preceded only the final
malformed-threshold/reference-authority and descriptive interval-rank repairs.
Final affected API/browser/pure gates above cover those changes. Thirty-six
default dated Funded cases independently compare every path value and schedule
hash with immutable commit `50df431`; all match
(`artifacts/reliability-m3b1-20261108/funded/default-parity.json`). Python
compilation, both changed JavaScript syntax checks and whitespace checks pass.
These overlapping targeted gates are not a full-suite or provider-parity claim.

Root independently rehashed all 90 final API captures and 49 final browser
downloads against the current engine identity; verification records are in
`root-final/`. Earlier failed/probe evidence remains: the initial mixed pure gate
had 42 passes and one optional-attribute compatibility failure (fixed, then
rechecked); the initial legacy command named a nonexistent test module and ran
no tests; the first browser gate had one test-fixture key error and three passes.
The first API probe also crossed a pre-freeze source edit during cancellation;
stable integration and final affected gates passed afterward. None of these
earlier runs is relabeled clean. All owned temporary servers stopped.

The whole requested goal remains incomplete. Native account-state strategy
execution/forecasting, full-procedure freeze/holdout/current development selection,
optional lifecycle comparison, forward monitoring and final full qualification
are separate remaining increments. No last-fold policy, reference comparison or
confidence label is a deployment recommendation.

## Native chronological strategy and account replay — 2026-11-08

Scope: a usable deterministic historical replay in the normal product. It closes
native entry/sizing/execution integration for the admitted MNQ/VWAP subset. It
does **not** complete native Monte Carlo, native economic search, frozen outer
campaign integration, final procedure/holdout selection or forward monitoring.
Reports say `HISTORICAL_SCENARIO_ONLY`, `native_forecast_available: false` and
`production_qualified: false`. Provider-rule review and modeled rule values are
saved; numerical/provider equivalence is not inferred from these examples.

The implementation uses the existing execution engine, phase transition owners,
RunStore, AnalysisStore, worker and prop routes. The native phase mode re-executes
actual strategy callbacks. It accepts/skips quantity before VWAP commits latches
and its daily entry allowance. The quantity controller receives the completed
signal close and causal stop, not the next open. Actual fills, gaps, commission,
stop exits and subsequent eligibility belong to the normal execution loop.
`native_money.py` preserves exact native money while retaining the legacy float
path; the cash bridge keeps provider state distinct from ordinary trading equity.

### Independent expected observations

All sources in this demonstration are explicitly synthetic, true MNQ price bars
(tick 0.25, point value 2), with every minute from previous-day 17:01 through 16:00
Chicago and no commission/slippage in these particular arithmetic examples.
The source backtest starts with $10,000 trading equity. Provider percentage-risk
bases use the declared $50,000 account, never that source reporting capital.

| Scenario | Independently expected actual results |
| --- | --- |
| Three-session current-balance risk 0.2% | Decision closes 118; stops 113, 113, 108. Planned unit losses $10, $10, $20. Balances $50,000, $49,900, $50,080 before decisions; whole quantities 10, 9, 5; trade nets −$100, +$180, +$100. Ordinary final equity $10,180; provider balance $50,180. |
| Same bars, fixed dollar risk $100 | Quantities 10, 10, 5; nets −$100, +$200, +$100; provider balance $50,200. |
| First next-open gaps from decision 118 to 120 | First accepted quantity remains 10 because 120 was unavailable at decision time. First loss $140; later quantities 9, 5 and gains $180, $100. Provider balance $50,140. Per-contract fill-to-known-stop risk increases $4. |
| Native skip changes eligibility | Original one-contract source takes an early −$10 trade and exhausts its one-trade allowance. A $1 budget skips the 5-point stop, keeps eligibility, then accepts 2 contracts at the later 09:06 close 118 with known stop 117.75. Actual 09:07 fill 118, target 121, net $12. This later opportunity is produced by real strategy execution, not fabricated by resizing a completed trade. |
| Independent Evaluation, same three sessions | Native quantities 10, 9, 5 and trading net $180; purchase fee $30 paid, activation fee $0, acquisition incomplete/censored. No pass-probability or mean acquisition cost is invented from this single path. |
| Seven-session fresh Funded payout | Signal 118, target 268, fixed 3 MNQ: 7 × $900 = $6,300 trading profit. First gross request/deduction $1,500 on 2026-01-09; modeled two-calendar-day receipt $1,500 on 2026-01-11. Original trading equity $16,300; provider balance $54,800; pending $0. The request, deduction and receipt remain separate events. |

Controller/unit cases additionally check actual floor touches and gap losses,
commission pushing a shallower daily exit through the account floor, provider
size tiers, cancelled entries, account retries and exact prior-loss offsets,
pending receipt cutoffs, no-trade coverage, default-path parity, strict flat EOF
and session boundaries, and separate source versus future-entry facts. A $13.50
planned unit loss under a $100 budget accepts 7 (planned $94.50); a later gap
produces actual loss $108.50 without changing the accepted quantity.

### Final API evidence and boundaries

`artifacts/native-sizing-m2c-20261108/api-final/` contains a complete normal-product
library for each arithmetic case, 12 passing API checks (50.51 seconds), test log,
JUnit, before/after engine identity and independent artifact verification.
Both identities are
`e2fdb34805ce3239f98580af9b621fa0fd3c088c79d64f0efc1da4743260a5f2`.
`verified-evidence.json` rehashes 52 saved analysis outputs plus each controlled
child's report/trade/equity/risk/decision/control files. The separate cache
boundary test intentionally corrupts its own test artifact and proves a new
analysis is created; it is not one of the four verified example libraries.

| Library under `api-final/data/` | Original IS report | Analysis | Controlled child |
| --- | --- | --- | --- |
| `test_real_native_report_workfl0/library` | `8d1558fee4f44783b1fb3a3adcf9e7ef` | `7f1842601b9a4ee1855308d2e7a67f9a` | `6592c13017dc4cea8125735ab27cd5f5` |
| `test_real_native_report_workfl1/library` | `77a5b0af462f4e2d83d0be1ce45953ab` | `0fdc6160c2414539a089ee1831c8a17d` | `b4219f4e24284027bd06a7aa262a7409` |
| `test_real_native_report_workfl2/library` | `7d65f3230e594a1680df59c5f11a22e8` | `941f3fc017b046cca280dbc01b565f1c` | `367de20db8c747e8af7bb488471c0f58` |
| `test_real_native_report_workfl3/library` | `364c2fba719b44bcb160d3abaf24d4c5` | `d290dd3398de4a5482de70548180108d` | `58d17cc8382a4626972f4bb09c35cae9` |

Checks reject an unknown phase, boolean size, opposite-phase inputs, implicit
Funded receipt assumptions, unsupported sampling, replacement costs, changed
planning costs, out-of-source session boundaries, NQ substitution, incompatible
MNQ point value, local strategy sizing, disabled EOD flat and a missing minute.
During execution, source and analysis deletion return 409. Controlled children
cannot become unconstrained phase sources or undergo generic detail/risk
reproduction. Repeated identical requests reuse a verified result; damaged
artifacts do not. Original source manifest and trade bytes remain unchanged.
The application is closed and reopened before asserting byte-identical saved
report JSON and ZIP; reopening performs no recomputation.

To inspect the first saved API case without recalculating:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/native-sizing-m2c-20261108/api-final/data/test_real_native_report_workfl0/library" \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8012
```

Open `http://127.0.0.1:8012/#backtests/report/8d1558fee4f44783b1fb3a3adcf9e7ef`
and choose Configure prop analysis, or reopen the saved result directly at
`http://127.0.0.1:8012/#backtests/prop/job/7f1842601b9a4ee1855308d2e7a67f9a`.
Stop an optional inspection server with **Ctrl-C**. No persistent server was
started for this API gate; TestClient lifespans closed their workers.

### Native regression scope and intermediate failures

The final frozen controller/execution gate passed 72 tests in 24.43 seconds, the
existing kernel gate passed 98 in 5.94 seconds, and 24 fixed cases matched immutable
commit `60a0cd4ea587813907d0f25dd3babe00416e3cf1` exactly for both current Python
and rebuilt Cython kernels (full account/path/RNG outputs, 100 paths per case).
Reproduction script, archived pre-native sources, hashes and case results are
under `artifacts/native-sizing-m2c-20261108/kernels/`. The earlier execution gate
passed 203 tests in 14.97 seconds; these scopes overlap and must not be summed as a
single unique test count.

The source calendar and close-boundary regression passed 88 tests in 6.03 seconds
(`calendar-release/`). Existing Evaluation/Funded optimizer, phase-profile and
chronological-profile regression passed 86 tests in 159.06 seconds
(`phase-regression/`). Final API checks passed 12 as recorded above. Compileall
and whitespace checks passed. These are targeted qualification gates, not a full
repository baseline or live-provider qualification.

Earlier attempts are retained rather than represented as clean: the initial
calendar run hit the sandbox's local multiprocessing socket restriction; the
permitted rerun then found an outdated test stub that did not accept the new
explicit calendar symbol. Updating that test-only stub preserved its original
snapshot-immutability assertion and yielded the 88-pass result. Initial API
probes caught fixture Decimal serialization/range-step mistakes, and an actual
admission mistake requiring dataset-wide regular spacing despite legitimate
maintenance gaps. The final admission proves minute cadence within each session.
One owned source-generation test was stopped because ordinary single-backtest
creation invoked unrelated default legacy simulations; the demonstration now
uses the existing one-configuration grid with strict `automatic_prop: false`.
No user process, existing dataset or earlier report was stopped or removed.

An earlier mixed kernel run had three test-only Decimal string-format mismatches
during concurrent test edits; the final scoped kernel/controller gates passed.
Browser history is recorded with the final product evidence below. Numerical
Python was held fixed during the final API/browser gates, at the captured engine
identity. Rebuilt binaries match their source; historical reports retain their
original identity and bytes.

To reproduce backend checks into a **new** evidence directory:

```sh
(
  set -e
  NATIVE_CHECK_DIR="artifacts/native-recheck-$(date +%Y%m%d-%H%M%S)"
  mkdir "$NATIVE_CHECK_DIR"
  .venv/bin/python -m pytest -q tests/test_native_replay_api.py \
    tests/test_native_account_execution.py tests/test_native_phase_control.py \
    tests/test_session_calendar.py tests/test_inferred_session_close.py \
    --basetemp "$NATIVE_CHECK_DIR/data" \
    --junitxml "$NATIVE_CHECK_DIR/junit.xml" \
    > "$NATIVE_CHECK_DIR/pytest.log" 2>&1
)
```

The calendar grid check requires local worker sockets. Run it in the ordinary
local environment, or grant the test process that capability if a sandbox blocks
it. Never reuse an existing evidence directory as pytest's `--basetemp`, which
pytest clears before starting.

### Native browser journey and saved product demonstration

This increment runs the actual native MNQ VWAP strategy with one Evaluation or fresh Funded controller. It does not provide native Monte Carlo forecasting or native policy selection. All examples below are explicitly synthetic arithmetic demonstrations, not strategy-edge, provider-parity or deployment evidence. Earlier saved reports remain unchanged.

Final evidence: `artifacts/native-sizing-m2c-20261108/browser-release-source`. The final six browser cases passed in 35.06 seconds. All 114 saved downloads were independently rehashed, including exact source CSVs against dataset SHA-256 and every analysis artifact against its normal report manifest. Each reopened analysis issued no POST. Every temporary server was owned by the portal fixture and stopped on exit. Desktop and 390 px viewport screenshots were inspected. Engine identity remained `e2fdb34805ce3239f98580af9b621fa0fd3c088c79d64f0efc1da4743260a5f2` before and after the gates.

Existing imported sizing campaigns and ordinary reports: `tests/test_phase_sizing_browser.py tests/test_reports_browser.py`, 18 passed in 61.98 seconds. The native-only summary branch was then covered by the final six native cases. `browser-final` is preserved with 6 passed assertions and 6 teardown errors from an older research view assuming an IS/OOS plan on the controlled child. That UI assumption was corrected. `browser-release` and `browser-release-ui` are also preserved; final exact-source reproduction artifacts are in `browser-release-source`.

#### Open the saved normal product

Start the ordinary application with one evidence library. For the main Funded percentage example:

```sh
cd /Users/yx/alphaquest-research-engine-2
ALPHAQUEST_DATA_DIR="$PWD/artifacts/native-sizing-m2c-20261108/browser-release-source/data/test_native_percentage_balance1" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8018
```

Open `http://127.0.0.1:8018/#backtests/report/fcfe70cb868f4c1e8db387951567973b`. This is the original saved native IS report, created through the normal one-configuration grid with `automatic_prop:false`; unrelated legacy automatic simulations were explicitly disabled. The default automatic behavior is unchanged. Original source trades are one MNQ with net −10, +20 and +20 USD.

Choose **Configure prop analysis**, expand **Configure native account-state replay**, select **Fresh Funded account** and the Apex 50K EOD profile. Leave session dates blank to use the complete saved IS session coverage. Set hard user cap to 40 MNQ, sizing mode to **Account-state sizing policy**, kind to **Percentage risk**, risk percent to `0.2`, reference to **Current account balance**. Keep the declared planning costs at the actual source values: zero slippage and zero commission. Current native admission requires these planning values to match saved execution costs. Keep minimum 1, policy maximum 40, optional cushion guards off. Set receipt delay to 2 calendar days and **Unrounded model entitlement**.

Choose **Check native source**. Expect MNQ, 3 complete observed sessions, 4,140 observed minute bars, CME dates January 5–7, 2026, future-fill sizing **No**, costs charged once **Yes**, and a versioned reviewed calendar. Choose **Run native replay**. An identical saved request can reopen its durable result; changing a supported declaration creates a separately identified analysis.

The native result shows decision balances 50,000 / 49,900 / 50,080, known close 118 with stops 113 / 113 / 108, planned unit risk 10 / 10 / 20, accepted quantities 10 / 9 / 5 and actual trade nets −100 / +180 / +100 USD. Final provider balance is 50,180; ordinary trading equity is 10,180 because its original backtest initial capital is 10,000. No trader payout was received or pending. **Open actual controlled backtest** shows the actual new trades; it is labeled a native historical replay, not a new IS/OOS declaration. The parent source remains unchanged.

Open the durable analysis directly at `http://127.0.0.1:8018/#backtests/prop/job/cee2d2df97d6449fb4884e0b4d438d3f`. Download report JSON, analysis ZIP, actual trade/equity CSV, original signal decisions JSONL, native account-control events, sizing decisions, session states, cash ledger and provider review from ordinary report routes. Reloading this URL does not resimulate. Stop the server with **Ctrl-C**. No persistent demonstration server was left running by the agent.

#### Independent expected comparisons

Use the corresponding library below, keeping port 8018 and stopping the previous server first. Open its source report and use the same ordinary configure/check/run controls, or open the saved analysis directly.

| Case | Declaration | Expected actual observations |
| --- | --- | --- |
| Evaluation percentage | 0.2% of current balance, cap 40, evaluation fee $30, activation $40 | Same 10 / 9 / 5 quantities and $180 trading net. $30 evaluation fee paid, $0 activation, acquisition incomplete and censored. Trading profit is not trader cash. |
| Fixed dollar risk | $100, cap 40 | Quantities 10 / 10 / 5 from known stop widths; nets −100 / +200 / +100; final provider balance 50,200. |
| Entry gap | 0.2% current balance, first fill 120 instead of decision close 118 | First accepted quantity remains 10; actual first loss is $140 and fill-to-stop risk increases $4 per MNQ. Later quantities 9 / 5; final balance 50,140. |
| Skipped then eligible | $1 planned risk, one observed session | Four opportunities are skipped below minimum quantity. At 09:06 Chicago the known stop is 117.75 vs decision 118, unit risk $0.50, so 2 MNQ are accepted and filled at 09:07. Target 121 yields $12. The earlier skips preserve the one accepted-entry allowance. Original fixed-size source instead took the early −$10 trade. |
| Payout separation | Fixed 3 MNQ, seven sessions January 5–13, lag 2 calendar days | Seven actual $900 trades = $6,300 trading profit. $1,500 gross withdrawal requested/deducted January 9; modeled receipt January 11. Cash received $1,500, pending $0, provider balance $54,800. Ordinary backtest equity remains $16,300; withdrawal never reduces that trading ledger. |

The main browser boundary test enters first CME session `2026-01-04` with last `2026-01-07`: the source check rejects the unobserved session and Run stays disabled. Clear both dates to restore full coverage. Source/cost/strategy guard coverage also exists in `tests/test_native_replay_api.py`: NQ or wrong point value, a missing observed minute, local strategy volatility sizing, disabled EOD-flat, changed planning costs, invalid phase/caps, missing receipt declaration, mismatched phase fields and forecast sampling inputs reject. Those are rejection checks, not inferred support.

#### Exact saved inputs and identities

Each case directory contains `SYNTHETIC-MNQ-observed-bars.csv` downloaded from the actual dataset endpoint, `original-source-report.json`, `source-research-declaration.json`, `browser-evidence.json`, normal analysis downloads and screenshots. The CSV includes one explicitly synthetic reserved OOS row after the full synthetic IS sessions. That final row is not executed by native replay and is not evidence of untouched market data. The source split uses source-timezone UTC dates; the native form uses CME session dates. Use the saved split dates exactly when rebuilding the source.

Main three-session UTC split: IS January 4–7, OOS January 8, 2026. Native CME sessions are January 5–7. Skip split: IS January 4–5, OOS January 6; native session January 5. Payout split: IS January 4–13, OOS January 14; native sessions January 5–13. All source datasets declare symbol MNQ, tick size 0.25, point value 2, timezone UTC. Use the exact strategy parameters and execution settings in `original-source-report.json`; local volatility sizing is disabled, EOD-flat enabled, one accepted entry per strategy reset day, and reset time 07:00 Chicago.

| Case library suffix | Original source ID | Analysis ID | Actual controlled backtest ID |
| --- | --- | --- | --- |
| `test_native_fixed_dollars_reac0` | `e131186c89864746b16eed8977f33fb2` | `19382c6c96b94ef78128825c1b8d5142` | `8056a6b70fdc4df6a2d72f7171404ba4` |
| `test_native_gap_keeps_causal_q0` | `96535b508bbc4eef88e2cfc68cefaf8b` | `ffead0845b4c45e4a8ea01d9ca95f899` | `81b7326e43504a409944cfce759a2b16` |
| `test_native_payout_keeps_tradi0` | `8bf099c5f54347f9908c629e2f05dcdf` | `cff7f2400639450aa0edd43c878d3578` | `ae4dda28f1004694b483847fee0ffefc` |
| `test_native_percentage_balance0` | `f31438dddcac4145abec62bac982acc7` | `1ec811b297804872be04383208c80071` | `eddb3e12c18149eb82f13eb516a98af7` |
| `test_native_percentage_balance1` | `fcfe70cb868f4c1e8db387951567973b` | `cee2d2df97d6449fb4884e0b4d438d3f` | `879cb9fe93814056b491ef7c71f96781` |
| `test_native_skipped_signal_pre0` | `44bcda4ef301498d8cc5c5dfe7c44288` | `95473a4617d14db3a4c53c978e1349da` | `961d74c90eae41e38765d48beb399dc7` |

All suffixes are under `artifacts/native-sizing-m2c-20261108/browser-release-source/data/`. Full SHA-256 values for every case are in `artifacts/native-sizing-m2c-20261108/browser-release-source/verified-evidence.json` and the per-case `browser-evidence.json`.

Main Funded report SHA-256: `0852b200555ecdda2e4ed71f78bbea21374c693e00a6e6f15ecae2165241ab73`; ZIP: `9f8eec81d729af606e8071aadbb590a969f6d357b242cb60f4145a5989f0e2d5`; exact dataset: `0adecad3c095cc7cd9650a6e82d5529b83718d5e700939d70b4d10fa0ae7badb`.

Payout report SHA-256: `a7845a5d6c2cd8609710b66680f349846c216850187a40ebb9fcfebfbeac051c`; ZIP: `8b09b3851b368d3ac534341c1e39ea0b65f38f5474b3f49337c69ad42f0fcbf5`; exact dataset: `5d191f992bd728706a5e6c7ce34e46f8b8edea9906c3a06bdf18ad3a91f614e0`.

#### Reproduce the automated product check

Use a fresh output path to preserve existing evidence:

```sh
(
  set -e
  cd /Users/yx/alphaquest-research-engine-2
  aq_native_run="/private/tmp/alphaquest-native-reproduce-$(date +%Y%m%d-%H%M%S)"
  mkdir "$aq_native_run"
  .venv/bin/python -m pytest -q tests/test_native_replay_browser.py --basetemp "$aq_native_run/data" --junitxml "$aq_native_run/junit.xml" > "$aq_native_run/pytest.log" 2>&1
)
```

The fixture creates normal local datasets, a normal saved single-configuration grid source, normal prop analyses and actual controlled child backtests. It uses no demo-only route or product oracle. Chromium needs process access on this macOS environment. Each owned server is stopped by the fixture, including failures. This browser gate is a focused workflow/evidence check, not a full repository or provider-certification claim.


## Native contiguous-block forecasts — 2026-11-08


The existing native prop form now optionally adds a native Monte Carlo forecast to its actual historical replay. Both results are retained separately in the same normal AnalysisStore report. The historical controlled RunStore child remains a real observed chronology; sampled source blocks never become a fabricated historical dataset or child backtest. Native policy optimization, campaign integration, historical-mean refitting and final procedure qualification remain pending.

Final evidence is `artifacts/native-forecast-m2d-20261108/browser-final`: four browser cases passed in 69.12 seconds. The six existing historical native browser cases passed separately in 38.03 seconds under `artifacts/native-forecast-m2d-20261108/browser-regression`. All 84 captured final downloads were independently rehashed, exact saved source CSVs match dataset SHA-256, each report file matches its manifest, all four reloads issued no POST, and retained detail IDs are exactly 0 and 1 while all four paths remain in metrics and schedules. Screenshots of declarations, source/model clocks, dynamic outcomes and censored means were inspected at desktop and 390 px widths. Every owned temporary server exited; no persistent demonstration server remains running.

Engine identity before and after: `619d0bae83c621462f869e06b0f5fd52b3bb84d4a0c07c356560a36083bc8ba9`. The synthetic fixtures are arithmetic and workflow demonstrations, not evidence of market edge, future precision or provider parity. Zero Monte Carlo standard error on the constant source pool does not certify the model or future performance.

### Reopen and reproduce the Funded example

Start the ordinary application with the saved Funded library:

```sh
cd /Users/yx/alphaquest-research-engine-2
ALPHAQUEST_DATA_DIR="$PWD/artifacts/native-forecast-m2d-20261108/browser-final/data/test_native_forecast_is_separa0" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8019
```

Open `http://127.0.0.1:8019/#backtests/report/29f8a3430541461196361d22a46a016d`. This original source was made by the normal one-configuration grid with `automatic_prop:false`, actual MNQ symbol/tick/point values, EOD-flat enabled and local strategy volatility sizing disabled. It has seven complete synthetic minute sessions. Automatic legacy reports were explicitly disabled for this grid; their product default and historical calculations are unchanged.

Choose **Configure prop analysis** → **Configure native account-state replay**. Select **Fresh Funded account**, Apex 50K EOD, **Fixed MNQ quantity** and 3 MNQ. Leave source session dates blank for the saved complete IS coverage. Actual execution and matching planning costs are zero slippage and zero commission. Receipt delay is 2 calendar days, **Unrounded model entitlement**.

Check **Add native Monte Carlo forecast** and enter:

- Total paths `4`; seed `1729`; contiguous source sessions per block `1`.
- Modeled horizon `9` calendar days; retain detailed paths `2`.
- Modeled calendar declaration `explicit-demo-weekdays-v1`.
- Start date `2026-01-26`; coverage end `2026-02-05`; timezone America/Chicago.
- No additional full closures or early closes for this explicit synthetic modeled-calendar example. The target calendar is user-declared and unverified; it is not copied from reviewed source-calendar metadata.

Choose **Check native source**. The actual source shows 7 observed complete sessions / 9,660 minute bars. The forecast plan shows 7 complete one-session source blocks, 4 total paths in one equally weighted start cohort, modeled cutoff `2026-02-04` exclusive and 7 modeled open sessions. Retained detailed IDs are `0, 1`, chosen before outcomes. Expected planned work is 38,640 source-validation bars + 104,880 feature-only warmup bars + 38,640 sampled execution bars = **182,160 total bar work**, with 26,189 schedule bytes and a 39,567,360-byte capture allowance. These are backend plan values, not frontend estimates or a claim that every planned trade occurs.

Choose **Run native replay**. The original historical part remains January 5–13, with $6,300 trading profit, $1,500 gross withdrawal and modeled historical receipt on January 11. Below it, **Native Monte Carlo forecast** shows a separate modeled target horizon: each of four paths realizes seven $900 trades, a $1,500 request/deduction on January 30 and modeled receipt February 1. Mean received cash is $1,500; mean pending cash is $0; mean gross deductions are $1,500; mean provider equity **change** is $4,800, equivalent to nominal balance $54,800 from the declared $50,000 basis. All four paths enter these means. Their constant arithmetic gives conditional MCSE 0; the UI explicitly limits its interpretation.

Expand **Inspect all modeled path summaries** and **Inspect retained native paths and both clocks**. Selecting path 1 changes presentation only. The source dates may repeat or move backward, while modeled target sessions remain chronological. Original source fill timestamps/prices remain distinct from modeled provider/cash dates. Warmup is prior-only feature processing and creates no trades, fees or provider activity. Provider state and actual trading cash continue across sampled blocks.

Open the durable analysis directly at `http://127.0.0.1:8019/#backtests/prop/job/0f18e55474c5489eb3f0de917ff948a1`. Its actual controlled backtest is `a0137f073a61462c8013db555a45cf63`. Reloading the saved analysis executes no POST or native bars. Download the normal report JSON/ZIP and dedicated `native_forecast_plan.json`, `native_forecast.json`, `native_forecast_paths.json`, `native_forecast_schedules.json` and `native_forecast_captures.json`. Historical `trades.csv`, `equity.csv` and cash ledger remain separate files. Stop the server with **Ctrl-C**.

### Independent Evaluation and dynamic-sizing observations

Switch the evidence library to the applicable suffix below, restart the same normal server, and open its source or saved analysis. All dates and inputs remain inspectable in the captured request JSON.

| Example | Inputs | Independent expected result |
| --- | --- | --- |
| Evaluation resolved | Same seven-session source and 3 MNQ; evaluation fee $30, activation $40; same forecast dates/horizon | Every path passes January 29, pays activation January 30 and reaches funded readiness February 2. All-path acquisition mean $70, elapsed calendar mean 7 days, 4 completed / 0 censored. No Funded outcomes enter Evaluation. |
| Evaluation censored | Same setup, horizon 3 calendar days, cutoff January 29 exclusive | All four paths pay $30, none acquires a funded account, observed duration 3 days. Eventual acquisition cost/time means and their MCSE are unavailable with `unresolved_acquisition_censoring`; restricted all-path fees remain $30. No successful-only statistic or fees/pass ratio is substituted. |
| Dynamic Funded forecast | Three-session source; hard cap 40; risk policy 0.2% current balance; 4 paths, seed 1729, block 1, horizon 3, same target start/coverage | Source block indices are [1,2,0], [1,0,0], [2,2,0], [0,1,1]. Accepted quantities are [10,5,10], [10,10,10], [5,5,10], [10,9,10]. Path provider equity changes are $200, $0, $100, $280. Equal-path mean $145 and conditional MCSE 60.759087111860616. Received and pending cash are $0. Historical source chronology independently stays quantities 10/9/5 and $180 trading profit. |

Dynamic arithmetic uses the known source outcomes and stop widths: source block 0 has unit net −$10 / planned unit risk $10; block 1 +$20 / risk $10; block 2 +$20 / risk $20. Quantity is the whole-contract floor of 0.2% of the current provider balance divided by unit risk, under the saved caps. The oracle lives in tests and does not call the production sizing or aggregate helper.

The report labels account cash P10/median as outcome distributions, distinct from the estimated mean's conditional Monte Carlo error. A Funded account can remain open at cutoff while finite-horizon cash observation is complete. Historical-law uncertainty, execution/liquidity, provider rules, settlement and future uncertainty are not measured by these MC standard errors.

### Rejection observations through the same form

Before the valid Funded check, the browser verified these declarations reject and keep Run disabled:

1. Modeled start January 13, on the last admitted source session.
2. Two distinct starts but total paths 3, so equal start-cohort allocation is impossible.
3. A modeled January 27 early close at 13:00 with no compatible observed source block shape. The date is not silently removed and no lucky redraw repairs it.
4. Retained detailed paths 5 with total paths 4.

Changing a forecast or calendar field invalidates the previous check. An execution failure fails combined analysis publication rather than silently dropping the forecast; any already-created historical child remains independently inspectable. Censored Evaluation with null acquisition means is a valid completed result, not such an execution failure.

### Exact source bytes, identities and split dates

All fixture input rows are synthetic. `SYNTHETIC-MNQ-observed-bars.csv` is downloaded from the actual dataset endpoint and matches its saved SHA-256. Its final reserved synthetic OOS row is unexecuted; it is included so a fresh source recreation can use the exact original declaration. Use `source-research-declaration.json` and `original-source-report.json` for original parameters, costs and split dates.

For the three constant-pool cases, source timezone UTC IS is January 4–13, 2026 and reserved OOS January 14; admitted CME sessions are January 5–13. For the dynamic case UTC IS is January 4–7 and reserved OOS January 8; admitted CME sessions are January 5–7. Modeled forecasts start January 26, after all admitted IS sessions. Do not confuse these three clocks/date declarations.

All suffixes below are under `artifacts/native-forecast-m2d-20261108/browser-final/data/`.

| Library suffix | Original source | Combined analysis | Actual historical child |
| --- | --- | --- | --- |
| `test_native_forecast_dynamic_q0` | `0b53e6a599f04052bfba2b887ee2db60` | `81d08647db0d4ccb8ef08f5b37f4cd4f` | `4d0888be9b624d42a6e7ee52ef29f0a8` |
| `test_native_forecast_is_separa0` | `29f8a3430541461196361d22a46a016d` | `0f18e55474c5489eb3f0de917ff948a1` | `a0137f073a61462c8013db555a45cf63` |
| `test_native_forecast_is_separa1` | `f5dfec353fcf41f4a9be66a8cf4c9977` | `e5ecc4a663a04af7813d26edabf43f22` | `2fd92a591d9a4a9a80b899e2675638bc` |
| `test_native_forecast_is_separa2` | `55effe7affb740e9b7f0c3faf38ad0e8` | `55fd65b3360c4a45ac1945b6383a2a68` | `086bf0e1abd64723b9d05d24ac08e04d` |

Full hashes, schedules, work estimates, expected values and absolute library paths are in `artifacts/native-forecast-m2d-20261108/browser-final/verified-evidence.json`, with per-case downloads in `browser-evidence.json`.

Funded report SHA-256: `470284a500dc7adee68de0abc7cb7225a940bc71cba75b7ced07cd5ff8e3d253`; ZIP: `6b4910e6b8f8f62964443254a834f2572fabaf77e44e7e41731bdd7cafb55266`; forecast: `4ab7ebad266258fd7d0c8b41ee616a34d549f42b46863b0409158d38dffd4500`.

Dynamic report SHA-256: `df3fbff345faba8020b5a8eb3a860a79e62de265f7945c4efb272db36f7cb929`; ZIP: `838ff3b4fe384c4d7ff5dfae8725477c6486cc51f83b9dc0d0dacf46b1b6eabb`; forecast: `90c23c62e035fd27937ef76781a1b5bdce1f693e65a3c17d1af2018fa31d04fc`.

### Repeat the focused product gate without replacing saved evidence

```sh
cd /Users/yx/alphaquest-research-engine-2
aq_forecast_run="/private/tmp/alphaquest-native-forecast-reproduce-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$aq_forecast_run"
.venv/bin/python -m pytest -q tests/test_native_forecast_browser.py --basetemp "$aq_forecast_run/data" --junitxml "$aq_forecast_run/junit.xml" > "$aq_forecast_run/pytest.log" 2>&1
```

Historical native regression: run `tests/test_native_replay_browser.py` with a separate fresh basetemp/log/XML directory. Chromium needs process access in this macOS environment. Portal fixtures create only owned temporary local servers and stop them on exit, including failures. These focused browser checks do not claim full-suite success, native optimizer integration or provider/deployment certification.


### Additional backend gates and earlier probes

Final API integration is `artifacts/native-forecast-m2d-20261108/api-final/`:
17 passed in 142.69 seconds, including historical API regressions, all-path
cash/censoring, blocks 1 and 5, unavailable block-10 pools, incompatible early
closes and rejection before reservation. Engine identity before/after matched.
Final focused contracts/adapter/phase owners/observed controllers are in
`pure-final/`: 99 passed in 63.26 seconds, including strict calendar arrays,
resource bounds, report-plus-components publication size, source/prefix hash
verification, rejected schedule tampering, phase separation and Python/compiled
observed controller checks. The independent owner gate also passed 58 checks;
it overlaps the final focused gate and is not an extra independent baseline.

Earlier probe failures remain saved. An API run correctly rejected a concurrent
production-code identity change; it was repeated only after the code freeze.
A positive contract fixture initially declared coverage two days short of its
latest cutoff; the fixture was corrected, preserving the production rejection.
Independent review tightened calendar array types and included embedded report
JSON in publication size before the final gates. These are targeted checks;
provider parity, whole-platform qualification and native policy selection are
not claimed.

Existing Evaluation/Funded/profile regression: 68 passed in 149.02 seconds
(`existing-phase-regression.log/.xml`). Root independently rehashed 64 API
component files and 84 browser downloads across eight saved analyses; verified
all-path retention and inspected narrow dynamic/censored views
(`root-verification.json`). Python compilation, changed JavaScript syntax checks
and `git diff --check` passed. The only warning in the API/legacy phase gates is
the existing Starlette/httpx deprecation. No persistent server was started.


# Native phase optimization and complete-procedure verification — 2026-11-08

Release evidence identifiers and checks are appended by the final evidence audit. Earlier isolated browser probes remain preserved and are not release-engine evidence. All synthetic sources use normal dataset/backtest/report routes. The examples test arithmetic, causal state, immutable selection and the product journey; they do not establish market edge, provider parity or production trading readiness.

## Native independent campaign

Open a saved MNQ VWAP source report, choose Configure prop analysis, then the independent Evaluation or Funded campaign. Select **Actual native strategy reruns · MNQ** as the execution model. This explicitly changes the sampling law: original observed source-session blocks and their prior-only warmup rerun the real strategy, while provider state continues between modeled target sessions. No saved trade is resized after its outcome.

For the seven-session constant-profit source, compare fixed quantities **1, 3 MNQ** in Funded and **3, 10 MNQ** in Evaluation. Set total paths **4**, seed **1729**, source block **1 session**, retain detailed paths **1**, horizon **9 calendar days**, target start **2026-01-26**, coverage end **2026-02-05**, declaration **explicit-demo-weekdays-v1**. Leave declared extra closures and early closes empty. This synthetic target calendar is explicitly unverified. Funded receipt delay is **2 calendar days**; the frozen receipt amount convention is unrounded kernel entitlement. Source and planning execution costs are zero for these arithmetic sources. Evaluation fees are **$30 evaluation + $40 activation**.

Choose **Save and check candidates**, inspect the real backend work counts/source pool, then **Run campaign**. Exact button wording remains visible in the screenshots. Inspect either candidate using the report selector; it changes presentation only. Expand retained native paths to compare original source timestamps/prices with modeled target dates and account-state sizing. All four paths enter the metrics; retained detail is the first declared path IDs, not selected by outcome.

Independent observations:

- Funded 1 MNQ receives **$0**, while 3 MNQ receives **$1,500** in every modeled path. The 3 MNQ path has seven $900 trades, $6,300 trading profit, $1,500 gross account deduction, $1,500 trader receipt and $4,800 provider equity change from $50,000. Request January 30 and modeled receipt February 1 remain different events. The 3 MNQ candidate ranks first.
- Evaluation 3 MNQ has all-path acquisition mean **$70 / 7 calendar days**; 10 MNQ has **$70 / 2 calendar days**. The 10 MNQ point dominates and is the complete Pareto frontier. No Funded cash data chooses Evaluation.
- Conditional MCSE is zero only because these synthetic paths have constant arithmetic. It is not uncertainty about future markets or provider rules.

For the three-session dynamic source, compare dollar risk **$100** and percentage risk **0.2% of current account balance**, with hard cap **40 MNQ**, initial configured capital $50,000, matching zero planning/execution costs, the same seed/paths/block/calendar and a **3-day** horizon. Retain all **4** paths. The dollar policy quantities by addressed path are `[10,5,10]`, `[10,10,10]`, `[5,5,10]`, `[10,10,10]`; percentage quantities are identical except the last path is `[10,9,10]`. The second quantity falls to 9 after the loss because current balance changes. Both policies receive $0 over this short horizon; neither is described as a profitable edge.

Native support remains explicit: true MNQ, supported VWAP strategy, EOD-flat, strategy-local volatility sizing disabled, complete admitted minute sessions, known causal stop when risk sizing requires it. Unsupported strategy/instrument/calendar/open-risk cases reject; a fixed-trade path is not silently used as native evidence.

## Freeze and inspect actual native OOS

The separate complete IS/OOS fixture has five full synthetic IS sessions January 5–9 and five later full sessions January 26–30. Source-timezone split boundaries are January 4–9 and January 25–30 (UTC); these retain the complete overnight CME sessions. Its native forecast comparison uses start January 12, horizon 7 calendar days, coverage January 19, quantities 1 and 3 MNQ, the same 4 paths/seed/block and 2-day receipt delay.

Select the 3 MNQ IS candidate, enter a rationale, and **Freeze selected candidates**. Then use **Launch OOS with frozen settings**. This is the existing selected-candidate manual OOS feature, distinct from the complete-procedure final verification below. Open the saved assessment: five actual later strategy trades use 3 MNQ, earn **$4,500**, deduct **$1,500** on January 30 and model a **$1,500 receipt on February 1** within the frozen seven-day window. The report links the actual controlled RunStore child. Its cash ledger, provider account state and normal trading equity remain separate. The frozen package bytes stay unchanged; there is no OOS ranking or replacement winner. Previously accessed history is not relabeled untouched.

## Reproduce a protected complete-procedure application

Use a fresh library for a new final-access demonstration. Reopening the saved release library is read-only, but it already contains the consumed final reservation and its access history; it cannot provide a second untouched claim.

1. Upload the saved `SYNTHETIC-procedure-history.csv` through Datasets. Select UTC, MNQ, tick size **0.25**, point value **2** and **Validate and save metadata only** before validation. Dates/counts remain visible; price rows are hidden.
2. Open dataset details → **Final research holdout reservations**. First/last CME sessions are **2026-01-23 / 2026-01-26**. With external access unknown, check shows **INSUFFICIENT_ACCESS_HISTORY**. Change to the explicit declaration that the sessions were not inspected, check again, and reserve. Eligibility is only under the recorded local scope; the external declaration remains unverified and there is no untouched-data certificate. The protected raw CSV download returns **409**.
3. In the normal backtest grid choose **Consecutive green hold**: green count 1–2 step 1; hold minutes 1; contracts 1; one worker; initial capital $10,000; zero slippage and commission. Disable automatic legacy prop reports for this source grid. Declare UTC IS January 5–22 and OOS January 23–30. IS reports contain 14 sessions, with exact net profits **$4,200** and **$1,400**; their per-session nets are $300 and $100. No holdout strategy execution has occurred.
4. Open either saved source report → Configure prop analysis → Nested research. Select both saved source configurations. Use rolling outer training **8 sessions**, test **2**, inner training **2**, validation **2**, purge **1**, embargo **1**, minimum inner folds **2**, outer folds **2**. Set qualification minima: folds 2, sessions 4, trades 4, trades per fold 2, positive-fold fraction 1, maximum profit concentration 0.6, extra round-trip cost $10, neighbors 1, bootstrap replicates 400/block 1/confidence 0.95/minimum tail samples 5.
5. Enable independent Funded economic validation with default Apex 50K EOD profile, fixed quantities **10, 20 MNQ**, **8 simulations**, source block 1 and complete exact ties. Keep reliability defaults (including five minimum outer blocks). In final requirements, require a final holdout and enable minimum observed Funded trader receipts **$1**. This is a predeclared single-final-path rule, not a lower bound on future mean cash.
6. Preview and run through the existing form. The two outer folds remain insufficient for the declared reliability requirement. In the completed report, choose the reserved dataset/session range, **Preview complete procedure and final feasibility**, then **Freeze reviewed complete procedure**. Review terminal training January 9–20 (8 sessions), inner validation January 15–16 and January 19–20, purge January 21, embargo January 22, final January 23/26 and exclusive cutoff January 27. Both original strategy configurations and the complete 2 × 2 signal/policy membership are frozen.
7. Check frozen final access and run final verification. The procedure freshly qualifies both configurations on permitted terminal development information, then retains the four tied Funded policies before actual final replay. Each final policy receives **$0**. The predeclared $1 final floor therefore gives **FAILED_VERIFICATION_CRITERIA** with no final-based replacement or reselection. The earlier outer report bytes stay unchanged.
8. Run frozen selection on current development. It repeats qualification on the pinned eligible history, excluding reserved final sessions; it does not copy a last-fold winner. Both terminal configurations again have means $100/$300 and the full four-policy family remains. The result says **NO QUALIFIED DEPLOYMENT CANDIDATE**, with research evidence, provider/model and operational blockers separately visible. Production qualified remains false.
9. Open each terminal report, inspect the qualification/frozen choices/final evidence/readiness, download the ordinary JSON/ZIP and captured procedure, terminal plan, access evidence and journal. Reloading performs no POST or numerical work. At 390 px, the tables stack into labeled rows without horizontal page overflow.

A saved result can be reopened with the ordinary application, using the exact library path and IDs in the release table. Start `ALPHAQUEST_DATA_DIR=<absolute library> .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8021`; open its listed hash route. Stop with Ctrl-C. All automated browser servers are temporary and stop in fixture teardown; none is left running.

## Final release evidence

Numerical source identity before and after all gates: `3a0b3bc7482e85b25d358b85459b43c84a4ee7113f52876c76130080aa09313b`. 23 saved downloads and 94 manifest ZIP members were independently rehashed. All five successful library journeys reopened without POST. Prior failed/probe evidence remains unchanged.

| Example | Saved library under repository | Campaign | Saved analysis |
| --- | --- | --- | --- |
| Independent Evaluation | `artifacts/native-phase-optimization-m2e-20261108/browser-final/data/test_native_campaign_fixed_pol1` | `ba14bb3a868b4ea5aa1de1cc6ca1bcc7` | `b1b04f63de064c259447df279b2d75c7` |
| Independent Funded | `artifacts/native-phase-optimization-m2e-20261108/browser-final/data/test_native_campaign_fixed_pol0` | `113882db496b466abae2cec6372854b1` | `a96f0bf7862a42f78778e83456936459` |
| Dynamic native policies | `artifacts/native-phase-optimization-m2e-20261108/browser-final/data/test_native_campaign_compares_0` | `45ab863ead6049c7b4c7f7dc85845e75` | `13430d4f595648f38b16e2ecbb470be9` |
| Actual native OOS | `artifacts/native-phase-optimization-m2e-20261108/browser-final-oos/data/test_native_campaign_frozen_ma0` | `43441085aba642369298772bea340fcd` | `3555539426b24304985796acb5c485be` |
| Complete procedure | `artifacts/procedure-native-search-m3b2-20261108/browser-final/data/test_complete_procedure_final_0` | `4a6dc8026132441e80ed24b9b2a4d01b` | final: `42b4799b723141ef9aa1764649082357`; current: `9e62119071794a6bada85fdf1eef0e69` |

Start from the repository root, replacing the library with the exact row above:

```sh
ALPHAQUEST_DATA_DIR="$PWD/<saved library>" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8021
```

For a campaign open `http://127.0.0.1:8021/#backtests/prop/campaign/<campaign-id>`; for a terminal or actual OOS report open `http://127.0.0.1:8021/#backtests/prop/job/<analysis-id>`. Native original source IDs and exact IS/OOS declarations are in each `evidence.json`; normal source report/CSV and hashes are retained. Procedure source CSV SHA-256 is `47bfeaf8e6465fd14975a9d02e7f750f3995ed029cb68810d85db49158e26b37`. Stop with Ctrl-C.

Run the complete automated normal-product journey again in a fresh directory (preserve release evidence):

```sh
AQ_RELEASE_REPRO=$(mktemp -d /private/tmp/aq-release-repro.XXXXXX)
.venv/bin/python -m pytest -q tests/test_native_campaign_browser.py tests/test_research_procedure_browser.py --basetemp "$AQ_RELEASE_REPRO/data" --junitxml "$AQ_RELEASE_REPRO/junit.xml"
```

Chromium/local-server process access is needed in the managed test environment. These commands run actual product calculations and stop their owned servers. The release logs contain only the existing Starlette/httpx deprecation warning in addition to the explicitly retained comma-format test failure. Numerical/API/legacy gates are documented separately by their owners; this browser evidence does not claim a full pytest run.

Release gate scope: `tests/test_native_campaign_browser.py` first run produced **3 passed / 1 failed in 221.18 seconds**; the one failure expected a thousands comma in the displayed correct `1500.0` OOS cash. Only that assertion changed. Its fresh `browser-final-oos` rerun passed **1 test in 56.99 seconds**. `tests/test_research_procedure_browser.py` passed **1 test in 26.31 seconds**. Both earlier failed output and successful rerun remain saved. Seven owned JavaScript files passed `node --check`; no numerical code changed for the assertion repair.

Copyable saved Funded campaign startup:

```sh
cd /Users/yx/alphaquest-research-engine-2
ALPHAQUEST_DATA_DIR="$PWD/artifacts/native-phase-optimization-m2e-20261108/browser-final/data/test_native_campaign_fixed_pol0" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8021
```

Open `http://127.0.0.1:8021/#backtests/prop/campaign/113882db496b466abae2cec6372854b1`. Its ordinary source is `http://127.0.0.1:8021/#backtests/report/5c93d35b2855482d8e991545cee21988`. Stop with Ctrl-C before switching libraries.

Copyable complete-procedure library startup:

```sh
cd /Users/yx/alphaquest-research-engine-2
ALPHAQUEST_DATA_DIR="$PWD/artifacts/procedure-native-search-m3b2-20261108/browser-final/data/test_complete_procedure_final_0" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8021
```

Open final evidence at `http://127.0.0.1:8021/#backtests/prop/job/42b4799b723141ef9aa1764649082357` and current development at `http://127.0.0.1:8021/#backtests/prop/job/9e62119071794a6bada85fdf1eef0e69`. The original report is `http://127.0.0.1:8021/#backtests/report/248805ad876543bbb0d9fbb9813d03bb`; configure prop analysis and reopen the named nested campaign to inspect its saved whole-procedure controls. Stop with Ctrl-C.


## M3b2 final product evidence — complete procedure, guarded final assessment, current development

Saved normal product library and 73 captured downloads: `artifacts/procedure-native-search-m3b2-20261108/api-final/`. The complete checksum inventory and IDs are in `evidence.json`. The labeled synthetic source has 20 observed weekday sessions / 80 bars, using MNQ prices and $2/point. No future/live outcomes are claimed. The library is 15 MiB; it uses the ordinary DatasetStore, backtests, phase children and AnalysisStore.

Engine identity before and after publication: `3a0b3bc7482e85b25d358b85459b43c84a4ee7113f52876c76130080aa09313b`.

| Saved item | ID |
|---|---|
| Dataset | `c91f6599beda4111a92705f96076692f` |
| Initial ordinary IS grid | `af8602a2cca5442a9cbbae676f1caf20` |
| Saved IS sources | `ae14fa4dabd34c0ba40812757e10663e`, `ba0f9ea95c024dccbd90cff352bb2328` |
| Robust campaign | `349584ff2619467285e6fdcd977d9515` |
| Protected final reservation | `66f033ab7d7c486fabc8c13ff038231d` |
| Procedure SHA-256 | `f43c4f4d9c64eb1e383526142af3d743be4c4761d079fe311ca29ddd666af4de` |
| Final application / report | `15d61078cd1540c58468c5e3f5527c1a` / `444c363e2b7f472798848739a5e9e314` |
| Current-development application / report | `acbf2b8d14e4442bb774469b4cee7226` / `f600c4f9abde49b1bdd05a926efb305f` |

To reopen the saved product without recomputing:

```sh
cd /Users/yx/alphaquest-research-engine-2
ALPHAQUEST_DATA_DIR=artifacts/procedure-native-search-m3b2-20261108/api-final/state \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8773
```

Open `http://127.0.0.1:8773/#backtests/prop/job/444c363e2b7f472798848739a5e9e314` for final verification, and `http://127.0.0.1:8773/#backtests/prop/job/f600c4f9abde49b1bdd05a926efb305f` for current selection. The normal report back link returns to the source's research configuration. Reopening is read-only and does not POST/run the analysis. Stop the temporary server with Ctrl-C. The publisher used TestClient lifespans and left no persistent server running.

Expected observations:

1. The dataset entered through `disclosure=metadata_only`, with `preview=[]`. Final sessions January 23 and 26 were reserved before the initial January 5–22 IS optimization. The captured `rejections/protected-csv.json` is a 409; inventory/checking did not expose protected OHLC. The reservation is eligible only within the recorded local scope and the user's unverified external-access declaration, not a universal untouched certificate.
2. Two actual `consecutive_green_hold` configurations have independent one-contract arithmetic: $300 and $100 net per selected validation session. Both qualify. Whole-session purge and embargo exclude January 21 and 22 from terminal training; terminal training is January 9–20, with the same inner qualification law. It is a new terminal fit, not either outer fold's winner.
3. The Funded study independently evaluates 10 and 20 MNQ for each qualified signal configuration. The four exact estimated receipt ties remain a four-member family. This case uses the supported saved fixed-signal-path scenario; the separately documented native search evidence demonstrates account-controlled strategy reruns. Neither case is live execution evidence.
4. The procedure was predeclared to require final verification and at least $1 of trader receipts. Each frozen final policy receives exactly $0 over the two actual final sessions: this short window cannot satisfy the profile's required payout trading-day history. The predeclared gate therefore reports `FAILED_VERIFICATION_CRITERIA`; it does not choose a different policy from the holdout.
5. Current development reruns the complete frozen qualification/selection procedure on the pinned eligible history, excluding final observations. It retains the same complete family as diagnostics and returns `NO_QUALIFIED_DEPLOYMENT_CANDIDATE`. The insufficient reliability evidence and failed final gate are explicit; provider/operational readiness remains unqualified.
6. The original campaign report and both application report downloads reopen byte-for-byte unchanged after a fresh app lifespan. `rejections/consumed-final.json` rejects a new final application against the consumed reservation. No new clean holdout claim or hidden repeated selection occurs.

Normal downloads:

- Campaign: `/api/research-campaigns/robust/349584ff2619467285e6fdcd977d9515/exports/report.json`.
- Final report/archive/procedure/selection/access evidence: `/api/research-campaigns/robust/349584ff2619467285e6fdcd977d9515/applications/15d61078cd1540c58468c5e3f5527c1a/exports/{kind}`.
- Current equivalents use application `acbf2b8d14e4442bb774469b4cee7226`.
- Normal AnalysisStore links remain `/api/prop-analyses/{analysis_id}/downloads/report.json` and `/files/{artifact_name}`. Child folders preserve provider rules, source checks, training context and phase metrics; `final-outer/` preserves actual ordinary final backtests and trade/decision downloads.

For a new reproducible run, use a fresh local data directory and the labeled `SYNTHETIC-source.csv`, follow the saved `optimization-request.json`, `declaration.json`, `procedure-freeze-request.json`, `final-request.json` and `current-request.json`, and generate new UUIDs/preview hashes from the current API. Do not reuse the consumed final reservation or call the original saved evidence “untouched” again. `publish.py` documents the complete normal-route sequence and refuses to overwrite the immutable evidence directory.

Validation: `api-gate-final/pytest.log` records 312 passing cases and one sandbox socket rejection before parallel calculation; `multiprocess.log` records that exact case passing outside the socket restriction (313 verified cases in total). The gate covers procedure/folds/phase selection, ordinary robust/economic/reference APIs, imports, research workflow, date/bar readers and datasets. Independent repaired access/cancellation probes passed 7/7, retaining their original failing logs under `/private/tmp/aq-procedure-independent-review/`. Additional terminal-reference role coverage is recorded separately in `terminal-reference.log`. These are scoped gates, not the complete final repository/provider qualification.
### Native nested family and release verification

The native nested API library is
`artifacts/native-phase-optimization-m2e-20261108/api-final/data/test_native_inner_search_and_f0`.
Source `a4401109600547bcbd1bbc477656fa6d`, campaign
`448f16b24d58474aa490b4d261af5239`, report
`471d2676eba04de99212fd35439ffb7b` preserve the complete two-policy family in both
outer folds. The nine-session labeled MNQ source uses train 5/test 2, inner train
1/validation 2, no gaps, two required inner and outer folds. Each inner validation
has two actual observations for its one-session block bootstrap; extra bootstrap
replicates cannot replace that history. The saved `native-nested-evidence.json`
contains the exact declaration, expected outcomes and report checksum.

Independently, both $100 fixed-risk and 0.2% current-balance policies submit 10/10
MNQ in each actual two-session outer window. Two $20-per-contract winning days
give $400 trading profit and $0 payout receipts under the profile's trading-day
requirement. Both exact receipt ties stay frozen; there is no outer-based winner.
Each result links a normal protected controlled backtest. As in the browser
libraries, set `ALPHAQUEST_DATA_DIR` to this path and open the saved report through
`#backtests/prop/job/471d2676eba04de99212fd35439ffb7b`; stop the temporary server
with Ctrl-C.

Root's read-only `verify_saved_release.py` checked 29 complete ordinary reports
and 454 component files across the final API/browser libraries, comparing every
file's size/SHA-256 and archive bytes. Output is `root-saved-verification.json` in
the native milestone artifact root. API tests additionally prove that changing
only a controlled child's catalogue manifest rejects an idempotent assessment
reuse while leaving the saved report bytes intact. Original failed probe logs
and immutable snapshots remain available; no earlier report was rewritten.

The frozen engine's API gate passed **51 checks**; native owner gates passed
**71** and **114** checks. Legacy campaign/regression passed **37** with one
socket-permission failure; that exact two-worker case passed after granting local
process access. The procedure/access gate passed **312**, its one socket-blocked
case passed on the targeted rerun, and the additional terminal-reference case
passed. The complete gate matrix, timings and paths are in
[the implementation checklist](robust_research_plan.md#m2e--m3b2-release-native-phase-search-and-guarded-complete-procedures).
Counts overlap and do not constitute a full repository-suite pass.

Reproduce the native root gates on the saved release code, using a new output
directory to preserve this evidence:

```sh
AQ_NATIVE_RELEASE=$(mktemp -d /private/tmp/aq-native-release.XXXXXX)
.venv/bin/python -m pytest -q tests/test_native_phase_campaigns.py \
  tests/test_native_nested_economics.py tests/test_research_phase_selection.py \
  tests/test_phase_analysis_cancellation.py \
  --basetemp "$AQ_NATIVE_RELEASE/data" --junitxml "$AQ_NATIVE_RELEASE/junit.xml"
```

The complete source snapshot is `qualified-source.tar.gz` in the native milestone
artifact root; later code changes may correctly reject new calculations from an
older frozen package. Saved reports remain readable without recalculation.

## Research workspace, drafts and saved visual review — 2026-11-08

Delivered through the existing portal on 8 November 2026. The Research navigation entry opens `#backtests/research`; source configuration and immutable calculations remain the normal backtest → prop configuration → check → run → AnalysisStore report workflow. Draft/template operations do not run numerical work or confer final-data access authority.

### Saved product demonstration

From `/Users/yx/alphaquest-research-engine-2`:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/research-workspace-m4-20261108/browser-final/data/test_draft_revision_template_f0" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8021
```

Open `http://127.0.0.1:8021/#backtests/research`. Stop the server with Ctrl-C. No persistent server was left running by the automated checks.

The saved workspace contains two named drafts and one completed nested campaign. Filter kind **Drafts** and open **SYNTHETIC preserved independent draft**, ID `88c437e8578643a9b388e9fa6ef03d9b`. Its 800 bootstrap replicates and full declared sources/settings are restored. Run remains disabled until a fresh preview. Expand **Review every saved declaration field** to inspect the full saved assumptions. The first draft, `f240e28806f24836a4af3c11e27fa443`, is revision 2; a stale-tab save was rejected while retaining its local edit, which was then saved as the separate draft.

The reusable template is `dd8c1748e310405b99132a567efd5163`. Applying it retained the current source selection and required a new preview. The demonstration explicitly added the neighboring configuration again before running. Source IDs are `558eaf46994b43a68198cda22486d135` and `a80d4046990344968a6a1a65a51bed50`. These are synthetic MNQ consecutive-green configurations with green counts 1 and 2, hold 1 minute, 1 contract, point value 2, tick size 0.25, and zero commission/slippage. Their saved IS dates are 2026-01-05 through 2026-01-22; declared OOS is 2026-01-23 through 2026-01-30. The ordinary source CSV is saved alongside the evidence, SHA-256 `47bfeaf8e6465fd14975a9d02e7f750f3995ed029cb68810d85db49158e26b37`.

Filter **Nested research**, then **Open saved report**. Campaign `4b5620f9621844d0a4f22d42d140d470`, analysis `4d16599e59c147618977d51218ea64e0`, can also be opened at `#backtests/prop/job/4d16599e59c147618977d51218ea64e0`. The actual saved inner means are independently expected to be **300 USD/session for green count 1** and **100 USD/session for green count 2**, in each outer fold. The parameter plot and exact table show both points, without interpolation. Two outer folds contain four retained Funded alternatives each. All eight earlier receipt forecasts and actual outer receipts are zero in this short synthetic example; overlapping points are not averaged, weighted or interpreted as eight independent folds. Research evidence remains **INSUFFICIENT_EVIDENCE**, production qualified **false**.

The fold timeline uses actual saved CME session labels: first training 2026-01-05–14, purge January 15, embargo January 16, outer test January 19–20; second training January 7–16, purge January 19, embargo January 20, outer test January 21–22. Calendar dates are not imputed as observations. At 390 px the chart scrolls inside its own region, and the exact table remains readable. Display-boundary checks confirm that first-16-fold and first-300-point limits disclose the cap while preserving all 17/301 test rows in the complete tables. Boolean parameters are excluded from numeric axes. Those boundary rows are isolated display tests, not saved research outcomes.

Saved `report.json` SHA-256: `3f5072864d217a52a87e82d5b4c775e973430e22617d29219ec37ffac7120f84`.
Saved `analysis.zip` SHA-256: `89b91c8191917599142e394a71e76bc7af8d7d933a1186b17422593bda94232b`.
The normal report and workspace both reopened with zero POST requests. Editable documents never changed this completed report.

### Source and policy boundary demonstrations

Use the same startup command with the library path replaced by the following exact directory:

| Library under `artifacts/research-workspace-m4-20261108/browser-final/data/` | Open | Expected observation |
| --- | --- | --- |
| `test_baseline_draft_missing_so0` | `#backtests/research?draft=be95ac8b858e4ffbb41713716d346e43` | The original source job was deleted only inside this synthetic test library. Missing anchor/source references and the original required one-MNQ baseline remain visible. The original draft is unchanged. A source-bound baseline template is rejected. |
| Same library | `#backtests/research?draft=aa6b591478c8456fab836c1faae6f246` | Explicit replacement anchor is saved in a new draft. Old missing references and baseline are retained until explicitly removed/rebound. The browser removed them in its editable form and obtained a fresh compatible preview; it did not rewrite the original draft. |
| `test_native_policy_draft_round0` | `#backtests/research?draft=af327962cf3b436a8bc1366244c55e13` | Revision 2 restores exactly six native policies: fixed 1 and 3 MNQ, plus dollar risk 100 and 0.2% current-account-balance risk at each hard cap 20 and 40. Planning capital 50000, point value 2, tick 0.25, zero costs, bounds 1–40 and both cushion guards false are preserved. A fresh real native preview passed; no campaign was run for this declaration-preservation case. |
| Same native library | `#backtests/research?draft=a98affd5ddb1432f938be32d9327569a` | The five-policy API declaration lacks one cap/policy combination. The grid form refuses to add or drop combinations, exposes the preserved declaration/download, and disables preview/run. It provides an explicit fresh-declaration action. |

The workspace separately renders original campaign, latest final-verification and current-development statuses. A later failed final application must not appear as an older completed campaign. This projection is server-derived; bounded report metadata that cannot be read yields REVIEW_REQUIRED and an ordinary full-report link. Unsupported saved schema versions remain read-only. Drafts do not pin ordinary source jobs; real campaigns keep existing dependency protections.

### Verification and reproduction

The final browser gate passed **3 tests in 17.38 s**. Targeted shared-control regressions passed **2 tests in 18.88 s**: actual native dynamic campaign and mobile navigation/layout. The native regression retains normal analysis `7d089a58a6a24ed795f30ac2d918e42f`, campaign `ff52d0b5e6344d79b20bc197a0d779e8`, in `browser-regression/data/test_native_campaign_compares_0`. Its four declared percentage-risk paths include the expected account-state quantity 9 after a loss; fixed-dollar risk uses 10 at the corresponding opportunity. Both receive zero trader cash over the short horizon. Source/model clocks and account balance remain distinct.

Both gates had unchanged complete engine identity `26edd1fb4462844c5e963fdf50023316758c2dc50497310afa326bcba8b3753b`. Independent release verification checked **14 saved downloads and 26 ZIP manifest members** across four evidence libraries. `artifacts/research-workspace-m4-20261108/release-verification.json` records exact IDs and every captured PNG/JSON/CSV/ZIP hash. Desktop timeline, parameter/forecast charts, missing-source form, native restored settings, rejection text and 390 px evidence were visually inspected.

Run fresh demonstrations without overwriting release evidence:

```sh
AQ_WORKSPACE_REPRO=$(mktemp -d /private/tmp/aq-workspace-repro.XXXXXX)
.venv/bin/python -m pytest tests/test_research_workspace_browser.py --basetemp "$AQ_WORKSPACE_REPRO/data" --junitxml "$AQ_WORKSPACE_REPRO/junit.xml" -q
AQ_WORKSPACE_REGRESSION=$(mktemp -d /private/tmp/aq-workspace-regression.XXXXXX)
.venv/bin/python -m pytest tests/test_native_campaign_browser.py::test_native_campaign_compares_actual_dynamic_policy_paths tests/test_backtests_browser.py::test_mobile_navigation_and_layout --basetemp "$AQ_WORKSPACE_REGRESSION/data" --junitxml "$AQ_WORKSPACE_REGRESSION/junit.xml" -q
```

Managed environments need Chromium/local-process access. Fixtures stop and join every temporary uvicorn server. Prior probes remain unchanged: they exposed test selector/duplicate-upload/collapsed-section assumptions, plus a client error that initially left a blocked draft message hidden; the final UI opens that message and preserves the document. Final logs contain the existing Starlette/httpx deprecation warning only. Backend/API and broader regression counts are reported separately by their owners. This increment does not establish provider parity or complete the remaining forward-monitor/lifecycle/whole-goal work.

Root API gate: **33 passed in 4.84 s** (`api-final/pytest.log`). Root independently verified four complete ordinary reports and 58 component files against sizes, SHA-256 values and ZIP bytes; `verify_saved_release.py` and `root-saved-verification.json` are in the M4 artifact root. Compilation of four changed Python files, seven JavaScript syntax checks and `git diff --check` passed. `qualified-checkout-5308d88.tar.gz` preserves the release source; later code changes may reject new work from its frozen sources while saved reports remain readable. Evaluation/Funded numerical identity comparison against `79cb5b0` is saved in `backend-final/phase_identity.json`.

## Timestamped forward observations — 2026-11-08

This increment follows a real current-development procedure application into
supplied-event checking, import, assessment and durable results in the existing
portal/AnalysisStore. It does not connect to a broker or place/cancel orders.
Signal implementation and account-state sizing equivalence are unverified;
research/provider/operational blockers remain visible. Synthetic, paper and
supplied actual-import provenance are distinct.

### Saved normal-product demonstration

The immutable library and downloads are under
`artifacts/forward-monitoring-m5-20261108/api-final/`. Its `evidence.json` records
all IDs and hashes; 36 downloaded artifacts reopened byte-identically after an
application restart. The library plus captures occupy about 6.7 MB. Every
observation in this saved demonstration is labeled **synthetic_harness**; source
backtest trades were not relabeled as forward observations.

From the repository root:

```sh
ALPHAQUEST_DATA_DIR=artifacts/forward-monitoring-m5-20261108/api-final/state .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8775
```

Open `http://127.0.0.1:8775/#backtests/prop/job/d19222de9b054dc58ecb63f59057efbd`
for the current-development report, then its forward-observation controls. The
saved monitor is
`http://127.0.0.1:8775/#backtests/prop/monitor/d863f7860e9e4e039459d2cc6f4f843b`.
Stop the temporary server with Ctrl-C. No persistent server was started by this
API demonstration; both TestClient application lifespans closed.

The ordinary source is dataset `ef7f9f049c134804aca993734aaad737`. Evaluated
campaign `119c3e875c8d45858aaa1aee329328f9` uses two saved consecutive-green
configurations, real inner qualification, independent Funded selection and a
predeclared same-signal one-MNQ reference. Two chronological outer blocks each
observe selected three-MNQ trader receipts of **1,500 USD** versus reference
receipts of **0 USD**. The explicit two-block reliability declaration yields
ASSESSABLE_WITH_LIMITATIONS; it does not establish independent historical sample
size or future/provider precision.

The complete procedure then reruns current development as application
`4243b328220a48288d0837f910c0c8aa`. Its selected package SHA is
`f307db82a10d853b50f65142de9b4a936f798b59d0dc773420d36f95442a8572`.
The recommendation is **RESEARCH_CANDIDATE_ONLY**, with provider and operational
blockers retained. Monitor `d863f7860e9e4e039459d2cc6f4f843b` binds this exact
server-verified current package. A no-qualified outcome cannot be promoted into
a bound policy; an unbound synthetic diagnostic remains available.

The separate synthetic stream supplies three MNQ bought at 100 and sold at 101,
with a total commission of 1.50 on each fill. Independent arithmetic is gross
**6**, fees **3**, net **3 USD**. Its original event batch is
`947a516cf4dd43e9b816013607fd4775`; the exact file is `source-events.json` and the
normal original-batch download. Reimporting it returns 200 and adds zero events.
Changing bytes under the same batch ID rejects 409.

| Normal assessment | Expected saved observation |
| --- | --- |
| `aec47bf0b42d4102bd479115f8ec2382` | ACTIVE at the captured clock; gross 6, commissions 3, net 3, flat position. |
| `4f43555aaad443faa456649635cca5fc` | New-ID exit correction to 100.5 gives gross 3, fees 3, net 0. The earlier supplied 50003 balance conflicts with 50000, so the assessment is PAUSED. |
| `1c0093de5b8e411382ead5b7c40aafa1` | Correlated position correction supplies 50000. Current blockers are resolved, but the saved snapshot retains the automatic pause before acknowledgement. |

Open any assessment at `#backtests/prop/job/<analysis_id>`. The explicit recovery
command records a reason and the backend SHA of the latest immutable assessment;
current monitor state becomes ACTIVE. All earlier snapshots remain unchanged.
That state describes the old saved clock, not current live health. A recovery
attempt today needs a fresh valid observation assessment, not an old heartbeat.
Retirement is terminal, and none of these advisory controls blocks platform
orders.

Inspect `events.jsonl`, source-batch JSON, captured policy, input snapshot,
reconciliation and ZIP through the normal downloads. Expected disclosures are
SYNTHETIC_ONLY, no verified broker/strategy execution, production qualified false,
and separate frozen forecast versus actual receipt/duration diagnostics marked
NOT_COMPARABLE. Matched calibration is not implemented. Fees are charged once;
slippage is diagnostic. Requests, provider deductions, trading P&L and balance do
not become trader receipts. Net trader cash separately subtracts actual paid
Evaluation/activation fees from receipts.

### Rejections, boundaries and reproducibility

Strict invalid decimal/clock/quantity fields, unsupported source identities,
changed batch/event IDs and correction forks reject. Ambiguous same-time market
or connection order remains unresolved. Protective overfills, fills after
cancellation, stale prior-position stops, mismatched balances and absent initial
account evidence pause the assessment without inventing missing fills/stops.
Unknown lot allocation remains unknown after partial exits. A market mark from
before entry cannot manufacture held-position profit or drawdown.

Recovery checks the exact latest report SHA and event head, current feed/position
health and assessment freshness. It preserves historical incidents and lifetime
drawdown; it cannot acknowledge away current risk or intrinsic causal conflicts.
Original receive clocks, supplied events and corrections are append-only.

The access probe uses the real dataset reservation API. Checking supplied
financial/market observations that overlap a protected session retains the
reservation and the risk records, while final eligibility becomes
PREVIOUSLY_ACCESSED. It grants no read of the protected dataset. Synthetic inputs
are conservatively included because their claimed independence is unverified;
pure heartbeat/connectivity records do not create financial-price access.

`api-final/publish.py` and `command.txt` record the normal-product publisher. To
reproduce into a **new, non-existing directory**, preserving release evidence:

```sh
AQ_FORWARD_REPRO=$(mktemp -d /private/tmp/aq-forward-repro.XXXXXX)
PYTHONPATH=tests:. .venv/bin/python artifacts/forward-monitoring-m5-20261108/api-final/publish.py "$AQ_FORWARD_REPRO/library"
```

The publisher refuses to overwrite an existing result directory. The exact
release gate command and output are in `api-gate-final/command.txt`, `pytest.log`,
`pytest.xml` and `gate.json`: **56 passed in 9.63 s**, including 49 forward checks
and existing access/publication boundaries. Independent original failures and
repaired probes remain in `independent-review/`; this includes the exact partial
fill oracle gross 4/fees 1/net 3 and the trader cash oracle 50−30−40=−20. Fixture
oracles stay in tests/development evidence, not a product test dashboard.

Complete Python/source identity before and after both gate and publication:
`3f6ce9d8ef3fd05f25aa7fc4a1a85686c67aae86ee6510063c587ad982a0ff1c`.
This is targeted evidence, not a full repository/provider/parity qualification.
Lifecycle, multi-strategy, legacy and browser gates are recorded separately.
## Frozen pair comparison and integration evidence — 2026-11-08

The normal API journey is saved at
`artifacts/frozen-pair-m4b-20261108/api-final/data/test_existing_report_to_check_0/library`.
From the repository, start an optional temporary reader:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/frozen-pair-m4b-20261108/api-final/data/test_existing_report_to_check_0/library" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8022
```

Open `http://127.0.0.1:8022/#backtests/prop/job/189d571453c94ce98338342a9d1d5b38`.
Stop the server with Ctrl-C. Automated fixtures stopped their own servers.
The source is explicitly synthetic complete-minute MNQ/VWAP data, with zero
trading costs and 3-MNQ fixed policies. Independent frozen campaigns are
Evaluation `d44c1d9ee99a4b5abd6f5d3051253a3f` and Funded
`0609c6d9b9864508beaa25adb0d11ffd`; their unchanged packages and exact candidate
IDs are captured in the comparison report. Ordinary manually executed OOS source
`99accacb3dd04aee9a11f3841ad87a3e` retains its prior-access history.

The common first session is January 26; exclusive cutoff is February 9, 2026.
Independently, the synthetic source earns $300 per contract per day. At 3 MNQ,
Evaluation passes January 29, pays $30 purchase plus $40 activation, and becomes
funded-ready February 2. Five subsequent $900 Funded sessions produce $4,500
trading profit; the modeled $1,500 request/deduction occurs February 6 and receipt
February 8. Expected received cash is $1,500, pending $0 and net trader cash
$1,430. Provider deduction is not another cash expense. The original independent
Funded forecast horizon stays unchanged; the observed continuation has its own
binding. There is no combined winner, ranking or implicit replacement.

From the ordinary OOS report, Configure prop analysis → Compare explicit frozen
Evaluation / Funded pairs. Select each exact frozen candidate and existing OOS
report, name the pair, and set the dates above. February 10 as cutoff rejects a
horizon longer than the frozen declaration. February 9 passes Check; checking
does not increment manual OOS attempts. Run saves the normal report, child
backtests, phase packages, source checks, bindings and exact cash JSON/CSV/ZIP.
Exact duplicate requests reuse the saved analysis. A changed declaration under
the same ID or altered child manifest rejects; original report bytes stay intact.
Children and both phase sources are protected from deletion while referenced.

Actual-controller boundary tests separately prove that a receipt exactly at the
exclusive cutoff remains $1,500 pending/$0 received/net −$70, readiness at cutoff
leaves Funded unstarted, and never-passed Evaluation keeps its $30 paid loss.
Accepted cancellation cannot publish a partial comparison; exact retry preserves
the request binding. These calculations use the existing execution/phase owners.

The isolated pair browser probe passed in 94.08 s and retained normal report
`f09677c4e63e4e8f8265a115f396de58`, screenshots, downloads and zero-POST reopen under
`artifacts/frozen-pair-m4b-20261108/browser-probe/`. Desktop and 390-pixel cash and
trace views were inspected. The shared-source API/unit/storage/multi-strategy gate
passed **25 checks in 130.39 s**, with unchanged Python identity
`3f6ce9d8ef3fd05f25aa7fc4a1a85686c67aae86ee6510063c587ad982a0ff1c`.

The first shared final browser attempt failed during CSV upload with
`OSError: [Errno 28] No space left on device`, before product UI execution.
Its log/XML and failed new scratch directory remain under
`artifacts/frozen-pair-forward-m4b-m5-20261108/browser-final/` and
`/private/tmp/aq-final-pair-forward-mySC5B/`. Existing legacy regression was stopped
before exhausting storage after **54 passed in 276.75 s**. That interrupted gate
is not labeled clean. No prior datasets, reports, evidence or snapshots were
deleted. After the user freed storage, the missing Playwright browser binary was
restored and fresh resumed gates were run separately; their results follow.


## Frozen pairs and supplied forward observations — product evidence

This increment uses existing backtest reports, prop configuration, normal analysis jobs and durable results. Every demonstration input is synthetic. It does not establish provider parity, broker connectivity, future profitability or deployment qualification.

### Final evidence

The final engine is `3f6ce9d8ef3fd05f25aa7fc4a1a85686c67aae86ee6510063c587ad982a0ff1c`, unchanged before/after the runs. The restored combined gate passed the pair and bound-forward cases, then failed a test assertion about a disabled option: **2 passed, 1 failed in 119.33 s**. A read-only DOM probe confirmed native `disabled=true` and `disabled=""`; Playwright reported a different option accessibility state. Only the test assertions changed to verify the native attribute/property. The no-qualified case then passed in a fresh library: **1 passed in 7.56 s**. No production fix was needed. This is targeted 2 + 1 passing workflow evidence, not a claimed all-green combined run. Desktop pair cash/ledger, 390 px pair/monitor and no-qualified admission screenshots were manually inspected. Independent re-verification checked **20 downloaded files and 56 ZIP members**, all three zero-POST reopens and all owned server teardowns; see `artifacts/frozen-pair-forward-m4b-m5-20261108/browser-verification.json`.

Prior evidence remains intact:

- Pair isolated browser probe: `artifacts/frozen-pair-m4b-20261108/browser-probe`, 1 passed in 94.08 s.
- Forward final-engine browser probe: `artifacts/forward-observation-m5-20261108/browser-probe`, 1 passed in 19.06 s.
- Shared final attempt: `artifacts/frozen-pair-forward-m4b-m5-20261108/browser-final`, CSV upload failed with ENOSPC before UI execution; 1 failed in 2.97 s.
- First resumed attempt: `.../browser-final-resumed`, 3 setup errors in 3.19 s because Chromium's cached executable was absent after disk cleanup. No product execution occurred. The required Playwright headless shell was restored without changing product code.

All temporary portal fixtures stop and join their servers. No persistent server is started by these tests. Use a separate port and Ctrl-C to stop any server started manually below.

### Final browser libraries and exact saved IDs

Use `ALPHAQUEST_DATA_DIR="$PWD/<library below>" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8022`, then the matching hash route. Ctrl-C stops the manual server. Saved views issue reads only; creating a new monitor/report is an explicit separate action. To keep these immutable evidence libraries unchanged, use them only for inspection or work from a separate copy when experimenting.

| Case | Library below `artifacts/frozen-pair-forward-m4b-m5-20261108/` | Open route |
|---|---|---|
| Frozen pair | `browser-final-restored/data/test_frozen_pair_normal_report0` | `/#backtests/prop/job/aafa5b7044364aa3acc5e2ff088d0904` |
| Current-policy observations | `browser-final-restored/data/test_current_policy_supplied_e0` | `/#backtests/prop/monitor/aab8a5c2b3cf43d782de195471fb0daf` |
| No-qualified diagnostic | `browser-no-qualified-final/data/test_no_qualified_current_poli0` | `/#backtests/prop/monitor/5985e4a5cffe4002a0733bfa3fd2d7a3` |

Pair source `3ecc81f9e4b4438fb70ee92ad4ab42a2`; ordinary OOS `10cd04c21fa14573a48389987c2e67d0`. Actual saved CSV includes IS dates 2026-01-04 through 2026-01-09 and OOS dates 2026-01-25 through 2026-02-06; exact split, source hash and frozen references are in `evidence.json` and the source report. The comparison uses CME session dates 2026-01-26 through the exclusive 2026-02-09 cutoff.

Current-policy report `2afb610c7e204737a07583d2c1029ba0`; synthetic monitor snapshots `4af6c900fff34b54a5ffc641060b73dc` (ACTIVE/net $3), `106b3af015cf44ee8a6b46c8b48226e8` (PAUSED/net $0 with balance mismatch), `d366ddec05a44bfc8926adba2ebbce91` (reconciled but still latched PAUSED). Current monitor ACTIVE followed explicit acknowledgement; each saved assessment remains unchanged and tied to its historical UTC clock. No-qualified current report `f58fef00c37449a586cb838add3700e7` permits only an unbound synthetic monitor; zero events, no assessment or forward outcome is fabricated. A forged actual-import declaration without binding rejects with HTTP 422.

The existing demonstrations deliberately lack complete comparable forecast-scope coverage and show NOT_COMPARABLE. Full compatible Funded forecast-scope comparison is the next separately reviewed increment; it is not claimed implemented here.

### Frozen Evaluation / Funded pair

Independent arithmetic: one predefined 3 MNQ Evaluation / 3 MNQ Funded pair pays $30 Evaluation and $40 activation fees. Evaluation becomes funded-ready on 2026-02-02. Funded begins then and uses only the remaining common window, with a request on 2026-02-06 and modeled receipt on 2026-02-08. Received cash is $1,500, gross account deduction is separately $1,500, pending receipt is $0, and net trader cash is $1,430. These are actual chronological synthetic-history outcomes, not Monte Carlo estimates. There is no winner or ranking.

Normal journey: open the saved ordinary manual OOS backtest → Configure prop → Frozen Evaluation / Funded pair comparison. Give the pair a name. For each phase, explicitly select its independently frozen native campaign, retained candidate and corresponding completed ordinary OOS report. Use first session 2026-01-26 and exclusive cutoff 2026-02-09. Check shows the exact source/package identities, complete work, costs and receipt assumptions. Run saves an ordinary report with two actual controlled child backtests, cash ledger, original frozen packages and downloads.

Boundary: cutoff 2026-02-10 rejects because it exceeds the independently declared native horizons. Check and saved reopen must not increment manual OOS access or change the frozen packages. Imported/external sources and incompatible profiles reject; existing OOS remains explicitly previously accessed. A shorter cutoff can leave a requested amount pending instead of received; the owner/API boundary tests cover that distinction. Multi-pair work is bounded rather than silently reduced.

Final durable API library (also available for read-only inspection):

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/frozen-pair-m4b-20261108/api-final/data/test_existing_report_to_check_0/library" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8022
```

Open `http://127.0.0.1:8022/#backtests/prop/job/189d571453c94ce98338342a9d1d5b38`. Ordinary OOS is `99accacb3dd04aee9a11f3841ad87a3e`; Evaluation campaign `d44c1d9ee99a4b5abd6f5d3051253a3f`; Funded campaign `0609c6d9b9864508beaa25adb0d11ffd`. Do not mutate preserved evidence libraries when inspecting them.

### Supplied observations and advisory recovery

Start from an actual complete current-development report. Expand Observe current policy, explicitly choose a retained frozen member and provenance, name the monitor, declare a source ID and operational/edge thresholds, then Check/Create. Multi-member families require an explicit preference reason; monitoring does not invent a historical winner. A no-qualified result permits only an unbound synthetic diagnostic; paper and actual-import policy bindings remain unavailable.

On the monitor, Check a raw `aq-forward-events-v1` JSON file, Import those reviewed bytes, choose an explicit UTC assessment clock, then save a new immutable ordinary report. Checking financial/market events records research exposure even without import, including protected-session conflicts. Newly accepted observations show WATCH/unassessed prominently. A previous saved ACTIVE state does not validate a changed event head. Opening a report or monitor does not assess or change controls.

Independent synthetic observations: 3 MNQ supplied fills earn $6 gross realized P&L, with $3 total supplied commissions and $3 net trading P&L. A $50 request, $60 provider deduction and $50 trader receipt remain separate. Net trader cash is $50 and provider balance is $49,943. A corrected exit produces $0 net trading P&L and a balance mismatch, so the advisory state is PAUSED. A corrected supplied position gives provider balance $49,940 and resolves current blockers, but PAUSED remains latched until explicit acknowledgement of the backend's exact latest snapshot SHA. The initial saved report bytes remain unchanged.

Exact duplicate event bytes are idempotent. Different bytes under the same batch ID reject. Corrections use new immutable event IDs, supersession links and reasons; originals remain downloadable. Slippage is diagnostic and is not deducted twice. Unknown payout entitlement remains unknown. Saved results remain SYNTHETIC_ONLY, supplied/unverified, NOT_COMPARABLE to the forecast, advisory-only and incapable of placing/cancelling platform orders. There is no continuous broker/data connection. Control recovery also requires a fresh assessment clock and no unseen observations/current blockers; old demonstration clocks are not a current-health claim.

Final API evidence can be inspected by starting the same server command with `ALPHAQUEST_DATA_DIR="$PWD/artifacts/forward-monitoring-m5-20261108/api-final/state"`: current report `d19222de9b054dc58ecb63f59057efbd`, monitor `d863f7860e9e4e039459d2cc6f4f843b`. Report route is `/#backtests/prop/job/{id}`, monitor route `/#backtests/prop/monitor/{id}`. The workspace includes a bounded searchable observation list with saved as-of and pending state.

### Rebuild the demonstration

Run from the repository root after restoring the matching Playwright browser if needed:

```sh
.venv/bin/python -m playwright install chromium --only-shell
.venv/bin/python -m pytest tests/test_frozen_pair_browser.py tests/test_forward_browser.py --basetemp=/absolute/fresh/evidence/data --junitxml=/absolute/fresh/evidence/junit.xml -q > /absolute/fresh/evidence/pytest.log 2>&1
```

Create the evidence parent first and use a genuinely fresh directory. Managed environments require Chromium/local-process access. The test helpers build synthetic datasets and ordinary backtest/campaign/procedure results through the real APIs; UI tests exercise configuration, checking, running, downloads, 390 px layouts and saved reopen. Fixture oracles stay in tests. Fresh synthetic incoming timestamps are created only after the fresh monitor; replaying old event timestamps remains retrospective. Evidence manifests include exact source CSV hashes, report/ZIP/raw-event hashes, explicit outcomes and zero-POST reopen assertions. Numerical/API/full-suite verification is reported separately; this guide does not imply those scopes passed merely because browser cases passed.

The resumed legacy gate passed **35 tests in 201.27 s**. Python compilation,
five changed JavaScript syntax checks and `git diff --check` passed. These targeted
gates do not replace the pending complete repository suite.

## Two-strategy complete research and market-series properties — 2026-11-08

The complete normal-product scenario uses two genuine registered strategies,
`consecutive_green_hold` and `vwap_pullback_risk_sizing`, with two signal settings
each. The clearly labeled synthetic source has 20 weekdays × 16 sparse observed
bars, zero costs, one source MNQ, tick 0.25 and point value $2. It is not complete
minute or tick evidence. Ordinary grids save 14 IS trades per configuration.
Independent per-session returns are $4/$12 for the first strategy and $20/$20
for VWAP; saved IS totals are $56/$168/$280/$280.

The immutable actual library is:
`artifacts/frozen-pair-m4b-20261108/api-final/data/test_two_strategies_full_membe0`.
Start a temporary read-only inspection session from the repository root:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/frozen-pair-m4b-20261108/api-final/data/test_two_strategies_full_membe0" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8023
```

Open `http://127.0.0.1:8023/#backtests/prop/job/5c4198a29ca94a76859b8ec64f3327a3`
for nested report, or report `d24ae5e862ad492fbbb64625fb4f7cc7` for the fresh
current-development application. The campaign is
`8c31ea446437453fbe22a4a7f85dfefb`; application is
`ecb47c1a2edd4b5d85863cb14a26424e`. The original ordinary source is
`2d4dafba6e4041509f76477c3e19b4b7`; grids are
`66dd4fcef3284598bfe898c45838e261` and `84884ab97a3d4adfa6b9432dda06727a`.
Stop with Ctrl+C. Inspect saved evidence without changing its declarations.

To reproduce through the UI in a fresh library, upload
`artifacts/frozen-pair-m4b-20261108/multi-strategy-inputs/SYNTHETIC-two-strategy-sparse.csv`,
create those two ordinary grids, open the first
IS trial → Configure prop → Nested research, and select both complete grids.
The saved request download contains exact strategy parameters, costs and
thresholds. Declare rolling 8-session outer training and 2-session tests,
2-session inner training/validation, one-session purge/embargo, and at least two
inner/outer folds. Use 1,000 qualification bootstrap repetitions, four historical
validation sessions, full neighboring membership and zero extra round-trip cost.
This repetition count resolves a computational family-tail requirement; it does
not increase the four observed sessions. A separate retained 400-repetition
example correctly returns insufficient tail resolution.

Enable independent Evaluation and Funded studies, both with whole-MNQ sizes
10 and 20. Each phase must show all four configurations × two sizes = eight
candidates. Evaluation's smallest-return member cannot reach $3,000 in 21
sessions: $4 × 20 × 21 = $1,680. Its full-family acquisition estimate stays
unresolved and it does not silently select from a smaller family. Funded retains
all eight exact $0-receipt ties. Across two outer folds, 16 ordinary backtests
execute; each source configuration has independently expected unit-size net
$8, $24 or $40 over its two sessions, with fixed-path provider quantities shown
separately. Trader receipts and pending cash are $0, not the backtest net P&L.

Freeze the complete procedure and run a separate current-development selection.
It reruns all four configurations and both eight-member phase families. Both
phases return **NO QUALIFIED DEPLOYMENT CANDIDATE** because the declared reliability
evidence is insufficient. No final holdout was consumed and no last-fold winner
was promoted. Downloads include complete inner/phase/outer/reliability results;
restart/reopen returns identical bytes with calculation functions disabled in
the automated check.

Exact fresh reproduction:

```sh
.venv/bin/python -m pytest tests/test_multi_strategy_research.py -q --basetemp=/absolute/new/multi-strategy/data --junitxml=/absolute/new/multi-strategy/pytest.xml
.venv/bin/python -m pytest tests/test_research_market_properties.py -q --basetemp=/absolute/new/market-properties/data --junitxml=/absolute/new/market-properties/pytest.xml
```

Create each parent directory first. Never reuse a preserved explicit basetemp;
pytest removes an existing one at startup. The first scenario passed within the
25-test shared API gate. The seven market-series checks passed in 54.55 s on the
same unchanged Python identity `3f6ce9d8…0ff1c` under
`artifacts/selection-properties-m6-20261108/final-resumed/`.

Those seven normal API runs cover six requested properties: a stable region with
$10/$12/$14 per-session neighbors; independent seeded IID noise (seeds 7 and 31);
a predeclared change from +$10 to −$10; an isolated −$10/+$20/−$10 parameter peak;
causal clock regimes (Europe −$2, US +$20); and a six-member family whose
400-versus-2,000 bootstrap repetitions change numerical tail resolution without
adding historical samples. Exact expected values, declared seeds, qualified and
rejected rows, report downloads and preserved failed/interrupted probes are in
the artifact README and tests. No qualification result is mocked. These are
controlled properties, not proof that a finite statistical procedure always
rejects every noisy market or detects every future change.

Root independently verified **53 complete reports and 742 component files**
across the final pair, forward, two-strategy and market-property libraries:
bytes, sizes, SHA-256 and every included ZIP member agree. The read-only script
and saved index are
`artifacts/frozen-pair-forward-m4b-m5-20261108/verify_saved_release.py` and
`root-saved-verification.json`. The matching full tracked checkout is retained as
`qualified-checkout-27cf056.tar.gz` with a SHA-256 file. It includes source,
calendars and packaging; environment and compiled-extension builds remain
separate requirements. Existing archives and reports were not replaced.

The standalone synthetic CSV for the two-strategy journey has SHA-256
`8c338a42cdc0a722dab436f35a4d679a4feccb8437cca7d993f49ce998f82c72`,
matching the normal saved dataset. The adjacent `strategy_parameters.json`
contains exact strategy defaults and each 1-to-2 search axis. These are inputs
for the normal product workflow; no separate demo endpoint or store exists.

## Complete supplied scope and local sizing arithmetic — 2026-11-08

The ordinary current-policy monitor now supports a narrowly matched descriptive
Funded cash comparison and local frozen-policy sizing arithmetic. It still does
not verify a broker/platform implementation, payout approval or future forecast
accuracy. The preceding M5 report library remains unchanged. This extension
retains the failed scope-clock/deduction probes and the repaired evidence rather
than overwriting the original release.

The final fixed-policy API journey is saved at
`artifacts/forward-comparison-m5b-20261108/api-final/`. Its `evidence.json` SHA-256
is `f667dc2c00efd1f8b1ecdee3ee3e00f222af265843c178e98af71264ffaff944`.
All 36 downloaded files reopened byte-for-byte; all three ZIPs contain the exact
saved report and listed files. The before/after engine is
`1ff01f1e8e370ef6781b5ec579ce60749310fbe3c0fcb5f78030c7aa7299f5e6`.
The focused owner/API/access/publication gate passed **114 tests in 28.96s**;
its exact command, log, JUnit, retained state and hashes are under
`artifacts/forward-comparison-m5b-20261108/api-gate-release/`. This is a focused
gate, not the whole-repository baseline. Independent probes retained three
initial clock/cash failures and then passed five repaired cases; those logs and
sources are under the adjacent `independent-review/` directory.

The saved normal product identifiers are:

| Item | ID |
|---|---|
| Synthetic dataset | `6512d0e182ad4b8f969077479e06ffef` |
| Full-procedure campaign | `a51da2f52b4a4fec8bcf402ad115c4d6` |
| Current-development application | `58dbce2d9f1145d0993bc04cdd759ba4` |
| Current-development normal report | `83b483fa69b34a4e80044a857ad64018` |
| Supplied observation monitor | `08d1aa5387ea4d678d7d9b33ab853226` |
| Partial-coverage assessment | `740d6aafafae46208c4261cc5ed98d8e` |
| Complete-coverage assessment | `07160ab7741e413b9b6d5f9815c499ac` |
| Corrected-receipt assessment | `4af9f34b788d445c9494e94ca2226c98` |

The chosen package hash is
`7c56564f214dc8dbedf73bfbeeb915fc62df7659854a5f668725368743e4465e`;
the immutable observation-plan hash is
`150393029272c7d3ca2d9efdc4384041db6c9164acd3c36ea1324f398e97f3f0`.
The saved source check binds both to the actual current-procedure selection and
normal training report. It does not promote the last outer-fold policy.

Reopen this library from the repository root:

```sh
ALPHAQUEST_DATA_DIR=artifacts/forward-comparison-m5b-20261108/api-final/state .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8777
```

Open `http://127.0.0.1:8777/#backtests/prop/job/83b483fa69b34a4e80044a857ad64018`
to inspect the current-development recommendation and its ordinary monitor
launcher. Open
`http://127.0.0.1:8777/#backtests/prop/monitor/08d1aa5387ea4d678d7d9b33ab853226`
for the declaration, original batches and immutable assessment history. The
complete report is
`http://127.0.0.1:8777/#backtests/prop/job/07160ab7741e413b9b6d5f9815c499ac`.
Download its normal JSON, ZIP, captured policy, input snapshot and raw batches;
reopen without running another assessment. Stop the server with **Ctrl-C**. No
persistent server was left running by this API demonstration.

Expected independent arithmetic and states:

1. The earlier selected Funded model estimates **$1,500** of trader receipts over
   its saved single-cohort horizon. The original model dates remain
   **2026-01-27 through exclusive 2026-02-03**. The synthetic observation explicitly
   declares a same-pattern translation to **2026-11-10 through exclusive
   2026-11-17** before the first target CME session opens. This is a supplied model
   transport assumption, not a forecast originally issued for those target dates.
2. Separate incoming synthetic events submit **3 MNQ**, buy at 100 and sell at
   101. At $2 per point, gross profit is **$6**. Two supplied $1.50 commissions
   total **$3**, so net trading profit is **$3**. Local fixed-quantity conformance
   reports `MATCH`; platform strategy behavior remains unverified.
3. A separately supplied request, gross account deduction and actual trader
   receipt are each **$50** under the captured 100% trader-share model. Provider
   balance is **$49,953** after trading profit and deduction. Trader receipt is
   **$50**, not account balance or trade P&L, and the deduction is not another
   trader expense. The model's full-cap request policy and payout eligibility are
   retained as unverified implementation assumptions; the fixture does not claim
   a provider would approve this $50 request.
4. The first assessment has `partial` coverage and remains `NOT_COMPARABLE`.
   An append-only corrected `account_coverage` claim completes the exact interval;
   the next report is `SYNTHETIC_SCOPE_COMPARISON`, with **$50 − $1,500 = −$1,450**.
   The report states **one observation**, supplied/unverified completeness and no
   calibration or future certification.
5. A new receipt correction changes the actual amount to **$25**, and a correlated
   completion correction declares **$25 pending**. The third report shows
   **$25 − $1,500 = −$1,475**. Gross deduction stays $50, trading net stays $3, and
   earlier reports/downloads remain identical. Reimporting identical source bytes
   creates no duplicate fills or cash.

The publisher records synthetic receiver-clock injection explicitly as
`receiver_clock_provenance: synthetic_harness_clock`; the normal product has no
clock-changing endpoint. Its fixture constructs the server with a deterministic
clock before the target session and advances it after the horizon. These are not
real elapsed live observations. `paper`/`actual_import` reject that clock
provenance, and a genuine complete observation requires an elapsed prospective
horizon and supplied records. For new monitors, declare a fresh compatible
calendar after policy selection; never relabel prior observations as prospective.
The inspectable `publish.py`, `monitor-request.json`, `monitor-check.json`,
`source-events.json`, normal captured inputs and `command.txt` reproduce the dated
synthetic journey without a separate demo API or evidence store.

Relevant rejection/clock/cash checks include changed calendar pattern or exact
absolute dates, pooled cohorts, pre-policy history, partial/voided coverage,
missing flat boundary state, trading outside declared sessions or after terminal
account status, ambiguous ties, future-received corrections and pre-origin cash.
Receipts at the exclusive cutoff remain outside the horizon; known pending
entitlement is preserved even after breach. Missing, unrelated, duplicated or
undersized gross deductions cannot produce a matched comparison. A saved **90%**
share independently reconciles **$1,000 gross / $900 trader entitlement and
receipt / $0 pending**. Unknown share evidence withholds comparison while keeping
all supplied financial facts. The existing ordinary request50/deduction60/receipt50
cash diagnostic remains representable; it is not silently promoted to a matching
100%-share model.


### Authoritative dynamic policy through the normal observation workflow

The final synthetic example creates a complete-minute MNQ/VWAP source, a normal
nested Funded study with a predeclared one-MNQ reference, a complete procedure
freeze and a fresh current-development fit. The selected 0.8%-current-balance
policy is bound to a monitor through the normal source check. Its independent
supplied decisions have $40 risk per MNQ: $50,000 × 0.008 / $40 = 10 contracts;
after a $100 loss, floor($49,900 × 0.008 / $40) = 9. The second trade earns $180,
so trading P&L is $80 and final equity $50,080. A later correction claiming 9
instead of 10 at the first decision yields MISMATCH and advisory PAUSED; original
MATCH/ACTIVE bytes remain unchanged through restart. Typed provenance is
SYNTHETIC_ONLY. No complete horizon is declared, so forecast comparison is
correctly NOT_COMPARABLE even though local sizing arithmetic agrees.

Final gate: **1 passed in 182.93 s**, with identical before/after engine
`1ff01f1e8e370ef6781b5ec579ce60749310fbe3c0fcb5f78030c7aa7299f5e6`.
The earlier 190.09 s probe remains preserved, but its synthetic records were typed
paper; the final gate corrects the typed provenance as well as the visible label.

From the repository root, inspect the actual saved normal reports:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/forward-comparison-m5b-20261108/dynamic-api-final-v2/data/test_actual_native_current_per0" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8778
```

Open `http://127.0.0.1:8778/#backtests/prop/job/08471bf5e92544c9ab237ce3424fd1da`;
the discrepancy report is `0339ff79ce6a4a5db580d5454eda251a` on the same route.
Monitor `7d270d54d1db4058aaa8ce444b1f8298` opens at
`/#backtests/prop/monitor/7d270d54d1db4058aaa8ce444b1f8298`. The source backtest is
`e925358cfabc40a9b06a29c3c6437873`, campaign
`39d741563a684ed8b889f6df0ceae81c` and current application
`7d885119a7d14481ab43e053eb8b1656`. Ctrl+C stops this manually started server.
The API test started no persistent server.

The library includes `dynamic-monitor-request.json`, `dynamic-monitor-events.json`,
`dynamic-monitor-report.json` and `dynamic-monitor-evidence.json`. Use normal JSON
and ZIP downloads from each report. The original MATCH report SHA-256 is
`1d270d7f5a63e05452a486afb2954ae2186ce2ba126183fa3f09381291bf4bde`.
An independent audit verified all 15 listed component hashes/lengths, package
self-hash, training-report identity and both saved/current sizing-source hashes.
Exact fresh reproduction is the command in the adjacent gate `commands.txt`:
run `tests/test_forward_dynamic_api.py` with a new basetemp/XML location. Never
reuse this retained evidence directory. External strategy eligibility, supplied
floors/caps and broker enforcement remain unverified.


## Complete supplied Funded scope and causal sizing diagnostics

Fixed normal-product browser evidence: **1 passed in 14.97 s**, engine `1ff01f1e8e370ef6781b5ec579ce60749310fbe3c0fcb5f78030c7aa7299f5e6` unchanged before/after. Durable library: `artifacts/forward-comparison-m5b-20261108/browser-release/data/test_prospective_funded_scope_0`. Current report `216d13ae86844b2b8ead0e220f974b8b`; monitor `1953f7df064d412495362af15130bf85`; partial report `10895d18685f47d1bdb7c53f7d3f9bf1`; complete report `cd42126181b44fe4b4d4b0eaad56e4a1`. Verified 8 downloaded files and 15 ZIP members, source CSV identity, unchanged prior snapshot, zero-POST reopen and owned server teardown. Desktop comparison/quantity views and 390 px comparison were manually inspected. `verification.json` and `evidence.json` retain exact checks and hashes.

The first new browser run is preserved at `artifacts/forward-comparison-m5b-20261108/browser-final`: 1 failed in 19.39 s. It exposed horizon valuation versus assessment knowledge-clock handling for a real supplied trade. The coordinated backend repair was verified before the fresh release run. After release, an approved copy-only clarification changed “frozen policy” to “frozen trading/sizing policy”; no numerical behavior changed. Final full-suite and bounded read-render validation of that exact final copy is reported separately after those checks finish. Earlier pair/monitor reports remain unchanged.

### Existing product journey

From a completed current-development report, expand Observe current policy, select an authoritative retained Funded package, and declare the observation source/provenance. The optional complete observation scope is saved immutably with that monitor. It contains the supplied account ID, first CME session, exclusive Chicago-date cutoff, every open session, declared early closes and the relation to the saved model calendar. The original forecast is not modified. Copying frozen dates preserves the absolute dates; explicit translation preserves relative session offsets and requires a transport rationale. The server checks weekday, civil horizon, full session/early-close pattern and single saved cohort. A translation is a declared assumption, not established stationarity.

The normal check shows exact plan/package/binding hashes, UTC opening/cutoff, receipt convention, source calendar and supplied/unverified status. Declaration must precede the first full CME session opening (17:00 Chicago on the preceding civil date). An old forecast cannot be treated as a newly observed prospective interval merely by changing labels.

After observation, use the existing event-file check/import. Include opening and closing flat position snapshots at the exact saved boundaries, all supplied signals/intents/orders/acknowledgements/fills/protection/positions/cash, and an `account_coverage` completion event referencing the exact plan, package and account. Complete coverage, fresh account, no replacement, frozen-policy adherence, terminal status and known pending trader cash are explicit supplied claims. Completion is received after the horizon. Partial, inconsistent or unknown coverage remains NOT_COMPARABLE.

The ordinary assessment report retains the original expectation and gives a descriptive one-account cash difference only when matched scope is established under those supplied claims. Request, gross deduction, received cash and pending entitlement remain separate. Cash at or after the exclusive cutoff is excluded from that horizon. One observed breach/no-breach or receipt/no-receipt is displayed beside the saved modeled probability; it is not a calibration score, p-value, expected-value accuracy test or future guarantee.

### Independent fixed-policy browser example

The actual current-procedure model preserves original dates 2026-01-27 through exclusive 2026-02-03 and expected trader receipts $1,500. The monitor explicitly declares a same-weekday translation to 2026-11-10 through exclusive 2026-11-17, with open sessions November 10, 11, 12, 13 and 16. The synthetic test receiver clock creates the monitor on November 9 before the full session opens at 23:00 UTC. The cutoff is November 17 at 06:00 UTC.

One separately supplied 3 MNQ round trip earns $6 gross P&L, costs $3 commission and nets $3 trading P&L. Supplied request/deduction/receipt amounts are $50 each; final flat account balance is $49,953. The complete-scope observed trader receipt is $50, so observed minus the frozen expected receipt is exactly −$1,450. This is not a claim that a provider would authorize the synthetic request. The local fixed-quantity check expects and observes 3 contracts; provider/platform implementation remains unverified.

First, the event file intentionally declares partial coverage and the report remains NOT_COMPARABLE. A new immutable correction supplies complete coverage; the new report becomes SYNTHETIC_SCOPE_COMPARISON while the first report bytes stay unchanged. Exact absolute-date mode with translated dates rejects before monitor creation. All incoming events and both raw files remain downloadable with original server-received clocks and correction links.

The browser fixture injects a deterministic clock into its ordinary test server and explicitly saves `synthetic_harness_clock` provenance. The product checkbox only declares that provenance and cannot change server time. There is no demo page, demo endpoint or product test-clock control. Normal paper/actual observation requires the real horizon to elapse; supplying future completion records does not establish complete received coverage. Do not replay this synthetic clock fixture as evidence of real elapsed performance.

### Dynamic decision evidence

A `sizing_decision` event links the signal to a preceding reconciled flat position snapshot and supplies account state, known-at clocks, execution timing, decision reference, initial stop, submitted quantity and trade/skip action. AlphaQuest recalculates with the actual frozen policy/planning assumptions using its existing local sizing implementation. The report shows supplied and recalculated quantities, requested quantity, denominator/budget, caps, reasons, planned risk and causal clocks. Later entry fills are not sizing inputs. A supplied skip needs an explicit zero-quantity decision; omitted opportunity history is not invented.

An arithmetic MATCH is conditional on supplied context. Floors, caps, platform strategy eligibility and broker enforcement are not independently verified. Missing context, mismatches, stale prior balances, unknown ordering or unsupported conditions remain visible and withhold matched scope when required. The authoritative native dynamic-current-policy API publisher passed in **182.93 s** on the same final engine. Normal library: `artifacts/forward-comparison-m5b-20261108/dynamic-api-final-v2/data/test_actual_native_current_per0`. Current-development report `634198a4ed454ed0b7a0915aa4b13099`; monitor `7d270d54d1db4058aaa8ce444b1f8298`; matching assessment `08471bf5e92544c9ab237ce3424fd1da`; discrepancy assessment `0339ff79ce6a4a5db580d5454eda251a`.

The actual saved policy risks **0.8% of current account balance**, with zero planned execution costs and an initial stop 20 points from a 100 reference on MNQ ($2/point): planned unit risk is $40. At $50,000, budget $400 gives 10 contracts. After a supplied $100 trading loss and a reconciled $49,900 flat snapshot, budget $399.20 gives 9 contracts. The later supplied trade earns $180, leaving $80 net trading P&L and $50,080 equity. This realized first loss is distinct from the $400 planned stop budget. Provider/user/policy caps are supplied and visible (20/40/60); none binds those two decisions. Receipts remain $0.

A correction supplies 9 for the first decision when the frozen local arithmetic expects 10. The discrepancy remains MISMATCH/PAUSED; the original matching report remains immutable. Both are SYNTHETIC_ONLY. No complete lifecycle comparison plan was asserted for this separate dynamic observation, so its forecast comparison remains NOT_COMPARABLE rather than inventing a horizon outcome.

Bounded read-only portal verification opened both saved assessments and the actual current-policy form, checked supplied/recalculated quantities and denominators, captured desktop causal context and 390 px mismatch rows, verified 4 downloads and 15 ZIP members, and reopened without any POST. It verified the final trading/sizing wording. Evidence: `artifacts/forward-comparison-m5b-20261108/dynamic-render/verification.json`; screenshots were manually inspected. Its temporary server stopped and joined. This renderer check performed no source generation, new assessment, strategy execution or policy selection.

### Reproduction and limitations

The final browser test is `tests/test_forward_comparison_browser.py`, using the real current-procedure, monitor, event-import, assessment and AnalysisStore routes. Save stdout/stderr and JUnit to a fresh artifact directory; retain its normal dataset/report library and hashes. It verifies screenshots at desktop and 390 px, unchanged prior snapshots, exact normal ZIP contents, source CSV identity and zero-POST saved reopen. All temporary servers stop and join at fixture teardown.

A normal manually started server uses `ALPHAQUEST_DATA_DIR="$PWD/<saved-library>" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8022`; stop with Ctrl-C. Saved synthetic reports reopen without advancing any clock or rerunning selection. Inspect immutable evidence libraries without changing them; use a separate copy for experiments. This increment supplies a descriptive matched-scope comparison, not calibrated future distributions, connected execution or production qualification.

### Open the fixed release library

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/forward-comparison-m5b-20261108/browser-release/data/test_prospective_funded_scope_0" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8022
```

Open `http://127.0.0.1:8022/#backtests/prop/job/cd42126181b44fe4b4d4b0eaad56e4a1` for the complete comparison and `/#backtests/prop/job/10895d18685f47d1bdb7c53f7d3f9bf1` for the preserved partial observation. Open `/#backtests/prop/monitor/1953f7df064d412495362af15130bf85` for the immutable plan, original raw batches, event corrections and saved as-of state. The synthetic receiver clock remains explicitly labeled; reopening does not advance or control the real server clock. Stop with Ctrl-C.

Complete report SHA-256: `d051a69063d2559b17d8771a5804c4c3b3fc22cf3a77f1d3d1a5e810048511b4`. ZIP SHA-256: `0e635a3768d4783afded93fa208c870fd1f56defca5a4ec93419d7b56989a58c`. Source CSV SHA-256: `47bfeaf8e6465fd14975a9d02e7f750f3995ed029cb68810d85db49158e26b37`. Plan SHA-256: `828b22ca7b7715bf1fc47a7653e2e851f3ad45ab1a5033c308e3ae909e299b80`. All other hashes and exact creation/receive/assessment clocks are in the evidence manifest.

### Open the authoritative dynamic library

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/forward-comparison-m5b-20261108/dynamic-api-final-v2/data/test_actual_native_current_per0" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8022
```

Open `http://127.0.0.1:8022/#backtests/prop/job/08471bf5e92544c9ab237ce3424fd1da` and `/#backtests/prop/job/0339ff79ce6a4a5db580d5454eda251a` to compare immutable arithmetic evidence. Expand Supplied policy decisions versus local arithmetic, then the causal-clocks section. Current monitor is `/#backtests/prop/monitor/7d270d54d1db4058aaa8ce444b1f8298`; its latest discrepancy remains PAUSED. Stop with Ctrl-C. Historical saved assessment clocks are not a present-health claim.

Matching report SHA-256: `1d270d7f5a63e05452a486afb2954ae2186ce2ba126183fa3f09381291bf4bde`. Discrepancy report SHA-256: `d0b2e9dfb12cb3d4e28f563529ea81fc8d38dea985c456f8c6a9acf421fc6b6b`. The normal library retains `dynamic-monitor-request.json`, `dynamic-monitor-events.json`, `dynamic-monitor-report.json` and `dynamic-monitor-evidence.json`; the read-render directory includes both normal ZIP downloads and hashes. Across fixed and dynamic browser evidence, 12 downloaded files and 30 ZIP members were checked. Full-suite results remain separately reported by the suite owner.

To rebuild the authoritative dynamic API example, run `tests/test_forward_dynamic_api.py::test_actual_native_current_percentage_policy_reconciles_supplied_arithmetic_and_freezes_report` with a fresh `--basetemp`, log and JUnit destination. It uses normal synthetic native source/current-policy/monitor paths; it is a heavier calculation than saved report inspection.

To repeat only the bounded saved-view check without calculations:

```sh
PYTHONPATH="$PWD" .venv/bin/python tests/inspect_forward_report_browser.py --library artifacts/forward-comparison-m5b-20261108/dynamic-api-final-v2/data/test_actual_native_current_per0 --expectations artifacts/forward-comparison-m5b-20261108/dynamic-render/expectations.json --output /absolute/fresh/render-directory
```

Use a fresh output path. The utility rejects a missing library, issues no POST requests, asserts the independent expected quantities/denominators and copied wording, checks unchanged normal downloads, and shuts down its own temporary server.

## 8 November 2026 — Final acceptance repairs and readable sizing explanations

The first complete suite retained 2,262 passes and eight investigated failures;
it is not a passing release result. The failure dispositions and retained paths
are in `robust_research_plan.md`. The corrected application identity is
`cb93c970dab535aaa3b0943243b15695e2c1b885513a13da164008e92bab3866`.
Malformed saved timezone metadata now reaches the normal dataset diagnostic
before any cache or source read. The 116-case reader/access/cache gate passed;
phase calculation identities remain unchanged. This does not change valid
source calculations or authorize reuse by omitting changed code from identity.

The normal saved monitor report now displays `current account balance` and
readable mismatch reasons. JSON downloads retain the original reason codes.
The actual repository read-render utility reopened both prior dynamic reports
on the corrected source, verified their original SHA-256 values, four downloads
and 15 ZIP members, and made zero POST requests. Desktop and 390 px views were
inspected. Evidence, independent expectations and the exact command are in
`artifacts/final-research-acceptance-20261108/dynamic-label-browser-v1/`.

Use the authoritative dynamic-library startup command in the preceding section.
Open the matching and discrepancy report links, then expand **Supplied policy
decisions versus local arithmetic**. Expect quantities 10 then 9, balances
$50,000 then $49,900, risk budgets $400.00 then $399.20, and readable words in
the denominator/reasons cells. The corrected supplied first quantity is 9
against a recalculated 10, producing MISMATCH and advisory PAUSED. Both snapshots
retain actual synthetic trading P&L $80 and ending equity $50,080. The prior
matching report stays unchanged. Download JSON/ZIP, reload, and reopen from the
monitor: no calculation is launched. Stop the temporary server with Ctrl-C.

The repaired prospective-clock/API/browser gate passed eight cases, including
future policy seals and DST boundaries, under the corrected source. Its normal
browser library is available with:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/final-research-acceptance-20261108/forward-clock-repair-gate-v1/data/test_prospective_funded_scope_0" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8022
```

Open `http://127.0.0.1:8022/#backtests/prop/job/1472693d8494404baaeacd1e4027a8bf`.
Expect frozen receipts $1,500, synthetic supplied receipts $50, difference
−$1,450, trading net $3, ending provider balance $49,953 and fixed quantity 3.
The earlier partial report `47da447933d747ceb03998c061465d4b` remains
NOT_COMPARABLE. The normal monitor is
`/#backtests/prop/monitor/1aeec84afa114078865727179a1d8187` and current-policy
report is `/#backtests/prop/job/bc58047afe384d65ae7f42734ea11adc`. Eight downloads,
15 ZIP members and unchanged prior bytes were checked. Stop with Ctrl-C.

These examples use labeled synthetic inputs and test-harness receiver clocks.
The product cannot change its server clock. Original forecast dates stay fixed;
the test declaration follows the actual policy seal and chooses a compatible
later observation window. Reopening these reports does not create genuine
future observations or a present broker-health claim. All automated temporary
servers stopped. A fresh complete passing suite remains the final release gate.

## 8 November 2026 — Native Lucid campaigns and provider identity qualification

### Native Lucid Evaluation profile in the existing research workflow

This increment exposes the already implemented native Lucid Evaluation controller in ordinary phase campaigns and nested economic studies. Lucid Evaluation is available only with **Actual native strategy reruns · MNQ**. Saved trade-path Evaluation remains Apex-only. Changing execution method retains the selected profile, fees and timing assumptions and blocks an unsupported declaration until the user chooses a supported execution method or explicitly changes profiles.

The local Lucid Evaluation summary shows the $3,000 target, $2,000 EOD trailing drawdown, 40% best-day consistency, no modeled evaluation expiry, the local $1,200 soft daily stop and 30-calendar-day activity rule, and the required zero activation fee. These are model rules; provider parity and deployment authorization remain unverified. Evaluation retry delay is entered in calendar days and activation delay in eligible sessions, each an integer 0–365. Defaults remain 0 and 1. Source trading commissions are charged once; account purchase/activation fees are separate explicit assumptions.

Synthetic independent arithmetic: the saved MNQ source has five complete IS sessions, January 5–9, with one 1-MNQ trade per session. Entry 118 to exit 268 earns $300 gross minus $1 round-trip commission, hence $299 net. Separate complete ordinary manual OOS sessions January 26–30 are retained in the source dataset and are not used by the campaign forecast.

In **Configure prop analysis → Create Evaluation campaign**, select native execution, LucidFlex 50K, fixed sizes `3,10`, four paths, seed 1729, block length 1, modeled start January 12, 2026, horizon 7 calendar days and calendar coverage through January 20. Keep the derived IS session window at January 5–9, 2026 and retain one detailed forecast path per candidate. Set modeled calendar version `explicit-synthetic-lucid-evaluation-v1` and timezone `America/Chicago`; leave the declared closures and early closes empty for this synthetic example. Declare evaluation fee $80.50, activation fee $0, retry delay 0 calendar days and activation delay 0 eligible sessions. This modeled calendar is explicitly synthetic and unverified. Use **Save and check candidates**, inspect the complete two-candidate work preview, then **Run campaign**.

Expected modeled outcomes: 3 MNQ earns $897 per trading session, passes January 15 and is ready January 16, for $80.50 acquisition cost and 4 calendar days. 10 MNQ earns $2,990 per session; after two sessions its $5,980 profit exceeds the target, but its best day is 50%, so it has not passed. Its third session yields $8,970 total with a one-third best day; it passes January 14 and is ready January 15, for $80.50 and 3 calendar days. All four paths complete in this deterministic synthetic pool. The complete Pareto frontier contains 10 MNQ; there is no hidden weighted cost/time score. Zero simulation variation in this constructed pool is not future precision or provider certification.

Inspect candidate forecasts, source/model date mapping and retained native decisions. Download the normal report and analysis ZIP; every manifest artifact is verified. Reloading the saved campaign must issue no POST and leave report/source bytes unchanged. At 390 px the controls and report remain usable without page-level horizontal overflow.

For nested research, include Evaluation and choose native execution before selecting Lucid. The separate catalogue leaves Lucid disabled for a new saved-path study. Save a draft/template with a declared $90.25 evaluation fee, the required $0 activation fee, retry delay 2 calendar days and activation delay 0 eligible sessions; load it and verify the exact declaration and choices survive. Loading requires fresh preview. Switching to saved-path execution retains Lucid and fees but blocks saving/running; switching back restores a valid native declaration. An explicit new legacy Apex declaration removes the native execution settings without changing the original native draft/template. The draft demonstration performs a real compatibility preview, not an economic run.

The final new browser gate passed **2 cases in 59.61 seconds** on frozen engine `456f68cbf67775382ffe22ac8df819ec53878c4b50c92a47259f68d43048cad4`. Production Python, all portal JavaScript, index HTML and the captured test files were identical before and after. The complete command, log, XML, identity snapshots and independent download verification are under `artifacts/native-lucid-evaluation-20261108/browser-final/`. The earlier failed provisional draft deliberately contained an unsupported $7.50 activation fee; the final test now proves that rejection explicitly and then previews the supported $0 declaration. Earlier directories remain unchanged.

The normal campaign library is `artifacts/native-lucid-evaluation-20261108/browser-final/data/test_native_lucid_evaluation_c0`. Saved source: `d84f2b1e3ab740b2911b76bceca4bdf0`; campaign: `140a33935dff49ba9935b98c0a106b86`; normal analysis: `de501fd20637460e999b3d063fdab224`. Its saved research split is IS `2026-01-04`–`2026-01-09`, OOS `2026-01-25`–`2026-01-30`; the actual CME session dates are January 5–9 and January 26–30 respectively. Each interval contains 6,900 complete observed synthetic minute bars. Dataset symbol MNQ, source timezone UTC, tick size 0.25 and point value 2 are saved in `source-report.json`; the exact strategy parameters and $0.50 commission per side are there too.

To inspect and reproduce through the product while preserving the evidence library, run from the repository root:

```sh
AQ_LUCID_DEMO=$(mktemp -d /tmp/aq-lucid-evaluation.XXXXXX)
cp -R "$PWD/artifacts/native-lucid-evaluation-20261108/browser-final/data/test_native_lucid_evaluation_c0" "$AQ_LUCID_DEMO/library"
ALPHAQUEST_DATA_DIR="$AQ_LUCID_DEMO/library" .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8017
```

Open `http://127.0.0.1:8017/#backtests/report/d84f2b1e3ab740b2911b76bceca4bdf0` for the saved source and follow the configuration steps above to create a new campaign in the disposable copy. The already saved result is at `http://127.0.0.1:8017/#backtests/prop/campaign/140a33935dff49ba9935b98c0a106b86`; direct normal analysis is `http://127.0.0.1:8017/#backtests/prop/job/de501fd20637460e999b3d063fdab224`. Opening or reloading the existing report issues no calculation POST. Stop the server with **Ctrl+C**. No persistent server was started for this gate; both temporary test servers stopped and joined successfully.

The separate nested settings library is `artifacts/native-lucid-evaluation-20261108/browser-final/data/test_native_lucid_nested_draft0`. Copy that directory instead in the same startup command to inspect source `6bc6cd4458f44cc9b1666df23f20a0f4`, draft `334e4605063d4d1dabc33675f2423942`, template `5857b346740d4c208a2e263a6dca4959`, and explicit legacy Apex draft `430aeb8bd5a744c58aaf5a117e467fc6`. Open `http://127.0.0.1:8017/#backtests/research?draft=334e4605063d4d1dabc33675f2423942`; review the native Lucid profile, $90.25/$0 fees and 2/0 timing, then preview compatibility. This library contains no nested research execution result; it demonstrates exact settings restoration, source checks and rejection boundaries.

The final campaign `report.json` SHA-256 is `8c8fa8be09ac238591213de14314fbb4c9207e77a00f62404f9f9111d4e1d614`; `analysis.zip` is `db6845362ebfcbd039bd81e6702119303c589f9b0cfc758f3ba33b09eb4ffcfc`; the exact saved dataset CSV is `3de6309cfef611c1f4b391ca64b99188f4cd14a65e0837213f312a4c11c58d71`. All 10 downloaded files across the two journeys and all 17 ZIP members were independently verified. The screenshots retain the source/model clocks, explicit unsupported-profile message, native forecast metrics and narrow decision/form views. Report/source bytes remained unchanged on reopening.

Five applicable existing browser regressions passed in **169.89 seconds**, separately under `artifacts/native-lucid-evaluation-20261108/browser-regression/`: all four native campaign cases and the native policy draft round-trip/membership guard. All five temporary servers stopped and joined, and the before/after production, web and captured test hashes remained identical. All 21 retained downloads and 78 report ZIP members in these regression libraries were independently checked. The full set is recorded in `browser-regression/verification.json`. This is a focused product gate, not a claim that the full repository suite or provider parity is complete.

The final API gate passed **6 cases in 243.65 seconds** on the same frozen engine. It includes the two Lucid cases and all four existing native phase campaign cases. The final native Lucid campaign is `24e82a0a69ef4610bd515348c43cae76`, forecast `1d2908113b384f719b9e305375b6eb6a`, frozen ordinary OOS assessment `8e14e58a24fa4ca39eca95faf82e9d29`, chronological child `42e915c25476481c8d4b41b57db5ba69`, and exclusive-cutoff forecast `949d1485626c43179a10172f391b3377`. The exact library, commands, independent arithmetic and normal copy/start/reopen instructions are in `artifacts/native-lucid-evaluation-20261108/final-api-v1/README.md`. Expected ordinary OOS pass is January 28 and readiness January 29; acquisition cost is $80.50 and evaluation profit is not trader cash. At the January 15 exclusive cutoff, readiness is censored and acquisition means remain null while fees are retained.

Actual freeze/OOS qualification exposed a missing Lucid implementation-identity entry. Both phase identities now capture each provider runtime used by native controllers, its source and compiled-kernel identity, and shared decimal arithmetic. These necessary identity changes intentionally prevent incompatible historical frozen packages from launching; saved historical reports and downloads remain readable. No numerical formula changed. The final seven-case identity gate in `artifacts/final-research-acceptance-20261108/phase-kernel-identity-final-v2/` passed in **29.61 seconds**, with no skips in this installed environment. It verifies direct source coverage, both phase cache identities, and an actual $1,500 Funded forecast whose frozen OOS launch rejects either changed provider runtime before OOS execution or access-ledger append. Prior report/ZIP/package bytes remain unchanged.

## 8 November 2026 — Complete local research acceptance

The unchanged complete repository run passed **2,315 tests**, including 176
browser cases, with zero failures/errors/skips and 24 existing deprecation
warnings in 6,497.25 seconds. Qualified commit:
`1d9214f8c154a01c85d0bcc1b869ba4fc4b21bfa`; engine:
`456f68cbf67775382ffe22ac8df819ec53878c4b50c92a47259f68d43048cad4`.
All 405 tracked files matched the pre-run archive after completion. Subsequent
changes only clarify documentation. All eight original full-suite failures pass
in this run; the earlier failed/interrupted libraries remain preserved.

The artifact-only final index verifies 23 normal product journeys, 74 sealed
reports, 1,113 manifest components and all 1,187 ZIP members, 302 saved backtests,
29 dataset records and original bytes, 42 captured downloads and 46 screenshots.
It checks independent expected outcomes, rather than only test counts. Exact
source hashes, IDs, normal URLs, seeds/schedules, saved settings, screenshots and
reopen proof references are in
`artifacts/final-research-acceptance-20261108/representative-final-index.json`.
SHA-256: `2e4ff8afbb3a031acc84f53b0e948ba9bfb9c2e86df08e6cf2cae4e6a177c1e9`.

For the final Lucid browser library, copy the saved normal data directory before
performing experiments:

```sh
AQ_FINAL_DEMO=$(mktemp -d /tmp/aq-final-research.XXXXXX)
cp -R "$PWD/artifacts/final-research-acceptance-20261108/full-suite-v3/data/test_native_lucid_evaluation_c0" "$AQ_FINAL_DEMO/library"
ALPHAQUEST_DATA_DIR="$AQ_FINAL_DEMO/library" .venv/bin/python -m uvicorn alphaquest.app:create_app --factory --host 127.0.0.1 --port 8777
```

Open `http://127.0.0.1:8777/#backtests/report/c52b7e62a4aa4a50889199959d196ed2`
for the source, or
`http://127.0.0.1:8777/#backtests/prop/campaign/e2b2c0dd49084d9783bcae2ad4c90537`
for the campaign. Direct analysis is
`http://127.0.0.1:8777/#backtests/prop/job/ecb4547babe0454581c32c45b7d0e47b`.
Repeat the exact profile/calendar/fee/sizing declaration in the preceding Lucid
journey. Expect $299 net per MNQ per source session, $80.50 purchase and zero
activation fee, 10 MNQ at three acquisition calendar days versus 3 MNQ at four.
The second 10-MNQ session crosses target but fails 40% consistency; the third
passes. Saved reload issues no calculation POST and leaves the report bytes
unchanged. Stop the temporary server with **Ctrl+C**.

To inspect other final libraries, replace the copied directory with the exact
`library` field in the final index and use that entry's `reopen_urls`. The index
also gives every named test and independent expectations. The fixed forward
comparison retains $1,500 modeled receipts versus $50 supplied receipts, a
−$1,450 difference, $3 trading net and $49,953 account balance; its earlier partial
snapshot stays NOT_COMPARABLE. The frozen pair retains $70 acquisition fees,
$1,500 receipts and $1,430 net. The native dynamic observation recalculates
10 then 9 contracts from 0.8% balance/$40 unit risk, with $80 trading profit and
$50,080 final equity; a changed supplied quantity remains MISMATCH/PAUSED without
changing the earlier report. These are explicitly synthetic local-model
demonstrations, not observations of future returns.

No persistent server was started. All automated server fixtures stopped. The
full command/environment, warning details, Definition-of-Done mapping and
publication record are in the [final acceptance record](robust_research_plan.md#final-acceptance-record).
Local research acceptance is complete. Provider/platform/broker/live readiness
remains unverified; no order placement or broker-enforced pause is supplied.

## 8 November 2026 — Delete unused phase campaigns and release source pins

The existing **Research → Manage campaign** screen now exposes checked phase
campaign deletion. It shows source-link and retained-analysis counts, rejects
frozen/assessed/active/dependent records with their IDs, and rechecks the fresh
confirmation inside the same analysis lock and one immediate catalogue transaction.
Deleting a campaign keeps backtests, jobs, completed reports, attempts and access
history. A backtest can then be deleted separately if no remaining owner pins it.
The original candidate membership is retained in the deletion record, not edited.
Deleted IDs cannot be reused for phase or nested campaigns. A deleted campaign
URL reopens its receipt, and the original declaration/manifest is downloadable.

The API/source ownership, stale-confirmation, idempotent retry, shared-report,
source/job-pin and deleted-ID checks passed. Fault injection on deletion of the
parent row, after all three association tables had been modified, rolled back
all links and the audit insert. A subsequent retry succeeded. Metadata-only
inspection/deletion passed with source reads and calculations poisoned.
Research-access rows were preserved rather than relabeled as untouched.

Final gates: **69 affected backend regressions**, **17 deletion API cases**, and
**4 browser cases** passed (90 distinct cases). A final receipt wording correction
also passed the new browser journey again in 44.16 seconds; it is not counted as
a new unique case. API/browser probes that exposed the missing frozen owner ID
and an asynchronous dialog test wait remain retained. The earlier complete
2,315-test gate stays bound to its original snapshot; this is a focused increment
qualification. Both phase numerical identities and all 33 files per phase still
match that snapshot. No phase formulas or legacy report meanings changed.

The actual final product library is
`artifacts/campaign-deletion-20261108/browser-release/data/test_campaign_delete_confirmat0`.
The copy/start/normal URLs, exact settings, stop command, independent expected
values, rejected boundaries, gate commands, hashes and inspection are in
`artifacts/campaign-deletion-20261108/README.md` and `verification.json`.
The saved example shows source backtest → Configure → Check → Run → a normal
Funded report with modeled receipts $0/$1,500 at 1/3 MNQ → cancellation preserves
the campaign → confirmed campaign deletion releases one source link → a separate
backtest deletion succeeds → the phase report and ZIP remain byte-identical.
The source input/report downloads and nine access events remain inspectable.
All three saved reports, 47 components, 50 ZIP members and five downloads were
independently verified. Desktop and 390 px screenshots show the real controls
and durable receipt; saved receipt reload makes no POST or DELETE.

The original user campaign was previewed only on a disposable consistent copy
of its catalogue, opened read-only. It is eligible to release 32 source links
and retain its completed analysis. No production campaign/backtest was deleted.
Restart a non-reloading development server to load the new API/schema, then
refresh the browser and confirm through **Research → Manage campaign**. Every
automated temporary server stopped and joined. No persistent server was started.


## 8 November 2026 — Research library purpose and simple campaign search

The existing Research page now leads with its purpose and one search field.
Campaigns, strategy studies and drafts have one-click category buttons; optional
phase/status/order controls are collapsed under More filters. Active filters
remain visible, with a single clear action. Cards show purpose, human-readable
strategy, dataset, full campaign ID, linked counts and View results / Manage
campaign actions. Saved stage, hashes and limitations are available on demand;
completed execution remains distinct from qualification. New-research source
selection loads only when requested and opens the ordinary backtest report.

Search now inspects every retained campaign source, activity and analysis link,
plus draft source/job references, rather than only its representative source.
Readable strategy names, compact/hyphenated UUIDs and a pasted link/log containing
one unique UUID are supported. Filtering/pagination remain metadata-only, with
execution and source-price reads poisoned in the API regression. No new store,
calculation, phase-selection rule or production-data migration was introduced.

The saved normal-product journey is report → Configure prop analysis → whole-grid
source check → Funded run → durable report → Research search by activity and both
source IDs → management/results → optional-filter empty state → clear → recovery
from a failed read → new-research source report. Independent synthetic net
outcomes are $300/$100 per MNQ per session at sizes 1/3; expected receipts under
the saved 14-day horizon and four-day lag are `[0,0,0,1500]`. The winning path's
second $1,500 stays pending beyond the horizon. All three downloaded payloads
and 15 manifest components plus the ZIP report were independently verified.
Saved browsing/reopening made no POST, PUT or DELETE and preserved report bytes.

The intact final library is `artifacts/research-page-ux-20261108/release/data/test_find_campaign_by_activity0`. Campaign
`736aea3f4a4a41a7bfa5759a8f379235` can be found by activity
`47054089e48d49798f5c68988358cd68`, either linked backtest or its URL. Exact copy/start/stop
commands, source IDs, normal URLs, settings, independent expected outcomes,
boundary/recovery checks, screenshots and gate reproduction are in
`artifacts/research-page-ux-20261108/README.md` and `verification.json`.
Desktop and 390 px screenshots were visually inspected; no horizontal overflow
was observed. Temporary test servers stopped and joined; no persistent server
was started. Existing user campaigns/backtests/results remain unchanged.

The final focused gate passed **40 cases** (34 API and six browser) in 101.66 s,
with zero failures/skips and one existing deprecation warning. Source hashes
were stable throughout; both phase numerical identities still exactly match
the earlier complete 2,315-test snapshot. This is a focused UX/catalogue
qualification, not a new full-suite or numerical/provider parity claim.

A metadata search on consistent disposable backups of the user's current
catalogues also found campaign `cc0fb9e5ecc5425bad4db20839eae37d` from activity
`19687121020d4487b9a3498ce416143f` and backtest
`739b88028ef846fdb8891ecb307ed574`, each with exactly one match, 32 linked backtests
and one activity. Original databases were opened read-only; no campaign was
deleted. The saved record is `artifacts/research-page-ux-20261108/actual-campaign-search.json`.
Restart an existing non-reloading app server once for the expanded backend
search, then refresh Research to load the new controls.

A separate saved-state browser probe reopens a disposable copy of the completed
procedure library, shows No qualified candidate prominently, and verifies distinct
Final verification / Current development statuses and the final-report backlink.
It records zero writes in `saved-assessment-states.json`; its screenshot was
visually inspected and its temporary server stopped. Finished intermediate data
was archived losslessly (1,490 verified payloads, 93.3 MB to 8.1 MB), with actual
tar restoration checks and notices at the original paths. The release product
libraries remain unpacked.


## 8 November 2026 — Cancel queued backtest activities

The existing **Strategies → Backtest activity** list and activity detail header
now expose **Cancel queued activity** only while a job is queued. Confirmation
cancels that activity; dismissal leaves it queued. The durable record retains
its declaration, timestamp/reason and all successful prior-attempt results.
It remains visible across reload/restart; deletion is a separate, reference-
protected action. Cancelled activities do not auto-resume. This action does not
stop running work or release campaign references.

The normal `POST /api/backtests/batches/{id}/cancel` endpoint (optimization alias
also supported) serializes its status transition with the worker claim using the
existing SQLite catalogue's immediate write transaction. If cancellation wins,
the delayed callback exits before runtime admission, source access, cache reuse
or publication; if execution wins, cancellation returns 409 without mutation.
Cancelled retries are idempotent. Unknown IDs return 404 and malformed IDs 422.
Cancelled/deleted stale callbacks were checked with execution and runtime
admission poisoned. Existing resume, parallelism, caches and report meanings are
preserved. No new store or execution service was added.

The saved product journey uses normal source/configuration → queued activity →
detail cancellation → reload → history cancellation → active/next-job completion
→ retained ordinary report. Its source is labeled **SYNTHETIC queued cancellation
arithmetic**. The independent oracle uses entry 100.25, exit 101.75, point value
10 and 2 CU round-trip commissions per contract: 13 CU per contract, hence
`[13,26,39]` for the 1/2/3-contract trials. Both unaffected jobs produced those
values and retained six normal reports. Both cancelled jobs stayed at zero
trials with no start timestamp. There were exactly two cancel POSTs, no DELETEs,
and dismissing confirmation preserved the queue. A separate queued-resume check
preserved earlier report and prop-file hashes. No OOS execution was launched.

The intact library is `artifacts/cancel-queued-activity-20261108/browser-release-v2/data/test_cancel_details_and_histor0`. Cancelled IDs are
`204a740b74794152a127c6c53d428e5d` and `c04858f263fb4a92aa2bbbd821578550`; unaffected active/next IDs
are `1415b0c2d79946a2a81660cd0fa7210d` and `926d4a2afc0e460cb7cc879abd548173`. Full copy/start/stop commands, normal
URLs, input arithmetic, expected boundaries, verified downloads and gate
reproduction are in `artifacts/cancel-queued-activity-20261108/README.md` and
`verification.json`. Desktop and 390 px evidence was visually inspected,
including scrolling to the table's action column. All temporary test servers
stopped/joined; no persistent server was started.

Focused qualification passed **90 distinct cases**: 60 cancellation/API/resume/
deletion, 27 parallel/cache/compact-report, and three browser cases. Every gate
had stable production hashes; production sources match across gates, and both
phase numerical identities still match the earlier complete 2,315-test snapshot.
The initial final-evidence fixture relabeling was rejected by normal duplicate-
CSV protection; that failed setup remains preserved. The final labeled input has
a distinct BOM identity and the final three browser cases pass. This increment
has focused qualification, not a new full-suite or numerical/provider-parity claim.

A non-reloading running app needs a backend restart before the new endpoint is
available, followed by a browser refresh. The production catalogue had activities
marked running and queued during this task; that server and all production jobs,
files and records were left untouched. Restarting only to cancel one queued job
can interrupt other work; wait for needed work to finish. Pre-update saved jobs
retain the existing engine-identity compatibility guard.

## Guided prop configuration — 2026-11-09

All eight configuration UX recommendations are implemented in the existing
backtest report → Configure prop analysis → check → run → durable report journey:

1. A goal-first landing recommends full robustness research, with separate saved
   candidate comparison and single-policy inspection choices. Legacy joint,
   budgeted cash-ledger and frozen-pair tools are explicit alternatives.
2. Sources → Research design → Accounts and sizing → Review and run shows only
   relevant settings. Tasks without research design omit that step.
3. Preliminary saved-source compatibility appears before detailed configuration;
   known unsupported native choices explain their requirements. Authoritative
   owner admission remains mandatory, and no execution is silently substituted.
4. Evaluation and Funded objectives/settings stay independent. Inactive phase
   controls are disabled so irrelevant validation cannot block the active phase.
5. Position sizing uses plain-language questions over existing fixed, dollar and
   percentage policies, bases and hard caps. Source costs are never charged twice.
6. Human labels and explanatory headings replace setup jargon; legacy JSON is
   an expert disclosure. Existing calculation meanings remain intact.
7. A desktop study summary and expandable mobile summary show declarations and
   check status; Review exposes every enabled setting plus authoritative checks.
8. Contextual window/sampling/seed controls, a selected-task all-settings view
   and separate previous-work history reduce the default form's density.

`docs/prop_setup.md` documents the workflow. Exact copy/start/stop commands,
source/campaign/analysis IDs, settings, normal URLs, downloads, expected boundaries
and screenshots are in `artifacts/prop-setup-ux-20261108/README.md`. The final
examples are intact normal product libraries, with SYNTHETIC source labels.
There is no separate demo page, API, database, simulation or evidence store.

Three normal-product demonstrations were executed through the guided controls:

- **Compare qualified candidates:** saved MNQ source, Funded Apex, fixed sizes
  1/3, 8 paths, block 1, 14 calendar days and 4-day receipt lag. The independent
  $300/$900-session paths produce modeled received cash `[0,1500]`; the next
  payout remains outside the horizon. Campaign `9a32a49effbe4395907f9fd75ab543c8`,
  analysis `18b0ea3355c847fea3a75116b0c68645` reopens without simulation.
- **Full robustness research:** two saved strategy sources, rolling 8/2 outer
  and 2/2 inner windows, 1/1 purge/embargo, qualification declared before work,
  optional independent Funded study at quantities 10/20. Every inner fold's
  qualification means are $100/$300 per session, matching independent synthetic
  arithmetic. Campaign `d71b087aece04a1d94a6fc7c498a26b8`, analysis
  `e1381e845e7c4ea1a5b1fea45a6755cb` saves research/reliability and remains
  **INCOMPLETE**, production_qualified false; this is not a deployment claim.
- **Inspect one native policy:** supported MNQ VWAP source, Funded Apex, fixed
  size 3. Independent unit nets `[-10,20,20]` imply `[-30,60,60]`, three trades,
  $90 trading profit, $50,090 provider balance and $0 trader receipts. Analysis
  `e7ed7d0006aa4bef99d8bb894348f001` and controlled backtest
  `d954b2da480847c7932577a1bd385a5a` are durable. Source report bytes are unchanged.
  The native JSON/ZIP are direct downloads, with every manifest component checked.
  This is one historical path, without a forecast or optimizer selection.

The guided checks exercise lazy loading without unrelated POSTs, preserved values
across steps/goals, remounting after report navigation, edit invalidation of Run,
inactive-phase validation, native compatibility, explicit qualification-only
intent, and recoverable defaults failure without a browser exception. Existing
Lucid restrictions still reject unsupported execution. Desktop and 390 px views
were inspected, including the mobile summary above the form and no page overflow.
Existing freeze, final manual OOS, drafts/templates, native campaigns/replays,
legacy economics, commission and historical report assertions remain in scope;
legacy detailed tests select their explicit goal/all-settings view.

The final primary browser sweep passed 21 cases and failed one old navigation
assumption: after restoring a draft to Sources, its test attempted to open the
hidden Accounts section. The test now follows the explicit navigation and that
exact native Lucid restoration case passes. Earlier diagnostic/interrupted
sweeps and their logs remain preserved; they are not claimed as clean gates.
The compatibility sweep passed 39 cases before stopping at three old navigation
assumptions: collapsed ordinary reports, reopened cash configuration at Sources,
and lazily loaded research history. Tests now select the applicable task/step or
open Previous analyses before accessing those controls; original arithmetic and
immutable-report assertions remain. A focused follow-up includes all three plus
the three cases not reached by that sweep. Final gate details and qualified case
membership are saved in `verification.json`. The follow-up passed all six cases.
Final qualification covers **113 distinct cases**: 46 backend contracts and 67
browser cases, counting each case once after its navigation correction. All
production hashes match across gates and current files; both phase identities
match the earlier full-suite snapshot. Native ZIP verification covers all 11
manifest components and the report itself. The sandbox-only Chromium launch
failure is retained separately; the permitted localhost browser follow-up passes.
This increment has focused qualification, not a fresh full-suite or numerical/
provider-parity claim. Production Python calculations were not changed.

All temporary servers stopped/joined. No persistent server was started and the
user's existing app/jobs, datasets, backtests and results were left untouched.
Refresh the browser to load this static UI change. Finished intermediate libraries
are losslessly compressed only after SHA-256 membership checks and full standard
`tar` restoration verification; original locations retain restore instructions.
Final examples remain unpacked, and prior evidence/reports are preserved.

## Twin Continuation strategy port — 2026-11-09

Delivered the supplied signal as the registered Python strategy
`alphaquest/strategies/twin_continuation.py` and the MultiCharts .NET signal
`multicharts/Twin_Continuation.cs`. The original is preserved in
`docs/strategies/twin_continuation.pl`. The
[strategy guide](strategies/twin_continuation.md) specifies all Inputs, chart
properties, execution assumptions, costs and the remaining platform checks.
This increment adds next-bar OCO entry stops and stop-only exits to the shared
backtester. Intrabar entry-bar extrema remain bounds; the existing prop source
adapter now admits their explicit `entry_stop` phase without changing account
transition/selection formulas or ignoring calculation hashes.

Saved **synthetic** normal-product evidence:

- `artifacts/twin-continuation-final-20261109/verification.json` records exact
  source/backtest/analysis IDs, parameters, IS/OOS splits and observations.
- Single-session MO backtest `2985e1f1faf841fab52ec2745cad4625`: entry 112.25,
  exit 119.75, `(119.75 - 112.25) * 20 - 2 = 148 CU` net.
- Single-session BO backtest `3c36c8fa0de2455fa8464a0319c3d1c0`: confirmed swing
  high/low 110/90, ATR 8, entry 110.25, target 126.25,
  `(126.25 - 110.25) * 20 - 2 = 318 CU` net. The analytical tests also independently
  check source MAE bounds 6 to 226 CU, with no measured MAE/MFE.
- Two-session MO backtest `abbc00df96444cb19643a1175a707071`: two source-driven
  trades of 148 CU each, total 296 CU. The second session contains explicitly
  synthetic leading flat bars to warm the continuing oscillator; Jan 17 is a
  zero-trade weekday. Its local prop analysis is
  `453e1af6d64f4afaa1a4d5108bb79f92`.
- Each source has its CSV, configuration/report screenshots, downloaded trade
  and equity CSVs, and report JSON. The two-session case additionally retains
  `momentum-prop-source-check.json`, source-check/report screenshots,
  `momentum-prop-prop-report.json` and `momentum-prop-analysis.zip`.
- `artifacts/twin-csharp-final-20261109/` retains a successful C# 5 core build,
  six input schedules, actual C# JSONL outputs and `verification.json`:
  **18,556 evaluated bars**, 15 state fields per bar and effective owned orders
  agree with Python. Cases include both directions/setups, missing boundaries,
  session volatility and ClockShift. This is a compiled-core comparison,
  not an installed MultiCharts backtest or SDK adapter compilation.

Reproduce with a **new** output directory:

```sh
.venv/bin/python tests/review_twin_continuation.py --output artifacts/twin-product-NEW
.venv/bin/python tests/review_twin_csharp.py --dotnet /path/to/dotnet --output artifacts/twin-csharp-NEW
```

The browser script uses Datasets → save a labelled synthetic source → Backtests
→ Twin continuation → declare IS/OOS → configure → Run → ordinary durable
report/downloads → Configure prop analysis → explicit legacy analysis form →
Check source → Run → durable local prop report/downloads. No separate surface,
result store, external engine or OOS launch is used. Backtest/source bytes and
reports are verified after reload. Owned temporary servers stop on exit.
Earlier review directories and reports remain unchanged.

Expected observations and rejection checks:

1. MO enters at the next observed Open, then exits at the next Open after the
   14:50 submission. Its entry-bar Low cannot trigger a stop before that stop
   has been submitted. BO's entry-bar High cannot retroactively fill its target.
2. The single-session examples reach the ordinary prop source check and reject
   with **At least two session weekdays are needed for separate training and
   validation**. Run remains disabled; rejection JSON/screenshots are saved.
   Insufficient research history is not bypassed or silently duplicated.
3. The separate two-session source passes the normal check: two native OHLC
   risk records, zero measured MAE/MFE, source net 296 CU and commissions 4 CU
   reconcile. Its saved local analysis reports zero validation passes and no
   funded result; the report explains that no training/validation evaluation
   passed. These are labelled synthetic model outputs, not forecasts or provider
   parity evidence. Reloading reopens the same report bytes without replay.
4. Automated boundaries cover both directions, equal pivots, partial/late
   buckets, the half-day heuristic, disabled MO consuming its opportunity,
   setup ownership, disabled BO target, pending-stop expiry, entry gaps,
   ambiguous two-sided stops, malformed Inputs and missing held session-close
   data. Known regular non-minute data rejects before research claims.
5. Twin reports omit the currently unsupported single-pending native entry
   decision sidecar; controlled native phase replay remains unsupported and
   rejects. The Backtests form and strategy guide disclose this boundary.

To inspect the saved library manually:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/twin-continuation-final-20261109" \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/#backtests/report/abbc00df96444cb19643a1175a707071`
or `http://127.0.0.1:8001/#backtests/prop/job/453e1af6d64f4afaa1a4d5108bb79f92`.
Download the stored artifacts; use `verification.json` for the other reports.
Stop this optional server with Ctrl-C. No persistent server was left running.
Matching original PowerLanguage and .NET exports from the installed Windows
platform remain necessary before claiming platform/trade-for-trade parity.

Validation: the focused execution/risk/native-decision/API/reuse/VWAP/grid/phase
identity/prop-analysis regression run passed **376 tests**. The final Twin suite
passed **30 tests**, including four additional stop-only evidence, invalid OCO,
setup-owned timed exit and disabled-target cases added after the broader run
was collected. The compiled-core comparison and browser journeys above also
passed. This is targeted validation; no full-repository or Windows-host pass
is claimed.

## Twin session-close failure diagnosis — 2026-11-09

A reported Twin backtest stopped with a generic HTTP 500 message after its
last displayed progress snapshot near 235,000 of 1,415,817 IS bars. Read-only
inspection found the saved Twin research window to be 2021-01-01–2024-12-31,
with source timezone America/New_York. Replaying the verified internal prepared
IS stream with **default Twin Inputs** and saved NQ instrument settings reproduces
a rejection at selected bar **239,337**, 2021-09-06 17:01 Chicago time. The
original failed HTTP request's Inputs were not persisted, so the reproduction
records its parameter/cost assumptions explicitly rather than claiming to have
recovered that request.

At that point a BO long remains open from 02:20 Chicago, entry price 15699.
The previous source close label is 12:00; the next observed label is 17:01.
The repository calendar's 2021-09-06 row is a noon early close. Twin's current
fixed BO flatten/session-close clocks are 15:45/16:00, so the guard rejects the
held position crossing 16:00 without an observed liquidation price. This
reflects missing holiday-close handling in this strategy port; the observed
noon gap is consistent with the saved calendar and does not by itself establish
corrupt data. No price-bar lookahead or invented close fill was added.

The guard previously raised an ordinary ValueError during replay. The fixed-run
API classified it as an unexpected error and returned only **Backtest failed;
no completed run was saved**. It now raises the existing handled DatasetReadError,
returning HTTP **422** with the configured close, last/next observed timestamps,
selected bar, held setup/side and a shortened-session/source-coverage explanation.
The trading rejection and numerical exit policy remain unchanged. Completing
this historical run still requires an explicitly specified shortened-session
exit policy, with corresponding Python/.NET integration and validation.

Saved evidence:

- `artifacts/twin-backtest-failure-20261109/{before-diagnostic.json,after-diagnostic.json,verification.json}`:
  actual IS failure state, source/cache hashes, default Inputs/costs and an
  unchanged failure bar, held position and 78 earlier completed trades.
  Source dataset/backtest databases were opened read-only. No OOS strategy
  replay or production report write occurred.
- The same directory includes the corrected strategy snapshot and a diagnostic
  reproduction script. From the repository root run
  `PYTHONPATH="$PWD" .venv/bin/python artifacts/twin-backtest-failure-20261109/reproduce.py`.
  It reads and checksums the existing internal cache, stops within the first
  240,000 IS bars, and writes its diagnostic to
  `/private/tmp/aq-twin-session-diagnostic-reproduced.json`. It requires that
  existing cache to remain available; no source data is recreated or changed.
- `artifacts/twin-session-rejection-review-20261109/` retains a labelled synthetic
  normal Datasets → Backtests → Twin → Run rejection demonstration, source CSV,
  configuration/error screenshots and `verification.json`. The visible error
  names the 16:00 configured close and observed 12:00 → 17:01 gap. The API's
  failed progress snapshot retains the same message; zero completed reports
  are published and source CSV bytes remain unchanged.

Reproduce the normal-product rejection in a new isolated library:

```sh
.venv/bin/python tests/review_twin_session_rejection.py --output artifacts/twin-rejection-NEW
.venv/bin/python -m pytest tests/test_twin_continuation.py tests/test_twin_continuation_api.py tests/test_backtest_api.py -q
```

The targeted run passed **84 tests**. The browser check passed with no browser
errors and stopped its owned temporary server. Existing user processes,
datasets/backtests/results and earlier evidence remain untouched. Reload the
backend code to receive the detailed rejection; this diagnostic change does not
make an unsupported holiday-close policy pass silently.

## Twin MC session-close parity — 2026-11-09

Implemented the measured MultiCharts session-close behavior in
`alphaquest/strategies/twin_continuation.py`, exposed through the existing
Backtests calendar controls/settings and saved report downloads. The supplied
workbook is preserved byte-for-byte at
`artifacts/twin-mc-early-close-parity-20261109/mc-reference.xlsx`. Its trade list
contains 685 paired trades through 2026-07-07; qualification and the new native
replay use only the 499 trades in the saved **2021–2024 IS**. No AlphaQuest OOS
run was launched. The provided workbook contains later outcomes and must not
be represented as untouched OOS evidence.

The `Strategy Analysis` and `Settings` sheets say **Export cancelled by user**.
The available `List of Trades` rows are complete paired entries/exits. Every
reported Profit ($) equals signed price change × contracts × 20. The zero-cost
comparison matches that exported arithmetic; it does not establish the missing
MC commission/slippage configuration or code/build identity. The export is a
development qualification oracle; no production report loads its trades or
requires MultiCharts.

Measured independent early-close expectations (Chicago close labels):

| MC trade / source rows | Entry | End of Day Exit | Expected reported P&L |
| --- | --- | --- | --- |
| 79 / 160–161 | BO long, 2021-09-06 02:20, 15699 | 2021-09-06 12:00, 15701.25 | `(15701.25-15699)*20 = 45` |
| 429 / 860–861 | BO long, 2024-06-18 19:01, 20223.25 | 2024-06-19 12:00, 20231 | `(20231-20223.25)*20 = 155` |
| 436 / 874–875 | MO short, 2024-07-04 09:21, 20377 | 2024-07-04 12:00, 20381.25 | `(20377-20381.25)*20 = -85` |

The local versioned NQ/MNQ calendar now supplies scheduled session-close
liquidation for both setups by default (`use_session_calendar=true`). It fills
at the **closing bar Close**, with configured market slippage/commission once;
it does not use the VWAP port's five-minute buffer or next-Open exit. Existing
price orders on that bar retain priority. Missing held closing bars and dates
outside reviewed coverage reject. Truncated data cannot establish an earlier
scheduled close. Custom BO session clocks require the explicitly labelled
fixed-clock mode; supported calendar mode uses 1700/1600. Calendar/code hashes
participate in normal report/cache/frozen compatibility. Earlier reports,
source exports, diagnostics and evidence remain unchanged.

The first corrected calendar replay completed all 499 trades and matched all
entry/exit timestamps, but found 214 fractional BO target-price differences.
The MC export consistently normalizes long sell-limit targets upward and short
buy-to-cover targets downward to 0.25 ticks. Applying the execution instrument's
outward target normalization resolves all 214. The final **normal saved report**
now matches **499/499** in entry/exit timestamps, directions, quantities,
entry/exit prices and reported trade P&L, with zero price/time/money tolerance.
Both sides total **165005 CU** under the zero-cost comparison. All 1,415,817
selected IS bars were replayed; the final position is flat.

Real product report in the existing library:

- Backtest: `1ae741ad99bd4ac5a0e1caf09595f93f`.
- URL: `http://127.0.0.1:8000/#backtests/report/1ae741ad99bd4ac5a0e1caf09595f93f`.
- Existing normal automatic Apex/Lucid report IDs:
  `7d21a46240c84005a829dc8b9e266964` and
  `327fcf893b10440ca82024812c697409`.
- `artifacts/twin-mc-early-close-parity-20261109/alphaquest-report` is a shortcut
  to that canonical normal backtest directory, not a second result store.
- `qualified-comparison/{verification.json,all-is-trades.csv,early-close-trades.csv}`
  seals the workbook/source/code identities, complete membership, exact values,
  timezone mapping, cost limitations and the three early-close matches.
- The analytical fixture oracle lives only in
  `tests/fixtures/twin_continuation/mc_early_close_reference.json`.

Exact reproduction with the existing saved source, matching the reference's
reported price-change arithmetic (choose a new output shortcut):

```sh
.venv/bin/python -m alphaquest.run_backtest \
  --database data/datasets.sqlite3 \
  --dataset-id 094287965d4444f69cb7eefe0d2f054c \
  --output artifacts/twin-mc-repeat-NEW \
  --strategy-id twin_continuation \
  --initial-capital 10000 --slippage-ticks 0 \
  --commission-per-contract-per-side 0 \
  --is-start 2021-01-01 --is-end 2024-12-31 \
  --oos-start 2025-01-01 --oos-end 2026-07-07

.venv/bin/python tests/review_twin_mc_reference.py \
  --reference artifacts/twin-mc-early-close-parity-20261109/mc-reference.xlsx \
  --report artifacts/twin-mc-repeat-NEW \
  --output artifacts/twin-mc-comparison-NEW
```

Expected: 499 trades, 343 winners / 156 losers, 165005 gross/net with these zero
costs, and all 499 qualification rows marked exact. Default source Inputs plus
`max_bars_back=5` and `use_session_calendar=true` apply. The starting capital is
an explicit AlphaQuest comparison setting, not recovered MC Settings. In the
portal select the saved NQ dataset and Twin, leave each parameter start=end,
review the saved IS/OOS dates, keep Use session calendar on, and enter these
costs. Before Run, the existing calendar panel identifies the CSV and same-Close
policy. In the report, inspect **Dataset, strategy & settings used**: mode
`twin_csv_session_close_v2`, calendar SHA-256, zero-minute buffer, 1034 observed
sessions / 36 shortened sessions. Download ordinary trade/equity/risk CSVs and
report JSON; inspect the three rows above. Reopening reads the saved result.

Saved normal-product browser demonstration:

`artifacts/twin-calendar-product-verified-20261109/verification.json` records a
clearly labelled synthetic source, backtest `e6f805119c984d52855b68dbfcd925f8`,
one-trial grid `b54343c2ce0546d4bfa09cea25902695` with `automatic_prop=false`,
and manual local analysis `0eb7dff26b89401397ef5dad783a0563`. The journey is
Datasets → save → Backtests → Twin/calendar → declare IS/OOS → Run → ordinary
report/downloads → Configure prop analysis → Check source → Run → saved local
report/ZIP → reload unchanged. It uses existing product surfaces/stores. The
manual demonstration explicitly sets Total NQ limit 0.1 and retains source
costs; it does not alter the user's strategy or real report configuration.

Independent synthetic expectations: two MO long entries fill 112.25; the
2024-06-19 and 2024-07-04 noon closing prices fill 119.75 after one adverse tick.
Each nets `(119.75-112.25)*20-2=148`, total **296 CU**. The normal source check
reconciles two native risk records, net 296 and commission 4 with zero measured
MAE/MFE. The saved local analysis exposes no training/validation pass and no
funded estimate, rather than inventing acquisition cash. Source bytes, report
JSON and prop downloads are verified after reload. Screenshots, CSV/JSON and
analysis ZIP are retained. Earlier failed review attempts remain preserved;
the verified directory above is the completed demonstration.

```sh
.venv/bin/python tests/review_twin_calendar.py --output artifacts/twin-calendar-NEW
```

Its temporary server stops automatically. To inspect this isolated synthetic
library later, optionally start
`ALPHAQUEST_DATA_DIR="$PWD/artifacts/twin-calendar-product-verified-20261109" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8001`
and open its recorded report paths; stop with Ctrl-C. No persistent server was
started for this work; the user's existing server remains available.

Validation: **198 targeted tests passed**, covering the new MC-based oracles,
source admission/coverage, missing/truncated early closes, bracket priority,
source costs once, outward target ticks, fixed-clock compatibility, existing
execution/VWAP/API/reuse and phase identity. The existing compiled C# core
comparison also passed 18,556 bars with 15 state fields/effective orders
(`artifacts/twin-csharp-calendar-20261109/verification.json`). Numerical parity
here is for the supplied historical IS trade fields under stated settings;
other Inputs, capped fractional stops, live fills, actual MC cost settings,
provider certification and later OOS remain outside this qualification.

## 2026-11-10 — Main navigation workflow preview

This increment on `epic/revamp-workflow` changes the existing main page to four
navigation destinations, in order: **Dataset, Research, Campaigns, Prop Sim**.
The Dataset screen markup is unchanged. Research now contains only a thesis and
summary placeholder. The former research catalogue is detached from the main
Research tab; existing `#backtests/research` bookmarks and report links remain
available under Prop Sim, alongside prop draft helpers and saved backend records.

Campaigns contains two hardcoded examples, **ORB + VWAP pullback** and **Twin
continuation**, each mapped to one strategy code. Selecting a campaign shows its
hypothesis, linked-research placeholder, shared entry/stop/target logic, broad
and narrow parameters, source file path, and example ES/NQ periods and stages.
These are labeled illustrative, not inferred from saved runs. **Saved runs** and
**New backtest** retain access to the existing product routes.

Prop Sim is a requested presentation placeholder in the main page, not a new
calculation path or report store. It shows APEX 50K EOD, a checkbox dropdown with
four example parameter sets, separate Evaluation and Funded sizing sections,
an evaluation-profile selector, and a three-year cash table. Risk examples are
$0/$200/$300/$50; no optimality or numerical parity is claimed. Annual costs,
trader receipts and net remain `—`, because no source check or calculation ran.
Existing backtest → configure → check → run → durable report paths and all
calculation owners are unchanged. This prompt does not implement simulation or
change source, account, selection or settlement behavior.

Reproduce from this checkout:

```sh
.venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8017
```

1. Open `http://127.0.0.1:8017/`. Expect the four navigation buttons in the
   specified order. Dataset upload, validation and library remain as before.
2. Select **Research**. Expect “No research theses yet”, without WFA controls or
   a saved campaign/study catalogue. `/#research` opens this empty thesis screen;
   older `/#backtests/research` bookmarks still open saved studies under Prop Sim.
3. Select **Campaigns**, then **Twin continuation**. Expect Twin-specific logic,
   `twin_continuation.py` under **Source code**, and two illustrative datasets
   dated 2021-01-01 → 2024-12-31. ES shows “Mechanic validation”; NQ shows
   “IS broad · 1 pass”. Reload preserves the chosen campaign URL. Browser Back
   restores ORB; `/#campaigns/missing` shows “Campaign not found”.
4. Select **Prop Sim**. Expect four example inputs and separate sizing lists.
   Select the first Twin Evaluation choice: the example profile reads **$300**.
   Open **Choose strategy inputs**, uncheck every choice: both lists show the
   empty state and the prior evaluation selection clears. Recheck one choice:
   both lists contain just that choice. The three-year table always contains
   nine `—` cells, with no fabricated cash outcomes. **+ Add inputs** reopens the
   dropdown. These interactions send no mutation requests.
5. At a 390px viewport, expect all four buttons in the top navigation, stacked
   campaign/sizing sections, and no horizontal page overflow. From Campaigns,
   **Saved runs** opens the retained browser and **New backtest** opens setup.
6. Stop the optional manual server with **Ctrl-C**.

Automated reproduction (use a fresh output directory to retain earlier evidence):

```sh
mkdir -p artifacts/workflow-nav-REVIEW
.venv/bin/python -m pytest -q tests/test_workflow_navigation_browser.py \
  --basetemp=artifacts/workflow-nav-REVIEW/browser
```

Saved browser evidence: `artifacts/workflow-nav-20261110/evidence/`
contains desktop Research/Campaigns/Prop Sim screenshots, mobile Campaigns/Prop
Sim screenshots, and `navigation.json`. Tests use an isolated synthetic library
and stop their temporary servers. No persistent server is started by this work.
The screenshots and JSON document UI behavior, not simulated performance.
Earlier dated numerical findings and evidence remain unchanged. Existing saved-run
browser journeys now enter via Campaigns → Saved runs.
The old saved-study route is retained separately from the new thesis tab.

Validation: **52 affected browser checks passed** (51 in the affected-module run,
plus the saved-run navigation/reload check), including
Dataset upload/edit/download/delete, backtest input persistence, report reopening,
automatic prop reports, optimization results, compact-report → prop-analysis
execution/downloads, and the retained saved-study catalogue. JavaScript syntax,
unchanged Dataset markup and `git diff --check` also passed. The verification
manifest and screenshot checksums are saved in `evidence/verification.json`.
This is targeted UI/workflow verification, not a full-suite or provider-parity claim.

## 2026-11-10 — Real campaign datasets and mechanic validation (workflow revamp 2)

This increment on `epic/revamp-workflow` replaces the preceding revision's
illustrative campaign datasets/stages with saved workspace sources and durable
workflow state. The campaign list now includes every registered or archived
strategy code. The two narrative descriptions remain illustrative; all displayed
dataset periods, saved results and mechanic-validation status are real. Prop Sim
remains the previously labeled placeholder and no prop calculation was changed.

The four research phases are **Mechanic validation → IS Broad → IS Narrow →
OOS**. This increment implements mechanic validation and ordered navigation.
IS Broad becomes navigable only after the saved mechanic review passes; its
screen states that execution is not implemented. IS Narrow and OOS stay locked.
No endpoint in this increment can mark those later phases passed. Existing
backtests and independent Evaluation/Funded reports remain available through
their original routes; these research phases do not replace those account-phase
optimizers.

The normal product journey is Campaigns → New backtest → existing backtest setup
with a saved dataset or **Upload a new dataset** → ordinary Dataset validation
and save → **Continue to backtest** → declare IS/OOS and costs → **Open mechanic
validation** → **Run validation · default parameters** → ordinary local backtest
report plus mechanic review. Configuration does not run a backtest. The initial
mechanic page has one run action, with saved settings in a collapsed disclosure.
It runs the declared IS range with the current strategy's defaults, using the
user's saved instrument/cost settings. It never reads OOS prices for this run.
Unsupported default strategy/source combinations reject instead of changing the
parameters. Automatic prop reports are omitted for this validation-only run.

Every outcome row comes from the real saved summary. Trade samples are selected
from actual completed trades: first, last, greatest positive **net** P&L, most
negative net P&L, and shortest elapsed holding duration. All rankings use exact
decimals; ties use the earliest trade number. Overlap produces one row containing
all selection reasons, so there are at most five rows. A run without wins or
losses explicitly discloses the missing category. No trade is fabricated.

Every metric needs an MC-parity check. Every sampled trade needs both MC-parity
and execution-correctness checks. Each click saves an optimistic review revision;
reload resumes it. Confirmation requires all the exact server-defined rows,
matching saved results, and at least one closed trade. A zero-trade run remains
inspectable and cannot pass mechanics. Final confirmation is a durable **user
attestation**, not an automatic/independently measured MultiCharts comparison.
Confirmed reviews are immutable. Saved workflow JSON, report JSON and trades
CSV are downloadable through the normal product routes.

The API enforces ordered phase admission, incomplete/stale review rejection,
strict boolean checks, source/code/instrument binding, and idempotent run
submission. A lost response reopens the saved run; interrupted requests can be
retried without overwriting an earlier report. RunStore retains referenced
validation reports, including deletion through an activity. Reviewed report or
trade changes fail closed. Opening a mechanic report in the ordinary report UI
cannot bypass the campaign gate through its old manual OOS action. Workflow
metadata/reviews use tables in the existing backtest catalogue; numerical
results remain in RunStore, with no new engine, service, database or result store.
Existing conservative engine identity includes this production code change;
earlier reports and qualification evidence remain unchanged.

### Reproduce the saved synthetic demonstration

Evidence/downloads are in `artifacts/campaign-mechanics-20261110/evidence/`:
ready/unreviewed/confirmed/mobile screenshots, `SYNTHETIC-mechanics.csv`, the
ordinary `report.json`, `trades.csv`, `mechanic-review.json`, and `journey.json`.
The browser exercised confirmations on synthetic rows to test the workflow;
this evidence does **not** establish measured MultiCharts parity. The independent
expected values are analytical test oracles in `tests/test_campaign_mechanics.py`,
not product fixtures or a separate test dashboard.

Start this checkout:

```sh
.venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8017
```

1. Open `http://127.0.0.1:8017/#campaigns/consecutive_green_hold`. Choose **New
   backtest**, then **Upload a new dataset**. Upload the saved
   `SYNTHETIC-mechanics.csv` with name **SYNTHETIC mechanics review**, source
   timezone **UTC**, symbol **SYNTHETIC**, tick size **0.25**, point value **10**.
   Validate/save using the ordinary Dataset page. The source has **25 rows**.
2. Select **Continue to backtest**. Expect the new dataset selected and the
   parameter grid hidden. Set initial capital **10000**, slippage **1 tick per
   fill**, commission **1 per contract per side**. Use explicit dates: IS
   **2026-01-05 → 2026-01-05**, OOS **2026-01-06 → 2026-01-06**. Review the split,
   then choose **Open mechanic validation**. Expect no results yet and three
   locked later phases. Saved defaults must be `green_bar_count=3`,
   `hold_minutes=20`, `contracts=1`.
3. Choose **Run validation · default parameters**. Expect **6** completed trades
   from **24 IS rows**, initial equity **10000**, final equity **10078**, gross
   after slippage **90**, commissions **12**, net **78**, slippage cost **30**,
   and maximum drawdown **37**. Each entry fills **100.25**. The six net P&Ls
   are **3, 43, -37, 13, 23, 33**. These come from entry reference price 100,
   exit reference prices 101/105/97/102/103/104, point value 10, a 0.25 adverse
   price adjustment at each fill, and 2 commission per round trip. No costs are
   deducted twice. The reserved 900-price OOS bar does not enter these outcomes.
4. Expect sample rows **1, 6, 2, 3, 4**, respectively first/last/biggest win/
   biggest loss/shortest duration. Holding durations in trade order are
   **21, 24, 25, 20, 23, 22 minutes**. Open **All recorded execution fields** to
   inspect exact source bar numbers, reference/fill prices, costs and reasons.
5. Before real confirmation, compare the same data, timezone, parameters, dates,
   execution assumptions and costs in MultiCharts and check trade execution.
   Tick one metric and reload: that check remains saved. Leave any metric or
   either trade check unticked: confirmation stays disabled and a direct confirm
   API request returns **409**. When legitimately reviewed, check every row and
   confirm. Expect a user-attested pass timestamp and **IS Broad ready**.
6. Open **IS Broad**: expect a navigation-only placeholder, with no run action.
   IS Narrow/OOS remain locked. A forged workflow `/oos` hash or phase API call
   returns the previous-phases rejection. The ordinary mechanic report also
   hides manual OOS and its OOS POST returns **409**, including after mechanics
   is confirmed. No OOS attempt is recorded.
7. Return to Campaigns and click the real saved dataset or **Inspect validation
   results**. Expect the same run and checks, with no new backtest. An existing
   historical dataset without a workflow opens setup; **Inspect saved results**
   opens its original report browser. New validation does not inherit a historical
   report's arbitrary parameters or treat its existence as a passed phase.
8. Download **Saved review JSON**, **Trades CSV**, or open the ordinary backtest
   report. At 390px, phase navigation is arranged in two columns; the tables
   scroll horizontally to reveal all values and checkboxes without page overflow.
   Stop the optional manual server with **Ctrl-C**.

For a clean automated reproduction, keep the earlier artifacts and use a fresh
output directory:

```sh
mkdir -p artifacts/campaign-mechanics-REVIEW
.venv/bin/python -m pytest -q tests/test_campaign_mechanics.py
.venv/bin/python -m pytest -q tests/test_campaign_mechanics_browser.py \
  --basetemp=artifacts/campaign-mechanics-REVIEW/browser
```

These browser tests use isolated normal dataset/backtest libraries and stop
their temporary servers. No persistent server was started for this increment.

Validation: **143 distinct backend checks passed**, covering native backtests,
splits/OOS isolation, both deletion paths, instrument settings, phase-owner
compatibility and the new mechanics contracts. The first run passed 141 checks;
two multiprocessing cases hit sandbox socket denials, then both passed outside
the sandbox. **37 product/browser checks passed** across the new journey, main
navigation, existing backtests, instrument/date settings, deletion and saved
strategy datasets. The final two mechanics journeys were repeated to save the
one-trade overlap demonstration: default one-contract arithmetic run nets **13**
and has one sample row with first/last/biggest-win/shortest-duration reasons, with
no fabricated biggest loss. `05-overlap.png` and `overlap-review.json` retain it.
JavaScript syntax and `git diff --check` passed. Exact source/download hashes and
run scopes are recorded in `evidence/verification.json`. This is targeted
workflow qualification, not a full-suite or MultiCharts/provider parity claim.

The saved synthetic library can also be reopened without resimulation:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/campaign-mechanics-20261110/demonstration/test_upload_default_run_review0" \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8017
```

Open the `workflow_hash_route` in `evidence/journey.json`, or navigate to
Campaigns → Consecutive Green Hold → SYNTHETIC mechanics product review. Expect
one saved validation run, its synthetic user-attested checks and IS Broad ready.
Stop this optional inspection server with **Ctrl-C**. The portable source CSV
and exported review/report allow reproducing the journey if the ignored test
library is unavailable in another checkout.

## 2026-11-10 — Running/completed job history (workflow revamp 3)

**Job history** is now available in the top bar at `/#jobs`. The four primary
navigation buttons remain Dataset, Research, Campaigns and Prop Sim. History
combines mechanic-validation attempts, existing backtest batches, saved standalone
backtests and prop-analysis jobs from their existing catalogues. It supports
running/queued, completed, failed/stopped and type filters; strategy/dataset/job-ID
search; 25-row paging; refresh; and automatic updates. Click a recorded timestamp
or View action to open `/#jobs/{kind}/{id}`. The detail view links directly to the
normal mechanic review, backtest report, batch progress/results or prop report.

UI-started mechanic validation now submits a server-owned background task and
returns HTTP **202**. Leaving the initiating page, navigating to Job history or
reloading the browser does not cancel it. The original synchronous API remains
available for existing callers. Native execution still uses the existing local
backtest function and ordinary RunStore publication. No new calculation engine,
service, database or numerical result store was added. Each mechanic attempt
stores only job metadata in the existing backtest catalogue; a failed attempt
remains visible after a successful retry. Progress comes from the existing
server tracker, with completed bar counts reconciled to the saved report.
Unknown totals do not produce a percentage. Batches show completed/total trials;
prop analyses show their recorded progress text. Completed standalone backtests
appear once saved; their older in-flight HTTP executions are not registered as
background jobs. Batch trial reports and mechanic reports are not listed twice
as standalone jobs.

**Completed** means that execution produced its result. It does not mean that
MC parity or execution correctness was reviewed, nor does it unlock IS Broad.
The existing row checks, immutable user confirmation and ordered phase gates
remain in force. History polling does not load numerical report files or rerun
calculations. Earlier reports, source inputs and saved review evidence stay
unchanged. Earlier mechanic runs are backfilled from recorded metadata; unknown
start/finish times display **Not recorded**. A server/process interruption is
recorded as interrupted rather than silently rerunning the calculation. Graceful
shutdown waits for owned background validations. The older batch/prop result
and recovery behavior remains with its existing owner.

### Product demonstration and expected observations

Saved outputs are in `artifacts/job-history-20261110/evidence/`: running history
and detail screenshots, completed history/detail and mobile screenshots,
`running-jobs.json`, `completed-job.json`, `completed-jobs.json`, ordinary
`workflow.json`, the downloaded `SYNTHETIC-source.csv`, and `journey.json`.
The browser test pauses before the real native replay solely to make navigation
and reload during execution reproducible; it does not fabricate measured
progress or trade outcomes. The visible preparing/zero-known-bars snapshot is
real tracker state before replay. The later 24 bars and 78 net come from the
ordinary saved native report.

```sh
.venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8017
```

1. Open the normal Campaigns → New backtest workflow. For the synthetic check,
   upload `evidence/SYNTHETIC-source.csv` through Dataset validation/save with
   timezone UTC, tick size 0.25 and point value 10. Choose Consecutive Green Hold,
   initial capital 10000, slippage 1 tick/fill and commission 1/contract/side.
   Set IS to 2026-01-05 and OOS to 2026-01-06; open mechanic validation. Configuration
   alone does not appear as an executed job in history.
2. Click Run validation and immediately choose **Job history** in the top bar.
   While running, expect the mechanic job and its actual stage/counts. On this
   tiny source the job may finish before a manual click; larger real sources
   naturally remain active longer. Do not expect artificial delays in production.
3. Click the job and reload during execution. Expect it to continue and update
   to Completed, **24 / 24 bars**. Open mechanic validation: expect the real
   **6 trades**, net **78**, and the five deduplicated sample rows described in
   revision 2. Confirm remains disabled until the user reviews the rows. Merely
   opening a completed job must not mark any check or phase as passed.
4. Choose Completed, then the Mechanic validation type filter, or search using
   the job ID. Expect one matching job. An unmatched search shows an empty state.
   A missing job ID returns 404; unsupported status/type filters return 422.
5. Existing batch jobs appear in the same list. The saved demonstration also
   executes a two-trial native batch (1 and 2 contracts, automatic prop disabled).
   Expect **2** history jobs total—one mechanic attempt and one batch—with **3**
   underlying backtest reports. Click the batch, then Open batch progress/results
   to reach its original results screen. The trial reports are not duplicate
   history rows. Expected trial net P&Ls for this synthetic source are 78 and 156.
6. On mobile, the top-bar shortcut remains accessible and the history table
   scrolls horizontally without widening the page. Stop the optional inspection
   server with Ctrl-C. Test servers stop through fixture teardown; this work
   starts no persistent server.

Focused reproduction:

```sh
.venv/bin/python -m pytest -q
mkdir -p artifacts/job-history-REVIEW
.venv/bin/python -m pytest -q tests/test_job_history_browser.py \
  --basetemp=artifacts/job-history-REVIEW/browser
```

Validation: **9 fast default checks passed in 5.10 seconds** (six mechanics,
three history contracts), and **2 affected browser journeys passed in 12.27
seconds** (new history/navigation/reload/result path and the existing full
mechanics review journey). Covered boundaries include retry retention, old-run
backfill without invented start times, interruption, exact paging/filtering,
missing IDs, source-report immutability and deduplication across catalogues.
JavaScript syntax and `git diff --check` passed. No broad legacy suite was run.
The manifest records exact scope and source/export hashes; this is workflow
qualification, not MultiCharts/provider or full-repository certification.

A fresh application lifespan also reopened the demonstration catalogues with
**2 completed jobs** and actual batch net P&Ls **78 / 156**, with byte-identical
saved backtest artifacts. `batch-results.json` and `reopened-history.json` retain
those ordinary API outputs. To inspect that saved normal-product library:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/job-history-20261110/product-verified/test_running_job_survives_navi0" \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8017
```

Open `http://127.0.0.1:8017/#jobs`; stop this optional inspection server with
Ctrl-C. The portable CSV and saved JSON exports also support reproduction when
this ignored test library is unavailable in another checkout.

## 2026-11-10 — Shorter mechanic outcome parity checklist

Mechanic validation now omits **Initial capital, Final equity, Ending position
contracts, Max drawdown pct, and Max drawdown duration seconds** from its outcome
parity table and required checks. The current report has **10** remaining outcome
rows. Underlying backtest summaries, numerical results, trade samples, report
files and earlier saved evidence retain those values. No backtest rerun is
needed to reopen an already completed mechanic validation with the shorter table.

For an existing incomplete review, reload the workflow. Retained checked rows
stay checked; the five removed rows are no longer confirmation requirements.
Reads do not rewrite stored review evidence. The next explicit save/confirmation
uses the reduced checklist. Confirmed historical reviews keep their original
stored attestations and remain read-only; their visible outcome table uses the
shorter list. Every remaining metric and each sampled trade's MC parity and
execution correctness still requires confirmation before IS Broad unlocks.

Reproduce through the existing Campaigns → dataset → mechanic validation flow,
or reopen one of its completed jobs through Job history. Expect the five named
rows to be absent and 10 outcome rows on the saved synthetic example. Open the
ordinary backtest report or download the review JSON: its nested report summary
still contains all five values. The synthetic example remains **6 trades**, net
**78**, maximum drawdown **37**, and five sampled trades. No measured MultiCharts
parity is claimed by the automated checkbox exercise.

Saved evidence: `artifacts/mechanics-parity-metrics-20261110/evidence/` contains
the updated unreviewed screenshot, ordinary report JSON and saved review JSON.
Earlier screenshots and immutable reports remain unchanged.

Focused validation: **one backend contract passed in 1.54s**, including legacy
pending/confirmed review handling and report-file preservation; **one existing
product browser journey passed in 6.95s**, including upload, real default replay,
10-row checklist, confirmation, reload and phase gates. `git diff --check` passed.
Temporary test servers stopped; no persistent server was started. To reproduce:

```sh
.venv/bin/python -m pytest -q tests/test_campaign_mechanics.py::test_default_run_exact_samples_review_gate_and_durable_reopen
mkdir -p artifacts/mechanics-parity-metrics-REVIEW
.venv/bin/python -m pytest -q tests/test_campaign_mechanics_browser.py::test_upload_default_run_review_resume_and_phase_lock \
  --basetemp=artifacts/mechanics-parity-metrics-REVIEW/browser
```

## 2026-11-10 — Remove Campaigns validation-results shortcut

Removed the **Inspect validation results** link from completed workflow cards on
Campaigns. Dataset-name navigation and unfinished **Resume backtest** links
remain available. Job history and saved review/report routes remain available.
To verify, open Campaigns → a campaign with a completed validation: expect its
dataset name and stage, without the removed shortcut. The dataset name still
opens the normal workflow. Saved screenshot:
`artifacts/campaign-link-removal-20261110/evidence/campaign-navigation.png`.
The one affected browser journey passed in **6.92s**; JavaScript syntax and
`git diff --check` passed. Its temporary server stopped after the check.

## 2026-11-10 — Sequential phase navigation

The four phases now use numbered **01 → 02 → 03 → 04** chevrons to make their
order explicit. The current phase is filled teal; passed phases show a checkmark;
locked phases use subdued styling and remain disabled. The helper text reads
“Complete each phase to unlock the next.” Desktop uses a left-to-right sequence;
mobile uses downward-pointing segments in one column, preserving the same order.
Buttons expose their step number, phase and state to assistive technology.

To inspect, open a campaign dataset's mechanic page. Expect step 01 current and
02–04 locked. After the normal row-by-row review and confirmation, expect 01
passed and 02 ready. Open IS Broad: step 02 becomes current, with 03/04 still
locked. At 390px, expect steps 01–04 stacked vertically without page overflow.
Earlier saved reports and review evidence remain intact.

Screenshots: `artifacts/phase-chevron-nav-20261110/evidence/phase-sequence.png`,
`01-ready.png` and `04-mobile.png`. The one affected normal-product browser
journey passed in **8.32s**, including phase ordering, disabled-state enforcement,
confirmation and mobile layout. JavaScript syntax and `git diff --check` passed.
Its temporary server stopped; no persistent server was started. Refresh the app
page to load the updated frontend assets.

## 2026-11-10 — IS Broad optimization and locked configuration selection

IS Broad now executes the existing native exhaustive optimizer from the campaign
workflow after the mechanic review has passed. It uses the workflow's saved
source, IS dates, strategy and execution costs. The parameter grid supports
start/end/step, server-validated iteration counts and bounded worker selection.
Jobs run in the existing background executor and remain accessible through Job
history after navigation or reload. Automatic legacy prop reports are disabled
for these grid requests; this increment selects strategy configurations only.
No production prop calculation, phase optimizer objective or numerical engine
was changed.

The results table shows every strategy parameter and the ordinary backtest
metrics, with the existing independent show/hide, freeze and reorder controls,
sorting, paging, report links and full results CSV. Column preferences persist
in this browser and never change calculated results. The current admission rule
is **strictly positive IS total net P&L after slippage and commissions**. Losing
and zero-profit rows are dark and their selection checkboxes are disabled.
Choose **one or two** eligible, distinct configurations. Checkbox changes save a
revisioned draft; **Confirm configs and continue to IS Narrow** permanently
locks the selection. IS Narrow shows those exact saved parameter sets and source
reports. Its execution is a later increment; OOS stays locked.

The server independently enforces phase order, grid completion, membership,
profitability, the two-choice limit and matching source/strategy/cost/IS identity.
Confirmation freezes selected report/artifact hashes. A modified or missing
selected artifact blocks carry-forward/download. Stale drafts and code changes
between preview/run or grid/confirmation reject. After confirmation, selections
cannot be replaced, unchecked or rerun. Before confirmation, a different grid
may replace a completed/failed grid; old jobs and reports remain in history.
Duplicate submissions reuse the existing job. Campaign grid jobs and their
candidate reports are retained against deletion. State and references live in
the existing backtest database; trial results and files use their normal store.

Saved demonstration: `artifacts/is-broad-20261110/evidence/` contains desktop
grid/results/IS Narrow screenshots, mobile navigation, actual results JSON/CSV,
the downloaded frozen package, the synthetic source CSV, both selected native
report directories and a SHA-256 manifest. The legacy table control check also
retains its screenshot and immutability observations. Earlier evidence remains
unchanged. This is a synthetic workflow/selection qualification: checking the
synthetic MC attestations does **not** establish measured MultiCharts parity.

To reproduce through the actual product:

1. Restart the app after updating code. For an isolated local review library:

   ```sh
   ALPHAQUEST_DATA_DIR=/tmp/alphaquest-is-broad-review \
     .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8017
   ```

   Open `http://127.0.0.1:8017/`. Upload the saved `SYNTHETIC-source.csv` through
   Dataset, with a synthetic name/symbol, timezone UTC, tick size 0.25 and point
   value 10. Choose Campaigns → Consecutive Green Hold → New backtest. Select
   this dataset, capital 10000, slippage 1 tick per fill, commission 1 per
   contract per side; declare IS 2026-01-05 through 2026-01-05 and reserved OOS
   2026-01-06 through 2026-01-06.
2. Run mechanics at default parameters. Expect six trades and net **78**. Review
   every visible outcome and sampled trade checkbox, then confirm mechanics.
   For this labeled synthetic exercise, the checkbox action only tests the
   attestation flow; real research requires your actual MC comparison. Before
   mechanics confirmation, direct IS Broad requests return 409.
3. Open step 02, IS Broad. Set green bar count **3 → 4, step 1**, hold minutes
   **20 → 60, step 20**, and contracts **1 → 3, step 1**, with one worker. Click
   Calculate iterations: expect **18**. Run IS Broad. Expect **COMPLETE · 18 / 18**;
   OOS's reserved 900-price bar must not enter any trial. Leaving the page does
   not cancel the job. Job history has one mechanic job and one native batch,
   with links back to IS Broad; the normal backtest library contains 19 reports.
4. Independent expected arithmetic for one contract: the hold-20 quote gains
   are `[1,5,-3,2,3,4] × 10 = 120`; subtract 30 slippage and 12 commissions to
   obtain **78**. Hold 40 exits three trades at the next hour's first close,
   each `(-2 × 10) - 5 - 2 = -27`, total **-81**. Hold 60 exits three at equal
   quote prices, each `0 - 5 - 2 = -7`, total **-21**. Quantities 2 and 3 scale
   each value linearly. Green count 4 never enters and returns zero. Thus trial
   net P&Ls in trial order must be:

   ```text
   78, 156, 234, -81, -162, -243, -21, -42, -63,
   0, 0, 0, 0, 0, 0, 0, 0, 0
   ```

   Only trials **1–3** qualify; the other 15 are disabled. Net P&L already
   includes costs; the displayed cost columns are not deducted again.
5. Open Columns, hide Total gross pnl and freeze Contracts. Expect the saved
   browser layout on reload. Choose two profitable trials: other unchecked rows
   become disabled at the cap. Uncheck one before confirmation to change the
   draft. Losing/zero rows remain disabled even when a slot opens. The backend
   rejects a forced losing/zero trial, unknown trial, duplicate configuration,
   third choice, another job's ID, or stale revision. An all-zero grid cannot
   confirm or unlock IS Narrow; selecting one eligible configuration is valid.
6. Choose trials **2 and 3** and confirm. Expect IS Narrow to show contracts
   **2 / 3**, green count **3**, hold minutes **20**, with IS net **156 / 234**.
   Reload: both inputs remain. Return to IS Broad: choices remain checked and
   disabled, and rerun is disabled. Download Saved IS Broad package and Results
   CSV; expect the same IDs/parameters/profits and the recorded confirmation
   timestamp. Report files stay byte-identical after navigation/review/downloads.
   OOS stays locked. Stop this optional inspection server with Ctrl-C.

The ignored local test library can also be reopened at
`artifacts/is-broad-20261110/browser-final/test_broad_search_columns_prof0`
using the same `ALPHAQUEST_DATA_DIR` startup command. Its workflow URL is
`/#campaigns/workflows/67f26c98bb88489fbce6f33b452d0bb7/is_broad`. Portable evidence
exports remain available in another checkout without that local database.

Focused validation: **12 default backend checks passed in 18.61s**, including
three new broad contracts; **3 affected product browser journeys passed in
18.59s** (new broad flow, existing mechanics confirmation, existing column
show/freeze/reorder/sort/persistence). Backend boundaries include concurrent
duplicate launch, stale previews/revisions, source/report identity, capped and
positive-only selection, code drift, all-zero results, deletion protection,
artifact tampering, durable reopen and job-history deduplication. No 180-test or
full legacy suite was run. JavaScript syntax and `git diff --check` passed.
Temporary test servers stopped through fixture teardown; no persistent server
was started. Reproduce only these affected checks with:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -x -q tests/test_campaign_broad_browser.py \
  tests/test_campaign_mechanics_browser.py::test_upload_default_run_review_resume_and_phase_lock \
  tests/test_optimization_layout_browser.py::test_select_columns_reorder_both_groups_sort_and_persist \
  --basetemp=artifacts/is-broad-REVIEW/browser
```

## 2026-11-10 — Six-criterion IS Broad gate and visible stage policies

This increment replaces the profitability-only rule **for new IS Broad grids**
with the six approved requirements in `docs/workflow_screening.md`. That document
also preserves the agreed IS Narrow requirements for later implementation.
Every workflow page now exposes **Passing criteria by stage**: mechanics and
Broad are implemented; Narrow's additional tests and OOS execution are visibly
pending. Expanding a future stage's rules does not execute it or unlock it.

Each Broad configuration now runs twice through the existing native strategy
and execution engine: normal costs and **one additional tick of slippage per
fill**. Native stress reports use the existing backtest catalogue and files;
the batch remains one history job, with each candidate linking its base and
stress reports. The result CSV includes the new screening metrics. Each result
also links a checked `is_screening.json` download containing the six measured
verdicts, complete-month P&L, observed coverage, policy and stress provenance.

The new streaming measurement observes every engine bar-close equity point,
including unrealized P&L. Earlier trade-close summary metrics and old files are
preserved. Policy snapshots bind the job, run and manual selection. The server
requires all six checks and sufficient evidence, rechecks native artifact
identities before confirmation/carry-forward, and blocks modified or missing
evidence. Cached results include native stress evidence and its integrity checks.
Both base and stress reports are retained against campaign deletion. No external
engine, provider oracle or future IS Narrow calculation is invoked.

Earlier **confirmed** profitability-only choices retain their original identities
and display a historical-rule notice; they are not certified against the new
six-test policy. Older **unconfirmed** grids display a rerun requirement and
cannot select configurations until a new grid records the six tests. Saved old
reports, screenshots, exports and reviews remain unchanged.

Actual product evidence is saved in
`artifacts/is-screening-20261110/evidence/`: stage/grid/results/Narrow/mobile
screenshots, insufficient-history and cost-stress rejection screenshots, normal
results JSON/CSV, frozen package, native screening measurements, labeled source
CSVs, both selected native baseline/stress report pairs, their shared comparison
artifacts, focused check logs and a SHA-256 manifest. `report-directories.json`
maps chosen trials to the original native run IDs. This is synthetic workflow
qualification; MC checkbox exercise is not measured MultiCharts/provider parity.

### Reproduce the passing grid

1. Restart with the new code. For an isolated inspection library:

   ```sh
   ALPHAQUEST_DATA_DIR=/tmp/alphaquest-six-criteria-review \
     .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8017
   ```

   Open `http://127.0.0.1:8017/`. Upload the saved `SYNTHETIC-source.csv`, using
   a synthetic name/symbol, UTC timezone, tick size **0.25**, point value **10**.
   Through Campaigns → Consecutive Green Hold → New backtest, select that source,
   initial capital **10000**, slippage **1 tick per fill**, commission **1 per
   contract per side**, IS **2024-01-01 → 2025-12-31**, and reserved OOS
   **2026-01-01 → 2026-01-01**. The reserved bar's 900 price must not enter any
   base/stress result or screening measurement.
2. Run default mechanics and perform the required review/confirmation. The
   synthetic source has **144 trades and 1872 net profit**. Open IS Broad. Expect
   all six rules visible, including the 24-month/100-trade floor and cost stress.
   Expand IS Narrow's rule summary even while it is locked: expect inherited
   Broad tests, 70% profitable neighbors, three of four profitable time blocks
   including the last, positive profit excluding the best month, and a
   dependence/search-adjusted 95% lower daily-profit bound. Its status explicitly
   says not implemented.
3. Set green count **3 → 4, step 1**, hold minutes **20 → 60, step 20**, contracts
   **1 → 3, step 1**, workers **1**. Calculate: expect **18 configurations**. The
   portal explains that each runs at normal and extra-slippage costs. Run and
   wait for **COMPLETE · 18 / 18**. Navigation/reload does not cancel execution;
   Job history links back to Broad. Expect **37 native reports** (mechanics plus
   18 base and 18 stress runs) and **2 history jobs**, without duplicate stress
   jobs.
4. Independent arithmetic: the source repeats the six-trade pattern from the
   earlier mechanic fixture each month for 24 months. Each month's quote gains
   sum to **120** per contract. Normal fills subtract **30** slippage and **12**
   commissions: **78/month × 24 = 1872**. An extra tick per fill costs another
   **30/month**, leaving **48/month × 24 = 1152** in the actual stress rerun.
   Two and three contracts scale those exact source results. Thus the native
   base net profits in trial order are:

   ```text
   1872, 3744, 5616, -1944, -3888, -5832, -504, -1008, -1512,
   0, 0, 0, 0, 0, 0, 0, 0, 0
   ```

   Only trials **1–3** pass all six criteria. For trial 1, expect **24 months**,
   **144 closed trades**, **24/24 profitable full months**, annual net profit
   approximately **935.3406** over 731 days, and maximum **MTM drawdown 40.50**.
   The legacy closed-trade drawdown remains **37**. The MTM low includes the
   fourth trade's **3.50** entry cost/unrealized loss while still recovering
   from the third trade's **37** loss. Longest MTM drawdown is **12180 seconds**
   (11:01 → 14:24 on a pattern day), approximately **0.019285%** of IS. The
   annual-profit/drawdown ratio is approximately **23.0948**.
5. Open trial 1's eligibility details: expect six PASS rows and actual values.
   Open its Cost-stress report: expect **144 trades, 1152 net profit**, with
   slippage set to **2 ticks**. Download Screening measurements: expect those
   values, complete monthly marks and the saved policy version `is-broad-v2`.
   Losing/zero and insufficient-trade configurations remain dark and disabled.
   Show/hide/freeze columns, then reload: layout preferences and results remain.
6. Choose trials **2 and 3**, then confirm. IS Narrow displays the exact locked
   parameters and **3744 / 5616** base profits; its criteria are visible but its
   search is not implemented. Reload or reopen through Job history: choices
   stay locked. OOS stays disabled. Downloads and review do not modify saved
   native result files. Stop the optional server with Ctrl-C.

### Reproduce the rejection cases

- **Insufficient history:** upload `short-SYNTHETIC-source.csv`, using the same
  instrument/cost settings, IS **2026-01-05**, OOS **2026-01-06**. After mechanics
  review, run Broad at fixed defaults. Its **6 trades / +78 net** must show
  **Insufficient evidence**, with history/trade and complete-month failures.
  It cannot be selected or unlock Narrow despite positive profit.
- **Cost fragility:** upload `cost-stress-SYNTHETIC-source.csv` and use the same
  2024–2025 split/settings as the passing source. Run fixed defaults. Only the
  final exit quote of each month's pattern changes from 104 to 99. This reduces
  normal monthly net by **50**, giving **28 × 24 = 672**, and stressed net to
  **−2 × 24 = −48**. Expect **Not qualified · 5 / 6 passed**, with cost stress
  failing and the other five passing. Selection and confirmation stay disabled;
  direct API selection also returns 409.
- **Strict boundaries:** the contract checks cover exactly 24 months/100 trades
  passing the evidence floor; 23 months/99 trades failing; profit or stress net
  equal to zero failing; annual profit equal to DD failing; exactly 50%
  profitable months failing; and drawdown duration exactly 25% failing. Partial
  months, zero-observation months, source-timezone month boundaries, DST,
  unresolved DD and padded declarations have independent numerical cases.
- **Integrity and history:** changing a stress trade file blocks selection and
  the screening download; changing a frozen base artifact blocks carry-forward.
  Valid cached base/stress pairs reuse together without extra native reports.
  Existing confirmed legacy choices reopen with their original rule and hashes;
  incomplete old grids cannot pass the new gate without rerunning.

Focused verification: **17 default backend checks passed in 35.56s**, **3 focused
legacy reporting checks passed in 1.86s**, and **3 affected browser journeys
passed in 28.91s**. The legacy cases prove historical trade-close summaries,
open-equity reconciliation and compact outputs retain their contracts. The
browser cases cover the passing grid, both explained rejections and existing
mechanics review. One additional targeted replay check passed in **7.50s** after
verifying that a normal full-detail replay can reuse the original candidate's
bound native stress evidence and download its screening measurements. Original
selection identity and source files remain unchanged. JavaScript syntax and source whitespace checks passed; raw
downloaded CSV evidence retains native CRLF bytes. No full/180-test suite was
run. Temporary browser servers stopped via fixture teardown; no persistent
server was started.

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q \
  tests/test_reporting.py::test_exact_sums_and_final_equity_reconcile_and_open_position_marks_are_preserved \
  tests/test_reporting.py::test_compact_retains_exact_metrics_and_csvs_without_creating_arrays \
  tests/test_drawdown.py::test_reporter_uses_closed_equity_after_costs_and_ignores_open_position_dips
mkdir -p artifacts/is-screening-REVIEW
.venv/bin/python -m pytest -x -q tests/test_campaign_broad_browser.py \
  tests/test_campaign_mechanics_browser.py::test_upload_default_run_review_resume_and_phase_lock \
  --basetemp=artifacts/is-screening-REVIEW/browser
```

The ignored saved normal-product library is
`artifacts/is-screening-20261110/browser-final/test_broad_search_columns_prof0`.
Set `ALPHAQUEST_DATA_DIR` to that directory to reopen the saved workflow
`/#campaigns/workflows/5699ee9da8344ff7ab0a28cfb722538c/is_broad` without recomputing.
Portable exports and report artifacts remain available when that local test
database is absent in another checkout.

## 2026-11-10 — One campaign results destination

Campaign IS Broad jobs now expose only **Open IS Broad** from Job history.
The duplicate **Open batch progress / results** link is removed for these jobs.
Both old `/#backtests/batches/{job_id}` and `/#optimizations/{job_id}` bookmarks
redirect to the corresponding campaign run at
`/#campaigns/workflows/{workflow_id}/is_broad?job={job_id}`. Generic batch-history
entries also link to that canonical view. The underlying optimizer, result/export
APIs, calculations, source files and report storage are unchanged.

IS Broad now includes the useful execution information from the generic view:
elapsed time, worker count, reuse count, active-trial stage/bar progress, errors,
saved run/source/grid/cost settings, queued cancellation and failed/interrupted
run resume. Results CSV, native report links, column controls, screening evidence
and locked selection remain available. The generic batch viewer continues to
serve standalone legacy jobs, which have no campaign phase page.

Earlier runs are preserved within IS Broad. A superseded job opens with an
**Earlier IS Broad run** notice, its original parameters/results/downloads and
disabled execution/selection controls. **Open current IS Broad** returns to the
active run. The server verifies that the requested job belongs to this workflow;
unknown or another workflow's jobs return 404. A direct selection request using
an older job ID still returns 409. Read-only archive state is projected from the
existing job catalogue; it does not create another result store or invent an
earlier confirmation.

Saved evidence is in `artifacts/single-campaign-results-20261110/evidence/`:
the job-detail screenshot with one destination, consolidated results, an earlier
run, mobile layout, native failed/resumed controls, original current/earlier
packages and result downloads, labeled synthetic source, standalone-viewer
verification, scoped check logs and a SHA-256 manifest. Previous dated evidence
and native artifacts remain unchanged. This navigation change makes no new
MultiCharts/provider or future-performance claim.

To reproduce in the normal product:

1. Restart the app and refresh. Open Job history → a campaign's IS Broad job.
   Expect one result link, **Open IS Broad**, with no generic batch-results link.
   Open it: expect the correct run, progress/settings and normal result table.
2. Open that job's former batch URL, then its old optimization alias. Both should
   land on IS Broad with the same job ID and saved rows. Opening or redirecting
   must not run any backtests or change a confirmed selection.
3. For a workflow with an older replaced grid, open the earlier job from history
   or its old batch URL. Expect **Earlier IS Broad run**, the earlier table and
   matching downloads, all selection/run controls disabled, and a link to the
   current run. Returning to current must preserve its confirmed choices.
4. In the saved synthetic demonstration, the earlier grid contains **one** row
   with net **1872**; the current grid contains **18** rows, with chosen trials
   **2/3** retaining **3744/5616**. Exactly **3 history jobs** and **37 native
   reports** exist: one mechanic run, an earlier one-trial grid, and the later
   grid, which safely reuses that first base/stress pair. All saved native
   artifacts remain byte-identical after links, redirects, reviews and downloads.
5. The focused controls journey cancels a genuinely queued native grid before
   execution: only its mechanic report should exist. It then runs a two-trial
   grid with a labeled, injected publication failure on trial 2. Expect trial 1
   retained and **Resume remaining 1 trials** on IS Broad. Restoring publication
   and clicking resume finishes the **same job**, with nets **1872/3744** and a
   byte-identical first report. This is controlled failure qualification, not a
   claim about an actual provider outage. No generic results page is needed.

Focused validation: **4 backend checks passed in 7.60s**. Three affected browser
journeys passed: consolidated campaign navigation/archive inspection, queued
cancellation/actual resume, and retained standalone column/report behavior. The
final campaign capture passed in **12.22s**, controls in **6.23s**; the original
combined campaign/standalone check passed in **15.71s**. JavaScript syntax and
whitespace checks passed. No default/full/180-test suite was run. Temporary test
servers stopped via fixture teardown; no persistent server was started.

```sh
.venv/bin/python -m pytest -q tests/test_job_history.py \
  tests/test_campaign_broad.py::test_no_profitable_rows_do_not_advance_retries_are_idempotent_and_one_choice_is_enough
mkdir -p artifacts/single-campaign-results-REVIEW
.venv/bin/python -m pytest -x -q \
  tests/test_campaign_broad_browser.py::test_broad_search_columns_profit_filter_and_locked_selection \
  tests/test_campaign_broad_browser.py::test_queued_cancel_and_failed_run_resume_live_on_is_broad \
  tests/test_optimization_layout_browser.py::test_select_columns_reorder_both_groups_sort_and_persist \
  --basetemp=artifacts/single-campaign-results-REVIEW/browser
```

To reopen the ignored saved product library without recomputation:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/single-campaign-results-20261110/browser-final/test_broad_search_columns_prof0" \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8017
```

Open `http://127.0.0.1:8017/#jobs/backtest_batch/c8ded000cffc4ecaa1bf76931f898537`.
The earlier job is `ff78862bee70406299870af5b044183d`; the workflow is
`55a105ed8906460cabe6ba89833f5f24`. Stop this optional inspection server with
Ctrl-C. Portable exports and the synthetic source remain available when the
ignored test database is absent from another checkout.
