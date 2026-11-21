# Campaign stage passing criteria

User-approved policy, updated 2026-11-11, on `epic/revamp-workflow`. IS Broad,
IS Narrow, and frozen-family OOS assessment are implemented.
The portal's **Passing criteria by stage** panel shows the same server-owned
rules, including while later phases remain locked.

## Parameter help in the search grids

Broad, Narrow and the general backtest grid show each parameter's meaning only
as a native hover tooltip on the name and range inputs. Inputs also reference
the hidden explanation with `aria-describedby` for screen readers. Narrow keeps
the selected Broad value visible, including locked parameters.

`alphaquest/web/parameter-help.js` supplies presentation-only explanations where
the strategy's existing parameter metadata is incomplete; otherwise it uses the
registry's `description`. Twin Continuation help defines BO (breakout), MO
(momentum), timeframes, units, time rules and disabled values. In particular,
`bo_target_mult` and `bo_max_stop_mult` multiply the 15-minute ATR frozen at
arming; the stop cap tightens the swing stop rather than filtering out an entry.
Zero disables the target or the stop cap respectively. Times use Chicago HHMM.

Keep wording-only updates in this UI resource so they do not change numerical
strategy source hashes or invalidate frozen workflow sources. New parameters
should still declare their normal description in strategy metadata when first
implemented. This help does not change defaults, grid values or calculations.

## Mechanic validation — implemented

Run the strategy's default parameters on the frozen IS source/settings. Every
visible outcome metric needs the user's MultiCharts-parity check. Each sampled
trade needs both parity and execution-correctness checks. All required checks
and explicit confirmation are necessary. Zero-trade mechanics cannot pass.
The application does not infer external parity from a numerical backtest.

## IS Broad — implemented, policy `is-broad-v4`

All four criteria must pass for a configuration to become selectable:

| Test | Passing condition |
| --- | --- |
| Evidence | At least **24 calendar months of observed IS coverage** and **100 closed trades**. |
| Net profitability | Total net IS profit **> 0**, including commissions and slippage. |
| Profitable months | **> 50%** of complete IS calendar months have positive net P&L. Zero/no-trade months are nonprofitable. |
| Cost resilience | A **native second backtest with +1 tick of slippage per fill** has net profit **> 0**. Parameters, source, research dates and other execution settings are unchanged. |

Select one or two eligible configurations, then explicitly confirm to lock them.
Failing rows and insufficient-evidence rows are disabled. Checks are enforced
again on the server; changing a UI checkbox or sending a direct request cannot
bypass them. Sorting and browser column preferences do not affect admission.
Annualized profit, maximum mark-to-market drawdown depth and duration, and
annualized profit/drawdown ratio remain measured and visible as diagnostics.
Neither drawdown duration nor the ratio affects current admission. The +1-tick
scenario is a minimum fixed stress, not a calibrated live-fill estimate.

### Measurement conventions

- Dates and calendar months use the dataset's source timezone. The declared IS
  start is inclusive local midnight; IS end is exclusive midnight after the
  saved inclusive end date. Elapsed durations are measured in UTC seconds,
  including DST, weekends and gaps. No OOS observations enter screening.
- Minimum history uses the **first through last observed IS source dates**, with
  the last date inclusive. Padding the research declaration cannot create the
  required history. Calendar-month anniversaries determine the 24-month floor.
- Annualized net profit is total net profit divided by elapsed declared IS
  years, using **365.2425 days/year**. It does not require every individual year
  to earn more than the entire period's maximum drawdown. Comparisons use saved
  decimal measurements, not rounded table cells. When drawdown is zero, the
  diagnostic ratio is unavailable rather than invented as infinity.
- A separate streaming capture observes **every authoritative engine bar-close
  equity point**, including open-position P&L and costs already charged. The
  screening measurements are separate from the historical report's
  trade-close drawdown summary, which remains unchanged. These are bar-close
  marks, not tick measurements or intrabar drawdown bounds.
- Monthly P&L is the change in the last observed equity mark for each local
  calendar month. Complete months must lie inside both the declared IS window
  and observed source-date coverage. Partial first/last months are excluded
  from the monthly percentage but remain in total profit and drawdown. Missing
  months carry forward the last observed mark and count as zero/nonprofitable;
  no price interpolation or synthetic market observation is created.
