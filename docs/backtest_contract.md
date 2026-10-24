# Backtest contract — v1 proposal for review

This document and the fixtures define the behavior for the first backtester. The fixtures are independent review expectations, not generated execution results. The dataset reader, minimal strategy interface, strategy-agnostic execution engine, consecutive-green-bars sample strategy, report generation, APIs, portal run controls, and completed report screen now implement their respective portions.

## 1. Dataset and clock

New backtests use the existing dataset contract:

```csv
Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol
```

The existing implementation is `alphaquest/datasets.py`. Dates use `MM/DD/YYYY`, times use 24-hour `HH:MM`, and all nine fields are required. Use the selected dataset's **saved source timezone**; do not replace it with the workstation timezone or silently override it at run time. Convert Date + Time to timezone-aware UTC timestamps. Preserve original CSV values and bytes. The dataset validator already rejects invalid numbers, inconsistent OHLC, negative volumes, duplicate/out-of-order UTC timestamps, and ambiguous/nonexistent local times at daylight-saving changes. The backtest must not reinterpret rejected local times.

**Assumption for this version: every timestamp labels the close of its bar.** This is a proposed convention, not something the CSV validator establishes. Record `timestamp_convention = "bar_close"` with every run and expose it with the eventual configuration/report. Do not infer it from the filename or observed spacing. Open-labelled data requires a separately reviewed conversion before using this convention.

A strategy sees one completed bar at a time, in UTC order. It cannot inspect future rows. `Volume`, `UpVol`, and `DownVol` remain available but are unused by this sample strategy. Do not assume UpVol + DownVol equals Volume.

Gaps remain gaps: no sorting, resampling, interpolated prices, fabricated bars, inferred trading calendar, or implicit session boundary. Consecutive bars means adjacent **observed** records, even across a gap. Holding time is elapsed UTC time, including gaps and market closures.

## 2. Strategy parameters and execution settings

The sample strategy has exactly three tunable parameters:

| Name | Meaning | Default | Valid values |
| --- | --- | ---: | --- |
| `green_bar_count` | Required consecutive green bars while flat | 3 | Integer >= 1 |
| `hold_minutes` | Target elapsed holding time | 20 | Integer >= 1 |
| `contracts` | Number of contracts to buy | 1 | Integer >= 1 |

Reject booleans, fractions, zero, or negative values for these integer parameters; do not silently coerce them.

Separate execution settings:

| Name | Meaning | Valid values |
| --- | --- | --- |
| `initial_capital` | Starting cash/equity | Finite decimal > 0 |
| `tick_size` | Price movement represented by one slippage tick | Finite decimal > 0 |
| `point_value` | Currency units per full price point per contract | Finite decimal > 0 |
| `slippage_ticks` | Adverse slippage on **each** entry and exit fill | Integer >= 0 |
| `commission_per_contract_per_side` | Commission for one contract on one fill | Finite decimal >= 0 |

Contracts is a quantity, not the monetary point value. Instrument settings must be supplied explicitly; a dataset symbol or filename is not a source of instrument specifications. All fixtures use a synthetic instrument, initial capital 10,000 currency units (CU), tick size 0.25, and point value 10 CU. These values are not specifications of NQ, ES, or another real product.

Represent decimal inputs and financial outputs as exact decimal strings in machine-readable artifacts. Calculate using decimal arithmetic, with no binary floating-point P&L or intermediate display rounding. Compare expectations by decimal value: `2.50` and `2.5` are equivalent; insignificant trailing zeros are not a financial difference. The fixture values terminate exactly. Percentage displays may round to two decimal places; the winning/losing/breakeven counts remain authoritative.

## 3. Entry, exit, and callback order

At the beginning of a run, position and consecutive-green count are zero. Each ordinary bar callback uses this order:

1. **If holding:** ignore all entry signals and do not accumulate green bars. If the bar's UTC close time is at or after `entry_time + hold_minutes`, request a full close with reason `hold_elapsed`, reset the counter, and return. Otherwise keep holding. A red bar or doji does not close an existing position.
2. **If flat:** `Close > Open` increments the counter; `Close <= Open` resets it to zero. When the count reaches `green_bar_count`, request one long entry for `contracts`, with reason `consecutive_green`, and reset the counter.
3. Execute the returned intent using that completed bar's Close as its reference price, plus adverse slippage. Do not execute an additional entry on an exit bar. The next observed bar is the first eligible bar of a new streak.

