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
- EOD triggers while holding at `15:55 <= Time < 23:00`, replacing the next
  bar's bracket with a market exit. Entry windows remain independent: the
  source can enter after EOD and request flatten after filling. No additional
  post-EOD entry veto is added.

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
| EOD | Trigger at the first eligible observed close; fill next Open |
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
`execute(bars, strategy, config)` inside `read_bars(...)`.

```bash
.venv/bin/python -m pytest tests/test_vwap_pullback.py tests/test_next_bar_execution.py -q
```
