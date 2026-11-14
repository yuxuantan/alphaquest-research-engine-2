# Campaign edge research and independent percentage-risk optimization

Status: **implementation covers M0–M7; final release verification is recorded in
`docs/prop_simulation_review.md`**. The initial capacity checkpoint is historical;
it is not the current implementation boundary.

| Milestone | Current implementation |
| --- | --- |
| M0 | Exact contracts and native origin-frequency law; real NQ source admission, including the reviewed pre-June-2021 venue pause. |
| M1 | Planned-R evidence, coverage and campaign/report integration; screening gates unchanged. |
| M2 | Disjoint fixed/percentage contracts, exact independent grids, full policy identity and percentage-aware automatic selection. |
| M3 | Native causal Evaluation/Funded execution for both accounts, including actual quantity, skips, caps and cash transitions. |
| M4 | Prepared event/price indexing, bounded prefixes/uniforms, checksummed read-only worker source, full counts, four-worker progress and existing checkpoints. |
| M5 | Frozen OOS forecast plus chronology and separately versioned full-count two-history qualification. |
| M6 | Main portal percentage controls, initial budgets, automatic IS selection/freeze/OOS and policy-aware tables/charts. |
| M7 | Existing percentage-aware supplied-event forward review, immutable historical compatibility, documentation and inspectable product evidence. |

The initial M1-only delivery and capacity findings remain preserved in the dated
implementation review. See the later independent percentage optimizer section for
current reproduction, actual outputs, verification scope and measured capacity.

Prepared 2026-11-14 for `epic/revamp-workflow`, following the percentage-risk
research-design discussion. Production behavior continues to be defined by
[workflow screening](workflow_screening.md), [prop simulation](prop_simulation.md)
and [its methodology](prop_simulation_methodology.md). This plan proposes an
additive extension; it does not change any current passing criterion.

## 1. Target user journey

1. Create a campaign with a dataset, strategy parameters and an explicit IS/OOS
   split. Use one contract with strategy-local risk sizing disabled as the default
   edge-research baseline.
2. Complete mechanic validation, then Broad and Narrow research. Inspect both
   ordinary dollar results and clearly labeled planned-R diagnostics. R statistics
   do not add automatic admission gates in this increment.
3. Freeze the strategy configurations and assess the existing campaign OOS and
   full-period Monte Carlo requirements. Preserve all prior-access disclosures.
4. From a qualified configuration, open the existing Prop Sim page. Select an
   account profile and fixed-contract or percentage-risk search. Percentage mode
   has independent Evaluation and Funded grids, bases and contract caps.
5. Click Run once. Source admission, IS simulations, automatic candidate-family
   selection, freezing and OOS qualification continue in existing workers after
   navigation away. No intermediate confirmation is required.
6. Read one concise result summary per phase, with full comparison tables and
   audit downloads available. Inspect the selected percentage policies, their
   actual quantities and their account economics.
7. A historical GO leads to the existing paper execution review. Reconcile the
   same frozen sizing policy against genuinely recorded forward decisions/fills.
   Inconclusive or failing results give the existing explicit next-step guidance.

One account profile is selected per independent run. Support Apex 50K EOD and
LucidFlex 50K, each with independent Evaluation and Funded calculations. This
creates four required profile/phase qualification cases, not a joint objective
or an automatic cross-provider winner.

If strategy behavior depends on quantity, account equity or accepted/skipped
orders, one-contract research establishes only that baseline's edge. The intended
sizing policy must receive a separately identified end-to-end assessment before
paper/live deployment. Where it changes campaign trading logic, introduce/freeze
it before that strategy's final campaign OOS assessment. Never relabel previously
accessed data as untouched after this change.

## 2. Research decisions and scope boundaries

- One contract is a controlled research default, not proof of constant risk or a
  universal research requirement. Preserve existing non-one-contract reports and
  deliberate alternative workflows; label their baseline instead of changing them.
- Inspect risk-normalized diagnostics from the first eligible backtest. A later
  high-volatility period can dominate fixed-contract dollars, and positive dollar
  expectancy does not imply positive equal-risk expectancy.
- Keep strategy-parameter optimization in Campaigns and sizing optimization in
  Prop Sim. Do not cross percentage grids with Broad/Narrow strategy grids here.
- Preserve current mechanics/Broad/Narrow/OOS/Monte Carlo admission policies.
  Additional R diagnostics do not alter existing counts, manual parity checks or
  historical verdicts. A new automatic R gate needs a separate policy decision.
