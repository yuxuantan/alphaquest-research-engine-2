# Noise

The [supplied PowerLanguage](noise.pl) is the reference for the
[AlphaQuest strategy](../../alphaquest/strategies/noise.py) and the
[MultiCharts .NET signal](../../multicharts/OFB_Noise_Signal.cs).

## How it trades

Noise looks for a directional 15-minute close outside the usual move for that
time of day. Each slot from 09:00 to 14:15 CT keeps its own history. With the
defaults, it averages the last 20 observations of `abs(close / date_open - 1)`
for that slot. The calculation excludes the current bar. It expands the higher
of the date open and the previous close upward and the lower anchor downward
by that percentage times the volatility multiplier.

The date open is the open of the first candle stamped on the civil chart date.
The previous close is the immediately preceding candle's close. Regular-session
data and Globex data therefore give different anchors. A slot with fewer than
20 qualifying observations cannot generate band-based orders.

| Event | Default rule |
| --- | --- |
| Long or short entry | At a close from 09:00 through 14:00 CT, go long above both the upper band and the candle open, or short below both the lower band and the candle open. Submit two contracts at market for the next bar. |
| Stop and target | 50 and 25 points from the actual entry fill, respectively. Both are active on the entry bar. |
| Band and EMA exit | At a warmed-up slot, close a long below the higher of the upper band and EMA 20, or a short above the lower of the lower band and EMA 20. Submit for the next open. |
| Opposite breakout | Through 14:00 CT, the enabled opposite setup takes priority over the band/EMA exit. Submit the exit and, if allowed, the opposite entry for the same next open. |
| Clock exit | The exact 14:30 CT close submits an exit for the next open, even if the slot history is unavailable. A missing 14:30 bar can leave the position open across sessions. |
| Daily admission | At most ten entry submissions, including reversals. Three closed positions with losses at least as large as the full-position stop also block entries. An opposing exit still goes through when admission blocks the reversal. |

The loss gate matches the source's update order. On a new chart date the
counters reset and the current closed-trade count becomes the baseline. On
other decision bars, if the total has increased, the signal checks the most
recent closed position once. The threshold is 50 × point value × two contracts
by default, or $2,000 on NQ. In AlphaQuest the comparison uses realized P/L after
its configured execution costs. The .NET signal reads the host's closed-position
profit. Compare cost treatment with a matching export after verifying the
zero-cost run. [MultiCharts Strategy Performance](https://www.multicharts.com/trading-software/index.php?title=Strategy_Performance)

## AlphaQuest

Open **Campaigns → Noise**. The explanation and numerical example are above
Datasets. Choose **New backtest**, select close-labelled one-minute NQ or MNQ
OHLC with the intended session coverage, declare the research split, and run
mechanic validation. The strategy reads UTC-normalized data on the Central
clock. Each independent replay needs enough leading data to warm the slots. The
default `max_bars_back=1` reserves one completed candle for the previous-bar
reference. Match this setting to the resolved PowerLanguage chart offset for
comparisons.

An observed quarter-hour close supplies the 15-minute decision. The first
observed minute in that candle supplies its open. AlphaQuest keeps protective
orders active on the intervening minutes and models their price path using the
nearer extreme first and Low first on ties. Market exits and reversals execute
at the next observed open. Fill timestamps identify the containing minute
close. Extend the replay window if it ends with a position still open. The
saved report records the clock rule and execution model.

## MultiCharts .NET mechanic validation

1. Create a new C# Signal named `OFB_Noise_Signal` in the PowerLanguage .NET Editor,
   paste the signal file, and compile. Apply it by itself to the same continuous
   NQ symbol, data range and session template as the PowerLanguage comparison.
2. Use one 15-minute series, bar timestamps at close, the Exchange clock in CT,
   IOG off, one-minute Bar Magnifier and Auto MaxBarsBack. Load enough history
   for 20 prior observations of each slot. For an Eastern chart, shift the three
   time inputs one hour forward. The original and .NET versions both read the
   chart clock.
3. Turn on `showValidation`. Blue lines show the bands, orange shows EMA, and
   red and green show the computed stop and target for held positions. The chart
   keeps the latest 480 line segments. Use native trade markers to identify
   fills. In Output, find the timestamped bar to inspect the anchors, slot
   history, candle prices, exit thresholds, entry gates, loss check, next-open
   submission and observed position or trade-count changes.
4. Compare both signals using identical source bars, session settings and zero
   costs first. Match submissions on the signal candle. Match fill prices,
   timestamps, quantities and reasons using the native trade list. Include a
   reversal with and without remaining entry allowance, a stop or target on
   the entry bar, and a session with no 14:30 candle. Repeat with matching
   costs to verify the loss gate at its threshold.

The .NET signal uses the host's built-in `XAverage` and per-contract special
orders. The local C# harness checks order arguments, submissions and diagnostics
with test doubles. Installed MultiCharts compilation, order arbitration,
rendering and trade-for-trade parity require the native check above.
[MultiCharts Special Orders](https://www.multicharts.com/trading-software/index.php?title=Special_Orders)

## Reproduce the saved campaign run

The evidence in `artifacts/noise-mechanics-20261124/` comes from the normal
AlphaQuest campaign. The input is synthetic and has a fixed answer.

1. Upload `synthetic-noise.csv` as NQ with source timezone `America/Chicago`,
   tick size 0.25 and point value 20. Use zero slippage and commission. Set
   initial capital to 10,000.
2. Open **Campaigns → Noise → New backtest**. Select that dataset and retain the
   default parameters. Use IS 2026-02-23 through 2026-03-27 and declare
   2026-03-30 as OOS. Open mechanic validation and run it.
3. Expect one closed trade for two NQ. The 2026-03-27 09:00 CT candle closes at
   20,010, above a 20,000 upper band. The next minute opens at 20,015 and
   reaches 20,040. The 50-point stop is 19,965. The 25-point target fills during
   the entry minute for $1,000 net at zero costs. The CSV labels both fills
   09:01 CT, or 14:01 UTC. The human mechanic review stays pending.
4. Download **Trades CSV** and **Saved review JSON**, then open the saved
   backtest report and check the exact 14:30 CT clock exit rule. The saved
   report, downloads and campaign screenshots are in the evidence directory.

Run the focused checks from the checkout root.

```sh
.venv/bin/python -m pytest -q tests/test_noise.py tests/test_strategy_sizing_contract.py
ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/python -m pytest -q \
  tests/test_campaign_mechanics_browser.py::test_noise_campaign_explanation_mechanics_and_downloads
dotnet run --project tests/multicharts_noise/NoiseCheck.csproj \
  --artifacts-path /tmp/alphaquest-noise-csharp
```