- Drawdown tracks the running equity high and time underwater at every bar;
  the final unresolved interval extends to the declared IS end. Profitable
  months alone cannot hide underwater open positions.
- Cost stress **reruns the native strategy/execution engine**. It does not
  subtract a guessed per-trade fee from the original result or assume unchanged
  trade counts. Automatic legacy prop optimization remains off for these grids.

### Durability and earlier results

The policy is snapshotted into the optimizer job, per-run research metadata,
screening measurements and selection state before execution. Native baseline
and stress runs use the existing backtest catalogue and report directory. Each
candidate references its stress report. The results table links both reports
and a checked `is_screening.json` download with all four current verdicts, monthly P&L,
metrics and stress provenance; normal results CSV includes screening metrics.
Background progress/history remains on the existing jobs workflow.
IS Broad is the sole results page for campaign grids. Job history links to the
specific saved run; old batch/optimization URLs redirect there. Earlier runs
remain inspectable read-only inside IS Broad after a replacement grid. The
generic batch viewer continues to serve standalone legacy jobs.
In the IS Broad results table, each parameter with more than one value in that
saved run's grid starts visible and frozen beside Select and Trial. Fixed input
parameters start hidden, while all result metrics remain visible. Numeric result
cells display two decimal places; saved values, sorting, criteria and CSV retain
their original precision. The maximum drawdown duration column displays elapsed
calendar days (saved seconds divided by 86,400), including weekends; its CSV/API
field remains in seconds. **Columns** can change visibility, freezing and order;
choices are stored in this browser for the specific run, and **Reset layout**
restores its defaults. Opening another saved grid derives new defaults from its
own axes.

Report/artifact identities are captured at publication and rechecked on
selection, confirmation, carry-forward and saved evidence downloads. Missing or
modified required evidence cannot pass. Native stress artifacts participate in
cache validation and retained-campaign deletion protection. A changed engine
identity still blocks selection from a current-policy grid. Older measured grids
are reassessed from verified saved evidence without changing their source reports.

Earlier reports and confirmed selections are immutable. Prior confirmed
profitability-only, six-rule `is-broad-v2`, and five-rule `is-broad-v3` choices
keep their original rule and identity. An unconfirmed v2 or v3 grid with complete
saved measurements can be selected under the four current checks without a
backtest rerun: the API presents a separate admission verdict, verifies the
original report and stress artifacts, and saves the new selection policy
alongside the original source policy. Older profitability-only grids still
require a measured run.

### Verify the four-rule selection in the normal portal

1. Open a completed IS Broad run. The **Passing criteria by stage** panel and
   each row's eligibility details show four checks. Drawdown duration and the
   annual profit/drawdown ratio remain available as measurements.
2. For an unconfirmed `is-broad-v2` or v3 run, expect a notice that saved
   measurements are being reassessed. A row that passes the four current checks
   can be selected and confirmed without starting another backtest. Its original
   **Screening measurements** download still contains the six original checks;
   the new selection policy is recorded separately in the saved IS Broad package.
3. Reopen a previously confirmed six-rule run. Expect its historical verdict
   and frozen selection to remain unchanged. Removing or changing a saved
   screening artifact must still block a new selection.

Focused reproducible checks use the labeled synthetic 24-month dataset and
normal campaign routes; the browser fixture starts and stops a temporary app:

```sh
.venv/bin/python -m pytest -q tests/test_workflow_criteria.py tests/test_campaign_broad.py
.venv/bin/python -m pytest -q \
  tests/test_campaign_broad_browser.py::test_broad_search_columns_profit_filter_and_locked_selection \
  tests/test_campaign_broad_browser.py::test_insufficient_history_and_extra_cost_failure_are_explained_and_unselectable \
  tests/test_campaign_broad_browser.py::test_saved_six_rule_grid_uses_four_rule_portal_without_rerun
```

## IS Narrow — implemented, policy `is-narrow-v4`

Retain **all four current IS Broad pass requirements** and add three checks.
All seven must pass for a Narrow configuration to be selectable:

1. **Time-block evidence:** each of four consecutive, approximately equal IS
   calendar periods contains at least one observed source-local date. Block
   observed-day counts and P&L remain visible for review; this check alone does not
   establish balanced activity.
