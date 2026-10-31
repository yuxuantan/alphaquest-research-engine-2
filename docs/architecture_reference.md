# Storage and trade export reference

[Home](../README.md) / [Docs](README.md) / [Architecture](architecture.md)

Current formats and limits. [Research checks](research_workflow.md#campaign-checks),
[planning costs](planning.md) and the [future export proposal](designs/trade_export_v1.md)
are separate from the implemented contract below.

## Storage and recovery

One data root: `data/` by default, changed with `ALPHAQUEST_DATA_DIR`.
[app.py](../alphaquest/app.py) connects the stores.

| Location, relative to data root | Contents |
| --- | --- |
| `datasets.sqlite3` | CSV bytes, hash, timezone and instrument defaults; runs capture their own settings. |
| `backtests.sqlite3`; `backtest_runs/<run-id>/` | Backtests, splits, OOS history, batches and saved result files. |
| `prop_analyses/catalog.sqlite3`; `prop_analyses/<analysis-id>/` | Jobs and reports, captured inputs/settings, downloads and integrity checks; one source backtest per analysis. |
| Existing cache folders/reuse records | Derived results keyed by source, settings and engine; not independent evidence. |

Completed reports publish from staging and reopen from saved files. On restart,
unfinished prop jobs become errors; interrupted batches keep saved trials and
need explicit resume. OOS requests resolve to completed reports or interrupted
status. Back up databases **and report folders** with no jobs writing;
test restore consistency. No restore pass is recorded.

## MultiCharts to AlphaQuest contract

[source.py](../alphaquest/prop/source.py) supplements a **completed AlphaQuest
backtest**, not a standalone MultiCharts backtest. XLSX/XLSM entry rows in
`List of Trades` must match:

| Column | Rule |
| --- | --- |
| `Trade #` | Unique ID, one per native `trade_number`. Exit rows without an ID are skipped. |
| `Type` | `EntryLong`/`EntryShort`, matching native side. |
| `Date` | Naive Excel/ISO entry time plus selected timezone → native UTC instant. API choices: Chicago, New York, UTC. |
| `Contracts` | Exact native quantity; positive and constant across source trades. |
| `Profit ($)` | Finite net P&L; difference from native net at most **USD 0.00000001** per trade. |
| `Drawdown ($)`, `Run-up ($)` | Optional finite measured adverse/favorable movement (MAE/MFE). Missing stays missing. |

Limits: **32 MiB** file, **64 MiB** expanded, **100,000 trades**. Excel serial
timestamps allow at most **1 ms** rounding noise to whole seconds; other entry
instants match exactly. Native Decimal costs and summary totals must match
exactly. Hashes detect changes during export checking. Invalid settings,
identity/cost mismatches or malformed declared risk files reject checking.

The adapter does **not** verify exported exit times/prices, build, contract
identity or event order; native exit times remain. DST ambiguity/nonexistent
local times are not qualified: use unambiguous UTC exports until tested.
MAE/MFE alone cannot establish which account limit was crossed first.

The [v1 exchange format](designs/trade_export_v1.md) is a proposal; no parser or
new endpoint is implemented for it.

## Cost conservation and worked boundaries

`reference_gross_pnl - slippage_cost - total_commissions = net_pnl`

`gross_pnl - total_commissions = net_pnl`

Native net already includes costs. To replace commission: restore source
commission once, normalize quantity once, deduct target commission once.
[commissions.py](../alphaquest/prop/commissions.py) retains source values and
saves separate simulation values and cost checks.

**Synthetic example:** two NQ contracts: USD 50 gross before costs − 10 slippage −
4 commission = 36 net. With a USD 0.50/side MNQ override, one MNQ nets
`(36 + 4) / 2 / 10 - 2 × 0.50 = USD 1.00`. Source net stays 36.
This is an example override, not a broker price or future outcome.

Export net `36.00000001` passes; `36.00000002` rejects. Quantity 3 instead of 2,
a duplicate ID or entry one second late rejects. Native bar bounds are not
measured tick MAE/MFE; close-only fallback can understate risk. Never invent
missing measurements.
