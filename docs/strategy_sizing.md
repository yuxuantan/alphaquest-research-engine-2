# Strategy sizing contracts

Implemented 2026-11-17. `alphaquest/strategy_sizing.py` is the shared contract;
each strategy module owns its `SIZING_SUPPORT`. Registration requires an explicit
declaration, including reasons for unsupported modes. There is no second list of
strategy IDs in Prop Sim admission. The code-owned strategy registry remains an
intentional security boundary: users cannot import arbitrary strategy scripts.

| Current strategy | Saved fixed-contract path scaling | Native fixed / percentage-risk account execution |
| --- | --- | --- |
| VWAP pullback | Local volume/risk sizing off; verified intraday source | EOD flatten on and local volume/risk sizing off. Uses the existing event accelerator when its one-entry/reset restrictions hold; otherwise the shared bar replay. |
| Twin Continuation | Fixed `qty`; verified intraday source | Immediate protection, reviewed session calendar, unshifted Chicago clock, 17:00–16:00 session. Both market momentum entries and breakout OCO stop entries are supported. |
| Consecutive Green Hold | Fixed contracts; only intraday source trades qualify for dated prop models | Unsupported. This strategy has no initial protective stop or guaranteed session exit. Adding either would change its trading rules; neither is fabricated. |

These are parameter-level capabilities, not claims about provider fills or future
profitability. Instrument, source integrity, complete holding prices, actual
intraday flatness and account-profile constraints are checked independently.
Campaign OOS and Monte Carlo qualification remain mandatory in the main Prop Sim
portal; implementing a sizing adapter does not qualify a campaign.

## Adding a strategy

1. Add its module and its normal entry in `strategies/registry.py`.
2. Declare `SIZING_SUPPORT = SizingSupport(...)` in that module. Supply validators
   for saved-path scaling and native account execution. A validator returns
   `None` when compatible, otherwise a concrete rejection reason. Validate the
   selected parameters, rather than treating the strategy name as proof.
3. Native support also requires explicit session settings and holding-coverage
   hooks, plus `on_bar_controlled(bar, position, admit_entry)`. Use the existing
   Bar/intents/execution engine. Generate a provisional entry with a causal
   initial stop; commit acceptance-dependent counters only after admission.
   `controlled_orders` is available for strategies whose opportunities are
   consumed on signal/submission (Twin's momentum rule deliberately does this).
4. Leave acceleration undeclared unless an exact acceleration adapter exists.
   Native sizing has a general replay implementation; it does not require a new
   numerical engine or a strategy-specific optimizer. The existing VWAP event
   compiler is an optional optimization with stricter constraints.
5. Add representative contract tests alongside the shared registration checks.
   Verify fixed-size signal/fill invariance and linear net/cost normalization,
   causal stop/quantity decisions, skips, cancellation, long/short gaps, session
   liquidation, provider floors and cash reconciliation. Test normal product
   APIs, durable downloads and the affected portal journey. A declaration alone
   is not a numerical qualification certificate.

Run `tests/test_strategy_sizing_contract.py` for every registration change, and
the strategy's execution tests. Native changes additionally select
`tests/test_strategy_sizing_api.py` and the affected existing native tests.

## Execution and causality

Fixed saved-path searches use the established phase adaptation and account
owners. They are exposure scenarios on a quantity-independent saved signal
path, with the existing fill/liquidity assumptions. Native searches instead run
the actual strategy through `execution.execute` and the same Evaluation/Funded
controllers for either fixed contracts or a percentage policy. No completed
trade tape is resized for native risk sizing.

Market entries use the completed decision price and known stop plan. Stop-entry
orders use their submitted trigger and precommitted stop/distance as the risk
reference. Both OCO children are sized from the same pre-entry account state
before seeing the next bar; only the first eligible trigger on the shared price
path is activated. Its sibling is cancelled. Unfilled quotes expire after their
one-bar lifetime. Gaps affect actual fills, not the already chosen quantity.
Acceptance, fill and cancellation counts remain separate.

Fill-relative stops remain fill-relative. Their planning stop is computed from
the known order reference, rounded to the adverse tick, with configured
entry/exit slippage and commissions included in planned loss. This is a risk
budget, not a guarantee against gaps. Actual SL/TP and provider floors follow
only the held suffix of the shared MultiCharts OHLC path (or ordered trade ticks
where already supported). Earlier extrema cannot stop an unfilled position.

Generic native simulations retain one signal state within each sampled block,
warm it using only its actual original prefix with entries rejected, and clone
mutable state independently. Twin counts observed warmup callbacks rather than
restarting warmup when the execution engine numbers another session locally.
Prefix caches are bounded and replay the original prefix on a cache miss.
The existing worker runtime, deterministic schedules, cancellation, progress,
phase metrics and AnalysisStore remain the owners. Generic bar replay can be
slower than the specialized VWAP event accelerator; correctness is independent
of whether acceleration exists.

The contract and strategy sources enter numerical provenance. Earlier sealed
reports remain readable and unchanged; incompatible frozen numerical packages
are not silently upgraded. A historical source lacking saved stop diagnostics
is not itself an execution input: native admission reconstructs causal proposals
from verified bars and current matching strategy identity, and still rejects an
incompatible source implementation.
