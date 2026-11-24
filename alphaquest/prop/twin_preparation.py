"""Exact reusable Twin market features, with independent account/order state.

The ordinary execution engine still owns every fill and provider-floor exit.
The tape is compiled by the original strategy with entries declined, using only
its original causal prefix. It stores potential arms/crossings, not executed
trades. Skipping is limited to bars with no market decision or executable touch.
"""
from array import array
from bisect import bisect_right
import copy
from dataclasses import replace
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from functools import lru_cache
import hashlib
import json

from ..strategies.twin_continuation import TwinContinuation, Parameters, CT, minutes, hhmm
from ..strategy import BracketIntent, CloseIntent, EntryIntent, StopEntriesIntent
from .native_control import executable_floor_reference

VERSION='twin-causal-market-cache-v1'
# The account-dependent interpreter below is qualified against this strategy
# revision. A future strategy edit retains full replay until parity is reviewed.
QUALIFIED_STRATEGY_SHA256='3cd5d081a4ef24f67b5732c385c93888b3716081adb697889f0c8394a7a10e06'


def supports(strategy):
    from pathlib import Path
    from ..strategies import twin_continuation
    return (type(strategy) is TwinContinuation and not strategy.p.debug_log and
        hashlib.sha256(Path(twin_continuation.__file__).read_bytes()).hexdigest()==QUALIFIED_STRATEGY_SHA256)

ARM_FIELDS=('arm_atr','level_long','level_short','stop_long','stop_short')
STATE_FIELDS=('p','parameters','config','instrument_symbol','tick_size','entry_protection_policy',
    'oco_entry_policy','ohlc_path_policy','session_plan','previous_stamp','observed_bars',
    'armed','ok_long','ok_short','arm_atr','level_long','level_short','stop_long','stop_short',
    'arm_trades','total_trades','setup','pending_setup','was_holding','traded_today','last_date')


@lru_cache(maxsize=16384)
def price_bracket(p,tick,setup,side,entry,stop,atr):
    """Only market/fill-derived prices are memoized; no account state or quantity."""
    long=side=='long'
    if setup=='MO':stop=entry+(-p.mo_stop_points if long else p.mo_stop_points)
    else:
        if (stop>=entry if long else stop<=entry):return CloseIntent('BO-L0' if long else 'BO-S0',timing='next_open')
        if p.bo_max_stop_mult>0:
            stop=max(stop,entry-p.bo_max_stop_mult*atr) if long else min(stop,entry+p.bo_max_stop_mult*atr)
    if p.immediate_protection:
        stop=(stop/tick).to_integral_value(rounding=ROUND_FLOOR if long else ROUND_CEILING)*tick
    target=None
    if setup!='MO' and p.bo_target_mult>0:
        target=entry+(p.bo_target_mult*atr if long else -p.bo_target_mult*atr)
        target=(target/tick).to_integral_value(rounding=ROUND_CEILING if long else ROUND_FLOOR)*tick
    return BracketIntent(stop,target)


@lru_cache(maxsize=16384)
def protection(p,atr,stop,momentum):
    # Keep the strategy's original protection construction authoritative.
    view=object.__new__(TwinContinuation);view.p=p;view.arm_atr=atr;view.entry_protection_policy='multicharts'
    return TwinContinuation._protection(view,stop=stop,momentum=momentum)


@lru_cache(maxsize=16384)
def entry_orders(p,tick,atr,level_long,level_short,stop_long,stop_short,ok_long,ok_short):
    from ..strategy_sizing import initial_risk_intent
    orders=[]
    if ok_long:
        intent=EntryIntent(p.qty,'BO-L',timing='next_open',protection=protection(p,atr,stop_long,False))
        orders.append((initial_risk_intent(intent,level_long,tick),level_long))
    if ok_short:
        intent=EntryIntent(p.qty,'BO-S',side='short',timing='next_open',protection=protection(p,atr,stop_short,False))
        orders.append((initial_risk_intent(intent,level_short,tick),level_short))
    return StopEntriesIntent(tuple(orders))


@lru_cache(maxsize=16384)
def market_entry_risk(intent,reference,tick):
    from ..strategy_sizing import initial_risk_intent
    return initial_risk_intent(intent,reference,tick)


class _CompileTwin(TwinContinuation):
    def _close_15(self,position):
        super()._close_15(position)
        self.tape.record_arm(self,self.tr_n>=self.p.bo_atr_period)

    def _close_momentum(self,*args):
        # Calculate a potential crossing independently of an account's consumed
        # daily opportunity, then restore the original flat-prefix behavior.
        consumed=self.traded_today;self.traded_today=False
        fire=super()._close_momentum(*args)
        eligible=self.traded_today
        if eligible:self.tape.record_momentum(fire)
        self.traded_today=consumed or eligible
        return 0 if consumed else fire


