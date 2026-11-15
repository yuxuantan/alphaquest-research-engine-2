# Trade tick datasets

Implemented 15 November 2026. The Dataset tab accepts **Sierra Chart `.scid`**
and the trade CSV below. Tick sources use the existing campaign, execution,
RunStore and Prop Sim owners. There is no separate tick simulator or result store.

## Import

1. Open **Dataset → Source format → Trade ticks**.
2. Choose one contract file, give it a name and set the root instrument and its
   exact tick size / point value. For example, NQ uses `0.25` / `20`; MNQ uses
   `0.25` / `2`. The instrument field identifies the price/risk contract; an
   expiry filename remains recorded separately. Source timezone must be UTC.
3. Click **Import trade ticks**. The upload streams to disk; the complete file
   is validated and indexed before it becomes selectable. The OHLC CSV upload's
   1 GB restriction is not applied to the raw SCID upload. Available disk space
   and the normal backtest/native simulation admission bounds still apply.
4. The library shows the trade count. **Minute CSV**, **Flow CSV**, and collapsed
   **Trade sources** downloads retain inspectable source evidence. Dataset details
   show the classified-volume percentage and execution/decision clocks.
5. Create a campaign backtest using this dataset. Existing mechanics review,
   phase ordering, frozen IS selections and OOS/Monte Carlo gates still apply.

SCID support is deliberately precise: `SCID` magic, 56-byte header, 40-byte
little-endian records, version 1, signed integer UTC microseconds since
1899-12-30. `Last` is the trade price; `High` / `Low` fields are not substituted
for it because Sierra may use these as quote fields. A record needs
`NumberOfTrades=1`, positive volume, a finite positive tick-aligned price, and
bid volume + ask volume <= total volume. All-zero deleted records are skipped
while original record ordinals remain intact. Aggregated and quote-only records,
truncated records, unsupported timestamps and timestamp inversions reject.
Equal timestamps are valid: original file order breaks the tie. No sorting or
clock clamping repairs an execution path.

Canonical CSV uses exactly these five columns, in this order:

```csv
timestamp,price,volume,bid_volume,ask_volume
2026-01-05T14:30:00.000000Z,25000.25,2,0,2
2026-01-05T14:30:00.000001Z,25000.00,1,1,0
```

Timestamps explicitly use UTC and at most six fractional digits. Volumes are
unsigned whole numbers; total volume is positive. Prices must be exactly
representable by the supported SCID float32 price storage and declared tick
grid. CSV is normalized into the same validated binary record format. Its
normalized source is downloaded as SCID; do not mistake this for the original
CSV byte encoding. Records are not claimed to be reconstructed exchange-sized
orders or a reliable aggressor classification where the source supplies none.

The Google Drive NQ archive was inspected at the file-list/schema level. Its
actual record contents were not downloaded or independently validated here.
Each imported contract receives the full local checks above.

## Multiple expiry contracts

Import individual expiry files first, using the same root symbol/settings.
Expand **Build a continuous tick dataset from contract files**, add a source and
inclusive first/last **CME session** dates for each range, and build the dataset.
Ranges must be ordered and non-overlapping. Each range must contain observed
minutes. The stored roll schedule binds parent dataset IDs and source hashes.

This is an explicit, unadjusted roll schedule, chosen before examining strategy
outcomes. There is no selection using the current session's final volume, no
mixing contracts within a session, no back adjustment and no invented trades
across gaps. Indicators can cross a real roll gap; choose and review the schedule
accordingly. A parent dataset cannot be deleted while a composed dataset
references it. Raw source files are retained for saved evidence; deleting a
library row is not a tick-file garbage-collection operation.

## Strategy inputs and order flow

Tick records form one-minute bars over `[minute start, minute end)`, labelled at
minute end. Minutes with no trades remain absent. OHLC comes from actual trade
prices; volume is summed. `UpVol` is classified ask volume and `DownVol` is
classified bid volume for these tick-derived bars; these are not price upticks
and downticks. Unknown volume is retained separately.

Strategies continue receiving **completed-minute callbacks**, not an HFT or
per-tick decision callback. `bar.flow` is an immutable `TradeFlow` containing:

| Field / property | Meaning |
| --- | --- |
| `records` | Individual source records in this minute |
| `bid_volume`, `ask_volume` | Source-classified executed volume |
| `unknown_volume` | Total minus bid/ask classified volume |
| `delta` | Ask volume minus bid volume |
| `delta_pct` | 100 × delta / classified volume; zero if none classified |
| `price_volume`, `vwap` | Actual sum(price × volume), and trade-volume VWAP |
| `largest_record_volume` | Largest recorded component, not an inferred parent order |

The built-in **VWAP pullback risk sizing** campaign has an optional **Use order
flow** filter, off by default. Its completed signal minute must have the minimum
record count, sufficiently classified volume, and directional delta >= the
configured threshold (positive for long, negative for short). Defaults are one
record, at most 10% unknown volume and at least 10% directional delta. These
parameters participate in the normal Broad/Narrow grid and refinement rules.
Its existing session VWAP formula remains unchanged; the exact trade VWAP is
available to strategies and in the Flow CSV.

For a new registered strategy, read `bar.flow` only in the completed-bar callback,
require a tick dataset when the strategy relies on it, and use ordinary intents.
For example:

```python
flow = bar.flow
if flow is None:
    raise ValueError("This strategy requires a trade tick dataset")
if flow.known_volume and flow.delta_pct >= minimum_delta_pct:
    # Combine this completed-minute evidence with a causal entry/stop plan.
    ...
```

No depth, resting orders, queue position, cancellation flow or liquidity can be
inferred from these trade records. Those require another source and model.

## Execution and risk

