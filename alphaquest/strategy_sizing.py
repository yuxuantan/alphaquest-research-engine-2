"""Strategy-owned sizing contracts; no strategy-ID allowlists or account engine.

Declarations are admission constraints, not certificates of numerical parity.
Saved-path scaling and causal native execution are independent capabilities.
"""
from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING

VERSION = 'strategy-sizing-contract-v1'


@dataclass(frozen=True)
class SizingSupport:
    fixed_path_check: object
    native_check: object
    session_settings: object = None
    holding_start: object = None
    accelerated_check: object = None

    def describe(self, parameters):
        fixed = self.fixed_path_check(parameters)
        native = self.native_check(parameters)
        return dict(version=VERSION,
            fixed_contracts=dict(supported=fixed is None, reason=fixed),
            percentage_risk=dict(supported=native is None, reason=native),
            native_fixed_contracts=dict(supported=native is None, reason=native),
            accelerated_native=bool(native is None and self.accelerated_check is not None
                                    and self.accelerated_check(parameters)))

    def require(self, parameters, mode):
        result = self.describe(parameters)[mode]
        if not result['supported']:
            raise ValueError(result['reason'])
        return self.describe(parameters)


def definition_for_parameters(parameters):
    from .strategies.registry import STRATEGIES
    matches = [definition for definition in STRATEGIES.values()
               if type(parameters) is definition.module.Parameters]
    if len(matches) != 1:
        raise ValueError('Sizing requires parameters from exactly one registered strategy.')
    return matches[0]


def native_settings(parameters):
    support = definition_for_parameters(parameters).sizing
    support.require(parameters, 'percentage_risk')
    return support.session_settings(parameters)


def native_session_plan(calendar, day, parameters):
    flat, buffer = native_settings(parameters)
    # Venue plan Close is shared. Its next-open cutoff requires a positive
    # buffer; same-close strategies use their own actual cutoff in _shape.
    return calendar.plan(day, flat, max(1, buffer))


def restore_parameters(values, strategy_id=None):
    from .strategies.registry import STRATEGIES, get_strategy
    from dataclasses import fields
    definitions = [get_strategy(strategy_id)] if strategy_id else [d for d in STRATEGIES.values()
        if {f.name for f in fields(d.module.Parameters)} == set(values)]
    if len(definitions) != 1:
        raise ValueError('Native parameters require a unique registered strategy identity.')
    return definitions[0].parameters(values)


def initial_risk_intent(intent, reference, tick):
    """Plan from a known decision/stop-order reference, never a future fill.

    Fill-relative protection remains fill-relative at execution. Its pre-entry
    risk plan includes conservative configured entry/exit slippage separately.
    """
    stop = intent.initial_stop
    plan = intent.protection
    long = intent.side == 'long'
    if stop is None and plan is not None:
        stop = plan.stop_price if plan.stop_price is not None else reference + (-plan.stop_distance if long else plan.stop_distance)
        if plan.max_stop_distance is not None:
            cap = reference + (-plan.max_stop_distance if long else plan.max_stop_distance)
            stop = max(stop, cap) if long else min(stop, cap)
        stop = (stop / tick).to_integral_value(rounding=ROUND_FLOOR if long else ROUND_CEILING) * tick
    if stop is None:
        raise ValueError('Percentage-risk execution requires a causal initial protective stop; none is invented.')
    if not (stop < reference if long else stop > reference):
        raise ValueError('Initial protective stop must be adverse to its known order reference.')
    return replace(intent, initial_stop=stop)


def controlled_orders(strategy, bar, position, admit):
    """Adapter for strategies whose signal opportunity is consumed on submission.

    Strategies with acceptance-dependent counters implement on_bar_controlled
    themselves. Account quantity is never passed into signal generation.
    """
    from .strategy import EntryIntent, StopEntriesIntent
    intent = strategy.on_bar(bar, position)
    plan = getattr(strategy, 'session_plan', None)
    if position is None and plan is not None and (plan.close is None or bar.timestamp_utc >= plan.close):
        return None
    if type(intent) is EntryIntent:
        return admit(initial_risk_intent(intent, bar.close, strategy.tick_size))
    if type(intent) is StopEntriesIntent:
        orders = tuple((initial_risk_intent(entry, price, strategy.tick_size), price)
                       for entry, price in intent.orders)
        return admit(StopEntriesIntent(orders))
    return intent
