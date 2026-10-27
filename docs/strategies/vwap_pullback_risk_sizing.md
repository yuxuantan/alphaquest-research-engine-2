# VWAP pullback — PowerLanguage port

Select **Vwap pullback risk sizing** in Backtests. The implementation is
`alphaquest/strategies/vwap_pullback_risk_sizing.py`. The supplied source is
preserved verbatim in [`vwap_pullback_risk_sizing.pl`](vwap_pullback_risk_sizing.pl),
SHA-256 `12047fb6956d99d58ba1662517b398b86028923575d0447fac735b2bb7066b66`.

All source Inputs are available in snake_case with their actual defaults:
`PositionSize` becomes `position_size`, `Max_Contracts` becomes `max_contracts`,
`ADXDecay_LB` becomes `adx_decay_lb`, and `ORStartTime` becomes `or_start_time`.
The extra `max_bars_back=42` models the chart history setting. The source header
says four contracts, but its Inputs specify **one contract**, the port's default.
Risk sizing and shorts default off; both ADX gates and EOD flatten default on.
EOD flattening now intentionally differs from the PowerLanguage source: it
uses the backtest-only last-bar lookahead rule below. The retained `.pl` is
the original source and is not silently rewritten.
`plot_trade_levels` emits signal details through the module's INFO logger;
enable INFO logging in your Python host to display them.

Use full-session **one-minute bars labelled by closing time**, with trade volume
in CSV `Volume`. Save the dataset with its actual source timezone. The strategy
converts UTC to `America/Chicago`, including DST. All session times use that zone.
Tick size and point value default to the dataset's saved instrument settings (with optional run-specific overrides): for NQ, 0.25
and 20 USD/point; for MNQ, 0.25 and 2 USD/point. Set costs separately. The reader
does not establish bar interval, full-session coverage, contract rolls, or
trade-volume provenance.

## Trading rules retained

- ORB includes closes **after 08:30 through 09:00**. The first observed outside
  bar makes it ready. A close strictly above/below the range latches the break,
  including on a possible entry-signal bar.
- VWAP uses `(High+Low+Close)/3`, weighted by trade volume. Nonpositive volume
  contributes weight 1. Default VWAP window: `(08:30,17:00]`; entry: `(09:00,17:00]`.
- Retest mode 1 latches a Low/High touch and requires a close strictly back
  above/below VWAP. Mode 2 requires a close through VWAP and a later reclaim.
  Latches survive rejected ADX, stop-distance, reward/risk, and sizing checks.
- Strict symmetric pivots reject equal highs/lows. Strength N requires N
  right-hand bars; detection starts at `CurrentBar > 2*N`. Pivot histories
  survive day resets.
- Stop mode 1 uses the latest confirmed stop pivot; mode 2 tracks the extreme
  since the first retest latch, including bars while ADX delays. Buffers extend
  stops outward. Targets use the latest confirmed target pivot. Levels freeze
  when an entry order is submitted.
- ADX elevation uses `>=`; decay uses `<= ADX[lookback]`, on the signal bar.
  ADX calculates on every evaluated bar, including outside sessions.
- Level direction, maximum stop distance, reward/risk, and sizing use the
  **signal close**. Next-bar gaps do not resize positions or recompute levels.
- Risk quantity is `floor(capital * risk_pct / 100 /
  ((stop_distance + 2*tick_size) * point_value))`, capped at `max_contracts`.
  Zero skips the order. Fixed `position_size` ignores the cap. Sizing capital
  is independent of execution capital and does not compound.
- Trade count increments on submission. Submission clears both directional
  break/retest flags. Opposing strict reclaims prevent simultaneous signals.
- Reset follows the exact crossing: current HHMM **> 23:00** and previous
  HHMM **<= 23:00**, plus the first evaluated bar. Date rollover alone does
  not reset. Missing the crossing can miss a reset; RTH-only data is unsuitable.
- With `use_eod_flat=true` (default), infer each session's close from its last
  observed daytime bar. Exit at the actual bar Close at/before five minutes
  earlier, capped by `eod_flat_time=1555`, and block entries at/after that cutoff.
  Pending entries that gap past the cutoff are cancelled. `use_eod_flat=false`
  disables this inference and entry restriction; remaining exposure closes at EOF.

## Backtest-only last-bar lookahead

This is an explicitly permitted historical simulation assumption, not a live
early-close detector. No exchange calendar or special-date list is fetched.
The engine buffers one session before replaying it through the same signal,
fill, cost, equity, and reporting code. It does not edit an old trade timestamp
while leaving its price or P&L unchanged. Existing saved reports remain intact;
run a new backtest to get the new behavior.

Sessions begin at 17:00 CT on the preceding date and end on the following local
date. The last observed bar on that ending date at/before 16:00 is the inferred
close. Evening bars at/after 17:00 belong to the following session; bars in the
16:00-17:00 maintenance interval cannot extend the inferred daytime close.
This session-ending date is not an official CME clearing trade date.

```text
target_cutoff = min(eod_flat_time, last_observed_daytime_bar - 5 elapsed minutes)
executable_cutoff = last real bar at or before target_cutoff
```

| Last daytime bar, CT | Target cutoff, CT |
| --- | --- |
| 16:00 | 15:55 |
| 12:00 | 11:55 |
| 12:15 | 12:10 |
| 15:59 | 15:54 |

Five minutes means elapsed time, not five CSV rows. If the exact cutoff minute
is absent, use the preceding actual bar and its Close, including adverse
slippage and both-side commissions. If no such bar exists, do not enter that
session. Earlier stop/target exits stay intact, including a bracket that fills
inside the cutoff bar before its Close. No new entry may fill at/after cutoff.

