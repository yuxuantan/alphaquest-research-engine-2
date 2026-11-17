# Permanently delete one campaign dataset workflow

Implemented 2026-11-16. This replaces reversible **Remove dataset link**. The
campaign/strategy and original dataset files cannot be deleted by this feature.

## Use it

1. Open **Campaigns → select a campaign**. Each workflow card shows its creation
   date, short workflow ID and an expandable saved-version identifier. Two cards
   with the same dataset name can represent independent workflows on one upload.
2. On the intended card, choose **Delete workflow and results…**. Only that
   workflow ID is selected. Other workflows using the same dataset are preserved.
3. Review the exact workflow, batch, report and file lists. Downstream Prop Sim,
   Monte Carlo and portfolio analyses to be deleted are explicitly listed and
   linked. **Dependent research studies that will also be deleted** identifies
   each nested study by name, creation date, state, ID, saved checkpoint count
   and saved-report link. Evidence used by another owner is listed under
   **Shared evidence kept**.
   A downstream multi-strategy portfolio is deleted as a whole if included in the
   preview; its other source workflows and datasets remain intact.
4. Cancel to leave everything unchanged. To proceed, acknowledge irreversible
   deletion and choose **Permanently delete**. There is no Undo or Restore.
5. The selected workflow, its unshared evidence files and listed downstream
   results disappear from Campaigns, saved results and Job history. Reloading does
   not bring them back. The dataset remains available for a new backtest.

Legacy cards without a workflow instead offer **Delete saved results…**. That
selects their specific saved-results group, while preserving reports pinned by
existing workflows or other owners. It never implicitly selects every workflow
sharing a dataset name or content hash. Shared evidence can remain visible under
saved results after its original workflow is deleted.

Old reversible-removal markers no longer hide cards. Previously hidden workflows
become visible so they can be individually inspected or permanently deleted.
The old restore and source-wide delete contracts are retired.

## What is removed and retained

The preview covers mechanics attempts/reviews; Broad/Narrow/OOS batches and frozen
state; backtest, native cost-stress, detailed and controlled percentage-risk child
reports; workflow Monte Carlo; dependent Prop Sim/portfolio records; their unused
independent phase packages and unshared analysis files. Downloads in deleted
report directories are removed too. The current numerical version is not required
for deleting an old workflow: this is metadata/ownership cleanup, not a rerun.

As of 2026-11-17, downstream nested research studies (`robust_research`) are
included in the confirmed cascade instead of blocking it. Their declarations,
plans, checkpoints and common catalogue links are removed. Generated research
backtests and child phase/native analyses are included when unshared. A cached
copy used by another surviving owner remains available. Discovery follows actual
source, job, analysis and owned-result references; an incidental `prior_access`
inventory does not select an otherwise unrelated study for deletion. Other
strategy definitions and original input datasets are never selected as a result
of a multi-strategy study being included.

Other workflows using the same dataset remain linked and retain their own files.
Reports used by surviving workflows, batches, research campaigns, analyses or
monitors are preserved with their transitive source/stress evidence. Running or
queued work, active detail generation and unfinished automation block deletion.
Forward-monitor/procedure dependencies that retain a downstream package also
block it; the preview identifies the dependency instead of silently removing it.

Original datasets, strategy code, shared market/replay caches, unrelated research plans,
price/outcome access history and manual OOS execution counts are retained. Deletion
never makes previously accessed OOS data untouched. Minimal receipts/tombstones
retain IDs, membership/counts, file names and cleanup state; they do not retain
trade tables, metric outputs, declarations or frozen phase packages as another
result store. Deleted study/phase/simulation IDs cannot be reused. This is application
file deletion, not forensic erasure of backups or disk blocks.

## API and recovery

`POST /api/campaign-dataset-links/preview` requires:

```json
{
  "strategy_id": "vwap_pullback_risk_sizing",
  "source": {
    "sha256": "<64 lowercase hex characters>",
    "source_timezone": "America/New_York",
    "source_kind": "native"
  },
  "workflow_id": "<32 lowercase hex characters>"
}
```

Use `group_id` (64 hex characters) instead of `workflow_id` for a legacy
saved-results group. Exactly one target is required; source-only, campaign-only
and mixed-scope requests reject. `DELETE /api/campaign-dataset-links` requires
that same body plus the preview's `confirmation_sha256`. Changed membership,
files, dependencies or state require a fresh preview. Repeating a successful
DELETE with its exact target/token retries cleanup safely without deleting new
workflows created later.

The preview includes `research_study_ids` and named `research_studies`, in
addition to its report/file and retained-evidence lists. No extra deletion
endpoint or separate confirmation is required: the existing confirmation covers
the complete visible cascade. The token also binds included study declarations,
plans, checkpoint contents and dependency membership. A changed checkpoint,
even with the same count, requires a fresh preview. Active study calculations
block deletion; surviving forward-monitor and frozen-procedure dependencies
remain protected. Research-access intervals and OOS-access attempts survive
removal so deleting a study cannot erase prior access.

The existing backtest and AnalysisStore catalogues participate in a single SQLite
ATTACH transaction with rollback journals. WAL/in-memory journal modes reject
before files are moved. A durable prepare record precedes renaming owned report
folders into private staging. SQL/filesystem failure rolls back catalogue changes
and restores moved folders. Startup restores pre-commit staging; committed cleanup
is retried after a crash or through **Retry file cleanup**. Symbolic-link report
folders reject. Only canonical report UUIDs below the owned report roots can be
removed; manifest-provided source paths are never deletion targets.

## Verification

Run only the affected checks:

```sh
.venv/bin/python -m pytest -q tests/test_campaign_dataset_links.py tests/test_prop_sim_deletion.py
ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/python -m pytest -q tests/test_campaign_dataset_links_browser.py
```

The native mechanics and Broad reports are real backtest outputs over explicitly
synthetic input prices. Downstream graph fixtures are labelled metadata-only and
make no prop numerical or qualification claim. Tests cover two same-dataset
workflows, shared report/analysis ownership, OOS access retention, real Broad-grid
cleanup, controlled-child ownership, stale previews, cancellation, blockers,
transaction rollback, crash recovery, cleanup retry and mobile/reload persistence.
Temporary browser servers stop in fixture teardown. Evidence and reproduction:
`artifacts/workflow-deletion-20261116/README.md`.

The 2026-11-17 increment additionally exercises a real completed nested-research
calculation through the normal API and deletes it via its legacy results group,
checking preserved research-access intervals and rejected ID reuse. Metadata-only
graphs over real mechanics reports exercise shared owners, checkpoint/plan races,
running jobs and rollback; these fixtures make no numerical research claims.
The focused browser path is
`tests/test_campaign_dataset_links_browser.py::test_dependent_nested_study_preview_cancel_confirm_and_reload`.
Current screenshots and an inspection-only preview of the previously blocked
user study are in `artifacts/dependent-research-deletion-20261117/`. No user
workflow, study or evidence was deleted during installation.
