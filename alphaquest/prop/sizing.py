"""Pure causal MNQ size decisions, not an account simulator.

Does not execute trades, mutate accounts or certify provider behavior.
Realized entry fills and completed-trade P&L are deliberately absent from inputs.
"""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
import re
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


def amount(value):
    if type(value) not in (str, Decimal):
        raise ValueError('Amounts require explicit finite decimal strings.')
    if type(value) is str and (len(value) > 196 or re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?|\.[0-9]+', value) is None):
        raise ValueError('Amounts require plain decimal strings without exponent or whitespace.')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Amounts require explicit finite decimal strings.') from exc
    if (not result.is_finite() or result.copy_abs() > Decimal('1e12')
            or len(result.as_tuple().digits) > 128 or result.as_tuple().exponent < -64):
        raise ValueError('Amount exceeds the bounded finite decimal contract.')
    return result


def instant(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.utcoffset() != timedelta(0):
        raise ValueError('Decision timestamps require explicit UTC.')
    return value


def session(value):
    return (value.astimezone(ZoneInfo('America/Chicago')).replace(tzinfo=None)+timedelta(hours=7)).date()


class SizingPolicy(Contract):
    """Percentage values are percent (0.5 means 0.5%), not fractions.

    Cushion guards are explicit opt-ins. They bound planned loss strictly
    below a touched floor; observed gaps may still exceed that planning loss.
    """
    kind: Literal['fixed_contracts', 'fixed_dollar_risk', 'percentage_risk']
    contracts: StrictInt | None = Field(default=None, ge=1, le=60)
    risk_dollars: Decimal | None = None
    risk_percent: Decimal | None = None
    reference: Literal['initial_configured_capital', 'current_account_balance', 'available_drawdown_cushion'] | None = None
    minimum_contracts: StrictInt = Field(default=1, ge=1, le=60)
    maximum_contracts: StrictInt = Field(default=60, ge=1, le=60)
    constrain_to_account_cushion: StrictBool = False
    constrain_to_daily_cushion: StrictBool = False

    @field_validator('risk_dollars', 'risk_percent', mode='before')
    @classmethod
    def money(cls, value):
        return amount(value) if value is not None else None

    @model_validator(mode='after')
    def coherent(self):
        present = {key for key in ('contracts', 'risk_dollars', 'risk_percent', 'reference') if getattr(self, key) is not None}
        expected = {'fixed_contracts': {'contracts'}, 'fixed_dollar_risk': {'risk_dollars'},
                    'percentage_risk': {'risk_percent', 'reference'}}[self.kind]
        if present != expected:
            raise ValueError('Declare only the inputs belonging to the selected policy.')
        if self.risk_dollars is not None and self.risk_dollars <= 0:
            raise ValueError('Dollar risk must be positive.')
        if self.risk_percent is not None and not 0 < self.risk_percent <= 100:
            raise ValueError('Percent risk must be positive and at most 100.')
        if self.minimum_contracts > self.maximum_contracts:
            raise ValueError('Minimum contracts cannot exceed maximum contracts.')
        return self


class AccountSizingState(Contract):
    """Pre-decision state; kernel equity and both floors exclude starting cash."""
    initial_configured_capital: Decimal
    equity_change_from_initial: Decimal
    account_floor_from_initial: Decimal
    daily_floor_from_initial: Decimal | None = None
    provider_max_contracts: StrictInt = Field(ge=0, le=60)
    user_max_contracts: StrictInt = Field(ge=0, le=60)

    @field_validator('initial_configured_capital', 'equity_change_from_initial', 'account_floor_from_initial', 'daily_floor_from_initial', mode='before')
    @classmethod
    def money(cls, value):
        return amount(value) if value is not None else None

    @model_validator(mode='after')
    def initial_positive(self):
        if self.initial_configured_capital <= 0:
            raise ValueError('Initial configured capital must be positive.')
        return self


class DecisionRisk(Contract):
    """Known order facts only; actual future entry fills are not accepted."""
    sizing_decision_time_utc: str
    initial_stop_known_at_utc: str
    entry_time_utc: str
    previous_source_exit_utc: str | None = None
    execution_timing: Literal['same_close', 'next_open']
    side: Literal['long', 'short']
    decision_reference_price: Decimal
    initial_stop_price: Decimal

    @field_validator('decision_reference_price', 'initial_stop_price', mode='before')
    @classmethod
    def price(cls, value):
        return amount(value)

    @model_validator(mode='after')
    def causal(self):
        decision, known, entry = map(instant, (self.sizing_decision_time_utc, self.initial_stop_known_at_utc, self.entry_time_utc))
        if not known <= decision <= entry:
            raise ValueError('Require stop-known-at <= sizing decision <= entry.')
        if self.execution_timing == 'same_close' and decision != entry:
            raise ValueError('Same-close sizing requires a matching decision and entry label.')
        if self.execution_timing == 'next_open' and decision >= entry:
            raise ValueError('Next-open sizing requires an earlier decision label.')
        if session(decision) != session(entry):
            raise ValueError('Cross-session sizing decisions are not supported by this session-state projection.')
        if self.previous_source_exit_utc and instant(self.previous_source_exit_utc) > decision:
            raise ValueError('The prior source trade was still open at the sizing decision.')
        distance = (self.decision_reference_price-self.initial_stop_price)*(1 if self.side == 'long' else -1)
        if distance <= 0:
            raise ValueError('The initial stop must be adverse to the known decision reference.')
        return self


class PlanningExecution(Contract):
    """Declared loss-side costs per simulated MNQ, not a second P&L charge."""
    tick_size: Decimal
    point_value: Literal['2'] = '2'  # Simulated MNQ; source NQ is normalized separately.
    entry_slippage_ticks: StrictInt = Field(default=0, ge=0)
    stop_exit_slippage_ticks: StrictInt = Field(default=0, ge=0)
    commission_per_contract_per_side: Decimal

    @field_validator('tick_size', 'commission_per_contract_per_side', mode='before')
    @classmethod
    def money(cls, value):
        return amount(value)

    @model_validator(mode='after')
    def valid(self):
        if self.tick_size <= 0 or self.commission_per_contract_per_side < 0:
            raise ValueError('Tick size must be positive and commission nonnegative.')
        return self


def ratio_floor(numerator, denominator, *, strict=False):
    """Largest whole q with q*denominator <= numerator (or < if strict)."""
    if numerator <= 0:
        return 0
    a, b = numerator.as_integer_ratio()
    c, d = denominator.as_integer_ratio()
    return max(0, (a*d-int(strict))//(b*c))


def choose_quantity(policy, state, risk=None, execution=None):
    """Return an auditable whole-MNQ decision without changing source or state.

    The caller owns source admission and account transitions. Stop and cost
    metadata may be absent for a fixed-contract policy without cushion guards.
    """
    policy = SizingPolicy.model_validate(policy)
    state = AccountSizingState.model_validate(state)
    risk = DecisionRisk.model_validate(risk) if risk is not None else None
    execution = PlanningExecution.model_validate(execution) if execution is not None else None
    needs_stop = policy.kind != 'fixed_contracts' or policy.constrain_to_account_cushion or policy.constrain_to_daily_cushion
    if needs_stop and (risk is None or execution is None):
        raise ValueError('This policy needs complete causal initial-stop and planning-execution metadata.')
    with localcontext() as ctx:
        ctx.prec = 256
        unit = None
        if needs_stop:
            distance = (risk.decision_reference_price-risk.initial_stop_price)*(1 if risk.side == 'long' else -1)
            if any(price % execution.tick_size for price in (risk.decision_reference_price, risk.initial_stop_price)):
                raise ValueError('Decision and stop prices must obey the declared executable tick grid.')
            unit = (distance + execution.tick_size*(execution.entry_slippage_ticks+execution.stop_exit_slippage_ticks))*Decimal(execution.point_value) + 2*execution.commission_per_contract_per_side
        cushion = state.equity_change_from_initial-state.account_floor_from_initial
        daily = state.equity_change_from_initial-state.daily_floor_from_initial if state.daily_floor_from_initial is not None else None
        basis = None
        if policy.kind == 'fixed_contracts':
            budget, requested = None, policy.contracts
        else:
            if policy.kind == 'percentage_risk':
                basis = {'initial_configured_capital': state.initial_configured_capital,
                         'current_account_balance': state.initial_configured_capital+state.equity_change_from_initial,
                         'available_drawdown_cushion': cushion}[policy.reference]
                budget = max(Decimal(0), basis)*policy.risk_percent/100
            else:
                budget = policy.risk_dollars
            requested = ratio_floor(budget, unit)
        caps = dict(policy=policy.maximum_contracts, provider=state.provider_max_contracts, user=state.user_max_contracts)
        if policy.constrain_to_account_cushion:
            caps['account_cushion'] = ratio_floor(cushion, unit, strict=True)
        if policy.constrain_to_daily_cushion and daily is not None:
            caps['daily_cushion'] = ratio_floor(daily, unit, strict=True)
        quantity = min(requested, *caps.values())
        reasons = [key+'_cap' for key,value in caps.items() if value < requested and value == quantity]
        if quantity < policy.minimum_contracts:
            quantity = 0
            reasons.append('below_minimum_tradable_quantity')
        return dict(quantity=quantity, action='trade' if quantity else 'skip', requested_contracts=requested,
                    denominator=policy.reference, denominator_value=str(basis) if basis is not None else None,
                    risk_budget=str(budget) if budget is not None else None,
                    planned_risk_per_mnq=str(unit) if unit is not None else None,
                    planned_total_risk=str(unit*quantity) if unit is not None else None,
                    caps=caps, reasons=reasons,
                    interpretation='Planning stop loss including declared costs; no gap guarantee. This amount sizes quantity only and is never deducted again from source net P&L.')
