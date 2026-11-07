# AlphaQuest local prop simulation

Current implementation (8 November 2026): later sections and the
[execution checklist](robust_research_plan.md) supersede earlier dated pending
statements. Native independent optimization, complete-procedure verification,
the guided workspace and explicit frozen phase-pair lifecycle comparison are
implemented. Supplied forward observations use the normal durable report workflow
with exact event/cash reconciliation and advisory recovery. Prospective Funded
observation plans support a descriptive single-path cash difference when full
supplied coverage, calendar alignment, cash-share conservation and local frozen
sizing checks agree. Dynamic contexts reuse the existing causal sizing owner;
changed numerical source identity withholds conformance. Coverage, external
strategy behavior and provider payout eligibility remain unverified. The full
repository acceptance gate remains outstanding. No provider or broker integration
is production-qualified. Earlier findings and reports are preserved below.

7 November 2026: saved-report prop configuration also exposes nested inner
research, actual execution-stress reruns, causal market-condition evidence and
durable qualification reports. These reports currently stop before
prop policy optimization and outer replay; no prop calculations or readiness
claims are replaced. The [research workflow](research_workflow.md#nested-inner-research)
explains the increment and the [checklist](robust_research_plan.md) records the
remaining complete-platform work.

8 November 2026 extension: optional **Economic validation** now carries the full
inner-qualified set into independent phase forecasts, seals the selected family,
and replays fixed policies on the actual outer source sequence through the same
campaign/AnalysisStore workflow. Evaluation feasibility precedes Pareto ranking;
Funded uses one fresh account and its exact outer cash horizon. Receipt cutoff,
retry/activation waits, empty observed sessions and abstention remain explicit.
The [workflow](research_workflow.md#nested-economic-validation) describes the
current controls. [Provider rule review](provider_rule_review.md) records dated
source evidence and known discrepancies without changing historical kernels.
Fixed-signal-path scenarios, sampled forecasts and provider/live qualification
remain distinct. The following reliability increment adds predeclared reference
forecasts/replays and fold-based comparison, calibration, coverage and stability
reports in this same workflow. Families have no implicit aggregate; missing
forecasts do not erase observed cash, and censored acquisition fees remain paid.
Optional conservative Funded selection resamples historical sessions and
re-estimates mean cash, preserving separate numerical-error requirements. It
does not optimize a single-account payout percentile or claim future confidence.
Final recommendation remains incomplete. Subsequent increments below implement
native chronological account-controlled reruns and optional native forecasts;
native candidate optimization and frozen campaign handoff remain pending.

## Canonical external sources — 2026-11-08

**Backtests → Import external trades** validates the versioned
[`aq-trade-export-v1` contract](designs/trade_export_v1.md) and saves an ordinary
backtest report. Original bytes, normalized trades/risk events, exporter identity,
declared research access and exact fee/slippage reconciliation remain inspectable.
No market dataset, missing sessions, measured excursions or native replay are
fabricated. Importing is distinct from model admission.

The normal **Configure prop analysis → Check source → Run analysis** journey
accepts a bounded annualized subset: identified USD NQ/MNQ with constant source
quantity, actual-fill timestamps, intraday-flat nonoverlapping trades, complete
ordered marks covering declared extrema, explicit contiguous business-weekday
inventory including empty edges, and exporter-declared signal-path invariance.
The declaration is an assumption, not independent proof of tick completeness or
execution scalability. Other imports remain useful saved reports and explain
why simulation is unavailable. The first M2a increment admitted annualized
analysis only; M2b adds the independent phase policies below. External standalone
dated/budgeted replay remains unavailable.

Actual fills already include slippage. Source fees remain in net returns;
commission overrides replace the source fee once, using one side while open and
two at close. Every newly adverse observed mark is a jump, preserving overshoot
when a threshold is crossed instead of inventing a fill at the threshold. The
adapted CSV retains original net/costs and ordered events alongside per-NQ
simulation values (one MNQ is 0.1 NQ). Observed-mark extrema are labelled
separately from measured companion excursions. Closed-trade or extrema-only
data cannot establish crossing order and rejects this simulation route.

Ordinary reports/downloads verify saved byte hashes without re-parsing or
recalculation. New analyses additionally verify source/canonical semantics,
capture immutable inputs in `analysis.zip`, and include importer/adapter code in
implementation identity. No Bridge or other external prop engine/results are
used. [Independent arithmetic, boundary checks and saved product evidence](prop_simulation_review.md#canonical-external-trades-and-local-prop-analysis--2026-11-08).

## State-aware independent phase sizing — 2026-11-08

Campaigns can retain legacy fixed size lists or declare `sizing_policies` for each
source. The latter expands every source/trial × hard MNQ cap × policy into a
candidate. A direct phase candidate supplies optional `sizing`, containing
`policy`, `initial_configured_capital: "50000"` and `planning_execution`.
Omitting it preserves the existing fixed-size path. In a policy candidate,
`micros` means the user ceiling; provider tiers and the simulation exposure cap
still apply. Phase objectives and source membership remain independent.

| Policy | Decision before each source opportunity |
| --- | --- |
| `fixed_contracts` | Requested whole `contracts`, constrained by declared/provider caps |
| `fixed_dollar_risk` | Floor of `risk_dollars` divided by planned loss per MNQ |
| `percentage_risk` | Floor of named base × `risk_percent / 100` divided by planned loss per MNQ |

Percentage `reference` is exactly `initial_configured_capital`,
`current_account_balance` or `available_drawdown_cushion`. These mean $50,000,
$50,000 plus the current account equity change, or current equity minus its
applicable account floor respectively. Payout account deductions reduce the
current balance/cushion; evaluation fees never enter funded account state.
The existing engines retain session-opening tier/daily floors and their current
EOD trail timing. No implicit funded replacement or acquisition inputs are added.

For the supported MNQ instrument (`tick_size: "0.25"`, `point_value: "2"`):

```text
planned loss / MNQ = (adverse stop distance from decision reference
                    + tick size × (entry slip ticks + stop-exit slip ticks)) × 2
                    + 2 × planning commission / side
```

Planning inputs must be explicit; actual future entry fills are excluded. This
amount chooses quantity only and is never charged to the already net source
P&L. For example, a five-point stop, one entry-slip tick, two stop-slip ticks and
$0.50 per side imply $12.50 planned loss per MNQ: $50 risk selects four. An
opt-in cushion constraint at exactly $50 selects three because touching the
floor counts as a breach. Observed gaps can exceed planned loss despite this
constraint. Min/max contracts, account/daily cushion guards and skip reasons are
part of the saved policy; below-minimum quantity consumes no trade, fee or
activity, while the session/calendar advances normally.

The shared pure contract lives in `prop/sizing.py`; `sizing_runtime.py` maps
source metadata/current state into it. Both existing account engines call it
inside their normal evaluation/funded transitions. Python and matching compiled
kernels support the same decisions; legacy default calculations retain their
fixed path. Independent Evaluation attempt samples and dated Funded samples save
complete decision aggregates plus up to 10,000 retained decisions per candidate.
This limits detail bytes, not candidate membership or simulated opportunities.
`sizing_summary.json`, `sizing_decisions.csv`, the normal report JSON and ZIP
remain ordinary AnalysisStore artifacts. Per-trade state uses session floors;
later EOD updates are represented by the account paths, not invented intratrade
trail updates. The legacy float account arithmetic is retained; exact Decimal
budget division uses the represented predecision account state.

Admitted risk-based sources currently require complete canonical external
ordered marks, causal same-close/next-open initial-stop decisions and explicit
exporter-declared path invariance. No original future fill or excursion supplies
the decision stop. Native fixed unguarded policies retain the existing scenario;
native dynamic/cushion-guarded policies reject until a suitable strategy rerun
can handle changed position callbacks and signals. New native report sidecars
capture actual decisions/stops/fills and verify replay/cache identity, but do not
prove invariance. All planning/source/code hashes are frozen with candidates.
Older reports remain immutable; incompatible frozen launches fail closed.

An external IS package can be compared, frozen and downloaded. Native OOS launch
cannot generate an external strategy's outcomes, so it rejects before accessing
data. Separately supplied external OOS assessment and chronological outer-policy
replay remain later work. These are local model scenarios, not provider parity,
tick-completeness certification or live execution readiness.

## Current behavior and navigation — updated 2026-11-08

Use an ordinary saved IS backtest/trial → **Configure prop analysis** → create an
independent phase campaign → **Check** → **Run** → durable results/downloads →
named IS freeze → manual frozen OOS assessment. Evaluation returns a cost/calendar
Pareto frontier; Funded ranks cash received before an exclusive calendar cutoff
from a fresh funded account. Neither selects using the other phase's data.
Campaign calendar coverage is automatic: scenario start + the saved Evaluation
chain limit (default 3,650 civil days), or + the Funded receipt horizon. The manual
coverage-end field is removed; checks, immutable manifests and downloads disclose
the derived date. Explicit API calendars and earlier reports remain supported.
This changes campaign normalization/UI, with no kernel, cutoff or metric change.
[Coverage behavior and limits](research_campaign_api.md#automatic-calendar-coverage--7-november-2026).
Candidate counts are also automatic. The manual maximum and fixed count ceiling
are removed; more than 128 candidates require explicit confirmation of the full
count before a campaign is saved. Source/size membership is never truncated.
Existing workload/report-byte limits remain. Admission source changes advance
the phase implementation hashes; existing reports stay readable, while old
campaign checks/frozen launches fail closed on incompatible implementation identity.
[Candidate confirmation evidence](prop_simulation_review.md#automatic-candidate-count-and-large-search-confirmation--2026-11-07).
IS first/last sessions default to the selected sources' common actual saved
coverage within declared IS, using CME session dates rather than trade dates.
Optional narrowing/reset remains available; source/trial changes rederive the
window. This fixes split boundaries outside the saved bar period without
relaxing validation or changing phase numerical identities.
[IS window behavior](research_campaign_api.md#valid-is-window-defaults--7-november-2026).
[Campaign controls](research_campaign_api.md) · [IS/OOS](research_workflow.md) ·
[Module ownership](architecture.md#final-module-ownership-and-retention) ·
[Final qualification](prop_simulation_review.md#final-architecture-cleanup--2026-11-06).

New grids can skip automatic **legacy** joint Apex/Lucid reports with
`automatic_prop: false`; omitted/true retains existing automatic behavior. The
shared form sends an opted-out single combination through the ordinary grid job
as well. This changes job orchestration, not account formulas or saved reports.
Manual legacy annualized sizing and budgeted observed cash remain supported;
standalone dated replay remains API/report compatible. Portfolio search is pending.

This document preserves the versioned contracts and historical numerical findings.
The phase sections immediately below are current contracts; dated standalone
release statements about absent UI are historical scope, superseded by campaigns.
The [historical notebook specification](#historical-notebook-specification-superseded-for-new-operations)
and subsequent dated qualification sections are retained evidence, not new defaults.
No prior calculation/rule identity or historical artifact was rewritten by cleanup.

## Independent phase optimization — updated 2026-11-06

[The phase optimization specification](phase_optimization_plan.md) extends this
model boundary with independent Evaluation cost/calendar-time Pareto search and
Funded horizon-cash search conditional on starting funded. The standalone
Evaluation and Funded backends below are implemented.
Independent Python simulation profiles have been extracted as described below.
The selectable UI methods remain current. Annualized joint sizing is
classified as **legacy business-level optimization**, retained with its formulas,
regression tests and reports until separately approved retirement; it must not
be the selection mechanism for independent phases. Explicit comparable saved
IS candidates across jobs/strategies are supported by both phase backends;
saved-trial campaign creation, portal comparisons and frozen phase OOS assessment
are implemented. Automatic generation of new grids and adaptive refinement remain
planned. The historical standalone sections below describe their original scope;
the [campaign guide](research_campaign_api.md) gives the current product workflow.
Completed dated source/cash-ledger work and all dated specifications/evidence
below are preserved. No provider rule or numerical parity is newly verified.

## Standalone Funded optimizer — 2026-11-06

`prop.funded_optimization` implements `funded-optimization-calendar-receipts-v1`.
`FundedCandidate`, `FundedSearch`, `check_search` and `optimize_funded` are Python
interfaces; serialized searches use the existing `POST /api/prop-analyses/check`
and `POST /api/prop-analyses` with `mode: "funded_optimization"`. The existing
AnalysisStore worker/catalogue publishes format-5 reports, file downloads and
`analysis.zip`. The original standalone increment added no UI; the subsequent
[campaign portal](research_campaign_api.md) now exposes it. No portfolio optimizer
is added. Existing annualized,
Evaluation, dated and budgeted requests/reports retain their meanings.

The sole objective is `expected_funded_cash_payouts_within_horizon`: the arithmetic
mean, over **all** simulated starts including zero payouts, of trader cash
entitlements whose modeled receipt date precedes the cutoff. Each path starts
with a fresh funded account at t=0, without acquisition or replacement. Evaluation
sources, pass probability, fees, acquisition time, strategy/size and joint
slot-year scores are absent from the contract and selector. Opposite-phase and
unknown fields reject. A zero evaluation pass estimate cannot block funded work.

### Search and source contract

Declare 1–128 explicit `FundedCandidate` entries, each with a saved IS backtest or
optimization trial (`source`), `FundedProfile`, whole-MNQ `micros`, `simulation`,
`sampling`, `costs` and optional inclusive session `period`. Strategy identity
and parameters come from the saved source; arbitrary parameter overrides are
not accepted. Candidates can span strategies and jobs, sizes and both supported
local profiles. Every candidate remains in the table, including infeasible ones.
Duplicate definitions, OOS/undeclared sources, unsupported profiles/scaling and
incompatible dataset/research-window/execution/cost protocols reject the whole
request before simulation. No implicit candidate truncation or new job generation.

Use one common `horizon_calendar_days` per comparison: **90, 180 and 365** are
supported research horizons, and any whole value 1–3650 is accepted. Run a
separate comparison for each horizon; cash over different horizons is not a
comparable ranking objective. The common `calendar` contains explicit
`start_dates`, `coverage_end`, optional full-session `closures`,
`timezone: "America/Chicago"` and a version label. Count Monday–Friday dates
excluding declared closures, retaining sampled zero-trade source sessions.
These are declared scenarios, not verified exchange calendars. Calendar coverage
must include each cutoff. Date cohorts are equally weighted; each candidate's
simulation count must be divisible by cohort size.

Sampling reuses circular source-session blocks of 1, 5 or 10 days. Each path has
an addressed MT19937 stream seeded from `SeedSequence([seed, path_index])`;
termination cannot shift later paths' draws. Candidate order never changes the
result. Save path schedule hashes, source/risk/cost hashes, strategy/parameters,
research/access history and job origins, rule snapshots, local code hashes,
calendar, seeds, counts and assumptions. No paired-inference claim is made.

### Payout clock and native qualification

The reusable `funded_profiles.simulate_dated_funded_profile` calls the native
Python `FundedAccount.advance` transitions. Its existing weekday component and
legacy batch/annualized calculations are retained. No second funded rules
engine is introduced. Local Apex EOD and LucidFlex 50K models preserve provider
tiers/exposure caps, qualifying profit/days, consistency, withdrawal limits,
drawdown, daily loss pauses and termination. Apex retains five $250 qualifying
days, 50% cycle consistency, $2,100 safety buffer and its six-cap ladder;
Lucid retains five $150 qualifying days, no funded consistency, its minimum
request, 50%-of-equity cap, five-request limit and 90% trader share. Complete
versioned rules are saved in each candidate's provenance; these are local rule
snapshots, not newly verified provider terms. Apex inactivity uses its existing
21-session window. Lucid's native calendar inactivity check is also evaluated
on non-session dates without advancing its trading-session counter.

Events use **Chicago civil-date labels at daily resolution**. The horizon is
`[start_date, start_date + H)`. Age/day metrics are date differences, including
weekends, closures and DST dates; they are not precise intraday elapsed hours.
For example, an event on the start date has age zero. The supported payout policy
requests automatically when the native kernel qualifies; the same native event
makes the gross account deduction. Save separately:

1. Trading net profit and remaining account equity (never counted as cash).
2. Eligibility date under the native qualification rules.
3. Automatic payout request date.
4. Gross account deduction date/amount.
5. Trader entitlement, modeled receipt date and received cash.

`receipt_delay_calendar_days` is mandatory, even when zero, and supports 0–365.
Receipt date = request date + this fixed civil-day delay, including weekends.
The saved scenario assumes entitlements remain payable after breach, inactivity
or payout-limit closure. It does not model refusal, bank business days, payout
fees, forfeiture, tax or discretionary withdrawals. Eligibility/request/deduction
are simultaneous under this policy; delayed bank receipt does not block subsequent
native payout cycles. This timing is an **unverified settlement assumption**.
A receipt exactly on or after the exclusive cutoff remains pending and contributes
zero cash. Requests at/after cutoff are not simulated. Source commission/slippage
is adapted once into native net trading outcomes; never subtract it again from
trader receipts, and never charge acquisition/activation costs to this objective.

### Metrics, risk constraints and uncertainty

Reports include `expected_payouts` (alias of the objective), median/P10/P90 cash,
first/zero payout probabilities, conditional mean calendar days to first receipt,
breach probability, expected number of **received** payouts, pending entitlement,
gross deductions, inactivity and payout-limit probabilities, survival and full
path payout distributions/events. Quantiles use the inverse empirical CDF.
Successful payout-limit completion is termination, not breach.

The serialized metric names are fixed for format 5. Let `R_i` be cash received
strictly before cutoff in path `i`, `L_i` its observed lifetime, and `N` all starts:

| Field | Definition / unavailable state |
| --- | --- |
| `expected_funded_cash_payouts_within_horizon`, `expected_payouts` | `sum(R_i)/N`, including zero paths; null if any horizon is incomplete. Sole ranking objective. |
| `median_payouts`, `p10_payouts`, `p90_payouts` | Inverse empirical CDF at 0.5/0.1/0.9 over all `R_i`; null for incomplete horizons. |
| `probability_first_payout`, `probability_zero_payout` | Fraction with at least one received payout / with zero received cash. Null for incomplete horizons. |
| `expected_days_to_first_payout_conditional_on_payout` | Mean civil days to first receipt among paid paths only; null for no receipts or incomplete horizon. |
| `account_breach_probability` | Fraction with native `blown` outcome; null for incomplete horizon. |
| `expected_account_lifetime` | Mean `L_i` only if every account terminates and horizons are complete; otherwise null. |
| `restricted_mean_account_lifetime_calendar_days` | Mean observed lifetime, bounded by H; not an extrapolated tail mean. |
| `probability_surviving_to_horizon` | Fraction open at H (lifetime-censored); null for incomplete horizons. |
| `expected_number_of_payouts` | Mean number of received payouts, including zero starts; null for incomplete horizons. |
| `expected_pending_cash` | Mean trader entitlement due on/after cutoff; retained even if a horizon is incomplete. Not part of the objective. |
| `expected_gross_account_deductions` | Mean gross native payout deductions before cutoff, including requests still pending settlement. Not trader receipts. |
| `probability_inactivity`, `probability_payout_limit_completion` | Fractions with native `inactive` / `paid_all` outcomes; null for incomplete horizons. |

`status`, `censoring` and `uncertainty` accompany every row; full path records
separate complete horizon observations from open lifetime and unresolved guards.

`expected_account_lifetime` is the unrestricted mean only when every observed
account terminates. Otherwise it is `null`, with
`restricted_mean_account_lifetime_calendar_days = mean(min(T,H))` for complete
horizons and explicit lifetime-censored path counts. If a computational guard
stops observation before H, this same saved field is only the mean observed-time
lower bound, not an identified restricted lifetime expectation. An open account
at H is not falsely terminated;
its finite-horizon cash is complete. A stopped/incomplete horizon instead makes
cash estimates unresolved, exposes accrued cash lower bounds, and prevents a
winner. Exceptions abort publication rather than publish a partial optimum.
No-payout conditional first-time mean is `null`.

Optional `constraints` are `maximum_account_breach_probability`,
`minimum_probability_first_payout`, `minimum_p10_payouts` and
`maximum_position_size` (the requested target size, before native tier caps).
They are hard filters on empirical estimates; equality satisfies a boundary.
A violating candidate cannot win. These filters are not confidence-certified
risk limits. Rank feasible rows by descending mean receipts, then ascending
candidate SHA-256 for exact ties; evaluation metrics never break ties. If no row
is feasible or any horizon is unresolved, return no winner with explicit status.

Uncertainty includes within-start-stratum mean Monte Carlo SE, normal 95%
Bonferroni intervals across the **entire declared candidate family**, nominal
whole-path stratified bootstrap intervals for means/quantiles, and nominal Wilson
probability intervals for a single start stratum. Multi-start Wilson intervals
are withheld because strata are not identically distributed. Declare
`bootstrap_replicates` (100–2000; default 400), `bootstrap_seed` (default 137)
and `near_tie_cash` (default zero). Report near-ties within that cash tolerance
or with overlapping family mean intervals; missing intervals also flag a tie
uncertainty. Normal/bootstrap intervals can understate rare/unobserved tails.
They measure conditional simulation error, not future uncertainty, model/rule
accuracy, historical selection bias or simultaneous risk certification.
`certified_optimum` remains false; no precision-qualified recommendation is made.

Full captures are bounded: submission rejects an estimated capture above
100 MiB (5,000 bytes per funded path), or over 50 million path-calendar-day
iterations. The existing exact 128 MiB artifact cap still applies at sealing.
Requested counts are never silently reduced. The default 20,000 simulations is
supported for one candidate; larger searches must explicitly budget their counts.
`source_checks.json`, `phase_candidates.json`, `phase_metrics.csv/.json`,
`ranking.json`, `sampling.json`, `request.json`, `calculations.json`, captured
inputs and `report.json` are published in the normal ZIP. Every candidate source
is registered before queueing for deletion protection. Reopen/download never
resimulates; source, timing, horizon, constraints, seeds or local implementation
changes invalidate numerical reuse. No separate result store is created.

This section describes the original standalone P3 backend increment. The
subsequent campaign portal implements saved-trial UI and frozen OOS assessment.
New-grid generation, adaptive screening/confirmation, verified settlement
calendars and provider/external numerical qualification remain deferred. See the
[reproducible saved-product evidence](prop_simulation_review.md#standalone-funded-optimizer--2026-11-06).

## Standalone Evaluation optimizer — 2026-11-06

`prop.evaluation_optimization` implements `evaluation-optimization-empirical-iid-v1`.
Use `EvaluationCandidate`, `EvaluationSearch`, `check_search` and
`optimize_evaluation`, or send the serialized search to the **existing**
`POST /api/prop-analyses/check` and `POST /api/prop-analyses` endpoints with
`mode: "evaluation_optimization"`. No Evaluation UI is built in this increment.
The existing AnalysisStore worker, source membership, integrity checks, report
JSON/file routes and ZIP downloads persist the results. There is no second
database, funded simulation, scalar winner or annualized selection call.

Each explicit candidate contains a saved backtest/trial source, whole MNQ size,
versioned Evaluation profile/fees, source cost treatment, optional inclusive
research period, simulation/sample counts/seeds/block size and retry policy.
The strategy ID, full parameters, research declaration and source/risk hashes
come from the saved source, not unverified client overrides. Exact duplicate
candidates reject. All submitted candidates are checked and retained; an invalid
candidate rejects the whole request before queueing. Admission requires declared
IS, identical dataset/version, IS/OOS windows, sampled period and execution/cost
protocol. Different supported strategy IDs and optimization jobs are allowed.
The source navigation anchor has no scoring privilege. This does not generate
new strategy trials or freeze an OOS package.

**Supported initial model:** the local Apex 50K EOD rule version, automatic
activation eligibility after a declared delay, independent fresh-account retries,
unlimited available acquisition capital. LucidFlex is rejected in this dated
optimizer: its component inactivity clock assumes synthetic weekdays and cannot
yet be safely remapped to target calendar closures. The existing standalone
Lucid profile component and legacy calculations retain their earlier behavior.
Unsupported profile versions, scaling, variable-risk sizing, timezones, reset
discounts, approval conditions, budgets and finite retry policies reject rather
than receive invented behavior. Every retry buys a full new evaluation at the
same declared fee. Fees are scenario inputs, not current provider quotes.

### Attempt law and calendar

The extracted `simulate_evaluation_profile` supplies the existing local attempt
outcomes and their complete session durations. Its existing repeated-chain output
is saved as **legacy retained-block diagnostics only**. The new objective model
fits the uniform empirical joint law of `(outcome, duration)` from the independent
attempts, then draws IID pairs for each fresh retry. This preserves the dependence
between failure/success and duration; it does not carry an unfinished block into
the next retry. Within each original attempt, the component's circular session
block bootstrap remains unchanged. This fitted empirical renewal model is an
explicit approximation to the underlying bootstrap attempt distribution, not an
additional provider/account kernel. Increasing first-stage attempts and retry
chains addresses different Monte Carlo errors.

Declare an equal-weight `start_dates` cohort, `coverage_end`, full-session
`closures`, `timezone="America/Chicago"` and a calendar `version`. Open sessions
are Monday–Friday except declared closures. A missing-trade day never creates a
closure. All dates require canonical `YYYY-MM-DD` strings; compact/ISO-week
spellings reject so a closure cannot be silently missed. Calendar coverage must extend through every requested computational
guard date; incomplete coverage rejects. These are user-declared scenario
calendars, not verified exchange/settlement calendars; early closes are unsupported.
The cohort size must divide the chain count. Session dates follow the existing
CME Chicago source convention; calendar durations are **civil date differences**,
not UTC hours divided by 24, so DST does not remove a civil day.

For purchase date `s`, take the first open session on/after `s`. An attempt lasting
`d` sessions consumes that session and the following `d-1` open sessions. After
failure on session `f`, purchase the retry at `f + 1 + retry_delay_calendar_days`
and roll its first trading session forward to an opening. On a pass at `f`,
eligibility is `activation_delay_sessions` open sessions after `f`; pay the
activation fee there. The account is usable on the **next open session**.
`T = usable_session_date - original_purchase_date` includes all failed attempts,
initial weekend/closure waits, retry overhead, activation delay and the final
readiness wait. No funded trades or payouts enter this calculation.

For example, purchase Friday 2026-01-09, pass in one session, declare Monday
2026-01-12 closed and one activation-delay session: eligibility Tuesday,
readiness Wednesday 2026-01-14, `T=5` days. With fees 30 and 40 and full pass
probability, acquisition costs exactly 70. These are scenario assumptions.

### Metrics, censoring and uncertainty

Let `n` be original attempts, `k` passes, `p=k/n`, `e` the evaluation fee and
`a` activation fee. With no unresolved attempts, `p>0`, IID stationarity, identical
full-price retries, automatic eventual activation and unlimited capital:

- `pass_probability=p`; `pass_probability_ci` is the existing nominal 95% Wilson
  interval. Computationally censored attempts produce separate eventual-probability
  bounds `[k/n, (k+censored)/n]`; the Wilson interval then refers only to observed
  passes through the cutoff, not eventual success.
- `expected_attempts_per_funded=1/p` and `cost_per_funded=e/p+a`. The activation
  fee occurs exactly once, on successful eligibility. This formula is **not** a
  finite-budget, finite-horizon or correlated retained-block estimate.
- `expected_calendar_days_to_funded = sum(T_i)/N` over **all** requested chains,
  only when all resolve. Median and P90 use inverse empirical CDF, rank
  `ceil(q*N)`; never average only completed chains. Identified quantiles can be
  returned under censoring only when every unresolved lower bound is strictly
  beyond that quantile.
- `probability_funded_by_day_30/60 = count(T_i <= day)/N`, including equality.
  With unresolved possibilities return `null` plus `[known/N, (known+possible)/N]`.
  A censor time beyond a checkpoint rules out funding before that checkpoint.
- `funded_accounts_per_30_calendar_days=30/E[T]` is an inverse-duration renewal
  rate for the saved start mixture, **not** the expected count in a finite month
  or a simulation of repeatedly rolling that cohort forward.

`max_attempts` and `max_calendar_days` are computational guards on the unlimited
model, never economic stopping rules. A stopped chain retains observed days,
attempt purchases, exact accrued Decimal fee amounts, whether activation was
paid, pending activation/readiness and its termination reason. If any chain is
unresolved, both acquisition means and expected attempts are unavailable in this
report, even though the fitted-law fee identity may otherwise be computable.
Zero observed passes is unresolved, not proof of a zero future probability; all
acquisition means stay null. Apex provider expiry remains a failed attempt,
distinct from computational censoring. Mean accrued cost/observed time are sample
lower bounds. The restricted mean at the common calendar guard is available only
when no chain stopped at the attempt-count guard.

Pass SE is `sqrt(p*(1-p)/n)`. Cost delta-method SE is
`e*sqrt(p*(1-p)/n)/p^2`; its nominal CI reverses the Wilson bounds:
`[e/p_upper+a, e/p_lower+a]`. Calendar mean SE uses within-start sample variance:
`sqrt(sum(s_j^2/n_j))/m` for `m` equal-weight start strata; the reported normal CI
is `mean ± 1.96*SE`, clipped below at zero. A stratum with fewer than two paths
has unavailable SE. Checkpoint Wilson intervals are supplied for a single start
date only. Quantile and marginal-cost CIs are explicitly unavailable.
Calendar intervals condition on the fitted empirical attempt law and omit
first-stage fitting error. No paired/simultaneous uncertainty or statistically
robust dominance is claimed. Source sampling error, regime changes and rule
uncertainty are separate from Monte Carlo error. Small synthetic demonstrations
are arithmetic qualification, not precision-qualified forecasts.

### Pareto contract and saved artifacts

A strictly dominates B iff `C_A <= C_B` and `T_A <= T_B` with at least one strict
inequality. No tolerances, rounding or weighted scalar decide membership. All
finite resolved nondominated points return, including exact ties. Frontier order
is ascending cost, then time, then candidate SHA-256. Tied candidate hashes affect
presentation only. All rows report membership, estimated dominated-by IDs and
status and zero-based nondomination layer `pareto_rank`; unresolved rows have
`dominated=null` and `pareto_rank=null`, remain in `unresolved_candidates`
and are never ruled out by a fabricated successful-only mean. `winner=null`,
`certified_frontier=false` and `robust_dominated=null` distinguish estimated
dominance from statistical certification that this version does not establish.

For adjacent slow/fast points with `T_slow>T_fast`, report
`(C_fast-C_slow)/(T_slow-T_fast)` USD/day saved. Ties have a null ratio with a reason.
This exchange rate is not a mandatory lambda or recommendation. In particular,
points `(100,10),(160,8),(180,4)` all belong to the frontier even though the middle
point is not a unique optimum of a linear weighted objective; `(190,12)` is
dominated. Their adjacent exchange rates are 30 and 5 USD/day. Exact duplicate
objective values from distinct candidate configurations all remain frontier ties.

Format-4 phase reports capture `request.json`, `source_checks.json`,
`phase_candidates.json`, `phase_metrics.json/.csv`, `frontier.json`, `sampling.json`,
`calculations.json`, raw source trades/risk/explicit exports, `report.json` and the
normal `analysis.zip`. Calculations retain the full original attempt arrays,
component provenance and all dated chain observations. Candidate, calendar,
source/cost/risk, seed/count, profile and local implementation/kernel identities
participate in request reuse. Automatic funded-report administrative metadata
is captured for audit but excluded from candidate and numerical cache identity;
changing it cannot affect Evaluation tie ordering or reuse. Origin job/trial
references and OOS access history are captured without consulting their outcome
metrics. Missing or corrupt cached artifacts trigger a new analysis instead of
satisfying reuse. Every source is registered before queueing and
protected by the normal active-job deletion lock; all source hashes are checked
again before publication. Reordering inputs reuses the same result. Reads do not
run simulation. Maximum 128 declared candidates and existing report size bounds
apply; resource preflight rejects excessive requested path capture without
silently lowering counts. Existing formats and annualized reports are preserved.

See [saved evidence and exact reproduction](prop_simulation_review.md#standalone-evaluation-optimizer--2026-11-06).

## Independent simulation component APIs — 2026-11-05

Use `evaluation_profiles.simulate_evaluation_profile` for one saved evaluation
source/profile/whole MNQ size and `funded_profiles.simulate_funded_profile` for
one saved funded source/profile/size and `horizon_weekdays`. Both reuse the local
provider kernels, reconciled costs/risk and fixed-path eligibility checks. They
can run separately, including funded execution when no evaluation passes.
Frozen contracts and `rule_version` are in `prop.phase_profiles`; the complete
[interface and responsibility table](phase_optimization_plan.md#implemented-precursor-independent-simulation-profiles)
documents arguments, outputs and limits.

For example, with an existing `RunStore` named `runs` and a saved source ID:

```python
from alphaquest.prop.phase_profiles import (
    SavedTradeSource, EvaluationProfile, FundedProfile, SimulationConfig,
    EvaluationSamplingConfig, SourceCosts, rule_version,
)
from alphaquest.prop.evaluation_profiles import simulate_evaluation_profile
from alphaquest.prop.funded_profiles import simulate_funded_profile

source = SavedTradeSource(source_id)  # Optional explicit matched export path.
version = rule_version('apex-50k-eod')
evaluation = simulate_evaluation_profile(
    runs, source, EvaluationProfile('apex-50k-eod', version, '49', '129'),
    micros=10, simulation=SimulationConfig(),
    sampling=EvaluationSamplingConfig(), costs=SourceCosts(mode='source'),
)
funded = simulate_funded_profile(
    runs, source, FundedProfile('apex-50k-eod', version), micros=3,
    horizon_weekdays=30, simulation=SimulationConfig(), costs=SourceCosts(mode='source'),
)
```

The two calls may use entirely different saved sources and research periods;
neither result is an input to the other. Fees in this example are saved scenario
inputs, not a current provider quote. `ResearchPeriod` uses inclusive CME session
dates inside the saved backtest period; omitting it uses that period without a
new split. Sources outside existing fixed-path/risk eligibility reject.

Evaluation returns the existing fee/pass-rate acquisition-cost estimator and
repeated-chain replacement duration/SE. **Replacement duration is trading
weekdays, not calendar days.** Zero sampled passes stays unresolved; a numerical
chain guard leaves timing unavailable. Apex's 21-weekday provider expiry and
Lucid computational censoring remain distinct. Funded returns payout mean/SE,
median/P10, zero-payout/breach/inactivity/survival diagnostics and path records.
Its horizon cap is inclusive in weekdays. Open accounts retain lifetime censoring;
unrestricted lifetime is unavailable even with complete horizon observations.
Trader payout and gross account deduction are distinct. Bank settlement and
pending bank receipts are not modeled; the kernel's payout-time convention is
explicit in provenance. These are component estimates, not independent optimizer
reports or verified future cash outcomes.

Legacy joint sizing delegates through compatibility wrappers with unchanged
counts/seeds, formulas, field meanings and report format. No portal route or
selector is added. See [actual saved evidence and reproduction](prop_simulation_review.md#independent-phase-component-extraction--2026-11-05).

## Selectable analysis methods — 2026-11-05

New portal configurations offer **Annualized sizing · existing single source**
and **Budgeted cash ledger · one unfunded slot**. Standalone **Dated phase
lifecycle · fixed sizes** is no longer selectable. Its transition calculations
remain available to the budgeted method, and earlier lifecycle reports and
downloads remain readable without recalculation or mutation.

An earlier lifecycle report offers **Configure budgeted analysis**. This copies
its account, phase sources, fixed targets and other saved settings into a new
budgeted configuration. Enter the monthly cap, observed dates and explicit timing
assumptions before checking/running; these inputs are not inferred from the old
report. No new analysis is submitted just by opening the form. Annualized remains
the default for fresh configurations. Legacy dated API support remains for
compatibility and development qualification.

The milestone-1 section below describes the earlier standalone workflow and its
saved evidence; use the budgeted method for new fixed-phase portal analyses.


## Portfolio milestone 2: exact cash ledger and monthly acquisition budget — 2026-11-04

From a saved backtest choose **Configure prop analysis → Budgeted cash ledger ·
one unfunded slot**. Keep the milestone-1 evaluation/funded source selections and
fixed MNQ targets. Set the monthly evaluation-plus-activation fee cap, saved prices,
budget timezone, start date and inclusive horizon end. The timezone dropdown
starts with Chicago (`America/Chicago`) and offers New York, Singapore and UTC.
A different valid timezone copied from a saved report remains selected. The visible
selection is saved explicitly and sets calendar-month boundaries.

The routine form keeps the account, method, fixed sizes, budget, dates and saved
fees visible. **Use full shared observed period** fills both dates from the
selected sources without overwriting them when a source changes later. Choose
receipt timing (same day, 5 or 30 calendar days) and the immediate-payment/seven-day
activation assumption from dropdowns; choosing a preset saves its explicit
unverified modeling description. No timing assumption is silently preselected.
Choose **Custom** to enter other timing or retain a copied report's exact values.
Optional source exports/search, commissions, risk overrides and JSON settings are
in expandable sections. Missing routine inputs are highlighted beside **Check
source** and focus the affected field before an API request. Fee help shows the
evaluation-plus-activation allowance needed, including when the cap blocks buying.
Source-check summaries keep detailed cost/risk/settings snapshots expandable.

Source checks require
the entire horizon inside the common observed session-date window. This is a
chronological observed scenario, without invented future trading or resampling.
Then **Check source → Run analysis** saves the ordinary AnalysisStore report.
New model IDs append `-cash-ledger-v1`; annualized and dated-phase reports retain
their earlier meanings. Saved reports/evidence are never rewritten.

The slot starts empty, without prior spending. At budget-local midnight the
scheduler attempts a purchase if the slot is empty. Its first partial month has
the full monthly cap. Subsequent months run from local calendar-month midnight to
the next local calendar-month midnight, converted to UTC with IANA/DST rules.
Purchase transactions pay the saved evaluation fee immediately. Replacements
wait until the next daily scheduler tick after a failed/expired evaluation,
activation expiry or funded-account closure. There is no same-session restart,
expected-cost purchase, assumed funding probability, renewal charge or refund.

The initial **activation-priority** policy requires enough available allowance
for **evaluation fee + full activation fee** before purchase. It immediately
reserves the activation fee, including while evaluation is unresolved. Reservations
reduce purchasing availability but are not expenses. Failed attempts release their
reservation. Passing creates a dated activation obligation and saved inclusive
deadline. Eligibility uses milestone-1 minimum/extended weekday wait. Payment occurs
at eligibility plus the saved calendar-day payment delay. It releases the
reservation and pays the activation fee from that month's remaining cap. Payment
at the deadline is accepted; an unpaid obligation expires at the deadline, releases
its reservation, and closes without a refund. Delays/deadlines must be explicitly
described as **unverified saved modeling assumptions**, not provider-rule claims.
Lucid retains its zero activation fee and existing trading rules.

At month reset, close the old month's paid-fee and unused-allowance totals.
Release the old reservation; the unspent allowance, including any unspent earmark,
expires in full. Start the new cap at zero spending, then re-reserve any outstanding
evaluation's potential activation fee or passed account's unpaid activation fee
**against the new cap before purchases**. Do not extend its original eligibility,
payment date or deadline. This preserves the obligation, never the old allowance.
The cap is fixed across months in this milestone, so every admitted obligation
fits the new cap. A new purchase that cannot cover its fee and reservation is
logged blocked/deferred; retry at subsequent daily scheduler ticks. Payouts never
change this test or expand spending permission. Every ledger row enforces
`0 <= paid_fees <= cap` and `0 <= reservations <= cap - paid_fees` with Decimal
USD-cent fee arithmetic; violated invariants prevent publication.

The existing firm kernels still own evaluation targets/consistency, intratrade
breaches versus daily stops, funded tiers/inactivity, requests and account
deductions. The financial timeline dates their daily transitions at modeled
16:00 Chicago session close. Funded observations must be in subsequent sessions
after eligibility and must open after actual activation payment. No carried
source position is inherited. Source net trading costs are adapted once by the
existing commission reconciliation and never charged again as cash fees.

A payout creates separate **request** and **gross account deduction** rows with
zero trader-cash delta. The funded kernel already deducted the gross amount;
the cash ledger does not deduct it again. Trader receipt is a distinct row at
request time plus saved calendar days at the same budget-local wall time (DST
aware). Require a nonempty saved payout-timing assumption even for zero-day
receipt. Modeled receipts round trader entitlement to USD cents with Decimal
`ROUND_HALF_UP`; raw entitlement and gross account deduction retain kernel
precision. No bank settlement is verified. Pending requests are assumed payable
under this scenario even after the account closes; cancellation/reversal and
provider approval workflows are not modeled. Dates/amounts after the horizon are
conditional obligations under that assumption, never claimed actual receipts.

The horizon is `[start-local-midnight, midnight-after-inclusive-end)`. Received
cash within it minus **actual paid evaluation and activation fees** is net cash.
The payout/evaluation-fee multiple is **aggregate received trader cash / aggregate
paid evaluation fees**, never the mean of account/path ratios; a zero denominator
is unavailable (`null`). Activation fees, monthly paid spending, remaining and
reserved allowance, pending passed-account fees, potential evaluation activation
fees and pending trader receipts remain separate. Evaluation profit, nominal
account equity and unused budget are not trader cash. Open accounts and pending
obligations stay open at the horizon; there is no terminal value or liquidation.

The durable report includes readable cash totals, monthly spending, account
states/deadlines, pending settlements, fixed source snapshots and the trading
trace. Download `cash_ledger.csv/.json`, `monthly_ledger.csv/.json`, `accounts.csv/
.json`, `pending_receipts.csv/.json`, transition traces and the ordinary report
ZIP. Settings, both original source/risk inputs and commission reconciliations
remain in that ZIP. Reopening reads saved bytes without submitting a calculation.
The implementation is `alphaquest/prop/cash_ledger.py`, dispatched through the
existing phase source checks and report publication; no separate API/page/store.

The configuration API uses the existing `/api/prop-analyses/check` and
`/api/prop-analyses` endpoints. In settings, use `ANALYSIS_MODE=budgeted_lifecycle`,
`SLOTS=1`, existing phase/source/price/commission choices, and the explicit fields
`MONTHLY_CAP`, `BUDGET_TIMEZONE`, `START_DATE`, `HORIZON_END`,
`PAYOUT_RECEIPT_DAYS`, `PAYOUT_TIMING_ASSUMPTION`, `ACTIVATION_DEADLINE_DAYS`,
`ACTIVATION_PAYMENT_DELAY_DAYS`, `ACTIVATION_TIMING_ASSUMPTION`, plus optional
`FEE_OVERRIDE_NOTE`. Money inputs must be nonnegative USD-cent strings; cap and
prices are at most $100,000. Receipt/payment delays accept 0–366 calendar days,
deadline 1–366; horizon at most 7,300 days inside observed coverage. Blank receipt,
deadline, timezone, dates or required descriptions reject. Cash fields cannot
silently select an annualized calculation; multiple slots reject.

The [milestone-2 review](prop_simulation_review.md#portfolio-milestone-2--cash-ledger-and-budget--2026-11-04)
contains actual saved synthetic report IDs, independent $100 ledger rows, expiry,
reset and late-receipt observations, commands and validation evidence. Synthetic
$30/$40 prices are explicit fee overrides, not current provider prices. This
milestone makes no new external/provider numerical parity claim. Synchronized
sampling/search, multiple separate/shared accounts and frozen OOS allocation
recommendations remain milestones 3–5.

## Portfolio milestone 1: separate phase sources and dated lifecycle — 2026-11-04

The accepted [five-milestone plan](prop_portfolio_plan.md) starts with a usable
fixed-selection observed replay. From a completed saved backtest (including an
optimization trial), open **Configure prop analysis** and choose **Dated phase
lifecycle · fixed sizes**. That opened backtest is the evaluation selection.
Choose **Same as evaluation source** or another saved funded backtest, whose
strategy/parameters remain its own immutable snapshot. Search the loaded sources
or load more. Choose separate whole-MNQ evaluation/funded targets and optionally
extend the activation wait. **Check source → Run analysis** publishes through the
existing AnalysisStore and report routes. Annualized sizing remains the default
single-source mode, with its existing training/renewal assumptions.

New dated models append `-dated-phases-v1` to the current Apex/Lucid model IDs.
They replay one evaluation and its subsequent funded account, without automatic
repurchase, simulated portfolio allocations, slot multiplication or annualization.
Account/risk arithmetic is inherited from the existing firm models; the Python
evaluation session reference is shared with dated replay. Compiled sampling keeps
an equivalent unboxed hot loop, qualified against that reference. Existing funded
account transitions supply tiers, daily stops, first account breach, qualifying
days, inactivity, withdrawal deductions and trader payout amounts.

Both sources independently reconcile identities, timestamps, fixed quantities,
net costs and complete captured OHLC or reconciled measured adverse coverage.
Close-only inputs and risk-budget/account-dependent source sizing reject. Supported
fixed-quantity paths are the registered consecutive-green and VWAP strategies;
VWAP must have `use_vol_sizing=false`. NQ/MNQ and USD 20/2 point values must be
identified. Use automatic instrument detection for a mixed NQ/MNQ pair. Commission
settings apply to both phases; each source's own recorded commission is replaced
once, preserving its slippage, or explicit source-cost mode retains those costs.
Linear exposure scaling does not re-execute size-dependent fills/liquidity.

Sources must be in the same declared research phase: IS with IS, or explicitly
executed OOS with OOS. The shared window is the intersection of saved observed UTC
periods inside both declarations. Complete trades outside that window are excluded
with counts; carried positions are excluded rather than inherited. Both sources
must be intraday flat. Chicago CME session-ending dates, UTC reconciliation and
explicit source calendar snapshots are checked; conflicting explicit calendars
reject. The existing weekday clock retains zero-trade weekdays including holidays.
It is a declared model clock, not a new exchange-holiday/settlement service.

Evaluation starts at the shared window's first session. Apex passes at its target
trade, fails at first account-floor breach or expires at 21 weekdays. Lucid checks
its target/40% consistency at close, uses actual elapsed calendar days for activity
and has no provider evaluation deadline. End-of-history open evaluations are
**unresolved**, never failed or restarted. A daily stop ends that session without
itself becoming an account breach. Observed adverse gaps/cost jumps can cross both
floors and breach before a recovering profitable close.

After passing, Apex's default activation wait is one additional weekday; Lucid's
is zero. A configured wait may extend, never shorten, that model minimum. Eligibility
is recorded at session close after that wait. Funded trading starts in the following
session, on the funded source's subsequent observations, at initial account equity
zero. No history is restarted, no passing-session funded trade is consumed and no
already-open source position transfers. If observations end during the wait, the
outcome is activation pending. Eligibility is a local model assumption, not evidence
of actual provider approval. Funded targets stay fixed while mandatory prior-close
provider tiers constrain actual orders.

The durable report shows each phase's metrics, activation dates, source/strategy/
parameter snapshots, daily-stop versus account-breach outcomes and a downloadable
`transition_trace.csv` / `.json`. Per-phase adapted trades, original source/risk
inputs, settings, commission reconciliations and calculation hashes are captured
in the normal report ZIP. Both source IDs participate in request identity,
catalogue membership and queued/running source/activity deletion protection.
Reopening reads saved outputs without calculation. Earlier reports are unchanged.

Payout dates represent modeled requests/account deductions and trader entitlements,
not bank receipts. No expected cash-by-deadline or budgeted forecast is claimed:
the exact ledger/cap, synchronized separate/shared-account optimization and frozen
OOS recommendations are milestones 2–5. No additional Bridge/provider parity is
claimed. See the milestone-1 review for actual saved demonstration IDs, independent
values, source boundaries, checks and exact reopening/reproduction commands.

## Refresh every unavailable prop account in a saved batch — 2026-11-03

Completed batch results now offer **Refresh all unavailable prop results** for
both Apex and Lucid. Each account is checked against its original source and
saved settings, including the companion export/timezone. Verified current
analyses are reused; remaining requests run through the normal AnalysisStore
worker. Already available values are retained. No strategy bars or OOS backtests
are run, and genuinely unavailable calculations remain N/A with their reason.

The existing append-only `optimization_prop_links` index now keys links by trial
**and account**. Its migration labels pre-existing links as Lucid without
changing their payloads. Independent Apex/Lucid revisions cannot overwrite one
another. The table, report links, status, exact sorting and CSV use these linked
results. **Original results CSV** / `prop_revision=0` retains the original values;
downloads pin one revision across both accounts. Ordinary reads never queue or
repair work. The existing Lucid-only action/API remains available.

The combined API is `GET/POST /api/backtests/batches/{id}/prop-refresh` (also
available under `/api/optimizations/{id}/prop-refresh`). POST checks/submits only
unavailable accounts. Duplicate requests reuse pending work, publication updates
the account-specific link, and startup reconciles pending links without new
calculation. Active analyses retain normal source/activity-deletion protection.
All calculations and downloads stay in the existing report catalogue; original
trials, source backtests and earlier reports remain immutable. Apex CSV provenance
now includes model version and original analysis ID alongside the existing IDs,
statuses and reasons. See `prop_simulation_review.md` for the actual rerun audit
and reproduction steps.

## Candidate-specific acquisition bounds — 2026-11-03

Current models: `alphaquest-apex50k-eod-v6-acquisition-bounds` and
`alphaquest-lucidflex50k-eod-v4-acquisition-bounds`. A failed acquisition-time
calibration no longer vetoes the whole joint search automatically. The account
rules, prices, source adaptation, deadlines and funding-attempt guard are unchanged.

For an unresolved acquisition size with observed screening passes, refine its
pass probability on 20,000 training evaluations at seed 46. Reuse the existing
failed-chain diagnosis; do not restart that chain, invent a replacement delay,
or average only chains that completed. The screening count remains separately
recorded, including when the independent refined sample has zero passes.

Bound the pass probability using a one-sided exact binomial upper limit,
with Bonferroni allocation `0.05 / number_of_evaluation_sizes`. This supplies
95% simultaneous coverage over those Monte Carlo pass-probability estimates,
conditional on the source/model, not on future performance or provider rules.
Censored individual evaluations count as possible passes in this bound.
The lower acquisition-cost bound uses the same fee/probability formula as the
objective. The whole funded payout ladder bounds receipts. At least one funded
session and one evaluation session, plus the configured activation days, bound
cycle duration below. An unknown duration with a nonpositive net numerator has
annualized upper bound zero; no negative truncated rate is substituted.

Exclude an unresolved pair only when its optimistic annualized bound is strictly
below the best complete pair. Preserve its missing acquisition mean and record
the bound, confidence method, refined/screening counts, original calibration
failure and exclusion reason in the normal CSV/JSON/ZIP. Affordable unresolved
candidates, censored individual evaluations and zero/negative comparisons that
could change the winner still prevent selection. Existing funded-lifetime
censoring protections remain in force.

Sizing shows an **Uncompetitive evaluation sizes excluded** table for excluded
sizes. Pair rows distinguish an excluded bound from a complete annualized
estimate. Remaining acquisition blockers identify their evaluation sizes and
can be inspected in the same Sizing view and provenance download. New model
and implementation identities invalidate old result/calculation reuse.

Saved batch snapshots and earlier reports remain immutable. To update an old
result, open that prop report → **Configure new analysis → Check source → Run
analysis**. This creates/reuses a current prop analysis on its existing source;
it does not run strategy bars or rewrite the batch's original automatic result.
See `prop_simulation_review.md` for the recovered trial-4 result, the genuinely
ambiguous trial-21 boundary, independent values and exact reproduction commands.

## Joint evaluation/funded sizing — 2026-11-02

This increment introduced `alphaquest-apex50k-eod-v5-joint-sizing` and
`alphaquest-lucidflex50k-eod-v3-joint-sizing`. Both choose evaluation and funded
sizes **together**, maximizing training long-run annualized net per slot:

`261 * (expected funded trader receipts - expected acquisition cost) /
(expected funded lifetime weekdays + expected acquisition weekdays)`.

Every permitted/user-capped whole-MNQ evaluation size is paired with every
funded target size (40 × 40 by default). Funded orders retain prior-close
scaling limits. Acquisition fees and timing include failed evaluation attempts;
Lucid adds zero activation weekdays and Apex adds one. All candidates share the
saved source adaptation, commissions, rules, block size and chronological split.
The existing 40% Lucid consistency profile is unchanged; this does not switch
to the investigated Bridge's 52% profile or claim full Bridge/provider parity.

Independent stage profiles avoid a full resimulation for each pair. Screening
uses 3,000 paths per size, with 20,000 repeated funding chains for each eligible
evaluation size. Statistically close training contenders are refined on 20,000
paths at seed 46; the matrix is reconsidered until no close contender has an
unrefined component. Exact zero-standard-error ties use the documented tie-break
without simulating identical ties solely to resolve grid order. Exact score ties
favor lower acquisition cost, smaller funded size, then smaller evaluation size.
Monte Carlo standard errors use the delta method, including funded receipt/
lifetime covariance and acquisition-cost/time uncertainty. They describe
simulation uncertainty conditional on the source sample, not future returns.

Funded lifetime calculations now use a 20,000-weekday computational guard.
Accounts still open have unknown terminal lifetime; their remaining ladder
bounds potential receipts. Such a profile cannot receive a complete lifetime
score. A selected pair is withheld if an unresolved acquisition or a funded
upper bound could change the winner. A rigorous zero-receipt bound applies when
even taking all positive source trades and skipping every loss cannot reach a
qualifying-day profit: the profile explicitly records zero simulated paths,
the requested count, an unknown lifetime and its analytical method. No unrun
paths or invented terminal outcomes are reported. A fully qualified nonpositive
winner remains nonpositive, with a notice that no positive score was found.

Both sizes and training acquisition economics freeze before any holdout runs.
Holdout evaluates the frozen pair on 20,000 evaluation, lifetime and first-year
paths. An incomplete holdout lifetime/acquisition estimate makes its annualized
rate unavailable without changing the training choice. The first-year funded
receipt distribution remains a separate, conditional-on-funded metric; this
objective is not cash in the first 261 days starting unfunded. Historical replay
retains the existing acquired-funded-account start, shared-slot trades, expected
acquisition fees and rounded-up mean replacement delay research assumptions.

Use the existing backtest → Configure prop analysis → Check source → Run
analysis → Sizing workflow. Sizing shows the chosen pair, training and holdout
annualized rates, uncertainty and a comparison filter for each evaluation size.
`joint_sizing.csv` saves every pair; `joint_sizing.json` includes stage profiles,
screening scores, refinement rounds, actual counts, seeds, censoring bounds and
tie-break. Both are normal AnalysisStore report files included in the existing
ZIP; there is no second calculation/report store. New model and implementation
identities invalidate old calculation reuse, including batch-refresh numerical
checks. Earlier reports/backtests remain immutable and carry an earlier-model
notice; explicitly configure a new analysis to calculate the joint model.

The dated investigation and earlier increment descriptions below preserve their
historical results. Their pass-first selection and 2,000-session funded lifetime
descriptions are superseded by this section. Actual-source and independently
derived synthetic demonstrations are in `docs/prop_simulation_review.md`.

## Lucid evaluation discrepancy investigation — 2026-11-02

The saved AQ 75.145% / $107.1262 / 88.69665-weekday result and the supplied
Bridge 37.84% / $212.7378 / 33.67555-weekday result use different evaluation
selection objectives, sizes, consistency thresholds, commissions, split
boundaries and funded-start timing conventions. Local AQ calculations reproduce
the three supplied Bridge metrics exactly when those conditions are aligned.
This is qualification of these evaluation metrics for this source, not full
funded-account or provider-rule parity. Production defaults and saved reports
are unchanged. See the dated investigation in `prop_simulation_review.md` for
the controlled comparison, independent checks and existing-product journey.

## Refresh unavailable Lucid results in a saved batch — 2026-11-01

Open a completed backtest batch and choose **Refresh unavailable Lucid results**.
The action retains every saved strategy backtest and Apex result. It checks
each unavailable trial against its original Lucid settings and source, reuses
a verified current-model analysis when possible, and otherwise submits only
Lucid analysis through the normal local analysis catalogue/worker. It does not
execute strategy bars, create new backtests or consume an OOS backtest slot.

The existing results table shows pending work, updated result links and the
reason for any remaining N/A. Progress survives reload. Clicking again reuses
pending requests; failed publication can be retried. Source incompatibility,
missing/corrupt inputs and genuine unresolved evaluation paths remain explicit
rejections/unavailable results, never fabricated numbers.

An append-only link index in the existing backtest catalogue joins verified
analyses to their original trial. It contains references/provenance and the
saved historical-net value needed for exact sorting; all calculations and
downloads remain in the existing AnalysisStore. Original trial JSON and report
files are immutable. The table and Results CSV use the same linked values and
analysis IDs. **Original results CSV** / `prop_revision=0` retrieves the original
trial snapshot. CSV exports pin the link revision so background publication
cannot change their ordering midway through a download. Ordinary GETs never
launch calculations or repair/write link state.

Both request and pure-calculation reuse keys include the explicit model version.
Cached calculations must also declare the expected model version. A previously
calculated report is reused only after source, settings, model, numerical source
hashes, native kernel and artifact integrity checks. Fresh prior calculations
can be reused across storage/UI changes without recomputing them; reports that
used an older calculation cache additionally require the matching cache source.
Current report/calculation version agreement is always required.

See `docs/prop_simulation_review.md` for the saved-batch demonstration and
independent cash expectations. This increment links/recalculates Lucid results;
it does not change account rules, sampling, sizing or provider-parity status.

## Lucid funding-time continuation — 2026-10-31

This earlier increment introduced `alphaquest-lucidflex50k-eod-v2-funding-continuation`;
the current joint model is specified above.
The earlier model aborted the entire repeated-funding calibration when one
evaluation was still open at 2,000 sessions. A high evaluation pass rate could
therefore coexist with unavailable funded sizing and historical net.

Open evaluation paths now continue beyond 2,000 sessions with their existing
balance, high-water mark, consistency, activity clock and bootstrap position.
The computational limit is 20,000 sessions **per evaluation attempt**; it is not
a provider deadline. Remaining open paths still prevent an unqualified funding
time estimate. No unresolved path is discarded, counted as a failed attempt,
restarted at session 2,000 or replaced by a fixed acquisition delay. The separate
2,000-session funded-account lifetime horizon remains unchanged.

Evaluation and funding-chain diagnostics record the initial/maximum horizons,
continued-path counts, longest attempt and remaining censored paths. They are
visible in the Evaluation view and durable report/calibration downloads.
Training-only selection, standard 3,000/20,000 simulation counts, cash rules,
source reconciliation and conservative OHLC risk semantics remain in force.

To update a saved earlier Lucid analysis, open **Configure new analysis** on
that report, **Check source**, then **Run analysis**. The form copies its account
model and saved settings. The existing saved trades are reused; no strategy
backtest or parameter sweep is executed. A new durable analysis is published in
the existing catalogue. Earlier reports, source backtests, batch trial snapshots,
datasets and OOS budgets remain unchanged. Existing batch snapshots continue to
reference their original automatic analysis; use the explicit batch refresh
action above to link a verified corrected report into the table. A manually
recalculated report is also available through its source's saved prop analyses
and its own durable URL.

This corrects computational truncation, without changing the dated provider
contract or claiming new provider-rule parity. See the corresponding journey,
actual-source result and independent boundary arithmetic in
`docs/prop_simulation_review.md`.

## Automatic LucidFlex 50K alongside Apex — 2026-10-29

New backtests, CLI runs and optimisation trials now calculate **both** the
existing Apex 50K EOD analysis and a separate **LucidFlex 50K** analysis. IS runs
still use IS only; OOS backtesting remains a manual selection from completed IS.
Both reports use the existing `/api/prop-analyses` catalogue, report format,
configuration/source-check flow and downloads. There is no second result store.
The existing `automatic_prop_analysis` remains the Apex result for compatibility;
its `companions` contains the Lucid descriptor and saved analysis ID. Existing
reports are not rewritten or automatically backfilled. Backtest summary cards
and optimisation columns distinguish the two Historical net values; they are
never added together or presented as comparable single-account payouts.

Lucid defaults use the user's **$80.50 evaluation purchase price**, zero
activation fee, five slots, standard 40% evaluation consistency and DLL on.
This price is an editable user-supplied input, not a guaranteed checkout quote.
The provider's current customization and consistency pages supersede the older
evaluation overview which still lists 50%. The 50% add-on/cushion is outside
this version. DLL off is supported through the same configuration form.

The dated local contract is `alphaquest/prop/lucid_rules.py`, included as
`provider_rules.json` in each Lucid report/ZIP. Rules checked on 2026-10-29:

- Evaluation: $3,000 target, $2,000 EOD trailing maximum loss, 40% maximum
  largest-day share assessed at session close, 40 MNQ maximum, no provider time
  limit, and no activation charge. Replacement timing adds zero extra activation
  weekdays; funded sampling begins on a subsequent session.
- Drawdown: the floor follows highest session-close equity and locks at +$100
  once the trail reaches that level. A funded payout request forces that lock
  immediately, including requests made before the normal trail lock. Touching
  the floor breaches the account intratrade, even if the source trade later wins.
  Captured adverse frontiers, opening gaps and cost jumps retain their normal
  source reconciliation and conservative held-OHLC interpretation.
- DLL on: a $1,200 soft daily stop in both phases, with observed jumps able to
  overshoot it and breach the account. **Holding $1,200 fixed above the trail is
  an explicit assumption**: the official Flex help pages confirm soft breach and
  phase coverage but do not specify the above-trail adjustment. This uncertainty
  is visible on the report and in its contract; no complete provider parity is
  claimed. DLL off has no daily stop.
- Funded: session-start limits of 20 / 30 / 40 MNQ at profit balances below
  $1,000 / from $1,000 / from $2,000; withdrawals can reduce the next tier. Five
  distinct $150+ days are required for each payout cycle, together with positive
  cycle profit. There is no funded consistency requirement or retained buffer.
  The gross request is 50% of total account profit, capped at $2,000 and at least
  $500. The account loses the **full gross amount**; the trader receives **90%**.
  Counters reset after each request. Five payouts end the simulated funded stage.
- DLL-on requests occur at the first eligible observed completed-trade mark
  within 18:00–15:45 New York time, then stop that session. If no intraday request
  is made, eligibility is checked at session close. DLL-off requests occur at session close. Unobserved
  intratrade request opportunities and bank settlement delays are not invented.
  Payouts are dated at request/deduction. Discretionary early live transitions,
  live P&L and live bonuses are outside scope; five payouts are a simulated-stage
  maximum, not a guaranteed entitlement to five actual payouts.
- Sources must already respect the regular 16:45 New York flatten time and
  18:00 session reopen. Later source exits are incompatible because the earlier
  liquidation price is unavailable; they are not account failures. Source hours
  use Eastern civil time including DST. Holiday early closes require correctly
  session-filtered source data and are not independently validated by this adapter.
- Inactivity uses 30 **calendar** days without an observed closed trade result
  of at least $1 in absolute value. Losing trades can satisfy activity. Bootstrap
  clocks start on Monday; historical replay uses actual elapsed calendar days.
- Published Lucid NQ/MNQ commissions are $1.75/$0.50 per contract **per side**.
  Source commission is replaced once; source slippage and original source values
  remain. The existing unidentified-instrument notice and explicit NQ/MNQ source
  selection apply. No Apex commission default is silently used for Lucid.

Monte Carlo retains 3,000 paths per permitted sizing point and 20,000-path final
evaluation, funding-chain, lifetime and first-year batches. Incomplete evaluation
paths continue past 2,000 weekdays up to a 20,000-weekday computational guard,
where they are **censored**, rather than provider deadline failures. Censored funding chains make replacement timing and
funded sizing unavailable; no probability or delay fallback is substituted.
Evaluation size, acquisition cost/time and funded size are fitted on training
only; holdout cannot choose or rescore them. Historical replay and annual-per-slot
ranking retain the existing research renewal convention (including an acquired
funded account at the start), not a simulation of live accounts after payout five.

The local Lucid kernel has an optional compiled build using the same source as
its Python reference (`.venv/bin/python setup.py build_ext --inplace`). Random
bounded integers are prefetched in batches and consumed in scalar MT19937 order;
every requested account path is simulated. Step-ledger tests verify both state
and random draw consumption. Both report fingerprints participate in backtest
and optimisation reuse. Publication failure rolls back both newly published
analyses instead of leaving a partially saved backtest.

Primary sources: [customization](https://support.lucidtrading.com/en/articles/16226050-lucidflex-customization),
[consistency](https://support.lucidtrading.com/en/articles/12945805-lucidflex-consistency-percentage),
[evaluation](https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account),
[drawdown](https://support.lucidtrading.com/en/articles/12945815-lucidflex-drawdown),
[scaling](https://support.lucidtrading.com/en/articles/12945808-lucidflex-scaling-plan),
[payouts](https://support.lucidtrading.com/en/articles/12945796-lucidflex-payouts),
[inactivity](https://support.lucidtrading.com/en/articles/11404632-inactivity-policy),
[commissions](https://support.lucidtrading.com/en/articles/11508978-approved-products-and-commissions),
[live boundary](https://support.lucidtrading.com/en/articles/16558826-new-live-structure).
Regular hours and account caps: [allowed trading times](https://support.lucidtrading.com/en/articles/11404729-allowed-trading-times),
[account limits](https://support.lucidtrading.com/en/articles/11404617-maximum-number-of-accounts).
See `prop_simulation_review.md` for saved product evidence and independent values.

The following Apex contract and historical records retain their original scope.

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
  is tested (1–40 by default), then scored jointly with funded size using the
  annualized objective above. Pass probability alone does not select size.
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
- Counts: 3,000 per screening point, 20,000-path close-contender refinement,
  20,000 training funding chains per eligible evaluation size,
  20,000 final evaluations, 20,000 final funded
  lifetime accounts and 20,000 independent first-year accounts. Lifetime guard
  is 20,000 weekdays; first year is 261. Analytical zero-receipt bounds explicitly
  record zero simulated paths. Independent horizons consume draws
  differently, so first-year and lifetime probabilities need not be monotone.
- Economics: fit every eligible evaluation acquisition profile on training only,
  with cost evaluation_price / training_pass_rate + activation_fee.
  Close contenders' pass estimates are refined on 20,000 training paths; replacement time is
  the mean of 20,000 repeated training evaluation chains including failed attempts
  and one activation day. Freeze these inputs before any holdout calculation.
  Rank all evaluation/funded pairs by 261 * (mean training lifetime payout - training acquisition
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

Everything in this notebook specification through **Parity qualification** records
the former notebook model. Its modules remain active in demo/parity tests, while
saved format-1 reports use their historical reader. Later dated local-model
updates below that qualification retain their own versioned scope. See the
[current ownership map](architecture.md#final-module-ownership-and-retention).


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

New VWAP backtests submit EOD flattening at the resolved cutoff and fill at
the **next observed bar Open**, with configured costs. The report identifies
`eod_next_open_inferred_session_close` and `order_timing=next_open`; older
cutoff-Close reports retain their original labels and results. Entry blocking
and inferred shortened-session cutoffs still apply. The source trade's
`exit_deadline_utc` identifies the order cutoff, while `exit_time_utc` labels
the bar containing the actual simulated Open fill. One-minute bars are
close-labelled: that label is not a measured fill tick or evidence of
liquidation by a provider deadline. Prop source validation remains unchanged
and must check the saved fill/risk evidence; no time is backdated to pass it.

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

### Native chronological account-controlled replay — 2026-11-08

The normal prop configuration/check/run workflow also supports
`mode: "native_phase_replay"`. This mode reruns the actual native strategy over
an explicit historical IS window and saves a normal RunStore backtest plus an
AnalysisStore report. It is one historical scenario, not a Monte Carlo estimate,
phase optimizer, frozen outer assessment or deployment recommendation. The
subsequent optional native forecast is a separate report component; native
optimizer/campaign integration remains pending.

The initial admitted subset is the current VWAP strategy, actual continuous/base
MNQ prices, tick size 0.25, point value 2, complete one-minute sessions, EOD-flat
enabled and strategy-local volatility sizing disabled. Source checking validates
all original dataset bytes, source/risk/cost identity, current strategy identity,
whole sessions inside the saved IS report, the reviewed exchange calendar and
every observed minute from 17:01 Chicago through the scheduled close. Maintenance
gaps may make the dataset's original spacing metadata irregular; the check proves
minute cadence separately inside sessions. It does not impute missing bars.
Missing open sessions, sparse or partial sessions, unreviewed dates, NQ relabeling,
dated-contract expiry, incompatible point values and other strategies reject.
The first capture contract supports at most 366 calendar days and 510,000 bars.

`KnownDecisionRisk` contains only the completed decision close, causal initial
stop, timestamp and current account state. The owner accepts a whole-MNQ quantity
or skips before VWAP commits its entry counter/latches. The existing execution
engine then fills the accepted order on the actual next open. Actual gap loss may
exceed planned stop risk. Existing strategy brackets and provider loss floors
share the ordinary conservative OHLC/gap fill rules. Planning commission and
entry/stop slippage must match saved actual execution settings; planning loss is
never deducted from P&L. Session/EOF boundaries require flat actual exposure and
no pending orders; this mode does not invent end-of-data liquidation.

Evaluation owns fees, sequential provider-account retries, activation and
censoring. Strategy features continue causally across retries; only provider
state resets, with prior-attempt trading P&L retained in the ordinary trade
ledger. Funded starts with one fresh account, has no acquisition inputs or
replacement, and separately saves requests, gross account deductions, modeled
trader receipts and pending amounts. The normal backtest retains initial trading
capital plus actual trade net P&L. A cash bridge translates provider floors and
withdrawals without subtracting them a second time from trading equity.

The request declares phase/profile, size cap, optional common sizing policy and
inclusive CME session period. Evaluation accepts only its retry contract. Funded
requires explicit modeled receipt lag and amount convention. The server derives
the versioned calendar. Reports capture the request, source check, complete
session inventory, code identity, provider-rule review, actual child backtest,
sizing decisions, control events, session states, cash ledger, CSVs and ZIP.
Controlled results have their own research role and cannot be reused as ordinary
unconstrained IS paths. Generic detailed/risk reproduction rejects them; their
original full trade/risk/decision/control artifacts remain downloadable.

MNQ has an explicit `cme_mnq` calendar mapping, separate from instrument price and
multiplier identity. CME's [Micro E-mini contract fact card](https://www.cmegroup.com/trading/equity-index/files/cme-micro-e-mini-futures-fact-card.pdf)
specifies MNQ's multiplier/tick and 17:00–16:00 Chicago session. The mapping shares
the existing reviewed equity-index closure CSV, preserving its checksum and
coverage; it does not extrapolate later holidays. Its first allowed session is
6 May 2019, supported by [CME's launch notice](https://www.cmegroup.com/notices/ser/2019/04/SER-8360.html).
The saved CSV currently ends on 2 November 2026. This is an EOD-close calendar,
not a complete intraday halt or individual-contract expiration calendar. Provider
rule equivalence, liquidity, OHLC ordering and settlement remain explicit
unverified assumptions. Earlier reports and numerical evidence are unchanged.


### Native contiguous-block forecasts — 2026-11-08

The same native prop form can optionally add `native_forecast`. The actual
historical child and its calculation remain separate from all modeled paths.
`native_draws.py` indexes the immutable admitted source sessions and samples
complete contiguous blocks of 1, 5 or 10 sessions, retaining loss and no-trade
blocks. Pools match session lengths, close/cutoff shape and relative calendar
gaps. A short final draw uses a declared leading prefix of a complete block.
Missing compatible shapes reject; there is no circular price wrap, price
rebasing, lucky redraw or discarded execution failure.

Each block creates the normal strategy and warms its features using every
permitted source bar strictly before that block, with entry admission disabled.
Warmup has no provider callbacks, trades or fees. The existing engine then
executes the actual source bars. Strategy state resets at the declared block
boundary; provider state and actual trading cash persist across blocks. Original
source timestamps/prices remain intact, with explicit mappings to chronological
modeled account dates. Source row indices are one-based ordinals of the admitted
selection, not raw dataset file lines. The report also saves source timestamps,
dataset bytes/hash, period and original bars for exact identification.

A versioned, explicit America/Chicago target-calendar declaration supplies
weekdays, full closures and optional early closes. It is labeled modeled and
exchange-unverified, separately from the reviewed historical source calendar.
Starts must be after the last admitted IS session. Every start has an exclusive
calendar-day cutoff and at least one modeled open session. Target coverage must
include all cutoffs. Total paths are allocated equally across sorted distinct
start cohorts. Addressed random streams bind seed, phase, path index and draw
slot, so adding later paths cannot shift earlier draws.

Evaluation retains every attempt, fee, readiness date and censored path. If any
path has not acquired an account by cutoff, eventual acquisition cost/time means
remain null; restricted fees/durations and completion probability remain visible.
Funded starts one fresh account and estimates cash received by the finite cutoff,
with separate pending cash, gross account deductions and provider equity change.
No Evaluation inputs or implicit replacement account enter it. All path summaries
and schedules are retained; only the first declared K paths retain full detail,
chosen before outcomes. Equal-cohort means and conditional Monte Carlo standard
errors are separate from account outcome percentiles and future uncertainty.
Each cohort needs at least two paths for an MC standard error; one-path cohort
means remain visible with unavailable precision. Historical-law uncertainty and
provider/settlement qualification are not supplied by these error bars.

Preflight counts source-content validation, feature warmup and actual sampled
execution, bounded at 10 million bar work, 16 MiB encoded schedules and a 100 MiB
estimated detail allowance. The estimate does not guarantee encoded size.
Publication enforces 128 MiB for component files plus embedded `report.json`,
excluding the separate compressed ZIP. Excess work rejects before job reservation;
excess encoded output fails publication without dropping paths or truncating
captures. Rebuilt execution schedules must match the checked plan exactly, and
source/code identities are rechecked after both actual and modeled calculations.
A failed forecast does not publish a completed combined report; an already-saved
actual historical child remains inspectable.

Normal downloads add `native_forecast_plan.json`, `native_forecast.json`,
`native_forecast_paths.json`, `native_forecast_schedules.json` and
`native_forecast_captures.json`. Native optimizer/campaign integration,
conservative historical refitting and frozen native outer application remain
pending. See the [saved workflow and independent expected values](prop_simulation_review.md#native-contiguous-block-forecasts--2026-11-08).


# Native independent phase search contract and limits — 8 November 2026

Additive `search_settings.native_execution` selects actual strategy/account-state
reruns; omission keeps the saved-trade calculation path and existing defaults.
Its fields are `model: observed_contiguous_blocks_with_prior_prefix_v1`, explicit
`horizon_calendar_days` (1–365), `early_closes` date-to-HH:MM map (default empty),
and `capture_paths` (default 1, maximum 20). Candidate `simulation` supplies the
path count/seed; `sampling.block_weekdays` supplies 1, 5, or 10 source sessions.
Evaluation's chain count/seed must agree with that single declared path law.
Funded's horizon must equal the native execution horizon. Both use the existing
phase calendar; modeled cohort starts follow admitted IS observations. Calendar
declarations, rules and settlement assumptions retain their verification status.

Admission requires the existing DatasetStore and actual supported continuous
MNQ VWAP source, original execution costs, compatible session calendars and
complete source identity. Public selection remains IS only. Private nested and
terminal training contexts must verify exact source/frozen membership; a public
request cannot set those contexts. Supplemental saved-trade excursion files,
unsupported strategies/scaling and incompatible calendars reject explicitly.

Evaluation retains the independent acquisition-cost/calendar-time Pareto
contract. Eventual acquisition means are unavailable when required paths remain
censored; fees spent on those paths are still saved. A visible resolved frontier
does not make an unresolved declared family safe to freeze. Funded retains mean
cash actually received within the saved horizon, conditional on one fresh
funded account. No Evaluation fee/pass statistic enters its selection. All
candidates remain in the saved report, including unresolved and infeasible rows.

Native manual OOS applies the complete frozen family chronologically through
normal controlled backtests; it does not resample, shorten the frozen horizon,
rerank or fit new policies. The original source must cover every required actual
session. Controlled children are pinned before execution and captured within the
ordinary AnalysisStore result. Reopening reads saved artifacts.

## Optional conservative native expected cash

Use the explicit method `native_origin_block_bootstrap_lower_mean_v1` inside
`conservative_objective`; the saved-trade method is not silently substituted.
Chronological blocks of original source-block origins are sampled into frequency
weights. Each weighted draw still executes its intact original bars with that
origin's strictly prior original feature prefix. Prices are never spliced into
a counterfeit history and quantities are never rewritten after execution.

Every refit reruns the same Funded owner. Saved evidence retains origin indices,
weights/seeds/hashes, individual cash outcomes, schedule hashes, conditional
means and Monte Carlo standard errors. The lower historical-mean order statistic
uses nominal family tail `(1-confidence_level)/complete_candidate_count`; at
least five expected tail replicates and the declared history/block minima are
required. Every cohort needs at least two inner paths, at most 512 in total.
A required calendar-shape pool with zero positive weight makes that refit and
its lower-mean objective unresolved; it is never redrawn, dropped or replaced
with the point mean. An insufficient family has no conservative winner.

This estimates uncertainty under an explicit origin-frequency/stationarity
model conditioned on original feature prefixes. Origins overlap; they are not
independent new histories. More Monte Carlo paths do not increase historical
sample size. The lower mean is not a single-account payout percentile, a future
cash guarantee, execution certification or verified provider parity. Conditional
Monte Carlo error remains a separate diagnostic.

## Bounded complete-family work and saved outputs

Admission checks the entire declared family before running: at most 50,000,000
bar operations, 16 MiB of complete point-forecast schedules and 100 MiB estimated
captures/refit metadata. Historical origin capture is limited to 1,000,000
indices. Conservative refit work is included in the family bound. Bounds never
truncate candidate membership, pools or outcomes. Final encoded artifacts plus
embedded report JSON must fit the existing 128 MiB publication limit.

Ordinary downloads include `native_forecasts.json`,
`native_forecast_paths.json`, `native_forecast_schedules.json`,
`native_forecast_captures.json`, and (for frozen assessments)
`native_chronological_replays.json` plus the normal controlled backtest files.
History refit evidence is saved with the existing conservative objective export.


The saved API/browser journey and targeted release evidence are recorded in `prop_simulation_review.md`. Full-goal qualification and provider/live parity are separate.

## Research workspace integration (8 November 2026)

**Backtests → Research** is navigation over existing phase/nested campaigns,
applications and editable drafts. Draft/template configuration lives in the same
AnalysisStore catalogue; ordinary source checks, independent numerical owners,
workers and durable reports remain authoritative. Templates cannot transfer
source identities or results. Draft revisions prevent stale overwrites; missing
sources and unsupported policy families are preserved and block fresh execution.
Saved evidence is shown through actual-session timelines, qualification plots
and matched Funded forecast/actual receipt plots with complete tables/downloads.
No new simulation, selector or separate result store is introduced. See the M4
normal-product journey and expected observations in `prop_simulation_review.md`.