- V1 uses one qualified strategy configuration per independent run, matching the
  current portal. Generalizing strategy admission is a later capability.
- Default percentage reference: initial configured capital. This is a stable
  planned-dollar budget. Existing current-balance and available-drawdown-cushion
  references can be advanced choices, fixed separately for each phase.
- Optimize percentages, not the percentage reference or contract cap. Caps and
  guard settings are frozen constraints. Strategy-local sizing remains disabled
  when the account controller owns quantity.
- Evaluation minimizes acquisition cost and calendar time through its full Pareto
  frontier. Funded maximizes received trader cash over the frozen horizon from a
  fresh funded account. No acquisition inputs enter Funded selection.
- Existing fixed-contract behavior, reports and portfolio objectives remain.
  This does not add portfolio Monte Carlo or independent replacement cash flow.

## 3. Design-time foundations and gaps (historical inventory)

| Surface | Implemented foundation | Work required |
| --- | --- | --- |
| Causal stop evidence | `decision_capture.py`, `canonical_trades.py` retain decision references, known initial stops and verified trade/cost identity where available. | Instrument-aware planned-R measurements, coverage status, report/table integration and legacy handling. |
| Quantity arithmetic | `prop/sizing.py` supports fixed contracts, dollar risk and three percentage references with whole-MNQ rounding and explicit optional cushion guards. | Generalize independent search contracts and candidate identities without overloading the legacy fixed `micros` field. |
| Native execution | `prop/native_control.py`, `native_draws.py`, `native_replay.py`, `native_search.py` support controlled strategy/execution and observed-block forecasts. | Qualify the complete new workload, calendar/retry semantics, all required profile cases and supported path counts. |
| Independent objectives | Phase profiles and `evaluation_optimization.py` / `funded_optimization.py` already own account simulation and metrics. | Route percentage candidates through native execution while retaining those owners and objectives. |
| Main portal | `prop_sim.py`, `web/prop-sim.js` admit one qualified configuration and declare fixed-contract phase ranges. | Typed percentage grids, source-capability checks, quantity diagnostics and mode-aware presentation. |
| Automatic selection | `prop_sim_selection.py`, `prop_sim_automation.py` choose/freeze families and launch OOS. | Policy-aware labels/tie-breaks and immutable percentage policy selection. |
| OOS qualification | `prop/oos_qualification.py` uses 10,000 historical refits and currently explicitly rejects non-null sizing. | A versioned native percentage estimator and independently qualified historical resampling law. Removing the rejection is insufficient. |
| Execution infrastructure | Existing AnalysisStore, bounded Runtime, source capture, stop, canonical reuse, progress and completed-refit checkpoints. | Include native source/catalogue/schedule/policy identity and publish mode-aware progress. |
| Forward review | Existing supplied-event monitor and frozen policy comparison. | Reconcile percentage quantity decisions, skipped entries, caps and account state as well as fills. |

At design time the native forecast request was bounded to 512 paths and 365 calendar days;
its search also has separate bar-work, schedule and capture bounds. The normal
Prop Sim form supports 8–20,000 paths, and Evaluation acquisition can have a
3,650-day computation guard. These are **real implementation gaps**. Do not
silently lower a requested count/horizon, remove all native bounds, or present
an unsupported workload as qualified. M0 and M4 must resolve these differences
through streaming/compilation and measured capacity before enabling the full mode.

## 4. Define the measurements before implementation

### 4.1 Planned initial risk and R

For a completed baseline trade with a verified causal initial stop:

```text
distance = side_sign × (decision_reference_price - initial_stop_price)
unit_planned_risk = distance × instrument_point_value
                  + (entry_slippage_ticks + stop_exit_slippage_ticks)
                    × tick_size × instrument_point_value
                  + entry_commission + planned_stop_exit_commission
trade_planned_risk = filled_quantity × unit_planned_risk
planned_net_R = actual_trade_net_PnL / trade_planned_risk
```

- The decision reference and initial stop must be known by the sizing decision.
  Do not use a later modified stop, realized loss, MAE/MFE or future fill to size
  the entry. Keep signal timestamp and actual entry-fill timestamp distinct.
- Label the result **Planned net R**, and save this exact versioned denominator
  definition. Commission/slippage assumptions are explicit and reproducible.
- For campaign diagnostics, use that report's instrument, point value, declared
  execution assumptions and quantity. The current Prop Sim `PlanningExecution`
  contract is MNQ-specific; do not reuse its USD 2 point value for an NQ/ES report
  or loosen that MNQ admission guard simply to compute research diagnostics.
