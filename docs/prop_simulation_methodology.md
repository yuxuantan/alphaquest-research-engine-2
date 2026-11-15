# How Prop Sim calculates Evaluation and Funded results

Implementation reference, checked on **14 November 2026**, against code at
`8f6d85a`. This describes the current **Prop Sim** tab, not a proposal for new
calculations. Historical reports retain their saved implementation, policy,
inputs and verdicts; this guide does not upgrade their results.

## Contents

- [Which simulation am I running?](#which-simulation-am-i-running)
- [Sources, IS/OOS windows and costs](#sources-isoos-windows-and-costs)
- [Sampling and clocks](#sampling-and-clocks)
- [Evaluation on IS](#evaluation-on-is)
- [Funded on IS](#funded-on-is)
- [What is frozen before OOS?](#what-is-frozen-before-oos)
- [Evaluation and Funded on OOS](#evaluation-and-funded-on-oos)
- [OOS qualification and confidence](#oos-qualification-and-confidence)
- [Percentage risk and portfolio cash flow](#percentage-risk-and-portfolio-cash-flow)
- [Results, downloads and reproduction](#results-downloads-and-reproduction)
- [Implementation map](#implementation-map)

## Which simulation am I running?

The same tab exposes two different workflows. Their objectives and evidence
must be read separately.

| Property | Independent Evaluation / Funded sizing | Portfolio allocation, percentage risk & full cash flow |
| --- | --- | --- |
| Portal entry | `/#prop-sim` | `/#prop-sim?mode=portfolio` |
| Configurations | One campaign-qualified strategy parameter configuration | One to four qualified VWAP configurations on one common NQ/MNQ dataset |
| Sizing | Search separate whole-MNQ ranges for Evaluation and Funded | Declare separate phase policies: fixed contracts or percentage at risk |
| Calculation | Sample saved trade-session paths, apply local account transitions | Rerun actual strategy and execution on chronological market bars under local account control |
| IS objective | Evaluation: acquisition cost/time Pareto; Funded: mean received cash | Observed received cash minus paid Evaluation/activation fees, over a finite allocation family |
| OOS | Frozen sizes, OOS account Monte Carlo, chronological scenario and historical confidence assessment | Frozen allocation/policies on chronological OOS; also a continuous combined-period scenario |
| Replacements | Evaluation retries until acquisition; Funded starts fresh and has no replacement | Full Evaluation → Funded → replacement lifecycle under a hard monthly fee cap |
| Monte Carlo | Yes, including the separate OOS historical confidence layer | No portfolio Monte Carlo qualification in this mode |

There are also older report/configuration routes and native independent research
campaigns elsewhere in the repository. They may support other objectives, native
forecasts or sizing policies. Their existence does not mean the current
independent Prop Sim form searches risk percentages. **Percentage-grid
optimization for that form has been discussed but is not implemented.**

Current independent-form defaults and hard size ceilings are:

| Setting | Apex 50K EOD | LucidFlex 50K |
| --- | --- | --- |
| Default Evaluation / Funded search ranges | 1–10 MNQ / 1–10 MNQ | 1–10 MNQ / 1–10 MNQ |
| Evaluation / Funded hard ceilings | 60 MNQ / 40 MNQ | 40 MNQ / 40 MNQ |
| Scenario purchase / activation fee | USD 49 / USD 129 | USD 80.50 / USD 0 |
| MNQ commission per side | USD 0.51 | USD 0.50 |
| DLL | Required | On by default; may be disabled explicitly |
| Evaluation consistency variant | No Lucid consistency variant | 40% standard; explicit 50% add-on |

Fees/commissions are editable scenario inputs, not current vendor quotes. Funded
tier caps can be lower than these hard ceilings. Historical saved inputs are
not changed to today's defaults.

New independent Prop Sim runs are automatic: one initial Run checks admission,
executes both IS searches, selects and freezes a small family per phase, and
runs OOS qualification. No later confirmation is required. The phases have
independent objectives and state; their jobs may nevertheless queue behind each
other because they share bounded compute resources.

## Sources, IS/OOS windows and costs

### Campaign qualification comes first

The server rechecks the selected configuration against mechanics validation,
frozen IS Broad/IS Narrow selections, the current completed campaign OOS job,
and the latest completed **current-policy campaign Monte Carlo** assessment.
Source identities, strategy parameters, candidate membership and saved artifact
hashes must agree. A checkbox or client-supplied passing verdict cannot bypass
these checks.

The Monte Carlo in campaign OOS is a separate, full-period trading-edge sanity
check. It is not the Evaluation/Funded account simulation described below.

Since campaign eligibility already inspected OOS and combined-period results,
Prop Sim OOS is explicitly **post-screening historical assessment**, not a new
untouched holdout. Freezing prop sizes prevents further OOS sizing selection;
it cannot undo prior access to that market history.

### Independent sizing uses the saved IS source only

The IS daybook comes from the selected configuration's saved IS backtest.
Bounds are the intersection of its declared campaign IS window and actual saved
coverage, expressed as CME Chicago session dates. The phase engines do not
automatically make another 70/30 split inside that IS window. Older legacy
joint reports have different splitting behavior and must not be substituted.

OOS assessment binds the corresponding saved OOS backtest to its frozen IS
parent. Strategy definition, parameters, split and execution costs must remain
compatible. Session-specific audit output can differ between periods, but
material strategy/execution settings cannot. OOS bounds are similarly restricted
to the declared OOS window and saved coverage.

### Saved trades become an account-simulation daybook

For the independent saved-source workflow:

1. Read and verify the source trades and available captured risk evidence.
2. Validate the NQ/MNQ symbol and point value: USD 20 per NQ point or USD 2 per
   MNQ point. Reject unsupported source shapes rather than guessing exposure.
3. Require chronological nonoverlapping trades. Cross-session risk that cannot
   be assigned safely to daily account rules rejects; it is not silently reduced
   to close-only P&L. Lucid sources must also satisfy the supported flattening
   window.
4. Normalize results to reference exposure, then price simulated MNQ quantities.
   Ten MNQ have one NQ's point exposure; this is a price-path proxy, not proof of
   identical liquidity, basis or fills.
5. Group complete trades in their original within-session order. Include
   zero-trade weekdays in the requested research period. For this portal the
   generic grid is weekdays, not a newly verified inventory of exchange openings.

A source session is sampled as a whole. Individual trades within that session
are not independently shuffled. Local account control can consume only part of
the session: for example, stop after a DLL hit, account breach or payout pause.
The subsequent saved strategy signals are not regenerated in this fixed-path
mode. This is a material distinction from native percentage-risk replay.

### Commissions replace source commissions once

The qualified fixed-size form declares a per-MNQ, per-side commission override.
For a source trade with quantity `q`, let `f = 1` for NQ or `10` for MNQ:

```text
gross_per_NQ_reference = (source_net + source_commission) / q × f
net_per_MNQ = gross_per_NQ_reference / 10 − 2 × declared_MNQ_commission_per_side
simulated_trade_net = net_per_MNQ × effective_MNQ_quantity
```

The source's execution slippage is already reflected in its fills and remains
in those prices. It is not charged a second time. Commission-adjusted adverse
bounds reserve the relevant fee adjustment, entry fee and realized exit loss;
these are conservative modeled bounds, not newly measured tick-level MAE/MFE.

Adverse risk is checked during a held trade, not only at its realized close.
Ordered adverse frontiers distinguish continuous OHLC threshold crossings from
observed jumps/gaps. Continuous segments assume threshold fills; observed jumps
can liquidate beyond the floor. This remains an OHLC/captured-path execution
model, not reconstructed tick sequencing.

## Sampling and clocks

### What “1,000 paths per size, per phase” means

With the default 1,000 paths, every declared size gets its own account estimate
from 1,000 simulated paths in each phase. Selecting a larger range does not
silently reduce that count. The form accepts 8–20,000 paths per size. More paths
reduce simulation noise under the fitted historical law; they do not create
additional historical trades or independent market regimes.

The default seed is 42 and the default history block is five weekdays. The form
supports 1, 5 or 10. The streaming sampler picks a random starting index, takes
consecutive daybook entries for the declared block length, wraps at the end,
then picks another block. Empty days remain empty. Dependence within a block is
preserved; the ordering across blocks is synthetic. Seeds and schedule hashes
are saved. Equal seeds alone are not a general guarantee of paired inference
across different account engines.

### Three clocks that must not be conflated

| Clock | Meaning |
| --- | --- |
| Historical source session | A Chicago-session-indexed entry in the IS or OOS daybook |
| Modeled account calendar | Scenario dates used for purchases, retries, weekends, declared closures, activation, inactivity and receipts |
| Historical chronological replay | Actual-order source sessions assigned to the covered replay window, without random resampling |

The independent scenario calendar is Monday–Friday minus user-declared full-day
closures, in `America/Chicago`. It is an assumption, not a verified exchange or
bank settlement calendar, and has no early-close model. The configured scenario
start date positions the simulated account on that calendar; it does not change
the source IS/OOS split.

Calendar-day durations include weekends and closures. A session-count deadline
advances only on modeled open sessions. Receipt delay is in **calendar days**,
not banking days. The native portfolio mode separately validates source-session
coverage and uses its captured calendar identity.

## Evaluation on IS

### Objective and endpoint

Evaluation asks: **what does it cost, and how long does it take, to acquire one
usable funded account at this size?** It includes unsuccessful Evaluation
purchases and their durations. It does not run Funded payouts, subtract Funded
losses or rank a combined annualized business score.

A path ends at the first usable funded session. It does not continue trading
Funded in the same independent Evaluation simulation. The Funded optimizer is
a separate fresh-account experiment.

Acquisition assumes fresh sequential retries and sufficient purchase capital.
There is no monthly purchase budget in the independent optimizer. Numerical
attempt/calendar guards can censor that unlimited-retry model; they are not
provider failures or economic budgets.

### Apex 50K EOD: attempt sample, then empirical renewal chains

The Apex Evaluation owner first generates the requested number of independent
attempts from the IS daybook. Each attempt starts at zero profit relative to the
USD 50,000 initial balance and follows these local rules:

- Profit target: USD 3,000, checked at completed-trade marks.
- Maximum trailing drawdown: USD 2,000, with EOD high updating the next
  session's floor. The implementation floor is
  `min(EOD_high − 2000, 3000)` in dollars relative to initial capital.
- DLL: USD 1,000 from the session opening equity. A DLL hit pauses that
  session; an account-floor breach terminates the attempt.
- Deadline: 21 modeled session weekdays. A still-open attempt becomes timeout.
  This preserved local session rule is not a claim about today's provider terms.
- Evaluation quantity ceiling: 60 MNQ, additionally bounded by the declaration.

The sample records **joint outcome/duration pairs**. A long failed attempt and
a short failed attempt therefore have different effects on acquisition time.
Let `p = passed_attempts / attempt_count`, purchase fee `F`, activation fee `A`.
For an identified estimate under the stationary IID fresh-attempt law:

```text
expected_attempts_per_funded = 1 / p
expected_acquisition_cost = F / p + A
```

Funding time is not `days among successful attempts`, and is not a conversion
of trading days by a constant multiplier. A second simulation draws entire
outcome/duration pairs from the empirical attempt distribution and lays retries
onto the scenario calendar. Each failed attempt consumes its sampled duration
and another purchase fee. After passing, it waits for activation eligibility
and the next open usable funded session.

The qualified portal uses as many renewal chains as the requested path count,
with `chain_seed = seed + 3`; the attempt sample uses the declared seed. Default
retry delay is zero extra calendar days, so the next purchase is after the failed
attempt's terminal day. Default Apex activation delay is one session, followed
by next-open-session readiness. Weekend/closure waits remain in calendar time.

The guards default to 10,000 attempts and 3,650 calendar days. Zero observed
passes, censored attempts or unresolved acquisition chains withhold the relevant
unconditional objectives. The engine retains lower bounds and identifiable
timing quantiles where possible; it does not report a mean calculated only from
chains that happened to finish.

Example arithmetic, **illustrative only**: at fee USD 49, activation USD 129 and
estimated attempt success 25%, expected acquisition cost is
`49 / 0.25 + 129 = USD 325`. That says nothing by itself about calendar time.

The compatibility component also retains older repeated-block-chain diagnostics.
Those are not the independent optimizer's calendar-time objective; read the
candidate's top-level `metrics` and model version.

### LucidFlex 50K: direct dated acquisition paths

Lucid uses a separate calendar-acquisition owner, not Apex's IID attempt-cost
formula or 21-session expiry. Each requested path starts a new purchased
Evaluation on the declared civil date, samples whole source-session blocks,
applies the account rules, and pays for every retry until funded readiness or a
numerical guard.

Current local Evaluation rules are:

- Profit at least USD 3,000 **and** best session profit no more than 40% of
  cumulative account profit, checked at session close. The explicit add-on
  changes 40% to 50% and requires the user to enter its actual checkout fee.
- No extra consistency cushion. Thus profit of USD 3,000 alone is not enough
  if one day's profit is too large.
- USD 2,000 EOD trailing drawdown, floor capped at USD 100 above starting
  capital: `min(EOD_high − 2000, 100)` in relative-profit dollars.
- Fixed USD 1,200 DLL when enabled, including above the profit threshold; it is
  not automatically removed. DLL-off is a declared alternative.
- 30-calendar-day inactivity; closed dates advance that clock. The local
  activity rule tracks an observed absolute account-equity change of at least
  USD 1 at a processed trade mark.
- No provider session expiry in this model. Calendar/attempt guards still
  censor unresolved acquisition.
- Maximum 40 MNQ; activation fee is zero. The portal declares zero extra
  activation sessions, with funded readiness on the next modeled open session.

Each fresh retry has its own addressed block stream. Fees and time are measured
directly over complete acquisition paths:

```text
expected_acquisition_cost = mean(all Evaluation fees + paid activation fees)
expected_calendar_days_to_funded = mean(ready date − initial purchase date)
```

These unconditional means are available only when **every requested path** has
acquired. Unresolved paths remain visible with accrued fees and restricted
observed-time summaries. Never replace the Lucid cost calculation with purchase
fee divided by first-attempt pass probability.

The pass-probability diagnostic is the first purchased account's pass fraction,
not the probability of eventually acquiring after repeated retries. Additional
diagnostics separate failures before/after first reaching the nominal target,
consistency-blocked sessions, time before the final attempt, final-attempt
pre-/post-target time, and pass-to-ready time. Some counts overlap conceptually:
they are explanatory measurements, not independent time buckets to sum.

Example, **illustrative only**: a USD 3,000 best day requires total profit of at
least USD 7,500 under 40% consistency, or USD 6,000 under 50%. Retries can add
substantially more time than the final attempt's consistency wait.

### Pareto membership and automatic choices

Evaluate every whole-MNQ size in the declared **Evaluation** range. The chart
uses complete, feasible estimates; no points are invented for missing or
unresolved candidates. Candidate A dominates B if A has no greater acquisition
cost or time and is strictly better on at least one. Exact ties remain visible.
The frontier is a point-estimate frontier, not statistically certified superiority.
If some rows are unresolved, resolved candidates remain usable; their frontier
does not imply comparison with those unresolved rows.

The automatic selector reads the sealed IS frontier and freezes:

1. Lowest expected acquisition cost.
2. Fastest expected funding time.
3. Lowest cost among candidates within **1.25 × the fastest time**.

Duplicate choices collapse, so one to three sizes may proceed. Exact metric ties
prefer smaller MNQ, then stable candidate identity. There is no arbitrary
cost/time weighting or hidden Funded-based Evaluation winner.

## Funded on IS

### A fresh account, independent of Evaluation

Each path begins with a fresh USD 50,000 Funded account, zero trading profit,
no previous payouts and its initial provider tier. It does not inherit an
Evaluation path's duration, pass probability, P&L or successful-day sequence.
It samples the selected configuration's **IS** daybook using the same declared
block concept and applies the Funded phase's separately declared size.

The default horizon is 90 calendar days, configurable from 1 to 365. The interval
is `[start, start + horizon)`: the final cutoff is exclusive. Weekends and
declared closures advance calendar inactivity and receipt timing without
creating trading sessions. Every path ends at the horizon or account closure.
There is **no replacement funded account** in this independent calculation.

### Local Apex Funded rules

Amounts below are profit/equity relative to the initial USD 50,000, not the
account's nominal balance.

| Session-opening profit tier | Maximum MNQ | DLL |
| --- | ---: | ---: |
| Below USD 1,500 | 20 | USD 1,000 |
| USD 1,500 to below 3,000 | 30 | USD 1,000 |
| USD 3,000 to below 6,000 | 40 | USD 2,000 |
| USD 6,000 and above | 40 | USD 3,000 |

Requested quantity is capped by the current tier and the declared maximum.
The USD 2,000 EOD trail eventually locks at USD 100 profit. Account-floor hits
terminate; DLL hits pause the session. Payout eligibility requires five
qualifying sessions of at least USD 250 profit, positive cycle profit, the best
day no greater than 50% of cycle profit, and sufficient equity above the
USD 2,100 safety net for the next payout rung.

The six gross payout rungs are USD **1,500, 1,500, 2,000, 2,500, 2,500, 3,000**.
The current local Apex kernel treats that amount as both account deduction and
trader entitlement. Qualification counters/cycle profit reset after payout;
the EOD trail observes pre-withdrawal balance. The portal counts approval days
under its saved rule. Completing the sixth payout closes the modeled account.
The local inactivity test requires two sessions of at least USD 50 profit in a
rolling 21-session window; empty sessions can therefore matter.

### Local LucidFlex Funded rules

The trailing drawdown is USD 2,000 and locks at USD 100 profit. Opening-profit
tiers are **20 MNQ below USD 1,000; 30 from USD 1,000; 40 from USD 2,000**.
When enabled, the DLL remains a fixed USD 1,200. Inactivity uses the preserved
30-calendar-day rule, including closed dates.

There is no Funded consistency gate. The local payout model requires five
qualifying days at USD 150, positive profit above the cycle start, and a gross
request of at least USD 500. Gross withdrawal is
`min(50% of current account profit, USD 2,000)`. Trader entitlement is **90%**
of gross; the account loses the **full** gross amount. There are five payout
rungs. Withdrawal locks the trail and resets cycle qualification state.

With DLL enabled, eligibility may be checked at supported completed-trade
marks and a request pauses the rest of that session. Source timing controls
whether an intraday request is allowed; the saved-source adapter marks exits
after 15:45 and before 18:00 New York as ineligible for that intraday check.
Session-close eligibility is also processed. This is a local timing assumption,
not verified provider approval latency.

### Received cash, pending cash and censoring

For every payout event the calculation keeps:

- Request/eligibility date.
- Gross account deduction, applied to the account at request.
- Trader entitlement, after the modeled share where applicable.
- Receipt date: request date plus declared calendar-day delay, default two.

Only receipts **strictly before** the horizon cutoff enter the objective.
Requests whose money arrives at or after cutoff are pending. A subsequent
terminal account event does not silently erase an already modeled entitlement.
Receipt timing/settlement remains an assumption, not a guarantee of payment.

```text
cash_received_for_path = sum(trader entitlements received before cutoff)
expected_Funded_receipts = sum(cash_received_for_path) / all_requested_paths
```

Zero-payout and breached paths remain in the denominator. Fees and time spent
acquiring the Funded account are excluded. There is no annualization, recurring
replacement assumption or Evaluation-adjusted score in this objective.

An account still open at the horizon has complete horizon cash but an unknown
eventual lifetime. Its lifetime is right-censored; that does not make its
90-day receipts unresolved. The report separates restricted observed lifetime
from an unconditional total-lifetime estimate, which is withheld when necessary.

Example, **illustrative only**: one Lucid path requests USD 2,000 gross, with
USD 1,800 trader entitlement. If receipt is before cutoff, its objective cash
is USD 1,800. If receipt is on cutoff, objective cash is USD 0 and pending cash
is USD 1,800; the account has still been debited USD 2,000.

### Selection and reported uncertainty

All complete feasible **Funded-range** sizes are ranked by mean received cash.
The optional maximum breach-probability cap is off by default. If explicitly
enabled it constrains empirical breach probability within the frozen horizon,
not eventual breach over the full historical dataset. Other diagnostic outputs
include zero-receipt probability, P10/median/P90 receipts, first-receipt
probability and conditional timing, payout milestones, pending cash, inactivity,
breach and survival-to-horizon probabilities.

For conditional simulation precision, the owner calculates within-start-cohort
mean standard errors, normal family-adjusted mean intervals, and whole-path
bootstrap intervals (the portal declares 100 such bootstrap replications).
These bootstrap intervals resample account outcomes and are **not** the later
10,000 historical-market refits. Rare unobserved outcomes and model uncertainty
are not resolved by these intervals.

The automatic selector freezes:

1. Highest positive mean received cash.
2. Smallest size retaining at least **95% of that peak mean**.

Duplicates collapse, so at most two sizes proceed. Exact cash ties prefer
smaller MNQ, then identity. A smaller size is not guaranteed to have a lower
breach probability. Unresolved/infeasible rows cannot be chosen; they do not
block choosing other resolved eligible rows. If there is no positive eligible
estimate, that phase reports no eligible candidate rather than borrowing an
Evaluation winner or consulting OOS.

## What is frozen before OOS?

The automatic continuation reads **sealed IS reports only** for family selection.
It saves original report identity/hash, selected sizes and their selection roles,
strategy/parameters, source and split, account rules, costs, sampling, seed,
requested path count, modeled calendar, retry/horizon/receipt settings, optional
constraints, selection policy and numerical implementation identity.

OOS is allowed to change the data role/source from its frozen IS parent to the
matching OOS report. It cannot change the selected size, strategy parameters or
execution-cost declaration, or search replacement sizes after seeing results.
Numerical changes fail compatible-package checks where required rather than
silently pretending an old freeze belongs to a new engine.

The automatic family is at most three Evaluation sizes plus two Funded sizes.
The qualification implementation also supports historical/manual packages of
up to four per phase; that upper contract does not mean the automatic selector
always chooses four.

## Evaluation and Funded on OOS

Each frozen candidate is assessed in two complementary ways.

### 1. OOS account Monte Carlo

Build a new daybook from **only the saved OOS source window** and rerun the
same phase owner with the frozen configuration and path count:

- Apex Evaluation fits OOS attempt outcomes/durations and runs its renewal
  calendar model.
- Lucid Evaluation runs direct OOS-sourced calendar acquisition paths.
- Funded runs fresh-account horizon paths from OOS sessions, including zero
  receipts, payout deductions, receipt delays, tier caps and terminal outcomes.

Sampled paths can reuse source sessions; simulated acquisition can extend beyond
the length of the observed OOS window. The resulting time is an estimate under
the fitted resampling law, not an observed future time-to-funding.

Assessment does not produce a new winning size or replacement frontier.
Its reports deliberately have `selection_status = assessment_only_no_reselection`.
IS/OOS comparisons retain original IS metrics and OOS/IS ratios.

### 2. One chronological OOS scenario

Alongside Monte Carlo, the saved-source assessment replays the frozen choice
through the OOS daybook in actual order:

- **Evaluation:** start at the beginning of saved OOS coverage, process source
  weekdays in order, buy retries when allowed, and stop at funded readiness or
  window end. Running out of the window before acquisition is censoring, not
  evidence that acquisition would never occur.
- **Funded:** start one fresh Funded account at the beginning of OOS for the
  frozen calendar horizon. Coverage shorter than that horizon rejects. Continue
  through its account outcome/receipt rules without replacement.

The default single chronological replay builds a weekday scenario starting
at the first OOS session, with an empty declared-closures tuple in the replay
owner. It should not be mistaken for an exchange-calendar-certified replay or
for the configurable account-start sensitivity scenarios.

These are fixed-signal saved-source replays, not strategy reruns. A single
chronological outcome is not a Monte Carlo mean or an independent qualification
of an average. The default historical GO gate below is based on resampled
account economics and evidence; one chronological outcome is complementary
diagnostic evidence, not an additional automatic gate.

## OOS qualification and confidence

### Current fixed historical policy

The current default is `prop-oos-qualification-v1`. It requires no user-supplied
business-dollar limit. Optional older economic-policy declarations/revisions
remain separate and retain their original verdicts.

Prerequisites include current campaign admission. For each frozen candidate,
the source must have **at least 12 complete OOS calendar months**, **100 closed
OOS source trades**, and an account result with status `estimated`. Funded must
also have enough calendar coverage for its whole frozen horizon. Complete months
are literal: 2 January through 30 December does not contain all twelve months.
The closed-trade count is taken from the bound saved backtest's summary; it is
not a count of simulated repeats.

The economic comparisons are:

| Phase | Ratio | Acceptable direction |
| --- | --- | --- |
| Evaluation | OOS mean acquisition cost / IS mean acquisition cost | At most 1.50 |
| Evaluation | OOS mean calendar time to funded / IS mean time | At most 1.50 |
| Funded | OOS mean received cash / IS mean received cash | At least 0.70 |

Passing the **point ratio** alone is insufficient. These margins are tested
using historical uncertainty bounds. Drawdown/breach diagnostics are not a
substitute for these account-economic checks, and there is no newly required
95th-percentile-drawdown-to-observed-drawdown gate here.

### Outer historical bootstrap versus inner account paths

For each frozen size with adequate evidence:

1. Generate **10,000 historical refits**. For each index, independently circular-
   block-resample the IS daybook and OOS daybook to their original lengths.
   The outer block length is `max(5, declared account block weekdays)`.
2. On each resampled history, rerun the existing Evaluation or Funded account
   estimator with the **full frozen inner path count**. Historical units are
   source sessions, not previously simulated account payouts.
3. Compute the OOS/IS economic ratios for that refit. Store its addressed seed,
   history-index hash, metrics and ratio.
4. Form percentile bounds from the resulting historical ratio distribution.

The history seed is 13742. Seeds are derived from history role and replicate
index, so changing worker order does not change intended draws. Funded may reuse
bounded calendar/index preparation and identical histories may reuse exact
calculations; neither optimization drops requested histories or account paths.

The nominal confidence level is 95%, with a fixed Bonferroni family budget of
12 metric tests: up to four Evaluation sizes × two checks, plus four Funded
sizes × one. Each tail is `0.05 / (2 × 12) = 0.00208333…`; the empirical bounds
use approximately the **0.2083rd and 99.7917th percentiles**, with inverse-CDF
quantiles. The budget is not reduced just because the automatic family is smaller.

Inner conditional Monte Carlo relative standard error must be at most **5%**
for the required mean estimates across the refits. Missing, nonfinite or
unidentified ratios cannot establish a pass. This separates numerical precision
from the outer historical evidence requirement.

### Verdicts

| Check type | PASS | FAIL | Insufficient evidence |
| --- | --- | --- | --- |
| Evaluation maximum ratio | Upper bound ≤ 1.50 | Lower bound > 1.50 | Bound crosses 1.50, or unavailable |
| Funded minimum ratio | Lower bound ≥ 0.70 | Upper bound < 0.70 | Bound crosses 0.70, or unavailable |

The candidate is **GO** only when evidence and precision requirements pass and
all required checks pass. With adequate evidence, any failed economic check
gives **NO_GO**. Missing evidence/precision or an unresolved comparison gives
**INSUFFICIENT_EVIDENCE**, rather than automatic approval or point-only rejection.
Failed campaign prerequisites override admission. Verdicts are per frozen
candidate and phase; there is no OOS-selected replacement winner.

GO means the historical model supports moving to forward execution review.
Forward status is initially **PENDING**; the separate execution review requires
at least 20 sessions, 30 closed trades and zero unexplained discrepancies with
its provenance/review requirements. Historical GO is not provider certification,
automatic live authorization or proof of full replacement-account profitability.

The block bootstrap assumes historical representativeness and suitable dependence.
Its nominal confidence does not mean a 95% probability of future success, and
its family correction does not erase earlier adaptive strategy search or prior
OOS access.

### Why qualification can be much slower than the initial search

With 1,000 inner paths, one frozen size can require roughly
`10,000 × (1,000 IS + 1,000 OOS) = 20 million` account-path evaluations for
historical refits, before additional phase-specific work. Apex also has attempt
fitting/renewal stages. This is distinct from a 1,000-path point estimate.
Repeated identical daybooks and prepared calendars can reduce actual repeated
work without reducing the requested sample counts.

Historical refits use the existing bounded process runtime, normally up to four
workers, subject to CPU availability/reservations and configuration. Work remains
server-owned after leaving the page. Prop Sim and Job history poll existing
progress metadata: phase, size, candidate index, completed/total resamples,
workers, elapsed time, rate and ETA when available. Those polls do not rerun
calculations. Writes are throttled to approximately once per second. Stopping
drains active siblings; restarting unfinished work does not resume an arbitrary
inner account path. Sealed completed results/frozen choices are retained.

### Optional assessments and reuse

- **Account-start sensitivity:** after a compatible OOS review, replay five
  evenly spaced, coverage-qualified starts chosen without consulting returns.
  Evaluation uses 180-calendar-day slices; Funded uses its frozen horizon.
  Each start is a fresh chronological account/acquisition scenario, not portfolio
  replacement or a new size search. Overlapping windows are dependent. Insufficient
  coverage remains inconclusive. These are optional, not five automatic extra gates.
- **IS robustness:** assess frozen sizes on declared block settings
  `{1, 5, 20, original}` and first/second IS halves. No new sizes are selected.
- **More-path precision:** explicitly assess the same frozen policies using the
  requested diagnostic count. It does not overwrite IS selection.
- **Business-policy review:** optional explicit cost/time/receipt limits and
  reasoned revisions, retaining old verdicts and marking post-access revisions
  retrospective. It is separate from the default fixed historical policy.

Identical qualified assessment inputs reopen the canonical running/completed
job and verified sealed report. Request IDs alone do not require another
simulation. Compatible saved point outputs and confidence evidence can be reused
for later reviews when their identities match; historical reports are not
rewritten. Failed/stopped attempts remain retryable. An assessment needing new
paths or incompatible numerical inputs cannot claim reuse of different evidence.

## Percentage risk and portfolio cash flow

### Sizing is applied before entry using current account state

In the portfolio form, choose **Percentage at risk**, declare separate
Evaluation/Funded percentages and caps, then choose a basis:

| Basis | Budget behavior |
| --- | --- |
| Initial configured capital | Percentage × USD 50,000; stable dollar budget |
| Current account balance | Percentage × current provider balance; compounds and responds to withdrawals/losses |
| Available drawdown cushion | Percentage × distance from current equity to the account floor |

```text
risk_budget = max(0, chosen_basis) × risk_percent / 100
unit_planned_loss = signed decision-price-to-initial-stop distance × point_value
                  + entry/stop-exit slippage allowance × point_value
                  + round-trip commission
requested_quantity = floor(risk_budget / unit_planned_loss)
actual_quantity = minimum(requested_quantity, declared cap, current provider cap)
```

The shared sizing owner can also impose explicitly declared account/daily-cushion
guards; the ordinary portfolio form does not expose those optional guard switches.
An unaffordable single contract is skipped. The percentage is a planned initial
loss budget, not percentage notional exposure or a promise of maximum realized
loss. Gaps, fills and later stop changes can exceed it. Planning costs size the
entry and are not separately debited a second time.

The engine reruns actual supported strategy callbacks, entries, fills, stops and
account transitions on market bars. It does not multiply completed saved trades
by newly chosen sizes. Every accepted signal sees current account state.
Supported sources currently require the VWAP strategy, EOD flattening,
strategy-local Vol Sizing disabled, common dataset and matching execution
settings. Missing possible holding-window minute prices reject explicitly.

For example, **illustrative only**, 0.20% of initial USD 50,000 is USD 100.
With MNQ point value USD 2, a 20-point stop, USD 1 round-trip commission and zero
slippage, planned loss is USD 41 per MNQ, admitting two contracts. A 40-point
stop gives USD 81, admitting one. This stabilizes planned dollars as stop
distance changes; it is not an independent margin or notional-exposure control.

### What the automatic allocation search does

The declared risk percentages are **inputs**, not a percentage grid optimized by
the independent Monte Carlo engine. The portfolio search compares a finite IS
allocation family:

- Separate accounts: integer account counts per configuration, up to the maximum
  concurrent accounts (one to four).
- Shared accounts: per-trade risk shares in 25% steps and permitted account
  counts. Only one position may be open in an account. Higher-share strategies
  have priority for simultaneous signals; saved order breaks ties. Strategies
  continue observing bars while another owns the position. Share multiplies
  that strategy's per-trade budget; it is not permission to open concurrent risk.
- Zero purchases: retain the budget unspent as an explicit baseline.

Choose the allocation maximizing **actual IS receipts minus actually paid
Evaluation and activation fees**; ties favor fewer accounts, then canonical
allocation order. Freeze allocation, phase sizing policies, rules, costs,
calendar/source and implementation identities before reading OOS prices.

It then runs the same frozen choice on a fresh-start OOS scenario and a continuous
combined IS+OOS scenario. Combined retains account/budget state across the split;
it is not the sum of two separately fresh-start scenarios. Strategies start
cold/flat when phase/account switches occur; Evaluation retries retain causal
feature state. No OOS reranking is performed.

Every purchase checks the shared hard calendar-month fee ceiling and reserves
its activation obligation. Failure releases the reservation; activation consumes
it. Payout receipts never enlarge the monthly ceiling, and unused allowance does
not roll over. Funded breach, inactivity or final payout completion can lead to
a replacement Evaluation purchase from the next civil day, subject to budget.
Account deductions, trader receipts, pending receipts, fees and reservations
remain separate ledger entries.

If zero purchases wins, the result says so. A best invested IS alternative may
be shown diagnostically; it does not replace the frozen zero-purchase OOS choice.
This mode provides observed cash-flow/allocation research, not portfolio Monte
Carlo expected-profit optimization or a new portfolio GO certification.

## Results, downloads and reproduction

### Reading the independent result columns

| Result | What it means |
| --- | --- |
| Acquisition cost | Evaluation purchases/retries plus activation to acquire one funded account; Apex uses its IID formula, Lucid direct complete-path fees |
| Calendar days to funded | Purchase-to-usable-Funded duration, including failed attempts and calendar waits |
| Pass probability | Attempt success diagnostic, not eventual acquisition probability after unlimited retries |
| P90 funding time | Tail of the acquisition-time distribution, subject to completeness/identifiability |
| Mean trader receipts | All-path average cash received before the fresh-Funded horizon cutoff; includes zero paths |
| P10 / median / P90 receipts | Account-outcome quantiles, not confidence intervals for the mean |
| First payout / zero payout | Probabilities over all paths; received timing is conditional on receiving a payout |
| Breach probability | Breach before the frozen horizon, not an eventual-lifetime guarantee |
| Survival / restricted lifetime | Open-at-horizon probability and observed time; eventual lifetime can remain censored |
| Pending cash | Entitlement with receipt outside the horizon, excluded from objective cash |
| Gross deductions | Amount removed from account equity; can exceed trader receipts |
| OOS/IS ratio and bounds | Frozen-policy deterioration comparison and historical confidence bounds |
| GO / NO_GO / insufficient evidence | Historical non-inferiority verdict under the saved policy, distinct from forward readiness |

Visible tables round for display. Saved numerical outputs preserve their
underlying precision. Always compare the same account model, horizon, costs,
sampling law and metric definition; a lifetime payout or legacy annualized
joint score is not the fresh-account horizon receipt objective.

### Normal product steps

1. Complete the campaign qualification pipeline and select its eligible
   configuration in **Prop Sim**.
2. Choose Apex/Lucid, separate Evaluation/Funded size ranges, paths, seed,
   blocks, fees/calendar, horizon and receipt delay. The optional Funded breach
   cap is disabled unless deliberately set. Click Run once.
3. Follow IS search, automatic frozen choices and OOS jobs on Prop Sim or Job
   history. Leaving the page does not cancel server-owned work.
4. Reopen the saved simulation. Inspect each phase's current OOS table and
   frozen-choice/criteria details; expand IS results or the Evaluation Pareto
   exploration when needed.
   **Conclusion & next steps** summarizes both phases at the top. A phase's
   expanded explanation identifies confidence, source-evidence and account-MC
   precision blockers, and each OOS table row names its next step. Inconclusive
   prop sizing does not revoke prior campaign checks. An extra-path diagnostic
   does not automatically update an OOS verdict. Historical-version results
   remain readable but cannot establish current qualification. Historical GO
   offers the existing paper review; even forward GO is not live authorization.
5. Download the phase report/evidence. Inspect `report.json` (or
   `calculations.json`) for `calculations.candidates`; each row holds its
   `metrics`, source/configuration manifest, uncertainty and censoring. OOS rows
   add `chronological_replay`, `is_comparison`, `outcome_summary` and
   `prop_qualification` where applicable.
6. Check `request.json`, `source_checks.json`, `phase_candidates.json`,
   `phase_metrics.json`/`.csv`, `sampling.json`, `provider_rules.json` and
   `frontier.json` or `ranking.json`. Source captures, policies and confidence
   records accompany the sealed report. Candidate paths are retained in the
   report calculations; do not infer all-trial membership from the visible chart.

Expected observations are structural, not promised profits: only IS selected
sizes appear in OOS assessment; OOS preserves original size/rule/cost identities;
zero receipts stay in means; unavailable objectives are labeled unresolved;
historical confidence uses saved source histories and no replacement selection.

For native percentage risk, use the portfolio mode, declare policies and Run.
Its saved downloads include `portfolio_frozen.json`, allocation results, actual
trades, sizing decisions, transitions and the full cash ledger. Reconcile each
quantity with its declared budget/known stop and each receipt/fee with the ledger.
The [native-portfolio evidence](evidence/qualified_prop_sim/native-portfolio/README.md)
provides a previously saved real-source demonstration, exact reproduction steps
and independent arithmetic. Its short-window outcome is an example, not a
forecast for another source.

### Reproducible arithmetic and boundary examples

The illustrative values in this guide are not inserted into product reports.
Existing focused tests hold independent oracles for:

- IS-only family selection, the inclusive 1.25× time and 95% receipt boundaries,
  smaller-size ties, duplicate collapse and resolved-row selection.
- Qualification equality at ratios 1.50 / 0.70, bounds crossing the margin,
  complete-month counts, the 12-test tail and actual phase-owner resampling.
- Native quantity/budget arithmetic, replacement cash and report evidence.

For a quick documentation cross-check, select only the affected arithmetic
cases; no backtest rerun, browser server or confidence job is required:

```sh
.venv/bin/python -m pytest -q \
  tests/test_prop_sim_automatic.py::test_evaluation_three_objectives_and_exact_time_boundary \
  tests/test_prop_sim_automatic.py::test_funded_peak_and_smallest_ninety_five_percent_boundary \
  tests/test_prop_sim_automatic.py::test_duplicates_and_exact_ties_choose_smaller_size \
  tests/test_prop_sim_automatic.py::test_unresolved_and_constraints_excluded_without_blocking_resolved \
  tests/test_prop_sim_automatic.py::test_phase_and_is_role_reject_and_rules_do_not_consult_other_phase \
  tests/test_prop_oos_qualification.py::test_fixed_margins_equality_fail_and_uncertain_are_distinct \
  tests/test_prop_oos_qualification.py::test_observed_complete_months_and_family_tail
```

For an existing committed native report's independent ledger audit:

```sh
.venv/bin/python scripts/verify_native_portfolio_report.py \
  docs/evidence/qualified_prop_sim/native-portfolio/analysis.zip
```

## Implementation map

These owners define the behavior; versioned saved artifacts are authoritative
for an individual historical report. Future numerical edits should update this
guide and preserve old report identities.

| Concern | Owner |
| --- | --- |
| Qualification, source check, form declarations, OOS admission/reuse | [`prop_sim.py`](../alphaquest/prop_sim.py) |
| Page-independent automatic continuation and freezing | [`prop_sim_automation.py`](../alphaquest/prop_sim_automation.py) |
| Automatic IS-only size-family policy | [`prop_sim_selection.py`](../alphaquest/prop_sim_selection.py) |
| IS/OOS candidate binding and durable campaign freeze | [`research_campaigns.py`](../alphaquest/research_campaigns.py) |
| Source adaptation, period/sizing contracts and calendars | [`phase_profiles.py`](../alphaquest/prop/phase_profiles.py), [`phase_search.py`](../alphaquest/prop/phase_search.py) |
| Commission replacement | [`commissions.py`](../alphaquest/prop/commissions.py) |
| Daybook and profile dispatch | [`native_analysis.py`](../alphaquest/prop/native_analysis.py) |
| Apex/Lucid local account transitions and sampler | [`native_engine.py`](../alphaquest/prop/native_engine.py), [`lucid_engine.py`](../alphaquest/prop/lucid_engine.py) |
| Evaluation attempts, dated acquisition and chronological replay | [`evaluation_profiles.py`](../alphaquest/prop/evaluation_profiles.py) |
| Evaluation IID economics, Pareto, assessments and artifacts | [`evaluation_optimization.py`](../alphaquest/prop/evaluation_optimization.py) |
| Funded dated account paths, receipts and chronological replay | [`funded_profiles.py`](../alphaquest/prop/funded_profiles.py) |
| Funded metrics, constraints, ranking and assessments | [`funded_optimization.py`](../alphaquest/prop/funded_optimization.py) |
| Historical OOS qualification policy and verdicts | [`oos_qualification.py`](../alphaquest/prop/oos_qualification.py) |
| Outer-history refits and bounded process runtime | [`oos_bootstrap.py`](../alphaquest/prop/oos_bootstrap.py), [`parallel.py`](../alphaquest/prop/parallel.py) |
| Distribution summaries, business revisions and account-start replay | [`assessment_review.py`](../alphaquest/prop/assessment_review.py) |
| Durable analyses, checksums and progress | [`store.py`](../alphaquest/prop/store.py) |
| Native portfolio qualification/source spools | [`prop_portfolio.py`](../alphaquest/prop_portfolio.py), [`portfolio_sources.py`](../alphaquest/prop/portfolio_sources.py) |
| Native risk sizing and portfolio allocation/lifecycle/budget | [`sizing.py`](../alphaquest/prop/sizing.py), [`portfolio_search.py`](../alphaquest/prop/portfolio_search.py), [`portfolio_lifecycle.py`](../alphaquest/prop/portfolio_lifecycle.py), [`portfolio_cash.py`](../alphaquest/prop/portfolio_cash.py) |

All production calculations described here are local to AlphaQuest. No Bridge
executable, external report table or notebook result is used as the runtime
calculator. Provider-rule review, broker/fill parity and prospective execution
validation remain separate from historical numerical correctness.

### Exact acceleration of internal historical refits (2026-11-14)

Internal refits now capture only phase means and their required precision. Each
account still runs to the same outcome or guard. Full published IS/OOS point
simulations retain their detailed evidence. Immutable calendars and independently
seeded RNG prefixes are reused within a worker with a 32 MiB accounted budget;
misses use the original stream. No history, path, retry or criterion is removed.
The matching compiled Lucid calendar/Apex renewal loops share their phase owner's
source with the Python reference. Funded uses its existing account transitions.

Compatible retries restore checksummed completed outer refits from the existing
catalogue, run missing indices only, then publish the same complete ordered family.
The progress panel in both Prop Sim and Job history labels restored work. Its
rate/ETA excludes those already completed indices. Source/rules/costs/seeds and
numerical/runtime implementation must match. Partial work does not establish a
qualification verdict; a source/implementation update needs a new simulation.
Pre-update running work has no retroactive checkpoints. See the
[contract and saved numerical evidence](evidence/qualified_prop_sim/refit-acceleration/README.md).

## Percentage policies in the independent phase optimizers (2026-11-15)

The current implementation and exact source/execution, sampling and qualification
contracts are in [Independent percentage-risk searches](prop_simulation.md#independent-percentage-risk-searches--2026-11-15).
The campaign's one-contract dollar/planned-R research evidence remains separate
from the native percentage policy's Prop Sim qualification.

Example: a 0.20% initial-capital policy requests USD 100 from the declared
USD 50,000 account. With a known 20-point MNQ stop and USD 0.50 per-side commission,
zero slippage gives USD 41 unit planned risk, hence two MNQ and USD 82 planned
risk. A 40-point stop gives USD 81 unit risk, hence one MNQ. Unit risk above
USD 100 skips that opportunity. Actual next-open gaps, account caps, withdrawals,
subsequent opportunity eligibility and provider stops are resolved natively.
This is not a retrospective multiplication of baseline trades.

Evaluation and Funded retain independent objectives and separate grids. An outer
historical refit changes each IS/OOS catalogue's origin frequencies, then reruns
that phase's entire frozen native estimator at the original path count. It does
not mix the two histories, reselect a percentage, or bootstrap the already saved
account outcome list. The result's new native resampling identity and original
source hashes distinguish it from older fixed-contract historical refits.

## Current default qualification: complementary evidence v2 (2026-11-15)

The current automatic Prop Sim assessment no longer runs the nested historical
refit procedure described in the dated sections above. See **Complementary Prop
Sim evidence replaces nested refits** in `prop_simulation.md` for the complete
measurement, budget and interpretation contract. New fixed-contract and native
percentage-risk runs use 5,000-account IS/OOS comparisons, finite acquisition
windows, coverage-only chronological starts and five 1,000-path stress scenarios.
Conditional Monte Carlo error, historical-period sensitivity and supplied forward
execution evidence are shown separately. No historical confidence interval or
equivalent old-policy confidence claim is produced. Sealed v1 reports remain
unchanged and readable under their original policy.
