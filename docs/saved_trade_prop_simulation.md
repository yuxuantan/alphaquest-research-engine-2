# Saved-trade Prop Sim

Current portal model: **`saved-trade-account-policies-v2`** (2026-11-20).
Both fixed-contract and percentage searches expose independent Evaluation and
Funded trade-handling settings. See [Account-policy v2](#account-policy-v2).
The v1 description below explains historical sealed reports and compatible
legacy API requests; it does not describe newly configured portal runs.

## Historical stop-budget v1

Implemented model: `saved-trade-stop-budget-v1` (2026-11-20).

This replaces per-account minute-bar replay for new percentage-risk searches in
the main Prop Sim workflow, for Apex 50K EOD and LucidFlex 50K, independently
in Evaluation and Funded. It also applies to their frozen OOS comparisons,
chronological starts and predefined sensitivity checks. Fixed-contract searches
keep their existing calculation law. Old sealed reports retain their original
model, evidence and verdict; they are not converted into results of this model.

## What is simulated

A source is a qualified campaign's saved, nonoverlapping, session-flat trade
schedule. Each trade supplies its saved price outcome and a **causal submitted
entry reference and initial protective stop**. MAE, MFE and future entry fills
are not sizing inputs. An absent stop is an error, not an invitation to infer
one from the eventual loss, MAE or optimized account outcome.

Verified decision sidecars are reused when available. Otherwise the ordinary
strategy/execution engine replays the original dataset and selected dates once
to recover submitted plans, including both sides of OCO orders before the actual
selection. Every resulting completed trade must match the original CSV exactly.
The metadata records this reconstruction, its implementation and content hash.
Original reports remain unchanged. A mismatch requires a new qualified backtest.
Verified derived plans also use the existing bounded ReplayCache, guarded by raw
source bytes and strategy/adapter/execution identity; the cache is disposable and
is not a second evidence store. Cold recovery can take one source backtest.
This one-time preparation is shared across policies; no strategy, indicator or
minute-price replay runs inside an account Monte Carlo path.

The model deliberately freezes the **opportunity schedule**. A skipped trade
does not reveal alternative setups or alter later entries, stops or targets.
This is a declared counterfactual assumption, not proof of signal invariance for
an account-aware live strategy. Strategies with quantity-dependent source trades
or unsupported fixed-path scaling are rejected by their sizing contract.

## Entry admission and quantity

At each saved opportunity, read only account state available before that entry.

1. Compute budget `B = reference * risk_percent / 100`. Reference is explicitly
   initial configured capital (USD 50,000), current account balance, or available
   account drawdown cushion. A fixed-dollar policy has its declared dollar budget.
2. Read remaining allowances `A = equity - account_floor` and, when enabled,
   `D = equity - daily_floor`. Floors use the existing provider-rule owners;
   these are EOD trailing models, not intraday-high-water trailing accounts.
3. Reject if `B >= A` or `B >= D`. Equality is rejected because touching a floor
   is a limit event. This check uses the **requested budget**, before contract
   rounding or provider caps. Do not silently reduce the budget to fit.
4. Compute loss per MNQ `U = abs(reference_price - stop_price) * 2`, plus declared
   loss-side entry/stop slippage and round-trip commission. Prices obey tick size
   0.25. The stop must be adverse and known no later than the submission.
5. Requested quantity is `floor(B/U)`, capped by the policy ceiling, user ceiling
   and current provider account tier. If below one contract, skip; never force
   one contract and exceed the risk budget.

Example: 0.5% of USD 50,000 is USD 250. With a five-point stop and USD 0.50
commission per side, `U = 5*2 + 1 = 11`, so quantity is 22 MNQ and planned loss
is USD 242 before lower provider caps. If only USD 125 remains for the day,
the opportunity is rejected even if a provider cap would reduce quantity to one.

## Outcome and execution assumptions

The initial protective stop is assumed active immediately, never widened beyond
the admitted risk, and filled at the modeled stop price with declared costs.
Account-limit liquidation also assumes a fill at the limit. Price-gap overshoot,
latency, queue effects, partial fills and size-dependent signals are excluded.

Saved net price outcomes retain source slippage and replace the original
commission with the selected MNQ commission exactly once. Normalize NQ to MNQ
exposure (ten MNQ per NQ), divide out the saved source quantity, then multiply
by the admitted whole-MNQ quantity. Before scaling, bound a negative outcome by
the planned per-MNQ stop loss. Record this bounding explicitly. Costs used to
plan quantity are **not deducted a second time**.

Positive saved outcomes remain positive saved outcomes: the model does not
reconstruct whether a hypothetical earlier protective stop would have removed
a later winner. It must not be advertised as exact execution replay or as a
measured improvement to the campaign strategy. It is the user-approved bounded
saved-outcome research law. Original backtest and execution sensitivity evidence
remain relevant separately.

Because admitted stop loss is strictly below both allowances, MAE/path crossings
are unnecessary for this account-limit calculation. The kernels receive the
bounded realized loss, not source MAE. Limits stop the session; account breaches
terminate the account. Under ideal stop fills and strict admission, such breaches
are largely prevented by construction. Zero simulated breach probability is
therefore **not evidence of resilience to real gaps**. Inactivity, expiry,
consistency, fees, restricted funding deadlines and payout eligibility can still
make a policy unattractive or unresolved.

## Sampling, account rules and assessment

Existing phase owners retain weekday-block sampling, zero-trade weekdays, seeds,
calendar closures and all requested paths. Evaluation pays for every retry,
stops at funding/activation or its explicit guard, and reports all-path cost and
time; it never averages only successful paths to manufacture a finite mean.
Lucid retains calendar inactivity, consistency and its computation guard. Apex
retains the independent attempt/renewal owner and account deadline.

Funded starts from a fresh account, runs its frozen calendar horizon, and uses
existing provider tiers, qualification days, payout deductions, trader shares
and receipt dates. Pending entitlements are not cash received. There is no
implicit replacement Funded account in this objective.

IS searches and automatic selection remain independent by phase. The policy,
costs, source, assumption/model identity and selected family freeze before Prop
Sim OOS. OOS runs exactly those choices, never replacements. Complementary
evidence uses the **same sizing law** in all baseline, stress and chronological
scenarios; zero nested historical refits remain the default. An assessment does
not make an already-accessed holdout untouched or authorize live deployment.

## Why the former mechanics were replaced

Per-path native replay recalculated account-dependent orders and traversed minute
prices to resolve intratrade floors. Its fidelity was useful when skips changed
signals, stops could slip through floors, or order priority mattered. It also
required expensive source spools, warmups, event preparation, price traversal
and worker transfers on thousands of long acquisition paths.

The approved model instead fixes the opportunity schedule, rejects oversized
budgets and assumes exact stop/limit fills. Reconstructing alternate setups or
intratrade liquidation timing adds computation without changing that model's
declared outcomes. New main-portal percentage searches therefore no longer build
native-execution declarations or dispatch native percentage simulations.

Native campaign execution, standalone native API compatibility, portfolio
controllers and historical numerical readers still have independent callers.
Their code is retained for those purposes; deleting them would remove unrelated
features and break old evidence. They are not a hidden fallback for the new
saved-trade percentage optimizer. Numerical/model changes invalidate old frozen
packages for new execution; original downloadable reports remain readable.

## Account-policy v2

The portal always declares `evaluation_trade_handling` and
`funded_trade_handling`, each with `account_limit_action` (`skip` by default,
or `exit_at_limit`) and `minimum_one_contract` (false by default, percentage
searches only). These declarations become each candidate's `SizingConfiguration`
and freeze with its source, costs, model identity and IS selection. Frozen OOS,
stress, precision and chronological-start assessments carry the same settings.
Changing settings creates a new simulation; it never revises an old IS package
or reselects in OOS. API requests omitting these additive declarations retain
their historical route for compatibility. Native portfolios and standalone
native execution remain separate and unchanged in scope.

### Causal quantity and account admission

For a percentage policy, compute dollar budget B from its declared reference.
Calculate unit planned risk U from the known submitted entry reference, initial
protective stop and declared loss-side costs, as in v1. Quantity starts at
floor(B/U). An enabled minimum-one option raises zero quantity to one only when
B is positive. Apply provider tiers and user/policy ceilings; the option cannot
defeat zero capacity or restore a terminated account. Fixed policies start from
their declared contract count and retain provider caps.

Compute intended whole-position risk Q*U **after caps**, then read current
remaining account and enabled daily allowances. In `skip` mode, touching or
exceeding either allowance rejects the trade; never silently shrink Q to fit.
This intentionally supersedes v1's requested-budget-before-caps rejection.
For example, a requested $2,000 budget capped to one $11-risk MNQ can trade with
$12 remaining, but cannot trade with $11 remaining. Admission never uses MAE.

With minimum-one on, a $5 budget and $11 unit risk trade one MNQ if the account
policy admits it. Record $11 actual planned loss and 0.022% of a $50,000
reference; do not label it as 0.01% risk. With minimum-one off it skips. If the
one contract exceeds an account allowance, the account-limit action still owns
the outcome: skip, or enter with an account-limit exit. The override is rejected
for fixed contracts. Account-cushion quantity-reducing guards cannot be combined
with v2: its two explicit actions own this decision.

### Captured excursions and ideal account-limit exits

`exit_at_limit` requires valid captured source excursions for every source trade,
including winners and excluded dates. Missing excursions reject with instructions
to capture them or choose Skip. A realized-loss fallback is never sufficient.
Existing native risk CSVs retain checksums; commission adaptation stays shared
and occurs once. Tick observations, MultiCharts modeled OHLC paths, conservative
held-OHLC upper bounds and measured exports retain distinct provenance. An OHLC
bound is not relabeled measured tick MAE.

Bound modeled losing outcomes and adverse loss at the initial protective stop
under the immediate, non-widening, ideal-stop assumption. Scale cost-adjusted
captured adverse loss to Q. If it reaches the nearer account floor, replace the
saved outcome with a loss ending **exactly at that floor**. Account floor wins
a tie. Daily hits pause the rest of the session; account hits terminate that
account (Evaluation retries stay with the existing retry owner). A later winner
can become a limit loss. Never size from MAE, infer new setups, deduct another
exit fee after a cost-inclusive exact limit loss, or retain a post-breach winner.

This shortcut assumes nonoverlapping positions, fixed intratrade daily/EOD-account
floors, loss limits that end trading for the session, and exact threshold fills.
It cannot reconstruct an intraday high-water trailing floor or synchronized
multi-position portfolio from scalar MAE. Gap overshoot, latency and liquidity
remain excluded. Full original entry/exit fidelity is not claimed.

### Diagnostics and interpretation

All visited eligible opportunities are aggregated. Skip rate uses visited
opportunities; account-limit-exit and over-budget rates use admitted entries.
Later opportunities after funding, mandatory pause or account termination are
excluded, rather than counted as affordability skips. Repeated Monte Carlo visits
are explicitly distinct from the unique original `source_trade_count`.

For each sizing row, IS and OOS expose skipped counts/rates and reasons,
account-limit exits split into daily pauses and account breaches, over-budget
entry counts/rates, and mean/maximum actual planned risk as a percent of its
reference (initial $50,000 for fixed contracts). Examples include causal risk,
quantity, before/after state and reason. Any nonzero deviation is a review warning;
no arbitrary automatic eligibility threshold is imposed. Unresolved IS sizes
also retain these diagnostics. Large deviations call for reviewing account fit
and strategy fidelity in a new IS study, not replacement selection in OOS.

Existing report JSON, `sizing_summary.json`, `sizing_decisions.csv`,
`saved_trade_model.json` and sealed evidence ZIP retain policy, provenance and
counters. Complete summaries survive the existing individual trace-detail bound;
examples are separately bounded. Complementary baseline/stress summaries carry
their own counters. Original reports and v1 verdicts are never rewritten.
