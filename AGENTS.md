# Temporary test scope during the workflow revamp

- Use the smallest test set relevant to the current change. A plain pytest run
  selects the focused mechanics/job-history/IS Broad/OOS criteria checks via `pyproject.toml`.
- For changes to the current UI, explicitly select the relevant cases in
  `tests/test_campaign_mechanics_browser.py` or
  `tests/test_workflow_navigation_browser.py`, `tests/test_job_history_browser.py`,
  `tests/test_campaign_broad_browser.py`, `tests/test_campaign_narrow_browser.py`,
  or `tests/test_campaign_oos_browser.py`, `tests/test_campaign_monte_carlo_browser.py`,
  `tests/test_prop_sim_browser.py`.
  Browser checks are opt-in; select only the affected journey.
- Older regressions remain intact but are excluded from default discovery.
  Do not routinely run the previous 180-check set or the full suite for each
  increment. Run a specific older test only when the change affects its behavior,
  or run a broader suite when the user requests it. Extend the focused default
  as new workflow phases are implemented.

# Agreed campaign screening policy

Follow `docs/workflow_screening.md` for the implemented IS Broad, IS Narrow,
and OOS criteria. The portal shares server-owned rules
from `alphaquest/workflow_criteria.py`, `alphaquest/campaign_narrow.py`, and
`alphaquest/oos_criteria.py`. OOS runs the complete frozen Narrow family through
`alphaquest/campaign_oos.py`; it must never tune or reselect IS candidates.
Preserve policy snapshots and historical confirmations; do not relabel an older
rule as passing a newer one.

Final full-period Monte Carlo is owned by `alphaquest/campaign_monte_carlo.py`
and runs inside OOS for its passing candidates. It is a retrospective sanity
check, with a separate verdict; it must not revise frozen IS choices or OOS
acceptance. Use the existing AnalysisStore worker/catalogue and sealed reports.
Keep the seed/policy fixed and retain the daily inputs, source hashes and path
outcomes. `tests/test_monte_carlo.py` contains fast arithmetic/cancellation checks;
select the native API/browser journeys explicitly when those surfaces change.
Current v2 gates are minimum evidence and positive 5th-percentile net profit
under both block settings. Mean/median profit and all drawdown measurements are
diagnostics. Preserve historical v1 verdicts; explicit policy updates reuse
verified saved daily/path CSVs and publish a new sealed assessment.

When adding strategy parameters, check the IS Narrow refinement rule in
`docs/workflow_screening.md` and `alphaquest/campaign_narrow.py`. Narrow locks
selected Broad values by default and offers **Refine in Narrow** for numeric
Broad axes with a finer representable step. `StrategyDefinition.description()`
copies each `Parameters` dataclass field's metadata into the parameter
description. A sparse integer-coded category that might otherwise appear
refinable must set `refinement_kind: categorical` in that field's metadata.
Ordinary numeric parameters need no declaration; binary `1,2` integer modes
stay locked because they have no finer integer step. The VWAP strategy's
`integer()` helper currently accepts only description/minimum/maximum, so
extend it or declare an exceptional field directly if this tag is needed.
Keep the opt-out eligibility covered in `tests/test_campaign_narrow.py`.

# Prop simulation deliverables

The main Prop Sim tab is orchestrated by `alphaquest/prop_sim.py` and
`alphaquest/web/prop-sim.js`. Keep campaign mechanics/Broad/Narrow/current OOS/
latest current-policy Monte Carlo qualification server-owned and rechecked at
launch. Exactly one configuration is supported by independent fixed-size searches. Reuse the independent
phase campaigns/AnalysisStore; do not duplicate their numerical engines or turn
the parent phase-reference record into another result store. Select
`tests/test_prop_sim.py` explicitly for admission/orchestration changes and the
browser journey above for the portal. These exercise the complete qualified
pipeline, so keep them opt-in when unrelated features change.
Keep phase size ranges independent (Apex Evaluation ceiling 60 MNQ, Funded 40,
LucidFlex 50K ceiling 40 in both, with Funded account tiers still enforced). Explicitly pass the phase simulation
cap; do not silently clip Evaluation to the older 40-MNQ default. Funded breach
probability is a diagnostic with an optional default-off eligibility cap over
the modeled horizon, not over the IS history. Preserve explicit historical caps.
The additive native portfolio mode supports one to four qualified VWAP EOD-flat
configurations on one common NQ/MNQ dataset. Keep its observed-IS cash objective
separate from independent phase objectives. Native percentage risk reruns actual
strategy/execution under the existing Evaluation/Funded controllers; never
retroactively resize saved trades when strategy/account state can change signals.
Shared accounts currently admit one position at a time with declared risk-share
priority. Preserve the hard monthly Evaluation/activation cap, reservation and
receipt/deduction separation, zero-purchase baseline and frozen OOS allocation.
Use `portfolio_sources.py` for checked temporary per-session source spools,
`portfolio_lifecycle.py` for orchestration and `portfolio_cash.py` for the shared
budget. No duplicate phase engine/store or claimed portfolio Monte Carlo GO.
Run `test_prop_portfolio_core.py` and `test_prop_portfolio_api.py` for this mode;
the normal-product evidence and scope are in the dated native-portfolio section
of `docs/prop_simulation.md` and `docs/prop_simulation_review.md`.

