# Campaign stage passing criteria

User-approved policy, 2026-11-10, on `epic/revamp-workflow`. IS Broad is
implemented. IS Narrow's additional requirements below are agreed and reserved
for a later implementation; displaying them does not execute or pass them.
The portal's **Passing criteria by stage** panel shows the same server-owned
rules, including while later phases remain locked.

## Mechanic validation — implemented

Run the strategy's default parameters on the frozen IS source/settings. Every
visible outcome metric needs the user's MultiCharts-parity check. Each sampled
trade needs both parity and execution-correctness checks. All required checks
and explicit confirmation are necessary. Zero-trade mechanics cannot pass.
The application does not infer external parity from a numerical backtest.

## IS Broad — implemented, policy `is-broad-v2`

All six criteria must pass for a configuration to become selectable:

| Test | Passing condition |
| --- | --- |
| Evidence | At least **24 calendar months of observed IS coverage** and **100 closed trades**. |
| Net profitability | Total net IS profit **> 0**, including commissions and slippage. |
| Profit / drawdown | Annualized net profit / maximum mark-to-market drawdown amount **> 1**. |
| Profitable months | **> 50%** of complete IS calendar months have positive net P&L. Zero/no-trade months are nonprofitable. |
| Drawdown duration | Longest mark-to-market drawdown is **< 25%** of the entire frozen IS period. An unresolved drawdown runs through IS end. |
| Cost resilience | A **native second backtest with +1 tick of slippage per fill** has net profit **> 0**. Parameters, source, research dates and other execution settings are unchanged. |

Select one or two eligible configurations, then explicitly confirm to lock them.
Failing rows and insufficient-evidence rows are disabled. Checks are enforced
again on the server; changing a UI checkbox or sending a direct request cannot
bypass them. Sorting and browser column preferences do not affect admission.

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
  decimal measurements, not rounded table cells. If drawdown is zero, positive
  annual net profit satisfies the profit/drawdown condition without inventing an
  infinite numeric ratio.
- A separate streaming capture observes **every authoritative engine bar-close
  equity point**, including open-position P&L and costs already charged. The
  six-criterion measurements are separate from the historical report's
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
and a checked `is_screening.json` download with all six verdicts, monthly P&L,
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
their original precision. **Columns** can change visibility, freezing and order;
choices are stored in this browser for the specific run, and **Reset layout**
restores its defaults. Opening another saved grid derives new defaults from its
own axes.

Report/artifact identities are captured at publication and rechecked on
selection, confirmation, carry-forward and saved evidence downloads. Missing or
modified required evidence cannot pass. Native stress artifacts participate in
cache validation and retained-campaign deletion protection. A new policy or code
change requires a new grid before an unconfirmed selection can be saved.

Earlier reports and confirmed selections are immutable. A prior confirmed
profitability-only selection keeps its original rule/identity and displays a
**historical-rule** notice; it is not relabeled as passing the six new tests.
An older unconfirmed grid must be rerun before choosing candidates. No old
checks, profits, files or attestations are silently rewritten.

## IS Narrow — agreed requirements, execution not implemented

Retain **all six IS Broad requirements** and add:

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

The later implementation must declare and save the time-block boundaries,
neighbor definitions, dependence-aware uncertainty method and tuning choices,
multiple-search correction, seeds and complete trial history before launching
Narrow. Missing/unsupported evidence must not be treated as a pass. Freeze the
selected configurations before accessing final OOS. The currently displayed
Narrow inputs are the locked Broad selections, not a completed Narrow search.

## OOS — future execution

Assess frozen choices without parameter reselection or using OOS outcomes for
IS candidate selection. Final OOS acceptance thresholds are not agreed in this
increment and no automatic OOS pass is available. Preserve explicit prior-access
history; a reused holdout must not be described as untouched.

The cutoffs above are the user's predeclared screening policy, not universal
statistical standards or evidence of future trading profitability. The product
demonstration and independent numerical expectations are recorded in
`docs/prop_simulation_review.md` under the six-criterion screening increment.