2. **Tested-grid parameter plateau:** use the nearest tested lower/higher value
   on every varied ordered-numeric axis, holding the other parameters fixed.
   At least **two distinct available neighbors** are required. **Every neighbor**
   must retain **at least 70% of the candidate's baseline net IS profit** and
   have **positive net profit in its own saved native +1-tick-per-fill rerun**.
   Retention uses exact decimal comparisons before display rounding. Boolean
   and `refinement_kind: categorical` axes are excluded. All seven checks remain
   required.
3. **Profit concentration:** total net IS profit remains **> 0 after removing
   the single best complete calendar month**. This policy targets recurring
   intraday strategies; rare-event or seasonal strategies need a different
   policy declared before searching.

Plateau assessment reuses the completed Narrow grid and its existing cost-stress
reports. It does not schedule any additional backtests or require finer values.
For example, a `5,10,15,20` grid assesses `20/20` against `15/20` and `20/15`.
Both are already tested. At a grid boundary, only available tested directions
are used, and the portal labels the assessment **one-sided**. A one-axis
endpoint has only one neighbor, so it remains insufficient evidence; a two-axis
corner can qualify with two neighbors if both pass. Missing rows *inside* a
completed declared grid are inconsistent evidence and still block selection.

The form no longer has a separate local plateau step. Expand **Eligibility** to
see the tested spacing, boundary directions, each neighboring native report,
net profit, retention percentage, and extra-slippage net profit. A drop below
70% or any nonpositive neighboring stressed net fails the plateau gate. The
result assesses stability **only at the tested spacing**, with no claim about
smaller untested changes. Minimum retention and the lowest neighboring profit
are also shown, without interpolation.

An **unconfirmed** completed branch can launch a finer or wider replacement
grid using the same form. Earlier jobs and reports remain in Job history;
attempts from them still count in the advisory search-family diagnostic. A
replacement clears that branch's unconfirmed selections. Confirmed choices
remain frozen.

Four-block and latest-block P&L, longest mark-to-market drawdown duration and
depth, and the search-adjusted daily-net confidence bound are **review
measurements**, not automatic vetoes. A candidate may pass despite an adverse
review measurement. The portal separates them from the seven required checks.
The +1-tick native cost rerun remains the minimum hard cost stress; it does not
claim to measure live slippage for a chosen position size.

For each confirmed Broad configuration, choose a Narrow grid. Parameters that
varied in Broad are locked at the selected Broad values by default. An explicit
**Refine in Narrow** choice can unlock a numeric Broad parameter when the saved
Broad grid has a representable finer step. The Narrow range must include its
selected Broad value, use a smaller step, include at least one new value, and
stay closer to that value than the midpoint to any other tested Broad value.
Thus a Broad swing length grid of `5, 20`, selected at `5`, may use Narrow
`3..7 step 1`; a binary mode grid of `1, 2` stays locked automatically. No
per-campaign refinement list is required. A future sparse coded mode can opt
out through `refinement_kind: categorical` in its strategy parameter metadata;
ordinary numeric parameters need no new declaration. Define the tag on its
`Parameters` dataclass field (for example,
`field(default=1, metadata={"refinement_kind": "categorical"})`). The strategy
registry copies field metadata into the parameter description, and
`campaign_narrow.refinement_options()` then excludes that field from the
checkbox and API opt-in. The current strategy fields do not use this tag;
binary `1,2` modes are already excluded by the integer-step refinement rule.
The other strategy parameters can vary. A grid must contain enough ordered
numeric values for at least one row to have two available numeric neighbors.
One numeric axis needs at least three values; two axes can each use two values.
Categorical axes may vary but do not count as adjacent numeric settings.
The native exhaustive optimizer validates
coupled strategy constraints before launch. Each Broad selection has its own durable
Narrow job. A completed branch can be selected and confirmed while another
branch is still running, interrupted, or not yet started. Its saved admission
includes the workflow's attempted-trial count **at that branch's confirmation**;
the confidence bound is advisory, and later searches on other branches do not
rewrite the frozen snapshot. The current unconfirmed branch's results show the
attempts recorded so far.
Up to two rows per Broad branch can be confirmed, at most four total. All four
may be eligible for later OOS assessment; no primary candidate is required.
Each confirmation is immutable. OOS navigation unlocks only when all branches
have confirmed selections. OOS assessment now applies the rules below. Prop simulation sizing and
portfolio selection remain future work.