The Evaluation Pareto chart shows resolved estimates, exact ties and the supplied
frontier; it must not fabricate points for unresolved or untested configurations.
Lucid 40% standard / 50% add-on Evaluation uses the saved-signal calendar acquisition owner
in `evaluation_profiles.py` / `evaluation_optimization.py`, not Apex's IID attempt
law or session deadline. Charge every retry, advance closed-date inactivity,
retain guard censoring and compute cost/time from all complete calendar paths.
Do not substitute fee divided by first-attempt probability. Funded continues
through its existing independent dated owner. The 50% add-on requires an explicit
purchase fee; arbitrary percentages reject. Subsequent live-account returns remain
unsupported. Frozen size choices can run existing-worker OOS, IS block/subperiod
robustness and more-path assessments without reselection or rewriting IS reports.
Use `tests/test_prop_evaluation_validation.py` and its normal browser journey
for this surface. Keep paired MC uncertainty distinct from provider/future risk.
Fast clock/cash oracles are in
`tests/test_lucid_calendar_acquisition.py`; full qualification/API/browser
journeys remain explicit opt-in checks. Preserve old report identities and fail
closed on incompatible frozen execution after numerical source changes.

For each future prop simulation subtask, deliver:

- A concrete implementation artifact within the scope of `docs/prop_simulation.md`.
- A usable increment in the actual final product workflow. Demonstrate it from
  the existing backtest report through prop configuration, source checking,
  analysis execution, and durable results. Do not create a
  separate page, demo-only API, or duplicate storage just to prove a subtask works.
- Inspectable actual outputs and reproducible user steps with independent
  expected values/outcomes, including relevant rejection/boundary cases. Keep
  fixture oracles in tests; the product shows meaningful source checks and
  results rather than a subtask test dashboard. Never fabricate future outcomes.
- Saved, inspectable evidence/downloads and exact instructions for the user to
  reproduce and validate the demonstration. State the expected observations.
- Appropriate automated checks alongside the demonstration; a test count alone
  does not satisfy the demonstration requirement.

Pair backend increments with the minimum real API/UI integration needed to use
them. Documentation-only tasks deliver the specification/help and examples;
they do not need an artificial validation screen. Synthetic examples, when
needed, must use the normal dataset/backtest/product workflow and be labeled.

Update `docs/prop_simulation_review.md` with each increment's user journey and
expected observations. Preserve earlier saved evidence and immutable snapshots.
Use temporary test servers for browser checks and shut them down after testing;
report any persistent server started and how to stop it.

Current scope: AlphaQuest owns every production prop calculation and report.
Do not invoke The Bridge executable/DLL, consume its generated results/tables/
charts, or require its installation to create a new AlphaQuest report. External
results are comparison oracles in development/qualification only. Preserve earlier
reports and evidence unchanged, and label reports made by earlier engines.
Implement source adaptation, account state transitions, sampling, size selection,
economics, charts and downloads locally. Reconcile measured companion exports
with source identity/times/quantities/net costs; never fabricate measured MAE/MFE
or deduct costs twice. Keep numerical parity status explicit and do not claim
completion before independently generated results match the supplied reference.
Use the existing backtest -> configure -> check -> run -> durable report workflow.
Preserve the user's Windows VM, other processes and all datasets/backtests/results.

# Independent phase optimizer work

Follow `docs/phase_optimization_plan.md` for the target architecture and milestones;
it extends `docs/prop_simulation.md`. The plan is not evidence of implementation.
Keep current/planned status explicit and retain all delivery requirements above.

- Evaluation independently searches eligible strategies, parameters, whole-MNQ
  sizes and supported account profiles. Minimize expected acquisition cost and
  calendar time using a Pareto frontier. No arbitrary lambda, funded strategy,
  funded payout data or joint annualized score may select an evaluation candidate.
