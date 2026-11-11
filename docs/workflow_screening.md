# Campaign stage passing criteria

User-approved policy, updated 2026-11-11, on `epic/revamp-workflow`. IS Broad and
IS Narrow are implemented. OOS execution remains a later stage.
The portal's **Passing criteria by stage** panel shows the same server-owned
rules, including while later phases remain locked.

## Mechanic validation — implemented

Run the strategy's default parameters on the frozen IS source/settings. Every
visible outcome metric needs the user's MultiCharts-parity check. Each sampled
trade needs both parity and execution-correctness checks. All required checks
and explicit confirmation are necessary. Zero-trade mechanics cannot pass.
The application does not infer external parity from a numerical backtest.

## IS Broad — implemented, policy `is-broad-v3`

All five criteria must pass for a configuration to become selectable:

| Test | Passing condition |
| --- | --- |
| Evidence | At least **24 calendar months of observed IS coverage** and **100 closed trades**. |
| Net profitability | Total net IS profit **> 0**, including commissions and slippage. |
| Profitable months | **> 50%** of complete IS calendar months have positive net P&L. Zero/no-trade months are nonprofitable. |
| Drawdown duration | Longest mark-to-market drawdown is **< 25%** of the entire frozen IS period. An unresolved drawdown runs through IS end. |
| Cost resilience | A **native second backtest with +1 tick of slippage per fill** has net profit **> 0**. Parameters, source, research dates and other execution settings are unchanged. |

Select one or two eligible configurations, then explicitly confirm to lock them.
Failing rows and insufficient-evidence rows are disabled. Checks are enforced
again on the server; changing a UI checkbox or sending a direct request cannot
bypass them. Sorting and browser column preferences do not affect admission.
Annualized profit, maximum mark-to-market drawdown and their ratio remain
measured and visible as diagnostics. The ratio no longer affects admission.

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
  five-criterion measurements are separate from the historical report's
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
and a checked `is_screening.json` download with all five verdicts, monthly P&L,
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
identity still blocks selection from a current-policy grid. The specific
six-rule-to-five-rule reassessment below uses verified historical evidence.

Earlier reports and confirmed selections are immutable. A prior confirmed
profitability-only or six-rule selection keeps its original rule/identity and
displays a historical notice. An unconfirmed `is-broad-v2` grid with complete
saved measurements can be selected under the five current checks without a
backtest rerun: the API presents a separate admission verdict, verifies the
original report and cost-stress artifacts, and saves the new selection policy
alongside the original source policy. Its original six-rule verdict and files
are unchanged. Older profitability-only grids still require a measured run.

### Verify the five-rule selection in the normal portal

1. Open a completed IS Broad run. The **Passing criteria by stage** panel and
   each row's eligibility details show five checks. The annual profit/drawdown
   ratio remains in the results table and CSV, with no pass/fail check.
2. For an unconfirmed `is-broad-v2` run, expect a notice that saved six-rule
   measurements are being reassessed. A row that passes the five current checks
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
  tests/test_campaign_broad_browser.py::test_saved_six_rule_grid_uses_five_rule_portal_without_rerun
