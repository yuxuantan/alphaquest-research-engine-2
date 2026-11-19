# Saved-trade percentage-risk Prop Sim

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
