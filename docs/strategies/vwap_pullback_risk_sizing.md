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
EOD orders fill at the next observed bar Open, matching the supplied strategy's
`MarketNextBar` instruction. The order cutoff now uses the shared CSV session calendar, which adds
shortened-session handling beyond the original source without future-bar
inference. The retained `.pl` is
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
- With `use_eod_flat=true` (default), look up the scheduled close in the shared
  [NQ calendar](../../calendars/README.md). Submit an exit from the first observed
  Close at/after five minutes before that scheduled close, bounded by
  `eod_flat_time=1555`, and fill at the **next observed bar Open** with costs.
  Block entries at/after cutoff and throughout full-closure/weekend sessions.
  Reserve the next one-minute fill bar when submitting entries; its close label
  must be strictly before cutoff. Cancel pending entries that gap past cutoff
  or into a different session. `use_eod_flat=false` disables these calendar EOD
  rules; remaining exposure closes under the explicit EOF policy.

## Causal CSV session calendar

The Python implementation reads `calendars/cme_nq_closures.csv` once per strategy
instance. The same bytes are bundled in an installed package. Read
[the calendar guide](../../calendars/README.md) for sources, reviewed coverage,
manual updates and source-publication limitations. No exchange calendar is
fetched during a run. Outside reviewed coverage, a missing/malformed file and
unavailable timely liquidation prices reject the run with an actionable source
error; the engine never guesses regular hours or infers a close from gaps.

Sessions use **America/Chicago local ending dates**, not CME clearing trade
dates. Evening bars after 17:00 belong to the following local date; the 17:00
close label itself is in maintenance. Friday evening and Saturday-ending dates
are closed under the weekly schedule. A full-closure row also blocks the
preceding evening, while any holiday-night reopening belongs to the next date.
Regular sessions close at 16:00 CT; exception rows supply the earlier time.

```text
scheduled_close = CSV exception time, or 16:00 within reviewed regular coverage
order_cutoff = min(configured eod_flat_time, scheduled_close - 5 minutes)
flatten_submission = first observed bar Close at/after order_cutoff
flatten_fill = next observed bar Open, whose close label must be <= scheduled_close
```

| Scheduled close, CT | Default order cutoff, CT |
| --- | --- |
| 16:00 | 15:55 |
| 12:00 | 11:55 |
| 12:15 | 12:10 |
| 08:15 (some Good Fridays) | 08:10 |
| 08:30 (mourning sessions) | 08:25 |
| Full closure | No entries |

A configured 15:45 cutoff remains 15:45 on regular days; shortened days can move
it earlier. Five minutes means elapsed time, not five observed rows. A missing
11:55 bar does **not** promote the 11:54 bar into an earlier decision: the next
observed eligible close submits flattening. If the next executable Open is in
the evening, the run rejects instead of fabricating a pre-close fill. The same
holding-bar guard runs **before** old pending brackets, preventing an evening
stop/target from disguising a missed scheduled close. Prior eligible bracket
fills retain priority, including through the cutoff bar.

Bars are close-labelled. An exit recorded on the 11:56 bar uses its Open,
ordinarily around 11:55, not its Close. A close-labelled bar does not establish
an actual execution tick or certify a broker/prop liquidation deadline.
At EOF, remaining exposure closes at the last actual Close with reason
`end_of_data`; it is never relabelled as a next-Open EOD fill. Truncating a day
at 09:03 leaves its scheduled cutoff unchanged and does not remove earlier
signals. This change eliminates the earlier **price-bar lookahead**; a strict
point-in-time calendar claim still requires dated notices published before the
simulated decision, as explained in the calendar guide.

New reports identify `eod_next_open_csv_session_calendar_v1`,
`session_flattening.lookahead=false`, the calendar SHA-256 and explicit coverage,
observed session counts, the first five resolved plans and a digest of plans.
`source_sha256` now hashes the Python strategy, its calendar helper and the CSV
as one dependency bundle. Calendar changes invalidate saved-result reuse,
queued optimization identity and new detail/risk replays. Existing reports and
their calendar/lookahead notices remain immutable. Old cutoff-Close and
next-Open inferred-session reports are labelled as earlier execution models.

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
| EOD | Calendar chooses the order cutoff; fill next observed Open by scheduled close with costs |
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
`execute(bars, strategy, config)` inside `read_bars(...)`. Use `execute()` for complete replay: its holding-bar guard validates scheduled
liquidation availability before applying pending orders. Direct `on_bar()` calls
need no future context, but do not themselves execute or validate fills.

```bash
.venv/bin/python -m pytest tests/test_vwap_pullback.py tests/test_next_bar_execution.py -q
```

## Reproduce the normal and early-close review

```bash
.venv/bin/python tests/review_vwap_session_flatten.py \
  --output artifacts/vwap-session-flatten-review-NEW
```

The command uses the normal saved-dataset and Backtests UI workflow with
clearly labelled synthetic minute-labelled price fixtures. It retains an isolated
library, durable report files, screenshots, CSV downloads, and comparisons in
that new directory. Its temporary server stops automatically.

Expected observations: order cutoffs are 15:55, 11:55 and 12:10 for session
closes of 16:00, 12:00 and 12:15 respectively. These deliberately sparse
fixtures have their next observed bar at the session close, so the exits fill
those bars' Opens at 16:00, 12:00 and 12:15. Each synthetic trade enters at
115.25, exits at 119.75, earns 90 gross, pays 2 commissions and nets 88 CU.
The saved report explicitly
shows calendar-based exits without bar lookahead; source CSV bytes and earlier runs remain unchanged.
To reopen the isolated review library after the command ends:

```bash
ALPHAQUEST_DATA_DIR="$PWD/artifacts/vwap-session-flatten-review-NEW" \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/#reports`, open a **SYNTHETIC** review report,
inspect its trade exit and settings, and download its trade/equity CSVs.
Stop this optional server with Ctrl-C. The user journey and run IDs are also
in the generated `verification.json`. The review script leaves no server running.
