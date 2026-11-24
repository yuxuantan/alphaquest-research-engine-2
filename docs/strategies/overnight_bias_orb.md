# Overnight Bias ORB

The supplied [PowerLanguage](overnight_bias_orb.pl) is the reference.
AlphaQuest registers [Overnight Bias ORB](../../alphaquest/strategies/overnight_bias_orb.py)
as `overnight_bias_orb`. The MultiCharts .NET signal is
[OFB_OvernightBiasORB_Signal.cs](../../multicharts/OFB_OvernightBiasORB_Signal.cs).

## Match the clocks and warm-up

| Input | Eastern chart | Central chart |
|---|---:|---:|
| SessStart | 09:30 | 08:30 |
| OREnd | 09:45 | 08:45 |
| LastEntry | 13:00 | 12:00 |
| FlatTime | 15:30 | 14:30 |
| SessEnd | 16:00 | 15:00 |

AlphaQuest converts source timestamps to Eastern for the strategy. Set the
dataset import timezone to the timezone in the file. Use the Eastern strategy
defaults even for CSVs recorded in Central time. MultiCharts uses the chart
clock, so use the appropriate column for its inputs.

The source resets on the **civil date change**. The pre-midnight evening
portion of a Globex session drops out of the bias range. The bar stamped
09:30 ET extends the overnight range. The bar stamped 09:45 ET supplies the
RTH Open and default opening range. The 10:00 ET close is the first bar that
can lock the range and submit a breakout.

Both ports use the completed RTH daily high, low and close to construct true
range at the next date change. The stop distance needs the simple average of
15 completed RTH true ranges by default. The opening-range band uses the
previous EMA. It is bypassed during opening ranges 1 through 19 and first
applies on range 20. Rejected breakouts leave the bias intact. The entry cap
counts submissions, including same-bar round trips.

Include at least two months of full-session data in the selected calculation
window for normal review. The defaults reserve the first **250 15-minute bars**
for MaxBarsBack before calculating the daily state. When an independently run
IS or OOS window starts later, it initializes its own history and warm-up.

## Run in AlphaQuest

1. Import full-session, close-labelled **one-minute OHLC** for NQ or MNQ. Supply
   the dataset's actual time zone and contract economics.
2. Open **Campaigns → Overnight Bias ORB → New backtest**. Select the dataset,
   declare the IS/OOS split and set matching costs.
3. Open **Mechanic validation** and run the default-parameter backtest. Inspect
   the metrics and sampled trades. Download **Trades CSV** and **Saved review
   JSON** from that page.
4. Compare the same calculation window, data and settings against the original
   and .NET signals in MultiCharts. Complete the existing parity and trade
   review only after that comparison. IS Broad and later phases use the
   ordinary campaign gates.

AlphaQuest groups the execution minutes into close-stamped quarter-hour
candles. The first observed minute supplies Open and the last supplies Close.
When the quarter-hour's final minute is absent, the next bucket's timestamp
can identify the last observed minute of the earlier candle. Decisions use
completed candles and observed prices only.

