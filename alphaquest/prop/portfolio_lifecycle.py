"""Actual native strategies under existing phase owners and one cash budget.

Shared accounts admit one open position at a time. No independent MAE sums,
synthetic netting, inferred concurrent fills or new provider transitions.
"""
from dataclasses import replace
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal

from ..execution import execute,ExecutionContinuation,Trade,EquityPoint
from ..strategy import EntryIntent
from ..strategies.registry import get_strategy
from .evaluation_profiles import NativeEvaluationController
from .funded_profiles import NativeFundedController
from .phase_profiles import SizingConfiguration
from .sizing import SizingPolicy
from .portfolio_cash import PortfolioCash
from .native_control import ExecutionSnapshot


class BudgetEvaluation(NativeEvaluationController):
    def __init__(self,*args,budget,slot,**kwargs):
        self.budget,self.slot=budget,slot
        super().__init__(*args,**kwargs)

    def _buy(self,day):
        if len(self.attempts)>=self.retry.max_attempts:return super()._buy(day)
        if not self.budget.buy(self.slot,str(self.fee),str(self.activation)):
            self._account_status='budget_wait';self.can_trade=False;return
        super()._buy(day)

    def _fail(self,day,state):
        super()._fail(day,state);self.budget.release(self.slot,state)

    def _activation_payment(self,day):
        if not self.activation_paid:self.budget.activate(self.slot,str(self.activation))
        super()._activation_payment(day)


class BasketStrategy:
    """One real position, deterministic known-signal priority, causal risk shares."""
    def __init__(self,members,owner,specifications,weights,config):
        self.owner,self.weights=owner,weights;self.active=None;self.last_position=False
        self.members={i:get_strategy(specifications[i]['strategy_id']).create(
            get_strategy(specifications[i]['strategy_id']).parameters(specifications[i]['parameters']),
            config,instrument_symbol=specifications[i]['symbol']) for i in members}
        self.priority=sorted(members,key=lambda i:(-weights[i],i))
        self.accepted=[];self.conflicts=0

    def on_bar(self,bar,position):raise ValueError('Portfolio strategies require causal account control.')
    def on_finish(self,bar,position):return None

    def allow_entry_fill(self,bar):
        strategy=self.members.get(self.active)
        return getattr(strategy,'allow_entry_fill',lambda b:True)(bar) if strategy else False

    def validate_holding_bar(self,bar,position):
        if position is not None:
            callback=getattr(self.members[self.active],'validate_holding_bar',None)
            if callback:callback(bar,position)

    def on_bar_controlled(self,bar,position,admit):
        # A close on this bar does not allow same-close reentry. All inactive
        # strategies still observe the current bar; declined signals do not commit.
        cooldown=self.last_position and position is None;self.last_position=position is not None
        if position is None and cooldown:self.active=None
        chosen=None
        for index in self.priority:
            owns=position is not None and self.active==index
            def accept(intent,index=index):
                nonlocal chosen
                if position is not None or chosen is not None or cooldown:
                    self.conflicts+=1;return None
                original=self.owner.sizing;policy=dict(original.policy)
                weight=self.weights[index]
                if policy['kind']=='percentage_risk':policy['risk_percent']=str(Decimal(policy['risk_percent'])*weight)
                elif policy['kind']=='fixed_dollar_risk':policy['risk_dollars']=str(Decimal(policy['risk_dollars'])*weight)
                else:
                    quantity=int(Decimal(policy['contracts'])*weight)
                    if not quantity:return None
                    policy['contracts']=quantity
                self.owner.sizing=SizingConfiguration(policy,original.initial_configured_capital,original.planning_execution)
                try:accepted=admit(intent)
                finally:self.owner.sizing=original
                if accepted is not None:
                    self.active=index;chosen=accepted
                    trace=self.owner.sizing_trace
                    decision=trace.decisions[-1] if trace.decisions and trace.summary['decision_count']<=trace.limit else None
                    if decision is not None:decision.update(portfolio_strategy=index,allocation_weight=str(weight))
                    self.accepted.append(dict(timestamp=bar.timestamp_utc.isoformat(),strategy=index,weight=str(weight),quantity=accepted.contracts))
                return accepted
            result=self.members[index].on_bar_controlled(bar,position if owns else None,accept)
            if owns:
                if result is not None:chosen=result
            elif type(result) is EntryIntent and result!=chosen:raise ValueError('Basket strategy returned an unaccepted entry.')
        return chosen