This means an uninterrupted green run does not pyramid, and bars observed while holding cannot be reused to trigger the next entry. All decisions above, including position checks, counter resets, quantity, and the holding deadline, belong in **one strategy script**. Dataset access, intent execution, commissions, P&L, and report arithmetic belong outside that script. A small reusable interface may expose current position/entry time and accept an entry or full-close intent; a plugin framework is unnecessary.

**Same-close execution is an explicit simulation assumption.** The completed Close is used both to classify the bar and as the entry/exit reference price. This model does not establish that an order observing that close could actually obtain it. Do not silently switch to a next-bar fill or describe this as an exact market-execution reconstruction. Fills are full quantity; this version does not model partial fills, liquidity, limit/stop orders, or intrabar price paths.

The hold is timed from the actual entry fill timestamp, which equals the entry bar's close timestamp in this model. If no bar exists at the deadline, keep holding until the first observed bar close at/after the deadline. Use that bar's Close; do not borrow a future price and backdate the fill. Report the actual holding time and deadline.

### End of data

After the final ordinary bar callback and any resulting fill, invoke the strategy's `on_finish` callback with the last observed bar and current position. The sample strategy requests a full close if still holding, using that last bar's Close and reason `end_of_data`. This exit decision lives in the strategy script, not a hidden engine liquidation rule. For this first reporting contract, a successful completed run finishes flat; a strategy that leaves an open position after `on_finish` must produce an explicit unsupported-completion error rather than silently omit it from P&L.

If the final ordinary bar already meets the holding deadline, the ordinary exit reason is `hold_elapsed`; `on_finish` does nothing. If a new entry occurs on the final bar, it is followed by an end-of-data exit at the same timestamp, charged slippage and commissions on **both** fills. It is a completed, zero-duration trade and must remain visible. This boundary case is deliberately included for review.

## 4. Fills, costs, and P&L

For quantity `q`, point value `v`, tick size `t`, slippage ticks `s`, commission per contract per side `c`, entry reference Close `E`, and exit reference Close `X`:

```text
entry_fill_price   = E + s * t
exit_fill_price    = X - s * t
reference_gross_pnl = (X - E) * q * v        # informational, before slippage
gross_pnl          = (exit_fill_price - entry_fill_price) * q * v
entry_commission   = q * c
exit_commission    = q * c
total_commissions  = entry_commission + exit_commission
slippage_cost      = reference_gross_pnl - gross_pnl  # informational
net_pnl            = gross_pnl - total_commissions
```

`gross_pnl` already includes the adverse slippage embedded in fill prices. **Do not subtract `slippage_cost` again.** Both normal and end-of-data exits use the same execution/cost formulas. Reference prices are the exact observed closes; this version applies no additional price rounding beyond the specified slippage arithmetic.

The account uses contract price-change P&L. Buying does not debit the contract's full notional value. This contract adds no margin, interest, funding, or collateral simulation, and it does not introduce capital-based sizing or reject entries based on an invented margin rule.

### Required arithmetic example

```text
E = 100; X = 102; q = 2; v = 10; t = 0.25; s = 1; c = 1
entry fill = 100.25; exit fill = 101.75
reference gross = 2 * 2 * 10 = 40
gross = 1.50 * 2 * 10 = 30
slippage cost = 40 - 30 = 10, already included in gross
commissions = 2 * 1 + 2 * 1 = 4
net = 30 - 4 = 26
```

## 5. Cash and equity

Start with cash and equity equal to initial capital. On entry, subtract entry commission from cash. While holding, mark unrealized P&L at each observed Close using the entry **fill**, not the entry reference price:

```text
cash_balance       = initial_capital + realized price-change P&L - all commissions paid
realized_net_pnl   = cash_balance - initial_capital
unrealized_pnl     = (current_close - entry_fill_price) * q * point_value  # zero if flat
equity             = cash_balance + unrealized_pnl
```

