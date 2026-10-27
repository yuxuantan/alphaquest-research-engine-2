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