ADX uses the existing [DirMovement/Wilder port](https://www.multicharts.cn/post?idno=181),
including its startup and smoothing sequence. The exhaustion gate averages
the preceding completed 15-minute ranges through the bar before the decision.

The existing execution engine operates on each minute. A market entry takes
the next open, and the bracket is active on that minute. The stop and target
retain the breakout close as anchor, including after an opening gap. AlphaQuest
uses outward eligible ticks for off-grid thresholds and the repository's
[minute OHLC fill model](../multicharts_execution.md). Confirm off-grid prices,
limit assumptions and cases where both exits touch a minute against the actual
chart export. AlphaQuest's minute-based fill timestamps identify the minute
containing execution by its close label.

`FlatTime` submits a market exit for the next observed open. AlphaQuest maps
`SetExitOnClose` to the reviewed NQ/MNQ session close, including early closes,
after any active price exit on the closing minute. A missing close with live
exposure or a truncated held position rejects the run. The backtest report
records the calendar and its coverage. Custom regular-session backtests can
use `use_session_calendar=false` and an explicit `chart_session_close` in
Eastern time if they need a different chart template. The fixed clock applies
the same close every session. Controlled account replay and execution decision
capture are unsupported for this strategy.

## Install and review in MultiCharts .NET

1. In PowerLanguage .NET Editor, create a new C# signal named
   `OFB_OvernightBiasORB_Signal`, paste the complete C# file and compile it.
2. Apply it to one **15-minute NQ Globex** chart series. Set **MaxBarsBack** to
   **250**, leave **IOG off**, and enable **Bar Magnifier → Intraday → 1 Minute**.
   Verify that the first RTH candle reads 09:45 on an Eastern chart. Load
   matching data, dates and costs. [C# signal guide](https://www.multicharts.com/trading-software/index.php?title=How_to_Create_a_.NET_Strategy), [Bar Magnifier guide](https://www.multicharts.com/trading-software/index.php?title=Bar_Magnifier)
3. Set `showValidation=true` and recalculate. The **Output** window shows
   breakout eligibility, direction, prior OR EMA and band, ADX, exhaustion
   range, RTH ATR, submission count, submitted prices and position changes.
   Blue segments mark the completed OR, red and green show the submitted
   stop and target, and chart text marks entry/flatten submissions and observed
   position changes. The latest bar also shows the current gate values.
4. Read the native trade markers or trade export for fill price, time and
   exit order name. The `-FB` names identify the fill-bar orders. The suffix-free
   bracket names identify reissued orders. `XL`/`XS` identify next-open market
   exits, and the native session exit follows the chart session template.
   An increase in closed trades while both observed positions are flat can
   identify a fill-bar round trip.
5. Export the trade lists from the PowerLanguage and .NET charts and compare
   each entry and exit with the AlphaQuest export. In particular, review opening
   gaps, both exits touched within a minute, scheduled early closes, and any
   entry submitted on a chart session's last bar. Align by the observed minute
   or enclosing signal candle as appropriate.

`showValidation` defaults off. The signal retains up to 60 recent annotation
objects and one latest-bar panel while enabled. It uses the platform ADX and
explicit stop/limit orders at the submitted absolute levels, with a native
chart-session exit via `GenerateExitOnClose()`.
[MultiCharts .NET programming guide](https://download.multicharts.com/downloads/MultiCharts.NET-ProgrammingGuide-v1.1.pdf)

## Reproduce the local verification

Generate the labeled synthetic source from the test fixture.

```sh
PYTHONPATH=tests .venv/bin/python -c 'from pathlib import Path; from test_overnight_bias_orb import product_fixture; Path("/tmp/synthetic-overnight-orb.csv").write_bytes(product_fixture()[0])'
```

Import as NQ in `America/New_York`, tick size 0.25 and point value USD 20.
Use capital USD 10,000, zero commission and zero slippage. Use IS
**2026-02-23 through 2026-03-27** and OOS **2026-03-30**. The expected IS result
is one long trade on March 27, signal close 122 at 10:00 ET, next open 124 in
the minute stamped 10:01, and target fill 140 in that minute. The prior RTH ATR
is 20, so the stop is 116 and the target is 140. Expected net P&L is USD 320.
The mechanics checklist remains pending human comparison.
[Saved Trades CSV](../evidence/overnight-bias-orb/trades.csv),
[Saved mechanics review](../evidence/overnight-bias-orb/mechanic-review.json).

Run the focused checks from the checkout.

```sh
.venv/bin/pytest -q tests/test_overnight_bias_orb.py tests/test_strategy_sizing_contract.py
ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/pytest -q tests/test_campaign_mechanics_browser.py::test_overnight_bias_orb_default_mechanics_and_downloads
pwsh -NoProfile -Command 'Add-Type -Path @("tests/multicharts_orb_validation/HostDoubles.cs","multicharts/OFB_OvernightBiasORB_Signal.cs","tests/multicharts_overnight_bias_orb/Program.cs"); [OvernightBiasOrbHostChecks]::Run()'
```

The C# check compiles the full signal against local host doubles and verifies
orders and validation output for both directions. Installed MultiCharts
compilation and trade-for-trade parity require matching native exports.
