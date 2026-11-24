# Delete a saved Prop Sim run — 12 November 2026

The normal Prop Sim page now offers **Delete simulation** on a saved result and
**Delete selected simulation** beside its saved-run selector. It previews the
selected profile/strategy/date and the counts of unshared reports to remove and
shared/protected reports to keep, then asks for confirmation. Running/queued
jobs block deletion; stopping a job does not itself delete its results.

Deletion removes the parent saved entry, its unused internal phase campaigns,
and unreferenced phase analysis records/files/cache entries. Reports used by
another simulation/campaign or frozen/assessed dependency are retained. Source
datasets/backtests and the campaign mechanics/Broad/Narrow/OOS/Monte Carlo
workflow are not deletion targets. An audit receipt keeps metadata, not another
numerical result copy; deleted request IDs cannot silently recreate the run.

## Reproduce the actual product demonstration

From the repository root:

```sh
ALPHAQUEST_PROP_DELETE_EVIDENCE_DIR=/private/tmp/prop-sim-deletion-reproduction \
  .venv/bin/python -m pytest -q \
  tests/test_prop_sim_browser.py::test_delete_saved_simulation_confirmation_and_source_preservation
```

The test uses a **labeled synthetic NQ source**, qualifies it through the real
campaign phases/current Monte Carlo, runs one Evaluation and one Funded size
with eight paths each through normal Prop Sim APIs, and opens the actual saved
results page. It first dismisses deletion and confirms the run still exists;
then it accepts the product confirmation and deletes that generated run.
No real user simulation is deleted. Its temporary test server stops at teardown.

Expected observations:

- Exactly **two unshared phase reports** are removed; no shared report is
  retained in this single-run scenario.
- The saved entry disappears, its status/report routes return 404, and its two
  phase jobs no longer appear in Job history.
- The source backtest JSON is identical before/after, the frozen Narrow selection
  is unchanged, and the original Monte Carlo report bytes/checksum are unchanged.
- Reloading `#prop-sim?deleted=<id>` shows the durable deletion receipt summary.
  The mobile page does not overflow horizontally.

Saved outputs from that real normal-product journey:

- `delete-action.png`: saved-result header with the Delete action.
- `deleted-mobile.png`: the product receipt summary on mobile.
- `deletion-preview.json`: exact confirmed scope and dependency token.
- `deletion-receipt.json`: actual deletion results and cleanup status.
- `preservation-verification.json`: synthetic source labeling, cancellation,
  deleted counts, source/workflow/Monte Carlo preservation and reload checks.

The IDs belong to an isolated test catalogue. They are evidence files, not live
links into the user's library. Earlier calculation screenshots/reports remain
unchanged in the parent folders. These are deletion observations, not fabricated
financial or future-performance outputs.

## Use it with your own saved simulation

1. Open Prop Sim and choose a run under **Saved simulations**.
2. Click **Delete simulation** in its result header, or the delete button beside
   the selector. For active jobs, stop/wait first.
3. Review its profile/strategy/date and exact removal/retention counts. Cancel
   leaves the run intact; confirm removes only that saved scope.
4. Expect the entry and unshared jobs/reports to disappear, with a success summary.
   Shared/protected reports and all source research remain accessible.
5. If filesystem cleanup could not finish, the durable success page provides
   **Retry file cleanup**. It retries only this deletion's staged directories;
   shared reports and source files are not part of cleanup.

## Focused lifecycle checks

```sh
.venv/bin/python -m pytest -q tests/test_prop_sim_deletion.py
```

These fast isolated metadata/file oracles remain in tests. They cover exact
scope and stale confirmation, shared results and the last-reference case,
active-job rejection, frozen phase retention, SQL rollback restoring parent /
campaigns/files, cleanup failure followed by retry, symbolic-link refusal,
Job history, and prevention of deleted-ID reuse. The normal browser demonstration
above supplies actual numerical publication/deletion evidence separately.

The implementation reuses the existing AnalysisStore deletion guards/catalogue
cleanup and CampaignStore transactional reference release. Report directories
are staged by rename, with SQL/file rollback on failure, then cleaned after
commit. The receipt supports idempotent deletion and retry after cleanup failure.
Metadata access and deletion run under the existing catalogue lock; a fresh
preview is required if dependencies change. Numerical code/identities are not
changed and deletion never reruns a calculation.

API: `GET /api/prop-sim/{id}/deletion` returns a read-only plan or receipt;
`DELETE /api/prop-sim/{id}` takes
`{"confirmation_sha256":"<token from the current plan>"}`. The response states
what was removed, retained and still needs file cleanup. Repeat the same DELETE
for safe retry; use a new request ID for a new simulation.
