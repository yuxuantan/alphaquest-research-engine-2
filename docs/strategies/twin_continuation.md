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

## Current minute-bar execution — 2026-11-16 (v6)

[MultiCharts execution contract](../multicharts_execution.md) is now authoritative
for new AQ minute-bar fills: nearest extreme first, Low first on ties, continuous
order-level crossings and protection only on the post-entry path. Both BO OCO
parents compete in that path order. Immediate protection stays enabled by default.
The report compares two full continuous-path diagnostics (High first / Low first),
replacing the v5 priority matrix. Native C# stop/target distances are explicitly
rounded outward to ticks to match AQ. The original PowerLanguage source and older
results below remain historical; this is not a claim of installed-host parity.

## Historical OCO entry priority and diagnostic isolation — 2026-11-15 (v5)

The v5 AlphaQuest model keeps immediate protection and stop-first uncertain exits.
It also resolves two-sided OCO entry ambiguity with a **fixed upper-entry-first**
assumption in the primary calculation: when the Open does not determine a winner
and both entry stops touch, choose the upper buy-stop and cancel the lower
sell-stop. Opening fills retain priority over all intrabar assumptions. This
entry choice is declared before replay and never selected using P&L. An upper
entry is not inherently more conservative than a lower entry.

The primary plus three complete strategy replays form this fixed matrix:

| Role | Both entry stops touched | Uncertain protection after entry |
| --- | --- | --- |
| Primary, used for screening | Upper entry first | Stop first |
| Diagnostic | Upper entry first | Favorable first |
| Diagnostic | Lower entry first | Stop first |
| Diagnostic | Lower entry first | Favorable first |

These are priorities between entry thresholds, not a fabricated monotone
Open/High/Low/Close path. Once one OCO threshold is assumed first, the opposite
threshold cannot have occurred before it. Consequently the adverse extreme is
post-entry in that case: a stop-only touch cannot be discarded as pre-entry even
in a favorable diagnostic. If stop and target are both possible after entry,
the declared protection assumption resolves that remaining uncertainty.

Each replay has independent strategy/account state on the exact selected bars
with identical costs; later signals and trade counts can diverge. The report
shows per-scenario status, net profit, drawdown, trades, protection/OCO ambiguity
counts and net difference from the primary. Expand **Evidence and downloads**
for primary and scenario OCO CSVs showing bar time/OHLC, both trigger prices,
chosen parent and cancelled side, alongside protection and trade evidence.
The same primary policy applies to extra-slippage screening. Diagnostic profit
does not rescue a failed primary or choose a replacement in IS/OOS.

A model/data limitation in a diagnostic now saves **inconclusive** sensitivity,
its exception type, reason and failed bar/time. Its summary and comparison are
null; no zero profit or partial report is substituted. Other completed scenarios
and the independently valid primary remain durable. Primary source/holding gaps
still reject. Cancellation, I/O and implementation/reporting failures propagate;
they are never relabelled as inconclusive market evidence. Existing workers,
publication and catalogue own all work, with no diagnostic result jobs or store.

The `entry-protection-ohlc-sensitivity-v2` evidence participates in existing
cache/deletion and integrity checks. Historical v1 reports and files remain
readable without requiring OCO files or modifying their verdicts. New numerical
and strategy source identities require a new mechanics workflow; old approvals
and failed jobs remain historical. Legacy delayed protection still rejects
ambiguous two-sided entries. Generic strategies still reject unless they
explicitly declare a supported OCO priority. No tick/broker/platform parity or
whole-strategy profit bounds are claimed. Four full replays replace v4's two;
the requested grid and normal source/cost evidence remain intact.

Reproduce the normal synthetic mechanics -> IS Broad -> durable report journey:

```sh
PYTHONPATH=.:tests ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/python \
  tests/review_entry_protection.py --oco --output artifacts/twin-oco-sensitivity-NEW
```

The source deliberately crosses buy-stop 110 and sell-stop 90 in the same bar.
The primary cap-enabled long fills 110.25, stops at reference 108 and fills
107.75: `(107.75 - 110.25) * 20 - 2 = -52`. The extra-slippage primary is -57.
Upper-first favorable exits earn 338; lower-first stop-first loses 52 and
lower-first favorable earns 338, all after costs. Every scenario records one
OCO ambiguity. The uncapped primary is -412. These independent fixture values
belong to a labeled 3-day example that fails campaign evidence minima.

