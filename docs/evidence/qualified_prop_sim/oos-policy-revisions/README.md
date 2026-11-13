# Revise saved OOS assessment limits — 13 November 2026

This increment supersedes the requirement to create a new simulation for a
changed business limit. Each version remains immutable; explicit revisions keep
history and append a fresh assessment. Production uses the existing Prop Sim
parent and AnalysisStore, with no new account engine, service or result store.
Earlier evidence in `../oos-policy-starts/` remains untouched.

## Use the portal

1. Refresh your saved simulation's normal `#prop-sim?analysis=...` page.
2. Click **Revise assessment limits** in the desired phase. Edit the values and
   supply a reason. **Cancel revision** restores saved values without saving.
3. Click **Save new policy version**. Expand **Policy history** to inspect earlier
   limits, timestamps and reasons. Existing one-policy simulations become version 1
   without changing the original policy's contents or hash.
4. Click **Run OOS assessment** to apply the current version. Compatible sealed
   OOS paths are reused, so neither IS nor Monte Carlo needs rerunning. Saving
   limits alone does not launch a calculation or rewrite a report.
5. Old results remain labeled with their original policy version and verdict;
   new results use the current version. Revision after OOS access is retrospective.
   Running jobs finish under the version captured when they started.
6. After the current-version OOS review completes, **Check account-start
   sensitivity** uses that policy's covered-start plan. Changing Evaluation's
   time limit or start count changes future diagnostic windows/dates; old plans
   and results remain. Frozen sizes, strategies, costs and account rules stay put.

A stale edit from another browser tab returns 409 and asks for a reload. Retrying
an identical just-saved revision does not append another copy. Blank reasons,
no-op revisions, wrong-phase limits and invalid values reject. Reverting is a
new revision with the earlier values and a reason, never deletion of history.

## Reproduce the actual product journey

From the repository root:

```sh
ALPHAQUEST_PROP_VALIDATION_EVIDENCE_DIR=/private/tmp/aq-oos-revision-reproduction \
  .venv/bin/python -m pytest -q \
  tests/test_prop_sim_browser.py::test_prop_sim_variants_frozen_assessment_robustness_precision_product_journey

.venv/bin/python -m pytest -q \
  tests/test_prop_evaluation_validation.py::test_variant_phase_independence_frozen_oos_robustness_precision_and_reopen

.venv/bin/python docs/evidence/qualified_prop_sim/oos-policy-revisions/verify_revision.py
```

The browser uses normal labeled synthetic dataset/backtest -> campaign
mechanics/Broad/Narrow/OOS/Monte Carlo qualification -> Prop Sim configure ->
source check -> Evaluation/Funded workers -> freeze -> OOS -> revision -> new
assessment -> JSON/ZIP downloads -> reload and mobile layout. There is no
fixture-only API, fabricated measured risk or external engine result in the
product calculation. Synthetic dates may extend past the test date; these are
not actual historical performance or predictions. Temporary test servers stop
at teardown and the user's existing server/jobs/data remain unchanged.

## Independent expected observations

The source, quantities, seeds and numerical rules match the preceding synthetic
journey: 12 MNQ, Lucid's purchased 50% consistency variant, fixed DLL enabled,
$99.50 purchase fee, no activation fee, $0.50 per MNQ side, 16 paths/seed 42/block 5.

- Evaluation version 1 permits mean cost≤$500 and time≤180 days. Its actual OOS
  mean cost is **$130.59375**, so PASS. Version2 changes only maximum cost to
  **$50**, producing FAIL with the exact same paths and metrics.
- Funded version 1 requires mean receipts≥$100 over 90 days. Its actual mean is
  **$2,812.50** including zeros, so PASS. Version2 raises the minimum to **$5,000**,
  producing FAIL with the same received-cash events and metrics.
- Both revision reasons are visible and both version 2 policies are retrospective.
  Canceling a draft edit leaves version 1 values intact. Reload retains versions,
  superseded PASS reports, current FAIL reports and frozen selections.
- The API test poisons the MC optimizer during reuse, changes the start count
  from 5 to 3, rejects stale/no-reason edits, accepts idempotent retries, and reverts
  via version 3. A paused running Evaluation review captures version 2; version 3
  is saved while it is running; the published review still contains version 2.
- Account-start launch after revision requires a completed OOS review of that
  version. It then uses the revised count/window without changing the old MC
  paths or any previous report. There is no automatic OOS reselection.

These dollar limits are deliberately synthetic test decisions, not suggested
commercial thresholds. PASS/FAIL here evaluates declared business limits and
sufficient evidence, not provider/live qualification or future certainty.

## Inspect saved outputs

- `*-oos-report.json`, `*-oos-evidence.zip`: original version 1 PASS reports.
- `*-revised-report.json`, `*-revised-evidence.zip`: version 2 FAIL reports and
  normal sealed downloads, including their saved policy and predecessor identity.
- `*-policy-revision.png`: inspected real portal history and both report versions.
- `variant-configuration.png`, `validation-mobile.png`: configuration and mobile UI.
- `verification.json`: product journey IDs, settings, revision metadata and checks.
- `verify_revision.py`: independent fee/cash sums, limits, unchanged path/metric
  checks, predecessor hashes and original ZIP report-hash verification.
- `independent-verification.json`: saved output from that verification.
- `source-identity.json`: all 33 numerical source hashes per phase unchanged, with
  the review implementation unchanged too. Only orchestration/UI contracts change.
- `sha256.json`: final evidence checksums, excluding the index itself.

Earlier snapshots and reports remain unchanged. Account rules, portfolio allocation
and full replacement-account cash-flow scope remain as previously agreed.
