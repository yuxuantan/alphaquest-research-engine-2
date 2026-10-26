# Single-strategy prop simulation specification

Status: implementation specification. `alphaquest/prop/` implements strict
rules/request types, immutable profile snapshots, and the saved-source session
adapter and deterministic historical evaluation engine. Completed backtest
reports open the actual **Prop simulation** workflow, including saved setups,
source checks, evaluation execution and durable results; see [the workflow
guide](prop_simulation_review.md). Funded execution, Monte Carlo and the CLI
remain unimplemented. The standalone Prop review screen has been retired.

Reviewed on 2026-10-25 against repository commit
`32aa6ffc86a837e3f4bd20b77d46f0196165c52d`.

## 1. Objective and chosen design

Estimate how one completed strategy backtest behaves under one prop-account
profile. Show the chronological account outcome first, then distributions from
resampling the same history and optional fixed-position-size comparisons.

```text
completed backtest
  -> session adapter
  -> deterministic prop-account engine
  -> Monte Carlo / sizing analysis
  -> saved results
  -> portal
```

Historical replay, Monte Carlo, size comparisons, stress scenarios, and displayed
account traces MUST call the same deterministic transition engine. Analysis
changes the supplied session sequence or its explicitly declared costs/scale;
it does not implement another set of account rules.

This is an account overlay on a frozen strategy trade stream. It does not rerun
strategy callbacks after a simulated suspension, liquidation, or withdrawal.
Subsequent source signals remain the historical signals. State-dependent changes
to the strategy after altered fills are outside this model and must be disclosed.

### First-release boundary

- One completed backtest, one strategy/parameter set, one instrument, one account,
  one phase per simulation, and one explicitly versioned account profile.
- Evaluation and funded phases are separate starting modes. An evaluation pass
  does not automatically start a funded account.
- Support `trade_close` and `bar_close` observations. Both are sampled models;
  neither establishes tick-level compliance or captures every intratrade breach.
- Require constant positive integer source contract quantity and exposure flat
  across each prop session's close and maintenance break. A zero-trade source is
  supported without per-contract normalization or a size recommendation.
- Provide chronological historical replay, session bootstrap, fixed-size grids,
  and a small declared stress matrix.
- Preserve source datasets, strategies, execution assumptions, reports, and costs.
  Unsupported inputs fail explicitly rather than being repaired or reinterpreted.

Defer measured excursions, external trade imports, intraday-trailing profiles,
overnight positions, variable source sizing, staged/adaptive sizing, strategy
parameter search, portfolios, multi-account campaigns, automatic repurchases,
broker integration, and live authorization. The initial named product is Apex
50K EOD; a small rule value model is sufficient, without a general plugin system.

## 2. Notebook identity and evidence

