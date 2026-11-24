# Individual workflow permanent deletion — 2026-11-16

The recovered November 15 implementation was narrowed from a campaign/source
family to exactly one workflow ID (or one explicit legacy saved-results group).
All deletion demonstrations here use temporary, labelled synthetic sources.
Native mechanics/Broad outputs are actual local backtests. The downstream graph
is labelled metadata-only; it makes no prop numerical or qualification claim.

`browser/permanent-workflow/` shows preview, cancel, acknowledgement, deletion,
reload and mobile rendering with a second workflow on the identical upload kept.
Every saved file of that other workflow retains its hash.
`browser/legacy-and-busy/` shows legacy results and a visible running-job blocker.
`browser/downstream-cascade/` shows the listed downstream simulations before
confirmation and verifies their unshared files are removed.

`verification.json` records the focused checks. They cover shared report/analysis
owners, the other workflow's Prop Sim, native percentage/OOS child reports, real
Broad-grid removal, stale preview/scope rejection, rollback across both catalogues,
crash recovery, cleanup retry, symbolic links, UUID serialization, WAL refusal,
ID tombstones and retained OOS access history. No production user data is deleted.

Reproduce from the repository root:

```sh
.venv/bin/python -m pytest -q tests/test_campaign_dataset_links.py tests/test_prop_sim_deletion.py
ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/python -m pytest -q \
  tests/test_campaign_dataset_links_browser.py \
  tests/test_workflow_navigation_browser.py::test_main_navigation_and_campaign_details
```

To retain browser evidence, set `ALPHAQUEST_LINK_EVIDENCE_DIR` to a new local
directory. Temporary portal servers stop in fixture teardown. The installed portal
uses the normal Campaigns page and original storage/worker owners, with no demo
endpoint or duplicate result store. Read `docs/campaign_dataset_links.md` for the
user journey, API contract and precise retention/deletion boundaries.