- A shared instrument-aware pure loss calculation should serve diagnostics and
  the MNQ sizing caller. Keep account/quantity decisions in the existing sizing
  owner. A possible small owner is `alphaquest/risk_metrics.py`; avoid a second
  account simulator or a second interpretation of commissions.
- Costs in the denominator describe planned loss. They are not subtracted from
  the already net trade P&L a second time.
- Actual-fill-to-initial-stop risk is a separate after-fill diagnostic. It can
  expose gaps and a stop on the wrong side of the actual fill. It must never be
  fed backwards into a next-open sizing decision.
- Missing/invalid/nonpositive risk produces an unavailable value and explicit
  coverage reasons. Never substitute zero, infer a stop, or quietly exclude
  missing trades and present the resulting mean as full coverage.

### 4.2 Initial campaign diagnostic set

Show valid/total trade coverage, mean and median planned net R, total planned
net R, net-R distribution/worst trade, and complete-month mean R with trade counts.
A cumulative closed-trade R chart may be offered as a diagnostic; its drawdown
is labeled closed-trade R drawdown, not dollar MTM drawdown or a tradable equity
curve. Partial months follow existing declared/observed-window conventions.

Show the current dollar results alongside these measurements. No Sharpe-like
ratio or new significance gate is introduced here. Missing R coverage does not
rewrite the campaign's existing eligibility; percentage-mode admission separately
requires complete native decision-time stop capability.

### 4.3 Percentage quantity

```text
budget = max(0, selected_reference_value) × risk_percent / 100
requested_quantity = floor(budget / unit_planned_risk)
quantity = min(requested_quantity, policy_cap, current_provider_cap, user_cap,
               any explicitly enabled account/daily-cushion planning caps)
if quantity < minimum_tradable_quantity: quantity = 0; skip entry
```

0.20 means 0.20%, not 20%. Initial-capital reference remains fixed at the declared
USD 50,000 model capital. Current balance responds to P&L and withdrawals;
available cushion is current equity minus the current account floor. Existing
optional planning guard defaults are retained and explicitly captured. Account
breach/DLL transitions always remain enforced independently of planning guards.
Gaps and actual fills can exceed the planned loss budget.

Illustrative oracle: 0.20% of USD 50,000 is USD 100. MNQ, a 20-point stop,
USD 2/point, USD 0.50 commission per side and zero slippage give USD 41 unit risk,
so quantity is 2 and planned total risk USD 82. A 40-point stop gives USD 81 and
quantity 1. Unit risk USD 101 produces a skip. These are arithmetic fixtures,
not recommended trading percentages.

## 5. Data contracts, identity and report storage

Introduce an explicit typed search axis: legacy fixed contracts or percentage
risk. A percentage candidate snapshots kind, exact decimal percentage, reference,
initial capital, minimum quantity, all caps/guards, planning execution costs,
profile/rules, phase, strategy parameters, source/windows/calendar and sampling.
The declared grid and complete attempted family remain in research provenance.

- V1 UI uses independent min/max/step controls for each phase and shows the full
  expanded percentage list and candidate count before Run. All grid arithmetic
  uses Decimal; require positive values/step, aligned endpoints, no duplicates
  and no hidden omissions. Normalize equivalent decimal spellings for identity.
- Keep percentage and fixed-contract request meanings disjoint. Reject conflicting
  fields. Do not reinterpret a legacy `micros` number as a cap or percentage.
- Phase-internal native anchors required by old interfaces must be explicitly
  separate from the actual sizing policy; selectors/reports cannot use an anchor
  as an executed size. Migrate those interfaces where ambiguity remains.
- `candidate_id`, calculation reuse and checkpoint identity include the entire
  sizing policy, source/price hashes, rules, source/target calendars, strategy and
  numerical implementation, native catalogue/sampling version and seeds.
- UI/docs-only changes retain numerical identity where computation is unchanged.
  Changes to risk calculation, account execution or sampling get honest new
  numerical identities. Never omit changed numerical code to reopen old freezes.
- Use existing backtest reports/AnalysisStore/campaign references. New reports
  may add versioned risk diagnostics at publication. Historical sealed reports
  remain unchanged. A verified saved sidecar can supply a separately sealed
  diagnostic assessment through existing report infrastructure without replay;
  absent causal evidence requires an explicit normal native replay/new source.
- A legacy source that lacks a valid causal stop cannot launch percentage mode.
  Show the precise missing capability and normal workflow to create a compatible
  source. Do not require reruns merely because a saved diagnostic is absent when
  all verified inputs already exist.

