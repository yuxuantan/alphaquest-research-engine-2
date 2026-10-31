# Trade export v1 — proposal

[Docs](../README.md) / [Architecture](../architecture.md)

This design is not implemented or scheduled here. The
[current XLSX contract](../architecture_reference.md#multicharts-to-alphaquest-contract)
remains the supported interface.

`aq-multicharts-trades-v1` is **proposed, not implemented**. Add it through the
existing source check if needed; current XLSX files are not v1.

| Record | Required content |
| --- | --- |
| Manifest | `schema_version`, `export_id`, `exporter_build`, platform edition/build/bitness, strategy/config hashes, dataset/contract identity, currency, point value, tick size; timestamp, session, bar-label and roll/adjustment conventions. |
| Source | `source_backtest_id`, manifest/trade SHA-256 and export SHA-256. Never match by filename or summary similarity. Standalone ingestion needs a separate adapter. |
| Trade | Unique `trade_id`, `side`, positive integer `quantity`, UTC `entry_time_utc`/`exit_time_utc`, prices and fill assumptions. Entry ≤ exit; positions cannot overlap in this model. |
| Money | Decimal strings: `reference_gross_pnl`, `slippage_cost`, `total_commissions`, `gross_pnl`, `net_pnl`; currency and whole-trade quantity basis. Exact native conservation; declare external tolerances by field/version. |
| Risk/events | Measurement basis, units, nullable MAE/MFE, coverage, source and timestamps. Ordered events need UTC time, sequence, quantity and account-equity/cost basis to determine first breach. Distinguish bar bounds from tick measurements. |
| Completion | Expected trade/event counts, complete/partial status and hashes. Reject unknown versions, missing/duplicate IDs, changed inputs and incomplete exports; never truncate or invent rows. |
