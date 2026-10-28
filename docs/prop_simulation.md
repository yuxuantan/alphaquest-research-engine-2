# AlphaQuest local prop simulation

All production account arithmetic, resampling, evaluation attempts, funded
payouts, sizing, economics, charts and downloads are calculated by AlphaQuest.
Model version: `alphaquest-apex50k-eod-v4-instrument-commissions`. Earlier saved v1/v2/v3 reports remain unchanged. No external executable/DLL, generated
reference HTML/JSON/CSV/chart, Windows VM or vendor license participates in a new
calculation. Saved external results are independent qualification oracles only.
This supersedes the integration and older notebook specifications retained below.

## Product and source contract

New research runs require a declared chronological IS/OOS split. Initial backtests,
optimisation trials and their automatic prop analyses use **IS only**. An explicitly
selected saved IS parameter set can later run OOS backtest + prop analysis, through an explicit manual action, without an attempt limit. See [the workflow and API contract](research_workflow.md).
The model's internal validation remains within that selected period. Previously saved
reports are preserved and do not establish an untouched holdout.

Every new portal/API backtest, CLI backtest and trial in a new optimization now
checks and runs this default model automatically: **Apex 50K EOD, $49 evaluation,
$129 activation, 20 slots**, block 5, last 30% holdout and standard simulation
counts. Automatic inputs are native fills plus captured held-OHLC equity excursion
bounds and observed opening/cost jumps; automatic runs do not discover or substitute an export from Downloads.
The default is strategy-independent. Ordinary report generation and model
qualification helpers remain usable independently of the orchestration layer.

Backtest reports lead with **Historical net · USD** and link to the saved default
analysis. Optimization tables place the same metric after varying parameters
and Trial; it sorts ascending/descending with N/A last. It is exactly
`calculations.history.totals.net`: full observed-history payouts minus acquisition
costs across the default 20 slots, including repeated evaluation fees and the
activation fee for each funded start. It is separate from backtest trading P&L,
funded lifetime payout, and the training annual-per-slot sizing objective. Slots
share the same trade sequence. The model's normalization and sample conventions
below remain unchanged; the metric is not an annual forecast.

