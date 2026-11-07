# Canonical trade export v1

[Docs](../README.md) / [Architecture](../architecture.md)

Implementation update, 7 November 2026: standalone import now uses
`aq-trade-export-v1`, generalizing the earlier MultiCharts-specific proposal.
Open **Backtests → Import external trades**, check the JSON export and save an
ordinary report. Original bytes, trade IDs, costs, stops and risk observations
are retained without inventing price bars or a DatasetStore row. This does not
qualify an installed MultiCharts exporter. The
[existing supplemental XLSX contract](../architecture_reference.md#multicharts-to-alphaquest-contract)
remains supported unchanged.

The table below retains the original proposal's intent. Its proposed
`aq-multicharts-trades-v1` identifier was replaced by `aq-trade-export-v1`;
existing XLSX workbooks are not canonical v1 exports.

| Record | Required content |
| --- | --- |
| Manifest | `schema_version`, `export_id`, `exporter_build`, platform edition/build/bitness, strategy/config hashes, dataset/contract identity, currency, point value, tick size; timestamp, session, bar-label and roll/adjustment conventions. |
| Source | `source_backtest_id`, manifest/trade SHA-256 and export SHA-256. Never match by filename or summary similarity. Standalone ingestion needs a separate adapter. |
| Trade | Unique `trade_id`, `side`, positive integer `quantity`, UTC `entry_time_utc`/`exit_time_utc`, prices and fill assumptions. Entry ≤ exit; positions cannot overlap in this model. |
| Money | Decimal strings: `reference_gross_pnl`, `slippage_cost`, `total_commissions`, `gross_pnl`, `net_pnl`; currency and whole-trade quantity basis. Exact native conservation; declare external tolerances by field/version. |
| Risk/events | Measurement basis, units, nullable MAE/MFE, coverage, source and timestamps. Ordered events need UTC time, sequence, quantity and account-equity/cost basis to determine first breach. Distinguish bar bounds from tick measurements. |
| Completion | Expected trade/event counts, complete/partial status and hashes. Reject unknown versions, missing/duplicate IDs, changed inputs and incomplete exports; never truncate or invent rows. |

## Implemented encoding and envelope

The UTF-8 JSON object has exactly `schema_version`, `export_id`, `manifest`,
`payload` and `completion`. Version is `aq-trade-export-v1`; the exporter ID is
unique nonempty text. Identical bytes with the same ID reopen the saved report;
different bytes conflict. A database uniqueness constraint also protects
concurrent imports. `payload` has `trades` and `risk_events` arrays in supplied
order. `completion` has `status: complete`, exact integer `trade_count` and
`event_count`, and `payload_sha256`.

The payload digest is SHA-256 of UTF-8
`json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
allow_nan=False)`. Array order and decimal-string spelling are preserved.
Separate SHA-256/length values identify the **original bytes**, including
whitespace and the manifest. Duplicate JSON keys, unknown fields/versions,
floating-point JSON tokens, nonfinite values, partial exports and mismatched
counts/hashes reject before publication.

Money and prices are plain finite decimal strings, such as `"0.25"`, `"-10"`
and `"6.00"`. Exponents, leading plus signs/zeros and JSON numeric money reject.
Limits: 128 digits, 64 decimal places, 32 MiB input, 100,000 trades, 1,000,000
events. Exact financial validation uses an independent 512-digit Decimal context
with rounding traps. Quantities/counts are strict integers, never booleans.
UTC timestamps use `Z` or `+00:00`, at most microsecond precision.

## Manifest fields

All listed fields are required; nullable values are identified explicitly.

| Object | Fields |
| --- | --- |
| Root | `origin` (`alphaquest`, `multicharts_dotnet`, `external`), `exporter_build`, positive decimal `initial_capital`. |
| `platform` | `edition`, `build`, `bitness` (32, 64 or null). |
| `strategy` | `id`, JSON `parameters`, nonnull `implementation_sha256`; decimal parameters are strings. |
| `dataset` | `name`, nonnull `sha256`, `contract`, `adjustment`; retained as external provenance, not a local price dataset. |
| `instrument` | `symbol`, uppercase three-letter `currency`, positive decimal `tick_size`, `point_value`. |
| `time` | `timestamp_basis` (`actual_fill`, `bar_open`, `bar_close`, `unknown`), IANA `source_timezone`, `session_convention: cme_chicago_1700_v1`, nullable `bar_interval_seconds` (required positive integer for bar labels). |
| `coverage` | `start_utc`, `end_utc`, increasing ISO `sessions` including declared no-trade dates, `calendar_id`, `calendar_sha256`, `completion: exporter_declared_complete`; endpoints lie in first/last declared sessions. |
| `research` | `phase` (`is`, `oos`, `unspecified`), textual `declaration`, `prior_access` (`unknown`, `accessed`, `exporter_declared_unaccessed`). |
| `execution` | `position_model: nonoverlapping_constant_quantity_round_trips`, `sizing_path_invariance` (`unverified`, `exporter_declared`), `cost_basis: actual_per_trade`, textual `fill_assumption`, string-list `assumptions`. |
| `risk` | `basis` (`ordered_marks`, `measured_extrema`, `missing`, `unknown`), `coverage` (`complete`, `partial`, `missing`, `unknown`), `units: whole_trade_account_currency`, `equity_basis: actual_fill_pnl_less_commissions_charged`, `observation_claim` (`exporter_declared`, `missing`, `unknown`). |

Missing/unknown risk remain distinct and cannot contain invented observations.
Exporter completeness, hashes and research labels do not independently certify
data authenticity, tick completeness, calendar correctness or untouched history.

## Trades and causal sizing information

Each trade supplies `trade_id`, `side` (`long`/`short`), positive whole `quantity`,
entry/exit UTC timestamps, actual/reference entry/exit prices, entry/exit and
total commissions, reference gross/slippage/gross/net P&L, entry/exit reasons,
paired nullable entry/exit bar numbers, nullable `initial_stop`, list
`stop_updates`, nullable `sizing_decision` and nullable `excursions`. See
[`canonical_trades.py`](../../alphaquest/canonical_trades.py) and its rejection
tests for exact field spellings. The normal trade table adds its catalogue
ordinal and retains `external_trade_id`; it never manufactures native bar IDs.

For sign +1 long / −1 short, exact reconciliation is:

```text
reference_gross = (exit_reference − entry_reference) × sign × quantity × point_value
gross           = (exit_fill − entry_fill) × sign × quantity × point_value
slippage_cost   = reference_gross − gross
commissions     = entry_commission + exit_commission
net             = gross − commissions
```

Actual fills already incorporate slippage, including genuine price improvement.
No cost is deducted twice. IDs are unique, round trips do not overlap, and
quantity cannot change within a trade. Partial exits need another explicit
contract and reject here.

A stop is `{price, known_at_utc, basis}`, with basis `submitted_order` or
`strategy_decision`. A sizing decision is
`{timestamp_utc, reference_price, execution_timing}`; timing is `same_close`,
`next_open`, `observed_open` or `external_declared`. Initial stop information is
known by decision time, decision precedes or equals entry and follows settlement
of any prior position. Same-close decisions coincide with entry; next-open
decisions precede it. The stop is adverse to the decision reference. A later gap
through the stop remains an outcome; future fills cannot choose earlier sizes.
These declarations are preserved, not independently authenticated.

## Ordered marks and excursion consistency

Events contain `trade_id`, global increasing integer `sequence`, UTC timestamp,
`kind` (`open`, `mark`, `stop_update`, `close`), `current_quantity`, `mark_price`,
nullable `stop_price`, `cumulative_realized_gross`, `commissions_charged` and
`marked_trade_net_equity`. Opening and terminal events reconcile to fills and
fees. Intermediate events retain the full position with no partial realization.
Stop updates match the supplied stop records. Global trade ownership is ordered,
including a close before the next open at a shared timestamp.

```text
marked_trade_net_equity = realized_gross + unrealized_gross_at_actual_fills − charged_commissions
```

Excursions have basis `observed_marks_net_equity` or
`exporter_reported_net_equity`, nonnegative decimal `mae`/`mfe`, and nullable
`mae_time_utc`/`mfe_time_utc`. Observed extrema match events exactly. Reported
extrema must bound supplied observations; larger values are retained as missing
path information and block the current prop adapter. They never create events.

## Current product capabilities

Valid exports with missing risk can still be inspected. Prop admission is
stricter: identified USD NQ/MNQ, actual-fill timestamps, explicit research phase,
constant source quantity, exporter-declared path invariance, complete ordered
marks covering all reported extrema, intraday-flat trades and a complete declared
2–20,000-weekday inventory. Unsupported calendars reject rather than filling
missing dates with invented zero-trade observations.

The first adapter supports the existing **annualized EOD analysis**. It retains
successively larger observed losses as the existing engine's adverse frontier,
with every mark treated as a jump. A breach uses the first observed crossing
mark, not an inferred continuous stop fill. Source-cost mode retains actual fees;
commission replacement reprices one side while open and two at close, retaining
actual-fill slippage. Original/canonical exports and declared sessions are saved
inside the ordinary AnalysisStore download. Tick completeness, liquidation and
path invariance remain unverified model assumptions.

Imported sources do not authorize native detail/risk recapture, controlled OOS,
nested reruns or a fabricated benchmark. External independent phase selection,
dated replay and dynamic sizing remain pending integration; APIs reject them
explicitly. A standalone pure sizing contract does not establish engine support.

`project_native_source` provides the same canonical vocabulary for existing
native reports, preserving original trade/risk fields and hashes. Historical
initial stops, decision references and session inventories stay unavailable if
they were not retained. MAE never becomes a fabricated stop.

Implementation owners: `canonical_trades.py` validates; `trade_imports.py`
publishes through RunStore; `prop/external_source.py` checks model admission and
projects event costs; existing account engines retain all transitions. Ordinary
saved-report reads verify artifacts without reparsing or recalculating results.
See the [delivery record](../prop_simulation_review.md) and
[active checklist](../robust_research_plan.md).