- Funded independently maximizes expected trader cash received over the saved
  horizon, conditional on a fresh funded account. Do not use evaluation pass
  probability, evaluation/acquisition fees, acquisition time or joint annualized
  slot economics in its inputs or selection. No implicit replacement account.
- Treat `prop/joint_sizing.py` as legacy business-level optimization. Preserve its
  calculations, regression tests, request meanings and historical reports until
  separately approved retirement. New phase selection must not call its selector
  or relabel legacy historical-net outputs as independent phase results.
- Reuse normal backtests, local account transitions, API/UI, workers, catalogues
  and AnalysisStore. Support saved IS candidates across strategies/jobs; no new
  service, database, execution engine, demo-only surface or duplicate result store.
- Save source/risk/cost identity, strategy parameters, sizes, account rules and
  assumptions, research windows/prior access, seeds/schedules and model/code hashes.
  Prove phase independence, full candidate membership and cache/deletion safety.
  Reject unsupported source scaling/profiles rather than inventing behavior.
- Select on IS only. Freeze the chosen phase package before manual final OOS;
  assessment applies frozen choices without reselection. Preserve editable splits
  and unlimited manual OOS history; do not relabel accessed data as untouched.
- Distinguish calendar from session time, model censoring from provider failure,
  conditional from unconditional estimates, and Monte Carlo error from future
  uncertainty. Never average only completed paths to fabricate an acquisition
  mean. Separate payout requests, account deductions and modeled trader receipts;
  disclose pending amounts and unverified settlement assumptions.
- Independent phase work does not undo completed portfolio phase-source or
  cash-ledger milestones. Portfolio optimization is optional downstream work and
  outside the initial implementation scope. Payouts cannot expand its hard monthly
  fee cap; unused allowance does not roll over.
- Each implementation milestone needs independent expected values, relevant
  boundary/rejection checks and a saved normal-product demonstration/downloads
  in `docs/prop_simulation_review.md`. Keep analytical fixture oracles in tests;
  label synthetic product sources. Documentation-only tasks need no artificial
  screen or simulation result. Do not claim numerical/provider parity without
  independently generated matching evidence.

# Architecture maintenance after phase migration

- Phase simulation belongs in `prop/evaluation_profiles.py` and
  `prop/funded_profiles.py`; selection/metric/artifact contracts belong in their
  respective `*_optimization.py` modules. Shared admission/calendar/capture is in
  `phase_profiles.py`/`phase_search.py`; use `phase_dispatch.py` for backend
  resolution. Unknown phases must reject; never silently fall back to a phase.
- API, AnalysisStore and campaigns orchestrate these owners. Do not duplicate
  simulations/selectors or create the formerly proposed `phase_optimization.py`
  or `phase_sampling.py` solely to follow obsolete design names.
- Preserve phase numerical hashes and legacy compatibility delegates for
  orchestration-only work. If numerical source changes are necessary, retain
  old reports and fail closed on incompatible frozen-package launch; never
  exclude changed calculation code from identity merely to allow reuse.
- New grid requests may set strict boolean `automatic_prop: false`; default true
  retains legacy automatic reports. Preserve per-job profiles/metric columns and
  cache separation, and keep opted-out trials usable by manual phase campaigns.
- Notebook `prop/analysis.py`, `model.py`, `settings.py` remain historical
  qualification/demo dependencies; format-1/2 readers remain supported. Prove
  absence of runtime, test, script and historical callers before retirement.
- Keep point-estimate selection distinct from precision/provider certification.
  Generated/adaptive campaigns, Lucid dated Evaluation and portfolio search are
  still pending. Update current documentation without deleting dated findings,
  ADRs, reports, immutable snapshots or prior numerical evidence.

# Prop Sim OOS economic review and start-date sensitivity

`prop/assessment_review.py` owns the additional versioned review of saved-source
Prop Sim OOS results. Require explicit immutable per-phase economic limits before
new Prop Sim OOS launches: Evaluation maximum acquisition cost/time; Funded minimum
received cash over its frozen horizon. Evidence minima and complete estimates are
separate from adverse IS-to-OOS watch flags. Historical assessments remain readable;
new retrospective limits never relabel their old verdicts. Reuse verified sealed
OOS outputs for review and account-start replay, without rerunning their MC search.
Prespecified full-window start dates use coverage alone; overlapping chronological
scenarios are dependent, with no replacement accounts or new size selection.
Keep the new review implementation hash separate and explicit in policies/reports,
while preserving unchanged phase numerical source hashes and frozen-package guards.

The approved Lucid model differences remain deliberate: no Evaluation consistency
cushion, fixed USD 1,200 DLL when enabled even above the trailing-profit threshold,
and 30 calendar days of inactivity. They are local assumptions, not new provider
parity claims. Portfolio allocation and full replacement cash-flow analysis remain
separate future increments. See the dated policy contract in
`docs/prop_simulation.md` and reproduction/evidence in `docs/prop_simulation_review.md`.

