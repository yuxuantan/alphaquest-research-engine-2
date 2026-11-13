# Automatic Prop Sim sizing and execution — 2026-11-13

Actual screenshots and downloads from the existing backtest → Prop Sim → sealed
phase results workflow. **All example market prices, dates and executions are
SYNTHETIC**, including future-dated bars. These prove local arithmetic and product
integration; they are not provider parity, trading readiness or a forecast. No
user library, running job, server or Windows VM was changed. Temporary servers
stopped at fixture teardown.

## Final inspectable outputs

Use `final/apex-50k-eod/` and `final/lucidflex-50k/`:

- `configuration.png`: ordinary Prop Sim configuration after entering from the
  existing qualified IS backtest report. The only launch action is **Run IS and OOS**.
- `evaluation-complete.png`, `funded-complete.png`, `mobile.png`: automatic roles,
  frozen sizes, current OOS results and durable mobile presentation.
- `evaluation-is.json`, `funded-is.json`: original normal-product IS reports,
  retaining every tested size and the complete frontier/ranking.
- `evaluation-oos.zip`, `funded-oos.zip`: normal evidence downloads, including
  sealed reports, source captures, actual account paths, frozen packages,
  qualification policy and historical-bootstrap traces.
- `simulation.json`, `journey.json`, `*-summary.json`: saved plan, policy/source
  identities, automatically selected roles, durable job IDs and result summaries.

The first demonstration folders alongside `final/` are retained unchanged. The
final captures additionally save the original IS reports for offline hash checks.
`SHA256SUMS` covers all saved artifacts. The actual synthetic market CSV and its
construction are retained in [the prior qualification evidence](../oos-confidence/README.md).

## Independently expected observations

The repeated six-trade weekday pattern uses IS 2024–2025 and OOS 2026. OOS has
twelve complete months and `261 × 6 = 1,566` closed source trades. Every numeric
daybook is identical, so each resampled history must have the same economics.
Both phase searches test **9 and 10 MNQ**, with eight declared paths per size;
the two sizes hit identical account objectives on this particular synthetic
history. The smaller-size tie rule must select **9 MNQ**. All three Evaluation
roles, and both Funded roles, collapse onto that one size; the engine must not
pad either family or pick a size using OOS performance.

| Profile | Evaluation cost / calendar days | Fresh-Funded mean cash receipts |
| --- | --- | --- |
| Apex 50K EOD | $49 + $129 = **$178 / 2 days** | **$13,000** |
| LucidFlex 50K | **$80.50 / 3 days** at 40% consistency | 5 × $2,000 × 90% = **$9,000** |

Funding time is measured from the saved Monday start, including modeled
pass-to-ready time. Funded means include all eight paths and distinguish trader
receipts from account deductions. The OOS/IS point ratios and both confidence
bounds must be **1.00**, across all 10,000 historical replicates. This exact
constant-history oracle does not represent real-market uncertainty. Historical
qualification is GO, while genuine forward execution remains **PENDING**.

The original IS report's canonical SHA256 must equal the saved selection's IS
report hash and the immutable OOS frozen package's parent-report hash. The OOS
family IDs must exactly match the IS selection. There is only one OOS assessment
per phase, and **zero required follow-up actions**. Reopening does not resimulate.

Read-only verification, without engine imports or simulation:

```sh
.venv/bin/python scripts/verify_prop_automatic_flow_evidence.py
```

Expected: four verified account/phase records, chosen size 9, collapsed role counts
3/2, matching original IS hashes, GO and forward PENDING.
`independent-verification.json` records this actual output;
`unchanged-implementations.json` verifies all 33 existing numerical source hashes
against the original reports, HEAD and working tree, plus selection-source identity.

## Reproduce in the actual product

1. Open an existing backtest report belonging to a campaign that passed mechanic
   validation, Broad, Narrow, OOS and Monte Carlo. Follow **Prop Sim**.
2. Select Apex 50K EOD or LucidFlex 50K and configure independent Evaluation and
   Funded size ranges, paths, fees, horizon, calendar and optional risk settings.
3. Click **Run IS and OOS**. Checking the source is included; the Check button is
   optional. No size selection, rationale, freeze or OOS confirmation follows.
4. Navigate away if desired. Return using Saved simulations or Job history.
   Inspect automatic roles and the current OOS table under each phase; download
   the original IS reports, frozen package and OOS ZIP. Reload to confirm durability.

For the exact synthetic browser reproduction:

```sh
ALPHAQUEST_PROP_AUTOMATIC_EVIDENCE_DIR=/private/tmp/aq-auto-evidence \
  .venv/bin/python -m pytest -q tests/test_prop_sim_automatic_browser.py
```

This creates and qualifies its own labeled synthetic dataset through existing
APIs, launches temporary normal-product servers, uses Chromium from the backtest
report, clicks only Run, leaves the page, returns to both completed OOS reports,
downloads evidence and checks reload/mobile layout. Optional
`ALPHAQUEST_QUALIFICATION_SEED_LIBRARY` names an isolated copy of the already-created
synthetic test library; each test clones it and never mutates a user library.

Focused boundary/recovery reproduction:

```sh
.venv/bin/python -m pytest -q tests/test_prop_sim_automatic.py
```

Expected boundaries: the Evaluation 1.25× time boundary and Funded 95% receipts
boundary are inclusive; duplicate roles collapse; unresolved/infeasible sizes do
not block resolved eligible ones; zero Funded receipts produce no selection/OOS
for that phase while Evaluation finishes; unknown phases, assessment reports and
manual freeze overrides reject. Recovery after an interrupted freeze/launch keeps
the exact frozen package. Stop prevents follow-on work and cancels owned jobs;
a shared IS job remains available to another run, which still completes. OOS
does not replace failed candidates or retry a NO_GO seeking a favorable outcome.
Older manual records keep their existing workflow and reports unchanged.
