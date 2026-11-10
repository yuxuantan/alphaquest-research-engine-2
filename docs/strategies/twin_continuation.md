# Twin Continuation — AlphaQuest and MultiCharts .NET

The supplied PowerLanguage signal is preserved byte for byte in
[`twin_continuation.pl`](twin_continuation.pl), SHA-256
`b4a6c1cdd82f12c27e703d94a01ba5f0c9e8b69541dc4b7529ca60bdde8a1861`.

| Platform | Source / selection |
| --- | --- |
| AlphaQuest Python | [`twin_continuation.py`](../../alphaquest/strategies/twin_continuation.py), strategy ID `twin_continuation`; **Twin continuation** in Backtests |
| MultiCharts .NET | Entire [`Twin_Continuation.cs`](../../multicharts/Twin_Continuation.cs), signal class `Twin_Continuation` |

For visual inspection directly from the signal, enable `ShowTradeValidation`.
The [chart validation guide](#chart-trade-validation) covers swing levels,
Momentum gates, entry submissions and observed positions. The separate Momentum
indicator is superseded and removed; earlier saved evidence remains unchanged.

The Python strategy is registered for the existing UI, API, CLI and parameter
grids. It uses the shared execution engine and ordinary saved reports, risk CSVs,
charts and downloads. All 27 source Inputs are available as snake_case parameters
with the source defaults. Examples: `BO_ATRPeriod` → `bo_atr_period`,
`BO_PivotTF` → `bo_pivot_tf`, `MO_FullBarsOnly` → `mo_full_bars_only`.
Python adds `immediate_protection=true`, `max_bars_back=5` and
`use_session_calendar=true`. The new protection mode is also exposed as
`ImmediateProtection=true` in C#. The Max Bars Back parameter skips
the leading five source records before state calculation, matching the source's
manual chart setting. The calendar option implements MC's platform-managed session close
locally, including scheduled early closes. The C# host uses
the chart's Maximum Bars Back; do not additionally skip records in that host.

## Data and installation

Use NQ or MNQ full-session **one-minute, close-labelled bars**, Data1 only,
Chicago session 17:00–16:00. Load the same leading history on both platforms;
the source recommends at least six months. Python converts the saved source
timezone through UTC to `America/Chicago`, including DST. Set the MultiCharts
chart timezone to Chicago/exchange time. The .NET code interprets `Bars.Time`
as that wall clock and verifies the one-minute chart resolution.

In PowerLanguage .NET Editor, create a new **Signal**, name it
`Twin_Continuation`, and replace its contents with the entire `.cs` file,
including `AlphaQuest.Twin`. Compile with the installed MultiCharts SDK.
Use IOG off (also declared in the code), no multiple entries/pyramiding,
Maximum Bars Back **5**, and the source session template. No DLL, Data2 or
external engine is used. `AQ_TWIN_CORE_ONLY` is a standalone test define;
do not define it in MultiCharts. `StartCalc` resets the full state on recalculation.

For AlphaQuest, save tick size and point value with the dataset: NQ 0.25 and
20 currency units per point; MNQ 0.25 and 2. `qty=1` means one contract of that
saved instrument. Switching symbols does not automatically convert one NQ to ten
MNQ. The known regular dataset interval must be 60 seconds. Irregular sources
can have missing minute bars; metadata alone cannot distinguish them from a
coarser irregular aggregation. Confirm the original bar construction yourself.
Minute alignment and subminute spacing are checked during replay.

AQ datasets are already close-labelled: normally leave `clock_shift=0`.
The source's `ClockShift=1` accommodates an open-stamped MultiCharts chart.
ClockShift affects intraday HHMM only; both ports deliberately keep the source
calendar date unshifted, including when the shifted clock crosses midnight.
Do not use ClockShift as a timezone conversion.

Configure costs separately in each platform. The signal does not hardcode its
header's research costs. AQ commission is per contract **per side**, and adverse
slippage is an integer number of ticks per market/stop fill; limit exits have no
adverse slippage. A $5 round-trip commission is 2.50 per side. The header's
$1 round-trip NQ slippage is not representable by AQ's integer 0.25-point ticks
($5 per NQ tick). Match an explicitly representable fill-cost setup for platform
comparison; the examples below use one tick each side and 1 commission each side.

## Fill-activated protection — 2026-11-09

**Immediate SL/TP is now the default in both implementations.** Set
`ImmediateProtection=true` in MultiCharts and `immediate_protection=true` in
AlphaQuest. Entry decisions and indicator updates still run on completed bars;
protection is prepared before the parent fills. No full trading-core IOG replay
is enabled. Set the option **false** on both platforms to reproduce the supplied
signal's delayed, following-bar protection. Earlier exits can change later
flat/arming gates and trade counts, as well as exit prices. This is an execution-model change,
not a claim that the original PowerLanguage already protected its entry bar.

- **BO:** a conditional absolute opposite-swing stop is bound to each eligible
  parent (`BO-L` or `BO-S`). A native per-contract ProfitTarget is prepared from
  frozen ATR × target multiplier, converted through the symbol's BigPointValue.
  It calculates the target from the actual entry fill. If enabled, a native
  StopLoss distance cap also uses frozen ATR; the tighter absolute/cap exit
  applies. Target multiplier 0 disables TP. With cap 0 the absolute swing stop
  still protects the entry. An enabled ATR target/cap requires positive frozen
  ATR; zero ATR rejects in immediate mode rather than silently disabling a leg.
  Stop ticks round adversely; target ticks round
  favourably, matching the documented native special-order rules.
- **MO:** a native per-contract StopLoss is prepared from `MO_StopPoints` before
  its next-Open market entry. MO has no profit target and does not inherit BO's
  target. Native exits are renewed while pending/held. Setup ownership is tracked
  from the pending parent; an unidentified held setup rejects.
- **Python:** each entry carries an immutable, precommitted `EntryProtection`.
  The shared engine resolves its bracket from the actual fill without invoking
  `on_bar` again. A fill notification updates setup ownership so an entry and exit
  inside one minute still increments completed trades exactly once. Other
  strategies without an attached plan retain their existing execution behavior.

For market/Open entries the remaining bar range is after entry; SL/TP conflicts
use the existing declared stop-first assumption. For intrabar stop entries the
adverse extreme may have occurred before entry. The engine accepts outcomes
whose order is established under its OHLC price-level fill convention, but
**rejects** uncertain post-entry stop timing or SL-versus-TP order. It does not
silently reuse the whole entry-bar range as a measured post-entry path or revert
to delayed protection. This one-minute strategy does not add a tick/bar-magnifier
feed; resolving rejected cases requires a separate finer-grained execution
integration. Disabling immediate protection explicitly selects the legacy model.
No tick sequence, liquidity or broker fill price is claimed from minute OHLC.

Intratrade bounds for a same-bar exit exclude the later Close and prices beyond
its exit. They remain labelled OHLC bounds, not measured MAE/MFE. Same-bar entry
and exit timestamps can have the same close label and a reported holding time of
0 minutes; that is bar-label precision, not an assertion of zero elapsed ticks.
Captured decision evidence and phase-controlled native execution are not extended
to attached plans by this change; unsupported requests reject.

The earlier **499/499 MC match / 165005 CU** record below qualifies the original
**delayed** mode only. Existing reports, source exports and evidence remain
unchanged. New reports save the selected protection flag, source hashes and
`session_flattening.protection_activation` (`on_entry_fill` or
`following_bar_legacy`). Changed-code detailed replays/frozen launches fail
closed under the existing identity checks; saved reports still reopen normally.
The immediate C# host needs compilation and a fresh trade export in the installed
Windows MultiCharts SDK before numerical/platform parity can be claimed. Native
markers can be named Profit Target / Stop Loss rather than BO-ST / MO-LS; the
commentary labels its original-order values as calculated candidates.

For the supplied trade 216, the execution-only fixture uses its actual bars and
frozen ATR: the new OHLC model exits at **10714.75 in the entry bar** (1050 gross
at zero costs), whereas the delayed model exits next Open at **10551.50** (4315
gross). These are model comparisons, not a newly measured immediate MC result.

Reproduce the saved normal-product examples with:

```sh
PYTHONPATH=.:tests .venv/bin/python tests/review_twin_immediate_protection.py \
  --output artifacts/twin-immediate-product-NEW
```

The script starts an isolated temporary existing-product server, verifies the
form's true default and help, creates ordinary saved IS backtests, inspects report
pages/downloads, reloads unchanged reports, checks an ambiguity rejection, then
stops the server. Sources are explicitly synthetic; appended reserved OOS rows
are not backtested. Saved demonstration:
`artifacts/twin-immediate-product-qualified-20261109/verification.json`, with the
normal library, report/risk/trade downloads and screenshots alongside it.

| Synthetic case | Mode | Entry / exit bar | Net CU |
| --- | --- | --- | --- |
| MO long, adverse entry-bar Low | legacy | 26 / 28 | +148 |
| Same MO inputs | immediate | 26 / 26 | -1507 |
| BO long, entry-bar target reached | legacy | 106 / 107 | +318 |
| Same BO inputs | immediate | 106 / 106 | +318 |

Independent costs: 1 contract, 20 CU/point, 0.25 tick, 1 adverse tick per
market/stop fill and 1 CU per side. MO immediate fills 112.25, stops at 37.25
and exits at 37.00: -75.25 × 20 - 2 = **-1507**. BO fills 110.25, uses frozen
ATR 8 and TP distance 16, exits at 126.25: 16 × 20 - 2 = **318**. A tight-cap
ambiguous entry bar returns HTTP 422 with no completed report for that attempt.
These fixture expectations live in tests; they are not future profitability
forecasts or production dashboards.

To inspect the saved demonstration manually, start an unused local port using
its normal library, then stop it with Ctrl-C after inspection:

```sh
ALPHAQUEST_DATA_DIR=artifacts/twin-immediate-product-qualified-20261109 \
  .venv/bin/uvicorn alphaquest.app:app --host 127.0.0.1 --port 8019
```

Open `http://127.0.0.1:8019/#backtests/report/cb95bab042764731abf67b9d2a27fa0b`
for the MO immediate example, or
`http://127.0.0.1:8019/#backtests/report/b8cee5445c3e4e2d9a5bc11b896da0c5`
for BO immediate. Compare with legacy IDs `aae5b0c20a1a41bead0c30f4a9ef777f`
and `bfd77518bba24a5991afb91eb557bbfd`. These are synthetic demonstration runs,
not the user's existing library. For your actual data, restart AlphaQuest,
refresh the form, choose Twin, verify **Immediate protection=true**, and run a
new IS backtest. In MC replace the entire C# file, compile, keep IOG off and
set **ImmediateProtection=true**. Preserve/export old runs before comparison.

All **304 targeted Python checks** passed across immediate/legacy strategies,
normal APIs, shared execution, excursion bounds, native controls/decision capture
and external-source compatibility. Portable C# protection-plan and inspection
checks passed **481,383 assertions**. Portable checks and source hashes are in
`artifacts/twin-immediate-protection-review-20261109/`; the eight Python/C# core
comparison cases are in `artifacts/twin-immediate-protection-core-parity-20261109/`.
They qualify local calculations and protection plans, not native SDK rendering,
order activation, broker routing, partial-fill races or live readiness. The
implementation uses the vendor's [special-order API](https://www.multicharts.com/trading-software/index.php?title=Special_Orders)
and [pre-generated exit activation](https://www.multicharts.com/trading-software/index.php?title=Auto_Trading).

## Chart trade validation

Replace the signal with the entire updated `multicharts/Twin_Continuation.cs`
file and compile in the PowerLanguage .NET Editor. On the existing one-minute
chart, open the signal's **Format / Inputs** and set **ShowTradeValidation=true**.
This single flag controls all chart diagnostics; it defaults to **false**.
The existing `DebugLog` Input controls Output Window logging separately.
Remove the old `Twin_Momentum_Oscillator` from your chart if already installed;
no separate indicator is needed. Repository source deletion does not uninstall
a study from your Windows installation.

The price chart keeps only:

- **Red high / green low:** the latest confirmed, still-open swing levels,
  using the signal's actual `HaveSwH/L` and `SwH/LOpen` state. A level becomes
  visible when confirmation is applied at the completed 15-minute calculation,
  after three completed pivot candles to its right. It is not backdated to
  the central pivot candle. Equality counts as a touch: High >= high or
  Low <= low ends the open line. A newer confirmation replaces the older one;
  the signal does not maintain all past unbroken swings.
- **One three-line summary:** timestamp, position, BO armed/idle, open high/low
  and the latest completed Momentum oscillator/threshold. Numbers are rounded
  here for readability; the detailed inspection retains their precision.
  The gold summary sits to the left of the latest bar, above its High.
- **MultiCharts' native trade markers:** the signal adds no duplicate historical
  text labels for fills, renewed orders, crossings or closed trades.

For full inspection, in the **MultiCharts .NET main window** choose
**View → Expert Commentary**, then click a chart bar. The signal writes its full
validation snapshot into that native inspection window, using
`ExpertCommentary.AtCommentaryBar`. Select the bar preceding an entry marker
for its submitted order, and the completed entry bar for its observed position.
No detailed snapshot is painted over the price bars. This works independently
of `ValidationHistoryLimit`, so a zero history limit does not remove inspection.
The detailed snapshot includes:

- **BO:** confirmed levels/open flags, frozen direction eligibility, frozen
  entry/opposite-swing stops, frozen/current ATR and warmup, volatility ratio/cap
  and lookback, session clocks and fill cutoff, arm state/trade count, 15-minute
  OHLC, target/stop-cap multipliers and submitted bracket prices/entry ownership.
  Frozen levels can differ from current open lines. The opposite-swing stop
  need not itself remain open. An exit bound to another entry has no effect
  on the held setup because MC uses `OrderExit.FromEntry`.
- **MO:** completed bucket end and observed minutes, basis, ATR, raw and
  previous/current smoothed oscillator, trigger, crossing, warmup, window,
  full-bucket gate, flat position, daily opportunity before consumption,
  half-day heuristic, enable/direction settings, and post-calculation fire/daily
  state. The source can consume its opportunity even when Momentum or the
  crossed direction is disabled. Late bucket completion preserves its original
  end time/minute count. All crossings completed on a selected processing bar
  are included; otherwise the latest completed bucket is identified as held.
- **Execution:** current entry/exit submissions and their owners, order-change
  context, observed position/average fill, and closed-trade count changes.
  Market submissions say `price=market`, not an invented fill price.

If Expert Commentary reports **"There are no studies with commentary on this
chart"**, replace the **entire signal source** with the current file and compile,
then confirm `ShowTradeValidation=true` on the signal applied to that chart and
recalculate. The earlier adapter made its only `WriteLine` call inside a helper
guarded by `AtCommentaryBar`; that version did not register in the user's
installation. The registration revision added a direct `CalcBar` write outside the selected-bar
condition. The current adapter writes **"Twin Continuation trade validation
v3"**, followed by
full details only for the selected bar. Reopen Expert Commentary and click a
calculated bar (after Maximum Bars Back). Expected: the v3 header and that bar's
details, including **BO TP: frozen15mATR × multiplier = distancePts**. At ATR 50
and multiplier 2 this reads `distancePts=100`. With target multiplier 0 it reads
`BO TP: disabled`. The three-line price-chart summary remains unchanged.

The direct registration write follows the documented native commentary usage;
it addresses a suspected registration/discovery issue, not a runtime-verified
diagnosis of MultiCharts internals. Source/core check outputs and exact source
hashes are saved in
`artifacts/twin-signal-commentary-registration-review-20261109/`. They do not
test the installed SDK or prove successful native-window registration. If the
same message remains with the updated signal and flag enabled after a reload,
record the installed MultiCharts .NET version/build and whether the v3 header
ever appears; that platform behavior still requires Windows verification.

Repeated bar selection must not clear swing lines or advance the strategy.
The subsequent v3 adapter processes each completed chart bar once. A callback
for an already processed bar takes an early inspection-only path: it reads the
bar's recorded inputs and reconstructs its original commentary on a **private
core copy**. It returns before the live `Step`, order `Send`, session exit
call and drawing updates. Checkpoints deep-copy all three mutable core arrays.
A normal full recalculation still clears/rebuilds the chart and journal.
`[RecoverDrawings(false)]` applies the vendor's documented drawing-retention
behavior outside the ordinary bar-close pass; it does not disable explicit
cleanup during a full recalculation.

The debug journal exists only with `ShowTradeValidation=true`. It stores one
compact numeric input frame per calculated bar and a private core checkpoint
every 1,024 bars; inspection replays at most 1,024 steps on that private copy.
It does not store a full text blob/core clone per minute or submit replay orders
to MultiCharts. Long debug histories still add memory use. Native `Bars.CurrentBar`
identifies records, so repeated wall-clock timestamps do not merge bars.

After recompiling v3 and recalculating, select bar A, then B, then A again.
Expected: each commentary has the selected timestamp and its original ATR,
orders and Momentum gates; the existing lines and latest three-line summary
stay put, and the strategy's trade count does not change. The portable isolation
fixture reconstructs 130 nonsequential/repeated selections across checkpoint
boundaries and matches the original commentary exactly, with zero live-state
changes or drawing operations. Source copies/hashes and actual outputs are in
`artifacts/twin-signal-commentary-isolation-review-20261109/`; the current
Python/C# numerical comparison is in
`artifacts/twin-signal-commentary-isolation-core-parity-20261109/`.
These do not prove native window/drawing behavior in the installed Windows SDK.

If another click still clears the display, inspect the PowerLanguage .NET
Editor's **View → Output Window**. Copy any exception and the installed
MultiCharts .NET version/build. The current adapter prints
`Twin validation v3 StartCalc: full calculation reset.` at a full calculation
start with validation on. A new copy of that line on every click would identify
an additional platform-triggered full reset, distinct from an inspection-only
callback. No platform-specific root cause is claimed from the symptom alone.

`ValidationHistoryLimit` defaults to **0** and controls **completed swing segments only**:

- **0:** currently open levels only.
- **Positive integer:** retain that many completed swing segments.
- **-1:** retain every completed segment across all loaded chart history,
  with no count or age cutoff imposed by the signal. Values below -1 reject.

At 0, the signal retains at most
**two open lines and one three-line text object**. Increasing it keeps that many
completed swing segments, never more text labels. **Existing charts may retain
an earlier saved value of 200; explicitly set it to 0 for the clean view.**
No full historical text labels are created even with that earlier value.
Unlimited history can increase chart memory/rendering work. It cannot draw
before loaded data and pivot warmup: a pivot needs seven completed candles
(three on each side of its central candle), then the 15-minute activation.
Load earlier chart history and recalculate to rebuild older segments. This
option retains past closed/replaced segments for inspection; it does not change
which currently open swing or frozen stop the strategy uses for trading.
The unlimited-history check retains 1,500 completed segments and one active
segment across more than four years of fixture timestamps, then verifies that
recalculation cleanup removes them. Saved output and exact source hashes are in
`artifacts/twin-signal-unlimited-swings-review-20261109/`; prior evidence is
unchanged. This is a portable lifecycle check, not a Windows rendering benchmark.
With the main flag false, no callback, commentary, chart objects, text formatting
or additional indicator/pivot calculation runs; only cheap flag/null checks remain.
Recompile the entire updated signal and recalculate to replace the earlier
cluttered implementation. If a platform-retained old drawing remains, remove
and re-add that signal instance. The older saved evidence is preserved.
Actual Windows rendering performance has not been benchmarked.

For historical entry checks, match history/Inputs and use the native commentary
inspection above. `MO-L/S` requires a fresh eligible crossing; `BO-L/S` requires
an armed eligible frozen stop order. Compare frozen prices with MC's entry
marker and owning stop/target. An entry and exit entirely within one bar can
change closed-trade count while the observed position remains flat. Use MC's
trade list/markers for those executions. Bar-close diagnostics cannot establish
intrabar execution order or broker tick timestamps. Match chart timezone,
sessions, Maximum Bars Back, costs and fill settings. Finally switch
**ShowTradeValidation=false** and recalculate: diagnostics should disappear and
identical input/history should retain its trades.

Reproduce portable lifecycle and independent numeric checks with:

```sh
dotnet run --project tests/multicharts_twin_drawings/DrawingCheck.csproj
```

Checks compile the delivered C# 5-compatible core/lifecycle/text, not a fake SDK.
Independent fixtures confirm high 110 / low 90 after seven candles at 15 and
360 minutes (including the shortened last session candle), equality-touch
invalidation, bounded history, cleanup and no repeated drawing operations.
Momentum arithmetic expects basis 105, ATR 11 and oscillator 500/33 after two
buckets with basis length 3 / range length 1 / signal length 1; partial-bucket
checks verify actual gate text and entry instructions. Installed MultiCharts
SDK compilation and chart appearance still need verification in Windows.
The earlier full-label implementation and its actual check output/source hashes
remain in `artifacts/twin-signal-validation-review-20261109/`. That check
passed 475,631 assertions, including complete signal-state/order equality with
diagnostics enabled versus disabled across missing minutes and session changes.
The independent Python/C# core comparison also passed all six cases (18,556
observed bars); its retained inputs/outputs are in
`artifacts/twin-signal-validation-core-parity-20261109/`. These checks do not
substitute for compiling and viewing the installed MultiCharts adapter.
The adapter uses the vendor's documented [drawing API](https://www.multicharts.com/trading-software/index.php?title=Plotting_on_the_Chart)
and [last-bar data property](https://www.multicharts.com/trading-software/index.php?title=Data_Access).
Full bar inspection follows the vendor's [Expert Commentary API and menu instructions](https://www.multicharts.com/trading-software/index.php?title=Output,_Alerts_and_Expert_Commentary).

The subsequent clutter fix removes all historical text drawings, defaults swing
history to 0, and keeps one three-line summary with readable gold text. Full
precision/gates/orders move to native bar-selected Expert Commentary. Current
portable evidence is saved separately in
`artifacts/twin-signal-compact-validation-review-20261109/`: 475,638 assertions
passed, including enabled/disabled state/order equality and compact summary
checks. `verification.json` includes the actual summary and full detail text.
Expected compact example: open high **22111.25**, broken low **--**, oscillator
**-31.06** versus **+/-100**, with exactly three lines. Earlier evidence above
is unchanged. The current Python/C# comparison is saved in
`artifacts/twin-signal-compact-core-parity-20261109/`. Windows SDK compilation,
Expert Commentary interaction and chart layout remain manual qualification.

## Measured MultiCharts session and price behavior — 2026-11-09

The supplied trade export records three **End of Day Exit** trades in the saved
2021–2024 IS: BO long trade 79 on 2021-09-06 at 12:00 CT / 15701.25, BO long
trade 429 on 2024-06-19 at 12:00 / 20231, and MO short trade 436 on 2024-07-04
at 12:00 / 20381.25. These establish same-closing-bar liquidation for both setups
on those scheduled early closes. A reference workbook is used only by development
comparison scripts; production does not load it or require MultiCharts.

With `use_session_calendar=true` (default), the saved NQ/MNQ symbol resolves the
existing local closure calendar. Its reviewed scheduled close supplies the
same-close liquidation deadline. A held position closes at that actual bar's
Close, with configured market slippage/commission once. There is **no five-minute
buffer or next-Open flattening**. Pending stop/target fills on the closing bar
retain priority. Missing held closing bars or dates outside calendar coverage
reject; missing prices never create an earlier close. Regular BO/MO time exits
remain as in the source. Calendar mode supports BO session clocks 1700/1600;
custom clocks require the explicitly labelled earlier fixed-clock mode
`use_session_calendar=false`. The source Momentum half-day heuristic is retained.

Measured BO profit targets also normalize outward to tradable ticks: long sell
limits round up and short buy-to-cover limits round down. This accounted for
214 fractional-price differences after the calendar fix. The corrected
2021–2024 IS comparison matches **499/499 trades** in entry/exit times, direction,
quantity, entry/exit prices and reported trade P&L: **165005 CU**, under the
zero-commission/zero-slippage comparison. The workbook's Settings sheet was
cancelled; the reported per-trade profits equal signed price changes × 20, so
actual configured MC commission/slippage settings are not established. Alternate
Inputs, capped fractional stops, live execution and later OOS are not certified.

New reports identify `twin_csv_session_close_v2` in their session settings and
retain the calendar checksum, instrument, coverage, scheduled-close examples
and observed plan digest. Calendar/helper/strategy changes participate in the
normal source/code hashes. Existing reports and dated evidence remain readable;
incompatible frozen-package/detail replays reject rather than ignore changed
calculation code. See the [measured comparison and reproduction steps](../prop_simulation_review.md#twin-mc-session-close-parity--2026-11-09).

## Logic retained

- BO builds session-aligned 15-minute ATR bars and `bo_pivot_tf=360` swing
  candles from Data1. Seven completed candles confirm the middle candle with
  three on either side; equal highs/lows count as pivots. A late unfinished
  candle/bar finalizes before the current minute updates its new bucket.
- BO ATR seeds with the mean of the first 14 completed true ranges, then uses
  Wilder smoothing. Session volatility is the last completed session's range
  divided by the previous 50 ranges, excluding that last range. It stays zero
  until enough sessions exist. Lookback is supported from 1 through 99.
- Swing availability is consumed by touches. On each completed 15-minute bar,
  while flat, BO freezes the eligible levels, opposite-swing stop and ATR. It
  renews next-bar entry stops until disarmed or the source cutoff is reached.
  A fill or completed trade disarms the old opportunity.
- MO builds calendar-clock 10-minute buckets, a close EMA basis, Wilder range,
  normalized oscillator `(close-basis)/(3*range)*100`, and signal EMA. Only
  strict crossings of ±trigger qualify, at inclusive bucket ends 08:40–09:30.
  Full-bars-only means **10 observed records**, not an inferred complete period.
- MO's daily opportunity is consumed even when MO or the crossing direction is
  disabled. Both indicators continue updating with their setup disabled. The
  source excludes July 3, December 24, and November Fridays dated 23–29;
  this heuristic is retained and is not an official early-close calendar.
- MO market entries take priority over BO on the same completed bar. One
  position is allowed. Exits close only their owning setup. BO levels/ATR
  remain frozen while holding; MO uses the filled entry ±75 points by default.
- MO submits its timed next-bar market exit at/after 14:50 through 16:00, plus
  a same-close exit when the unshifted calendar date changes. BO uses a
  same-close exit from 15:45 through its session close. Python models the
  calendar session-close fallback (or fixed-clock fallback with calendar off); C# calls `GenerateExitOnClose()` using the
  chart session, matching the original `SetExitOnClose` instruction.

## Execution contract and limits

Market entries/exits fill the next **observed** Open. BO stop entries are active
for the next observed bar only, renewed by subsequent callbacks. Opening gaps
fill at Open; otherwise a touched entry stop fills at its level, with adverse
slippage. The first filled side cancels the sibling. If both sides touch and
the Open does not determine which filled first, AQ rejects the run rather than
invent a tick path. The original MultiCharts signal can resolve that bar under
its own fill settings; such cases need finer data for comparison.

The supplied source / `immediate_protection=false` observes a newly filled
position at its entry bar Close and starts protection on the following bar.
The current default attaches protection before entry and activates it on fill,
using the entry-bar rules above. Later held-bar brackets use Open-gap priority,
then stop first on a dual-touch bar. BO target multiplier
zero disables the limit; stop-only exits use no fabricated distant target.
BO stop-distance caps apply against actual fill price and frozen ATR. An invalid
opposite-swing stop submits the source's next-bar market exit.

If a timed exit and its stop are submitted together, AQ uses the next-Open market
exit; both already-marketable orders execute at Open under the base fill model.
Extra stop-only slippage scenarios can differ in such a tie. BO targets are
normalized outward to the execution tick grid. Immediate-mode stops also
normalize adversely to match the native special orders; legacy stop handling
retains the prior engine treatment. Python uses 50-digit Decimal indicator arithmetic;
C# uses doubles. Threshold-edge and platform fill differences still require
matched exports.

The next observed bar can follow a gap across a time cutoff, as in the original
next-bar instructions. AQ does not silently cancel those source entry orders.
Calendar-enabled holding validation rejects exposure that missed its known
session-close bar before later-session orders execute. The error displays the
scheduled close, last/next observed timestamps, selected bar and held setup/side.
The calendar supplies early closes; the port does not infer them from gaps.
With calendar off, the earlier fixed-clock rejection remains explicit.
At EOF, pending entries expire and remaining exposure explicitly
closes at the last actual Close with reason `end_of_data`, a repository terminal
policy additional to the source. All fill timestamps are the containing bar's
close label; they are not actual execution ticks.

Intrabar stop-entry bars contribute their entry and, only when still held,
their Close as known held prices. Same-bar protected exits contribute their
exit reference instead; full-bar extrema remain appropriate excursion bounds
only on the retained holding interval, since they may precede entry or follow exit. `intratrade_risk.csv` labels this `entry_phase=entry_stop`.
The ordinary prop source checker admits that phase and retains conservative
OHLC bounds and source net costs once. Measured tick MAE/MFE remain absent.
This source-admission extension participates normally in phase calculation
hashes; incompatible earlier frozen packages fail closed, and earlier saved
reports remain readable without recalculation.

Twin's OCO entry decisions are not supported by the existing single-pending
native decision sidecar. Its reports explicitly omit that sidecar. Normal
backtests, parameter grids and historical trade/risk prop analysis work;
controlled native phase replay/sizing remains unsupported. The Backtests form
states this boundary. No candidate is presented as certified for those modes.

## Reproduce and inspect

```sh
.venv/bin/python -m pytest tests/test_twin_continuation.py tests/test_twin_continuation_api.py tests/test_next_bar_execution.py -q
.venv/bin/python tests/review_twin_continuation.py --output artifacts/twin-product-NEW
.venv/bin/python tests/review_twin_csharp.py --dotnet /path/to/dotnet --output artifacts/twin-csharp-NEW
```

The product review saves clearly labelled synthetic datasets through Datasets,
selects Twin in Backtests, declares IS/OOS, runs, downloads CSV/JSON, reopens
saved reports and opens prop configuration. Single-session cases demonstrate the
normal insufficient-history rejection. A separate two-session Momentum source
checks source identity/costs, runs the normal local analysis and downloads its
report/ZIP (two trades of 148 CU; 296 CU source net). No OOS is executed. Its
owned temporary server stops on exit. The synthetic fixtures exercise mechanics;
they are not evidence of future profitability or sufficient strategy research.

The following historical expectations use **legacy delayed protection**
(`immediate_protection=false`), NQ point value 20, one tick slippage and 1
commission per side. Immediate-mode expectations and current evidence are
recorded in the fill-activated section above:

| Synthetic case | Expected observation |
| --- | --- |
| MO, basis 3 / range 1 / signal 1 / trigger 10 / warmup 2 | At 08:40 CT, basis 105 and range 11 give oscillator `500/33 > 10`. Next 08:41 Open 112 fills 112.25. Submit timed exit at 14:50; 14:51 Open 120 fills 119.75. Net `(119.75-112.25)*20-2 = 148`. Entry-bar Low 30 cannot activate an exit submitted at that bar's Close. |
| BO, pivot TF 15 / ATR period 1 / Max Bars Back 0 / MO off | Seven candles confirm swing high 110 and low 90. Final 15-minute range/ATR is 8. Next stop entry fills 110.25; target `110.25+2*8=126.25` fills on the following bar. Net `16*20-2 = 318`. Entry-bar High 130 does not retroactively fill that target. MAE bounds are 6 to 226 CU; they are not measured excursions. |
| Both entry stops touched, Open between them | Reject ambiguous OCO entry; no completed report is published. |
| Missing held configured session close | Reject missing liquidation data before an evening stop/market fill. |
| Regular five-minute source or invalid HHMM/length | Reject; do not construct one-minute buckets from unsupported data. |

Saved evidence locations and the complete journey are recorded in
[`prop_simulation_review.md`](../prop_simulation_review.md#twin-continuation-strategy-port--2026-11-09).
The C# comparison compiles the **actual delivered core**, with C# 5 syntax, and
compares 15 state fields and effective owned orders against Python on long/short
fixtures and seeded multi-session missing-minute/clock-shift probes.
It excludes only the MC host through `AQ_TWIN_CORE_ONLY`; it does not compile
against substitute SDK classes or claim to execute MultiCharts.

To reopen a saved review library:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/twin-continuation-final-20261109" \
  .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/#reports`, or use the exact backtest/analysis paths
in `verification.json`. Stop this optional server with Ctrl-C.

**Historical IS trade parity is established for the supplied export and the
reported fields above.** The workbook omits its Settings export and code/build
identity; this comparison does not certify every platform setting or live use.
Match source bytes, history, Inputs, costs and fill settings when qualifying
another run. The Windows SDK adapter was not compiled in this environment. The .NET APIs follow the vendor's
[order and FromEntry contract](https://www.multicharts.com/trading-software/index.php?title=4.6.1_Orders),
[special session-close orders](https://www.multicharts.com/trading-software/index.php?title=Special_Orders),
and [chart resolution interface](https://www.multicharts.com/trading-software/index.php?title=4.2_Data_Access).
