# MultiCharts-compatible minute-bar execution

Implemented 2026-11-16. Current model: `multicharts-ohlc-nearest-extreme-v1`.
This contract supersedes earlier AQ stop-first/upper-entry-first assumptions for
**new** OHLC backtests. Saved results, policy confirmations and supplied original
strategy sources remain unchanged. Existing tick execution remains available;
this increment does not add tick ingestion or storage work.

## Price path and activation

For a completed minute with Open O, High H, Low L and Close C:

| Condition | Assumed chronological path |
| --- | --- |
| H − O < O − L | O → H → L → C |
| H − O ≥ O − L (including ties) | O → L → H → C |

Every valid price increment between the vertices is traversed. AQ computes
segment crossings without allocating synthetic tick arrays. It does not jump
from Open directly to High/Low when an intermediate stop is active. The Open is
observed first; there is no interpolation across an overnight/missing-bar gap.
This is MultiCharts' documented **non-magnified backtest assumption**, not proof
of the historical order of trades. See [Intra-bar Price Movement Assumptions](https://www.multicharts.com/trading-software/index.php?title=Intra-bar_Price_Movement_Assumptions)
and [.NET Price Movement Emulation](https://www.multicharts.com/trading-software/index.php?title=Price_Movement_Emulation_within_the_Bar_at_Backtest_and_Optimization).

Both strategies calculate their signals once on the completed minute. Pending
next-bar market orders execute at the following observed Open; stop entries fill
at their first eligible crossing, or at Open on a gap beyond the trigger. A pair
of OCO entry stops chooses the first crossing along this path and cancels its
sibling immediately. Overlapping thresholds that trigger simultaneously reject.
Entry slippage affects the fill and fill-relative exits, not the assumed market
path. Orders generated at a bar's Close cannot trade that bar's earlier extrema.

An already active bracket fills its first eligible stop or target along the path.
A target may therefore fill before a stop even if both fall inside the same bar.
A stop gap fills at Open with adverse configured slippage. A limit gap improves
to Open by default. Default limit penetration is zero (touch or better); an
explicit penetration stress fills at the first eligible modeled price beyond
the limit. The optional no-improvement stress fills opening targets at their
submitted limit. Limits receive no adverse market slippage. These stress settings
must match the comparison setup; they do not model queues, depth or partial fills.
See [Limit Order Execution Assumptions](https://www.multicharts.com/trading-software/index.php?title=Limit_Order_Execution_Assumptions).

## Strategy-specific protection

**Twin Continuation:** `immediate_protection=true` in AQ and
`ImmediateProtection=true` in the maintained C# signal. Protection is prepared
before parent submission and activates on fill, including the remainder of its
entry bar. BO keeps its frozen opposite swing stop, optional frozen-ATR stop cap
and frozen-ATR target. MO uses its fill-relative stop distance. Absolute stops
round outward adversely; distance stops/targets round outward to a whole tick.
C# explicitly rounds native special-order distances upward before conversion to
per-contract currency. Its shared order router selects the active BO/MO owner and
prioritizes an explicit same-close exit, then next-Open exit, over fresh brackets;
inactive setup exits are not submitted. No fresh special SL/TP is generated when
an explicit closing action replaces the next-bar bracket. Exit orders bind to their named BO/MO parent. SL/TP do not
inspect a Low or High visited before entry. The normal bar-close strategy callback
is not called a second time at fill. A same-bar round trip consumes one trade.
`false` retains delayed protection timing; it still uses the new MC price path.
The original supplied PowerLanguage file is a historical delayed-protection
reference, not the maintained immediate-protection implementation.

**ORB/VWAP:** preserve its existing timing: market entry next Open; the strategy
observes the position at that minute's Close and then submits next-bar protection.
This change does not add immediate brackets to VWAP or change its sizing, ADX,
VWAP, retest/pivot logic or calendar exits.

Example: O=100, H=130, L=85, C=115; buy stop=110, attached SL=90,
fill-relative TP distance=10, zero costs. Low is nearer Open, so the path is
100→85→130→115. Entry occurs at 110 **after** 85. Target fills at 120;
90 cannot stop the position before entry. Profit is10 points. For a held long
with SL 95/TP 105, O100/H108/L85, High is nearer: TP 105 fills before Low 85.
At O100/H110/L90, the tie visits Low first: SL 95 fills first.

## Risk, prop simulation and sensitivity

`execution.py` owns all fills and money. Ordinary orders, attached exits and
native percentage-risk account/daily floors use the same crossing function.
Provider floors compete with strategy orders in chronological modeled order;
a later floor crossing cannot undo an earlier target fill. Costs are charged
once. Held risk uses only the path between activation and exit; it excludes
pre-entry extremes and prices beyond the exit. MAE/MFE are **model estimates**,
not observed tick excursions. The risk artifact identifies
`held-price-path-equity-v2`. Existing fixed-source prop simulations consume their
sealed source's saved fills/risk; they do not silently recompute old trades.
New native strategy/account replays use the changed execution owner. Historical
MC resampling does not recover the original intrabar chronology.

Twin reports save the primary model and two complete independent strategy
replays: always O→H→L→C, and always O→L→H→C. Each replay follows the entire path,
including its own later fills, positions and decisions. These are diagnostics,
not performance bounds or alternative candidates to select after seeing profit.
A diagnostic model/data failure is inconclusive; no missing total is fabricated.
Old v1/v2 sensitivity evidence remains readable with its original labels/files.
New reports use `entry-protection-multicharts-path-sensitivity-v3`.

If a source already has observed ordered trades, its tick window takes priority
over OHLC emulation. Strategies still see completed minutes. Actual tick input is
not synthesized by this model and its chronology is not changed by diagnostics.

## Matching MultiCharts configuration

Use the maintained C# signal in `multicharts/`, not a preserved supplied source.
For the reference comparison set:

- One-minute Data1, identical symbol/contract/roll policy, history and warmup.
- Chicago exchange time; close-labelled bars; matching 24-hour CME session
  template and shortened-session calendar. AQ `clock_shift=0` matches this chart.
- IOG **off** (also declared by the signals); Bar Magnifier **off**. IOG by itself
  does not supply observed tick chronology. Magnified/live results have a different
  information set and are outside this OHLC equivalence claim.
- Twin manual Maximum Bars Back 5 (or the same explicit AQ value), no pyramiding,
  matching Inputs, immediate protection on in both places by default.
- Identical instrument minimum tick, point value, quantity, per-side commission,
  adverse slippage and limit-touch/penetration settings. NQ and MNQ are distinct
  contracts; no automatic ten-for-one conversion is implied.
- Match session exit semantics: Twin same-close session exit; VWAP its existing
  next-Open cutoff exit. Missing liquidation bars reject in AQ instead of making
  up a session-close price. End-of-data liquidation remains explicitly labeled.

See [Calculation per Bar](https://www.multicharts.com/trading-software/index.php?title=4.6.6_Calculation_per_Bar)
and [Bar Magnifier](https://www.multicharts.com/trading-software/index.php?title=Bar_Magnifier).

## Verification and limits of the claim

`tests/test_multicharts_execution.py` independently expands small integer-price
bars into every traversed price and verifies OCO ownership, same-bar protection,
cash, risk and provider-floor competition. Focused execution, Twin, scenario,
native-controller and real-tick regressions cover the integration.

`tests/review_twin_csharp.py` compiles the delivered C#5-compatible decision core,
compares indicator/state/order streams and independently runs C#-driven decisions
through the sole AQ execution owner. It also checks native protection plans and
fractional-tick normalization. Inputs, emitted decisions, full event outputs and
verification summaries are saved for inspection. Python Decimal versus C# double
indicator values use an explicit numeric tolerance; actual selected fixture
orders/fills/cash/risk must match exactly.

This proves the tested code contracts and the documented modeled fills. It is
**not installed-MultiCharts certification**: its SDK, licensed host, proprietary
native special-order engine and a fresh matching immediate-protection export are
not available in this macOS checkout. An installed-platform comparison must use
the settings above and compare trades (parent, side, quantity, bar, price, costs,
exit reason) on the same data. Local host doubles do not establish native fill
parity or live brokerage behavior. Earlier delayed-only exports cannot qualify
new immediate-protection results.

Run the core review with:

```sh
PYTHONPATH=.:tests .venv/bin/python tests/review_twin_csharp.py \
  --dotnet /path/to/dotnet --output /tmp/aq-multicharts-core-review
```

Run the normal-product synthetic campaign/report review with:

```sh
PYTHONPATH=.:tests ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/python \
  tests/review_entry_protection.py --output /tmp/aq-multicharts-product-review
```

Both use isolated sources. The product review shuts down its temporary server.
Numerical/source identities change for new runs. Old sealed reports are preserved;
existing freezes are not relabeled compatible and require a new workflow when
current source guards reject them.


## Saved delivery evidence

[`artifacts/multicharts-ohlc-20261116`](../artifacts/multicharts-ohlc-20261116/README.md)
contains the synthetic normal-product reports, CSV downloads, browser captures,
C# decision inputs/outputs, exact replay events and checksum manifest. The compiled
core review covers 18,923 completed-bar observations across 11 cases and 18
independent full replays. The product example's capped OCO row has primary
-52.00, High-first 338.00, Low-first -52.00 and extra-slippage primary -57.00.
All amounts use the fixture's 20 per point, one contract, one tick of adverse
slippage and 1.00 per contract per side. These are synthetic model outputs.

Relevant focused checks pass; the two older VWAP tests for the original parameter
count and an exact CLI artifact file list also fail on the unchanged base commit
(the newer order-flow Inputs and `risk_metrics.json` predate this work). They
remain outside this change; no full-suite or installed-MultiCharts pass is claimed.