`execution.py` still owns fills, slippage, commissions, position state and P&L.
For a tick-derived bar it uses a checked private `TickWindow` to resolve orders:

- A next-open market order uses the first recorded trade of the next bar.
- Stop entries trigger at the first recorded crossing. Competing OCO entries
  choose the first crossing, cancelling the other side. Invalid overlapping
  thresholds reject rather than inventing a winner.
- Attached entry protection starts at the actual entry record. Pre-entry extrema
  do not affect held risk or trigger exits. Later stops/targets resolve in the
  recorded order; OHLC adverse/favourable sensitivity replays are unnecessary.
- A stop uses the first observed price at/beyond its trigger, plus declared stop
  slippage. A jump across a stop can therefore fill worse than its trigger.
  Limits retain their submitted price, penetration and configured opening-price
  improvement rules. Full fills are a model assumption, not measured liquidity.
- Native account/daily floors compete with strategy stops and targets on that
  same price path under the existing phase controller.
- Intratrade MAE/MFE includes only observed held prices and costs. Every new
  adverse record is retained in order as an observed jump. Fixed-size Prop Sim
  can therefore resolve the first crossing of any account floor without assuming
  a continuous price segment between trades. Unknown intervening prices are not
  fabricated.

Trade fills use actual source timestamps, including sub-second values in CSV.
Equity/strategy decisions retain the completed-minute clock. At a minute boundary,
a decision and next-open fill can share the same timestamp; source-bar/event
ordering establishes causality. The canonical projection labels such a fill
`observed_open` rather than claiming a strictly later clock timestamp.
Same-close market orders retain the existing completed-minute price proxy and
zero-latency/full-fill assumption. Trade ticks resolve observed path order; they
do not eliminate spread, liquidity, latency or missing-data uncertainty.

## Campaign and Prop Sim integration

| Surface | Behavior |
| --- | --- |
| Mechanics / Broad / Narrow / OOS | Original trade path retained through date selection, prepared streams, multi-worker execution and cost-stress reruns |
| Campaign criteria | Existing server-owned rules unchanged; period MTM measurements retain their documented minute-close sampling |
| Final campaign Monte Carlo | Existing daily P&L sanity check from the actual tick-executed reports; does not resample individual trades as price observations |
| Fixed-size independent Evaluation / Funded | Existing account engines use verified source outcomes and ordered adverse jumps; separate phase objectives and costs remain unchanged |
| Percentage-risk independent optimizers | Existing supported EOD-flat VWAP family reruns actual signals, tick fills and controllers; order-flow filter is supported |
| Apex / LucidFlex | Existing supported profiles, limits, calendars, cash and payout transitions apply |
| OOS / complementary checks | Frozen choices and source captures are reused; no reselection or nested historical refits are introduced |
| Separate / shared portfolio and replacement cash flow | Tick windows and flow survive session spools; actual strategies/controllers and the existing fee budget/cash ledger are reused |

Native percentage/portfolio capabilities remain those documented by the existing
owners (currently the supported NQ/MNQ EOD-flat VWAP family). Tick upload does not
make an arbitrary strategy or unsupported instrument eligible for those models.
Qualification requirements are not bypassed: Prop Sim's qualified selector still
requires all campaign phases and current Monte Carlo to pass.

Raw trades and minute indices have independent SHA-256 checks. Dataset identity
binds the CSV, raw tick path and minute index, so identical OHLC with different
intraminute paths cannot share results. Changing a saved tick size rejects; import
a new source instead. Caches/spools preserve flow/windows; mutation rejects.
Reports retain source identities and execution assumptions. New numerical owners
include the tick adapter in their implementation identity. Earlier reports stay
readable; incompatible frozen calculations are not silently upgraded.

## Verification and normal-product demonstration

Focused arithmetic/import/execution/API coverage:

```sh
.venv/bin/python -m pytest -q tests/test_tick_datasets.py
```

This includes a real four-phase campaign, final Monte Carlo and automatic Prop Sim
IS/OOS assessments, without bypassing gates; Apex/Lucid Evaluation/Funded native
percentage replays; indexed versus ordinary execution; and shared/separate
portfolio cash/quantity checks.

For an inspectable browser demonstration in a retained normal product store:

```sh
AQ_TICK_PRODUCT_DIR=/private/tmp/alphaquest-tick-product-proof \
ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome \
.venv/bin/python -m pytest -q tests/test_tick_datasets_browser.py
```

Use a fresh directory. The temporary server/browser shut down after the test.
The store, original synthetic SCID, reports, downloads, hashes and screenshots
remain there. Reopen it without resimulation:

```sh
ALPHAQUEST_DATA_DIR=/private/tmp/alphaquest-tick-product-proof \
.venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8015
```

Open the saved report from `product-evidence.json` using
`/#backtests/report/<source_id>`; its normal Prop configuration opens the native
account replay. The saved analysis is at `/#backtests/prop/job/<analysis_id>` (or use
Job history's report link). Stop this optional reproduction server with Ctrl-C.

All demonstration records are labelled **SYNTHETIC**. Independent expected
percentage-risk quantities are `10, 9, 5`; trade net P&Ls are `-120, 180, 100`.
The first stop is 113 but the next recorded trade is 112, so the first loss is
`(112−118) × 2 × 10 = −120`. Subsequent risk budgets use the actual account
balance. Final provider trading balance is 50,160; cash receipts remain governed
by the account's payout rules, not by this trading profit.

The SCID record layout/chunking approach reuses the reviewed older AlphaQuest
converter at commit `1f76adb6188c94ecd133bf0773f2cb77c07b696c`.
Its older execution engine, same-session dominant-contract selection and
source-specific qualification claims were not imported.
