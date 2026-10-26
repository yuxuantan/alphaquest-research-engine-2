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

Current scope: new prop analyses use the licensed The Bridge Funded Lab CLI as
the calculation authority. The Bridge is a black box; do not infer or fit its
engine from saved outputs. Preserve the qualified executable/input/settings
hashes and compare fresh actual outputs against the supplied Bridge report.
The old pinned notebook and numerical modules are historical qualification
material only. Keep old saved reports immutable and label their previous model.
New runs must use the existing backtest → configure → check → run → report
workflow. Reconcile every companion export trade ID, direction, UTC entry time,
quantity and net P&L to its native backtest before using measured excursions.
Do not fabricate missing MAE/MFE or deduct costs twice. Never bypass or copy
Bridge license credentials. Invoke funded-lab only; leave collector/live/broker
operations and the user's Windows VM and servers alone. Preserve all prior
datasets, backtests, results and evidence. No official-rule research gates or
mandatory full-session bar calendars are part of this integration.