```

## IS Narrow — implemented, policy `is-narrow-v1`

Retain **all five IS Broad requirements** and add:

1. **Parameter stability:** at least **70%** of valid immediate neighboring
   configurations are profitable after costs. Use the predeclared grid steps
   and every applicable direction, rather than choosing neighbors after seeing
   results. Invalid coupled combinations are excluded explicitly. Categorical
   neighborhoods must be declared for the relevant strategy.
2. **Stability across time:** divide IS into **four consecutive, approximately
   equal calendar periods**. At least **three** must be net profitable, including
   the **most recent**.
3. **Profit concentration:** total net IS profit remains **> 0 after removing
   the single best complete calendar month**. This is the agreed recurring
   intraday-strategy policy; a rare-event strategy needs a separately approved
   research policy declared before its search.
4. **Statistical evidence after searching:** the **95% lower confidence bound
   on mean net daily P&L must exceed zero**, preserving time dependence and
   correcting for all configurations attempted in Broad and Narrow, including
   unsuccessful searches and reruns. An ordinary winner-only interval does not
   satisfy this condition.

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
ordinary numeric parameters need no new declaration. The other strategy parameters can
vary. At least one Narrow parameter must vary so every row has an immediate
neighbor. The native exhaustive optimizer validates coupled strategy
constraints before launch. Each Broad selection has its own durable
Narrow job; all branches must finish before any Narrow row becomes selectable.
Up to two rows per Broad branch can be confirmed, at most four total. Each
confirmation is immutable. OOS navigation unlocks only when all branches have
confirmed selections; OOS execution and acceptance rules remain unimplemented.

The Narrow job saves its Broad selection identity, selected Broad anchor values,
explicitly refined and still-frozen parameters, refinement rule version, IS plan,
source and cost identity, all grid axes, five-rule screening policy, and the
`is-narrow-v1` policy before launch. Native baseline and +1-tick cost-stress
reports are saved in the usual report store. Missing reports, changed measured
artifacts or changed neighboring evidence make a row ineligible. Results show
all nine checks per row, sortable metrics, visible/frozen varied parameter
columns, report links, and CSV/package downloads. Fixed inputs start hidden.

The four period boundaries divide the declared inclusive IS dates into four
consecutive ranges with nearly equal calendar-day counts. Period P&L uses
last-observed daily native mark-to-market equity in the source timezone. The
best complete month's net P&L comes from the original native screening
capture; the full-period net less that one month must remain positive.

The confidence gate uses the saved native daily equity series, at least 100
observed source-local dates, and a predeclared **five-observation Bartlett
HAC** long-run variance estimate. It calculates a one-sided normal lower bound
for mean net P&L per observed trading day. The one-sided tail probability is
`0.05 / N`, where `N` is the sum of planned trial counts in every retained
Broad and Narrow job for this workflow, including failed/incomplete attempts
and replacement searches. This Bonferroni correction includes unsuccessful
trials. The estimator is deterministic; no random seed is used. Its normal
approximation is an uncertainty check on this historical IS sample, not a
guarantee about future returns. The full method and observed family size are
shown on the page and saved with the selection. If there are fewer than 100
observed dates or inconsistent daily/source evidence, this check fails.

### Reproduce the Narrow journey

Run the focused API and browser checks (the browser fixture starts and stops a
temporary server):

```sh
.venv/bin/python -m pytest -q tests/test_campaign_narrow.py
.venv/bin/python -m pytest -q tests/test_campaign_narrow_browser.py
```

The labeled synthetic source and saved browser/API results are in
`docs/evidence/is_narrow/`. The test uploads that source through the normal
dataset route, completes mechanic validation, runs a two-config Broad grid,
confirms both Broad rows, runs two two-config Narrow grids, and confirms one
passing row from each branch. The fixture's six trades earn **78 CU per source
day** at one contract; 120 active days give **9,360 CU** net, four equal
calendar periods give **2,340 CU** each, and removing the best 390 CU month
leaves **8,970 CU**. The two-contract Broad branch doubles those amounts.
The full attempted family is six configs (two Broad + four Narrow). The
browser shows the Broad `contracts` value disabled in each Narrow form, the
varied `hold_minutes` column visible and frozen, and OOS locked until both
branches are confirmed. Direct requests that vary `contracts`, select before
both jobs finish, or use changed neighboring evidence are rejected. No
MultiCharts parity is asserted by this synthetic exercise; the mechanic
confirmation is a labeled user-attestation fixture.

## OOS — future execution

Assess frozen choices without parameter reselection or using OOS outcomes for
IS candidate selection. Final OOS acceptance thresholds are not agreed in this
increment and no automatic OOS pass is available. Preserve explicit prior-access
history; a reused holdout must not be described as untouched.

The cutoffs above are the user's predeclared screening policy, not universal
statistical standards or evidence of future trading profitability. The product
demonstration and independent numerical expectations are recorded in
`docs/prop_simulation_review.md` under the six-criterion screening increment.
