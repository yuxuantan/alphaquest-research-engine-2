# Backtest API review

The existing FastAPI server exposes the tested reader, allowlisted strategy,
engine, and reporter. The Backtests screen uses these APIs; a full report screen
remains a separate subtask. Start the server with:

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

Every page has `items`, `offset`, `limit`, and `total`. Limits range from 1 to
1,000; default 100. Indexed ordinal lookups avoid loading the complete report
JSON. Equity includes trade number, exit timestamp, net trade P&L, and equity
after costs. The starting point has trade number 0, null exit timestamp, and
zero P&L. The report file retains full bar-close equity for reconciliation.

## Request and validation

```json
{
  "dataset_id": "SAVED_DATASET_ID",
  "strategy_id": "consecutive_green_hold",
  "strategy_parameters": {"green_bar_count": 3, "hold_minutes": 20, "contracts": 2},
  "execution_settings": {
    "initial_capital": "10000", "tick_size": "0.25", "point_value": "10",
    "slippage_ticks": 1, "commission_per_contract_per_side": "1"
  }
}
```

These settings describe the synthetic arithmetic fixture, not NQ or another
instrument. All strategy parameters and execution settings must be explicit.
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
  "$AQ_API/api/datasets?filename=arithmetic_5m.csv&name=API-arithmetic-review&source_timezone=UTC" \
  --data-binary @tests/fixtures/backtest_contract/arithmetic_5m.csv \
  | .venv/bin/python -c 'import json,sys; r=json.load(sys.stdin); print(r.get("id") or r["dataset_id"])')
AQ_PROGRESS_ID=$(.venv/bin/python -c 'from uuid import uuid4; print(uuid4())')

cat > /tmp/aq-backtest-request.json <<JSON
{
  "dataset_id": "$AQ_DATASET_ID",
  "strategy_id": "consecutive_green_hold",
  "strategy_parameters": {"green_bar_count": 3, "hold_minutes": 20, "contracts": 2},
  "execution_settings": {
    "initial_capital": "10000", "tick_size": "0.25", "point_value": "10",
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
