"""Optional ADX/pivot streams; executable signal/default source stays unchanged."""

from collections import deque
from decimal import localcontext
from types import SimpleNamespace

from ..strategy_features import Feature
from .vwap_pullback_risk_sizing import _ADX, VwapPullbackRiskSizing


def adx(bars, parameters):
    history = deque(maxlen=parameters.max_bars_back + 1)
    indicator = _ADX(parameters.adx_len)
    for bar in bars:
        history.append(bar)
        with localcontext() as context:
            context.prec = 50
            value = indicator.update(history) if bar.bar_number > parameters.max_bars_back else None
        yield value


def pivots(bars, parameters, name):
    # Reuse the exact strict-pivot implementation and warm-up convention.
    state = SimpleNamespace(_history=deque(maxlen=parameters.max_bars_back + 1), current_bar=0)
    for bar in bars:
        state._history.append(bar)
        state.current_bar = bar.bar_number - parameters.max_bars_back
        yield VwapPullbackRiskSizing._pivots(state, getattr(parameters, name))


def stop_pivots(bars, parameters):
    return pivots(bars, parameters, "stop_swing_len")


def target_pivots(bars, parameters):
    return pivots(bars, parameters, "target_swing_len")


features = (
    Feature("adx", "1", ("max_bars_back", "adx_len"), adx),
    Feature("stop_pivots", "1", ("max_bars_back", "stop_swing_len"), stop_pivots),
    Feature("target_pivots", "1", ("max_bars_back", "target_swing_len"), target_pivots),
)


def bind(strategy, readers):
    if "adx" in readers:
        strategy._adx = SimpleNamespace(update=lambda history: readers["adx"].at(history[-1].bar_number))
    original = strategy._pivots

    def cached_pivots(strength):
        name = "stop_pivots" if strength == strategy.parameters.stop_swing_len else "target_pivots"
        reader = readers.get(name)
        return reader.at(strategy._history[-1].bar_number) if reader else original(strength)
    strategy._pivots = cached_pivots