The backtest report also displays a **Prop analysis summary** immediately below
Trade-close equity. It reads the saved analysis: historical net/payouts/acquisition
costs first, then evaluation pass rate, selected sizes, acquisition cost per funded
account and lifetime funded-account payout/risk metrics. The slot count, data
window, fees and excursion provenance remain visible. New reports select their
recorded automatic analysis; older reports select the latest completed saved
analysis (or show the latest operation's status). Full-detail reports can discover
their source report's analysis. Viewing/reloading never submits a calculation or
searches for a new excursion export. No analysis, incompatible input, no validation
passes, historical engines and loading errors have explicit states. The full
analysis and original JSON download remain available directly in the summary.

Each immutable backtest records its analysis ID, model/profile version, settings
and native-source policy in `run_metadata.automatic_prop_analysis`. Workers compute
the normal report files locally without database access; the coordinator
publishes through the one existing prop catalogue. Full-detail replays reuse
their original analysis after exact trade/equity CSV checks. CLI `--output` is a
shortcut to the normal saved Backtest directory, so it creates no duplicate result
store; CLI initialization does not interrupt active portal analyses.

Empty, one-session, weekend or variable-quantity sources retain the model's
explicit source rejection (`incompatible`), and Historical net is N/A with the
reason. A completed simulation with no validation evaluation passes also has N/A
historical net, as acquisition-dependent results are unavailable. An operation
error has status `error`; its result is never a fabricated zero or a successful
simulation. Backtests remain inspectable, and optimization status identifies
prop calculation errors. Standard counts are never reduced to improve runtime.
Consecutive zero-net/zero-adverse trades in one session share their redundant
floor check; the first check, every nonneutral trade, session boundary, random
draw and standard path count remain. Exact comparison tests include floor hits.

Identical optimization reuse verifies both backtest and prop artifacts, including
the saved prop report, ZIP and captured file hashes. Changing model code, settings,
source or fees invalidates the trial identity. The normal configure/check/run
path can reopen a verified completed default report for the same source/settings;
modified/missing artifacts trigger a new analysis. Failed calculation attempts
are not reused as successful trials. Historical reports and old optimization
grids are not rewritten or automatically recalculated; their readers/downloads
remain available. Existing reports can still enter the manual workflow below.

Use completed backtest report → configure → check source → run → durable report.
There is one active API/catalogue, `/api/prop-analyses`, under data/prop_analyses.
`native_analysis.py` orchestrates the local model; `native_engine.py` owns account
transitions and sampling; `source.py` reconciles immutable native fills and an
optional original MultiCharts excursion export. The external runner has been
removed. The browser presents only saved AlphaQuest calculations for new
reports (format 3); saved SVGs remain downloadable. Format-2 external reports show a historical notice and retain
their downloads; they do not populate the new results page. Format-1 notebook
snapshots retain their historical reader.

The funded report opens with an Overview of one funded account: mean and median
lifetime payout, payout probability, drawdown failure and conditional payout
timing. Evaluation, Sizing, Historical replay and Source & model have separate
keyboard-accessible views. Payouts exclude acquisition fees; historical net is
labelled with its slot count and full data window. Training selection assumptions
are explicit beside the sortable size comparison. Details and downloads preserve
all metrics, settings and precision. Formatting, tab changes and sorting never
recompute financial results or submit a new analysis. Missing funded outcomes
remain unavailable, and incomplete measured excursions are disclosed up front.

Native source IDs, strategy/dataset metadata, UTC times, quantities and Decimal
cost conservation remain preserved. An optional XLSX/XLSM supplies measured MAE
and MFE only after every entry ID, direction, UTC entry time, quantity and net P&L
matches. Net amounts use absolute tolerance 1e-8 for spreadsheet floating noise.
For matched exports, simulation retains the original export's float representation
of reconciled net amounts: insignificant binary differences can change a rare
threshold path. Original native Decimal net values and export values both remain
in trades.csv; the source's exact cost ledger is unchanged. No commission or
slippage is deducted a second time. Excursions normalize by original quantity.

Pre-capture native inputs use realized losing P&L as adverse excursion, zero for
winners; this remains explicitly labeled close-only fallback. New native inputs
use captured held-bar risk and ordered adverse extrema as described below.
No measured excursions or trades are fabricated. Variable quantities, overlapping
positions, empty sources and invalid source cost arithmetic reject explicitly.

Session days are entry UTC converted to Chicago, plus seven hours (17:00 Chicago
session boundary). Weekend session dates reject; all zero-trade weekdays between
first/last sessions remain. The split is floor(0.7 * weekday count), or an explicit
holdout date leaving nonempty samples. At least two session weekdays are required.
The original dataset timezone remains source metadata, separate from export time.

## Local calculation contract

The qualified scope is one strategy, Apex 50K EOD, DLL on, full-cap payouts,
standard counts and the slot-year sizing objective. Prices, slots, whole-micro
NQ limit, bootstrap blocks 1/5/10, approval-day counting and explicit holdout date
are editable. Unsupported choices reject, without silently substituting a model.

- Evaluation: $3,000 target, $2,000 trail based on best close, $1,000 DLL,
  21 weekday deadline, no minimum days. Intratrade adverse checks use the tighter
  DLL/account floor; a DLL hit clips the day at its floor and ends trading for
  that day, while touching the account floor fails the account. Observed opening
  and cost jumps can overshoot both floors. Passes stop at the trade reaching
  the target. Every size from 1 through the lower of 60 MNQ and the user cap
  is tested (1–40 by default). Highest training pass
  count wins, with grid order resolving exact ties.
- Funded: $2,000 EOD trail, floor locks at +$100 after a close reaches +$2,100.
  Prior-close levels: 20 MNQ/$1,000 DLL below +$1,500; 30/$1,000 from +$1,500;
  40/$2,000 from +$3,000; 40/$3,000 from +$6,000. The tighter user cap applies.
  Five new days of $250+ and an inclusive 50% consistency check are required.
  Full-cap withdrawals are $1,500/$1,500/$2,000/$2,500/$2,500/$3,000 from equity
  above +$2,100; six payouts close the account. Cycle profit/qualifying counters
  reset after withdrawal. Approval-day qualification follows the explicit setting.
  The trail observes the pre-withdrawal close.
- Inactivity: at least two days of $50+ in the last 21 weekdays; the check runs
  on nonqualifying activity days. A day reaching $50 itself does not close for
  inactivity, even when its previous qualifying activity day is too old.
- Random draws: local NumPy RandomState/MT19937, streamed circular contiguous
  blocks. Training seed 42, holdout seed 43. Draw only when the previous block
  is consumed. A new account resets the block; failed evaluations within a
  funding chain retain the unfinished block. Training funding-chain seed 45,
  holdout funding-chain seed 44; one
  activation day is added after passing. No global RNG state is shared.
- Counts: 3,000 per sizing point, 20,000 training funding chains,
  20,000 final evaluations, 20,000 final funded
  lifetime accounts and 20,000 independent first-year accounts. Lifetime guard
  is 2,000 weekdays; first year is 261. Independent horizons consume draws
  differently, so first-year and lifetime probabilities need not be monotone.
- Economics: select evaluation size on training only, then calibrate acquisition
  cost as evaluation_price / selected_training_pass_rate + activation_fee.
  Training pass rate is the selected 3,000-path sweep point; replacement time is
  the mean of 20,000 repeated training evaluation chains including failed attempts
  and one activation day. Freeze these inputs before any holdout calculation.
  Rank funded sizes by 261 * (mean training lifetime payout - training acquisition
  cost) / (mean training funded lifetime + training replacement days), over every
  permitted/user-capped size. Holdout evaluation acquisition cost/time are separate
  validation estimates and cannot choose, rescore or gate a successful training
  fit. Historical replay uses the frozen training cost and ceil(training mean
  replacement days). No training passes or bounded-chain failure makes funded
  sizing unavailable; no hardcoded probability/delay fallback is used.
- Historical slots: one actual chronological account replay, scaled by number
  of slots; slots share their trades. Replacements incur expected acquisition
  cost. Payouts/costs round by calendar quarter before annual totals are added.
  Training history supplied the sizing choice; this is observed-history replay,
  not an independent forecast. With zero evaluation passes, acquisition-dependent
  results remain unavailable instead of receiving a made-up probability or delay.

## Publication and evidence

Queued/running/complete/error states share the existing durable catalogue.
Duplicate active submissions share an ID. Source hashes are checked before and
after calculation; original export bytes and settings are captured. Completed
reports publish by atomic rename and include calculations.json, per-trade source
reconciliation, evaluation/funded size CSVs, account traces, quarter/year cash,
chart-data JSON, locally generated SVGs and analysis.zip. No saved report is
rerun on reload/reopen. Numerical errors remain operation errors.

Limits: 100,000 trades, 20,000 weekday grid, 32 MiB compressed/64 MiB expanded
workbook, 128 MiB published files. Funding-chain guard is 10,000 attempts; exhausting
it is an operation error, not a fabricated funding time. Requested simulation
counts are fixed and are never silently reduced. The engine supports nonoverlapping
trades; measured MAE still cannot establish the exact price path inside a trade.

Qualification is external to production: scripts/verify_native_prop.py reads
reference results only after AlphaQuest has calculated a new report. The browser
reproduction script guards its production worker against vendor executable/DLL
reads, generated reference result reads and calculation subprocesses. See
prop_simulation_review.md for actual outputs, numerical comparisons and commands.

---

# Retired external-engine integration record

The following integration was rejected because AlphaQuest did not own its
calculations. Its saved results/evidence remain immutable. Its completion claim
established replay equivalence only and does not satisfy independent calculation.

# The Bridge Funded Lab portal integration

Current authority: the licensed **The Bridge 2.9.5.0** `funded-lab` CLI, executable
SHA-256 `4b0032d156072fc3aa290c2ac21a644b449e7ccf64335f918a02729250495a61`.
This supersedes the older notebook model for **new** portal operations. The
black-box executable generates all financial calculations, RNG draws, selections,
CSV tables and charts. The portal does not fit numbers to a saved report or
reinterpret the model. The original notebook remains historical evidence below.

## Normal workflow

Completed backtest report → Configure prop analysis → Check source → Run analysis
→ durable report. There is one active product workflow. New requests use
`/api/prop-analyses` with source_backtest_id, trade_file, export_timezone and the
Bridge settings form. Notebook-style overrides are rejected for new operations.
Old saved JSON/CSV/ZIP files and report readers remain unchanged.

The source backtest remains authoritative for identity, strategy/dataset metadata,
UTC fills, quantities and net costs. The original MultiCharts XLSX supplies
measured excursions absent from native storage. Each entry row must match native
trade ID, direction, UTC entry timestamp, quantity and net P&L (absolute tolerance
1e-8 for Excel floating noise; monetary source conservation uses Decimal). Export
exit rows are not additional trades. The file timezone is explicit, Chicago by
default. Source datasets/backtests are never rewritten or augmented in place.
Exactly one fully matching export in Downloads is suggested automatically;
otherwise the user selects an existing path. No upload is needed for the supplied
source. Other sources currently require a fully matching XLSX/XLSM export. Missing
source files, mismatched costs/times/IDs/quantities and empty sources reject; no
trades or measured excursions are fabricated.

## Execution and model identity

`bridge_source.py` reconciles source/export data. `bridge.py` validates the Bridge
form and captures immutable inputs. `bridge_engine.py` invokes only:

```text
TheBridge-Hosted.exe funded-lab --files <captured.xlsx> --settings <form.json> --out <staged-dir>
```

The existing licensed Windows login is used through Parallels `--current-user`.
No credential/license file is read, copied or bypassed. Collector, live, broker,
download and installation commands are not invoked. The user's already-running VM
and servers are neither started nor stopped. The default executable is
`C:\Program Files\The Bridge\TheBridge-Hosted.exe` in VM `Windows 11`; configure
ALPHAQUEST_BRIDGE_VM / ALPHAQUEST_BRIDGE_EXE if installed elsewhere. Inputs/output
must be under the macOS home shared as `\\Mac\Home`. Engine hash is pinned;
changing ALPHAQUEST_BRIDGE_EXPECTED_SHA256 requires separately qualifying a new
build rather than silently claiming parity after a vendor update.

Native fills already include trading costs. Matched export net P&L must agree;
The Bridge adds zero commission/slippage in the qualified model. Evaluation and
activation prices are external expenses, with explicit $49+$129 and $109+$0
choices. Default form: Apex 50K EOD, DLL on, full history, last 30% holdout,
block 5, most net per year per slot, full-cap payout requests, approval day counts,
20 slots, max total NQ 4, standard simulation size. Standard means original
20,000 final evaluations/accounts and 3,000 sizing simulations as resolved by
The Bridge; all resolved settings/rules/seeds remain in its captured settings.txt.
The local notebook's defaults, holdout leakage and selection formulas do not
participate in new calculations.

The supported first integration fixes account/product, standard counts, slot-year
objective and full-cap payout policy to the matched report. Prices, slots, total
NQ limit, block, explicit holdout date, DLL, opposite-netting and approval-day
counting remain explicit supported form values. Unknown or incompatible form keys
reject rather than being silently ignored. This is software-model parity, without
a claim about current official-provider correctness or actual micro execution.

## Publication, downloads and retained evidence

One existing catalogue under data/prop_analyses tracks queued/running/complete/error.
Each run copies the matched XLSX without renaming its strategy basename, captures
settings and executable identity, invokes the black box into staging, requires
successful real-data results, verifies resolved settings and source stability,
and atomically publishes all files. Duplicate active requests share a job ID.
Progress follows the run.log sections. A failed operation is never a completed
simulation outcome. The CLI's own process is bounded to 30 minutes; no existing
user process is terminated. Restarted incomplete jobs become errors.

Format 2 report.json wraps the **unaltered** Bridge results.json plus native source,
export/native/settings/executable/application hashes and a file manifest. All
original CSV, report.html, chart PNG, logs, original Bridge ZIP and captured input
are downloadable, together in analysis.zip. The portal renders Bridge's own
formatted table strings and captured chart images, without financial calculations
in JavaScript. Original HTML is an attachment; it is not executed in the portal.
URLs for captured files allow only saved manifest entries and constrain paths to
the job directory. Reload/reopen read saved files; neither requires Bridge/Windows.
Historical format-1 reports continue to show their original numbers with an
explicit historical-model notice and a link to configure a new Bridge analysis.

Limits: 32 MiB compressed / 64 MiB expanded XLSX, 100,000 trades, 128 MiB published
Bridge artifacts. No simulation count or input is silently reduced.

## Demonstrated parity

A fresh licensed CLI run, an actual temporary-server portal workflow, and a real
new run published through the user's existing portal all match the supplied
`/Users/yx/Downloads/20261026_171955/report.html` report's complete account/settings,
file/date metadata, part1 evaluation, part2 funded/slot results and warnings.
All eight CSV tables match exactly and all three chart PNGs are byte-identical.
The new published report is `2f58d252071e45aeb78859c4eb66cf30`. Creation timestamps,
output paths and timestamped export filenames naturally identify each new run.
See prop_simulation_review.md for exact UI steps, expected values and artifacts.

---

## Historical notebook specification (superseded for new operations)

The text below records the previously delivered model and its saved evidence.
Its reproduction claims apply to the old notebook, not The Bridge model.

# Notebook-compatible prop analysis

Authority: `notebooks/PropFirm_MonteCarlo_Apex50K_2508.ipynb`, SHA-256
`f79b6c6cc54e7bd64d619bb684ec4c6537c7bcf1d1e1d3f6d5bd6e74c908f89b`.
Downloaded on 2026-10-26; 1,016,849 bytes, 23 cells; exact reviewed revision.
Executable cells take precedence over notebook prose. Stored outputs are not oracles.

Workflow: completed backtest report → configure prop analysis → source check →
run analysis → durable report with saved tables, charts and downloads.

The strict deterministic account engine, official-rule/instrument profiles,
bar-coverage inspection, export-session profiles and mandatory calendars are
retired. No current provider verification or trading authorization is implied.
Legacy `/api/prop-simulations` and `#backtests/prop/results/...` readers are retired;
old `data/prop_runs`, SQLite catalogues and `artifacts/prop-*` remain untouched.

Implementation increments: (1) native trade adapter, statistics, daily grid and
main evaluation; (2) evaluation/staged sizing and repeated attempts; (3) funded
first payout and size selection; (4) lifetime ladder, economics and robustness.
Each uses the same final portal workflow with immutable results.

## Adapter contract

Use saved `trades.csv`; entry UTC timestamps are converted to the saved source
IANA timezone and stripped of timezone for the notebook. Preserve original UTC,
direction, trade ID, quantities, strategy and dataset identities and costs.
Weekend trades are excluded before quantity normalization, followed by the OOS
filter. The grid spans filtered first/last weekdays, including zero-trade weekdays.
Constant quantities normalize profit to one mini equivalent; variable quantities
require explicit opt-in. No bar completeness or measured MAE is required.
Reference gross profit is pre-cost input. Saved per-side commission becomes round
trip commission. Slippage assumptions must reconcile observed fills, including
limit exits with no adverse slippage. Never deduct source costs twice.
Keep literal notebook defaults alongside source-derived overrides.

## Preserved model limitations

Holdout is reused for staged/funded/lifetime selection. Staged sizing omits DLL.
Daily evaluation omits DLL; trade/excursion evaluation ignore degradation kwargs.
Missing excursions fall back to close-only trade mode; partial MAE uses realized
loss (zero on winners). Raw excursions are not quantity-normalized by the notebook.
Weekdays, deadline fallback and 22-day inactivity are approximations. DLL
liquidation clips to the exact threshold. Executable funded drawdown is $2,000.
First-payout selection relaxes its ceiling when necessary; lifetime falls back
to safest size. Acquisition and repeated attempts use shortcut formulas.
Fractional mini/micro equivalents are analytical scaling, not actual micro fills.

## Runtime and persistence

Numerical functions live in `alphaquest/prop/model.py` with explicit per-instance
state. `analysis.py` runs extracted cell calculations; `adapter.py` owns source
mapping and Decimal cost reconciliation. HTTP handlers orchestrate only.
NumPy 2.5.4 / pandas 3.1.0 are pinned. Reference execution in
`scripts/prop_notebook_reference.py` compiles original pinned notebook cells into
a fresh namespace, replaces upload with a temporary canonical CSV, injects explicit
settings, and omits presentation. It does not import production numerical code.
Bootstrap CI retains the notebook's fixed seed 42 and 10,000 draws; bounded
batches preserve flattened random draw order. Main/sweep counts are never reduced.

Native source presets retain saved per-side costs as round-trip overrides.
When limit fills differ from nominal slippage, the source preset explicitly
uses observed mean normalized slippage to reconcile aggregate baseline net;
per-trade differences remain visible in CSV. This is still the notebook's
constant per-trade formula, not a reconstructed execution model.

`data/prop_analyses` is the single new-format catalogue and result store. Jobs are
queued, running, complete or error. One worker bounds concurrent memory; each job
has its own model state. Duplicate active requests return the same job. Restarted
incomplete jobs become errors. Files publish by directory rename before catalogue
completion; downloads are available only for completed jobs. Source hash is
rechecked before publication. Reopening reads saved files without computation.
JSON/CSV/ZIP downloads contain source identities, exclusions, UTC/native dates,
input hash, resolved settings and origins, literal defaults, notebook/model/source
hashes, application commit, runtime and seed streams. No legacy results migrate.

Resource bounds reject oversized requests explicitly: 100,000 trades, 20,000
weekdays, 100,000 simulations per call, 64 sizes and 300 retained sample paths;
horizon guards are bounded separately. The server never silently truncates counts.

## Sizing and attempt sample semantics

Main simulation uses the full filtered sample. Cell 8 selects on the early
training weekday slice and evaluates the winner on validation with seed +2600;
its sweep uses PROP_MC_SIMS and common seed +2000. Cell 8b reuses validation and
seed +15000, omits DLL, rounds stage sizes to two decimals, and uses notebook
CI comparisons. Paths use seed +5000 and the current sample. Correlated attempts
use selected validation pass rate; independent attempts use the main pass rate.
The literal ATTEMPT_FEE=100, EVAL_FEE=100 and PA_ACTIVATION=140 remain available;
pricing presets explicitly override all three while leaving BLOWN_COST=150.

## Funded first payout

Cell 11's executable rules, including the $2,000 drawdown inherited from the
challenge, are saved with the report. Funded processing stays at trade resolution
with USE_MAE tied to the effective evaluation engine, even for daily evaluation.
Qualifying, strict consistency comparison, 22-trading-day inactivity and horizon
outcomes preserve original calculation order. Sweeps use seed +8000; detail at
the selected size uses +9000. Net EV subtracts (blown + inactive) × BLOWN_COST.
If no size meets MAX_BLOWN_RATE, the notebook's all-sizes fallback is retained and
marked. No official-provider profile or evidence approval is involved.

## Lifetime and final economics

Cell 15 runs the six-step payout ladder and selects the maximum expected total
subject to MAX_BLOWN_RATE, falling back to the minimum blown rate if necessary.
Original payout cycles, permanent drawdown lock, withdrawal reductions,
consistency, inactivity and horizon truncation are retained. Observability adds
raw account lifetimes and first-payout days without random draws or state changes.
LIFETIME_SIMS is declared but unused in the executable notebook: the selected
result is a sweep row using LIFETIME_SWEEP_SIMS. That fact appears in downloads.

Cell 16 uses **main full-sample pass probability at NUM_CONTRACTS** to calculate
`EVAL_FEE / pass_rate + PA_ACTIVATION`; it does not substitute selected evaluation
size or holdout probability. Expected net subtracts that cost from selected
lifetime extraction. The original NEGATIVE EV / THIN / WORKABLE / STRONG labels
are model output. Zero-pass acquisition cost is infinite; JSON null plus an
explicit explanation represents non-finite values. These shortcuts are not a
simulation of real purchases, campaigns or payment receipt.

Robustness reruns blocks 1, 5 and 10 at seed +7700, preserves downstream validation
sample use, compares evaluation at NUM_CONTRACTS and funded at lifetime-selected
size, then restores the configured block. All raw row results and chart data are
saved. Lifetime sweep uses seed +12000. Source equity uses cell 5b's $100,000
plotting base; account simulation equity paths remain profit relative to zero.

## Parity qualification

Fresh original notebook comparisons run under Python 3.12.5, NumPy 2.5.4 and
pandas 3.1.0. Stored notebook outputs are ignored. All compared discrete counts,
arrays, numerical aggregates and selections matched **exactly** (zero numerical
tolerance needed in this runtime), including a full-count native portal run.
Tests also cover all three evaluation engine settings, blocks 1/5/10, holdout
on/off, missing MAE, measured-excursion numerical processing, quantity/cost/date
boundaries, selection fallbacks, zero-pass economics and deterministic payout
outcomes. Cross-runtime equality is not claimed; pins and input/source hashes
are part of the report. The reference harness adds only observation of raw
lifetime-day arrays and captures pre-sizing statistics before notebook variable
reuse; numerical notebook calls and draw ordering remain original.

All four increments are delivered. Exact saved IDs, settings, outputs and
reproduction steps are in `prop_simulation_review.md`. Original-count sweeps,
main/detail simulations and 300 retained paths were tested through the portal;
reduced fixture demonstrations are separately labeled.

## Funded-sizing qualification status (2026-10-28)

The saved-report audit of `fed437c6d2944703b94eb45484a7039d` reproduces its
arithmetic but does **not** qualify its 20-MNQ recommendation as optimal or fully
faithful to current Apex rules. The funded search omits eligible targets above
20; an unchanged-model training extension favors 40. Current-rule inactivity,
consistency boundaries, excursion coverage and selection-economics limitations
are documented with independent probes and original provider sources in
[the detailed audit](reviews/prop-sizing-fed437c6-20261028.md). The previously
qualified numerical assumptions above remain preserved as versioned historical
behavior; no saved results were rewritten by this audit.


## Held-bar risk and complete permitted sizing (2026-10-28)

The v2 model tests every integer micro-equivalent size through the lower of the
user exposure cap and the stage limit: funded 40 MNQ; evaluation 60 MNQ. The
default user cap is 4 NQ, so both grids contain 1–40 MNQ. Funded orders still obey
the 20/30/40-MNQ tier from the prior session close; selecting 40 does not start a
fresh account at 40. Training selects the objective maximum and the selected size
is fixed for holdout. The Sizing view saves/displays the complete range, caps,
unit increment and whether the selected size is at the search boundary. This
implements the [published 50K funded size tiers](https://apextraderfunding.com/help-center/additional-helpful-items/scaling-levels-pa-explained/).

The shared execution engine captures risk for every new backtest and optimization
trial, independently of the strategy. `intratrade_risk.csv` retains trade identity,
quantity, net costs, lower/upper MAE and MFE in source account currency, fill
phases, full bars held, session crossing, and an ordered adverse frontier. Each
frontier entry is `[loss, observed_jump]`; only a new adverse maximum is retained.
The manifest seals the CSV SHA-256 and coverage counts. Financial trade/equity
CSVs and strategy decisions retain their original arithmetic. Entry commission
and adverse entry fill appear in marked equity; actual final net includes exit
costs once. Analysis normalizes source quantity once, with no extra cost debit.

Same-close entries exclude earlier entry-bar OHLC; next-open entries include their
entry bar. Next-open and bracket-gap exits exclude later exit-bar prices. An
intrabar stop excludes prices beyond the stop after exit. A target exit cannot
establish whether the adverse bar extreme preceded the target; lower/upper bounds
retain that ambiguity. Prop analysis uses the conservative adverse upper bound.
These are observed OHLC bounds, **not measured tick MAE/MFE**, and may classify a
possible breach conservatively. Independently reconciled measured exports remain
available explicitly; their earlier model contract is preserved.

Evaluation, funded simulations and historical replay use the first adverse
threshold hit. A continuous segment reaches the tighter DLL/account floor first;
a DLL stops the day and a touched account floor closes the account. Observed
opening gaps and actual entry/exit cost jumps liquidate at the observed equity,
so they can overshoot the DLL and close the account. Later risk events after a
DLL stop are ignored. OHLC cannot reveal unobserved tick gaps or liquidity: other
intrabar threshold fills remain an idealized assumption. MFE is captured for
inspection; it does not convert EOD trailing drawdown into intraday trailing DD.
See [EOD drawdown enforcement](https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-drawdown-explained/).

The source check rejects a missing/modified declared risk artifact, mismatched
trade IDs/timestamps/quantities/net costs, invalid bounds/frontiers and native
positions crossing CME session dates. The daily model cannot allocate overnight
unrealized P&L safely and **does not substitute close-only risk** for those inputs.
A new backtest remains available with its risk download and an incompatible prop
status. No account outcome is fabricated. Earlier sources without capture remain
explicitly labeled close-only fallback if analyzed without an upgrade.

On a pre-capture declared IS report, **Capture intratrade risk** performs the normal
immutable-source replay, verifies summary and trade/equity CSV hashes against the
original, and publishes a new compact backtest plus automatic v2 prop analysis.
Its `risk_from_run_id` links the source. Repeated requests reopen that replay.
OOS risk replays are blocked: the user must select a completed IS report and manually
run OOS again. Legacy undeclared reports remain read-only. All
original reports/evidence stay unchanged; new prop ZIPs include the captured risk
CSV, source reconciliation and complete size sweeps.


## Training-calibrated acquisition economics (v3, 2026-10-28)

The 52.5%/five-day constants are retired for new calculations. V3 inherits the
held-OHLC risk measurements and complete permitted sweep from v2. A single
strategy-independent calibration is derived from the training portion of the
selected source period; all candidate funded sizes share it. Actual funded size
and training cost/delay are fixed before holdout evaluation or funded simulations.
A low acquisition pass rate raises the repeated evaluation cost; a long funding
chain also reduces productive time. Because funded lifetimes differ, those
common acquisition inputs can change the ranking of candidate sizes.

`calculations.training_economics` records method/status, exact training date
window, selected evaluation micro size, passes/path count, pass-rate interval,
fees, expected evaluation attempts, acquisition cost, funding-chain count/seed,
and mean/median replacement time including activation. The funded selection
object links the same calibration. Each funded-sizing CSV row includes
`acquisition_cost`, `replacement_days` and `evaluation_pass_rate`, allowing its
`slot_year` score to be independently recalculated. `training_economics.json`
is a normal captured artifact and is included in the standard report ZIP.

The Evaluation view separates training calibration from holdout results. Sizing
shows the training-derived inputs and a full-precision inspection. Historical
replay labels its acquisition inputs as frozen training estimates. A zero-pass
training sample remains an inspectable completed analysis with funded sizing and
cash unavailable. Positive holdout passes cannot rescue it. If a valid training
fit has zero holdout passes, its selected size remains frozen; funded holdout
results are explicitly conditional on starting funded. Holdout acquisition
estimates remain unavailable instead of becoming zero costs or replacement days.
A bounded holdout funding-chain failure also cannot erase training selection.

Saved v1/v2 reports retain their original arithmetic, values and assumption text
and are labeled earlier models. Configure a new analysis from a declared IS
backtest to obtain v3 without replaying its trades or rewriting earlier results.
New backtests and optimization trials use v3 automatically. Existing OOS reports
remain readable, and fresh OOS calculations still require the explicit manual
backtest workflow. This increment does not loosen the OOS access policy.


## Selected prop report deletion

Completed prop reports and saved-analysis lists expose a selected-report Delete
control. `DELETE /api/prop-analyses/{id}` removes that inactive analysis and its
downloads/calculation-reuse references after confirmation. Backtest reports,
source datasets, optimization metrics and OOS execution history remain intact.
Queued/running analyses reject deletion. File staging rolls back on SQL failure;
post-commit cleanup can be retried. Original numerical reports remain unchanged
unless the user selects and confirms deletion of that particular report.

See [strategy navigation and report management](strategy_navigation.md) for the
strategy → instrument/full dataset → saved IS/OOS run browser. Browsing never
resimulates or rescales a saved result.

## Instrument commissions (v4, 2026-10-29)

New reports separate source costs from simulated trading commissions. The current
account/sizing model trades **MNQ at every candidate size**: 10 MNQ is ten micro
contracts, not an order for one NQ. Broker rate defaults live in
`alphaquest/prop/commissions.py`, separately from account arithmetic. The saved
Apex Rithmic schedule lists NQ $1.99 and MNQ $0.51 **per contract per side** for
both evaluation and funded accounts. Other published instrument rates are retained
in the schedule catalog, with the source URL and verification date, without adding
support for other instruments to this NQ/MNQ account model. Runtime does not fetch
or depend on the website. Broker name and MNQ per-side commission are editable;
custom brokers require a rate, and zero is allowed.

The normal configuration form exposes commission treatment, source instrument,
broker, and per-side commission. `auto` recognizes an immutable saved NQ/MNQ
symbol (including the full-dataset metadata), verifies the source point value
($20/$2), and applies the Rithmic default or explicit rate. An unidentified source
retains source costs with a visible notice; an explicit commission override then
requires selecting the source instrument. Other instrument conversions, conflicting
symbols, incompatible point values, and negative/nonfinite rates reject. `source`
mode deliberately retains source costs while normalizing identified MNQ exposure.
No assumption is made from a dataset filename. Defaults are suggestions and saved
settings/rate provenance are inspectable in the report.

For each source trade, **add back its actual recorded commission**, retain its
slippage, normalize to source quantity/point value, and deduct the simulated MNQ
round-turn commission once. With an NQ source, per-MNQ net is
`(source_net + source_commission) / source_quantity / 10 - 2 * MNQ_per_side`.
With an MNQ source it is
`(source_net + source_commission) / source_quantity - 2 * MNQ_per_side`.
The same adjusted daily pool feeds evaluation, funding chains, funded sizing,
holdout simulations and historical replay. Training/holdout selection boundaries,
path counts, account rules and source slippage stay as specified above. Recorded
source commission is authoritative; the NQ schedule default does not overwrite it.

Captured OHLC and measured source excursions include source costs, and compact
frontiers omit dominated observations and commission-side labels. A new exact tick
path cannot be reconstructed from them. V4 preserves every original observation
and uses a **conservative commission-adjusted simulation bound**: reserve the larger
of the one-side and round-turn fee deltas at saved adverse marks, also include the
new entry commission and realized exit loss. Observed gap flags remain in order.
This can overstate adverse risk; it is not exact repriced MAE/MFE. Close-only inputs
retain the realized-loss fallback. Source measurements and earlier reports are
never relabeled or modified. This correction intentionally differs from earlier
net-scaling engines; no external-engine numerical parity is claimed for v4.

Source checking shows the selected treatment/rate and original cost reconciliation.
Saved `trades.csv` retains source costs and adds `simulation_net_per_mnq`,
`simulation_commission_per_mnq`, plus NQ-equivalent kernel amounts and conservative
risk inputs. `commission_reconciliation.json` captures the applied rate, broker,
schedule provenance, formula, risk policy and totals normalized to one NQ exposure
per source trade (divide those totals by ten for one MNQ). The Source & model view
and standard report ZIP include this artifact. Report/model identities and calculation
cache hashes distinguish the new engine; all prior saved reports remain readable.

Source: [Apex Rithmic commissions and instruments](https://apextraderfunding.com/help-center/rithmic/rithmic-commissions-instruments/),
checked 29 October 2026. The schedule is not a live guarantee of future fees.
