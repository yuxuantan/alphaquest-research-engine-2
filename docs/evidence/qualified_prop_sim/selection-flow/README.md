# IS table selection → frozen OOS validation — 12 November 2026

This presentation increment uses the existing Prop Sim workflow and numerical
reports. It moves size checkboxes beside the IS cost/time or cash metrics,
removes the duplicated forty-tile selector, and makes frozen OOS assessment the
primary next action. No API, numerical source, account rule, eligibility policy,
frozen package or stored report is changed.

## Reproduce the normal product journey

```sh
ALPHAQUEST_PROP_VALIDATION_EVIDENCE_DIR=/private/tmp/prop-selection-flow-reproduction \
  .venv/bin/python -m pytest -q \
  tests/test_prop_sim_browser.py::test_prop_sim_variants_frozen_assessment_robustness_precision_product_journey
```

The fixture starts an isolated temporary server and stops it at teardown. It
uses the normal labeled synthetic NQ dataset/backtest -> mechanics/Broad/Narrow/
OOS/Monte Carlo qualification -> Prop Sim source check -> actual Evaluation and
Funded engines -> saved reports. No real user simulation or source is changed.
The $99.50 Lucid 50% purchase price is an explicit synthetic scenario input,
not a provider quote.

Expected observations in the actual portal:

1. In each **IS results** table, select **12 MNQ** beside its metrics. Only
   eligible rows have a checkbox. The compact summary reads
   **Selected: 12 MNQ · 1 of 4 sizes**; no size grid exists in validation.
2. Sort the MNQ column in both directions: the same candidate remains checked.
   Enter the required single-line selection note, then freeze. Frozen IDs and
   their rationale retain the existing immutable package contract.
3. The section becomes **OOS validation**, with only **Frozen choices: 12 MNQ**
   in its summary. IS checkboxes are locked. **Run OOS assessment** is enabled
   as the primary action, and **Additional diagnostics** is collapsed.
4. Run OOS. Its saved results, chronological observation, progress and downloads
   are visible directly in the validation section. Only the frozen ID appears.
5. Expand Additional diagnostics to run IS block/subperiod robustness (8 paths)
   and more-path precision (64 paths). Their controls and saved result sections
   stay inside that details panel. Closed diagnostics do not fetch result bodies;
   metadata/progress polling remains available while jobs run.
6. Reload: frozen choices and OOS results reopen, with diagnostics collapsed.
   The 390-pixel mobile page has no horizontal page overflow; wide metrics tables
   scroll within their own containers. Checkbox and MNQ columns stay pinned.

The saved source, variant and path settings match the preceding validation
increment. Independent all-path arithmetic still gives Evaluation's initial
**$99.50 mean cost** and **13.875 mean calendar days** at both tested sizes:
**0 + 9.4375 + 2.9375 + 1.5 = 13.875** for earlier attempts, first target,
further trading and readiness. Funded's initial all-start mean receipts are
**$39,600 / 16 = $2,475**. These are labeled synthetic observations, not future
performance estimates for the user's strategy.

`*-selection-summary.png`, `*-validation.png` and `validation-mobile.png` show
the new UI. `verification.json` records the actual source/run/frozen identities,
baseline arithmetic and six completed assessments. The corresponding JSON and
ZIP downloads contain the normal sealed numerical evidence. Earlier evidence
in `../validation/` remains unchanged.

## Focused presentation boundaries

```sh
.venv/bin/python -m pytest -q \
  tests/test_prop_sim_browser.py::test_is_table_size_selection_limits_exclusions_sorting_and_compact_summary \
  tests/test_prop_sim_browser.py::test_evaluation_pareto_chart_tradeoffs_ties_and_unresolved_rows
```

The forty-size presentation oracle stays in tests, not the product. It shows
all forty comparison rows but only ten eligible checkboxes (3–12 MNQ), explicit
**Outside Pareto frontier** and **Unresolved** reasons, and a specific Funded
constraint reason. Four selected sizes disable additional choices; removing one
re-enables them. Sorting retains all selected IDs. No duplicate selector or
pre-freeze OOS/diagnostic action appears. The existing server requirement to
resolve a search before freezing is displayed, not silently changed. The normal
product journey above separately proves actual calculations and submission.

Refresh an existing current-model saved simulation to use the new flow. This UI
change requires no new backtest or simulation. Older numerical-version guards
remain as before; no historical package is silently upgraded.