## 6. Campaign behavior

### Mechanic validation

Keep the single default-parameter Run and existing metric/trade parity checklist.
Show the research baseline quantity and sizing owner. For the default research
path, strategy-local risk sizing is off and one contract is used. Alternative
existing baselines remain labeled/readable. Put planned-risk/R evidence in a
separate diagnostic panel; do not silently add mandatory parity checkboxes.

Trade detail includes the decision reference, initial stop/known-at timestamp,
filled quantity, point value, planned costs, unit/total planned risk and net R.
An actual fill beyond the planned stop is visible as an execution diagnostic.

### IS Broad and IS Narrow

Keep current search axes, refinement, frozen selections, branch independence,
criteria and maximum carry-forward membership. Add opt-in R columns and a compact
coverage/diagnostic panel. Existing varied parameter visibility/freeze defaults,
2dp display and unrounded sorting/criteria remain. Sizing fields are not new
optimization axes in the baseline edge-research workflow.

An R/dollar disagreement prompts an explanatory review message. It does not
create a new automatic fail rule. Future general equity-dependent strategies
need an explicit sizing-dependent research mode with its own policy identity;
this increment initially supports the current native VWAP/EOD-flat capability.

### Campaign OOS and final Monte Carlo

Continue assessing the complete frozen strategy family under its saved baseline.
Optional planned-R summaries are evidence, not new final Monte Carlo tests.
Do not reuse the one-contract campaign verdict as proof that the percentage
policy passed. Prop Sim performs the separate frozen sizing assessment below.

An optional later constant-dollar-risk diagnostic replay can help investigate
R/dollar disagreement. It is not needed for the first release and must be
identified separately from the original baseline report.

## 7. Percentage simulations in the existing phase owners

Native execution must re-evaluate supported strategy callbacks, accepted/skipped
entries, fills, protective orders and account state for every policy/path.
Never resize the list of trades completed by a different policy and call it a
native percentage backtest. Account pauses can change subsequent opportunities.

Reuse `native_control.py`, `native_draws.py`, `native_replay.py`, `native_search.py`
and the existing execution engine. Restrict admission to supported, EOD-flat,
causal-stop strategies initially (currently VWAP), with unchanged source/price
coverage requirements. Reject unsupported sources clearly.

### Evaluation

Keep `evaluation_profiles.py` as simulation owner and
`evaluation_optimization.py` as objective/Pareto/report owner.

- Apex: generate the empirical joint first-attempt outcome/session-duration law
  using the native risk policy and existing deadline/account rules. Retain the
  independent fresh-attempt renewal/calendar model, every retry fee, activation
  and next-usable-session timing. Reuse the existing renewal arithmetic where
  its inputs satisfy that same law; do not silently substitute a different retry
  law or a Funded cash score.
- Lucid: retain the full dated acquisition model with native strategy execution
  inside each account attempt. Keep saved consistency variants, declared fee,
  fixed DLL assumption, 30-calendar-day inactivity, retry costs, closures,
  activation/readiness and computation guards. Do not substitute fee/pass-rate.
- Reset fresh-attempt account state appropriately. A current-balance/cushion
  percentage responds to the actual Evaluation account state within an attempt.
- Preserve all-path acquisition means and censoring. An open/unresolved tail
  withholds a complete mean; it cannot disappear from the denominator.

### Funded

Keep `funded_profiles.py` as owner and `funded_optimization.py` as metric/ranking
owner. Start each path with a fresh Funded account, enforce its current tiers and
DLL/trailing floor, and resize at each causal entry. Payout deductions change
account equity and therefore dynamic risk references. Preserve request/deduction/
entitlement/receipt separation and the exclusive receipt cutoff.

Rank all-start expected trader receipts over the declared horizon, including
zero-cash and breached paths. No Evaluation fee/time/pass rate, replacement
assumption or portfolio budget enters this objective. The breach cap remains
optional/default off; report breach risk as a diagnostic.

## 8. Monte Carlo law, historical confidence and freezing

### IS account simulation

Use the existing causal observed-block native forecast machinery. Blocks retain
original market paths and appropriate original-source prior-only feature warmup;
clock mapping/shape compatibility must follow the native calendar contract.
Never splice unrelated prices into a fabricated continuous price path or use
future source history to warm a decision. Carry/reset strategy and account state
only as the declared existing block/account model specifies.

Use index-addressed schedules shared across policies where valid. Different
policies may terminate/skip at different times; this must not accidentally shift
another path's random stream. Preserve full requested account counts and all
candidate membership. Native mode gets an explicit sampling/version identity;
it is not advertised as bit-identical to legacy fixed saved-trade resampling.