The Narrow job saves its Broad selection identity, selected Broad anchor values,
explicitly refined and still-frozen parameters, refinement rule version, IS plan,
source and cost identity, all grid axes, four-rule screening policy, and the
`is-narrow-v4` policy before launch.
Native baseline and +1-tick cost-stress
reports are saved in the usual report store. Missing reports, changed measured
artifacts or changed neighboring evidence make a row ineligible. Results show
all seven required checks and separate review measurements per row, sortable
metrics, visible/frozen varied parameter columns, report links, and CSV/package
downloads. Fixed inputs start hidden.
The Narrow grid uses the same sortable header, sticky/frozen column, checkbox,
and eligibility-row styling as IS Broad.

IS Narrow screening reads and verifies each visible native report, its
cost-stress evidence, adjacent grid trials, and daily equity. Repeating that
work on every header click made sorting appear unresponsive. For a fully loaded
results table, header clicks now request only the saved trial order from the
existing optimization results route and rearrange the visible rows; no
backtest or screening rerun occurs. When sorting needs rows outside the loaded
page, the portal shows a sorting status while it loads them.

An interrupted Narrow grid retains its completed trials and offers **Resume
remaining trials**. Resume requires the saved job's exact conservative engine
identity; a production Python change rejects the request before modifying the
job. The portal shows that rejection beside the button, and interrupted trials
are not shown as active workers. Starting a new grid under changed code creates
a new job; the earlier completed reports remain inspectable.

The four period boundaries divide the declared inclusive IS dates into four
consecutive ranges with nearly equal calendar-day counts. Period P&L uses
last-observed daily native mark-to-market equity in the source timezone. The
best complete month's net P&L comes from the original native screening
capture; the full-period net less that one month must remain positive.

The confidence diagnostic uses the saved native daily equity series, at least
100 observed source-local dates, and a predeclared **five-observation Bartlett
HAC** long-run variance estimate. It calculates a one-sided normal lower bound
for mean net P&L per observed trading day. The one-sided tail probability is
`0.05 / N`, where `N` is the sum of planned trial counts in every retained
Broad and Narrow job for this workflow **at the time of assessment**, including
failed/incomplete attempts and replacement searches already recorded. A
confirmed branch freezes that count and diagnostic. Later attempts on other
branches can change the live diagnostic there but do not retroactively change
an earlier branch's saved assessment. The estimator is deterministic; no random seed is used. Its normal
approximation is an uncertainty check on this historical IS sample, not a
guarantee about future returns. The full method and observed family size are
shown on the page and saved with the selection. With fewer than 100 observed
dates, the diagnostic reports insufficient evidence; a missing or inconsistent
required daily source artifact still blocks selection.

Previously confirmed `is-narrow-v1`, `is-narrow-v2`, and `is-narrow-v3`
selections retain their original admission and frozen evidence. The historical
v3 reader retains its saved explicit local steps and two-sided requirements.
Completed, unconfirmed older grids use v4 directly from saved adjacent native
results and cost-stress reports. No grid rerun or additional backtest is needed
when those artifacts remain intact. Old `plateau_steps` metadata does not change
v4's neighbor selection. Historical confirmations are never relabeled as v4.
Use **Clear pending selection** to discard unconfirmed choices, including older
rows that no longer qualify. Confirmed selections cannot be cleared.

### Tested-grid plateau reproduction

`docs/evidence/is_narrow_tested_grid/README.md` provides saved normal portal
outputs and exact steps. The current two-branch journey tests hold minutes
`14,16,18,20`: all have 9,360 CU at one contract and 100% retained neighboring
profit. Interior settings 16 and 18 qualify. The one-axis endpoints are labeled
one-sided but have fewer than two neighbors. A separate two-axis journey
varies green-bar count `2,3` and hold minutes `14,16,18,20`. The green=3 / hold=14
corner qualifies with its two available neighbors, despite neither axis having
both directions. Its green=2 neighbor earns 16,560 CU; the hold=16 neighbor earns
9,360 CU. Job counts stay unchanged while the page assesses these saved trials.

