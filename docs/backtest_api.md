# Backtest API review

The existing FastAPI server exposes the tested reader, allowlisted strategy,
engine, and reporter. The Backtests configuration and completed report screens
use these APIs. Start the server with:

```bash
.venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8000
```

## Endpoints

| Method and path | Response |
| --- | --- |
| `GET /api/strategies` | Allowlisted IDs, descriptions, source hashes, and strategy-owned parameter definitions/defaults/minima. |
| `POST /api/backtests?progress_id=UUID` | Runs the selected strategy; returns HTTP 201 with the durable completed record after replay, reporting, and saving. |
| `GET /api/progress/UUID` | Current stage, `bars_processed`, `total_bars`, and `run_id`; failures also include `error`. |
| `GET /api/backtests?offset=0&limit=100` | Page of completed records, including summaries and resolved provenance/settings. |
| `GET /api/backtests/RUN_ID` | One completed record, including summary/provenance; no unbounded result arrays. |
| `GET /api/backtests/RUN_ID/trades?offset=0&limit=100` | Page of full, exact trade records. |
| `GET /api/backtests/RUN_ID/equity?offset=0&limit=100` | Starting equity and equity after each completed trade, matching `equity.csv`. |
| `GET /api/backtests/RUN_ID/chart?max_points=1000` | Bounded preview of initial equity and equity after completed trades. |
| `GET /api/backtests/RUN_ID/exports/trades` | Saved trade CSV, streamed as a download. |
| `GET /api/backtests/RUN_ID/exports/equity` | Saved trade-close equity CSV, streamed as a download. |

Every page has `items`, `offset`, `limit`, and `total`. Limits range from 1 to
1,000; default 100. Indexed ordinal lookups avoid loading the complete report
JSON. Equity includes trade number, exit timestamp, net trade P&L, and equity
after costs. The starting point has trade number 0, null exit timestamp, and
zero P&L. The report file retains full bar-close equity for reconciliation.

The chart response has `items`, `total`, `limit`, `sampled`, `method`, `currency`,
and `meaning`, plus `peak` containing the exact peak equity point from the full
CSV (the first occurrence when tied). `max_points` is 16–2,000 (default 1,000); small runs retain every
point. Large runs retain initial/final equity and chronological minimum/maximum
points per trade-count bucket, using Decimal comparisons. Points have
`trade_number`, `exit_time_utc`, `net_pnl`, and `equity`, matching the equity
endpoint and `equity.csv`. The initial point has trade number 0 and a null exit
time. No open-position equity points are shown, and no metrics are calculated
from the preview. The worker streams the existing `equity.csv`, using memory
bounded by the preview cap and one record. No source dataset connection is held,
no migration or replay is needed for older saved runs, and the full report is
not sent to the browser. Each chart request scans the equity CSV once; this can
take time for very large files.
Chart read errors return an error rather than partial data. Values use CU
(account currency unspecified); the current execution contract stores no
currency code. Download names include the run ID, and only the two allowlisted
CSV exports are exposed.

## Dataset instrument settings

Save positive finite decimal strings with each dataset before running a backtest:

```bash
AQ_API=http://127.0.0.1:8000
AQ_DATASET_ID=YOUR_SAVED_DATASET_ID
curl -fsS -X PATCH "$AQ_API/api/datasets/$AQ_DATASET_ID/instrument-settings" \
  -H 'Content-Type: application/json' \
  -d '{"tick_size":"0.25","point_value":"10"}'
```

The response is the updated dataset metadata. The original CSV, hash, timezone,
validation metadata and dataset ID are preserved. Both fields are required;
unknown fields, floats, zero, negative and non-finite values return 422. A missing
dataset returns 404. Uploads may optionally provide both `tick_size` and
`point_value` as query parameters on `POST /api/datasets`.

Existing datasets without instrument settings remain readable and editable, but
new backtests return 422 until these settings are saved. No values are inferred.
The run request requires capital, slippage and commissions in
`execution_settings`. Optional `tick_size` and `point_value` decimal strings
override either dataset default for this run only; omitted or null fields use
that saved default. Overrides must be positive and finite; numeric JSON values,
booleans, invalid strings, zero and negative values return 422. Run overrides
never update dataset metadata.

The server captures the selected dataset's defaults at run start and stores them
in `run_metadata.dataset.instrument_settings`. `execution_settings` records the
full resolved configuration. `run_metadata.instrument_overrides` records only
values that differ numerically from the captured defaults; equal decimal
spellings are not overrides. Empty `{}` means the run used dataset defaults.
The completed report displays the defaults and overrides, including after a
refresh or server restart. Older reports without this provenance show it as not
recorded. Editing a dataset during replay or afterward does not change that run
or earlier reports.

## Request and validation

Optional top-level `from_date` and `to_date` fields restrict the replay:

```json
{"from_date": "2026-01-05", "to_date": "2026-01-31"}
```

Add these to the existing dataset/strategy/settings request. They are inclusive
calendar dates in the dataset's saved source timezone. Omit either for an open
bound or both for the full dataset. Invalid/reversed bounds or an empty selection
return 422; failed selections never become completed reports. Values outside
the available data are clipped by selecting only matching observed bars.

The strategy starts fresh with no history from outside the range, and its
end-of-data callback runs at the last included bar. The saved record includes
`run_metadata.selection` with the requested dates, timezone, actual UTC range,
selected count and original source row bounds. Original dataset metadata is
unchanged. Preparation uses `total_bars=0` until the exact count is known;
replay/done progress and reconciliation use the selected count.