OOS economic limits can now change through explicit policy revisions in the
same simulation. Preserve each version and its original report verdicts, require
a reason and predecessor hash, and label post-access revisions retrospective.
Queued/running jobs retain their captured version. Re-review compatible sealed
OOS MC paths rather than rerunning optimization; require a current-version OOS
review before new account-start sensitivity. Expose history/version labels in the
normal portal. See the later revision contract in `docs/prop_simulation.md`.

Saved-source Prop Sim path count must not shrink with the selected size range.
Do not reintroduce aggregate estimated-capture/path-day caps for basic independent
Evaluation/Funded or their plain saved-source assessments, or the aggregate
report-size ceiling at their publication step. Retain all requested paths and
normal source evidence/downloads. The existing per-size input range is8–20,000
regardless of range size. Optional historical refits, native reruns and legacy
reports retain their separate bounds. See the dated path-count contract and
normal-product evidence in `docs/prop_simulation.md`/`prop_simulation_review.md`.

# Current qualified Prop Sim OOS presentation and reuse

The later user-approved historical qualification policy in `docs/prop_simulation.md`
supersedes mandatory business-dollar declarations for the default Prop Sim gate.
Business policies/revisions remain optional and keep their historical verdicts.
For qualified Prop Sim, identical assessment inputs reopen the running/completed
canonical job/report; do not create another report because a request UUID,
qualification timestamp or reuse-parent ID differs. Keep substantive rules,
implementation/source identity, diagnostic paths and explicit policy revisions
separate. Admission/reuse/queueing share the existing AnalysisStore lock; verify
sealed reports and IS/OOS source captures before complete reuse. Failed/stopped
attempts remain retryable. Do not rewrite or delete old reports or add a second
result store. The portal shows one current OOS table per phase, collapsed sizing
and criteria, and lazy individual historical report loading. The conclusion view
in `web/prop-sim-conclusion.js` explains saved server verdicts only; do not change
qualification or numerical identities to generate UI advice. Distinguish
inconclusive sizing from campaign failure, historical GO from forward readiness,
and historical-version results from current qualification. Expose confidence,
source-evidence and inner-MC precision blockers without promising that diagnostic
extra paths will update an OOS verdict. Keep checks focused
on `tests/test_prop_sim_assessment_reuse.py` and its browser journey for this
orchestration/presentation surface. Preserve numerical/qualification hashes.

# Automatic qualified Prop Sim workflow

New portal/API runs default to `automatic:true`: Run checks source admission,
executes both IS searches, selects families using `prop_sim_selection.py`, freezes
and runs OOS qualification without further confirmation. Read only sealed IS
frontier/ranking data for selection: Evaluation cheapest, fastest, and cheapest
within 1.25× fastest time (at most 3); Funded peak mean receipts and smallest size
retaining 95% (at most 2). Collapse duplicates and tie-break smaller MNQ. Persist
selection/source identity and original IS report hash; carry it into normal OOS
artifacts. Never use OOS to select replacements or fabricate forward execution.
`prop_sim_automation.py` continues on the existing AnalysisStore worker through
phase completion notifications and startup recovery. Preserve stop intent,
shared-job consumers, immutable freezes, idempotency and legacy manual records.
`automatic:false` is historical/API compatibility only; new UI always runs the
automatic plan. Explicitly scoped older manual browser fixtures use that flag;
`test_prop_sim_automatic_browser.py` verifies the unmodified automatic default.
Use the focused selector/orchestration tests in `test_prop_sim_automatic.py` and
the one-click product journeys when changing this surface. Do not require a page
to remain open, add another scheduler/service/store, or change numerical owners
for orchestration-only work. See the dated product/evidence contract.

Qualified OOS historical refits now use `prop/oos_bootstrap.py` on the existing
`prop/parallel.py` Runtime, four workers by default. Preserve index-derived seeds,
ordered output, full path counts, unchanged phase owners and bounded shared CPU
reservations. Capture dispatcher/runtime hashes in qualification identity. Worker
stop markers must drain active siblings before releasing the reservation. Progress
belongs to `phase_analysis_progress` in the existing catalogue and is metadata
only, throttled to one-second writes. Prop Sim and Job history share
`web/prop-progress.js`; no polling-triggered calculations. Check exact serial
parity/cancellation with `test_prop_confidence_parallel.py` and the actual product
journey in `test_prop_confidence_parallel_browser.py`. Preserve old sealed reports.
