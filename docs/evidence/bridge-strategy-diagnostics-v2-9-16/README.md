# Bridge Prop Desk v2.9.16 strategy diagnostics

Captured on 2026-11-22 in the existing Windows demo session. See the
[reproduction steps and findings](../../prop_simulation_review.md#bridge-prop-desk-v2916-strategy-diagnostics--2026-11-22).

- [Starting Simulation](start.png) shows the original four-strategy Funded
  portfolio and profile.
- [Whole history](strategy-open-now.png) and [Since going live](relative-strength-since-live.png)
  show the Relative Strength cone. [Drawdown](relative-drawdown-matrix.png),
  [Sum](relative-sum-matrix.png), and [status and recovery](relative-detail-status.png)
  show the strategy-level drawdown views.
- [Matrix values](relative-strength-matrices.csv) are transcribed from the
  screenshots in signed USD. The drawdown percentiles rank by depth. The
  sum percentiles rank signed net P&L.
- The files with an `archive-` prefix came from the prior Bridge desktop
  inspection on the same date. The other screenshots came from the live
  comparison documented here.
- [Cone endpoints](cone-endpoints.csv) records the source dates, counts and
  terminal values for both strategies. [Luck Alone observations](luck-alone.csv)
  records the displayed baseline, row-one rates, point gap, number of copies,
  and displayed range for each comparison. Both CSVs are screen transcriptions.
- [Single-strategy Evaluation](single-opt-eval.png), [two-candidate Evaluation](two-opt-eval.png),
  [two-candidate Funded](two-opt-funded.png) and [Funded pair only](pair-only-funded.png)
  show the changes to the Optimise headline. [Loaded Twin](two-opt-loaded-twin.png)
  and [loaded pair](pair-only-loaded.png) show the resulting Simulation.
- [Restored Simulation](restored.png) shows the original portfolio weights,
  allocations, profile, phase and first-year size preset.