The source is
[PropFirm_MonteCarlo_Apex50K_2508.ipynb](https://colab.research.google.com/drive/1XyYJ4l-nZNPd8hgqdabHlHJPZXAwv4Up?usp=sharing).
It was fetched afresh through Google Drive on the review date and parsed as
notebook JSON without executing its cells.

| Property | Verified value |
| --- | --- |
| Drive file ID | `1XyYJ4l-nZNPd8hgqdabHlHJPZXAwv4Up` |
| Filename | `PropFirm_MonteCarlo_Apex50K_2508.ipynb` |
| Reported modification time | `2026-09-03T13:35:20.773Z` |
| Download length | 1,016,849 bytes |
| Notebook cells | 23, including Markdown cells |
| Supplied and freshly computed SHA-256 | `f79b6c6cc54e7bd64d619bb684ec4c6537c7bcf1d1e1d3f6d5bd6e74c908f89b` |
| Comparison | Exact match; no change from the supplied snapshot |

References below use the notebook's visible cell labels, such as `CELL 6b`,
rather than zero-based notebook array indexes. Notebook output images and stored
numerical results are not validation fixtures. This review checks source behavior,
not a fresh execution of its example backtest.

### Feature disposition

| Notebook feature / cells | Decision | Repository behavior |
| --- | --- | --- |
| CSV/Excel upload and permissive parsing, 1/3 | Replace; external import deferred | Start with existing completed runs; no date guessing, dropped invalid rows, or spreadsheet dependency |
| Instrument labels and source quantity, 2/3 | Correct | Capture currency/instrument assumptions and actual constant source quantity; labels alone do not establish contract equivalence |
| Costs and trade statistics, 4 | Incorporate with correction | Preserve authoritative source costs; add only declared cost deltas; R-multiples deferred unless genuine risk data exists |
| MAE/MFE extraction and synthetic fallback, 4b | Defer | No inferred or fabricated measured excursion |
| Weekday pool and zero days, 5 | Correct | Explicit session calendar and coverage policy across the selected interval |
| Evaluation rules and outcomes, 6/6b/7 | Incorporate with correction | One deterministic engine and explicit observation mode |
| Daily aggregate engine, 6 | Defer | Daily totals alone cannot model within-session suspension |
| Fixed-size sweep, 8 | Incorporate with correction | Train-only selection, valid integer quantities, frozen holdout evaluation |
| Staged sizing, 8b | Defer | Future sizing policy must reuse the same rule engine |
| Equity paths, charts, summaries, 5b/9/10 | Incorporate | Curves come from actual saved simulation traces |
| Independent/correlated repeated attempts, 10/10b | Defer | No unsupported attempt independence or repurchase campaign |
| First payout and funded ladder, 11–15 | Incorporate with correction | First payout is a projection of the full funded lifecycle |
| Economic funnel and robustness, 16 | Partly incorporate | Separate phase objectives, fees, block sensitivity, and conditional funded receipts; defer account-acquisition economics |

### Specific defects and modeling limits to correct

1. **Holdout leakage.** `CELL 8` selects evaluation size on `train`, then leaves
   global `TRADE_BAG` on `validation`. `CELL 8b` compares and chooses staged
   variants there. `CELL 12` selects funded size and `CELL 15` selects lifetime
   size without returning to training data. Those funded/staged choices have
   inspected the holdout. Source filtering through `OOS_START_DATE` also does
   not prove independence from earlier strategy development. Partition objects
   must be explicit immutable inputs, not global mutable notebook state.
2. **Missing staged-sizing DLL.** `simulate_staged()` in `CELL 8b` checks the
   account floor but never applies a daily-loss floor or session suspension.
   Its flat-size baseline therefore need not match the main engine even at
   identical size and seed. Staged sizing is deferred, with no separate engine.
3. **Excursion normalization.** `CELL 3` divides source profit by quantity and
   resets `contracts` to one. `CELL 4b` subsequently reloads raw MAE/MFE without
   the matching division. At source quantity two, P&L can be per contract while
   excursion remains per two contracts. Missing MAE is also replaced with the
   realized loss, making missing winner excursions zero. Future imports must
   preserve source quantity, units, coverage, and missingness for every field.
4. **Different engine behavior.** Daily evaluation omits DLL, while trade and
   excursion evaluation enforce it. `simulate_apex_trade()` and
   `simulate_apex_excursion()` accept `**kw` but discard degradation arguments.
   Funded engines do apply trade degradation. The current `USE_MAE` switch fixes
   a previously described MAE mismatch, but `ENGINE='daily'` still means daily
   evaluation versus trade-resolution funded processing. Mode and scenario
   settings must have identical meaning across phases and analyses.
5. **Calendar approximations.** The pool spans first/last trade dates using
   weekdays, excludes weekend timestamps, approximates inactivity with 22
   trading days, and draws evaluation session counts from `DEADLINE_POOL`.
   Session labels, weekend purchases, holidays, source coverage, and calendar
   deadlines must instead be explicit. Calendar expiry must not silently fall
   back to a fixed number of sessions when history is short.
6. **Perfect-threshold liquidation.** Trade/excursion engines set `eq` to
   `dll_floor` after crossing it. They can shield the account from a lower
   permanent floor even when an observed loss overshoots both. Keep the actual
   observed loss, model remaining closing costs where exposure is open, and
   recheck the permanent floor. Do not interpolate an unobserved perfect fill.
7. **Rule and accounting discrepancies.** Funded Markdown says drawdown is
   $2,500 while executable `PAYOUT_MAX_DD` inherits $2,000. Funded DLL inherits
   the evaluation's fixed DLL instead of implementing funded tiers. The generic
   `BLOWN_COST` and fee/pass-rate acquisition formula do not simulate account
   purchases, activation, elapsed time, or payment receipt. Keep those shortcuts
   out of the first-release financial results.
8. **Selection claims.** Overlapping Wilson intervals do not establish size
   equivalence. The first-payout sweep falls back to all sizes when none meets
   its risk ceiling; lifetime selection falls back to the safest size. Return
   `no_eligible_size` instead of silently relaxing a declared constraint.

## 3. Repository integration and input contract

Existing components remain authoritative:

| Existing component | Reuse and constraint |
| --- | --- |
| [`execution.py`](../alphaquest/execution.py) | `Trade` and `EquityPoint` supply source results; no prop logic is added to strategy callbacks |
| [`reporting.py`](../alphaquest/reporting.py) | Exact Decimal serialization, reconciled source report, streamed staging/publication conventions |
| [`backtest_runs.py`](../alphaquest/backtest_runs.py) | Source run lookup and paged trades; its indexed equity is trade-close equity |
| [`backtest_api.py`](../alphaquest/backtest_api.py) | Worker/progress/orchestration pattern and captured dataset/strategy/settings metadata |
| [`backtest_data.py`](../alphaquest/backtest_data.py) | Saved selection bounds and UTC convention; dataset-local date selection is distinct from prop-session dates |
| [`decimal_math.py`](../alphaquest/decimal_math.py) | Existing exact monetary operations |

The adapter accepts a completed run ID and captures its manifest plus SHA-256
hashes of consumed report/trade artifacts. It reconciles counts and monetary
totals before simulation. Metadata includes strategy ID/source hash/parameters,
dataset ID/hash, selected UTC period, source timezone, initial capital, tick size,
point value, source quantity, commissions, slippage, and execution assumptions.
Never reinterpret dataset-local selection dates as prop-session dates.

`trades.csv` contains full completed trades. `equity.csv` and stored `run_equity`
contain initial equity plus trade closes only. Full bar-close marks are in the
`equity` array of `report.json`. The latter must be streamed or staged with a
bounded parser; `json.load()` of an arbitrarily large report is not acceptable.
A small streaming-parser dependency may be added during implementation if needed;
it does not justify importing the notebook's pandas/matplotlib stack.

### Adapter records

Produce immutable logical records, staged on disk when necessary:

- `SourceSnapshot`: provenance, artifact hashes, instrument/currency declaration,
  source quantity and cost settings, supported observation modes.
- `Session`: trading-date label, UTC open/close/reset, calendar/coverage status,
  ordered trades and observations, flat opening/closing exposure, source totals.
- `Observation`: original bar/trade identity, order, UTC label, flat/open state,
  and P&L relative to the start of its source trade; retain realized versus
  unrealized components and original entry/exit costs.

For source trade `j`, its baseline is source initial capital plus all earlier
completed source net P&L. Subtract this baseline from source equity marks within
that trade. Rebase the resulting relative path onto the simulated account's
equity before the accepted trade. Do not apply future changes in the source's
cumulative equity after a simulation has skipped trades or withdrawn money.
Flat marks between trades have zero additional trading P&L.

### Eligibility

- Account and instrument currency must be explicitly compatible. Existing runs
  may report only currency units, so a snapshotted run-level currency declaration
  is a modeling input; no currency or FX conversion is inferred from the symbol.
- Snapshot the traded contract's weight in the profile's contract-limit units.
  This can come from an explicitly selected, sourced instrument profile or a
  complete custom declaration, with its rule source; reject an unknown
  mapping. Quantity limits cannot compare a micro count directly to a mini cap.
- Each executed source trade has the same positive integer quantity, no overlap,
  no partial exits, and sufficient provenance/cost fields for the selected mode.
- Trades and exposure marks must establish flatness at required boundaries. Flat
  only at end of the entire dataset is insufficient. Trades during a declared
  maintenance break or ambiguous boundary-crossing fills are unsupported.
- The [VWAP port](strategies/vwap_pullback_risk_sizing.md) labels next-open and
  intrabar fills with the containing bar's close. Preserve that convention. If
  a containing bar could straddle a prop boundary and the correct session cannot
  be established, reject that selection; do not assign an invented fill time.
- Decline variable source quantities in both modes. A fixed-size backtest should
  be generated through the ordinary workflow if comparison is needed. Do not
  silently divide out the VWAP strategy's risk-sizing behavior.
- No-trade sources still have a selected observation period. Simulate account
  clocks and costs; return no sizing choice rather than inventing a trade.

## 4. Sessions, calendar, and observation modes

### Explicit clock

Persist a `SessionCalendar` snapshot: IANA account timezone, trading-date
assignment, scheduled opens/closes, reset times, closed dates, early closes,
expected strategy-data windows, and coverage policy. Resolve timestamps to UTC
with a named timezone database/version. Do not use machine-local time or a fixed
UTC offset. Reject ambiguous or nonexistent user-supplied local instants.

For the initial Apex model, use `America/New_York`, a session starting at 18:00
on the previous calendar date and ending at 16:59:59 on its trading-date label,
followed by the maintenance break. Boundary instants use explicit half-open
intervals in the calendar; bar-close interval labels need separate containing-bar
validation described above. Sunday evening activity can belong to Monday.
The calendar snapshot supplies holiday/early-close exceptions; a weekday-only
schedule is allowed solely as a prominently labeled user-selected approximation.

Saved backtests do not certify market-calendar completeness. The run must choose
an explicit expected-data-window/coverage assumption for every scheduled session
in the selected range. The product remembers this exporter expectation once per
dataset identity and resolves an immutable calendar for each new setup. Observed
timestamp spacing can suggest a cadence but cannot prove the intended schedule.
This is a model configuration, not a new dataset evidence
approval workflow. Bar gaps remain gaps. Do not fabricate bars or prices.

| Session status | Treatment |
| --- | --- |
| Covered, no trades | Zero trading P&L; advances the calendar and inactivity clocks |
| Covered, with trades | Ordered observations and reconciled source P&L |
| Market closed by calendar | No trading; calendar time and scheduled external fees still advance |
| Missing/unknown coverage | Reject the requested historical range/resampling pool; never turn it into a zero |
| Partial first/last session | Require an explicit whole-session selection; do not silently trim it |

The observation range comes from the selected backtest period, not first/last
trade dates. Expected strategy windows may cover less than the full market
session, but must establish that no unsupported exposure remains afterward.
Future synthetic calendars must cover the requested horizon and be snapshotted.

### `trade_close`

Apply each accepted completed trade's net P&L at its recorded close label.
Intermediate open-position equity and entry-time expenses are unobserved in this
mode. Treat the whole trade as one net change, preserving original costs once.
Check account rules at each trade close and scheduled session/calendar event.
Do not present an absence of observed breaches as intratrade survival evidence.

### `bar_close`

Use the complete source bar-close equity stream, including entry commissions and
unrealized marks, joined to completed trade identity by bar numbers. Check after
each recorded mark, including flat exit marks. Entry/exit in the same bar has
only the net observation recorded by the source; invent no intermediate path.

If an open-position mark triggers a stop, close at that observed mark with the
source market-exit commission and adverse exit slippage, plus any declared
additional closing-cost stress. The mark already includes entry costs; do not
deduct entry costs again or use the eventual source exit. A flat completed-trade
observation incurs no second exit charge. Record detection and assumed liquidation
separately. Neither this observation nor the closing fill is a tick reconstruction.

Bar-close mode does not inspect each bar's High/Low, infer OHLC order, or claim
that observed adverse marks are measured full-trade MAE. Both modes use identical
phase rules and report their coverage/resolution limitations.

## 5. Rule profiles and initial product

`RuleProfile` contains identity/version/platform/currency, separate evaluation and
funded values, session policy, source URLs/retrieval dates, assumptions, and a
canonical hash. Numerical inputs are strict finite Decimal values or strict
integers as appropriate; reject booleans, NaN/infinity, unknown fields, and
inconsistent ladders/tiers. A profile change creates a new snapshot/hash.

The first built-in candidate is `apex_50k_eod_rithmic`. Its proposed funded phase
also starts at 50,000 with drawdown 2,000 and no evaluation access deadline.
Do not silently apply it
to Tradovate or legacy accounts. Rules are research modeling inputs, not proof
that all conduct/operational account requirements are modeled.

The following official pages were read on 2026-10-25. Their retrieval date is
known; an unprovided legal effective date must remain unspecified.

| Source | Values/behavior grounding the initial profile |
| --- | --- |
| [EOD Evaluations](https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-evaluations/) | 50K evaluation: starting balance 50,000; target 3,000; drawdown 2,000; DLL 1,000; maximum six mini contracts; no minimum trading days |
| [EOD Drawdown Explained](https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-drawdown-explained/) | EOD threshold updates at market close and applies intraday; touch fails; PA lock is starting balance +100; Rithmic evaluation lock differs from Tradovate |
| [Daily Loss Limit Explained](https://apextraderfunding.com/help-center/additional-helpful-items/daily-loss-limit-explained/) | Session suspension, market liquidation, and next-session reset; 50K PA tiers below |
| [EOD Payouts](https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-payouts/) | Five sessions at net profit >=250; strict best-session share <50%; balance >=52,600 to request; leave >=52,100; minimum withdrawal 500; caps 1,500/1,500/2,000/2,500/2,500/3,000; 100% split; six approved payouts |
| [PA Inactivity Policy](https://apextraderfunding.com/help-center/billing/inactivity-policy-on-performance-accounts-pa/) | At least two session profits >=50 in a rolling 30-calendar-date window; purchase date starts initial period; profits belong to session closing dates |
| [Evaluation Fees and Access](https://apextraderfunding.com/help-center/billing/evaluation-plan-fees-and-access-explained/) | Expiry 18:00 ET on day 30; target review at 16:59:59 with pass processing after 18:00; price is a separately supplied input |

Funded tiers, selected using the previous eligible EOD balance minus starting
balance, are fixed for the following session:

| Profit range | Maximum mini contracts | DLL |
| --- | ---: | ---: |
| Below 1,500, including negative | 2 | 1,000 |
| [1,500, 3,000) | 3 | 1,000 |
| [3,000, 6,000) | 4 | 2,000 |
| >=6,000 | 4 | 3,000 |

The configuration implementation refreshed those pages on 2026-10-25 and also
read [PA Scaling](https://apextraderfunding.com/help-center/additional-helpful-items/scaling-levels-pa-explained/)
and [Evaluation Position Sizing](https://apextraderfunding.com/help-center/additional-helpful-items/position-sizing-evaluation/).
Two distinctions are recorded in profile evidence instead of silently reconciled:

- The scaling page labels the top 50K tier `5,999 & Up`, overlapping its preceding
  range; the DLL article says `6,000 & Up`. The implementation explicitly selects
  the DLL article's disjoint lower bounds `0/1500/3000/6000`. This choice is stored
  as `source_conflict`, with both URLs and the selected interpretation.
- Both position-sizing pages describe excess orders being rejected without an
  account penalty. The profile records `excess_size_action="reject_order"` as the
  provider behavior. The first-release overlay rejects an incompatible simulation
  as an operation/input error instead of skipping source trades or classifying
  it as a failed account. This corrects the original proposed failure outcome.

Profiles have version `1.1.0` and explicit Rithmic, Tradovate, and WealthCharts
IDs for this one product; evaluation lock differences are captured per platform.
No legal effective date was supplied for the whole resolved product, so source
`effective_on` remains null. In particular, confirm tier timing relative to withdrawals
and session exceptions. The proposed simulation convention is EOD **after** an
immediate modeled withdrawal for the next session's tier; label that timing as
an assumption unless independently confirmed. Never silently substitute a fixed
evaluation DLL for the funded schedule.

## 6. Deterministic state and event order

Use a small value-based state: phase/status, account balance `B`, current sampled
equity `E`, EOD high-water balance `H`, permanent floor `F`, session opening
balance, fixed session DLL/contract limit, source trade/position identity,
suspension flag, payout cycle counters, activity dates, and modeled cash ledger.
Keep source observations immutable. Money in the equations below is in the
resolved account currency; absolute balances and profit offsets are never mixed.

The initial account is flat at `B = E = H = A`, where `A` is profile starting
balance. Set `F = A - D` for drawdown amount `D`. At session end, update
`H = max(H, closing balance before payout)` and ratchet the next floor:

```text
candidate_floor = H - D
F_next = max(F, min(candidate_floor, configured_absolute_lock))
```

An unlimited lock is represented explicitly, without serializing infinity. The
PA candidate lock is `A + 100`; evaluation and funded values remain separate.
Withdrawals never lower `H` or `F`.

### Session processing

1. Process any earlier calendar event (expiry, cost, inactivity) before later
   trading. At equal timestamps use the explicit order below.
2. Open a session flat. Freeze its DLL and contract limit from the applicable
   tier. Set `DLL_floor = opening balance - session DLL`. A disabled DLL is an
   explicit optional value, not a zero/negative magic number.
3. Before an accepted entry, enforce contract limits. A candidate exceeding a
   session limit is incompatible with the frozen-stream overlay; reject the
   simulation operation rather than declaring an account failure. The actual
   provider rejects excess orders without an account penalty. Do not silently
   resize, clip, or skip a strategy trade. Source trades after a prior suspension are
   skipped and do not count as accepted entries.
4. Apply each accepted observation's relative trading change to simulated
   state. Check permanent failure first. If `E <= F`, record drawdown detection,
   liquidate any remaining exposure using the observation-mode rule, record
   closing costs/final equity, and terminate as failed. If only
   `E <= DLL_floor`, record a DLL hit; liquidate remaining
   exposure using the observation-mode rule, recheck `F` after closing costs,
   and suspend the rest of the session if still alive.
5. If one sampled observation crosses both floors, or closing costs cross the
   lower one, permanent failure wins. Unknown earlier crossing order is not
   evidence that the DLL provided protection. No threshold-fill interpolation.
6. At a covered session close, require flat exposure. Compute accepted session
   net trading profit, including forced-exit costs and excluding withdrawals
   or external account fees. Update qualifying/activity/cycle counters from
   this profit. Suspended sessions can contribute a loss; skipped trades do not
   recover it. Ratchet `H/F`; process payout and the next-session tier.
7. Evaluation target is recognized at a flat completed-trade observation and
   records `target_reached_at`; under the chosen policy freeze further trading
   pending the same session's close. At valid EOD, record `passed` with simulated
   review/recognition timestamps. This stop-on-target policy is a disclosed
   modeling choice, and external approval is not simulated evidence.
8. Process daily calendar closure checks after that date's eligible session and
   immediate modeled payouts. On the final evaluation date, its valid EOD pass
   has priority over the later 18:00 expiry. Never process trading at/after expiry.

Rule breach outranks payout or pass at the same observation. At a session close,
account survival precedes cycle/activity updates and payout. A valid second
activity session on the last allowed date counts before inactivity closure.
First-release inputs must establish these orderings; ambiguous scheduled
boundaries are rejected rather than resolved using future information.

### Terminal outcomes versus operational status

| Account outcome | Meaning |
| --- | --- |
| `passed` | Evaluation meets the modeled target/review policy |
| `failed_drawdown` | Sampled equity or modeled forced-exit equity touches/crosses permanent floor |
| `expired` | Evaluation deadline occurs without a prior modeled pass |
| `closed_inactive` | Funded activity window fails after its initial grace period |
| `completed_payout_ladder` | Final allowed modeled payout completes the funded lifecycle |
| `unresolved_data_end` | Historical observations end while account is still active |
| `censored_horizon` | Monte Carlo computational horizon ends with an active account |

`session_suspended` is nonterminal. Invalid inputs and execution/storage errors
are failed **operations**, never financial account outcomes or successful saved
simulations. A completed simulation operation may legitimately contain censored
accounts. First-payout eligibility is a milestone, not another engine or terminal
outcome.

Historical replay ends at its declared data boundary. It must not label an active
account expired/inactive using a fabricated missing future. Calendar events up
to the explicit end timestamp, including closed-market days, still apply.

## 7. Money, sizing, costs, and withdrawals

### Source and scaling arithmetic

Use existing exact monetary helpers and Decimal-string JSON/CSV. No binary-float
P&L or intermediate display rounding. Counts and quantities are strict integers;
statistical probability/interval calculations may use floating point separately.

Source `gross_pnl` already embeds fill slippage; `net_pnl` also subtracts both
commissions. Never subtract `slippage_cost` again. Source initial capital is a
baseline to remove, not cash to add to the prop account.

For constant source quantity `q0` and candidate quantity `q`, scale monetary
trade/path/cost components by `q/q0`. Use exact rational arithmetic or validated
exact Decimal results; never round a repeating per-contract quotient and then
multiply it back. If exact scaling cannot be represented under the supported
monetary contract, reject that candidate explicitly.

The first release compares integer quantities of the **same instrument** only,
including a source backtest actually traded in micros if its contract-limit
weight is explicitly established. For limit checks use
`candidate_quantity * contract_limit_weight <= session_limit` with exact
arithmetic. This is rule-unit accounting, not a cross-instrument P&L conversion.
Fractional traded contracts and synthesizing micro performance from a mini
backtest are deferred. A label such as `0.3 MINI = 3 MICRO` cannot establish
executable equivalence, fees, or fills.
Declare unchanged fill prices and linear cost/liquidity scaling as assumptions.

Additional commission/slippage stress is an explicit delta charged only on
accepted fills, with timing preserved in bar-close mode. An open-position forced
exit replaces the source exit; it does not incur both exits. External purchase,
activation, recurring platform/data charges are separate dated cash events, not
trading P&L or losses that modify a qualifying-session profit.

### Payout lifecycle

For the initial immediate-payment model, at each funded session close:

- Require account survival, sufficient qualifying sessions, positive cycle
  trading profit, strict consistency, minimum request balance, and a withdrawal
  of at least the configured minimum.
- Set gross withdrawal `W = min(B - safety_net_balance, current_ladder_cap)`.
  Require the post-withdrawal balance to respect the safety net.
- Record eligibility, assumed approval, account debit `W`, and modeled receipt
  `W * profit_split` as separate ledger fields/events at the same timestamp.
  This is the explicit `immediate_approval_and_payment` assumption, not an actual
  provider approval or bank receipt. Delays, denials, and pending reserves are
  deferred; no unpaid eligibility amount counts as received cash.
- Set `B := B - W`. Reset cycle trading profit, best-session profit, qualifying
  and traded-session counters after assumed approval. Activity history and
  permanent floor remain. Complete the account after the last permitted payout.

Cycle consistency uses net **trading** profit since last modeled approval,
excluding withdrawals and external fees. Use multiplication for the strict
comparison (`best_session_profit < limit * cycle_profit`), avoiding a division
boundary. A payout cannot become eligible solely because a withdrawal changed
a denominator. Apply inactivity to the latest 30 local calendar-date labels,
inclusive of today; the first full window ends on purchase date +29 days.
Sessions qualify only after closing, including the final date of a window.

Reconcile at every saved path:

```text
account_balance = starting_balance + accepted_realized_net_trading_pnl
                  - gross_account_withdrawals
sampled_equity  = account_balance + current_unrealized_pnl
modeled_net_cash = sum(modeled_receipts) - sum(external_costs)
```

Entry commissions already realized on open trades belong in the realized trading
component. Prior modeled receipts survive later account failure; remaining
account equity and unapproved eligibility are not external cash.

### Conditional phase economics

Evaluation mode charges one explicitly configured attempt fee at start and
reports the modeled attempt outcome. It has no funded payout receipts.
Funded mode starts with a fresh funded account and reports outcomes **conditional
on already having that account**. If configured, charge its activation fee once
and dated ongoing fees through the modeled lifetime; do not charge unknown
historical evaluation costs. Gross receipts and net cash are separate outputs.

Do not subtract `fee / pass_rate`, append `BLOWN_COST`, multiply independent phase
means, or claim a date-bounded end-to-end campaign return. Such a campaign needs
attempt transitions, activation delay, shared calendar/regime, payment timing,
and actual cost schedules, and is deferred. No repurchase occurs on closure.

## 8. Historical replay, Monte Carlo, and selection

Historical replay preserves ordered actual sessions and observations from an
explicit account start through the selected data boundary. Its one account
outcome is not an estimated pass probability. Closed days and genuine no-trade
sessions remain in the timeline.

Monte Carlo samples complete covered session records from an explicit training
or validation partition. `block_length=1` is independent-session bootstrap;
`5` and `10` are circular moving-block bootstrap over eligible source sessions,
including covered zero-trade sessions. Blocks wrap only inside their partition.
Preserve original within-session order, durations, and observation-mode semantics.

Give every simulated path a real configured purchase/start instant and a
synthetic session calendar. Consume one sampled session on each scheduled open
session; closed dates consume no sample but advance calendar clocks. Map relative
source observations only onto compatible destination session schedules. For the
first release require matching relative session/data-window structures for all
source/destination sessions; reject incompatible early closes or DST schedules
rather than truncating or moving observations outside the destination session.
This restriction is an explicit first-release limitation of resampling.

Day 1 of evaluation is its purchase calendar date in the account timezone; expiry
is 18:00 on day 30 for the candidate profile. Start-time partial access must be
represented; reject a replay requiring trades before purchase. The default
historical start is the first selected session open. Calendar windows are never
drawn from the notebook's `DEADLINE_POOL`. Funded simulation has a configurable
calendar end/horizon; an active account at that guard is censored, not failed.

Save seed, RNG algorithm/version, independent sampling/scenario stream names,
and source session IDs/indices per path (or a reproducible bounded trace plus
index-stream hash). Paired size candidates use the same source-session index
stream. Determinism must not depend on candidate order, progress polling, or
chart requests. Pin implementation/environment information for reproducibility.

Holdout defaults to the final 30% of complete eligible sessions: use the first
`floor(0.70 * N)` for training and the rest for validation, requiring both
partitions nonempty. A requested simulation that needs more compatible history
than exists is rejected, without fallback. A user may disable holdout explicitly,
in which case all sizing results are labeled in-sample. This split does not
certify that the underlying strategy was developed without seeing validation.

Selection is frozen before reading validation performance:

- Evaluation: maximize training pass rate subject to predeclared failure and
  drawdown limits; exact objective ties choose the smaller valid quantity.
- Funded: maximize training mean modeled receipts through the declared horizon,
  subject to the declared account-failure ceiling. Show net cash separately and
  include zero-receipt accounts in the objective mean. For this constraint,
  funded account failure includes drawdown and inactivity
  closure; report those rates separately as well as their sum. Ladder completion
  and horizon censoring are not failures.
- If no quantity meets the constraints, return `no_eligible_size`. Do not relax
  ceilings, relabel a fallback optimal, or choose from validation rankings.
- A single selected quantity per phase is evaluated on holdout. Stress/block
  comparisons on holdout are diagnostics; retuning based on them consumes that
  holdout and requires a newly independent evaluation before another claim.

Initial stress scenarios: higher accepted-fill costs, reduced positive completed
trade net P&L, and block lengths 1/5/10. To preserve path consistency, positive
trade-profit reduction is a declared adverse adjustment at its actual exit,
leaving prior marks and losing trade outcomes unchanged; a source trade forced
out earlier does not receive its unused future adjustment. Label this as exit
profit stress, not a fully degraded market path. Winner-to-loser replacement,
MAE transformations, and staged sizing are deferred.

## 9. Saved results and portal behavior

Persist operations separately from source backtests under `prop_runs/` with a
small `prop_simulations.sqlite3` catalog beside existing run storage. Use new IDs,
atomic staged publication, paged result reads, and no completed catalog entry
until source validation, simulation, and reconciliation all succeed. Do not
overwrite source reports or enrich their financial results in place.

The saved manifest includes format/engine version, phase, analysis type, source
snapshot and hashes, full resolved profile/hash, calendar/coverage snapshot/hash,
observation mode and limitations, currency declaration, sizes, fees, scenarios,
partitions, synthetic dates/horizon, seed/RNG, outcome counts, reconciliation,
and artifact hashes. Complete results must remain interpretable without a later
mutable template, dataset metadata edit, or current strategy source tree.

Artifacts:

- `report.json`: metadata, assumptions, aggregate statistics, and references to
  streamed detail; no enormous embedded all-path array.
- `outcomes.csv`: one row per path with phase/outcome, dates, receipts, fees,
  drawdown, payout count, and censoring flag.
- `events.csv`: complete historical account ledger; bounded selected Monte Carlo
  trace ledgers with an explicit retained-path count and selection policy.
- `payouts.csv`: per-path modeled withdrawals/receipts, streamed to disk.
- `comparisons.csv`: training selections, frozen validation results, and declared
  stress/block comparisons, identified by phase and partition.

Aggregate statistics use all paths, not retained chart samples. Report terminal
outcome counts/rates, DLL hits per actually processed session, drawdown from the
EOD high-water balance to observed/liquidation equity, and sampled equity-peak
drawdown as a separately named metric. Include conditional time-to-pass and
first-payout distributions, mean/median/P10/P90 receipts and net cash, probability
of zero receipts, probability of each payout count, and censoring fraction.
Show calendar time versus trading-session counts separately. Undefined statistics
are `null`/N/A, never NaN, infinity, or zero substituted for missing results.

Wilson intervals describe event-frequency Monte Carlo error conditional on the
historical sample/model. They do not measure uncertainty in future strategy
edge, selection bias, rule coverage, or market regimes. Use one outcome per path
as the statistical unit. Censored first-payout times are not failures, and the
conditional observed-time quantiles are not survival-adjusted lifetime estimates.
Use "receipts through horizon" when paths remain active; do not advertise an
unconverged mean as full-lifetime expectation.

CLI/service and then API/portal expose the same request contract. Proposed routes:
`POST /api/prop-simulations`, list/detail, paged outcomes/events, and allowlisted
artifact exports. Reuse current local worker-thread/progress conventions with
bounded simulation/horizon/grid/trace request limits. No background-job platform
is needed. Progress reports stage and paths completed; retries do not imply reuse
of an unknown successful operation.

The completed backtest screen gains **Simulate prop rules**. It presents source
costs and compatibility, profile/phase, observation resolution, calendar/coverage,
historical versus sampled analysis, fixed size/grid, and simulation settings.
Results separate source backtest performance, account balance, and external
modeled receipts/net cash. Show exact settings, first terminal reason, saved
traces, downloads, holdout status, and sampled-monitoring limitations. Preserve
existing reports and dataset screens. Duplicate submission is disabled while the
request runs; reload reads durable completed results.

## 10. Small module boundaries

These are implementation destinations, not files created by this specification.
Keep evaluation and funded transitions together rather than duplicating them.

| Proposed file | Responsibility |
| --- | --- |
| `alphaquest/prop/types.py` | Immutable requests, source/session/observation records, state, events, results |
| `alphaquest/prop/rules.py` | Strict profiles, phase values, tier resolution, canonical snapshots/hashes |
| `alphaquest/prop/sessions.py` | Source artifact adapter, calendar/coverage, normalization and session staging |
| `alphaquest/prop/calendar.py` | Immutable declared source calendar/windows and unambiguous session boundaries |
| `alphaquest/prop/coverage.py` | Reusable exporter expectations, pinned schedule resolution, bounded timestamp inspection and coverage assessment |
| `alphaquest/prop/_report_reader.py` | Bounded reader for saved report metadata and trade/equity records |
| `alphaquest/prop/engine.py` | Pure deterministic transitions for both phases and one path runner |
| `alphaquest/prop/analysis.py` | Bootstrap, explicit partitions, paired fixed-size selection, stress and aggregates |
| `alphaquest/prop/runs.py` | Service orchestration, reconciliation, artifacts and durable run catalog |
| `alphaquest/run_prop_simulation.py` | CLI argument validation and calls to the service |
| `alphaquest/prop_api.py` | HTTP validation/progress/paging/export boundary; no financial logic |
| `alphaquest/web/prop.js` plus existing HTML/CSS | Form, progress, result inspection, bounded charts |
| `tests/test_prop_*.py` and dedicated fixtures | Independent financial/lifecycle cases and integration checks |

The engine must accept session iterators without database, filesystem, RNG,
strategy, or HTTP access. The analysis layer owns RNG and sequence construction;
the runs layer owns disk-backed input staging and publication. Memory may grow
with bounded batch/trace size, not simulations multiplied by horizon. Financial
arithmetic cannot depend on a consumer's Decimal context.

## 11. Acceptance examples

Unless stated otherwise these are synthetic account-engine fixtures, not claims
about a real strategy. Use independent expected values, not simulator-generated
goldens. Scenarios specify the observations necessary for the selected mode.

| Case | Input / setup | Required result |
| --- | --- | --- |
| Source costs exactly once | Existing arithmetic trade: source initial 10,000; quantity 2; gross 30; commissions 4; net 26; informational slippage 10 | At equal quantity, prop initial 50,000 becomes 50,026. At quantity 1 it becomes 50,013. Never subtract informational slippage again |
| DLL overshoot | Trade-close mode; `F=48,000`; opening equity 50,000; DLL 1,000; first completed trade -1,200; later source winner +800 | Equity remains 48,800, one DLL suspension, later trade skipped; next covered session resumes |
| Both floors crossed | Same setup, first observed completed-trade loss -2,100 | `failed_drawdown` at 47,900; never clip to 49,000 and continue |
| Open-mark forced close | Bar-close mark 48,990; DLL floor 49,000; permanent floor 48,000; two contracts; per-side commission 1; tick .25; point value 10; slippage 1 tick | Mark already includes entry costs. Additional market exit costs are 2 + 5 = 7; close at equity 48,983; suspend; eventual source exit is ignored |
| Forced close reaches floor | Same mark/exit assumptions but active permanent floor 48,985 | Closing at 48,983 causes permanent failure, overriding temporary DLL suspension |
| EOD ratchet | Start 50,000; drawdown 2,000; covered flat session closes 50,800 | Next floor 48,800; a subsequent lower close does not lower it; touch fails |
| Evaluation pass | Target 3,000; six accepted flat net wins of 500 within valid access | Record target at 53,000; stop further trading by declared policy; modeled pass at valid EOD; no funded activation/receipt |
| Late source end | Evaluation history ends on day 5 at 50,500 with no breach | `unresolved_data_end`, not day-30 expiration |
| Deadline | Start 2026-01-05 at 18:00 ET, day 1 Jan 5; no target reached; covered calendar through expiry | Day 30 is Feb 3; expiry at Feb 3 18:00 ET; no trades at/after expiry; closed dates still count |
| Funded tiers | Prior eligible EOD profit exactly 1,500 / 3,000 / 6,000 | Next-session maximum/DLL is respectively 3/1,000; 4/2,000; 4/3,000; limit remains fixed within the session |
| First payout | Fresh funded account; six sessions net +500; no earlier payout; initial cap 1,500 | At balance 53,000, withdraw 900, leave 52,100, receipt 900 at split 1; qualifying/cycle counters reset, activity dates and prior floor remain |
| Consistency equality | Five qualifying sessions +1,500,+500,+500,+250,+250; cycle profit 3,000 | Best session equals 50%; payout blocked despite balance and day count |
| Eligibility versus safety net | Engine state has five qualifying sessions, positive cycle profit, passing consistency, balance exactly 52,600 | Minimum withdrawal 500 is eligible and leaves 52,100; do not require 53,100 |
| Non-unit profit split | Synthetic profile; eligible gross withdrawal 1,000; split .80 | Account debits 1,000; receipt 800; neither side records the other value |
| Later account loss | Earlier immediate modeled receipt 900; later drawdown failure | Receipt stays 900; remaining unwithdrawn account profit is not cash; no replacement charge |
| Activity on final day | Funded purchase Jan 1; +50 qualifying session dates Jan 2 and Jan 30; other sessions net zero | Jan 30 window passes; on Jan 31 both still qualify; on Feb 1 Jan 2 leaves the inclusive window and closure occurs without another qualifying session |
| Sunday and DST | Sunday 20:00 ET observation; then session opens across DST changes | Assign Sunday activity to Monday; recompute UTC from IANA zone, without dropping weekends or using fixed offsets |
| Missing versus zero | Covered full selected session with no trades versus a required session with unknown coverage | First contributes zero and advances clocks; second rejects the operation |
| Overnight/boundary ambiguity | Source position spans maintenance break, or a fill-containing bar straddles boundary | Explicit unsupported-input result; no forced source rewrite |
| No trades | Covered source with no executed trades and valid account/calendar config | Historical clocks/outcome apply; no invented trades, no divide-by-zero quantity normalization, no selected size |
| Holdout isolation | Change only validation outcomes while keeping training fixed | Selected quantity and training results unchanged; block samples never cross partitions |
| No feasible size | Every training candidate exceeds the declared risk ceiling | `no_eligible_size`; no fallback winner |
| Censoring | Funded account alive at declared Monte Carlo horizon | `censored_horizon`; receipts retained; no forced failure or full-lifetime claim |
| Reproducibility | Same snapshots, seed, RNG/engine version and request, different candidate ordering | Same per-path sampled session IDs and outcomes for matching candidates |
| Publication failure | Input/reconciliation/storage failure after staged output | No completed prop run; source run and datasets unchanged |

Additional acceptance checks must cover the whole payout ladder, repeated cycle
resets, paid receipts after closure, observation-mode differences, zero/all Monte
Carlo successes, interval bounds, fee schedules on closed dates, tier movement
after payout, chart trace equality, bounded-memory parsing/simulation, API
validation, portal reload, and compatibility with older backtest reports.

## 12. Implementation sequence and review boundary

### Configuration API now available

`alphaquest.prop.types` provides frozen rule values plus `SimulationConfig`,
`MonteCarloConfig`, `SizingConfig`, `StressConfig`, `UserFees`, and `DatedFee`.
Constructors require exact Python types (Decimal money, integer quantities,
tuples, dates, naive local wall times, and aware UTC instants). `from_dict()`
requires every schema field, forbids unknown fields, and decodes only exact
decimal/date/time strings and JSON arrays. There is no implicit type coercion.

`get_profile()` defaults to `apex_50k_eod_rithmic`. The explicitly named variants
`apex_50k_eod_tradovate` and `apex_50k_eod_wealthcharts` cover only the verified
evaluation lock difference. `funded.tier_for_profit(Decimal(...))` resolves a
prior-session profit into a tier; it does not advance account state or apply
withdrawals. Negative profit uses the first tier; lower bounds are inclusive and
upper bounds are the following tier's lower bound.

`resolve_profile(profile)` returns `ResolvedProfile`. Its JSON contains the full
rule/profile/evidence snapshot and `profile_sha256`; reload through
`ResolvedProfile.from_json(text)` validates the saved content without consulting
the current template. `resolve_simulation(config, profile)` returns the envelope
for a future saved run, including that profile snapshot, all request settings and
user fees, and `settings_sha256`. `ResolvedSimulation.from_json(text)` validates
both hashes. The product setup integration now persists this envelope in the
shared prop store described below.

Hashes use UTF-8 canonical JSON with sorted object keys and compact separators.
Decimal coefficients/exponents are canonicalized without ambient precision or
rounding; numerically equivalent spellings and signed zero have the same
identity. Ordered arrays remain ordered. The profile digest includes source
metadata, assumptions and any reusable user-supplied `fee_defaults`. Per-run fee
overrides are bound by the separate simulation-settings digest. Wire dictionaries are detached copies; nested
domain values are frozen and contain tuples. Hashes detect changed saved content,
not externally signed approval or trust. Retrieval dates and versions do not
automatically update when loading an old snapshot.

Simulation requests identify a source run, calendar ID/hash, timezone-data
version, and coverage declaration; the adapter verifies these against an explicit
calendar before adapting source data. Configuration types alone do not establish
calendar/source validity. Fees must be resolved from a configured account-profile
default or an explicit simulation override (zero is allowed), in matching currency. Evaluation has an
attempt fee and no activation fee; funded has an activation fee and no attempt
fee. Explicit dated costs must fall within the requested period. Analysis settings
exclude measured excursions and staged sizing. Product configuration and input
previews and historical evaluation execution are available. Funded execution
and Monte Carlo remain unimplemented.

### Saved-source adapter API now available

`prepare_backtest(runs, resolved, calendar, instrument)` is a context manager.
It accepts the existing `RunStore`, a `ResolvedSimulation`, a `SessionCalendar`,
and an explicit `InstrumentDeclaration`. The declaration records symbol, account
currency interpretation, actual source tick size/point value, rule-unit contract
weight/source URL, and its basis. It must match the request, captured execution
settings, and any saved symbol/currency. It does not infer these from a ticker or
consult a later mutable dataset/instrument catalog.

Construct the calendar from `CalendarDay` values declaring **every calendar
date**, including closed dates. A covered day must supply one or more ordered
`DataWindow(first_utc, last_utc, bar_interval_seconds)` values with inclusive
expected bar-close labels. Windows may describe only the strategy's declared
data hours, but each expected label must exist. Missing, unknown, partial, or
irregular coverage is rejected, without fabricated bars or zero-filled days.
The explicit policy permits declared holidays and earlier closes. Selecting
`weekday_approximation` records that limitation and requires weekends closed;
the adapter does not choose that mode automatically.

Session opens/closes/resets use the profile's IANA timezone; Sunday evening can
belong to Monday. Calendar snapshots include resolved UTC boundaries and the
declared timezone-data version. `SessionCalendar.from_json()` checks that saved
boundaries agree with the available timezone interpretation. Ambiguous and
nonexistent boundaries fail. Observations in maintenance breaks, or next-open
fill-containing bars crossing a prop open, are unsupported. In particular, a
minute bar labeled after the precise prop close is not silently backdated or
assigned an invented pre-close fill, even if the source position is flat.

Bind the calendar's `id`, `sha256`, `mode`, `timezone_data_version`, and
`coverage_assumption` into the request before `resolve_simulation()`. The source
calendar describes the historical input pool; it does not certify a future
Monte Carlo destination schedule. The latter remains analysis-layer work.

```python
from alphaquest.prop import prepare_backtest

# runs, resolved, calendar and instrument are explicit caller-owned values.
with prepare_backtest(runs, resolved, calendar, instrument) as source:
    saved_source_snapshot = source.snapshot.to_dict()
    for session in source.sessions():
        for observation in source.observations(session.trading_date):
            consume(session, observation)  # caller-supplied sink; no engine yet
```

Preparation copies/hashes `report.json`, `trades.csv`, and `equity.csv` using
bounded reads, then stages report records in temporary disk-backed SQLite.
The reader consumes one bounded record at a time, never a full report array;
unsupported oversized records/metadata fail explicitly. It checks the completed
catalog manifest without invoking legacy enrichment or modifying source rows.
CSV records must agree with the report; the existing reporting reconciler checks
the ordered authoritative events. Additional checks bind recorded price P&L and
commissions to source execution settings, match exposure/cash to trade identity,
and match original selection bounds/counts to the observed period. Required
provenance/selection fields absent from older reports cause an explicit
unsupported-input error, without changing those older reports or their screens.

Only after complete validation does the context expose reusable iterators:

- `sessions(quantity=...)` includes covered zero-trade and declared closed days,
  source bar/trade counts, resolved boundaries, and scaled session net P&L.
- `trades(trading_date=None, quantity=...)` returns `ScaledTrade`, whose frozen
  `source` retains every original `Trade` field, including quantity, prices,
  reasons, timestamps, and costs. Scaled monetary fields are separate.
- `observations(trading_date, mode=..., quantity=...)` streams either all source
  bar-close marks or just completed-trade closes. Flat marks between trades have
  zero relative change; no-trade streams have no invented source quantity.
  Every trade's observations are relative to its own pre-entry source baseline,
  with realized/unrealized components and original absolute equity retained.
  `equity_change` is the cumulative change **within that trade**, not a per-bar
  delta to sum repeatedly. Commission fields identify costs already embedded in
  those observations, not additional charges to apply.

Quantities must be the request's fixed quantity or a member of its sizing grid.
Every requested trade/path scale is checked before the view is exposed. Exact
rational scaling avoids rounding a per-contract quotient; a repeating Decimal
result is unsupported. Original fills and source quantity remain unchanged, and
informational slippage is not deducted a second time. Variable source quantities
and exposure across prop closes/maintenance are rejected in both modes. No MAE,
MFE, OHLC intrabar path, or synthetic excursion is produced.

`SourceSnapshot` is frozen and includes detached canonical manifest/calendar
JSON, the instrument declaration, source counts/quantity, artifact byte hashes,
and sampling limitations. Its `sha256` identifies that complete snapshot.
All iterators must be consumed within the context. Full validation precedes any
useful output; normal exit, early consumer exit, and preparation failure remove
all temporary copies/indexes. The adapter does not publish a prop run or execute
any account rules.

1. Review this specification and its modeling restrictions.
2. Implement validated rules/configuration, then source/session adaptation.
3. Implement deterministic evaluation, then funded transitions and cash ledger.
4. Add Monte Carlo, frozen size selection, and declared stress scenarios.
5. Add durable results/CLI, then API/portal.
6. Independently verify the acceptance examples and run existing regression and
   relevant browser checks; report limitations beside actual check results.

Measured-excursion work requires a later specification for units/quantity
normalization, source trade matching, complete coverage, missingness, cost basis,
and ordering uncertainty. MAE/MFE extrema alone do not establish their temporal
order or exact liquidation prices. Do not enable an excursion label by filling
missing winners with zero MAE or renaming sampled bar-close marks.

The product source check exposes compatibility. Separate evaluation execution
applies account rules and saves account outcomes. Funded execution and Monte
Carlo remain future increments.
This specification, notebook identity check, and green engineering checks do not
establish provider approval, exact
MultiCharts parity, future payout receipt, or trading readiness.

## Demonstrable deliverables for each subtask

Every future implementation must deliver a usable increment in the actual final
product workflow, inspectable actual outputs, and exact user steps with
independent expected values/outcomes and relevant rejection/boundary checks.
Pair backend work with the minimum real API/UI integration needed to use it.
Do not build a separate subtask demonstration page/API/store. Fixture oracles
belong in tests; any example data must use the normal product workflow and be
clearly labeled. Automated tests supplement the user demonstration. Preserve
earlier saved snapshots and do not fabricate future account outcomes. Extend
[the workflow guide](prop_simulation_review.md) as increments land.

### Product configuration and source checking now available

The completed backtest report's **Set up prop simulation** action opens
`#backtests/prop/new/<source-id>`. Saving navigates to
`#backtests/prop/<setup-id>`; saved setups are listed for that source backtest.
The form exposes named platform rules, independent evaluation/funded settings,
observation mode, fixed quantity, inherited user-supplied profile fee with optional override, explicit UTC analysis
bounds, source-unit declaration, and calendar/coverage declaration. It displays
the captured rules/evidence/sources, assumptions and conflicts. Current templates
are used only for new saves; reopening and checking an older setup consumes its
saved `ResolvedSimulation`, not a mutable template. Form edits invalidate the
visible compatibility result and require a new save before checking.

`alphaquest/prop/runs.py` introduces `PropRunStore` using the planned
`prop_runs/` directory and `prop_simulations.sqlite3` database. `prop_setups`
contains immutable draft settings and source IDs. Saving edits creates a new ID,
never rewrites an earlier snapshot. `prop_checks` records immutable compatible
or rejected source checks and points to the saved setup. A compatible check does
not turn a draft into a completed simulation. Publication uses staged directories
and database transactions; interrupted processing does not publish a check.

`alphaquest/prop_api.py` exposes `/api/prop-simulations/profiles`,
`/sources/<id>`, `/setups` (POST/list), `/setups/<id>` (GET),
`/setups/<id>/check` (POST), bounded `/checks/<id>/sessions` and
`/checks/<id>/observations`, and allowlisted setup/check exports. Sessions and
observations are staged incrementally in per-check SQLite and CSV outputs;
previews page at most 100 rows. No full source report array is loaded into RAM.
Source reads preserve the original artifacts/catalog and captured strategy,
dataset, selected period, execution settings, quantities and costs. Checks retain
the full source snapshot/hash and both observation modes. A rejected check saves
its reason and offers no successful preview.

The default **Coverage check** resolves a reusable source-session profile chosen
once for the dataset ID and content SHA-256. Presets offer CME equity cash hours
and overnight sessions with one- or five-minute bar-close labels. Cash hours
mean 09:30–16:00 New York: inclusive close labels start at 09:31 or 09:35.
Overnight close labels start one interval after 18:00, ending at the last aligned
label before the 16:59:59 prop close. A 17:00 label is incompatible with this prop
boundary and is rejected, not discarded. Sunday evening belongs to Monday.
Custom profiles record an explicit cadence and inclusive first/last close labels
in New York. They can use the market model or a labeled weekday approximation.
The original explicit JSON calendar remains an advanced override for schedules
with other exceptions. Existing saved manual calendars keep their behavior.

Automatic schedules use exactly `pandas_market_calendars==5.5.0`, `CME_Equity`,
over the reviewed model range 2013–2026. This is a pinned calendar model, not a
certification that every exchange/exporter exception is correct. Its model
holiday closures, early closes and historical breaks are intersected with the
chosen exporter window; source bars never define that window. The model was
reviewed on 2026-10-26 against the
[CME trading-hours entry point](https://www.cmegroup.com/trading-hours.html) and
[pinned calendar implementation](https://github.com/rsheftel/pandas_market_calendars/blob/v5.5.0/pandas_market_calendars/calendars/cme.py).
Those links are provenance, not evidence of a live product-specific exception
feed. In particular, modeled 13:00 New York holiday closes are assumptions;
use an advanced explicit calendar where a verified export schedule differs.
Dates outside the reviewed range require an advanced calendar. No live exchange
lookup or holiday inference from missing bars occurs during simulation.

Inspection streams the full `report.json` through `ReportReader`, hashes its
bytes, and writes compressed exact timestamp runs and trade counts to the
existing prop SQLite store. Memory does not grow with the bar array. A cache is
keyed to the report's file identity/size/modification/change times, catalog hash,
session policy and scan version. Saving an automatic setup forces a fresh scan;
checking and execution independently revalidate the source artifact hashes.
Daily inspection results distinguish complete zero-trade sessions, modeled
closures, early closes, missing whole sessions, off-grid/extra bars, and partial
boundaries. The full selected period is retained, including explicit selected
prefix/suffix dates without observations. Gaps reject saving; none are filled,
trimmed, or relabeled as zero trading.

`PUT /sources/<id>/session-profile` stores dataset preferences;
`GET /sources/<id>/coverage` returns a bounded daily preview. Automatic setup
requests carry the profile hash instead of a manual calendar. The API resolves
the calendar again and rejects stale profile hashes or incompatible coverage.
Each setup captures its profile, report hash, calendar hash, calendar model and
source URLs/review date in downloadable `coverage.json`. Setup JSON embeds only
the first 50 session rows; `GET /setups/<id>/coverage` pages the captured report.
Completed results copy and hash that artifact. Editing the dataset preference
never changes earlier setups or results; reopening uses their captured data.
The advanced calendar records its explicit coverage basis. All modes record
actual timezone-file identity, profile session policy and resolved UTC boundaries.
Source calendars are limited to 10,000 dates, 24 windows per explicit day;
cadence is 1–86,400 seconds. Product decimal inputs are exact strings, limited
to magnitude 1e12 and 18 fractional places, and quantities to 1–10,000.

Subtasks 1–3 provide setup and input-checking stages. **Run simulation** now
executes historical evaluation; funded execution remains disabled with its
reason. The old demo-only routes/code have been removed; previously
saved `prop_reviews/` files remain on disk as historical evidence.

### Historical evaluation execution now available

`alphaquest/prop/engine.py` implements deterministic evaluation transitions using
caller-owned session/trade/observation iterators and an event sink. It has no
storage, HTTP, strategy or RNG access. Exact money helpers handle sampled marks,
forced exits, suspension, target freeze/review/recognition, expiry, EOD floor
ratchets and external costs. The Rithmic/WealthCharts absolute floor cap is
initial balance plus configured lock profit; Tradovate evaluation has no cap.
Source initial capital never enters the prop balance. Trade-close mode updates
trading balances at completed-trade observations; bar-close mode preserves
entry expenses and open marks.

This release rejects a historical start other than the first declared session
open, and an end other than a declared reset within the source calendar. These
are explicit partial-session limitations. End can select a complete calendar
prefix; later source trades are not reached. Early market closes use the
declared close for the EOD ratchet and retain the profile's fixed review/
recognition wall times. Purchase date is evaluation day 1. A valid final-date
pass precedes equal-time expiry. External fees due at the terminal instant
are included; later fees are not incurred.

`PropRunStore.execute` prepares/reconciles source artifacts again, then compares
their snapshot identity with the latest compatible check. Changed bytes require
a fresh source check, even if semantically equivalent. A saved result includes
resolved settings/profile, source/calendar snapshots and hashes, assumptions,
engine/Python versions, summary and reconciliation. `prop_results` extends the
existing catalog without rewriting setups/checks. Staged output and a database
transaction publish results only after ledger deltas reconcile to final balance,
external costs to net cash, accepted entries to natural/forced closes, and source
counts to processed/skipped/not-reached counts.

Under `/api/prop-simulations`, the API adds POST `/setups/<id>/run`, GET
`/results?setup_id=...`, `/results/<id>`, `/results/<id>/events`,
`/results/<id>/chart`, and allowlisted `/results/<id>/exports/<filename>`.
Outputs include `report.json`, streamed `events.csv`, source/config/profile/
calendar JSON, and artifact byte hashes. Per-result SQLite supports paged
events and bounded actual trace samples. Charts use only saved observed/modeled
equity events and disclose omitted intermediate events; financial aggregates
never derive from chart samples.

The result URL `#backtests/prop/result/<result-id>` is reached from its setup.
It shows outcome/reason, equity/balance, floor/high-water, suspension/trade
counts, dates, external fees and modeled net cash separately. Completed
operations can contain `passed`, `failed_drawdown`, `expired` or
`unresolved_data_end` account outcomes. Invalid inputs and storage/reconciliation
errors publish no completed result. Existing results reopen without source
re-execution or current-template resolution. Funded execution, stress and
Monte Carlo are rejected explicitly, never substituted with evaluation.

### Reusable profile fees

Account profiles can contain immutable `fee_defaults: ProfileFees` with matching
currency, a UTC `configured_on` date, separate nullable evaluation `attempt_fee`
and funded `activation_fee`, and `origin="user_supplied"`. At least one price
must be set; values are finite nonnegative exact decimals. A missing price means
unknown, never zero. These prices are distinct from sourced trading rules and
their source retrieval/effective dates. The sourced-rule version stays unchanged
when user pricing changes; the complete profile hash changes with its defaults.
Version `1.1.0` templates include prices supplied by the user on 2026-10-26:
standard evaluation **USD 49**, funded activation **USD 129**; alternatively
evaluation **USD 109**, funded activation **USD 0**. For each platform, the
existing `apex_50k_eod_<platform>` ID selects standard pricing and the distinct
`apex_50k_eod_<platform>_no_activation` ID selects the second option. Trading
rules are the same within a platform. Prices are marked user supplied, not
officially verified or assigned an inferred effective date. These defaults
apply to future setups only; existing custom prices take precedence. The
no-activation option requires a zero activation fee, including any funded
simulation override, and rejects contradictory nonzero/null defaults before
writing configuration. Evaluation charges only its chosen attempt price;
funded activation belongs only to funded mode, which remains unimplemented.

The existing `PropRunStore` catalog stores current defaults per platform in
`prop_profile_fees`; this is configuration, not another simulation store.
`PUT /api/prop-simulations/profiles/<profile-id>/fees` sets `attempt_fee` and/or
`activation_fee` as decimal strings (null for unknown). GET `/profiles` returns
resolved templates containing those defaults. The setup's reusable profile editor
saves prices once; future setups inherit them. `POST /setups` accepts an omitted
or null `fee` to inherit the selected phase default, or an explicit string for a
simulation override, including zero. Missing default plus missing override is an
operation error. Custom prices are not copied between platforms, pricing options
or phases.

Resolved config `fees.origin="profile_default"` requires the amount to equal the
corresponding value in the captured profile, never today's template. Overrides
retain `origin="user_supplied"`. Both amounts and provenance are hashed and
saved. External fees are charged once under the existing cash ledger semantics;
account capital, P&L, drawdown and target mechanics are unchanged. Editing defaults
changes only future snapshots; an existing setup must be saved as a new setup to
capture new prices. Earlier results and downloads retain their original bytes.

Pre-feature profile snapshots omit `fee_defaults` and retain their exact golden
hash. The reader accepts that legacy shape without consulting current defaults;
the writer likewise omits an absent optional default. Existing explicit setup
fees reopen as simulation overrides. Reusable fee settings are user supplied;
configuration does not claim a newly verified provider price or effective date.

### Reusable instrument profiles

`alphaquest/prop/instruments.py` defines strict, immutable `InstrumentProfile`
and `ResolvedInstrumentProfile` values. The initial `nq` / `mnq` catalog has
version **1.0.0**, reviewed **2026-10-26**, currency **USD**, tick **0.25**,
point values **20 / 2**, and Apex standard-contract weights **1 / 0.1**.
Profiles contain provider/platform applicability, CME specification URL, Apex
weight URL and dated evidence for evaluation/funded equivalence and instrument
availability on Rithmic, Tradovate and WealthCharts. Effective dates remain
unknown. Published commission schedules are availability evidence, not a
replacement for commissions already embedded in the completed backtest.

The setup's **Select instrument** control applies the selected contract units
and generates the interpretation; there are no required manual unit fields in
profile mode. Its read-only table, mismatch explanation and source links are
part of the normal setup workflow. Source tick size and point value must match
exactly as Decimal values; any known source symbol/currency must also match.
Missing identity/currency is a modeling declaration made by explicitly choosing
the profile, not a fact inferred from a file name or matching numeric settings.
Automatic selection is allowed only when structured source symbol, currency and
specifications all match. No NQ-to-MNQ, currency, fill or cost conversion occurs.
Contract weight controls limits only and never scales monetary P&L a second time.
Nonstandard aliases and unsupported instruments use the existing explicit custom
declaration; ambiguous symbols are not guessed into a contract family.

GET `/api/prop-simulations/instrument-profiles` returns sourced profile
snapshots/display values, optionally with metadata compatibility for a completed
`source_backtest_id`. POST `/setups` accepts an `instrument_profile_id` instead
of the five manual instrument fields; mixed/incomplete declarations are rejected.
The server resolves the profile and validates source/account compatibility,
independently of browser preflight, before publishing any setup. Unknown IDs,
incompatible currencies, changed tick/point values and unsupported provider/
platform mappings are operation errors, not financial account outcomes.

`InstrumentDeclaration.profile` embeds the full instrument snapshot/hash.
`SimulationConfig.instrument_profile_sha256` binds that identity into resolved
settings; source snapshots also hash the full declaration. These optional fields
are omitted when absent, with legacy readers retaining the exact old wire shape
and hashes. Saved selection IDs, declaration values and settings hashes must
agree. The adapter still revalidates actual source artifacts at check/execution
time; a previous metadata match is not execution authorization. Existing saved
setups/results resolve their captured profile, never the current catalog.
Template edits create different future settings/source identities without
changing earlier snapshots. Catalog outages allow saved checks/execution and
downloads, while saving edits to a profile waits for current templates.

New setup/result exports include `instrument.json`; result artifact manifests
hash its bytes alongside the other captured inputs. Results display the source
instrument/profile identity. Earlier custom declarations remain available through
**Custom / legacy declaration**, and earlier result downloads are preserved.
This increment does not add measured excursions, rolling contracts, broker/live
authorization, overnight exposure, variable source sizing, funded execution or
Monte Carlo.