The same review also saves a second ordinary backtest where an adverse entry
stop exits safely at -47, but favorable holds would cross a missing scheduled
session-close price. Those diagnostics are inconclusive; the primary completes,
and no close price or diagnostic P&L is invented. The worker regression exercises
this condition inside IS Broad's cost-stress pass as well. Temporary review
servers stop on exit. Earlier evidence directories remain unchanged.

Saved normal-product evidence is in
`artifacts/twin-oco-sensitivity-qualified-20261115/verification.json`, with
source CSVs, report/download JSON and screenshots of complete and inconclusive
sensitivity. To reopen that isolated library:

```sh
ALPHAQUEST_DATA_DIR=artifacts/twin-oco-sensitivity-qualified-20261115 \
  .venv/bin/uvicorn alphaquest.app:app --host 127.0.0.1 --port 8019
```

Open `http://127.0.0.1:8019/#campaigns/workflows/8ca6f38346944fbba31d9c168d8910e5/is_broad`
for the completed two-member grid, then
`http://127.0.0.1:8019/#backtests/report/a6303ff35d0444e2a39abb1437a4c90a`
for the four-model table and its OCO CSVs. The independent diagnostic-gap example
is `http://127.0.0.1:8019/#backtests/report/1e9734015d924de4b67c8c96c15b8e82`:
expect primary -47, two inconclusive favorable scenarios with missing-close
reasons, one completed lower/stop-first diagnostic, and unavailable comparisons
for incomplete scenarios. Reopening performs no replay. Stop with Ctrl-C.

Focused checks are `tests/test_entry_oco_sensitivity.py` and
`tests/test_entry_protection_sensitivity.py`; they cover independent OCO/cost
arithmetic, opening priority, forced post-entry stops, generic/legacy rejection,
unchanged source bytes, diagnostic-only and primary failures, cancellation,
historical v1 evidence, cache/download tamper checks and the real IS Broad
cost-stress owner. The affected browser journeys are
`tests/test_campaign_broad_browser.py::test_twin_conservative_entry_sensitivity_report`
and `tests/test_campaign_broad_browser.py::test_twin_oco_entry_priorities_and_inconclusive_diagnostics`.

The actual failure was also rechecked on a verified private copy of job
`bec2ce0ceddb43cbb424948a0b819c7e`, trial 1's 2021–2024 IS source and original
extra-slippage settings (1 tick, 1.99 commission per side). All 1,415,817 selected
bars completed under all four models. The primary captured 2 OCO entry
ambiguities and 19 protection ambiguities. Saved qualification outputs are
`artifacts/twin-oco-real-trial1-20261115/verification.json` and its `report/`
directory, including all scenario trades, checksums and OCO/protection CSVs.
Their trade counts, net P&L and commissions independently reconcile to the saved
CSV sums. The primary net is 88,654.24; upper/favorable is 117,094.24,
lower/stop-first 88,654.24 and lower/favorable 118,884.24. These are retrospective
model results, not observed tick execution or forward forecasts. This isolated
check used the normal report/execution owners without publishing into the user's
catalogue; the original failed 2/36 job remains unchanged. It did not execute OOS
or rerun the full 36-member grid, and does not establish a campaign verdict.

## Entry-bar OHLC policy and sensitivity — 2026-11-15 (historical v4)

The current v5 contract above supersedes this original v4 OCO rejection and
mandatory diagnostic completion behavior for new reports.

Immediate protection remains the default. AlphaQuest v4 resolves uncertain
post-stop-entry protection with the explicit `adverse_first` assumption: if a
stop could have been touched after entry, assume that stop occurs first. The
ordinary engine applies the stop fill, configured slippage and commissions.
It never fills at the earlier Open for an intrabar entry. Unambiguous exits,
Open-entry brackets and later held-bar stop-first behavior retain their rules.
Ambiguous two-sided OCO entries still reject; this policy does not decide which
entry happened. Calendar/source gaps and unsupported native capture still reject.

Every new immediate-protection report includes a second **complete strategy
replay**, with identical selected bars, parameters and costs, under
`favorable_first` entry-bar assumptions. An eligible target wins a stop/target
conflict; a stop-only touch whose post-entry timing is unknown is treated as
pre-entry, leaving the position open. A stop forced by the Close with no reached
target still executes. Each replay has a fresh strategy and actual position
state: changed exits can change later entries, trade counts and P&L.