class TwinMarketPreparation:
    MAX_PREFIX_BYTES=32*1024*1024
    def __init__(self,catalogue,factory,config,*,checkpoint,progress):
        self.catalogue=catalogue;self.factory=factory;self.config=config;self._calendar=None
        probe=factory();self.parameters=probe.parameters
        if type(probe) is not TwinContinuation or type(self.parameters) is not Parameters:
            raise ValueError('Twin market preparation requires its exact registered strategy.')
        self.arm_at=array('i',[-1])*len(catalogue.bars);self.arms=array('i');self.values=[];self._value_ids={}
        self.momentum={};self.snapshots={};self.prefix_records=[];self._digests=None
        self.snapshot_bytes=0;critical=set();boundaries={s.first_bar for s in catalogue.sessions}
        warm=_CompileTwin(self.parameters,execution_config=config,instrument_symbol=probe.instrument_symbol);warm.tape=self
        previous_date=None;previous_session=None;bo_exit_seen=mo_exit_seen=False
        for i,bar in enumerate(catalogue.bars):
            if i%1000==0:checkpoint();progress('causal_features',i)
            self.current=i
            if i in boundaries:
                critical.add(i);bo_exit_seen=mo_exit_seen=False
                if self.snapshot_bytes+16384<=self.MAX_PREFIX_BYTES:
                    self.snapshots[i]=self.state(warm);self.snapshot_bytes+=16384
            warm.validate_holding_bar(bar,None)
            if warm.session_plan!=previous_session:
                plan=warm.session_plan
                self.prefix_records.append((json.dumps(dict(session_date=plan.day.isoformat(),session_type=plan.kind,
                    scheduled_close=plan.close.isoformat() if plan.close else None),sort_keys=True)+'\n').encode())
                previous_session=plan
            local=bar.timestamp_utc.astimezone(CT);clock=local.hour*60+local.minute
            if local.date()!=previous_date:critical.add(i);previous_date=local.date()
            session_minute=(clock-1-minutes(self.parameters.bo_session_open))%1440
            exit_minute=(minutes(self.parameters.bo_exit_time)-minutes(self.parameters.bo_session_open))%1440
            session_end=(minutes(self.parameters.bo_session_close)-minutes(self.parameters.bo_session_open))%1440
            if not bo_exit_seen and session_minute+1>=exit_minute and session_minute<session_end:
                critical.add(i);bo_exit_seen=True
            if not mo_exit_seen and minutes(self.parameters.mo_exit_time)<=clock<=16*60:
                critical.add(i);mo_exit_seen=True
            if warm.session_plan.close and bar.timestamp_utc>=warm.session_plan.close:critical.add(i)
            warm.on_bar_controlled(replace(bar,tick_window=None) if bar.tick_window is not None else bar,None,lambda proposal:None)
            if self.arm_at[i]>=0 or i in self.momentum:critical.add(i)
            if i<=self.parameters.max_bars_back:critical.add(i)
        self.values=tuple(self.values);self.prefix_records=tuple(self.prefix_records)
        self.critical=tuple(sorted(critical));del self.current,self._value_ids
        progress('causal_features',len(catalogue.bars))
        from .native_preparation import PriceIndex
        progress('price_index',0)
        try:self.index=PriceIndex(catalogue.bars,config.tick_size)
        except ValueError:self.index=None  # Exact feature reuse remains valid for fractional-tick source prices.
        progress('price_index',len(catalogue.bars))
        self.accounted_bytes=(len(self.arm_at)*self.arm_at.itemsize+len(self.arms)*self.arms.itemsize+
            len(self.values)*128+len(self.critical)*32+self.snapshot_bytes+
            ((len(self.index.low)+len(self.index.high))*self.index.low.itemsize if self.index else 0))

    def __getstate__(self):return {**self.__dict__,'_digests':None,'_calendar':None}

    def record_arm(self,warm,ready):
        row=[]
        for field in ARM_FIELDS:
            value=getattr(warm,field)
            if value not in self._value_ids:self._value_ids[value]=len(self.values);self.values.append(value)
            row.append(self._value_ids[value])
        flags=int(ready)|int(warm.ok_long)*2|int(warm.ok_short)*4|int(warm.armed)*8
        self.arm_at[self.current]=len(self.arms);self.arms.extend((*row,flags))

    def record_momentum(self,fire):
        self.momentum[self.current]=(*self.momentum.get(self.current,()),fire)

    @staticmethod
    def state(warm):
        return dict(values={name:getattr(warm,name) for name in STATE_FIELDS},
            flattening=copy.deepcopy(warm.session_flattening),digest_sessions=warm.session_flattening['sessions'])

    def strategy(self,first,checkpoint):
        state=self.snapshots.get(first)
        if state is None:
            # Budget overflow retains exact original-prefix replay, not a
            # shortened history or an approximate indicator initialization.
            warm=self.factory()
            for i in range(first):
                if i%1000==0:checkpoint()
                bar=self.catalogue.bars[i];warm.validate_holding_bar(bar,None)
                warm.on_bar_controlled(bar,None,lambda proposal:None)
            state=self.state(warm)
        if self._digests is None:
            digest=hashlib.sha256();self._digests=[digest.copy()]
            for record in self.prefix_records:digest.update(record);self._digests.append(digest.copy())
        if self._calendar is None:self._calendar=self.factory().calendar
        result=object.__new__(CachedTwin);result.__dict__.update(state['values']);result.calendar=self._calendar
        result.session_flattening=copy.deepcopy(state['flattening'])
        result.session_digest=self._digests[state['digest_sessions']].copy()
        result.programme=self;result.source_index=None
        return result


