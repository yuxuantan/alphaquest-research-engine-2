"""Native execution/phase-owner boundary and exact provider cash offsets.

Provider transitions remain in native_engine/lucid_engine. Fills and risk-order
arbitration remain in execution.py. This module only states their boundary and
reconciles two cash ledgers whose meanings are deliberately different.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Protocol

from alphaquest.decimal_math import add, subtract, multiply
from alphaquest.strategy import EntryIntent, Position


@dataclass(frozen=True)
class ExecutionSnapshot:
    timestamp_utc: datetime
    bar_number: int
    engine_initial_capital: Decimal
    engine_trade_cash: Decimal
    position: Position | None


@dataclass(frozen=True)
class KnownEntryProposal:
    """No future entry timestamp, next open, actual fill or completed-trade net."""
    decision_time_utc: datetime
    decision_bar_number: int
    side: Literal['long', 'short']
    timing: Literal['same_close', 'next_open']
    decision_reference_price: Decimal
    initial_stop_price: Decimal
    initial_stop_known_at_utc: datetime
    reason: str
    exit_deadline_utc: datetime | None


@dataclass(frozen=True)
class EntryAcceptance:
    opportunity_id: int
    action: Literal['accept', 'skip', 'halt']
    accepted_intent: EntryIntent | None
    sizing_decision: dict


@dataclass(frozen=True)
class SessionRiskOrders:
    """Equity barriers expressed in the engine's unchanged trading ledger.

    execution.py translates these to executable price levels for the current
    actual position and arbitrates them with the actual strategy bracket.
    Thresholds concern current marked equity, before a future exit commission.
    """
    session: date
    account_floor_engine_equity: Decimal
    daily_floor_engine_equity: Decimal | None
    entry_allowed: bool
    reason: str | None


@dataclass(frozen=True)
class SessionContext:
    session: date
    scheduled_close_utc: datetime
    calendar_version: str
    calendar_sha256: str
    observed_bar_count: int
    fully_observed_or_flat_after_entry_cutoff: bool
    kind: Literal['observed','modeled'] = 'observed'
    expected_bar_count: int | None = None

    def __post_init__(self):
        if type(self.session) is not date or self.scheduled_close_utc.tzinfo is None or self.scheduled_close_utc.utcoffset()!=timedelta(0):
            raise ValueError('Native session context requires an actual date and UTC close.')
        if not self.calendar_version or len(self.calendar_sha256)!=64 or any(c not in '0123456789abcdef' for c in self.calendar_sha256):
            raise ValueError('Native session context requires a versioned calendar SHA256.')
        if self.kind=='observed':
            if type(self.observed_bar_count) is not int or self.observed_bar_count<1 or self.fully_observed_or_flat_after_entry_cutoff is not True or self.expected_bar_count is not None:
                raise ValueError('Observed native context requires verified bars, not a modeled expected count.')
        elif self.kind=='modeled':
            if type(self.observed_bar_count) is not int or self.observed_bar_count!=0 or self.fully_observed_or_flat_after_entry_cutoff is not False or type(self.expected_bar_count) is not int or self.expected_bar_count<1:
                raise ValueError('Modeled native context has no observed target bars; declare only a positive expected source-bar count.')
        else:raise ValueError('Unknown native session context kind.')


class NativePhaseOwner(Protocol):
    """Methods implemented by the existing evaluation/funded phase owners."""
    def begin_session(self, session: SessionContext, snapshot: ExecutionSnapshot) -> None: ...
    def admit_entry(self, proposal: KnownEntryProposal, snapshot: ExecutionSnapshot) -> EntryAcceptance: ...
    def risk_orders(self, snapshot: ExecutionSnapshot) -> SessionRiskOrders: ...
    def after_entry_fill(self, snapshot: ExecutionSnapshot, acceptance: EntryAcceptance) -> None: ...
    def after_trade_close(self, trade, snapshot: ExecutionSnapshot, *, triggering_floor: str | None) -> None: ...
    def cancel_entry(self, acceptance: EntryAcceptance, snapshot: ExecutionSnapshot, reason: str) -> None: ...
    def end_session(self, session: SessionContext, snapshot: ExecutionSnapshot) -> None: ...


@dataclass
class ProviderCashBridge:
    """Exact mapping, not an account-transition or fill model.

    Normal backtest cash remains initial capital plus actual executed trade P&L.
    Provider equity is relative to a separately explicit configured capital and
    additionally excludes gross account withdrawals. Bank receipts do not enter
    either trading ledger. The initial backtest capital is never the risk base.
    """
    provider_initial_capital: Decimal = Decimal('50000')
    cumulative_gross_withdrawals: Decimal = Decimal('0')
    account_start_trading_net: Decimal = Decimal('0')

    def __post_init__(self):
        if self.provider_initial_capital != Decimal('50000'):
            raise ValueError('The supported native provider profiles require explicit capital 50000.')
        if not self.cumulative_gross_withdrawals.is_finite() or self.cumulative_gross_withdrawals < 0:
            raise ValueError('Invalid cumulative gross withdrawal.')

    def provider_equity(self, engine_trade_cash, engine_initial_capital):
        return subtract(subtract(subtract(engine_trade_cash, engine_initial_capital),self.account_start_trading_net), self.cumulative_gross_withdrawals)

    def provider_balance(self, engine_trade_cash, engine_initial_capital):
        return add(self.provider_initial_capital, self.provider_equity(engine_trade_cash, engine_initial_capital))

    def engine_barrier(self, provider_floor_from_initial, engine_initial_capital):
        return add(add(add(engine_initial_capital,self.account_start_trading_net), self.cumulative_gross_withdrawals), provider_floor_from_initial)

    def deduct_gross(self, amount):
        if not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0:
            raise ValueError('Withdrawal requires a finite nonnegative exact gross amount.')
        self.cumulative_gross_withdrawals = add(self.cumulative_gross_withdrawals, amount)

    def reconcile(self, engine_trade_cash, engine_initial_capital, provider_equity):
        trading = subtract(engine_trade_cash, engine_initial_capital)
        if add(add(provider_equity, self.cumulative_gross_withdrawals),self.account_start_trading_net) != trading:
            raise ValueError('Native account cash does not reconcile to actual trade P&L and gross withdrawals.')
        result=dict(trading_net_pnl=str(trading), provider_equity_from_initial=str(provider_equity),
                    cumulative_gross_withdrawals=str(self.cumulative_gross_withdrawals))
        if self.account_start_trading_net:result['prior_attempt_trading_net']=str(self.account_start_trading_net)
        return result


def executable_floor_reference(snapshot, absolute_engine_floor, tick_size, point_value):
    """Exact execution helper: first adverse tick touching marked equity floor.

    It produces only a trigger/reference level. Existing execution gap/stop
    slippage and commission routines remain authoritative for the actual fill.
    No future OHLC bar is an argument. Negative prices and short positions work.
    """
    position = snapshot.position
    if position is None:
        raise ValueError('An executable price barrier requires an actual position.')
    if tick_size <= 0 or point_value <= 0:
        raise ValueError('Tick and point value must be positive.')
    signed = Decimal(position.contracts*(1 if position.side == 'long' else -1))
    money_per_point = multiply(signed, point_value)
    # Exact finite arithmetic and integer ratios avoid any fixed precision cap.
    numerator = subtract(add(multiply(position.entry_fill_price, money_per_point),
                             absolute_engine_floor), snapshot.engine_trade_cash)
    denominator = multiply(money_per_point, tick_size)
    a,b = numerator.as_integer_ratio(); c,d = denominator.as_integer_ratio()
    top,bottom = a*d,b*c
    if bottom < 0: top,bottom = -top,-bottom
    ticks = top//bottom if position.side == 'long' else -((-top)//bottom)
    return multiply(Decimal(ticks), tick_size)


def actual_close_hit(actual_engine_equity, account_floor, daily_floor=None, *, triggering_floor=None):
    """Classify the actual fully charged exit; never truncate or rewrite it."""
    if triggering_floor not in (None,'account','daily'):
        raise ValueError('Unknown executable floor trigger.')
    if actual_engine_equity <= account_floor or triggering_floor=='account':return 2
    if triggering_floor=='daily' or (daily_floor is not None and actual_engine_equity<=daily_floor):return 1
    return 0


def exact_rule_values(value):
    """The saved rule's decimal text interpretation; never convert binary bits."""
    if type(value) is float:return Decimal(str(value))
    if isinstance(value,tuple):return tuple(exact_rule_values(item) for item in value)
    return value


