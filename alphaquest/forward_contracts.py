"""independent forward event contract; no historical trade adaptation."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Union
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .prop.sizing import AccountSizingState

ID=Annotated[str,Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')]
UUID=Annotated[str,Field(pattern=r'^[0-9a-f]{32}$')]
SHA=Annotated[str,Field(pattern=r'^[0-9a-f]{64}$')]


def number(value,*,nonnegative=False,positive=False):
    if type(value) is not str or len(value)>128 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)',value):
        raise ValueError('Use a finite plain decimal string, never a binary float or exponent.')
    try:amount=Decimal(value)
    except InvalidOperation:raise ValueError('Invalid decimal value.') from None
    if not amount.is_finite() or len(amount.as_tuple().digits)>40 or abs(amount.as_tuple().exponent)>20:
        raise ValueError('Decimal precision exceeds the exact event contract.')
    if nonnegative and amount<0 or positive and amount<=0:raise ValueError('Value must be '+('positive.' if positive else 'nonnegative.'))
    return value


def utc(value):
    if type(value) is not str or 'T' not in value:raise ValueError('UTC event timestamps require ISO date and time.')
    if value.endswith('-00:00'):raise ValueError('An unknown UTC offset is not an explicit UTC timestamp.')
    try:stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise ValueError('Invalid UTC event timestamp.') from None
    if stamp.utcoffset() is None or stamp.utcoffset().total_seconds()!=0:
        raise ValueError('Use explicit UTC event timestamps; source-local conversion belongs in the adapter.')
    return stamp.isoformat().replace('+00:00','Z')


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)


class PolicyBinding(Strict):
    campaign_id:UUID
    application_id:UUID
    phase:Literal['evaluation','funded']
    package_sha256:SHA
    family_preference_reason:str|None=Field(default=None,max_length=1000)


class Instrument(Strict):
    symbol:str=Field(min_length=1,max_length=40)
    tick_size:str
    point_value:str
    currency:Literal['USD']='USD'
    @field_validator('tick_size','point_value')
    @classmethod
    def positive(cls,value):return number(value,positive=True)


class Source(Strict):
    source_id:ID
    label:str=Field(min_length=1,max_length=120)
    adapter:Literal['timestamped_events_v1']='timestamped_events_v1'
    connection_claim:Literal['supplied_records_only']='supplied_records_only'
    position_cost_basis:Literal['fifo','unknown']='unknown'
    receiver_clock_provenance:Literal['server_wall_clock','synthetic_harness_clock']='server_wall_clock'


class Thresholds(Strict):
    maximum_position_contracts:int=Field(default=2,ge=1,le=10000)
    maximum_drawdown_cash:str='500'
    maximum_signal_to_order_seconds:int=Field(default=30,ge=0,le=86400)
    maximum_order_ack_seconds:int=Field(default=30,ge=0,le=86400)
    maximum_unprotected_seconds:int=Field(default=5,ge=0,le=3600)
    maximum_fill_latency_seconds:int=Field(default=60,ge=0,le=86400)
    maximum_market_data_age_seconds:int=Field(default=60,ge=1,le=86400)
    maximum_heartbeat_age_seconds:int=Field(default=60,ge=1,le=86400)
    maximum_clock_skew_seconds:int=Field(default=5,ge=0,le=300)
    maximum_slippage_ticks:str='2'
    maximum_commission_per_contract_side:str|None=None
    require_protective_stop:bool=True
    require_position_snapshot:bool=True
    minimum_trades_for_edge_check:int=Field(default=20,ge=2,le=10000)
    minimum_rolling_mean_net_per_trade:str|None=None
    edge_window_trades:int=Field(default=20,ge=2,le=10000)
    @field_validator('maximum_drawdown_cash','maximum_slippage_ticks','maximum_commission_per_contract_side')
    @classmethod
    def nonnegative(cls,value):return None if value is None else number(value,nonnegative=True)
    @field_validator('minimum_rolling_mean_net_per_trade')
    @classmethod
    def finite(cls,value):return None if value is None else number(value)
    @model_validator(mode='after')
    def enough_window(self):
        if self.minimum_trades_for_edge_check>self.edge_window_trades:
            raise ValueError('The edge observation window must hold the declared minimum trade count.')
        return self


def day(value):
    if type(value) is not str or str(date.fromisoformat(value)) != value:
        raise ValueError('Use canonical YYYY-MM-DD session dates.')
    return value


class FundedObservationPlan(Strict):
    schema_version: Literal['funded-observation-plan-v1'] = 'funded-observation-plan-v1'
    first_session: str
    cutoff_date_exclusive: str
    calendar_timezone: Literal['America/Chicago'] = 'America/Chicago'
    open_sessions: list[str] = Field(min_length=1, max_length=366)
    early_closes: dict[str, str]
    calendar_alignment: Literal['exact_saved_dates', 'declared_pattern_translation']
    transport_assumption: str | None = Field(default=None, min_length=1, max_length=2000)
    account_id: ID
    account_scope: Literal['one_fresh_funded_account_no_replacement'] = 'one_fresh_funded_account_no_replacement'
    initial_balance: str = '50000'
    currency: Literal['USD'] = 'USD'
    policy_implementation_claim: Literal['supplied_unchanged_frozen_policy'] = 'supplied_unchanged_frozen_policy'
    coverage_claim: Literal['all_signals_orders_fills_positions_and_cash'] = 'all_signals_orders_fills_positions_and_cash'

    @field_validator('first_session', 'cutoff_date_exclusive')
    @classmethod
    def dates(cls, value): return day(value)

    @field_validator('initial_balance')
    @classmethod
    def capital(cls, value): return number(value, positive=True)

    @model_validator(mode='after')
    def coherent(self):
        days = [day(value) for value in self.open_sessions]
        if days != sorted(set(days)) or days[0] != self.first_session or not all(self.first_session <= value < self.cutoff_date_exclusive for value in days):
            raise ValueError('Declare ordered unique open sessions throughout the exact half-open interval.')
        for key, value in self.early_closes.items():
            day(key)
            if key not in days or len(value) != 5 or value[2] != ':' or not value.replace(':', '').isdigit() or not 0 <= int(value[:2]) <= 23 or not 0 <= int(value[3:]) <= 59:
                raise ValueError('Early closes require an included open session and HH:MM clock.')
        if self.calendar_alignment == 'declared_pattern_translation':
            if not self.transport_assumption or not self.transport_assumption.strip():
                raise ValueError('Explicit calendar transport requires a predeclared rationale/assumption.')
        elif self.transport_assumption is not None:
            raise ValueError('An exact calendar comparison does not use a transport assumption.')
        return self


class MonitorDeclaration(Strict):
    schema_version:Literal['aq-forward-monitor-v1']='aq-forward-monitor-v1'
    monitor_id:UUID
    name:str=Field(min_length=1,max_length=120)
    observation_kind:Literal['synthetic_harness','paper','actual_import']
    policy_binding:PolicyBinding|None=None
    forecast_observation:FundedObservationPlan|None=None
    source:Source
    instrument:Instrument
    initial_balance:str='50000'
    thresholds:Thresholds=Field(default_factory=Thresholds)
    control_mode:Literal['advisory_only']='advisory_only'
    order_placement_enabled:Literal[False]=False
    @field_validator('order_placement_enabled',mode='before')
    @classmethod
    def no_orders(cls,value):
        if value is not False:raise ValueError('Order placement is unsupported; this field must be strict false.')
        return value
    @field_validator('initial_balance')
    @classmethod
    def capital(cls,value):return number(value,positive=True)
    @model_validator(mode='after')
    def binding(self):
        if self.observation_kind!='synthetic_harness' and self.source.receiver_clock_provenance!='server_wall_clock':
            raise ValueError('Only explicitly synthetic observations may declare a deterministic harness receiver clock.')
        if self.forecast_observation is not None and self.policy_binding is None:
            raise ValueError('A forecast observation needs authoritative current-policy membership.')
        if self.observation_kind!='synthetic_harness' and self.policy_binding is None:
            raise ValueError('Paper/actual observation requires server-verified current-policy authority.')
        return self


class BaseEvent(Strict):
    event_id:ID
    event_time_utc:str
    source_sequence:int|None=Field(default=None,ge=1)
    supersedes_event_id:ID|None=None
    correction_reason:str|None=Field(default=None,min_length=1,max_length=1000)
    @field_validator('event_time_utc')
    @classmethod
    def time(cls,value):return utc(value)
    @model_validator(mode='after')
    def correction(self):
        if bool(self.supersedes_event_id)!=bool(self.correction_reason):
            raise ValueError('Corrections require both an existing target event and an explicit reason.')
        if self.supersedes_event_id==self.event_id:raise ValueError('A correction needs a new immutable event ID.')
        return self


class Signal(BaseEvent):
    kind:Literal['signal']='signal'
    signal_id:ID
    side:Literal['buy','sell']
    quantity:int=Field(ge=1,le=10000)
    reference_price:str
    stop_price:str|None=None
    target_price:str|None=None
    @field_validator('reference_price','stop_price','target_price')
    @classmethod
    def price(cls,value):return None if value is None else number(value)


class Intent(BaseEvent):
    kind:Literal['intent']='intent'
    intent_id:ID
    signal_id:ID
    side:Literal['buy','sell']
    quantity:int=Field(ge=1,le=10000)
    order_type:Literal['market','limit','stop']='market'
    reference_price:str
    limit_price:str|None=None
    stop_price:str|None=None
    target_price:str|None=None
    @field_validator('reference_price','limit_price','stop_price','target_price')
    @classmethod
    def price(cls,value):return None if value is None else number(value)
    @model_validator(mode='after')
    def order_prices(self):
        if self.order_type=='limit' and self.limit_price is None:raise ValueError('Limit intent requires a known limit price.')
        if self.order_type=='stop' and self.stop_price is None:raise ValueError('Stop intent requires a known trigger price.')
        return self


class Order(BaseEvent):
    kind:Literal['order']='order'
    order_id:ID
    intent_id:ID
    side:Literal['buy','sell']
    quantity:int=Field(ge=1,le=10000)
    execution_kind:Literal['paper','actual','synthetic']


class OrderStatus(BaseEvent):
    kind:Literal['order_status']='order_status'
    order_id:ID
    status:Literal['acknowledged','cancelled','rejected']
    reason:str|None=Field(default=None,max_length=1000)


class Fill(BaseEvent):
    kind:Literal['fill']='fill'
    fill_id:ID
    order_id:ID
    side:Literal['buy','sell']
    quantity:int=Field(ge=1,le=10000)
    price:str
    commission:str
    execution_kind:Literal['paper','actual','synthetic']
    @field_validator('price')
    @classmethod
    def price_value(cls,value):return number(value)
    @field_validator('commission')
    @classmethod
    def fee(cls,value):return number(value,nonnegative=True)


class ProtectionIntent(BaseEvent):
    kind:Literal['protection_intent']='protection_intent'
    protective_order_id:ID
    order_id:ID
    protection_type:Literal['stop','target']
    side:Literal['buy','sell']
    quantity:int=Field(ge=1,le=10000)
    trigger_price:str
    @field_validator('trigger_price')
    @classmethod
    def price(cls,value):return number(value)


class Protection(BaseEvent):
    kind:Literal['protection']='protection'
    protective_order_id:ID
    order_id:ID
    protection_type:Literal['stop','target']
    side:Literal['buy','sell']
    quantity:int=Field(ge=1,le=10000)
    trigger_price:str
    status:Literal['active','cancelled','filled','rejected']
    @field_validator('trigger_price')
    @classmethod
    def price(cls,value):return number(value)


class Position(BaseEvent):
    kind:Literal['position']='position'
    signed_quantity:int=Field(ge=-10000,le=10000)
    average_entry_price:str|None=None
    account_balance:str|None=None
    @field_validator('average_entry_price','account_balance')
    @classmethod
    def money(cls,value):return None if value is None else number(value)


class Market(BaseEvent):
    kind:Literal['market']='market'
    price:str
    @field_validator('price')
    @classmethod
    def finite(cls,value):return number(value)


class Heartbeat(BaseEvent):
    kind:Literal['heartbeat']='heartbeat'


class Connection(BaseEvent):
    kind:Literal['connection']='connection'
    status:Literal['connected','disconnected','degraded']
    reason:str|None=Field(default=None,max_length=1000)


class Cash(BaseEvent):
    kind:Literal['cash']='cash'
    cash_event_id:ID
    category:Literal['payout_request','provider_deduction','trader_receipt','evaluation_purchase_fee','activation_fee']
    amount:str
    related_cash_event_id:ID|None=None
    request_amount_basis:Literal['unknown','trader_entitlement','gross_withdrawal']='unknown'
    expected_trader_amount:str|None=None
    @field_validator('amount','expected_trader_amount')
    @classmethod
    def positive(cls,value):return None if value is None else number(value,nonnegative=True)
    @model_validator(mode='after')
    def receipt_basis(self):
        if self.category!='payout_request' and (self.request_amount_basis!='unknown' or self.expected_trader_amount is not None):
            raise ValueError('Entitlement basis belongs only to a payout request.')
        if self.request_amount_basis=='trader_entitlement' and self.expected_trader_amount is not None and Decimal(self.expected_trader_amount)!=Decimal(self.amount):
            raise ValueError('A trader-entitlement request amount must equal its declared expected trader amount.')
        return self


class Void(BaseEvent):
    kind:Literal['void']='void'
    @model_validator(mode='after')
    def target(self):
        if self.supersedes_event_id is None:raise ValueError('A void must explicitly supersede a prior event.')
        return self


class AccountCoverage(BaseEvent):
    kind: Literal['account_coverage'] = 'account_coverage'
    plan_sha256: SHA
    package_sha256: SHA
    account_id: ID
    first_session: str
    cutoff_date_exclusive: str
    coverage: Literal['complete', 'partial']
    fresh_account: bool
    initial_balance: str
    currency: Literal['USD']
    frozen_policy_followed: bool
    terminal_status: Literal['active_at_cutoff', 'breached', 'inactivity', 'payout_limit_completed']
    terminal_at_utc: str | None = None
    replacement_accounts: int = Field(ge=0)
    pending_trader_cash: str | None
    complete_through_utc: str
    statement: str = Field(min_length=1, max_length=2000)

    @field_validator('first_session', 'cutoff_date_exclusive')
    @classmethod
    def dates(cls, value): return day(value)

    @field_validator('terminal_at_utc', 'complete_through_utc')
    @classmethod
    def times(cls, value): return None if value is None else utc(value)

    @field_validator('initial_balance', 'pending_trader_cash')
    @classmethod
    def amounts(cls, value): return None if value is None else number(value, nonnegative=True)

    @model_validator(mode='after')
    def outcome(self):
        if not 1 <= (date.fromisoformat(self.cutoff_date_exclusive)-date.fromisoformat(self.first_session)).days <= 365:
            raise ValueError('Coverage requires a bounded 1 through 365 civil-day interval.')
        if (self.terminal_status == 'active_at_cutoff') != (self.terminal_at_utc is None):
            raise ValueError('Ended accounts require a terminal clock; active-at-cutoff has no earlier terminal clock.')
        return self

class SizingDecision(BaseEvent):
    kind:Literal['sizing_decision']='sizing_decision'
    signal_id:ID
    position_event_id:ID
    context_known_at_utc:str
    account_state:AccountSizingState
    execution_timing:Literal['same_close','next_open']
    side:Literal['long','short']
    decision_reference_price:str
    initial_stop_price:str|None=None
    initial_stop_known_at_utc:str|None=None
    submitted_quantity:int=Field(ge=0,le=60)
    action:Literal['trade','skip']

    @field_validator('context_known_at_utc','initial_stop_known_at_utc')
    @classmethod
    def clocks(cls,value):return None if value is None else utc(value)

    @field_validator('decision_reference_price','initial_stop_price')
    @classmethod
    def prices(cls,value):return None if value is None else number(value)

    @model_validator(mode='after')
    def coherent(self):
        from datetime import datetime
        stamp=lambda value:datetime.fromisoformat(value.replace('Z','+00:00'))
        if stamp(self.context_known_at_utc)>stamp(self.event_time_utc):
            raise ValueError('The account context must be known at or before the decision.')
        if (self.initial_stop_price is None)!=(self.initial_stop_known_at_utc is None):
            raise ValueError('Initial stop price and known-at clock are supplied together.')
        if self.initial_stop_known_at_utc and stamp(self.initial_stop_known_at_utc)>stamp(self.event_time_utc):
            raise ValueError('The initial stop must be known at or before the decision.')
        if (self.action=='skip')!=(self.submitted_quantity==0):
            raise ValueError('A skip has zero quantity; a trade has positive quantity.')
        return self


Event=Annotated[Union[Signal,Intent,Order,OrderStatus,Fill,ProtectionIntent,Protection,Position,Market,Heartbeat,Connection,Cash,Void,AccountCoverage,SizingDecision],Field(discriminator='kind')]


class EventBatch(Strict):
    schema_version:Literal['aq-forward-events-v1']='aq-forward-events-v1'
    batch_id:UUID
    source_id:ID
    events:list[Event]=Field(min_length=1,max_length=5000)
    @model_validator(mode='after')
    def unique(self):
        ids=[event.event_id for event in self.events]
        if len(set(ids))!=len(ids):raise ValueError('A batch must not repeat an event ID.')
        return self


class Assessment(Strict):
    request_id:UUID
    as_of_utc:str
    @field_validator('as_of_utc')
    @classmethod
    def time(cls,value):return utc(value)


class Control(Strict):
    request_id:UUID
    action:Literal['pause','resume','retire']
    reason:str=Field(min_length=1,max_length=1000)
    acknowledged_snapshot_sha256:SHA|None=None
    @model_validator(mode='after')
    def recovery(self):
        if self.action=='resume' and self.acknowledged_snapshot_sha256 is None:
            raise ValueError('Resume requires acknowledgement of the current resolved assessment snapshot.')
        return self