### Automatic IS-only selection

Retain existing roles, parameterized by percentage policy:

- Evaluation: lowest cost, fastest funding, and lowest cost within 1.25 times the
  fastest funding time; collapse repeated candidate IDs; at most three.
- Funded: highest mean receipts, and the lowest declared risk percentage retaining
  95% of that peak mean; collapse repeated candidate IDs; at most two.
- Use lower declared percentage then candidate ID for exact ties within the same
  phase/reference/constraints. A lower percentage is not certified safer.
- Preserve exact-tie frontier membership and every tested row. Equal estimated
  outcomes or rounded chart points do not prove distinct policies equivalent
  under other histories; do not deduplicate policies on that basis.

Freeze selected percentages, references, caps, rules, costs, windows, schedules,
policy/numerical identity and original sealed IS reports. OOS cannot tune them,
select a replacement or grow the selected family automatically.

### OOS point estimates and native historical refits

Run the frozen policies on OOS source blocks and an actual chronological OOS
account replay using the same policy/phase rules. Distinguish the single
chronological scenario from a Monte Carlo mean.

The current 10,000-refit `_means` implementation rejects variable sizing. Add a
native policy-aware estimator, not a rejection bypass. Design and qualify a
versioned outer historical law using the existing original-block-origin resampling
foundation (`native_draws.history_origin_weights`): independently resample IS and
OOS origin frequencies, retain original causal source paths/prefixes, then run
the full frozen inner estimator under those weighted histories. Preserve valid
calendar-shape pools without inventing missing observations. A required pool
with no admissible origin yields insufficient evidence, not a uniform fallback.

Proposed concrete outer law to freeze in M0 and verify in M5:

1. For each role (IS=0, OOS=1), keep the complete ordered native catalogue of
   original block origins. Let its length be N; source bars/prefixes remain intact.
2. Set the origin-index run length to `max(5, declared_inner_block_sessions)`.
   Draw circular runs over origin-index positions until exactly N indices have
   been sampled, truncating only the final run to reach N. This is a bootstrap
   of origin frequencies; the unit is an origin-index position, not a fabricated
   five-calendar-day price series.
3. Use master seed 13742. Derive a role seed with
   `SeedSequence([13742, role]).generate_state(1)[0]`; call the existing
   `history_origin_weights` with that role seed and the outer replicate index.
   Its current `[role_seed, replicate_index]` addressing is recorded in the new
   native policy identity. Index order, worker count and percentage order cannot
   change a refit's source history.
4. Within a required native calendar-shape pool, draw origin i with probability
   `origin_count[i] / sum(origin_count[j] for j in that pool)`. Preserve the
   original source prefix for each draw. Zero total pool weight is unavailable
   evidence; never redraw a convenient outer history or substitute uniform weights.
5. Run the full frozen inner estimator on IS and OOS weighted catalogues, retain
   both means/precision and compute each phase's economic OOS/IS ratios. Do not
   re-optimize a percentage inside a historical replicate. Save catalogue hashes,
   role/replicate seeds, weights hashes, inner schedule provenance and all results.

This is a separately versioned native resampling model, with overlap/stationarity
limitations; it is not promised to reproduce the old saved-daybook bootstrap's
numeric intervals. M0 must validate the declared block-origin units against the
catalogue builder before freezing this implementation contract. The existing native Funded lower-mean diagnostic is useful
infrastructure, but is not already the required two-history ratio qualification.
Record the changed native sampling law and its assumptions explicitly.

Retain the current economic policy by default:

| Test | Requirement |
| --- | --- |
| Evidence | At least 12 complete OOS months and 100 closed source trades, complete account estimates, plus full declared Funded horizon coverage. |
| Evaluation retention | Historical-confidence upper bounds for OOS/IS acquisition cost and calendar time are each at most 1.50. |
| Funded retention | Historical-confidence lower bound for OOS/IS mean receipts is at least 0.70. |
| Precision | Full frozen inner count for every history, with the current maximum relative inner standard error 0.05; unresolved estimates remain inconclusive. |
| Family/confidence | 10,000 refits, nominal 95%, existing maximum family budget 12 for one saved profile/run. |

These thresholds are local historical-model policies, not universal trading safety
limits. The new native sampling implementation gets its own identity and cannot
relabel old fixed-contract assessments. Cross-profile/adaptive search is not
covered by an automatic claim of global family confidence.

