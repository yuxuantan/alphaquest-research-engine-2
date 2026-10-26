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
