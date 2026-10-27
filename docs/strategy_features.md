# Optional strategy feature streams

Every registered strategy receives shared optimization data preparation and
completed-trial reuse automatically. Feature streams are an optional code-owned
extension for expensive, data-only calculations. No optimizer changes or
strategy-name branches are needed to add another strategy's features.

Define an adapter module with `features` and `bind(strategy, readers)`, then
register it using `StrategyDefinition(module, factory, acceleration=adapter)`.
If the factory takes `execution_config`, set `accepts_execution_config=True`.
Without an adapter the normal factory and strategy callbacks run unchanged.

```python
from alphaquest.strategy_features import Feature

# build(bars, parameters) yields exactly one immutable value per selected bar.
# parameters contains ONLY these declared fields, already strategy-validated.
features = (Feature("moving_average", "1", ("lookback",), build),)

def bind(strategy, readers):
    # Install only readers that are present; uncached calculations keep working.
    # Read sequentially with readers["moving_average"].at(bar.bar_number).
    # Each trial gets fresh readers and a fresh strategy instance.
    strategy.moving_average_reader = readers.get("moving_average")
```

`build` receives a one-pass iterator of selected `Bar` values and a namespace of
only its declared dependencies. Preserve the strategy's causal behavior,
warm-up, session boundaries, numeric precision, rounding and missing-value rules.
Yield one value per bar, including warm-up placeholders. Compute inside your
numeric context, then exit that context **before yielding**; builders run in
lockstep. Do not consume future bars to produce an earlier bar's value. Features
must be independent of account/execution state, orders, fills, positions,
quantities, trade counts and nondeterministic/external inputs. Such state always
belongs to the fresh trial strategy.

The coordinator groups validated parameter sets by feature name/version and
only the declared dependency values. Repeated groups can share one immutable
stream; unrelated parameter changes must leave it unchanged. Selected data and
date bounds are implicit in the job-owned workspace, so features cannot leak
across sources/jobs. Change `version` when feature semantics change. All adapter
code belongs under `alphaquest/`; the engine identity hashes that code and
installed package versions before allowing completed-trial reuse.

The cache is an acceleration hint. It can be absent because a dependency set is
unique, the grid fits one worker wave, or the stream/storage budget is exhausted.
`bind` must preserve the ordinary calculation path for every absent reader.
Readers allow repeated access to the current bar and forward access only. Do
not retain them beyond the trial or mutate their values. Builders and consumers
remain code-owned; clients cannot submit modules, paths or serialized caches.
Temporary pickle streams are produced inside the private job workspace only,
never imported from a user-provided cache file.

`alphaquest/strategies/vwap_features.py` is the initial adapter. It reuses the
signal's existing ADX and strict-pivot implementations and leaves its executable
source/default hash unchanged. ADX declares `max_bars_back, adx_len`; each pivot
declares `max_bars_back` and its own strength. Stop and target readers can share
bar values without sharing mutable strategy state. VWAP and all trade-dependent
state continue through the original callbacks.

Qualify an adapter by comparing every execution event, equity point and relevant
strategy state against the ordinary strategy, not only aggregate metrics. Vary
all declared dependencies and unrelated parameters; include warm-up, dates,
session/DST boundaries, zero volume, long/short trades and ambiguous-bar behavior
where relevant. `tests/test_optimization_acceleration.py` contains these parity
checks for the first adapter and a separate synthetic future-strategy example.
Use `python -m alphaquest.benchmark_optimization` to establish actual benefit
for representative grids at the same worker count with result reuse disabled.