On exit, add gross price-change P&L and subtract exit commission from cash, then set unrealized P&L and position quantity to zero. Entry commission on an open position is already a realized expense. Open-position losses must appear in equity before the trade closes.

The curve contains an initial point (`bar_number = 0`, `timestamp_utc = null`) followed by one point per observed bar, after that bar's decisions/fills. The final bar's point also includes any `on_finish` fill; update that point rather than append a second point for the same bar. This preserves the initial balance without inventing an earlier market timestamp.

For the arithmetic fixture: entry cash is 9,998 and unrealized P&L is -5, so entry equity is **9,993**. At a later Close of 100.50, equity is **10,003**. Final equity is **10,026**.

## 6. Trade and run output

Each completed trade has these fields. `bar_number` is 1-based in data-record order, excluding the header; it is not a wall-clock interval or necessarily a physical CSV line number.

| Field | Definition |
| --- | --- |
| `trade_number` | Deterministic 1-based order within the run |
| `side` | `long` in this version |
| `entry_bar_number`, `exit_bar_number` | Data-record ordinals |
| `entry_time_utc`, `exit_time_utc` | Actual simulated fill timestamps |
| `exit_deadline_utc` | Strategy-supplied deadline; for the sample, entry timestamp plus configured hold minutes |
| `contracts` | Filled quantity |
| `entry_reference_price`, `exit_reference_price` | Observed closes used as fill references |
| `entry_fill_price`, `exit_fill_price` | Prices after adverse slippage |
| `entry_commission`, `exit_commission`, `total_commissions` | Costs in CU |
| `reference_gross_pnl`, `slippage_cost` | Informational reconciliation fields |
| `gross_pnl`, `net_pnl` | P&L as defined above |
| `actual_holding_minutes` | `(exit_time_utc - entry_time_utc) / 60 seconds` |
| `entry_reason` | `consecutive_green` for the sample |
| `exit_reason` | `hold_elapsed` or `end_of_data` |

Save the resolved strategy parameters and execution settings with each eventual run, along with dataset ID/hash, saved source timezone, timestamp convention, and strategy identity/source hash. Do not infer contract settings from a prior run. Trade exports and summaries must use the same underlying fills and arithmetic.

### Execution interface clarification

The initial interface omitted a way to carry the required deadline into trade records. `EntryIntent` now accepts optional `exit_deadline_utc` metadata, as an aware UTC datetime. A supplied deadline cannot precede the actual entry timestamp. The sample strategy will supply its deadline; a strategy without a deadline may leave it `None` (reported as null). The engine records this value without calculating a holding period or triggering an exit. This does not change any reviewed fixture's decisions or expectations. The current `Position` exposes the actual filled quantity, price, bar number, and entry timestamp.

`alphaquest.execution.execute(bars, strategy, execution_config)` yields immutable `Trade` and `EquityPoint` records. Equity points also expose `realized_net_pnl` as defined in section 5. Monetary operations use operand-derived Decimal precision and do not depend on the strategy's or consumer's Decimal context. No intermediate monetary rounding or second slippage deduction occurs.

The stream retains one equity point until the next observed bar or normal EOF, so the final point includes the `on_finish` fill without emitting a duplicate final point. A trade is emitted when closed, before its associated equity point. The engine pulls no next bar before the current callback and fill have completed. The strategy API supplies no dataset handle or future rows; it is an input boundary, not a Python security sandbox.

Exhaust the stream inside the reader's resource context before treating a run as complete. Previously emitted events are provisional if the reader, strategy, or engine later raises. Invalid input is not normal EOF and does not trigger `on_finish`. An empty input is rejected. Stopping early does not invoke `on_finish`; the caller owns input-resource cleanup. Only one ordinary intent per bar is supported. Entries while holding, closes while flat, unknown/multiple intents, and an entry from `on_finish` raise explicit errors. A successful stream must end flat.

Summary definitions:

- `trades_taken`: number of completed round trips, including end-of-data and zero-duration trades; entries/exits are not counted as separate trades.
- `winning_trades`: trades with **net** P&L > 0; `losing_trades`: net < 0; `breakeven_trades`: net = 0 exactly, before display rounding.
- `win_rate_pct = 100 * winning_trades / trades_taken`. Breakeven trades remain in the denominator. With zero trades, return `null` and display **N/A**.
- `total_gross_pnl`, `total_commissions`, `total_net_pnl`: sums over completed trades. `total_slippage_cost` is informational and is not a second deduction.
- With a completed flat run, `final_equity = initial_capital + total_net_pnl` and `total_net_pnl = sum(trade.net_pnl)`.
- With zero trades: all monetary totals and trade counts are zero, equity stays at initial capital, the trade array is empty, and no dummy trade is created.

### Trade-close drawdown metrics

Drawdown uses initial capital and **every completed trade's post-cost equity**,
matching `equity.csv`. It excludes open-position equity fluctuations and is
calculated from the complete series, never the bounded chart sample.

- `max_drawdown_amount`: largest positive `prior_peak_equity - equity`, in account
  currency units (CU). The running peak includes initial capital.
- `max_drawdown_pct`: largest `100 * (prior_peak_equity - equity) / prior_peak_equity`.
  This uses the corresponding peak, not initial capital, and is maximized
  independently of the monetary amount. It can exceed 100% if equity is negative.
  Percentages use 28 significant Decimal digits, round-half-even.
- `max_drawdown_duration_seconds`: longest elapsed UTC time from a peak to its
  recovery (`equity >= peak`), or to the final dataset bar if still unrecovered.
  Include gaps and time after the last trade. An equal-peak observation recovers
  the drawdown and becomes the latest peak timestamp for subsequent declines.
  Initial capital has no fill timestamp, so its duration clock starts at the
  first observed bar close. The longest duration need not belong to the deepest
  drawdown. Duration is stored as exact decimal seconds and displayed in days,
  hours, minutes and seconds. No drawdown and zero-trade cases return zero.

New reports record `period_start_utc` and `period_end_utc` from the first/last
observed bar closes. A one-bar loss can have positive drawdown and zero elapsed
duration; no earlier timestamp is invented for the initial balance.

Hand checks: initial 100, peak 120 at minute 10, trough 90 at minute 20,
recovery 120 at minute 60 gives amount **30**, percentage **25%**, duration
**50 minutes**. The reviewed `end_of_data` fixture gives **20 CU, 0.2%, 4 minutes**;
`last_bar_entry` gives **14 CU, 0.14%, 2 minutes**. All other reviewed fixtures
have zero trade-close drawdown, including the arithmetic fixture whose only
completed trade wins despite its open-position loss.

### Report artifacts and precision

`alphaquest.reporting.generate_report` consumes a complete engine event stream independently of the strategy. It writes `report.json` (summary, provenance/configuration, reconciliation results, full trades, and full equity), `trades.csv`, and `equity.csv`. It copies the engine's trade and equity values and only aggregates authoritative trade fields; it does not recalculate fills, costs, or unrealized P&L. Shared exact Decimal arithmetic supports both execution and aggregation without relying on the caller's Decimal precision.

Following the requested export change, `equity.csv` contains **starting equity and one row after each completed trade**, rather than one row per observed bar. Its columns are `trade_number,exit_time_utc,net_pnl,equity`. The starting row is trade number 0 with a blank exit timestamp, zero trade P&L, and initial equity. A trade row uses the trade's exact net P&L and its corresponding engine equity point after closing and charging all costs. Include breakeven trades and end-of-data exits, even when entry/exit timestamps coincide. Zero trades produces just the starting row. The engine and `report.json` retain the bar-close curve defined in section 5, including unrealized P&L, for reconciliation.

Store monetary values as decimal strings and timestamps as UTC ISO 8601. The initial JSON equity timestamp remains null; null values become blank CSV cells. A zero-trade CSV has the normal trade header and no data rows. A recurring win-rate percentage is represented with 28 significant Decimal digits using round-half-even; counts remain exact and authoritative. Zero-trade win rate remains null, displayed as N/A by the command.