def run_lineup(context,allocation,*,capture=False,checkpoint=lambda:None,progress=lambda value:None):
    """One synchronized observed history, including every replacement and fee."""
    first,last=map(date.fromisoformat,(context['first'],context['last']));cutoff=last+timedelta(days=1)
    budget=PortfolioCash(context['monthly_cap'],str(cutoff));specs=context['strategies']
    slots=[];accounts=[];trades=[];decisions=[];transitions=[];counts=dict(evaluation_attempts=0,funded_accounts=0,
        funded_breaches=0,funded_payout_completions=0,funded_inactivity_closures=0,shared_signal_conflicts=0)
    if allocation['placement']=='separate':
        for i,count in enumerate(allocation['counts']):
            for _ in range(count):slots.append(dict(members=[i],weights={i:Decimal(1)},phase='evaluation',owner=None,cash=context['execution'].initial_capital))
    else:
        total=sum(allocation['weights']);weights={i:Decimal(n)/Decimal(total) for i,n in enumerate(allocation['weights']) if n}
        for _ in range(allocation['accounts']):slots.append(dict(members=list(weights),weights=weights,phase='evaluation',owner=None,cash=context['execution'].initial_capital))
    def snapshot(slot,end=None):
        if not capture or slot.get('owner') is None:return
        owner=slot['owner'];row=slot['episode']
        row.update(end=str(end) if end else None,outcome=owner.account_outcome,equity_from_initial=str(owner.equity),
            sizing=owner.sizing_trace.result(),sessions=owner.session_trace,control_events=owner.events,
            conservation=owner.bridge.reconcile(slot['cash'],context['execution'].initial_capital,owner.equity))
        row['sizing'].pop('decisions',None)
        if slot['phase']=='evaluation':row['attempts']=owner.attempts
    def install(slot,number,phase,day):
        snapshot(slot,day)
        policy=context[phase+'_sizing'];cap=policy.policy['maximum_contracts']
        args=dict(max_micros=cap,session_contexts={d:c for d,c in context['sessions'].items() if day<=d<cutoff},start_date=str(day),cutoff_date_exclusive=str(cutoff))
        if not args['session_contexts']:return False
        if phase=='evaluation':owner=BudgetEvaluation(context['evaluation_profile'],policy,cap,calendar=context['calendar'],
            retry=context['retry'],budget=budget,slot=number,**args)
        else:owner=NativeFundedController(context['funded_profile'],policy,cap,
            receipt_delay_calendar_days=context['receipt_delay'],receipt_amount_convention='usd_cents_half_up',**args)
        slot.update(owner=owner,phase=phase,cash=context['execution'].initial_capital,
            strategy=BasketStrategy(slot['members'],owner,specs,slot['weights'],context['execution']),payout_cursor=0)
        owner._sync(ExecutionSnapshot(datetime.combine(day,time(),timezone.utc),0,
            context['execution'].initial_capital,context['execution'].initial_capital,None))
        episode=dict(slot=number,phase=phase,start=str(day),members=slot['members'],weights={str(k):str(v) for k,v in slot['weights'].items()})
        slot['episode']=episode;accounts.append(episode)
        if phase=='funded':counts['funded_accounts']+=1
        return True
    def close_funded(slot,number,day):
        snapshot(slot,day)
        outcome=slot['owner'].account_outcome
        counts['funded_breaches']+=int(outcome=='blown');counts['funded_payout_completions']+=int(outcome=='paid_all')
        counts['funded_inactivity_closures']+=int(outcome=='inactive')
        transitions.append(dict(date=str(day),slot=number,event='funded_closed',outcome=outcome))
        slot.update(owner=None,phase='evaluation');budget.release(number,outcome)
    day=first
    while day<=last:
        checkpoint();budget.advance(day)
        # Rotate purchase/admission order by civil day so the budget does not
        # permanently privilege the first listed strategy. This policy is frozen.
        order=list(range(len(slots)));offset=(day-first).days%len(slots) if slots else 0;order=order[offset:]+order[:offset]
        for number in order:
            slot=slots[number]
            if slot['owner'] is None and not install(slot,number,'evaluation',day):continue
            owner=slot['owner']
            if slot['phase']=='evaluation':
                if owner._last_snapshot is not None:owner._advance_calendar(day,observed_session=day if day in context['sessions'] else None)
                if owner.outcome=='funded_ready':
                    transitions.append(dict(date=str(day),slot=number,event='funded_start'))
                    if not install(slot,number,'funded',day):continue
                    owner=slot['owner']
            else:
                owner._advance_calendar(day-timedelta(days=1))
                if owner.account_outcome!='open':
                    close_funded(slot,number,owner.terminal_date or day-timedelta(days=1))
                    if not install(slot,number,'evaluation',day):continue
                    owner=slot['owner'];owner._advance_calendar(day,observed_session=day if day in context['sessions'] else None)
            if day not in context['sessions']:continue
            sequence=[replace(bar,bar_number=i+1) for i,bar in enumerate(context['bars'][day])]
            if not sequence:raise ValueError('An observed portfolio session has no actual bars.')
            before=len(owner.sizing_trace.decisions);attempts=len(owner.attempts) if slot['phase']=='evaluation' else 0
            conflicts=slot['strategy'].conflicts
            for event in execute(sequence,slot['strategy'],context['execution'],account_control=owner,
                    continuation=ExecutionContinuation(context['execution'].initial_capital,slot['cash']),completion='require_flat'):
                if type(event) is EquityPoint:slot['cash']=event.equity
                elif type(event) is Trade and capture:
                    trades.append(dict(date=str(day),slot=number,phase=slot['phase'],side=event.side,contracts=event.contracts,
                        strategy=slot['strategy'].active,entry=event.entry_time_utc.isoformat(),exit=event.exit_time_utc.isoformat(),
                        entry_fill_price=str(event.entry_fill_price),exit_fill_price=str(event.exit_fill_price),
                        total_commissions=str(event.total_commissions),gross_pnl=str(event.gross_pnl),net_pnl=str(event.net_pnl)))
            counts['shared_signal_conflicts']+=slot['strategy'].conflicts-conflicts
            if capture:decisions.extend(dict(d,slot=number,date=str(day)) for d in owner.sizing_trace.decisions[before:])
            if slot['phase']=='evaluation':counts['evaluation_attempts']+=len(owner.attempts)-attempts
            else:
                for event in owner.payout_events[slot['payout_cursor']:]:budget.payout(number,event)
                slot['payout_cursor']=len(owner.payout_events)
                if owner.account_outcome!='open':
                    close_funded(slot,number,day)
        budget.receive_due()
        if (day-first).days%20==0:progress(dict(completed=(day-first).days+1,total=(last-first).days+1))
        day+=timedelta(days=1)
    # Last-day closure clocks still count when the final date is a weekend.
    # A replacement would start after this window and must not be purchased.
    for number,slot in enumerate(slots):
        if slot['owner'] is not None and slot['phase']=='funded':
            slot['owner']._advance_calendar(last)
            if slot['owner'].account_outcome!='open':close_funded(slot,number,slot['owner'].terminal_date or last)
    counts['evaluation_attempts']=sum(row['event']=='evaluation_purchase' for row in budget.ledger)
    for slot in slots:snapshot(slot)
    result=dict(allocation=allocation,cash=budget.result(),counts=counts,open_accounts=[dict(slot=i,phase=s['phase'],
        outcome=s['owner'].account_outcome if s['owner'] else 'awaiting_replacement',equity=str(s['owner'].equity) if s['owner'] else None) for i,s in enumerate(slots)],
        start=str(first),cutoff_exclusive=str(cutoff),history='One actual chronological path; no resampling or future forecast.')
    if capture:result.update(cash_ledger=budget.ledger,trades=trades,sizing_decisions=decisions,transitions=transitions,pending_settlements=budget.pending,accounts=accounts)
    return result