def json_native(value):
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,(date,datetime)):return value.isoformat()
    if isinstance(value,dict):return {key:json_native(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [json_native(item) for item in value]
    return value


class NativeControlBase:
    """Shared execution adapter; provider transitions stay in phase owners."""
    def __init__(self,sizing,micros,*,max_micros,session_contexts,start_date,cutoff_date_exclusive):
        from .phase_profiles import SizingConfiguration,SizingTrace,positive_integer
        if type(sizing) is not SizingConfiguration:raise ValueError('Native control requires explicit common sizing and planning costs.')
        positive_integer('micros',micros,60);positive_integer('max_micros',max_micros,60)
        if type(session_contexts) is not dict or not session_contexts or any(type(v) is not SessionContext or k!=v.session for k,v in session_contexts.items()):
            raise ValueError('Native control requires an explicit verified session context mapping.')
        kinds={value.kind for value in session_contexts.values()}
        if len(kinds)!=1:raise ValueError('Native owner cannot mix observed and modeled session contexts.')
        self.context_kind=next(iter(kinds))
        self.start_date=date.fromisoformat(start_date) if type(start_date) is str else start_date
        self.cutoff=date.fromisoformat(cutoff_date_exclusive) if type(cutoff_date_exclusive) is str else cutoff_date_exclusive
        if type(self.start_date) is not date or type(self.cutoff) is not date or not self.start_date<self.cutoff:
            raise ValueError('Native observation dates must form a nonempty exclusive window.')
        if any(not self.start_date<=day<self.cutoff for day in session_contexts):raise ValueError('Native session lies outside the declared observation window.')
        self.sizing,self.micros,self.max_micros=sizing,micros,max_micros
        self.contexts=dict(session_contexts);self.bridge=ProviderCashBridge()
        self.sizing_trace=SizingTrace(sizing);self.events=[];self.session_trace=[]
        self._session=None;self._last_session=None;self._last_snapshot=None;self._engine_initial=None
        self._pending=None;self._active_acceptance=None;self._last_exit=None;self._decision_count=0
        self._daily_halt=False;self._finalized=False;self._trading_net=Decimal(0)
        self.can_trade=False;self.account_floor=Decimal(-2000);self.daily_floor=None;self.provider_cap=0

    def session_context(self,timestamp_utc):
        from .phase_lifecycle import session_date
        day=session_date(timestamp_utc)
        if day not in self.contexts:raise ValueError('Bar has no verified native session context.')
        return self.contexts[day]

    def _emit(self,event,**values):
        record=dict(sequence=len(self.events)+1,event=event,session=self._session.session if self._session else None)
        record.update(values);self.events.append(json_native(record))

    def _sync(self,snapshot):
        if type(snapshot) is not ExecutionSnapshot:raise ValueError('Native control requires an immutable execution snapshot.')
        if self._engine_initial is None:self._engine_initial=snapshot.engine_initial_capital
        elif self._engine_initial!=snapshot.engine_initial_capital:raise ValueError('Native continuation changed its original execution capital.')
        self._last_snapshot=snapshot
        self.equity=self.bridge.provider_equity(snapshot.engine_trade_cash,snapshot.engine_initial_capital)

    def _state(self):
        return json_native(dict(equity_from_initial=self.equity,balance=add(Decimal(50000),self.equity),
            account_floor_from_initial=self.account_floor,daily_floor_from_initial=self.daily_floor,
            provider_max_contracts=self.provider_cap,outcome=self.account_outcome))

    def begin_session(self,session,snapshot):
        if self._finalized or self._session is not None or snapshot.position is not None or self._pending is not None:
            raise ValueError('Native session may begin only once while flat with no pending entry.')
        if self.contexts.get(session.session)!=session or (self._last_session is not None and session.session<=self._last_session):
            raise ValueError('Native sessions must follow the verified chronology exactly.')
        expected_cash=self._last_snapshot.engine_trade_cash if self._last_snapshot is not None else snapshot.engine_initial_capital
        if snapshot.engine_trade_cash!=expected_cash:
            raise ValueError('Native continuation cash must equal the last closed execution snapshot; a fresh account cannot import unexplained P&L.')
        self._sync(snapshot);self._session=session;self._daily_halt=False
        self._phase_begin(session,snapshot)
        self._session_before=self._state();self._session_trades=0;self._session_skips=0
        self._emit('session_begin',state=self._session_before)

    def admit_entry(self,proposal,snapshot):
        from .sizing import KnownDecisionRisk,AccountSizingState,choose_quantity
        if self._session is None or snapshot.position is not None or self._pending is not None:
            raise ValueError('Native entry admission requires an active flat session without a pending order.')
        self._sync(snapshot);self._decision_count+=1
        if proposal.decision_time_utc!=snapshot.timestamp_utc or proposal.decision_bar_number!=snapshot.bar_number:
            raise ValueError('Entry proposal must refer to the current completed execution bar.')
        before=self._state()
        if self.can_trade and not self._daily_halt:
            risk=KnownDecisionRisk(sizing_decision_time_utc=proposal.decision_time_utc.isoformat(),
                initial_stop_known_at_utc=proposal.initial_stop_known_at_utc.isoformat(),
                previous_source_exit_utc=self._last_exit.isoformat() if self._last_exit else None,
                execution_timing=proposal.timing,side=proposal.side,
                decision_reference_price=proposal.decision_reference_price,initial_stop_price=proposal.initial_stop_price)
            state=AccountSizingState(initial_configured_capital='50000',equity_change_from_initial=self.equity,
                account_floor_from_initial=self.account_floor,daily_floor_from_initial=self.daily_floor,
                provider_max_contracts=self.provider_cap,user_max_contracts=min(self.micros,self.max_micros))
            decision=choose_quantity(self.sizing.policy,state,risk,self.sizing.planning_execution)
        else:
            decision=dict(quantity=0,action='skip',requested_contracts=0,caps={},
                reasons=['daily_halt' if self._daily_halt else self.account_outcome],
                denominator=self.sizing.policy.get('reference'),denominator_value=None,
                risk_budget=None,planned_risk_per_mnq=None,planned_total_risk='0')
        q=decision['quantity']
        decision.update(opportunity_id=self._decision_count,source_trade_id=f'native-opportunity-{self._decision_count}',
            state_before=before,sizing_decision_time_utc=proposal.decision_time_utc.isoformat(),
            decision_reference_price=str(proposal.decision_reference_price),initial_stop_price=str(proposal.initial_stop_price),
            session=str(self._session.session),phase=self.phase)
        intent=EntryIntent(q,proposal.reason,proposal.exit_deadline_utc,proposal.side,proposal.timing,proposal.initial_stop_price) if q else None
        acceptance=EntryAcceptance(self._decision_count,'accept' if q else ('skip' if self.can_trade and not self._daily_halt else 'halt'),intent,decision)
        if q:self._pending=acceptance
        else:self._session_skips+=1
        self.sizing_trace(decision);self._emit('entry_admission',**decision)
        return acceptance

    def risk_orders(self,snapshot):
        if self._session is None:raise ValueError('Native risk orders require an active session.')
        return SessionRiskOrders(self._session.session,
            self.bridge.engine_barrier(self.account_floor,snapshot.engine_initial_capital),
            self.bridge.engine_barrier(self.daily_floor,snapshot.engine_initial_capital) if self.daily_floor is not None else None,
            self.can_trade and not self._daily_halt,None if self.can_trade and not self._daily_halt else ('daily_halt' if self._daily_halt else self.account_outcome))

    def after_entry_fill(self,snapshot,acceptance):
        if self._pending!=acceptance or snapshot.position is None or snapshot.position.contracts!=acceptance.accepted_intent.contracts:
            raise ValueError('Native fill does not match its accepted quantity.')
        self._sync(snapshot);self._pending=None;self._active_acceptance=acceptance
        diagnostic={}
        planned=acceptance.sizing_decision.get('planned_risk_per_mnq')
        if planned is not None:
            from .sizing import PlanningExecution
            config=PlanningExecution.model_validate(self.sizing.planning_execution)
            intent=acceptance.accepted_intent;direction=Decimal(1 if intent.side=='long' else -1)
            distance=multiply(subtract(snapshot.position.entry_fill_price,intent.initial_stop),direction)
            fill_risk=add(multiply(add(distance,multiply(config.tick_size,Decimal(config.stop_exit_slippage_ticks))),Decimal(config.point_value)),
                          multiply(Decimal(2),config.commission_per_contract_per_side))
            diagnostic=dict(initial_stop_adverse_to_actual_fill=distance>0,
                fill_to_initial_stop_risk_per_mnq=str(fill_risk),
                fill_gap_risk_change_per_mnq=str(subtract(fill_risk,Decimal(planned))),
                fill_to_initial_stop_risk_interpretation='Actual entry fill to the original known stop, with declared stop-exit costs; diagnostic only, not a guaranteed stop fill or active-bracket claim.')
        self._emit('entry_fill',opportunity_id=acceptance.opportunity_id,quantity=snapshot.position.contracts,
            actual_fill_price=snapshot.position.entry_fill_price,state_after=self._state(),**diagnostic)

    def after_trade_close(self,trade,snapshot,*,triggering_floor=None):
        if snapshot.position is not None or self._active_acceptance is None:raise ValueError('Native completed trade must close its accepted filled position.')
        orders=self.risk_orders(snapshot);self._sync(snapshot)
        hit=actual_close_hit(snapshot.engine_trade_cash,orders.account_floor_engine_equity,
            orders.daily_floor_engine_equity,triggering_floor=triggering_floor)
        self._trading_net=add(self._trading_net,trade.net_pnl);self._session_trades+=1
        self._last_exit=trade.exit_time_utc
        if hit:self._daily_halt=True
        self._phase_close(trade,hit)
        reconciliation=self.bridge.reconcile(snapshot.engine_trade_cash,snapshot.engine_initial_capital,self.equity)
        self._emit('trade_close',opportunity_id=self._active_acceptance.opportunity_id,trade_number=trade.trade_number,
            quantity=trade.contracts,net_pnl=trade.net_pnl,total_commissions=trade.total_commissions,
            entry_fill_price=trade.entry_fill_price,exit_fill_price=trade.exit_fill_price,
            triggering_floor=triggering_floor,account_hit=hit,state_after=self._state(),conservation=reconciliation)
        self._active_acceptance=None

    def cancel_entry(self,acceptance,snapshot,reason):
        if self._pending!=acceptance:raise ValueError('Cancelled entry must match its accepted submission.')
        self._sync(snapshot);self._pending=None
        self._emit('entry_cancelled',opportunity_id=acceptance.opportunity_id,reason=reason)

    def end_session(self,session,snapshot):
        if self._session!=session or snapshot.position is not None or self._pending is not None or self._active_acceptance is not None:
            raise ValueError('Native session must finish once while actually flat without pending orders.')
        self._sync(snapshot);self._phase_end(session,snapshot)
        reconciliation=self.bridge.reconcile(snapshot.engine_trade_cash,snapshot.engine_initial_capital,self.equity)
        row=dict(date=str(session.session),state_before=self._session_before,state_after=self._state(),
            executed=self._session_trades,skipped=self._session_skips,conservation=reconciliation)
        self.session_trace.append(row);self._emit('session_end',**row)
        self._last_session=session.session;self._session=None

    def finish_replay(self):
        if self._session is not None or self._pending is not None or self._active_acceptance is not None or self._last_snapshot is None:
            raise ValueError('Native replay must be exhausted and flat before publication.')
        if set(self.contexts)!=set(date.fromisoformat(row['date']) for row in self.session_trace):
            raise ValueError('Native replay did not consume its complete verified session inventory.')
        if subtract(self._last_snapshot.engine_trade_cash,self._last_snapshot.engine_initial_capital)!=self._trading_net:
            raise ValueError('Native execution cash must reconcile to every actual completed trade and its costs.')
        if not self._finalized:
            self._phase_finish();self._finalized=True
        result=self._phase_result()
        sizing=self.sizing_trace.result()
        sizing['interpretation']='Quantities are accepted submissions, not completed trades. Actual fill, cancellation and completed-trade counts are separate; planning risk is not charged again.'
        result.update(mode='native_historical_chronological_replay',historical_paths=1,phase=self.phase,
            trace=self.session_trace,control_events=self.events,sizing=sizing,
            sizing_decisions=self.sizing_trace.decisions,trading_profit=str(self._trading_net),equity=str(self.equity),
            execution_counts=dict(accepted_submissions=sizing['summary']['trade_count'],
                filled_entries=sum(event['event']=='entry_fill' for event in self.events),
                completed_trades=sum(event['event']=='trade_close' for event in self.events),
                cancelled_entries=sum(event['event']=='entry_cancelled' for event in self.events),
                skipped_opportunities=sizing['summary']['skipped_count']),
            conservation=self.bridge.reconcile(self._last_snapshot.engine_trade_cash,self._last_snapshot.engine_initial_capital,self.equity),
            readiness='HISTORICAL_SCENARIO_ONLY',native_forecast_available=False,
            assumptions=['Actual native strategy callbacks and fills; quantity is admitted at the completed decision bar without the next open.',
                'Provider rules, OHLC intrabar ordering, execution liquidity and modeled settlement remain unverified assumptions.',
                'This component contains one historical path and does not select a policy. Optional native forecasts are separate; independent native IS campaigns perform policy selection.'])
        if self.context_kind=='modeled':
            result.pop('historical_paths',None);result.pop('native_forecast_available',None)
            result['mode']='native_modeled_path';result['observation_kind']='modeled'
            result['observed_target_history']=False
            result['modeled_sessions']=result.pop('observed_sessions',len(self.session_trace))
            if 'horizon_observations_complete' in result:
                result['modeled_horizon_complete']=result.pop('horizon_observations_complete')
            if 'strategy_state_on_retry' in result:
                result['strategy_state_on_retry']='Only the provider account resets here; the explicit modeled execution adapter supplies strategy reset and prior-prefix warmup.'
            result['readiness']='MODELED_SCENARIO_ONLY'
            result['assumptions']=[
                'Actual native execution replays observed source bars; account and cash dates use a separately declared modeled target calendar.',
                'Quantity is chosen from the completed source decision bar and current provider state, without its future entry fill.',
                'The declared empirical source-block draw law supplies strategy reset, strictly prior source warmup, source/model clock mapping and complete schedule identity.',
                'Target sessions are modeled, not observed future data. Provider rules, OHLC ordering and settlement remain unverified assumptions.']
        return json_native(result)