Completed summaries include `max_drawdown_amount`, `max_drawdown_pct`, and
`max_drawdown_duration_seconds`, as decimal strings. All use full trade-close
equity after costs. Duration is elapsed UTC time from a peak to recovery or
dataset end if unrecovered; an initial-capital peak starts at the first bar.
New report artifacts also record `period_start_utc` and `period_end_utc`.
For older runs, the server streams the saved report to recover its period and
the complete equity CSV to calculate metrics once, then caches them durably in
the completed-run catalogue. Replay, datasets, and original JSON/CSV artifacts
are unchanged. The first retrieval of an older large run can take longer;
subsequent requests and restarts use the enriched catalogue. Newly generated
`report.json` artifacts include the metrics directly. See the contract's
drawdown definitions for recovery, percentage and duration conventions.

```json
{
  "dataset_id": "SAVED_DATASET_ID",
  "strategy_id": "consecutive_green_hold",
  "strategy_parameters": {"green_bar_count": 3, "hold_minutes": 20, "contracts": 2},
  "execution_settings": {
    "initial_capital": "10000",
    "slippage_ticks": 1, "commission_per_contract_per_side": "1"
  }
}
```

These settings describe the synthetic arithmetic fixture, not NQ or another
instrument. All strategy parameters and per-run capital/cost settings must be explicit. Tick size and monetary point value default to the saved dataset values, with optional validated per-run overrides.
Decimal settings must be JSON **strings**, preserving precision. Integer
parameters/ticks reject booleans, fractions, and string coercion. Missing/unknown
settings, unsupported IDs, invalid values, and unsupported saved schemas are
rejected. Strategy constructors perform parameter validation; the registry
contains no green-bar/holding rules. Clients cannot supply Python source,
import paths, filesystem paths, or a timezone override.

Results record dataset ID/hash/saved source timezone, strategy ID/source hash,
resolved strategy parameters, execution settings, `timestamp_convention="bar_close"`,
and the same-close full-fill assumption.

## Reproducible fixture commands

From the repository root, with the server running, save the fixture. Extraction
also accepts the existing ID if the CSV/timezone was already uploaded:

```bash
AQ_API=http://127.0.0.1:8000
AQ_DATASET_ID=$(curl -sS -X POST \
  "$AQ_API/api/datasets?filename=arithmetic_5m.csv&name=API-arithmetic-review&source_timezone=UTC&tick_size=0.25&point_value=10" \
  --data-binary @tests/fixtures/backtest_contract/arithmetic_5m.csv \
  | .venv/bin/python -c 'import json,sys; r=json.load(sys.stdin); print(r.get("id") or r["dataset_id"])')
curl -fsS -X PATCH "$AQ_API/api/datasets/$AQ_DATASET_ID/instrument-settings" \
  -H 'Content-Type: application/json' \
  -d '{"tick_size":"0.25","point_value":"10"}' > /dev/null
AQ_PROGRESS_ID=$(.venv/bin/python -c 'from uuid import uuid4; print(uuid4())')

cat > /tmp/aq-backtest-request.json <<JSON
{
  "dataset_id": "$AQ_DATASET_ID",
  "strategy_id": "consecutive_green_hold",
  "strategy_parameters": {"green_bar_count": 3, "hold_minutes": 20, "contracts": 2},
  "execution_settings": {
    "initial_capital": "10000",
    "slippage_ticks": 1, "commission_per_contract_per_side": "1"
  }
}
JSON

curl -sS -X POST "$AQ_API/api/backtests?progress_id=$AQ_PROGRESS_ID" \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/aq-backtest-request.json > /tmp/aq-backtest-result.json &
AQ_POST_PID=$!

curl -sS "$AQ_API/api/progress/$AQ_PROGRESS_ID"
wait "$AQ_POST_PID"
cat /tmp/aq-backtest-result.json

AQ_RUN_ID=$(.venv/bin/python -c 'import json; print(json.load(open("/tmp/aq-backtest-result.json"))["id"])')
curl -sS "$AQ_API/api/backtests/$AQ_RUN_ID"
curl -sS "$AQ_API/api/backtests/$AQ_RUN_ID/trades?offset=0&limit=10"
curl -sS "$AQ_API/api/backtests/$AQ_RUN_ID/equity?offset=0&limit=10"
```

The first poll can return 404 if it arrives before the POST starts tracking;
repeat the poll. This tiny fixture may complete before the first successful
poll. Expected: one trade, gross P&L 30, commissions 4, net P&L 26, final equity
10026. Equity contains starting equity 10000 and the trade-close point at
`2026-01-05T10:30:00Z`, equity 10026.

## Progress, storage, and failures

The POST remains open, using the existing request-and-poll pattern. Preparation,
replay, report assembly, and persistence run in a worker thread. Stages are
`preparing`, `replaying`, `saving_report`, `saving_results`, then `done` or `failed`.
Bars processed means completed ordinary callbacks/fills; reaching total bars
does not mean results are saved. `done` and HTTP 201 require persistence.

The optional progress UUID uses the existing 128-snapshot in-memory tracker.
Snapshots reset on restart; reused tracked IDs return HTTP 409. Responses and
progress carry a separate run ID. Completed records survive restart and source
dataset deletion. Validation errors return 422 (missing dataset: 404). Replay
or save failures never enter the completed catalogue. Requests are not retried
or resumed automatically.

`backtests.sqlite3` beside the dataset database contains completed manifests and
indexed trade/equity JSON rows. Financial values remain decimal strings. Report
artifacts stream under `backtest_runs/RUN_ID/`. SQLite publishes the record only
after every row and report file is saved. Normal failures roll back rows and
clean staging files. A hard interruption can leave an unlisted staging/artifact
directory; retrieval/listing require a committed record and cannot treat it as
success. No external task queue or background-job framework is introduced.