Focused checks cover exact 70% retention, positive-but-below-threshold rejection,
a nonpositive stressed neighbor, categorical and diagonal exclusions, unequal
Decimal spacings, too few neighbors, missing internal grid rows, preserved
v1/v2/v3 confirmations, and existing coarse v2/v3 grids assessed and confirmed
without creating a job or rewriting native reports.

### Historical v3 fine-grid plateau evidence

The historical `docs/evidence/is_narrow_plateau/` snapshot preserves the labeled synthetic source,
normal portal screenshot, results JSON, selected package, and journey record.
That earlier two-branch journey used `hold_minutes=17,18,19,20`, local step 1.
Every row earns independently expected **9,360 CU** at one contract and survives
extra slippage; values 18 and 19 have both sides and **100% retention**. The
boundary rows 17 and 20 are disabled because 16 and 21 were not tested. With two
contracts, the profit amounts double while retention stays 100%. Confirm two
interior rows per branch and download their package; each selection saves the
full v3 plateau evidence and each job saves `plateau_steps`.

Focused analytical checks separately cover exact 70% acceptance, a positive
neighbor just below 70% rejection, a zero-profit extra-slippage neighbor,
missing internal evidence, excluded categorical/diagonal configurations,
Decimal local steps, and coarse-grid replacement without changing old reports.
These fixtures verify the gate arithmetic; they are not measured strategy edge.

### Reproduce the Narrow journey

Run the focused API and browser checks (the browser fixture starts and stops a
temporary server):

```sh
.venv/bin/python -m pytest -q tests/test_campaign_narrow.py
.venv/bin/python -m pytest -q tests/test_campaign_narrow_browser.py
```

The labeled synthetic source and saved browser/API results for v2 are in
`docs/evidence/is_narrow_v2/`; earlier v1 evidence remains in
`docs/evidence/is_narrow/`. The independent-branch journey and its saved
source, result, package, screenshot, and step record are in
`docs/evidence/is_narrow_independent_branches/`. The test uploads that source through the normal
dataset route, completes mechanic validation, runs a two-config Broad grid,
confirms both Broad rows, runs two four-config Narrow grids, and confirms two
passing rows from each branch. The fixture's six trades earn **78 CU per source
day** at one contract; 120 active days give **9,360 CU** net, four equal
calendar periods give **2,340 CU** each, and removing the best 390 CU month
leaves **8,970 CU**. The two-contract Broad branch doubles those amounts.
The full attempted family is ten configs (two Broad + eight Narrow). The
browser shows the Broad `contracts` value disabled in each Narrow form, the
varied `hold_minutes` column visible and frozen, and OOS locked until both
branches are confirmed. The first completed branch can be confirmed before
the second branch starts; its selection remains valid when that later job
changes the workflow-wide attempted-trial count. Direct requests that vary
`contracts`, select from an incomplete branch, or use changed neighboring
evidence are rejected. No
MultiCharts parity is asserted by this synthetic exercise; the mechanic
confirmation is a labeled user-attestation fixture.

## OOS — implemented, policy `campaign-oos-v1`

Run the complete confirmed Narrow family, **one to four configurations**, on
its frozen OOS window. A single table compares each candidate with **its own
selected IS report**. Parameters, dataset, sizing inputs, initial capital,
commissions, baseline slippage, benchmark settings, and research dates remain
frozen. The native engine starts flat for OOS. It executes only the explicitly
selected parameter dictionaries, never the Cartesian product of their values.
The default worker count is four, subject to the shared machine limit.

All seven checks must pass **per candidate**:

| Check | Passing condition |
| --- | --- |
| Evidence | At least **6 observed calendar months**, **6 complete calendar months**, and **50 closed OOS trades**. |
| Profitability | Net OOS profit **> 0** after native commissions and slippage. |
| Annualized profit retention | OOS annualized net profit **≥ 50%** of that candidate's IS annualized net profit. |
| Profit per trade retention | OOS net profit per closed trade **≥ 50%** of its IS net profit per trade. |
| MTM drawdown deterioration | OOS maximum bar-close MTM drawdown **≤ 1.5 × IS MTM drawdown**. If IS drawdown is zero, OOS drawdown must also be zero. |
| Monthly consistency | Profitable complete OOS months **≥ max(40%, IS profitable-month percentage − 15 percentage points)**. |
| Cost resilience | A second **native OOS replay with +1 tick slippage per fill** remains net profitable. |

