# Prop portfolio implementation plan

Accepted 2026-11-04. This plan extends [prop simulation](prop_simulation.md)
through its existing backtest → configure → check → run → durable report journey.

## Accepted scope

Optimize expected net cash over a configured horizon under a hard monthly
 evaluation-plus-activation spending cap. Payouts never expand the cap and unused
allowance expires monthly. Evaluation and funded phases may use separate saved
strategies, parameters and fixed sizes. Selections remain fixed within each phase;
mandatory provider scaling and risk limits still apply. Start with Apex 50K EOD,
LucidFlex 50K and NQ/MNQ, selected saved backtests/optimization trials. Ultimately
compare portfolios of separate accounts and strategies sharing one account.
Deliver research recommendations and allocation exports, without trading approval.

## Five milestones

1. **Separate phase sources and dated lifecycle.** Configure/check both sources,
   fixed sizes, source membership/protection/identity, chronological evaluation,
   eligibility/delay and subsequent funded observations; phase metrics and trace.
2. **Exact cash ledger and monthly budget.** Dated evaluation/activation spending,
   payout receipt assumptions, horizon, expiring monthly allowance and hard cap.
3. **Synchronized simulation and optimization across separate accounts.** Common
   market observations, dependence, joint allocations and budget-constrained search.
4. **Shared-account execution and combined placement optimization.** Combined
   exposure, netting/placement, account risk and mixed shared/separate allocation.
5. **Frozen OOS validation and recommendation export.** Freeze selections before
   untouched validation; research recommendations, provenance and allocation files.

## Shared delivery requirements

AlphaQuest calculates locally. No external Bridge runtime or generated production
inputs. Use AnalysisStore and existing report/API/UI routes; no demonstration-only
screen/API or duplicate report store. Preserve previous reports/evidence, source
datasets/backtests, other processes and the Windows VM. Reconcile costs once and
version changed models. Deliver minimum usable UI/API with each backend increment,
meaningful automated checks, normal-workflow demonstrations, independent expected
values and rejection/boundary cases. Fixture oracles stay in tests. Save inspectable
evidence/downloads, exact reproduction/reopening/start/stop steps and expected
observations. Update prop_simulation.md and prop_simulation_review.md. Stop owned
temporary servers. Never fabricate unresolved or future outcomes or claim untested
numerical/provider parity. Annualized renewal assumptions remain labelled until
the later cash/budget model is delivered.

## Implementation progress log

- 2026-11-04: Read required project instructions and specification/review,
  architecture and research workflow. Clean starting worktree. Plan created
  before implementation. Milestone 1 in progress; milestones 2–5 pending.
- 2026-11-04: Implemented optional dated phase configuration, independently
  reconciled evaluation/funded sources, shared observed window, fixed-size
  suitability/risk checks, both-source catalogue membership/deletion protection,
  versioned request identity and normal durable reports/downloads. Evaluation
  sessions now share arithmetic between sampled and dated paths. Existing funded
  transitions supply dated trading, provider scaling and first-limit trace data.
  Kernel/first-breach gate: 56 passed, two standard-count cases deselected.
  Normal API/browser demonstrations and storage/regression gates in progress.
- 2026-11-04: **Milestone 1 complete; milestones 2–5 pending.** Final product
  workflow demonstrates same source, changed funded parameters only at fixed
  10/3 MNQ, a different funded VWAP strategy, incompatible source, recovering
  winning-trade breach, and Lucid zero-extra-wait switching. Separate NQ/MNQ
  fixed-quantity sources normalize once. Final source admission also rejects
  partial phase settings, naive timestamps, disjoint windows, conflicting
  calendars and inherited open positions. Shared Python evaluation sessions
  retain equivalent specialized compiled hot loops for existing simulation speed.
  116 distinct targeted pytest checks passed, including standard-count compiled
  parity, persistence/deletion/reuse and browser work; final current-code UI
  journeys and independent Decimal/date payout ledgers passed. Report and trace
  IDs, exact commands, expected observations and remaining limits are recorded
  in prop_simulation_review.md. Evidence: artifacts/prop-portfolio-m1-20261104/.
  All 10,245 inventoried original source/report files remained unchanged; all
  owned servers stopped. No persistent server, commit or remote push was made.

- 2026-11-04: Milestone 2 implementation adds optional budgeted dated mode to the
  normal configure/check/run/report workflow: exact purchase/activation fees,
  activation-priority reservations and reset policy, modeled settlement timing,
  dated cash/monthly downloads, fixed sources and one initially unfunded slot.
  Original milestone-1 gate: 13 passed; independent saved payout/date oracle
  matched all five prior demonstrations before extension. Final qualification,
  preservation audit and review documentation are in progress.
- 2026-11-04: **Milestone 2 complete; milestones 3–5 pending.** Budgeted dated
  mode demonstrates exact $30 + $30 + $40 = $100 paid spending, failed-attempt
  release, blocked replacement, reset/re-reservation, activation expiry, pending
  obligations and an after-horizon modeled receipt through the normal UI/API and
  durable report/downloads. 75 distinct focused checks passed; the independent
  standard-library oracle conserved all 154 saved ledger rows and verified 115
  ZIP hashes. Final UI reopening reused every report ID and preserved all 258
  fixture files. All 42,664 inventoried original source/report/evidence files
  stayed unchanged. IDs, independent expected rows, commands and limitations
  are in prop_simulation_review.md; evidence is
  artifacts/prop-portfolio-m2-20261104/. All owned temporary servers stopped;
  no persistent server, commit or push. One observed path/slot is supported;
  future projections, synchronized portfolios and allocation search remain later
  milestones. Receipt/activation timing and post-closure payment remain explicitly
  unverified scenario assumptions, without new provider/Bridge parity claims.

- 2026-11-05: Standalone dated lifecycle is removed from the portal method
  selector. Its calculation code and saved reports remain supported. Earlier
  reports offer **Configure budgeted analysis**, retaining their phase sources
  and sizes while requiring budget, dates and timing assumptions. This is a
  presentation/workflow change; portfolio comparison and selection remain pending.