The rule uses only the selected replay slice. A truncated or sparse day,
including the final selected day, is deliberately treated as an early close.
For example, a selection ending at 09:03 moves that day's cutoff to 08:58 and
can eliminate its morning entries. Choose complete data when that assumption
is unwanted. This is the limitation accepted in place of maintaining dates.

Reports label the execution model `inferred_session_close`. Their strategy
metadata records the enabled lookahead rule, session count, missing/earlier
cutoff counts, the first five resolved examples, and a SHA-256 of all resolved
plans. Trades carry their executable cutoff in `exit_deadline_utc`; forced
exits use reason `eod_flat`. These values persist in normal report downloads.

## History and ADX

The first `max_bars_back` records supply history without evaluating strategy
state. The following record is PowerLanguage `CurrentBar=1`. Initial DM/TR
means use `adx_len` changes ending on that record. ADX averages its first
`adx_len` DX values cumulatively, then applies Wilder smoothing. Unavailable
initial ADX lookback values are zero. This follows the published
[MultiCharts DirMovement initialization and recurrence](https://www.multicharts.cn/post?idno=181).

`max_bars_back` must cover both pivot windows, ADX length, and decay lookback.
Match this chart property and leading history when comparing MultiCharts
exports. Indicators use a fixed 50-digit Decimal context; PowerLanguage uses
floating point, so threshold-edge differences remain possible.

## Execution assumptions and parity limits

Generic engine intents support next-observed-bar markets and one-bar OCO
brackets. The sample strategy retains same-close execution. Reports save the
selected execution assumption.

| Event | Replay behavior |
| --- | --- |
| Entry | Next observed **Open**, with adverse slippage |
| Entry bar | No bracket: with IOG off, the source sees the filled position at its close and submits exits for the following bar |
| Bracket | Submitted at each holding close; active for the next observed bar only |
| Stop gap | Open beyond the stop, with adverse slippage |
| Target gap | Open beyond the target, without adverse limit slippage |
| Ordinary target | Target price; a touch suffices; no adverse limit slippage |
| Both levels hit | Stop first, unless the Open has already executed one side |
| EOD | Last-bar lookahead chooses the executable cutoff; fill its Close with costs |
| EOF pending entry | Cancel; no fabricated future bar or fill |
| EOF exposure | Final Close liquidation with costs and `end_of_data`, an explicit repository policy additional to the source |

OHLC replay does not reconstruct tick order, queue position, or MultiCharts
Bar Magnifier paths. Limit touch rules, ambiguous bars, and final liquidation
can differ from a MultiCharts configuration. Market/stop slippage and both-side
commissions use the shared engine. Short P&L and unrealized equity reverse the
price direction correctly.
Bracket prices are used verbatim, without additional tick rounding.

All reported fill times label the **containing bar's close**, including Open
and intrabar fills. They identify the fill bar, not an observed execution tick.
`actual_holding_minutes` is the difference between those labels. Equity has
one point per bar; `position_contracts` remains unsigned, and trade `side`
identifies direction.

Tests establish deterministic synthetic mechanics and reconciled arithmetic.
**MultiCharts trade-for-trade parity has not been established**: no matching
bar/ADX/trade export was supplied. Compare identical data, history, Inputs,
costs, session settings, and fill settings before making a replication claim.

## Run

With default source Inputs and your saved dataset (first save tick size and
monetary point value in Datasets; this example assumes 0.25 and 20):

```bash
.venv/bin/python -m alphaquest.run_backtest \
  --dataset-id YOUR_DATASET_ID --output artifacts/vwap-pullback-run \
  --strategy-id vwap_pullback_risk_sizing \
  --initial-capital 500000 \
  --slippage-ticks 1 --commission-per-contract-per-side 2.50
```

Costs above are illustrative. `--strategy-parameters` accepts a JSON object
with every parameter: decimals as strings, booleans as JSON booleans, integers
as JSON integers. The API requires every parameter explicitly; the portal
provides all controls. Python callers construct
`VwapPullbackRiskSizing(Parameters(), execution_config=config)` and consume
`execute(bars, strategy, config)` inside `read_bars(...)`. With EOD inference
enabled, use `execute()` rather than calling `on_bar()` directly: execution
prepares the future session context required for this declared lookahead.

```bash
.venv/bin/python -m pytest tests/test_vwap_pullback.py tests/test_next_bar_execution.py -q
```

## Reproduce the normal and early-close review

```bash
.venv/bin/python tests/review_vwap_session_flatten.py \
  --output artifacts/vwap-session-flatten-review-NEW
```

The command uses the normal saved-dataset and Backtests UI workflow with
clearly labelled synthetic one-minute-price fixtures. It retains an isolated
library, durable report files, screenshots, CSV downloads, and comparisons in
that new directory. Its temporary server stops automatically.

Expected observations: a 16:00 close exits at15:55; a 12:00 close exits at11:55;
a 12:15 close exits at12:10. Each synthetic trade enters at115.25, exits at117.75,
earns50 gross, pays2 total commissions and nets48 CU. The saved report explicitly
shows backtest lookahead; source CSV bytes and earlier runs remain unchanged.
To reopen the isolated review library after the command ends:

```bash
ALPHAQUEST_DATA_DIR="$PWD/artifacts/vwap-session-flatten-review-NEW" \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/#reports`, open a **SYNTHETIC** review report,
inspect its trade exit and settings, and download its trade/equity CSVs.
Stop this optional server with Ctrl-C. The user journey and run IDs are also
in the generated `verification.json`; this command never starts a persistent server.