Preserve GO / NO_GO / INSUFFICIENT_EVIDENCE distinctions, prerequisite admission,
source checks and policy revisions. Existing campaign OOS access remains disclosed;
new sizing OOS is a post-screening assessment, not a newly untouched holdout.

## 9. Performance, progress and operational durability

This is the largest engineering risk. Replaying bars for 10,000 outer refits
multiplied by the full inner count is substantially more expensive than applying
fixed-size account arithmetic to a saved daybook. The latest fixed-size speedup
cannot be assumed for native percentage mode.

- Benchmark one representative qualified real configuration and independently
  designed synthetic cases across all four profile/phase combinations first.
  Include 1,000 inner paths and multiple distinct historical refits; report cold
  preparation, warm per-refit times, memory and cancellation latency separately.
- Compile the existing strategy/execution/account hot loops where measured. Cache
  immutable market features, causal block catalogues/calendars and exact indexed
  schedules with bounded accounting. Cache only calculations proved equivalent.
- A faster opportunity representation is optional later work and requires a
  declared size/account-invariance capability plus native trace parity. A list
  of trades realized at one fixed size is not such proof.
- Stream aggregate account results. Retain all requested point path outcomes and
  deterministic schedule/source provenance, while detailed intrapath traces use
  a declared bounded capture subset. Outer refits retain means, precision,
  history/schedule hashes and all 10,000 outputs; do not create a backtest report
  or duplicate raw market dataset for every inner account path.
- Qualify the native 512-path/365-day and work/capture bounds before widening them.
  Keep count/horizon/censoring semantics explicit. Do not reinstate removed
  aggregate bounds for the unaffected fixed-size saved-source workflow.
- Show expanded grid, counts and estimated work before Run; no hidden reduction
  of paths/refits/candidates. Unsupported workloads must reject clearly. A
  release cannot claim normal 1,000-path percentage support while only its
  eight-path fixture works.
- Reuse the existing Runtime and CPU reservations, four workers by default. No
  nested pools, application-worker multiplication or separate scheduler.
- Generalize progress from mandatory `micros` to a mode-aware label (profile,
  phase, percentage/reference or fixed quantity), candidate/total, paths or
  refits completed, worker count, elapsed time, ETA and restored count.
- Prop Sim and Job history consume the same lightweight catalogue metadata.
  Throttle writes to one second; polling never starts calculations or opens
  full reports to derive progress.
- Reuse completed-refit checkpoints with full native policy/source/catalogue/
  sampling identity. Retry only missing outer indices in deterministic order.
  A partially completed refit restarts at that index; do not claim intrabar
  resume. Flush completed batches at cooperative stop and drain workers before
  releasing reservations. Source spools and temporary contexts close on exit.

**Performance release gate:** demonstrate the representative 1,000-path workload
and a supported complete OOS qualification through the ordinary workflow, with
measured resource use and progress. If exact execution is not practical, keep
percentage mode explicitly unqualified/pre-release and revisit the execution
representation. Do not ship a weaker hidden qualification or substitute fixed
trades to make the progress bar finish.

## 10. Portal and report design

Extend the existing form, results and download routes.

- One sizing-mode switch; hide irrelevant fixed/percentage controls.
- Each phase has its own percentage min/max/step, advanced reference and whole-MNQ
  ceiling. Show USD budget at the initial state and its share of initial allowed
  drawdown. For dynamic references, label that USD budget as initial only.
- Switching account profile restores valid phase-specific ceilings without silently
  clipping a saved declaration. Existing fixed configuration remains readable.
- Run performs source checks internally. Explain unsupported strategies, missing
  causal stops/price coverage and invalid grids before enqueueing expensive work.
- Main result: selected policy/roles, IS economics, OOS conclusion and next step.
  Keep full search tables, assumptions and diagnostics collapsed by default.
- Comparison columns include percentage, reference, contract cap, mean/median and
  p95 quantity, quantity range, skipped-entry rate, cap-binding rate and relevant
  phase economics. Quantity statistics say whether they cover executed entries;
  skip rate uses all eligible pre-sizing opportunities. Display opportunity
  counts so account pauses are not confused with low-budget sizing skips.
- Track requested versus admitted risk and distinguish provider caps, optional
  cushion guards, below-one-micro skips and account-halted opportunities. Never
  describe a cap-bound policy as actually risking its whole nominal budget.
- Evaluation chart keeps cost/time axes; tooltips show the percentage policy and
  quantity distribution. Preserve exact ties and supplied frontier membership.
