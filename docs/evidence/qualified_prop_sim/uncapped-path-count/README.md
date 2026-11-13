# Paths are independent of the size range — 13 November 2026

The former Funded path cap was an approximate report-storage admission estimate:
`100 × 1024 × 1024 / (40 sizes × 5,000 bytes per path)`, rounded down, is 524.
It was not an account rule or statistical requirement. That size-dependent cap
is removed from the portal and basic saved-source phase admission/publication.
All requested paths remain in the saved report and normal ZIP downloads.

## Normal product steps

1. Open an eligible saved IS backtest report and click **Configure prop simulation**
   (or open its usual Prop Sim page).
2. Select your qualified configuration/account and set either phase to 1–40 MNQ.
   Enter 1,000 paths per size, per phase. The preview shows the requested count
   and total; it no longer reduces it to 524 or disables checking due to an
   estimated capture size.
3. Click **Check source and settings**, then **Run Evaluation and Funded**.
   Inspect progress here or in Job history.
4. Reopen the saved simulation and download each normal **Evidence ZIP**.
   `report.json` retains each candidate's configured path count and every path.

The path field's existing 8–20,000 range is the same at every size range. This
increment removes the coupling between size count and allowed paths. It also
removes basic saved-source aggregate path-day/capture gates and their report
publication ceiling, so they cannot reject the expanded run later. Native signal
reruns, optional historical refits and legacy reports retain separate contracts.

## Actual saved demonstration

`forty-size-configuration.png` shows the real portal requesting 40 sizes in each
phase and 1,000 paths per size: **80,000 paths overall**. The actual qualified
pipeline uses labeled SYNTHETIC prices, not real market performance or future
predictions. It runs mechanics/Broad/Narrow/OOS/full-period Monte Carlo before
becoming selectable in Prop Sim. AlphaQuest computes both phase reports locally.

The synthetic account is Apex 50K EOD, sizes 1–40 for both phases,1,000 paths,
seed 42/block 5, $49 purchase/$129 activation, $0.51 commission per MNQ side, and
an explicitly selected **10-calendar-day Funded horizon**. The short horizon
keeps this boundary demonstration focused and is not a recommended assessment
horizon. All sizes retain every requested path; no truncation/subsampling occurs.

Independent expected observations:

- Each report has 40 candidates, the complete size set 1…40, and 1,000 path rows
  for each candidate: **40,000 captured paths per phase**.
- The old Funded estimate is 200,000,000 bytes, above 100 MiB, yet source checking,
  launching, both workers, durable publication and reload succeed.
- Each Funded mean equals the sum of **all 1,000** path receipts divided by 1,000,
  including zeros. Each path's received cash equals its received payout events;
  pending entitlement is not silently counted.
- Each resolved Apex Evaluation cost equals `$49 / empirical attempt pass
  probability + $129`, independently computed from the saved report metrics.
- Saved source captures, full path outcomes, source identities and normal report
  downloads remain present. Frozen/source qualification and phase independence
  remain enforced.

## Reproduce

From the repository root:

```sh
ALPHAQUEST_PROP_PATH_EVIDENCE_DIR=/private/tmp/aq-path-count-reproduction \
  .venv/bin/python -m pytest -q \
  tests/test_prop_sim_browser.py::test_forty_sizes_keep_one_thousand_paths_through_saved_product_results

.venv/bin/python -m pytest -q \
  tests/test_phase_resource_bounds.py \
  tests/test_prop_oos_source_identity.py::test_admission_revision_compatibility_is_exact_directed_and_preserves_hashes

.venv/bin/python docs/evidence/qualified_prop_sim/uncapped-path-count/verify_outputs.py
```

The browser test uses a temporary isolated server/catalogue and stops it at
teardown. Submission waits allow the full source-check request to finish; the
original 30-second browser-test budget was insufficient for this larger request.
No existing user simulation is submitted/stopped and no persistent server starts.
The saved browser result table and reload contain all 40 sizes. Fast automated
boundaries also admit 40×20,000 paths, retain optional-refit/unknown-phase rejection,
and publish a 129-MiB captured artifact with the saved-source publication option
while retaining the legacy rejection.

## Evidence and compatibility

- `evaluation-forty-size-evidence.zip`, `funded-forty-size-evidence.zip`: actual
  normal AnalysisStore downloads, containing full 40,000-path reports per phase.
- `forty-size-verification.json`: actual job/workflow IDs, counts, settings,
  download sizes and durable reload observations.
- `forty-size-configuration.png`, `forty-size-funded-results.png`: inspected UI.
- `verify_outputs.py`: independent read-only path-membership/cash/cost arithmetic.
- `independent-verification.json`: source-hash and existing-report compatibility
  checks, with exact old/new admission source hashes.
- `sha256.json`: final evidence checksums, excluding the index itself.

Only the admission file `phase_search.py` changes its fingerprint:
`a078590d…3a051` -> `14fbe784…ec36c`. The other 32 fingerprinted source files per
phase and all numerical/account kernels remain unchanged. Directed compatibility
admits exactly that reviewed transition, and the preceding known audit revision,
when every other implementation field matches. Unknown or numerical changes
still reject. Old reports/packages/evidence remain unchanged and compatible.
