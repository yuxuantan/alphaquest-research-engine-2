# Resolved selections can freeze beside unresolved sizes — 13 November 2026

The freeze admission rule now checks the selected candidates only. Each must
still be a resolved IS Evaluation frontier point or feasible ranked Funded
candidate. An unselected unresolved row does not block freezing. Such rows stay
visible and unselectable; the portal and chart download explicitly describe the
Evaluation frontier as comparing resolved candidates only. No numerical owner,
account rule, saved report, computation cutoff or frozen choice is rewritten.

## Existing saved simulation: read-only portal demonstration

Open `http://localhost:8000/#prop-sim?analysis=2d19909ce7b3404ca73adb534d6a8d2a`,
refresh, and select 3, 6, 8 and 12 MNQ in Evaluation's IS results table. Enter a
selection note. **Freeze selected sizes** is enabled even though 1 and 2 MNQ
remain unresolved. Only after you submit Freeze will **Run OOS assessment**
become available for those frozen choices. No sizing simulation rerun is needed.

`live-run-readonly.png` and `live-run-readonly.json` demonstrate this exact saved
run with the current portal. The temporary browser only read existing reports,
checked local controls and entered a local note. It submitted zero write
requests: the user's simulation was neither frozen nor assessed by this check.
The 1/2-MNQ unresolved rows still have no selection checkbox. The comparison
scope is explicitly limited to resolved candidates.

## Independent native calculation and freeze/OOS boundary

```sh
ALPHAQUEST_RESOLVED_FREEZE_EVIDENCE_DIR=/private/tmp/resolved-freeze-reproduction \
  .venv/bin/python -m pytest -q \
  tests/test_research_campaigns.py::test_freeze_resolved_selection_with_other_censored_candidates
```

This normal backtest -> configure phase campaign -> source check -> local
worker -> saved report -> freeze -> OOS -> durable exports journey uses a
labeled synthetic source in an isolated temporary catalogue. It does not use or
modify the user's sources. The explicit three-calendar-day guard makes the
boundary reproducible without thousands of trading days.

Independent expected arithmetic: the source earns $3,000 per NQ per trading
day, or $300 per MNQ. At 1 and 3 MNQ, three days cannot reach the $3,000 target.
At 10 MNQ, the account reaches its target Monday, advances through one activation
session Tuesday and is ready Wednesday: **2 calendar days**, **$30 purchase +
$40 activation = $70 acquisition cost**. All eight paths agree. This is a
synthetic Apex clock/fee oracle, not a future outcome for the user's Lucid run.

Expected boundary observations:

- 1 and 3 MNQ are censored/unresolved; 10 MNQ is a resolved frontier point.
- Selecting an unresolved size alone or alongside the resolved size rejects
  with HTTP 422. Unknown membership also rejects, without creating a freeze.
- Selecting only 10 MNQ succeeds despite the unresolved rows. Repeating the
  same freeze returns the same package; freeze/read operations cannot invoke
  the optimizer. Existing source/report file hashes remain unchanged.
- OOS runs only the frozen 10-MNQ candidate, without invoking the Pareto selector
  or modifying IS results. Its report remains assessment-only, with no winner.

`evaluation-report.json`, `frozen-package.json`, `oos-report.json`, and their
normal `is-evidence.zip` / `oos-evidence.zip` downloads retain those actual
outputs and provenance. Fixture expectations remain in tests.

## Qualified Prop Sim product regression

```sh
ALPHAQUEST_PROP_VALIDATION_EVIDENCE_DIR=/private/tmp/resolved-freeze-product \
  .venv/bin/python -m pytest -q \
  tests/test_prop_sim_browser.py::test_is_table_size_selection_limits_exclusions_sorting_and_compact_summary \
  tests/test_prop_sim_browser.py::test_prop_sim_variants_frozen_assessment_robustness_precision_product_journey
```

The first case is a presentation oracle kept in tests: forty comparison rows,
explicit unresolved exclusion, a four-choice limit, sort/sticky behavior and an
enabled freeze with a nonempty note despite an unselected unresolved row. It
also checks the new resolved-only comparison labels.

The second uses the actual synthetic qualified backtest -> account configuration
-> source check -> both phase engines -> freeze -> OOS/robustness/precision ->
saved reload/download flow. `product/verification.json` records all six
assessment identities and independent all-path arithmetic; its screenshots and
both OOS evidence ZIPs are saved here. Earlier evidence directories are intact.
Both browser servers stop on fixture teardown. The read-only inspection uses
and leaves the user's existing port-8000 server running.