- Sorting uses saved precision; normal numeric display remains two decimals.
  If 2dp would collapse distinct percentage inputs, display enough percentage
  precision to distinguish them and retain exact decimals in downloads.
- Normal JSON/CSV/ZIP contains policies, source checks, risk coverage, quantity
  diagnostics, candidate membership, selections, account outcomes, qualification
  and checkpoint/runtime identities. Reopening is read-only and never resimulates.

## 11. Paper execution and eventual portfolio use

Extend existing forward policy/reconciliation to compare the frozen percentage,
reference, quantity caps, causal stop/decision prices, account state, expected
whole quantity and actual accepted/skipped outcome. Include received-cash versus
account deductions when they affect the selected reference. Preserve the current
20 distinct sessions, 30 closed trades, zero unexplained discrepancies and manual
signal/execution review requirement. Historical GO remains permission for paper
review, not automatic live authorization or provider certification.

Portfolio mode already accepts declared percentage policies. Later it can consume
qualified frozen phase-policy references rather than manual copying. Portfolio
allocation, simultaneous exposure, monthly budget and full replacement economics
remain their own objective/assessment. An independently qualified policy does
not qualify a combined portfolio or require rewriting current portfolio results.

## 12. Delivery milestones and exit evidence

| Milestone | Concrete artifact / product increment | Exit evidence |
| --- | --- | --- |
| M0 — contracts and feasibility | Finalize denominator, source capability, native sampling law, API schema and profile/phase semantics; build a bounded read-only prototype benchmark. | Source/module map, exact arithmetic fixtures, four-case runtime/memory estimates, native bound mismatch resolution proposal, documented sampling assumptions. No production qualification claim. |
| M1 — campaign risk evidence | Instrument-aware risk calculation, versioned coverage/R metrics and trade-detail/optional result columns in normal campaign reports. | NQ/MNQ/ES point-value cases; known-before-entry checks; saved-source derivation without replay where possible; missing-evidence case; unchanged campaign gates/manual checks; normal browser report and downloads. |
| M2 — policy/search contracts | Typed independent percentage grids and complete immutable candidate identities through existing phase APIs/reports. | Decimal/grid rejection cases, profile ceilings, no fixed/percentage ambiguity, source rechecks, phase independence, legacy readers/cache/deletion protections. Pre-release outputs explicitly say which assessment is not yet supported. |
| M3 — exact native phase simulation | Single-policy then declared-grid Evaluation and Funded through existing owners/controllers and ordinary phase reports. | Four account/phase combinations; quantity and cash/date oracles; skips/caps/DLL/trailing floor/withdrawals/gaps/censoring; chronological source coverage; native fixed-versus-percentage trace equality when quantities coincide. |
| M4 — production-scale execution | Qualified compiled/prepared native loops, streaming capture, bounded Runtime and mode-aware shared progress/checkpoints. | Representative real-source 1,000-path measurements; supported path/horizon boundary tests; serial/parallel equality; cold/warm/cache-budget parity; stop/retry and changed-source/corruption rejection; cheap portal/job polling under load. |
| M5 — percentage OOS qualification | Frozen native OOS point/chronological calculations and full versioned two-history confidence assessment. | Exact small-history enumerated/hand-calculated oracles; both histories affect bounds; same frozen policies; all counts preserved; sparse-pool/zero-mean/incomplete evidence; unchanged thresholds with new honest implementation identity; complete normal-product qualification. |
| M6 — main one-click workflow | Main Prop Sim percentage controls, automatic selection, immutable freeze, OOS continuation and concise result UI. | One initial Run per profile completes both phases in an isolated normal portal; navigation away/restart/shared-consumer/stop behavior; selections read only sealed IS; no OOS replacements; all downloads reopen; responsive layout and charts. |
| M7 — forward and migration qualification | Percentage-aware supplied-event paper review, historical compatibility, documentation and durable evidence. | Quantity/skip/account-state mismatch rejection; original fixed reports/seals unchanged; old freezes readable/fail closed appropriately; exact reproduction and current/planned labels; focused release checks. |

M0 precedes a commitment to full native runtime support. M1 is useful independently.
M2–M5 may use existing ordinary phase-research routes for pre-release numerical
work, with explicit implemented/unsupported status. The main portal's automatic
qualified percentage option is enabled only when the complete chain is usable.
No separate demo page, service, storage or qualification shortcut is introduced.

Each implementation increment updates `prop_simulation_review.md` with the actual
normal product journey, independent expected outputs, rejection boundaries, saved
screenshots/downloads, reproduction and test scope. Keep fixture oracles in tests
and label synthetic product sources. Documentation alone is not implementation.

