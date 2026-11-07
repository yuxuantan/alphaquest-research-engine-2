# Prop portfolio implementation plan

7 November 2026: [robust research](robust_research_plan.md) now has an initial
inner-window execution/qualification increment. Independent policy selection,
frozen chronological outer replay and common-horizon pair comparison remain
pending there. Existing dated phase-source and exact budgeted cash milestones
below are retained; payouts still cannot expand the monthly fee cap.

Accepted 2026-11-04. This plan extends [prop simulation](prop_simulation.md)
through its existing backtest → configure → check → run → durable report journey.

## Prerequisite research workstream — updated 2026-11-06

[Independent phase optimization](phase_optimization_plan.md) is the prerequisite
research workstream for future optimizer-driven portfolio recommendations.
The implemented Evaluation campaign minimizes acquisition cost and calendar time
through an estimated Pareto frontier; the implemented Funded campaign maximizes
horizon cash payouts conditional on already being funded. They can search saved trials across strategies/jobs independently, then
freeze selections before manual final OOS assessment. Neither uses the other's
objective inputs. The existing annualized joint-sizing calculation is classified
as legacy business-level optimization and remains preserved.

This is **not a replacement or restart of completed milestones 1–2** below.
Separate phase sources, dated transitions and the exact cash ledger/monthly-cap
scheduler remain implemented capabilities with their existing evidence. They
replay fixed choices on one observed path; separate campaigns now optimize each
phase independently above that replay. The phase work adds research selection above these
primitives and retains the cash accounting and hard-cap contract unchanged.

The original five-milestone roadmap and progress entries below are retained.
Milestones 3–5 remain pending portfolio work; portfolio optimization is optional
and outside the initial independent-phase implementation. A future portfolio
optimizer may consume frozen phase outputs and synchronized source paths to
maximize finite-horizon trader cash under the spending cap. It must model
dependence and timing rather than combine marginal summaries or feed joint
annualized scores back into phase selection. Phase-level OOS freeze is delivered
by the new plan; portfolio-level allocation/OOS validation remains separate.

The **saved-candidate product prerequisite is implemented and regression-qualified**
as recorded in the [cleanup evidence](prop_simulation_review.md#final-architecture-cleanup--2026-11-06).
The full original phase research exits remain partial: generated grids, adaptive
confirmation, simultaneous frontier certification, verified calendars/settlement
and numerical/provider parity are unclaimed. Do not label the entire research
prerequisite complete. Next portfolio work is milestone 3's smallest fixed-plan,
separate-account comparator: saved frozen phase choices, synchronized observed
sources, exact fee/receipt timing, zero-purchase baseline and the unchanged hard
monthly fee cap. Expand bounded separate-account search within milestone 3.
Milestone 4 is shared-account execution/placement and stays deferred until combined
exposure/risk can be reconstructed. Milestone 5 adds portfolio-level freeze/manual
OOS. No portfolio implementation is added here.

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

- 2026-11-05: Added the independent-phase prerequisite specification and migration
  boundary. Documentation only; no new optimizer, forecast, test qualification
  or portfolio milestone is claimed. Existing milestone-1/2 evidence is preserved.