The reporter streams arrays/rows to temporary files, validates a flat final point and all P&L/equity reconciliations, then publishes a new output directory. It rejects an existing output directory and leaves no completed report if replay or validation fails. The caller should supply the saved row count, which is checked against the final observed bar number. `alphaquest.run_backtest` wires the existing reader, sample strategy, engine, and reporter together, records dataset and strategy hashes/settings, and always supplies that row count.

### Backtest API

The existing FastAPI server also exposes the tested components through a code-owned strategy allowlist. Each strategy supplies its parameter definitions and validation. API runs require all strategy parameters and execution settings explicitly; financial settings use decimal strings and no instrument values are inferred. A worker thread runs preparation, replay, report saving, and result indexing while the existing progress endpoint exposes stage, processed/total bars, and run ID. Completion is emitted only after durable artifacts and a committed completed-run record exist. Failed runs have no completed record.

Completed summaries/provenance and indexed trade/equity rows are persisted in `backtests.sqlite3` beside the dataset store, with report files in `backtest_runs/RUN_ID/`. Records survive restart and source deletion. Retrieval is paginated (default 100, maximum 1,000 rows), and the equity endpoint follows the requested trade-close CSV format. The full bar-close series remains in the report JSON. See [API endpoints and reproducible commands](backtest_api.md). No external task queue is added.

The portal's Backtests screen renders parameter definitions from the allowlisted strategy endpoint, keeps execution settings separate, reviews the fixed bar-close convention, and sends explicit settings through the same APIs. It locks the form while the POST is active and polls actual progress. Completed reports show authoritative summaries, at most 1,000 trade-close equity chart points, 50 trades per table page, all saved settings, and the existing trade/trade-close-equity CSV downloads. Completed history is paginated, and a report hash URL reopens after refresh. The chart uses initial equity and equity after completed trades, matching equity.csv and excluding open-position fluctuations. Large-run samples retain endpoints and trade-count bucket extrema; metrics still use complete engine outputs. Currency is labelled CU (account currency unspecified), since no currency code exists in this contract. Monetary inputs, outputs, and tooltips remain decimal strings; only chart geometry and approximate axis labels use floating point. See [portal fixture review instructions](backtests_portal.md).

## 7. Hand-checkable fixtures

Files live in [`tests/fixtures/backtest_contract/`](../tests/fixtures/backtest_contract/). [`expected.json`](../tests/fixtures/backtest_contract/expected.json) contains each fixture's complete resolved settings, expected trades, summary, and full equity path. [`expected_trades.csv`](../tests/fixtures/backtest_contract/expected_trades.csv) is a flat review table of all expected trades. The CSVs are source bars, not engine-generated outputs. The expectations were manually specified and checked by standalone arithmetic; they were not produced by replaying an implemented strategy.

All fixture dates are January 5, 2026. UTC is the saved source timezone except for `gap_deadline`, whose source timezone is **America/New_York**. For that fixture, source 14:02 corresponds to UTC 19:02. Uploading it with UTC selected would change its expected timestamps.

| Fixture | Bars | Parameters (green count / hold minutes / contracts) | Slippage ticks / commission per contract per side | Expected result |
| --- | ---: | --- | --- | --- |
| `arithmetic_5m` | 7 | 3 / 20 / 2 | 1 / 1 | One trade, net +26; 20 minutes is four five-minute intervals |
| `doji_and_red_reset` | 11 | 3 / 2 / 1 | 0 / 0 | Doji and red each discard two accumulated greens; entry only on bar 9 |
| `no_pyramiding` | 10 | 3 / 2 / 1 | 0 / 0 | Ten green bars produce two sequential trades, no overlapping entries |
| `gap_deadline` | 6 | 3 / 20 / 1 | 0 / 0 | Target 19:22 UTC; actual exit 19:42 UTC; actual hold 40 minutes |
| `gap_streak` | 4 | 3 / 20 / 1 | 0 / 0 | A gap between the second and third green does not reset the streak |
| `end_of_data` | 5 | 3 / 20 / 1 | 0 / 0 | Exit after two minutes at dataset end, loss -20 |
| `no_trades` | 5 | 3 / 20 / 1 | 0 / 0 | No completed green streak; no trades; win rate N/A |
| `breakeven_after_costs` | 5 | 3 / 2 / 1 | 1 / 1.25 | Gross +2.50 offsets commissions 2.50; net zero; win rate 0% |
| `last_bar_entry` | 3 | 3 / 20 / 2 | 1 / 1 | Enter and exit on the final bar; zero-minute hold; net -14 |