## 13. Focused verification matrix

Use existing relevant tests plus small dedicated risk/grid/native cases. Select
browser journeys explicitly; do not run the old 180-check suite per increment.

| Area | Required examples |
| --- | --- |
| Risk arithmetic | Long/short; tick grid; NQ/MNQ/ES units; net costs once; invalid/missing stops; exact quantity boundaries; percent unit 0.20; entry-gap diagnostic; one-micro affordability. |
| Causality | Stop known late rejects; actual next-open fill cannot size the earlier decision; changed risk changes accepted trades under real native execution; warmup uses strictly prior source observations. |
| Account behavior | Both profiles; all three references; provider tiers; payout reductions; DLL-on/off; consistency variants; closures/weekends/DST; inactivity; retries/activation/readiness; unresolved acquisition; pending receipts. |
| Selection | Full frontier/ties; phase separation; <=3 Evaluation/<=2 Funded; lower-percent tie-break; repeated roles collapse by candidate ID; rounded equality does not remove a policy; no OOS-ranked replacement. |
| Qualification | Full frozen family; 10,000 addressed refits; complete inner counts; ratio/bounds and current thresholds; sparse pools; zero/negative/missing denominators; inadequate history; precision failure; historical policy labels. |
| Durability | Canonical complete/running reuse; stopped retry; immutable source/policy hashes; corrupted checkpoint rejection; cancellation drains workers; referenced source deletion protection; no duplicated raw sources or one-report-per-inner-path explosion. |
| UX | One Run; both phases survive navigation; same cheap progress in Prop Sim/jobs; exact percentage labels; meaningful skipped/capped diagnostics; one current OOS table; historical results lazy/read-only; mobile overflow checks. |
| Compatibility | Original fixed workflows and strategy admission; old input meanings/report seals; portfolio calculations unchanged; honest new numerical identities; no live server restart during tests. |

Use temporary test servers and stop them. Applying numerical source changes to the
live workspace is a final operational step after isolated proof; inspect active
jobs first and preserve immutable reports. Use the established user authorization
for a particular restart, rather than silently interrupting later unrelated work.
All implementation commits stay on `epic/revamp-workflow`; no push is implied.

## 14. Final acceptance and proposed execution order

Release acceptance requires all of the following:

1. Existing campaigns can show verified planned-R evidence without changing
   their current screening policy or falsifying missing historical risk data.
2. Every admitted percentage candidate executes native causal strategy/account
   behavior and retains the exact frozen definition used for selection.
3. Both profiles support separate Evaluation and Funded grids, objectives,
   constraints, full admitted path counts and clearly documented horizons/work bounds.
4. Automatic selection uses IS only; the full frozen family receives OOS and
   current-policy historical confidence without reselection or missing paths.
5. Quantity/cash/date/clock results match independent expected outcomes and
   trace-level compatible-policy oracles, with performance evidence at meaningful
   workload size rather than only constant-day fixtures.
6. Stop/retry, canonical reuse, source/identity guards and cheap progress work
   through the normal product, and saved results reopen without computation.
7. Historical reports remain intact. Current, historical, unqualified, inconclusive
   and paper-review states are explicit; none imply certified future outcomes.

Recommended work order: M0, then M1, M2, M3, M4, M5, M6 and M7. If M0/M4 exposes
unacceptable exact-native cost, deliver the independently useful R diagnostics
and resolve that bottleneck before claiming the percentage optimizer complete.
The capacity checkpoint does not authorize stopping after a partial milestone.
Resolve the execution bottleneck and complete all remaining implementation and
verification work; retain full counts and exact native execution.

## References

- [CME: Proper Position Size](https://www.cmegroup.com/education/courses/trade-and-risk-management/proper-position-size)
  supports sizing from stop distance and a declared loss budget; it does not
  establish a mandatory one-contract research sequence.
- [CME: The 2% Rule](https://www.cmegroup.com/education/courses/trade-and-risk-management/the-2-percent-rule)
  explicitly describes that percentage threshold as arbitrary. This plan's
  examples are arithmetic fixtures, not universally safe prop-account sizing.
- Current local architecture/contracts: `prop/sizing.py`, `native_control.py`,
  `native_draws.py`, `native_replay.py`, `native_search.py`, phase profile and
  optimization owners, `oos_qualification.py`, `oos_bootstrap.py`, `store.py`,
  `prop_sim.py`, `prop_sim_selection.py`, `prop_sim_automation.py` and
  [the phase migration plan](phase_optimization_plan.md).
