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