class CachedTwin(TwinContinuation):
    """Only eligibility and actual-position decisions vary by replay account."""
    def _protection(self,*,stop=None,momentum=False):return protection(self.p,self.arm_atr,stop,momentum)

    def on_bar_controlled(self,bar,position,admit):
        intent=self.on_bar(bar,position)
        plan=self.session_plan
        if position is None and (plan.close is None or bar.timestamp_utc>=plan.close):return None
        if type(intent) is StopEntriesIntent:return admit(intent)
        if type(intent) is EntryIntent:return admit(market_entry_risk(intent,bar.close,self.tick_size))
        return intent

    def _on_bar(self,bar,position):
        p=self.p;i=self.source_index
        self.observed_bars=i+1;self.previous_stamp=bar.timestamp_utc
        plan=self._set_session(bar)
        if self.observed_bars<=p.max_bars_back:return None
        stamp=bar.timestamp_utc.astimezone(CT);date=stamp.date();clock=stamp.hour*60+stamp.minute;time=hhmm(clock)
        if self.was_holding and position is None:self.total_trades+=1;self.setup=None
        if position is not None and not self.was_holding:self.setup=self.pending_setup
        self.was_holding=position is not None
        start=minutes(p.bo_session_open);sm=(clock-1-start)%1440
        end=(minutes(p.bo_session_close)-start)%1440;fill_end=(minutes(p.bo_last_fill)-start)%1440
        flat=(minutes(p.bo_exit_time)-start)%1440
        offset=self.programme.arm_at[i]
        if offset>=0:
            self.armed=False;flags=self.programme.arms[offset+5]
            if position is None and flags&1:
                for j,name in enumerate(ARM_FIELDS):setattr(self,name,self.programme.values[self.programme.arms[offset+j]])
                self.ok_long=bool(flags&2);self.ok_short=bool(flags&4);self.armed=bool(flags&8);self.arm_trades=self.total_trades
        midnight_exit=False
        if date!=self.last_date:
            self.traded_today=False;midnight_exit=self.last_date is not None and self.setup=='MO' and position is not None
            self.last_date=date
        fire=0
        for possible in self.programme.momentum.get(i,()):
            if not self.traded_today and position is None:self.traded_today=True;fire=possible
        if fire:
            self.armed=False;self.pending_setup='MO'
            return EntryIntent(p.qty,'MO-L' if fire==1 else 'MO-S',side='long' if fire==1 else 'short',timing='next_open',protection=self._protection(momentum=True))
        if self.armed and (position is not None or self.total_trades>self.arm_trades):self.armed=False
        if position is not None:
            long=position.side=='long'
            session_end=bar.timestamp_utc==plan.close if plan.close else False
            if midnight_exit or (self.setup=='BO' and sm+1>=flat and sm<end) or session_end:
                self.was_holding=False;self.total_trades+=1;self.setup=None
                reason=('MO-LX2' if long else 'MO-SX2') if midnight_exit else 'session_close' if session_end else ('BO-LX' if long else 'BO-SX')
                return CloseIntent(reason)
            if self.setup=='MO' and p.mo_exit_time<=time<=1600:return CloseIntent('MO-LX' if long else 'MO-SX',timing='next_open')
            return price_bracket(p,self.tick_size,self.setup,position.side,position.entry_fill_price,self.stop_long if long else self.stop_short,self.arm_atr)
        if self.armed and sm+1<fill_end:
            self.pending_setup='BO'
            return entry_orders(p,self.tick_size,self.arm_atr,self.level_long,self.level_short,self.stop_long,self.stop_short,self.ok_long,self.ok_short)
        return None


def next_event(path):
    start=path.current+1;end=path.session.end_bar
    if start>=end:return end
    if path.programme.twin.index is None:return start
    # Preserve every accepted/cancelled/rejected working-entry submission.
    if type(path.next_order) in (EntryIntent,CloseIntent,StopEntriesIntent) or path.base.armed:return start
    critical=path.programme.twin.critical;j=bisect_right(critical,path.current)
    bound=min(end-1,critical[j] if j<len(critical) else end-1)
    if path.account.position is not None:
        if type(path.next_order) is not BracketIntent:return start
        orders=path.adapter.risk_orders(path.snapshot)
        floor=max(orders.account_floor_engine_equity,orders.daily_floor_engine_equity) if orders.daily_floor_engine_equity is not None else orders.account_floor_engine_equity
        stop=executable_floor_reference(path.snapshot,floor,path.config.tick_size,path.config.point_value)
        bracket=path.next_order;target=bracket.target_price;long=path.account.position.side=='long'
        if target is not None:
            penetration=path.config.tick_size*path.account.fill_assumptions.limit_penetration_ticks
            target=target+penetration if long else target-penetration
        lower=max(stop,bracket.stop_price) if long else target
        upper=target if long else min(stop,bracket.stop_price)
        hit=path.programme.twin.index.first_touch(start,bound+1,lower,upper)
        if hit is not None:return hit
    return bound