The saved report shows both net profits, drawdowns, trade counts, ambiguous-entry
counts and favorable-minus-conservative net P&L. Expand **Evidence and downloads**
for checksummed ambiguity CSVs (bar OHLC, entry, bracket, chosen assumption and
modeled outcome), the favorable report/trades/equity/risk, and the sensitivity
JSON. The net P&L attached to assumed same-bar exits already includes costs; its
sum is not the whole-strategy impact. The comparison comes from full replays.
Large differences require investigation; no arbitrary sensitivity threshold or
new acceptance criterion is imposed. Screening and its extra-slippage run use
only their own conservative results. Favorable results never replace an IS/OOS
configuration or rescue a failed screening decision.
Each ordinary and cost-stress backtest adds one complete diagnostic replay;
grid computation increases accordingly. Source spools and ambiguity CSVs stream
with bounded memory; evidence publishes atomically with its parent report and
participates in existing reuse/integrity checks. Cancellation retains no completed
report for that attempt.

These scenarios cannot determine the actual intrabar sequence, bound whole-strategy
profitability or establish MultiCharts/broker parity. Excursions remain OHLC
bounds. Full intrabar certainty requires additional ordered market observations.
This AlphaQuest assumption does not change the MultiCharts host's own fill model.

The execution/source identities change. Old reports, verdicts and snapshots remain
readable without mutation; old mechanics approval does not authorize the new model.
Create a new workflow, rerun and review mechanics, then launch IS Broad with
**Immediate protection = true**. The previous failed job remains historical.
The original delayed mode remains available explicitly; generic `EntryProtection`
defaults to rejection unless its plan declares a policy.

Reproduce a normal-product synthetic demonstration (temporary server stops on
exit; output must be a new directory):

```sh
PYTHONPATH=.:tests ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/python \
  tests/review_entry_protection.py --output artifacts/twin-entry-protection-NEW
```

The normal mechanics -> IS Broad -> report journey runs two settings of the stop cap
on a labeled synthetic NQ source. The cap-enabled member has one ambiguous entry:
entry 110.25, stop reference 108.00, stop fill 107.75, $20/point and $2 commission
produce **-52.00**. Extra-slippage stress produces **-57.00**. Favorable target
127.25 produces **338.00**, a **390.00** sensitivity difference. The 3-day source
fails historical evidence requirements; this demonstration claims no qualified
campaign, OOS result or MultiCharts parity. Saved evidence is described below.

Saved normal-product evidence:
`artifacts/twin-entry-protection-qualified-20261115/verification.json`, with
source CSV, job/workflow/results JSON, downloads and browser screenshots. Its
temporary review server shut down after verification. To inspect that isolated
library, start an unused local port:

```sh
ALPHAQUEST_DATA_DIR=artifacts/twin-entry-protection-qualified-20261115 \
  .venv/bin/uvicorn alphaquest.app:app --host 127.0.0.1 --port 8019
```

Open `http://127.0.0.1:8019/#campaigns/workflows/21332f5efab147018d92f9d57d68b32e/is_broad`
to see both completed trials. Open
`http://127.0.0.1:8019/#backtests/report/da8110346d7943b4baff326f9aa8e678`
to inspect the cap-enabled member, its one modeled ambiguity and the -52/338
comparison. Expand **Evidence and downloads**, inspect both trade CSVs and
the JSON provenance, then reload; the report bytes and results stay unchanged.
Stop the inspection server with Ctrl-C. No OOS was executed. Existing user
datasets, workflows and historical reports were not altered by the demonstration.

Focused regression coverage:

```sh
.venv/bin/python -m pytest tests/test_entry_protection_sensitivity.py \
  tests/test_twin_immediate_protection.py -q
ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/python -m pytest \
  tests/test_campaign_broad_browser.py::test_twin_conservative_entry_sensitivity_report -q
```

Tests retain generic rejection, long/short symmetry, the reported real price
example, certain-stop and uncertain stop-only cases, unchanged legacy timing,
later strategy-state divergence, compact/full replay parity, zero-ambiguity
reports, cancellation, tamper rejection, and actual two-worker Broad cost-stress
screening. Old shared execution, risk and native decision checks remain intact.

## Fill-activated protection introduced — 2026-11-09 (historical v3 rejection policy)

The rejection behavior in this dated section records the earlier model. The
2026-11-15 policy above supersedes it for newly generated AlphaQuest reports.

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
