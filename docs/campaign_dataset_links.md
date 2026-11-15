# Remove campaign–dataset links

On **Campaigns → select a campaign**, each dataset card has **Remove dataset
link**. Confirming removes the dataset from that campaign's main-page list.
Entire campaigns cannot be deleted through this feature.

The confirmation identifies the dataset and how many saved workflows use that
link. It explicitly retains the campaign/strategy code, dataset files, phase
progress, backtests, reports and Job history. Running jobs continue; removal
neither cancels them nor invalidates their saved evidence or Prop Sim references.
Saved results remain inspectable through Job history and Saved runs.

Use **Undo** immediately afterward, or expand **Removed datasets** and choose
**Restore link** later. Removal survives reloads and application restarts. Explicitly
creating a new backtest workflow with the same source relinks it; merely viewing
results or completing a background job does not. Restore does not rerun a backtest.

A link identifies a campaign plus source content SHA256, source timezone and
native/external source kind. All workflow variants for that logical source are
removed together, including the saved-run fallback cards. The same source in
another campaign stays linked. This also prevents old reports or reuploaded
aliases from silently making a removed source reappear.

## Implementation and checks

`alphaquest/campaign_dataset_links.py` stores only reversible navigation state in
`campaign_dataset_removals`, in the existing backtest SQLite catalogue. It never
removes workflow rows, source files, calculation records or frozen packages.

- `GET /api/campaign-dataset-links?strategy_id=…` lists removed links.
- `POST /api/campaign-dataset-links/preview` validates a linked source and returns
  a confirmation hash and retained workflow/report counts.
- `DELETE /api/campaign-dataset-links` requires the exact campaign/source plus
  that confirmation hash. A changed workflow scope rejects a stale confirmation.
  Repeated removal is idempotent. A campaign-only request is invalid.
- `POST /api/campaign-dataset-links/{strategy_id}/{source_key}/restore` restores
  that one association. There is no whole-campaign deletion route here.

Focused verification: four API/storage checks, the existing mechanics lifecycle
regression, two real browser journeys and the existing main-navigation journey
(eight checks). Temporary browser servers stop in fixture teardown. Run:

```sh
.venv/bin/python -m pytest -q tests/test_campaign_dataset_links.py
ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/python -m pytest -q tests/test_campaign_dataset_links_browser.py
```

Saved synthetic product evidence is under
`artifacts/campaign-dataset-links-20261115/`: screenshots and retention hashes in
`workflow-link/`, legacy-list persistence/relink evidence in `legacy-link/`, and
the idle-only portal application record. Reproduce by opening a synthetic
campaign dataset, cancelling removal once, confirming it, using Undo, removing
again, reloading, and restoring through Removed datasets. The campaign remains
listed and the original dataset, workflow, report and file hashes stay unchanged.

The user validation job `6ac1127dcf03420687757192e2dbbbcf` was allowed to finish
before application. The port-8000 portal restarted with no interrupted jobs;
all nine completed-job file hashes stayed unchanged. Persistent server PID:
`79681`; stop with `kill 79681`.
