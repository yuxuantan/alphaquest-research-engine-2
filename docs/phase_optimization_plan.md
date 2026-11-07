# Independent Evaluation and Funded optimization

Additive work, 7 November 2026: the [robust research plan](robust_research_plan.md)
extends the existing phase architecture. Its first implementation executes
session-aware inner research and qualification through normal backtests and
AnalysisStore. It does not yet feed qualified sets into phase selection or run
chronological frozen outer tests. The independent objectives and numerical
owners below remain unchanged; retain all dated evidence and legacy paths.

[Home](../README.md) / [Docs](README.md) / [Architecture](architecture.md)

Specification and incremental implementation plan, consolidated 2026-11-06.
Final code baseline: `445c14030c0e060d5844cfaa3bcf6564dd13a981` plus cleanup diff.
The qualification record is [here](prop_simulation_review.md#final-architecture-cleanup--2026-11-06).
**Implemented: standalone Evaluation/Funded backends, saved-trial campaigns,
portal visual comparisons, named IS freeze and manual frozen OOS assessment.
Automatic grid generation and adaptive refinement remain planned.** Original planning baseline:
`71f97a61e568b39b6bf17647078dcdb2364069cb` (historical). This document extends the local models
and product boundary in [prop simulation](prop_simulation.md). The portal extension
below is implemented; provider rules are not newly verified. The extraction described below retains
legacy numerical semantics; it does not complete an optimization milestone.

## Implemented saved-trial research campaigns — 2026-11-06

[`research_campaigns.py`](../alphaquest/research_campaigns.py) now expands declared
saved backtest/job/trial references and per-source whole-MNQ sizes into independent
Evaluation or Funded searches. Candidate count is automatic; above 128 requires
explicit confirmation, with no fixed candidate-count ceiling. It enforces common IS
protocol and source-risk/cost compatibility, rejects duplicates and incomplete
jobs/trials, and captures every candidate's strategy parameters and provenance.
The existing prop configuration/report screen exposes check, run, frontier/ranking,
exports, reopen and immutable candidate/frontier freeze. Calculations use the
existing phase worker/AnalysisStore; campaign records reference sealed reports.
Numerical identity excludes UI/docs, interrupted runs retry explicitly, and
campaign dependencies are protected from deletion.

See the [campaign API and product guide](research_campaign_api.md) and
[actual review evidence](prop_simulation_review.md#phase-research-campaigns--2026-11-06).
This closes the saved-candidate campaign portion of P2/P3/P4 and the IS package
freeze portion of P5. It does **not** claim the full milestone exits: automatic new
grid generation and adaptive refinement/simultaneous certification remain planned.
The subsequent portal extension implements frozen-package manual OOS dispatch
and enforcement as described below. Screening is exhaustive
at the declared sampling schedule; refinement is explicitly not requested. The
standalone implementation sections below retain their original delivery scope;
references there to deferred campaign UI/freeze are superseded by this section.

## Implemented portal comparisons and frozen OOS — 2026-11-06

The existing prop screen now has phase creation actions, source/profile/rule and
research-window disclosures, bounded source × size checks, candidate completion
progress, visible full metrics, source links and durable CSV/JSON/ZIP downloads.
Evaluation displays the saved point-estimate frontier on a cost/time scatter,
comparison and marginal acceleration tables; Funded displays ranking, constraints
and all-start payout distributions. Strategy/size/profile filters never recompute
selection. Censored/unresolved/infeasible members remain inspectable.

Freeze saves named candidate(s), strategy/parameters, source identities, rule/model
versions and code hashes, search criteria/history, costs, seeds, calendar and
horizon alongside immutable report/campaign hashes. Manual OOS reuses ordinary
OOS backtests from these IS parents and only the frozen candidates/sizes/settings.
Phase assessments bypass both selectors, append to the same AnalysisStore, and
cannot overwrite the IS report/package or return an OOS winner. Prior access is
recorded and displayed, including repeated attempts. A changed numerical model
rejects launch. Sources needing a separate measured companion export reject this
launch path before accessing OOS; captured native-risk sources are supported.

This delivers the requested saved-candidate portal and frozen-assessment journey,
not all original P1–P5 research-certification criteria: generated grids, adaptive
confirmation and simultaneous/precision-certified frontier claims remain planned.
See [the user guide](research_campaign_api.md) and
[actual saved evidence](prop_simulation_review.md#phase-campaign-portal-and-frozen-oos--2026-11-06).
Earlier standalone sections record their original backend-only delivery scope.

## Implemented standalone Funded backend — 2026-11-06

[`funded_optimization.py`](../alphaquest/prop/funded_optimization.py) implements
explicit saved-IS candidate search maximizing expected trader cash received
before an exclusive calendar horizon, starting fresh funded with no evaluation
source or acquisition inputs. It supports both local Apex EOD and LucidFlex
profiles, whole-MNQ targets, saved strategies/parameters across jobs, configurable
90/180/365-day horizons, declared calendars and fixed civil-day receipt delays.
The existing funded component gains a dated runner around native account
transitions; `phase_search.py` shares calendar/admission/input capture with
Evaluation. The existing APIs/AnalysisStore publish full candidate tables,
feasibility, deterministic ranking, near-ties, uncertainty and path events.

The [implemented objective, payout clock, constraints, qualification rules,
metrics and limits](prop_simulation.md#standalone-funded-optimizer--2026-11-06)
are the exact contract for this backend version. Normal-product API evidence and
independent arithmetic are in the [review log](prop_simulation_review.md#standalone-funded-optimizer--2026-11-06).
Hard constraints filter empirical estimates, not confidence-certified risk.
Whole-path bootstrap and family mean intervals do not establish a certified
optimum or future/provider uncertainty. Open-at-horizon lifetimes are censored;
complete horizon receipts remain usable. Incomplete horizons prevent a winner.

The original standalone release implemented **P3 backend scope**; the later
campaign/portal release above added UI and frozen assessment. Precision/provider
certification and portfolio optimization remain outside that delivery. Legacy
joint sizing and previous reports remain preserved. No
external executable, generated reference table or provider verification is used.

## Implemented standalone Evaluation backend — 2026-11-06

[`evaluation_optimization.py`](../alphaquest/prop/evaluation_optimization.py)
composes the independent Evaluation component into an explicit saved-IS candidate
search and strict two-objective Pareto frontier. It accepts candidates across
eligible strategies/jobs, with saved parameters, whole-MNQ size, profile/version,
evaluation/activation fees, retry policy and sampling configuration. It uses the
normal check/run APIs, existing AnalysisStore worker/catalogue, all-source
membership and durable report/downloads. That standalone release was backend-only;
the later campaign portal now exposes it. Legacy annualized and portfolio
workflows remain unchanged.

The exact implemented [metric formulas, calendar, assumptions, Pareto rules and
independent examples](prop_simulation.md#standalone-evaluation-optimizer--2026-11-06)
supersede planned choices for this backend version. In particular:

- The initial model is an **empirical IID sequential retry** renewal model over
  the extracted component's joint outcome/duration distribution. It keeps failed
  attempt durations and stops at usable-account readiness. The old retained-block
  funding-chain output is preserved as diagnostics, not silently treated as IID
  calendar timing. Calendar means condition on the fitted attempt law.
- Initial dated optimizer admission supports local Apex EOD only. LucidFlex's
  existing weekday inactivity clock requires a dated attempt implementation
  before inclusion; it rejects rather than silently ignores closure effects.
- Start-date cohorts, Chicago civil-date clock, explicit full-session closures,
  activation/retry overhead, all-start chain censoring and threshold bounds are
  implemented. Calendars are declared scenarios, not verified exchange calendars.
- All Pareto ties and nonconvex frontier points remain. Unresolved competitors
  are not definitely excluded. No winner/lambda is returned. Dominance is estimated
  only; simultaneous/paired comparisons and robust certification remain future
  work. Nominal first-stage pass/cost intervals and conditional second-stage time
  SE/CI are retained with their different estimands disclosed.
- Requests contain an explicit nonempty candidate set; since 7 November 2026,
  there is no fixed count ceiling and searches above 128 require confirmation
  at the API/portal admission boundary. There is no automated generation,
  screening/refinement, frozen-package decision or final-OOS assessment is added.
  All source windows/cost protocols must match and sources must be declared IS.

The standalone release implemented the backend portion of P1/P2. Subsequent
campaign/portal work added UI, saved candidate controls and freeze/OOS; **the full
original P1/P2 exits remain partial** because simultaneous inference and broader
research qualification are still pending.
See the [review evidence](prop_simulation_review.md#standalone-evaluation-optimizer--2026-11-06)
for actual normal-backtest → API check/run → saved results/downloads, independent
arithmetic and limitations. No numerical/provider parity beyond those checks is
asserted; no external engine was invoked.

## Implemented precursor: independent simulation profiles

The Python component interfaces are
[`evaluation_profiles.simulate_evaluation_profile`](../alphaquest/prop/evaluation_profiles.py)
and [`funded_profiles.simulate_funded_profile`](../alphaquest/prop/funded_profiles.py).
Shared frozen input/result dataclasses live in
[`phase_profiles.py`](../alphaquest/prop/phase_profiles.py). These expose existing
local account kernels and sampling, not a second engine or new HTTP modes.

| Interface | Inputs and responsibility | Returned contract |
| --- | --- | --- |
| `simulate_evaluation_profile(runs, source, profile, micros, simulation, period, sampling, costs)` | One `SavedTradeSource`, `EvaluationProfile` (local profile ID/version, purchase/activation fees, DLL), whole MNQ target, `SimulationConfig`, optional inclusive `ResearchPeriod`, `EvaluationSamplingConfig` and `SourceCosts`. Stops at acquisition. | `EvaluationProfileResult`: attempt outcomes/durations, pass estimate/Wilson interval, acquisition cost and timing/SE diagnostics, explicit unresolved/censoring status and provenance. |
| `simulate_funded_profile(runs, source, profile, micros, horizon_weekdays, simulation, period, sampling, costs)` | One saved funded source, `FundedProfile` (local profile ID/version, funded DLL/approval policy), whole MNQ target, positive weekday horizon and phase-neutral sampling. Starts each path fresh funded; no acquisition or replacement. | `FundedProfileResult`: modeled trader payouts and gross deductions, payout mean/SE/median/P10, zero/positive payout probability, survival/breach/inactivity, per-path observations, censoring and provenance. |

Supported IDs are `apex-50k-eod` and `lucidflex-50k`.
`rule_version(id)` returns the current local implementation version; an unknown
ID/version rejects. Rules are local snapshots, not newly verified provider policy.
The phase-specific inputs reject opposite-phase profile/sampling contracts.
Neither runner reads the other phase's backtest or calls the joint selector.
Funded runs even without an evaluation source or after all evaluations expire.

Single-source admission reuses `source.prepare_source`, `commissions.adapt`,
`phase_lifecycle.validate_phase_source` and `native_analysis.day_book`. This
preserves exact source costs, native-risk/export reconciliation, chronological
nonoverlap, intraday-flat/fixed-quantity and NQ/MNQ scaling restrictions. The
existing qualified strategy whitelist remains. All source trades are checked
before the requested session period is sampled; zero-trade weekdays are retained.
There is no new internal 70/30 split or selection. Export paths are explicit;
these interfaces do not discover files in Downloads. Source manifest/trade/risk/
export hashes are rechecked after computation. Provenance includes the saved
strategy/parameters/research declaration, cost/risk identity, requested period,
phase account projection, kernel/code hashes and seeds/counts/block configuration.

Numerical compatibility is deliberate:

- `native_analysis.training_economics` delegates to extracted
  `evaluation_profiles.acquisition_economics` with its original counts/seeds,
  formulas, strings and dictionary shape. `native_analysis._funded_profile`
  delegates to `funded_profiles.lifetime_profile`. `joint_sizing.py`, its gating,
  selector, score, refinements and report schemas remain intact.
- Acquisition cost remains the legacy `fee / pass_probability + activation`
  estimator. Replacement duration remains the repeated-chain **trading-weekday**
  mean, including the existing activation weekday. It is not calendar time or
  the new dated acquisition-cost estimator specified later in this plan.
- Apex `timeout` remains provider expiry at 21 weekdays. Lucid `timeout` is
  computational censoring; no provider deadline is invented. A chain guard
  leaves timing unavailable. The old kernel aborts a chain batch without
  per-path records, so `chain_censored_paths` is `null`, never a fabricated count.
  Zero sampled passes means unresolved acquisition, not proven impossibility.
  The pass fraction/interval describe observations through the attempt cutoff;
  censored possible passes also appear in explicit pass-probability bounds.
- Funded horizons retain the kernel's inclusive weekday count. Payouts retain
  its request/deduction-time modeled receipt convention, without bank settlement
  or pending-receipt forecasts. Open accounts are lifetime-censored; complete
  horizon payouts remain usable, while unrestricted lifetime means are `null`.
  No terminal equity is counted as payout. New payout quantiles use inverse CDF;
  legacy summary fields retain their original definitions and quantile methods.

The full pre-extraction deterministic calculation payloads match for Apex and
Lucid; tests also cover phase isolation, rules, costs/risk rejections and censored
cases. See [saved evidence and reproduction](prop_simulation_review.md#independent-phase-component-extraction--2026-11-05).
This precursor alone did not implement P1–P5. The standalone backend sections
above now add dated acquisition and funded receipt selection with durable reports;
the saved-trial campaign UI and freeze/OOS enforcement are implemented by the
later increments above. Broader generated/adaptive search remains future work.

## Objectives and non-objectives

Build two independent research optimizers over strategy, strategy parameters,
position size and supported account profiles:

- **Evaluation:** minimize expected acquisition cost and expected calendar time
  to a usable funded account. Return the cost/time Pareto frontier; no lambda,
  annualized score or funded payout can select an evaluation candidate.
- **Funded:** maximize expected trader cash payouts received within a configured
  horizon, conditional on starting with one fresh funded account. Evaluation
  pass rates, fees, acquisition time and joint annualized economics are excluded.

Candidate sets may combine saved IS backtests and trials from multiple strategies
and optimization jobs. Selection uses IS only. Freeze the selected package before
manually assessing final OOS. Phase results must be independently useful: neither
phase requires a strategy, analysis, successful result or selected size from the
other phase.

Initial scope is the currently supported local Apex 50K EOD and LucidFlex 50K
models and eligible NQ/MNQ sources. A supported profile means a versioned local
rule implementation, not newly verified provider policy. No arbitrary firm-rule
editor, new backtest engine, service, database, live execution, portfolio search,
shared-account allocation or automatic final OOS execution. Existing annualized
joint sizing remains supported as **legacy business-level optimization** until
separately approved retirement. Its formulas, tests and historical reports stay.

## Inspected baseline and architectural gaps

This table records the inspected pre-extraction baseline. The precursor and
standalone backend, saved-campaign and portal sections above supersede its input,
dated-sampling, API, campaign, UI and frozen-assessment gaps. The table is a
historical baseline, not a list of currently absent portal features.

| Actual implementation | Reusable behavior | Gap for this plan |
| --- | --- | --- |
| [optimization.py](../alphaquest/optimization.py), [optimization_api.py](../alphaquest/optimization_api.py), [optimization_worker.py](../alphaquest/optimization_worker.py) | One strategy/dataset per exhaustive grid; ordinary durable backtest trials, bounded workers, reuse, resume and sortable results. | No cross-job candidate campaign or independent phase objectives. Sorting saved historical net is not phase optimization. |
| [optimization_prop.py](../alphaquest/optimization_prop.py) | Append-only account refresh links in the backtest catalogue; numerical identity checks; calculations stay in AnalysisStore. | Refreshes account-specific legacy analyses; does not search strategies or select a phase frontier. |
| [native_analysis.py](../alphaquest/prop/native_analysis.py), [joint_sizing.py](../alphaquest/prop/joint_sizing.py) | Source/cost adaptation, internal chronological train/validation split, local sampling and stage profiles. Joint selection calls training acquisition and funded lifetime profiles, then freezes both sizes before internal holdout. | Default selection maximizes `261 * (funded receipts - acquisition cost) / (funded lifetime weekdays + acquisition weekdays)`. Funded profiles are gated on calibrated evaluation results. Stage-profile reuse does not make selection independent. |
| [native_engine.py](../alphaquest/prop/native_engine.py), [lucid_engine.py](../alphaquest/prop/lucid_engine.py), their backends | Evaluation-session and funded-account transitions, first breaches, daily stops, tiers, payouts and inactivity. | New wrappers need phase-only input types, dated sampling, per-path censoring and horizon receipt metrics. Preserve kernel regression/parity checks. |
| [phase_lifecycle.py](../alphaquest/prop/phase_lifecycle.py) | Independently reconciled phase sources, fixed sizes, shared observed dates, subsequent-session activation, both-source identity/protection. | Fixed selections on one observed path; no search or Monte Carlo forecast. Current eligibility includes a strategy whitelist and fixed-path/risk restrictions. |
| [cash_ledger.py](../alphaquest/prop/cash_ledger.py) | Exact paid fees, monthly cap/reservations and separate payout requests, deductions and modeled receipts. | Starts one slot unfunded on observed history. It is not a conditional-funded sampler, acquisition expectation estimator or portfolio optimizer. |
| [prop_api.py](../alphaquest/prop_api.py), [store.py](../alphaquest/prop/store.py), [prop.js](../alphaquest/web/prop.js), [index.html](../alphaquest/web/index.html) | Configure/check/run and atomic durable reports, source membership, fingerprints, downloads and historical readers. Portal offers annualized and budgeted methods; dated API/reader remains compatible. | No independent phase forms, multi-candidate contracts, frontier or campaign freeze. Existing OOS source admission allows manual exploratory analyses; it is not a frozen campaign assessment gate. |
| [research.py](../alphaquest/research.py), [research workflow](research_workflow.md) | Saved chronological declarations; manual OOS from an IS parent with inherited strategy parameters/costs; unlimited attempts with history. | No campaign-wide cross-strategy split compatibility, frozen prop sizes/profiles or assessment-only phase execution. |

Existing regression anchors include `test_joint_prop_sizing.py` (independent
Decimal joint-score oracles and censoring bounds), `test_prop_training_economics.py`
(training/holdout isolation), `test_prop_phases.py`, `test_prop_phase_validation.py`,
`test_prop_cash.py`, `test_research_workflow.py`, `test_optimization.py` and their
API/browser counterparts. `review_prop_phase_oracles.py` and
`review_prop_cash_oracles.py` independently inspect saved product outputs.
These are existing evidence/checks, not test passes claimed by this specification.

## Target architecture and module responsibilities

The dependency direction is: saved IS trials → checked phase candidates → local
phase simulation → phase metrics/selection → normal durable report → frozen
selection package → manual assessment-only OOS. A later, optional portfolio
optimizer may consume the phase results and retained dependence information.
No portfolio score feeds back into either phase's selection.

The implementation uses the following ownership map. Earlier proposed filenames
`phase_optimization.py` and `phase_sampling.py` were not required and are not APIs.

| Implemented module | Responsibility and boundary |
| --- | --- |
| `prop/evaluation_profiles.py` / `prop/funded_profiles.py` | Independent phase simulation; legacy acquisition/lifetime helpers remain compatibility delegates. |
| `prop/evaluation_optimization.py` | Evaluation request, empirical IID retries, acquisition/calendar metrics, full strict Pareto/ties/unresolved set, marginal acceleration and format-4 writer. No funded selector/input. |
| `prop/funded_optimization.py` | Funded request, fresh-account dated runner, all-start horizon receipt/risk metrics, constraints/ranking/near-ties and format-5 writer. No acquisition inputs/replacement. |
| `prop/phase_profiles.py` / `prop/phase_search.py` | Shared types, source/risk/cost admission and identities, calendar, IS compatibility, captured inputs. Phase-specific schedules/uncertainty stay with their estimator. |
| `prop/phase_dispatch.py` | Lazy, strict phase resolution shared by API, campaigns and AnalysisStore; no simulation or selection. |
| `research_campaigns.py` / `campaign_api.py` / `web/campaigns.js` | Saved source/job/trial expansion, complete bounded membership, immutable campaign manifest, named freeze, assessment links and existing prop-screen controls. |
| `prop/store.py` / `prop_api.py` | Existing queue/worker, source membership/deletion locks, bounded preflight, atomic artifacts and durable readers/downloads. Phase-specific report schemas stay with the owner; common sealing/source capture is already shared. |
| `optimization.py` / worker/API / `research.py` | Ordinary backtesting/grids, saved IS/OOS protocol, reuse and manual OOS execution. New grids can explicitly skip automatic joint reports; old requests keep the automatic default. Campaigns do not launch new grids. |
| `prop/native_analysis.py` / `prop/joint_sizing.py` | Retained legacy joint-business calculation and compatibility delegates, never independent selection. |

See [retention/dependency audit](architecture.md#final-module-ownership-and-retention)
for historical notebook modules and code-identity preservation.

Share small settlement/date helpers with `cash_ledger.py` only after regression
proof. Do not call its unfunded budget scheduler to produce conditional-funded
results. Legacy `native_analysis.calculate()` and `joint_sizing.select()` remain
a separate dispatch path; new phase runners must not call them to select sizes.

## Candidate and result contracts

### Candidate identity and admissibility

A phase candidate is one immutable tuple of source backtest, strategy/parameters,
target size and account profile under a campaign revision. Record:

| Field group | Required content |
| --- | --- |
| Identity | Contract version, phase, candidate hash, source run ID; all origin optimization job/trial references, including aliases after deduplication. |
| Source | Dataset ID/hash, trades/risk/export hashes, symbol, point value, timezone/session/calendar identity, observed coverage, execution/slippage and source commission snapshots. |
| Strategy and sizing | Registered strategy ID, implementation hash, complete typed parameters, original quantities, positive whole MNQ target, user/provider limits, fixed-path scaling eligibility and effective-size policy. |
| Account | Profile ID/version, relevant phase rule hash, fee/timing assumptions where applicable, local verification status and provenance. No claim that a saved price is current. |
| Research | Saved IS/OOS declaration, campaign common windows, prior-access history, training/internal validation roles, IS source status and selection protocol hash. |
| Computation | Sampler/metric/kernel versions, code hashes, RNG algorithm, seed schedule, path counts/guards, block length, calendar/start cohort, horizon and settlement policy where applicable. |

Evaluation profile projections contain evaluation rules, purchase/retry costs,
activation cost and readiness timing only. Funded projections contain funded
rules, fresh-account state, trader share/withdrawals and settlement only. A UI may
display a common firm name, but irrelevant phase data must not enter the runner,
selection or numerical cache key. Capture any full administrative profile once
as provenance, separately from the phase calculation identity.

Start with the existing fixed-quantity, nonoverlapping, intraday-flat source
contract and complete native OHLC risk or reconciled measured risk. Reject
close-only, missing costs/risk, unrecognized profiles and invalid sizes with
specific reasons. Whole MNQ targets are not fractional micro orders: 1 NQ of
source exposure normalizes to 10 MNQ equivalents; modeled instrument and costs
must agree. Mandatory funded tiers can reduce effective size below the target.
Variable/account-dependent sizing or size-dependent fills require fresh ordinary
backtests with declared parameters; do not linearly rescale them as fixed paths.
Do not sweep a strategy quantity and an exposure multiplier twice without an
explicit, deduplicated interpretation. Extend strategy eligibility by capability
checks and qualification, not by assuming every registered strategy is scalable.

For the first campaign version require common instrument economics, source/data
conventions and identical declared IS/OOS windows across candidates; different
strategy IDs/job IDs are allowed. NQ/MNQ mixes need reconciled USD normalization
and matching observation coverage. Different dataset versions, calendars or
windows reject pending explicit reconciliation; never silently compare unequal
periods. Historical source/cost assumptions remain visible. A uniform declared
commission scenario may adapt supported sources once; slippage stays as saved.
Different execution-cost protocols require separate comparison groups, not an
unlabelled leaderboard. Each independent phase may have its own campaign; it
need not share a source or window with the other phase.

### Requests, results and state

Proposed modes are `evaluation_optimization` and `funded_optimization`. Extend
`POST /api/prop-analyses/check` and `POST /api/prop-analyses` with a discriminated
request carrying a campaign revision or explicit candidate references and its
phase configuration. Keep an existing source report as the navigation anchor;
the anchor has no scoring privilege. Reject opposite-phase fields instead of
silently accepting an unused funded strategy or evaluation fee. Recheck hashes
on submission; changing sources/settings invalidates the checked configuration.

Results contain the resolved request, candidate manifest, check/rejection rows,
per-candidate metrics and intervals, path counts/outcomes, frontier or payout
ranking, unresolved competitors, selection/freeze status and file manifest.
Distinguish `invalid`, `estimated`, `censored`, `precision_unresolved` and
`analytically_bounded` candidate states from job `queued/running/complete/error`.
A completed report may have an unresolved selection. Missing estimates are
`null` with reason, units and estimand; never NaN, a synthetic zero or a false
finite mean. Proven infinity uses `null` plus an explicit `infinite` status.
Zero actual payout is a valid measured/simulated outcome, not a missing result.

Return all admissible evaluation frontier points. A user's explicit choice of
one point, or a predeclared constraint such as fastest under a cost ceiling,
is a separately recorded decision. Never hide a scalar weight behind a default.
Funded ranking uses the unconditional mean cash within the fixed horizon only;
downside/survival are diagnostics or predeclared eligibility constraints. Exact
ties retain all tied candidates; stable hash ordering is presentation only.
Statistical overlap must not be described as a proven unique winner.

## Implemented metric and selection contracts

The exhaustive field/formula references are the current
[Evaluation metrics](prop_simulation.md#metrics-censoring-and-uncertainty) and
[Funded metrics](prop_simulation.md#metrics-risk-constraints-and-uncertainty),
with [Evaluation selection](prop_simulation.md#pareto-contract-and-saved-artifacts).
`phase_metrics.json/.csv` exposes these fields without UI rounding. The broader
mathematical design below is a target contract; it does not expand implemented
profiles, estimator assumptions or statistical guarantees.

| Owner | Implemented estimand / selection contract |
| --- | --- |
| Evaluation | Single-attempt pass probability and bounds; `fee/p + activation` cost and `1/p` attempts only when acquisition resolves; all-start civil-calendar mean/median/P90 readiness, inclusive day-30/day-60 probabilities/bounds, inverse mean throughput. Lower bounds and unavailable tails stay explicit. |
| Evaluation uncertainty | Nominal Wilson pass/cost inversion, delta-method cost SE, within-start conditional calendar mean SE/CI; no marginal-ratio/quantile intervals or simultaneous/paired dominance certification. |
| Evaluation selection | Strict two-objective cost/time Pareto retains all ties and nonconvex points, complete candidate table and unresolved competitors. Marginal acceleration is cost increase / positive calendar days saved; null when undefined. No winner or arbitrary lambda. |
| Funded cash | Mean objective `expected_funded_cash_payouts_within_horizon` (`expected_payouts` alias), all-start median/P10/P90, payout/zero probabilities, conditional first-receipt time, receipt count, pending trader entitlements and gross account deductions. Only receipt dates strictly before cutoff count; no evaluation fees or terminal equity. |
| Funded risk/lifetime | Breach/inactivity/payout-limit probabilities, horizon survival, restricted mean observed lifetime; unrestricted lifetime null for open/censored accounts. Incomplete horizon withholds objective/ranking winner. |
| Funded selection/uncertainty | Empirical hard constraint filters; feasible descending cash then candidate hash, full ranking and tolerance/interval near-ties. Whole-path stratified bootstrap, within-start SE, family normal mean intervals; no certified optimum or provider risk guarantee. |
| Frozen OOS | Apply frozen configuration to ordinary OOS sources; per-candidate metrics/constraint status, empty ranking/frontier and null winner. Repeated assessments append; IS/package bytes remain unchanged. |
| Legacy / observed ledger | Existing annual slot score and observed budgeted cash retain their own definitions and inclusive/exclusive timestamp conventions; never alias either to a phase objective. |

## Mathematical metric definitions

All expectations refer to the saved source/resampling model, not a provider or
future-performance guarantee. Monetary values are USD; cash-event arithmetic is
Decimal cents with the existing explicit rounding policy. Probability uses [0,1].
Quantile convention is inverse CDF, `Q(q) = inf{x: F(x) >= q}`; record the estimator.

### Evaluation: acquire one funded account

At `t0` purchase one evaluation. On failure/expiry retry serially according to
the saved delay policy; on pass pay activation and wait until the account is
usable for its first eligible funded session. Stop there, without simulating any
funded trade or payout. Initial scope assumes acquisition capital is available:
monthly spending-cap scheduling belongs to the preserved ledger/future portfolio
work, not an implicit constraint in this optimizer.

For path `i`, let `K_i` be purchased attempts before readiness, `T_i` elapsed
calendar days from `t0` to readiness, and `C_i` all actual evaluation/activation
fees paid along that chain. Sum failed-attempt fees and any supported renewal or
reset fees; unsupported fee schedules reject. No evaluation trading profit,
funded payout or account face value offsets acquisition cost. Activation expiry
and retry behavior, if enabled, must be explicit and included in the chain.

| Metric | Definition |
| --- | --- |
| Pass probability | Probability a single purchased evaluation passes before a modeled terminal failure/expiry. Separate this from eventual funding across retries and readiness after activation. Show deadline/computational truncation explicitly. |
| Expected acquisition cost | `E[C]` through first usable funded account, including unsuccessful attempts. With complete model paths, estimate `sum(C_i)/N`. Never average only successful chains when others are unresolved. |
| Expected calendar days to funding | `E[T]`, with `T = infinity` if never funded. Report a finite estimate only under the declared finite-mean continuation model and sufficient uncensored computation; also disclose guards/assumptions. |
| Median / P90 funding time | `Q_T(0.5)` and `Q_T(0.9)` over all chains, not successful chains only. Unreached quantiles are lower-bounded/unavailable. |
| Funding within 30/60 days | `Pr(T <= 30)` / `Pr(T <= 60)` from the same chain ensemble and readiness event. Paths unresolved before the threshold give bounds, not failures. |
| Funding throughput | `1/E[T]` usable accounts per calendar day per serial acquisition lane under the stated renewal policy; optionally `30/E[T]` per 30 days. It is not concurrent portfolio throughput or `E[1/T]`. Unknown mean → unknown throughput. |
| Marginal cost per day saved | For adjacent frontier points ordered slow/cheap to fast/costly: `(C_fast - C_slow)/(T_slow - T_fast)` USD/calendar day. Zero time difference → unavailable; show the two candidate IDs and uncertainty. This diagnostic never weights the objectives. |

For an explicitly IID attempt model with constant purchase fee `f`, certain
activation fee `a`, pass probability `p > 0`, mean attempt duration `d`, failure
retry delay `r` and final activation/readiness delay `w`, independent oracle
identities are `E[C] = f/p + a` and `E[T] = (d + (1-p)*r)/p + w`.
These identities are not a shortcut for retained-block dependence, variable fees,
activation failures or calendar alignment. Legacy funding chains retain an
unfinished block across attempts; the new contract must state its own continuity
and use actual chain costs/times. Zero sampled passes does not prove `p=0`.
An analytically impossible pass can establish infinite funding time and
unavailable acquisition optimization; a computational guard cannot.

Candidate `a` dominates `b` iff `C_a <= C_b` and `T_a <= T_b`, with at least one
strict inequality. The point-estimate frontier contains all undominated complete
estimates and is labeled empirical. Preserve unresolved candidates alongside it.
For simultaneous confidence rectangles, call dominance supported only when
`upper(C_a) <= lower(C_b)` and `upper(T_a) <= lower(T_b)`, at least one strict.
Otherwise show uncertainty/possible frontier membership. Bounds for evaluation
exclusion must use evaluation information only, never a funded payout ladder.

### Funded: one account already funded

Start at `t0` with the profile's fresh-funded state: initial trading equity/trail,
tier, zero prior payouts, reset counters and no inherited position. Acquisition
and activation are already complete and outside the objective. Choose a common
positive calendar-day horizon `H` and start cohort/timezone for a comparison.
Receipts count in `[t0, t0+H)`; an inclusive end-date UI converts to the next local
midnight. Do not multiply weekday means by `7/5` or substitute 261 sessions.

For path `i`, let `R_ij` be trader share actually modeled as received at `s_ij`.
`P_i(H) = sum_j R_ij * 1[t0 <= s_ij < t0+H]`. Select the largest `E[P(H)]` over
all funded-start paths, including zero-payout/breached accounts. No replacement
account is purchased within this phase objective. Any unavoidable funded charge
must be separately disclosed with its cash treatment; unsupported charges block
profile admission rather than silently changing payouts into net acquisition cash.

Report mean, median and P10 payouts (P10 is the initial downside statistic),
`Pr(P(H)>0)`, `Pr(P(H)=0)`, and probability of drawdown breach by the horizon.
Distinguish request, gross account deduction, trader entitlement and modeled
receipt. Pending receipts beyond cutoff are separate; no terminal equity value.
Preserve explicit settlement delay and post-closure payment/cancellation policy.

Let `F` be time to first cash receipt. Report `E[F | F < H]` with that condition
in the label and its denominator, plus restricted mean wait `E[min(F,H)]` across
all paths (use `H` for no receipt). Do not label the conditional mean as an
unconditional expected time. An eventual unconditional `E[F]` is not estimated
from this finite horizon; nonpayers may make it infinite.

Let `L` be time to operational account closure. Report `S(t)=Pr(L>t)` at declared
checkpoints, restricted mean active lifetime `E[min(L,H)]`, quantiles only where
identified, and separate cumulative incidence of breach, inactivity and payout-
limit completion. Successful payout-limit closure is not a breach. An account
open at `H` is right-censored for total lifetime but has a complete `P(H)` if the
path was simulated through `H`. Post-closure pending receipts may still enter
`P(H)` under the saved policy. Do not reuse a terminal lifetime estimator as this
finite-horizon payout objective.

## Sampling, clocks, censoring and uncertainty

1. Construct one comparable IS session grid per campaign revision, including
   verified no-trade observations. Distinguish a known no-trade session from a
   missing-data gap. Current `day_book()` spans first/last trades and inserts
   weekdays; the new adapter must check full declared source coverage and cannot
   infer a holiday or market close from missing trades.
2. Resample contiguous session blocks from IS, preserving intraday trade order,
   risk frontiers and fees. Retain blocks across failed attempts for the initial
   acquisition model; a fresh independent chain starts a new stream. Record
   circular wrap behavior and the synthetic target dates separately from source
   dates. Do not sample across IS/OOS or internal fit/validation boundaries.
3. Map draws to a dated target calendar with explicit start-date distribution,
   timezone, weekends, closure assumptions, inactivity and activation clocks.
   Version the calendar. Initial allowed mode may use an explicitly disclosed
   weekday calendar, matching existing limitations; it must not be called a
   verified exchange/settlement calendar. DST and weekend delays count in
   calendar metrics. Compare candidates under the same target-date cohort.
4. Use common random schedules across candidates sharing aligned observations
   for paired comparisons. Seeds alone do not ensure pairing: account termination
   changes draw consumption. Address draws by path/block/replicate, independent
   of worker completion order, and retain schedule hashes. Independent sources
   without justified alignment cannot claim paired uncertainty or dependence.
5. Predeclare block length (existing 1/5/10 supported choices), seed namespaces,
   screening/refinement counts and maximum computation before search. The initial
   plan uses 3,000 screening paths and 20,000 independent confirmation paths per
   surviving or potentially competitive candidate, consistent in scale with
   current runs. Never silently lower counts; save requested/actual counts and
   reasons. Freeze survivors before the confirmation draw; no repeated favorable
   reseeding or optional stopping. Further refinement is a new recorded revision.
6. Use 95% intervals: binomial intervals for uncensored proportions, independent
   whole-path resampling for means/quantiles and paired whole-path resampling for
   differences when schedules align. Fix bootstrap replicate count/seeds before
   execution. For independent complete paths, also report mean Monte Carlo
   standard error `s/sqrt(N)`; paired differences use the standard deviation of
   pathwise differences, not two independent-error formulas. Quantile and
   marginal-ratio intervals may be unavailable when
   events are scarce or a time difference crosses zero. Simultaneous comparisons
   must account for the entire declared candidate/metric family (e.g. Bonferroni
   allocation); nominal per-row intervals do not certify a frontier after search.
7. Save a censor record per path: observed time, event, guard/termination reason,
   cost accrued, pending activation/receipts and unresolved status. Provider
   failure/expiry is an event; a numerical limit is censoring, not failure.
   Under common administrative cutoff `tau`, report `E[min(T,tau)]` and funding
   incidence through `tau`. Unresolved paths contribute accrued-cost/time lower
   bounds; never fill missing tails with successful-path averages. Threshold
   probabilities use known events plus unresolved possibilities for bounds.
   Do not extrapolate an unrestricted mean from a survival tail. More complex
   censoring needs a justified estimator/assumption before admission.
8. If computation ends before funded horizon `H`, payout estimates are incomplete;
   show accrued receipt lower bounds and only mathematically valid upper bounds.
   Distinguish this from a complete horizon with open accounts. A potentially
   competitive unresolved candidate prevents a certified optimum/frontier.
9. Monte Carlo intervals quantify simulation error conditional on source/model.
   Historical sampling uncertainty, multiple strategy testing, regime change,
   rule uncertainty and OHLC execution limits are separate. Report block-length,
   costs and timing sensitivity on IS as declared experiments. Do not tune them
   to final OOS. Precision thresholds and evidence/sample requirements are saved
   campaign inputs; unset thresholds mean no precision-qualified recommendation.

## Research campaigns and IS/OOS separation

Campaigns start with explicit saved candidate sets; subsequent milestones may
expand declared strategy/parameter grids using ordinary optimization jobs. Save
the complete search space and total trial cap, including failed/rejected trials,
deduplication aliases and all narrowing decisions. A candidate list selected after
viewing OOS is development evidence, not untouched final research.

Selection stages are IS fit/search and optional IS internal validation. Existing
prop internal 70/30 holdout is inside the backtest's selected research period;
it is not final OOS. Predeclare whether internal validation only diagnoses or
influences selection, and include every used period in the development history.
No final OOS bars, automatic prop metrics, payout outcomes or refreshed historical
net enter candidate admission, refinement, ranking, tie resolution or freeze.

Before any final OOS assessment, publish an immutable package containing the
campaign/candidate/result hashes, chosen evaluation frontier point(s) and/or
funded winner/tie set, decision rationale, source and strategy hashes, complete
parameters, fixed size, rule/profile/cost/timing versions, horizon, calendar,
seeds, metric definitions, split/prior access and predeclared acceptance limits.
Freezing one phase never requires a choice in the other. Freeze multiple frontier
points only as a predeclared assessment family, with multiplicity disclosure.

Manual assessment creates ordinary OOS backtests from their saved IS parents,
then new phase **assessment-only** reports linked to the package. Apply frozen
sizes/profiles to OOS sources; do not rerun size search or the internal selector.
Existing automatic joint reports can remain attached to ordinary OOS backtests
but are not the phase assessment and cannot change the package. Validate all
parameter/date/cost/size/profile overrides server-side. Code/model mismatch
requires an explicit new package or preserved compatible implementation; never
silently substitute a new engine. Assessments append; they cannot overwrite IS
selection or return a better OOS candidate as a revised winner.

Keep the current unlimited manual OOS policy and editable split forms. Campaign
freeze adds a reproducibility contract, not a restored attempt limit. Record all
prior accesses/assessment attempts. A revision informed by OOS is a new development
campaign; it does not erase exposure or relabel the same data as untouched.

## Persistence and provenance

Use the existing backtest catalogue for job/trial/research references and the
existing AnalysisStore catalogue/files for phase analyses, campaign manifests,
frozen-package records and assessment links. Small additive index tables may
index those records in existing databases; do not create a new database or copy
reports into a parallel campaign directory. Store calculation outputs once;
campaign/freeze records reference IDs and verified hashes.

Extend `analysis_sources` to every referenced candidate source before queueing,
not just the navigation anchor. Apply existing lock/publication/deletion patterns
to prevent a running campaign losing a source. Completed results must reopen
from captured inputs without a source replay. Frozen references need explicit
dependency-aware deletion protection; never cascade-delete source reports or
silently leave a freeze link dangling. Respect original file/ZIP size limits:
preflight campaign bounds, capture shared inputs once per report and link sealed
candidate analyses rather than silently exceeding limits.

Normal downloadable artifacts should include `phase_candidates.csv/.json`,
`source_checks.json`, `phase_metrics.csv/.json`, `sampling.json`, path summaries
and censoring counts, saved chart data, phase frontier/ranking, reconciliations
and `frozen_package.json` when applicable. Paths/traces must allow independent
audit of metrics within declared storage bounds; record any trace subset and
its deterministic selection. Use existing `report.json`, `calculations.json`,
file allowlist and `analysis.zip` publication/download routes. Artifact names
are proposed and must be versioned before their implementation release.

Numerical reuse keys include phase, candidate inputs, profile projection,
source/risk/cost hashes, campaign window, target calendar/start cohort, sampling
schedule, horizon/settlement, metric/kernel/implementation versions and counts.
Include local uncommitted calculation hashes, not Git commit alone. Cross-phase
reuse or a legacy joint result cannot satisfy a phase-only request. Keep runtime
metadata and operational refresh links separate from numerical identity. Reads,
sorting, reopen and downloads never run a calculation. Publication is atomic;
restart/interruption cannot mark partial candidates as a completed optimum.

## Migration strategy

1. This documentation change classifies joint sizing as legacy business-level
   optimization; it does not alter today's default annualized method. Preserve
   historical specification sections, reports, saved metric meanings and tests.
2. Add explicit phase modes and additive schemas. Label new phase outputs with
   new model/metric contracts. Preserve format-1/2/3 readers, old request meanings,
   annualized calculations and completed dated/cash-ledger reports.
3. In phase configuration/results, make the relevant phase objective primary;
   never preselect a candidate using `slot_year`, historical net or legacy
   pass-first sizing. When independent modes ship, label the retained annualized
   choice **Legacy business-level joint sizing** in new configuration/help.
   Existing automatic reports may continue; they are not independent selection.
4. Add cross-job campaigns, bounded generation and frozen assessment in increments
   below. Changing the automatic default or deleting legacy code/tests/reports
   is not part of this plan and needs separately approved retirement scope.
5. The completed separate-phase replay and exact cash-ledger milestones remain
   usable and preserved. Optional portfolio work is downstream: it may combine
   independent outputs with synchronized source paths, budget constraints and
   finite-horizon receipts. Marginal phase summaries alone do not identify joint
   dependence or solve allocation. See [portfolio plan](prop_portfolio_plan.md).

## Acceptance criteria and independent checks

All subsequent implementation increments must pass their numerical and source
contracts and demonstrate the actual product journey with saved inspectable
outputs. The following are required gates, not results of this documentation task:

| Gate | Required evidence |
| --- | --- |
| Phase independence | Evaluation executes with no funded source/rules/payout calculation. Changing/removing funded data cannot change its result. Funded executes with no evaluation source/probability/fees/time, including when all evaluations fail. Opposite-phase fields reject; poisoned irrelevant dependencies are never called. |
| Search coverage | At least two eligible strategies and two saved optimization jobs can contribute candidates. Exact parameter/size/profile Cartesian coverage within each phase, stable deduplication and all rejection counts are auditable. Supported profile limits and whole MNQ boundaries enforced. |
| Pareto and funded objectives | Independent arithmetic enumerates dominated, tied and trade-off points; no weighted scalar selector. Funded ranking uses all-start horizon receipts, including zero paths, and can disagree with legacy joint selection. |
| Time and cash | Independently derived attempt-chain fees/dates; weekends/DST/activation readiness, 30/60 boundaries, receipt exactly at exclusive horizon, pending after closure, and request/deduction/receipt separation. No costs deducted twice. |
| Censoring and uncertainty | Zero observed passes, rare passes, no payout, incomplete acquisition, unresolved P90, open-at-H versus stopped-before-H, interval overlap and paired schedules. Guards never become provider failures or fabricated finite means. |
| Research isolation | Mutating reserved OOS or opposite-phase data leaves IS candidate selection unchanged. Mixed splits and unapproved overrides reject. Freeze hash precedes manual OOS; assessment cannot rescore or mutate it. |
| Durability | Normal UI/API checks and downloads, restart/reopen without POST/recalculation, idempotency, multi-source deletion protection and cache invalidation. Earlier report/evidence hashes remain unchanged. |
| Regression/local ownership | Relevant existing kernels/compiled parity, joint-sizing, research, source/risk/cost, phase replay, ledger, API and browser checks pass. No external generated results/runtime are production inputs. Any reference parity remains explicit, with unverified fields identified. |

Test-only analytical examples (not product results or provider assumptions):

- IID evaluation with `p=1/2`, purchase fee 30, activation fee 40, every attempt
  lasting 2 calendar days and no delays has `E[C]=100`, `E[T]=4`, median 2 days,
  P90 8 days, and throughput 1/4 account/day. Funding by 30/60 is respectively
  `1-2^-15` / `1-2^-30`. This validates definitions, not real account rules.
- Cost/time points A=(100,10), B=(140,6), C=(160,12) give frontier {A,B}; C is
  dominated and B saves four days at 10 USD/day. Identical points remain ties.
- A hypothetical two-path funded ensemble receiving 0 and 100 by `H` has mean
  50 and zero-payout probability 1/2. A request due exactly at `t0+H` contributes
  zero within the horizon and remains pending. These event oracles belong in tests.

Product demonstrations must instead generate labeled synthetic data/backtests
through normal dataset/strategy flows, derive independent expected events for
those actual inputs, and save actual versus expected values. Do not inject these
oracle tables into runtime or invent completed demonstration IDs. Every release
updates [the review log](prop_simulation_review.md) with exact reproduction,
saved IDs/URLs/downloads, boundary cases and owned temporary-server shutdown.

## Incremental implementation milestones

P1/P2/P3 have the bounded backend and portal delivery described above. Saved
candidates cover part of P4; named freeze and manual assessment implement the P5
product path. Full original research-certification exits remain unclaimed: new
grid generation, adaptive confirmation, simultaneous inference and precision
qualification require further work. The table retains those original exit
criteria. Prefixes separate this work from portfolio M1/M2.

| Milestone | Concrete artifact and normal user journey | Exit criteria | Verified status / remaining exit |
| --- | --- | --- | --- |
| P1: single-candidate Evaluation | Phase contracts, single-source admission, dated acquisition sampler/metrics. Saved IS report → Configure Evaluation → profile/whole MNQ size/timing → Check → Run → durable report. | No funded dependency; every requested evaluation metric or explicit censoring reason; independent chain/cost/calendar cases and invalid-source checks saved. Single candidate is explicitly not yet a search. | Implemented for Apex dated acquisition; Lucid dated Evaluation rejects. Current synthetic arithmetic/browser qualification is linked above; no provider certification. |
| P2: Evaluation search and Pareto | Candidate references across saved strategies/jobs, bounded sizes/profiles, comparison and frontier in the same configuration/report. Minimal immutable campaign revision persisted. | Multi-strategy/multi-job fixture, exact within-phase search coverage, all frontier/tie/unresolved candidates, marginal-cost diagnostics and simultaneous uncertainty; no lambda or funded inputs. | Saved-candidate search/UI implemented; simultaneous dominance and precision qualification remain open. Full original exit is partial. |
| P3: conditional Funded optimization | Independent funded runner, dated settlement, horizon metrics, sizes/profiles and saved candidate set support. Saved IS report → Configure Funded → candidates/profile/size range/horizon → Check → Run → report. | Works with no successful evaluations or evaluation fields; horizon receipt/survival/zero-payout cases, full ranking and missing-precision states; ledger and joint regressions unchanged. Can proceed after P1 shared contracts without depending on P2's selected result. | Apex/Lucid fresh-funded backend, campaigns/UI and receipt boundaries implemented; certified risk/precision and provider settlement verification remain open. |
| P4: bounded campaign generation | Extend campaign form to declare multiple strategy parameter grids and link ordinary optimization jobs/trials; preserve saved-candidate entry. | Search caps/failed trials/aliases recorded; common IS protocol checked before jobs; deterministic serial/parallel results and resume; every result opens its original trial and phase report. | Saved-job/trial expansion and bounded sizing implemented. Automatic new-grid generation/adaptive refinement/resume orchestration are pending; full milestone incomplete. |
| P5: freeze and final OOS assessment | Package freeze and manual assessment links in ordinary phase/backtest reports; assessment-only dispatch and provenance downloads. | Frozen strategy/size/profile/horizon/costs/seeds and acceptance limits; OOS mutation/override tests; no reselection; repeated assessments append with access history; independent saved end-to-end evidence. | Named IS freeze/manual repeated OOS assessment product path implemented and qualified; source-export launch restriction and original broader acceptance certification remain explicit. |

At every exit: publish inspectable report/ZIP and source checks, meaningful
automated gates plus independently checked actual output, exact expected UI
observations/reproduction commands, preservation manifest and remaining limits.
Use a fresh artifact path per run. No new persistent server is needed; stop
temporary servers owned by the checks. Test counts alone do not close a milestone.

## Explicit assumptions and unresolved decisions

- Provider prices, rule currency, activation approval/deadlines, settlement and
  payment after closure are not verified by this plan. Save dated local rule
  snapshots and explicit scenario assumptions; unsupported mechanics reject.
- A weekday target calendar is an allowed disclosed approximation. A verified
  holiday/early-close/settlement calendar and start-date cohort must be specified
  before claiming more realistic calendar forecasts; no retrospective missing-bar
  inference. Concrete start cohort and delay values are required campaign inputs.
- Stationarity, retained-block retries and eventual finite funding means are
  modeling assumptions. The oracle IID identities do not establish them. Hard
  guards, refinement resource caps, precision tolerances and minimum evidence
  counts need saved values before qualification; unset means unresolved.
- Initial funded scope is one fresh account with no replacement, fixed target
  constrained by provider tiers and the existing supported payout policy. Used
  funded accounts, alternative withdrawal control and account-dependent strategy
  sizing require a later contract, not an implicit optimization dimension.
- NQ/MNQ linear scaling does not establish liquidity/market-impact parity. Native
  OHLC risk is conservative modeled coverage, not fabricated measured MAE/MFE.
  Existing external comparison discrepancies remain unresolved unless separately
  measured. New metrics need independent oracles; this spec asserts no parity.
- Portfolio allocation and monthly-cap optimization remain optional later work.
  Neither completion of this plan nor a best phase estimate establishes the best
  multi-account cash allocation or trading readiness.
## 8 November 2026: native candidate and complete-procedure integration

Independent campaigns and nested studies now support the explicit native
contiguous-block execution method. Each admitted candidate reruns the actual
strategy and phase account owner with its fixed-contract, fixed-dollar or
percentage policy. Evaluation still selects an acquisition-cost/calendar-time
Pareto family; Funded still selects finite-horizon receipts from a fresh account.
All declared members stay in the search; native origin-weight refits provide an
explicit conservative historical-mean option with separate Monte Carlo precision
and unresolved-family handling. The previous fixed-path calculation remains the
default when native execution is omitted.

Native selected families apply to actual outer and manual OOS bars without
resampling, horizon shortening or reselection. Complete procedures freeze the
qualification/search algorithm, references and evidence rules, then rerun terminal
selection on pinned eligible development. Protected final assessment is optional,
audited and permanently consumed when authorized. A separate current-development
application produces a research candidate or an explicit no-qualified-candidate
result; it cannot promote a last-fold winner or use final outcomes to reselect.

Current owners remain the respective phase profiles/optimizers, shared
admission/capture, strict dispatch, existing campaign worker and AnalysisStore.
`native_search.py` adapts candidates; `research_access.py` and
`research_procedure*.py` own local access/complete-procedure orchestration. No
Bridge runtime, joint selector, second account engine or result database enters
this path. See current contracts in [prop simulation](prop_simulation.md),
[campaign API](research_campaign_api.md) and saved product journeys in
[prop review](prop_simulation_review.md).

This extends the earlier dated findings; it does not erase their evidence. Guided
catalogue/templates, optional predefined frozen-pair lifecycle comparison,
timestamped forward monitoring and full-suite final acceptance remain pending.
Provider, broker, numerical-reference and operational readiness are separate
qualification boundaries; no live integration is declared production-ready.
