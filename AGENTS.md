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