### Expected trades (all timestamps below are UTC on January 5, 2026)

| Fixture / trade | Entry → exit | Entry fill → exit fill | Contracts | Gross | Commissions | Net | Actual hold | Exit reason |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| arithmetic_5m / 1 | 10:10 → 10:30 | 100.25 → 101.75 | 2 | 30 | 4 | **26** | 20 min | hold_elapsed |
| doji_and_red_reset / 1 | 10:08 → 10:10 | 105 → 107 | 1 | 20 | 0 | **20** | 2 min | hold_elapsed |
| no_pyramiding / 1 | 10:02 → 10:04 | 102 → 104 | 1 | 20 | 0 | **20** | 2 min | hold_elapsed |
| no_pyramiding / 2 | 10:07 → 10:09 | 107 → 109 | 1 | 20 | 0 | **20** | 2 min | hold_elapsed |
| gap_deadline / 1 | 19:02 → 19:42 | 100 → 103 | 1 | 30 | 0 | **30** | 40 min | hold_elapsed |
| gap_streak / 1 | 10:40 → 11:00 | 100 → 102 | 1 | 20 | 0 | **20** | 20 min | hold_elapsed |
| end_of_data / 1 | 10:02 → 10:04 | 100 → 98 | 1 | -20 | 0 | **-20** | 2 min | end_of_data |
| breakeven_after_costs / 1 | 10:02 → 10:04 | 100.25 → 100.50 | 1 | 2.50 | 2.50 | **0** | 2 min | hold_elapsed |
| last_bar_entry / 1 | 10:02 → 10:02 | 100.25 → 99.75 | 2 | -10 | 4 | **-14** | 0 min | end_of_data |

`no_trades` has no trade rows. Final equities, in table order by fixture, are 10026, 10020, 10040, 10030, 10020, 9980, 10000, 10000, and 9986.

### Behavioral review notes

- `doji_and_red_reset`: bar 3 is a doji; bar 6 is red. Both erase the preceding two greens. Bars 7–9 form the first qualifying streak.
- `no_pyramiding`: bars 4–5 are green while holding. Bar 5 exits but cannot re-enter. Only bars 6–8 count toward the second entry.
- `gap_deadline`: the deadline lies between observed source bars 14:17 and 14:42. The reference exit is the observed 14:42 Close of 103, with its real UTC timestamp.
- `gap_streak`: source bars 10:00, 10:01, and 10:40 are three adjacent green records despite the time gap.
- `end_of_data`: the last close is before the deadline, so `on_finish` requests the exit. This is not a completed 20-minute hold.
- `breakeven_after_costs`: positive reference/gross P&L is not a winning trade after costs. One breakeven trade gives 0/1 = 0% win rate.
- `last_bar_entry`: entry cash/equity are 9998/9993 immediately after the buy; the following same-time sell leaves 9986. The final bar's stored equity point is 9986.

The execution review command in `tests/review_execution.py` uses predetermined, test-only intent schedules and compares every trade field and equity point with these independent expectations. It checks execution at known decisions, independently of sample strategy logic.

The separate command in `tests/review_strategy.py` instantiates `ConsecutiveGreenHold` from `alphaquest/strategies/consecutive_green_hold.py` using each fixture's parameters. It reads the saved CSV through the existing reader, executes the actual strategy through the unchanged engine, and only then compares all trade fields and equity points. It prints an entry/exit table with reasons. The original source fixtures and expectations are unchanged.

`tests/review_reports.py` runs the same strategy on saved fixture IDs and checks every summary field, full trade record, equity point, and CSV row against the independent expectations. Generated reports and isolated saved fixture databases remain in the requested output directory for review.
