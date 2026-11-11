# Temporary test scope during the workflow revamp

- Use the smallest test set relevant to the current change. A plain pytest run
  selects the seventeen focused mechanics/job-history/IS Broad criteria checks via `pyproject.toml`.
- For changes to the current UI, explicitly select the relevant cases in
  `tests/test_campaign_mechanics_browser.py` or
  `tests/test_workflow_navigation_browser.py`, `tests/test_job_history_browser.py`,
  `tests/test_campaign_broad_browser.py`, or `tests/test_campaign_narrow_browser.py`.
  Browser checks are opt-in; select only the affected journey.
- Older regressions remain intact but are excluded from default discovery.
  Do not routinely run the previous 180-check set or the full suite for each
  increment. Run a specific older test only when the change affects its behavior,
  or run a broader suite when the user requests it. Extend the focused default
  as new workflow phases are implemented.

# Agreed campaign screening policy

Follow `docs/workflow_screening.md` for the implemented IS Broad and IS Narrow
criteria. OOS execution remains planned. The portal shares server-owned rules
from `alphaquest/workflow_criteria.py` and `alphaquest/campaign_narrow.py`.
Preserve policy snapshots and historical confirmations; do not relabel an older
rule as passing a newer one.

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