These thresholds are a pragmatic screening policy, chosen before this OOS
execution. They allow up to 50% deterioration in time-normalized earnings and
per-trade expectancy while limiting drawdown growth and monthly deterioration.
They are not universal statistical cutoffs, evidence of a future guarantee, or
a substitute for trading-risk limits. Repeatedly selecting on observed holdout
results remains subject to overfitting; see the authors' primary paper,
[The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

### Measurements and comparison

All source dates and months use the dataset source timezone. Inclusive dates
become local-midnight bounds, with durations measured in elapsed UTC time.
Annualized profit uses the full declared period and **365.2425 days/year** for
both IS and OOS, so unequal period lengths are normalized. The history floor
uses observed source coverage, not padded declaration dates. Missing complete
months carry forward equity and count as zero/nonprofitable. Partial months
remain in total profit and MTM drawdown but are excluded from the monthly rate.

OOS MTM drawdown is captured from every authoritative native bar-close equity
point, including open P&L and costs already charged. It is not the historical
trade-close `max_drawdown_amount`, an intrabar extreme, or a daily approximation.
No costs are deducted twice. Drawdown durations are displayed in calendar days.
Profit per trade uses actual net profit divided by actual closed trade count.
Threshold comparisons use unrounded decimals; table values display two decimals.
Insufficient history, no trades, and missing/changed source evidence cannot pass.

Each baseline and cost-stress result is a durable ordinary backtest report.
`oos_screening.json` stores the measured period statistics, matching native
cost-stress identity, and policy. Frozen IS comparisons, source/artifact hashes,
family membership, implementation hashes, policy, and pre-launch prior-access
history are stored in the existing job catalogue. Native reports, JSON/CSV
assessment downloads, and per-row PASS/FAIL reasons reopen without resimulation.

### Navigation, execution and history

Click OOS after every selected Broad branch has confirmed its Narrow choices.
Opening the page does not execute OOS. **Run all frozen OOS configurations**
starts the exact family in the existing batch worker. It continues if the user
navigates away. Job history links directly to the OOS page and selected attempt;
older generic batch URLs redirect there as well. The page shows cheap worker
progress, refreshes measurements when a candidate finishes, and supports
stopping and resuming remaining configurations under the same engine identity.
Completed reports survive stopping or a server restart. A code change requires
another explicit assessment; saved reports and history are retained.

Any number of the four configurations can pass independently; no primary winner
is named, no candidate is added or retuned from OOS, and IS confirmations remain
unchanged. The overall OOS phase is marked passed when the full batch completes
and at least one candidate passes; the table always shows the individual count.
A completed batch with zero passing rows is not qualified. Prop simulation is
not implemented by this increment.

Each explicit repeat assessment is appended to history. The existing research
access ledger records actual OOS reads, and the existing OOS-attempt history
records each candidate's execution. The page discloses prior attempts and local
access status before launch. Unknown/external access stays unknown; reused OOS
is never called untouched. Protected final-session reservations continue to be
enforced by the normal read guard. Campaign report actions return to the correct
campaign phase; an individual report cannot bypass the complete-family launch.

### Reproduce OOS acceptance

`docs/evidence/campaign_oos/README.md` contains the normal-product steps, saved
source/results/screenshots/downloads, and independent expected values. The
stable synthetic OOS has 60 active days at 78 CU/day: **4,680 CU** per contract,
with **2,880 CU** after the extra tick per fill. Its matching two-year IS has
120 active days and **9,360 CU**. The degraded source produces **2,160 CU** OOS
and **360 CU** after extra slippage; its profit/trade retention is **46.15%**,
so it fails despite remaining profitable. Two-contract candidates double all
currency amounts, with unchanged retention percentages.

Focused API checks cover exact family membership rather than an eight-row
Cartesian expansion, freeze enforcement, closed phases, idempotent launches,
actual OOS MTM capture, inclusive thresholds and zero-drawdown handling, no-trade
and short-history rejection, stop/resume, prior access/repeated history,
report/verdict corruption, deletion protection and reopening without replay.
Browser checks cover the real single-table portal, column freezing/sorting,
progress, job-history navigation, acceptance reasons, and durable downloads.

## Final full-period Monte Carlo sanity check — implemented

After a completed OOS batch, **Final Monte Carlo sanity check** on the OOS page
assesses all its verified passing candidates independently (up to four). It is
an additional, separately reported retrospective check. It does not introduce a
fifth research phase, alter the seven OOS rules, reselect IS candidates, tune
parameters, or implement prop simulation.

### Inputs and simulation

Use each candidate's exact frozen IS report and matching OOS report. Verify the
native evidence and reconcile saved daily equity to the saved closed trades and
native net total. Stitch additive daily net P&L from both reports, keeping each
phase's actual execution/warmup/flat-at-end behavior; this is not a new continuous
price replay across the split. Costs are already in net P&L and are not deducted
again. There is no resizing, compounding, account replacement, or provider model.

Daily means the last observed bar of each source-local calendar date. Retain
observed dates with zero trades/P&L and daily marks of any open position. Do not
invent zero observations for missing source dates, holidays or an untested gap
between declared windows. Report that gap in calendar days. Each simulated path
has exactly the combined number of observed source dates. Partial/no-trade days
remain part of the input; no trading-calendar inference is added by this check.

The stationary circular block bootstrap samples consecutive daily increments
with replacement, with independent restart probability 1/L per observation.
Blocks may wrap around the pooled history and may cross the stitched split.
Run **5,000 paths for mean block length L=5 and another 5,000 for L=20**. Preserve
short clusters rather than treating every trade as independent; use both block
lengths as a simple dependence sensitivity check. Resampling with replacement
allows total profit to change, unlike a shuffle of the same trades. The method
is based on [Politis and Romano's stationary bootstrap](https://doi.org/10.1080/01621459.1994.10476870);
its assumptions do not establish that market P&L is stationary.

Current policy `campaign-full-period-monte-carlo-v2` fixes seed 42, PCG64 with
`SeedSequence([42, L])`, 128-path batches, NumPy version and linear quantiles.
Each candidate uses the same deterministic schedules. An unchanged completed
check is reopened/reused rather than rerolled. Interrupted/stopped checks can
be explicitly run again with the identical policy and seed. Source or model
changes produce a distinct saved assessment; earlier results remain unchanged.

### Passing rules

Both rules must pass. The profit rule must hold under **both** block settings:

| Rule | Threshold |
| --- | --- |
| Sufficient input evidence | ≥100 observed source dates and ≥100 closed trades across IS + OOS |
| Positive lower-tail profit | Empirical 5th percentile of full-period net profit **>0** |

Profit is strictly positive; equality at zero fails. Drawdown has no pass/fail
threshold in v2. Historical v1 assessments used a 95th-percentile drawdown limit
of 2× observed daily-close drawdown; those policies, verdicts and artifacts are
retained unchanged. No annual profit/drawdown ratio is introduced as a gate.

### Descriptive metrics and historical path favorability

Display mean and median full-period net profit alongside the 5th percentile,
median and 95th-percentile daily-close maximum drawdown, historical net/drawdown,
the 95th-percentile drawdown/historical drawdown multiple, positive-path frequency
and its estimated Monte Carlo standard error. These measurements inform review
and later sizing; none adds a new eligibility condition.

The original drawdown's percentile within simulated drawdowns is
`100 × (fraction strictly below + 0.5 × fraction equal)`. This midpoint treatment
of ties gives 50% when every drawdown is identical. A lower percentile describes
a more favorable historical drawdown relative to sampled paths. It is a
retrospective diagnostic, not a p-value or selection-luck test. When historical
drawdown is zero, the drawdown multiple is undefined and displays N/A.

Both original and simulated drawdown include starting P&L zero and use the same
daily-close basis. They do not measure intraday liquidation risk or the native
bar-close MTM drawdown. A strategy with positive lower-tail profit can pass even
when its drawdown multiple exceeds 2×; acceptable account risk must be assessed
against an explicit budget and account rules during subsequent sizing.

The bootstrap expected mean net profit is anchored to the historical sample.
Mean/median profit therefore receive no arbitrary retention thresholds against
the original result; requiring a positive median would add no protection beyond
the positive 5th-percentile requirement. The thresholds are retrospective local
screens, not a literature-certified guarantee of profitability.

### Updating an existing assessment without simulation

A saved v1 report is labeled as a historical policy in the portal. **Apply
updated policy to saved paths** validates the same frozen IS/OOS evidence and
sealed Monte Carlo population, then creates a new ordinary AnalysisStore report
under v2. No strategy replay, random draws, new OOS attempt, or cost deduction
occurs. The original daily/path CSV files are copied byte-for-byte; the new
report references their original analysis, policy, implementation, NumPy version
and checksums. The original JSON/ZIP and verdict remain untouched and downloadable.
Missing/corrupt path populations cannot be silently treated as passing. Current
reports with unchanged inputs are reused as before. GET requests never create
or migrate jobs. Policy updates are explicit and appear in normal job history.

Pooling IS and already accessed OOS reuses selection data. The results are
conditional on those observations and the bootstrap/stationarity assumptions;
they cannot prove an untouched holdout, correct multiple testing, forecast new
market regimes, establish MultiCharts parity, or certify trading readiness.

### Product use and durable evidence

Use the existing AnalysisStore catalogue, background worker, cooperative stop
control and sealed report/archive. Jobs continue after navigation, appear as
**Final Monte Carlo check** in Job history, and link to the exact OOS attempt.
Progress polls read only metadata while active; reopening completed reports
verifies artifacts and reads saved measurements without simulation. A cancelled
job publishes no partial passing population. Frozen IS/OOS reports are retained.

The single results table shows two block scenarios per candidate, combined
status, evidence counts, lower-tail profit, mean/median profit and per-rule
reasons. It prominently shows the frozen IS and OOS **bar-close MTM maximum
drawdown** from the existing verified backtest results. These are separate
period measurements, not a calculated stitched every-bar MTM drawdown.

**Daily-close Monte Carlo drawdown diagnostics (optional)** is collapsed by
default. It contains historical, median and 95th-percentile daily-close
drawdown, the drawdown multiple and historical drawdown percentile. Its help
explains that daily sampling misses intraday peaks/losses and cannot establish
intraday account-rule survival. Daily-close measurements stay on the same basis
as the daily-P&L bootstrap and are not substituted for the native MTM values.
This is a presentation change: numerical policy, saved artifacts, admission and
downloads are unchanged; existing assessments need no migration or rerun.

Monetary values display two decimals. Download JSON, exact
daily inputs, all path outcomes and a checksummed ZIP. Store source IDs and
artifact hashes, parameters, research windows, prior OOS verdict, policy, seed,
NumPy/calculation identity and limitations. Corrupt sources cannot launch a new
check; corrupt Monte Carlo artifacts cannot be presented as passing. A saved
sealed snapshot remains inspectable even if its live source later changes.

See the [historical v1 evidence](evidence/campaign_monte_carlo/README.md) and [current v2 journey and independent expected values](evidence/campaign_monte_carlo/v2/README.md).

### IS Narrow result sorting and verification reuse (2026-11-21)

Sorting is presentation only. Completed grids reuse disposable, checksummed
per-trial eligibility views in the existing bounded replay cache. Each view is
bound to the current implementation and policy, relevant job/trial/report
metadata, and artifact identities (path, inode, size, modification and change
times). Changes to evidence invalidate the view; unrelated job progress and
checkbox changes do not. During fresh verification, shared artifact bytes and
neighbor evidence are verified once per request and checked for concurrent
changes before returning. A missing or corrupt cache entry is recomputed.

Completed grids of up to 200 trials load their assessed rows once and display
50 rows at a time. Header clicks request only ordered trial IDs, using the
existing exact-decimal SQLite ordering across the whole grid, with missing values
last and trial-number ties. Existing row elements, expanded eligibility details,
and column preferences survive sorting and pagination. Changed source identities
cause a verified reload. Larger or unfinished grids retain server pagination and
reuse the same per-trial assessment cache when complete.

This cache is never selection authority: saving and confirming selections still
run the existing server-side evidence and implementation checks. Screening rules,
original reports, frozen confirmations, exports, and backtest calculations are
unchanged. No backtest rerun is required to display or sort saved results.
