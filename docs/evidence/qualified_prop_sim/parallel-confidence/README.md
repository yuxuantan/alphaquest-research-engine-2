# Four-worker historical confidence and live progress

Actual normal-product screenshots, progress samples and sealed downloads from
the qualified backtest → Prop Sim → automatic IS/freeze/OOS workflow. **All example
prices, market dates and executions are SYNTHETIC**, including future-dated bars.
These demonstrate local arithmetic and integration; they do not qualify provider
execution or forecast future performance. Earlier evidence is preserved unchanged.

## Inspect these outputs

- `configuration.png`: existing Prop Sim entered from the qualified IS backtest
  report; separate 9–10 MNQ phase searches, eight paths per size, LucidFlex 50K.
- `prop-sim-progress.png`, `job-history-progress.png`: the same actual running
  confidence job, advancing count/bar, four workers, elapsed time, current-size
  ETA and last-update time on both pages.
- `observed-job-progress.json`: actual metadata polled through the normal Job
  history API while the background job executes; counts increase.
- `evaluation-complete.png`, `funded-complete.png`, `mobile.png`: durable OOS
  results after the single initial Run, reload and mobile layout.
- `evaluation-oos.zip`, `funded-oos.zip`: normal sealed product downloads with
  source captures, account paths, original frozen choices, complete historical
  bootstrap traces, policy/code identities and execution diagnostics.
- `journey.json`: normal source/simulation IDs and complete saved automatic plan.
- `evaluation-serial-parity.json`, `funded-serial-parity.json`: separate analytical
  fixture checks using non-identical daybooks and two actual worker processes,
  exactly matching an independent copy of the preceding sequential seed/refit
  contract. These are test oracles, not additional product reports.
- `independent-verification.json`: actual read-only arithmetic/provenance result.
  `SHA256SUMS` identifies every saved artifact.

## Independent expectations

The source repeats an identical six-trade weekday pattern, IS 2024–2025 and OOS
2026. Both tested sizes reach the same point objectives, so automatic roles
collapse onto 9 MNQ. LucidFlex Evaluation costs $80.50 with no activation fee and
requires three calendar days from the Monday scenario start at 40% consistency.
Fresh-Funded receipts are `5 × $2,000 × .90 = $9,000` per path, including all eight
paths in the mean and distinguishing trader cash from account deductions.

Identical numeric daily inputs independently imply all 10,000 historical OOS/IS
ratios and their confidence bounds equal **1.00**. The observed execution must
record four distinct worker PIDs without nested pools; all 10,000 rows stay in
replicate-index order and retain their original seeds. Historical qualification
is GO and genuine forward execution stays PENDING. A constant-history oracle
does not test real-market uncertainty or prove a fourfold runtime improvement.

Read-only verification, without importing the production simulation owners:

```sh
.venv/bin/python scripts/verify_prop_parallel_confidence_evidence.py
```

Expected: two verified phase records, four workers/PIDs, 10,000 resamples, eight
paths per size, bounds [1, 1], GO, forward PENDING and matching source identities.

## Reproduce the user journey

1. Open an IS backtest report from a campaign that passed every required strategy
   phase and final Monte Carlo. Follow **Prop Sim**.
2. Configure the account, independent phase size ranges, path count, costs and
   calendar/horizon. Click **Run IS and OOS** once. Source checking is integrated.
3. In the phase's current OOS card, observe the historical-confidence bar, size
   position, resamples and active workers. Follow **Job history / progress** to
   see the same metadata there. Counts update without another calculation.
4. Navigate away and return. Both OOS jobs continue automatically; sizes remain
   frozen. Download the final normal ZIPs and reload the page.

For the exact synthetic product reproduction:

```sh
ALPHAQUEST_PROP_PARALLEL_EVIDENCE_DIR=/private/tmp/aq-parallel-evidence \
  .venv/bin/python -m pytest -q tests/test_prop_confidence_parallel_browser.py
```

It creates its own qualified synthetic source and temporary product server. An
optional `ALPHAQUEST_QUALIFICATION_SEED_LIBRARY` may identify an isolated copy of
the already-qualified synthetic fixture; each test clones it. The actual browser
test captures live progress on both pages, waits for both completed numerical
reports, downloads ZIPs and checks reload/390-pixel layout. No user library is
used. The temporary server stops at fixture teardown.

Focused numerical/runtime boundary checks:

```sh
.venv/bin/python -m pytest -q tests/test_prop_confidence_parallel.py \
  tests/test_prop_oos_qualification.py::test_actual_account_owners_resample_histories_and_preserve_path_count \
  tests/test_prop_parallel_runtime.py::test_shared_budget_ordered_results_and_no_nested_worker_pool \
  tests/test_prop_parallel_runtime.py::test_concurrent_serial_reservations_transfer_without_deadlock
```

Expected: eight passing checks. Non-identical daybooks produce exact sequential
reference traces/metrics in both phases. Cancellation signals active children,
drains them before returning CPU slots and leaves the pool reusable. Progress
reads use metadata only and its rows are removed with the analysis. An explicit
single worker or smaller available CPU budget falls back to the same numerical
contract. The default is four workers within the existing machine capacity;
`ALPHAQUEST_PROP_WORKERS` retains its existing bounded override.

Qualification captures the new dispatcher/runtime hashes explicitly; historical
reports remain sealed/readable. All 33 phase numerical files are unchanged, so
IS reports and frozen choices remain compatible. The user's active OOS job was
left untouched during isolated development/testing; applying to the auto-reload
server and restarting unfinished OOS was separately approved. Original completed
IS reports and frozen packages must remain identical after that restart.

The authorized live restart was also checked through the existing APIs:
Evaluation job `4b184f9d2ed34c21a24d2ab7b2d7ae7c` advanced from 3 to 22 resamples
with four active child processes near 100% CPU each; Funded job
`31b8953ee1f049f29d611db8eeed89e2` is queued normally behind it. Both completed
IS report IDs and frozen-package hashes matched the saved pre-restart values.
These are startup/progress observations, not final results for the user's real
history. The original unfinished jobs remain in history as cancelled attempts.
