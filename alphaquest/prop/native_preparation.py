"""Exact event indexing for the supported one-entry-per-reset VWAP capability.

This is a prepared input to execution.execute, never another fill/account engine.
Actual causal opportunities (including rejected ones) are compiled by the real
strategy. Static holding levels only skip observed bars proved unable to execute
an order. No completed trade tape is scaled. Detailed captures use full replay.
"""
from array import array
from bisect import bisect_right,bisect_left
from dataclasses import asdict, replace
from decimal import Decimal
from ..decimal_math import subtract
from .native_draws import NativePathPreparation,verify_catalogue,_parameters
from ..strategy import EntryIntent,CloseIntent,BracketIntent
from ..strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
from .native_control import executable_floor_reference

VERSION='native-vwap-causal-event-index-v1'


def capability(parameters):
    from ..strategy_sizing import definition_for_parameters
    support=definition_for_parameters(parameters).sizing
    support.require(parameters,'percentage_risk')
    return support.describe(parameters)['accelerated_native']


class PriceIndex:
    """Immutable exact integer-tick range extrema; first touch, never fill price."""
    def __init__(self,bars,tick):
        self.tick=tick;self.n=1
        while self.n<len(bars):self.n*=2
        limit=2**63-1;self.low=array('q',[limit])*(2*self.n);self.high=array('q',[-limit])*(2*self.n)
        for i,b in enumerate(bars):
            for price in (b.low,b.high):
                if price%tick or abs(price/tick)>=limit:raise ValueError('Prepared prices require exact representable whole ticks.')
            self.low[self.n+i]=int(b.low/tick);self.high[self.n+i]=int(b.high/tick)
        for i in range(self.n-1,0,-1):
            self.low[i]=min(self.low[2*i],self.low[2*i+1]);self.high[i]=max(self.high[2*i],self.high[2*i+1])

    def first_touch(self,start,end,lower,upper):
        from decimal import ROUND_FLOOR,ROUND_CEILING
        lo=int((lower/self.tick).to_integral_value(rounding=ROUND_FLOOR)) if lower is not None else -(2**63-1)
        hi=int((upper/self.tick).to_integral_value(rounding=ROUND_CEILING)) if upper is not None else 2**63-1
        def visit(node,left,right):
            if right<=start or left>=end or (self.low[node]>lo and self.high[node]<hi):return None
            if right-left==1:return left
            middle=(left+right)//2
            hit=visit(node*2,left,middle)
            return hit if hit is not None else visit(node*2+1,middle,right)
        return visit(1,0,self.n)


class NativeEventPreparation:
    """One immutable checked source programme per worker/source/cost definition."""
    VERSION=VERSION
    def __init__(self,catalogue,strategy_factory,config,*,checkpoint=lambda:None,progress=lambda *args:None):
        from time import monotonic
        total=len(catalogue.bars);last=0.;previous_stage=None
        def report(stage,done):
            nonlocal last,previous_stage
            now=monotonic()
            if stage!=previous_stage or done in (0,total) or now-last>=1:
                progress(stage,done,total);last=now;previous_stage=stage
        report('source_validation',0)
        self.catalogue=catalogue;self.checked=verify_catalogue(catalogue,checkpoint=checkpoint)
        report('source_validation',total)
        report('causal_features',0)
        self.config=config;self.factory=strategy_factory
        strategy=strategy_factory()
        self.parameters=strategy.parameters
        self.accelerated=capability(strategy.parameters)
        self.schedule_patterns={};self.native_layouts={}
        if not self.accelerated:
            self.legacy=NativePathPreparation(catalogue,strategy_factory,config,checkpoint=checkpoint)
            report('causal_features',total)
            return
        if type(strategy) is not VwapPullbackRiskSizing or strategy.config!=config or _parameters(strategy.parameters)!=catalogue.parameters_json:
            raise ValueError('Prepared native strategy or source identity differs.')
        capability(strategy.parameters);self.offers={};self.cutoffs={};self.session_endpoints={};self.calendar_sha256=strategy._calendar.sha256;self.symbol=strategy.instrument_symbol
        self.sessions={s.first_bar:s for s in catalogue.sessions}
        resets=[]
        self.legacy=object.__new__(NativePathPreparation)
        self.legacy.catalogue=catalogue;self.legacy.checked=self.checked;self.legacy.factory=strategy_factory
        self.legacy.config=config;self.legacy.max_bytes=NativePathPreparation.MAX_BYTES;self.legacy.bytes_used=0;self.legacy.snapshots={}
        for index,bar in enumerate(catalogue.bars):
            if index%1000==0:checkpoint();report('causal_features',index)
            if index in self.sessions:
                charge=4096+32*(len(strategy._history)+len(strategy._adx_history))
                if self.legacy.bytes_used+charge<=self.legacy.max_bytes:
                    self.legacy.snapshots[index]=NativePathPreparation.clone(strategy);self.legacy.bytes_used+=charge
            old_time=strategy._previous_time;old_current=strategy.current_bar
            offered=[]
            def admit(intent):
                target=strategy.last_target_high if intent.side=='long' else strategy.last_target_low
                offered.append((intent,BracketIntent(intent.initial_stop,target)))
                return None
            strategy.validate_holding_bar(bar,None)
            strategy.on_bar_controlled(replace(bar,tick_window=None),None,admit)
            # Reset detection uses the same observed HHMM crossing as the actual
            # strategy, including sparse pre-entry source inputs.
            from ..session_calendar import CT
            time=bar.timestamp_utc.astimezone(CT);hhmm=time.hour*100+time.minute
            if (strategy.current_bar==1 and old_current==0) or (old_time is not None and hhmm>strategy.parameters.day_reset_time>=old_time):resets.append(index)
            if offered:
                self.offers[index]=tuple(offered)
        report('causal_features',total)
        self.offer_indices=tuple(sorted(self.offers))
        for s in catalogue.sessions:
            j=bisect_left(self.offer_indices,s.first_bar)
            first_offer=self.offer_indices[j] if j<len(self.offer_indices) and self.offer_indices[j]<s.end_bar else None
            if first_offer is not None and not any(s.first_bar<=r<=first_offer for r in resets):
                raise ValueError('Observed source must reset entry-dependent state before its first daily opportunity.')
            # Snapshot the actual cutoff from reviewed source calendar.
            plan=strategy._calendar.plan(s.context.session,strategy.parameters.eod_flat_time,strategy.parameters.close_buffer_minutes)
            cutoff=plan.cutoff
            times=[catalogue.bars[i].timestamp_utc for i in range(s.first_bar,s.end_bar)]
            self.session_endpoints[s.first_bar]=(times[0],times[-1])
            self.cutoffs[s.first_bar]=s.first_bar+bisect_left(times,cutoff)
            if self.cutoffs[s.first_bar]>=s.end_bar-1:raise ValueError('No actual next-open liquidation bar after the source cutoff.')
        self.offer_indices=tuple(sorted(self.offers));report('price_index',0)
        self.index=PriceIndex(catalogue.bars,config.tick_size);report('price_index',total)
        self.accounted_bytes=len(self.index.low)*self.index.low.itemsize+len(self.index.high)*self.index.high.itemsize+len(self.offers)*512
        self.parameters=strategy.parameters

    def session_path(self,session,adapter):return NativeEventPath(self,session,adapter)


    def has_offers(self,session):
        i=bisect_left(self.offer_indices,session.first_bar)
        return i<len(self.offer_indices) and self.offer_indices[i]<session.end_bar


class NativeEventPath:
    """Private, checked event iterator used only by the ordinary engine."""
    def __init__(self,programme,session,adapter):
        self.programme=programme;self.session=session;self.adapter=adapter
        self.current=None;self.next_order=None;self.account=None;self.snapshot=None
        self.processed=0;self.skipped=0;self.taken=False;self.active_bracket=None
        self.base=NativePathPreparation.clone(_guard_template(programme.parameters,programme.config,programme.symbol,programme.calendar_sha256));self.parameters=self.base.parameters;self.config=self.base.config
        self.instrument_symbol=self.base.instrument_symbol;self.session_flattening=self.base.session_flattening

    def __iter__(self):
        i=self.session.first_bar
        while i<self.session.end_bar:
            self.skipped=i-(self.current+1 if self.current is not None else self.session.first_bar)
            self.current=i;self.processed+=1
            yield replace(self.programme.catalogue.bars[i],bar_number=self.processed)
            i=self._next()

    def after_bar(self,account,next_order,snapshot):self.account=account;self.next_order=next_order;self.snapshot=snapshot
    def on_bar(self,bar,position):raise ValueError('Prepared opportunities require actual account admission.')
    def on_finish(self,bar,position):return self.base.on_finish(bar,position)
    def validate_holding_bar(self,bar,position):return self.base.validate_holding_bar(bar,position)
    def allow_entry_fill(self,bar):return self.base.allow_entry_fill(bar)
    def on_bar_controlled(self,bar,position,admit):
        if position is not None:
            if not self.base._session_plan.allows(bar.timestamp_utc):return CloseIntent('eod_flat',timing='next_open')
            return self.active_bracket
        if self.taken:return None
        for intent,bracket in self.programme.offers.get(self.current,()):
            accepted=admit(intent)
            if accepted is not None:
                self.taken=True;self.active_bracket=bracket
                self.base._pending_entry_day=self.session.context.session
                return accepted
        return None

    def _next(self):
        start=self.current+1;end=self.session.end_bar
        if start>=end:return end
        if type(self.next_order) in (EntryIntent,CloseIntent):return start
        if self.account.position is not None:
            if type(self.next_order) is not BracketIntent:raise ValueError('Prepared holding requires the supported static bracket.')
            order=self.adapter.risk_orders(self.snapshot)
            floor=max(order.account_floor_engine_equity,order.daily_floor_engine_equity) if order.daily_floor_engine_equity is not None else order.account_floor_engine_equity
            stop=executable_floor_reference(self.snapshot,floor,self.config.tick_size,self.config.point_value)
            bracket=self.next_order;target=bracket.target_price;long=self.account.position.side=='long'
            if target is not None:
                penetration=self.config.tick_size*self.account.fill_assumptions.limit_penetration_ticks
                target=target+penetration if long else target-penetration
            lower=max(stop,bracket.stop_price) if long else target
            upper=target if long else min(stop,bracket.stop_price)
            cutoff=self.programme.cutoffs[self.session.first_bar]
            bound=min(end-1,max(start,cutoff))
            hit=self.programme.index.first_touch(start,bound+1,lower,upper)
            return hit if hit is not None else bound
        if self.taken:return end-1
        offers=self.programme.offer_indices;j=bisect_right(offers,self.current)
        return offers[j] if j<len(offers) and offers[j]<end else end-1


def run_generic_path(catalogue,schedule,owner,config,target_contexts,*,preparation,checkpoint,capture,terminal_early_exit):
    """Universal controlled replay; acceleration is optional, never admission.

    One signal state per sampled block, warmed on its actual prior prefix.
    Every holding bar uses execution.execute; no completed trade is resized.
    """
    from ..execution import execute, EquityPoint, ExecutionContinuation
    from .native_control import json_native
    from datetime import date
    if preparation.legacy is None:
        preparation.legacy=NativePathPreparation(catalogue,preparation.factory,config,checkpoint=checkpoint)
    continuation=None;captures=[];mappings=[];provenance={};captured=0;terminal=False
    for draw in schedule['draws']:
        checkpoint()
        block=catalogue.blocks[draw['source_block_index']]
        selected=catalogue.sessions[block.first_session:block.first_session+draw['used_sessions']]
        mapping={s.context.session:date.fromisoformat(d) for s,d in zip(selected,draw['target_sessions'],strict=True)}
        adapter=PreparedClockView(owner,{s.context.session:s.context for s in selected},target_contexts,mapping)
        strategy=preparation.legacy.strategy(selected[0].first_bar,checkpoint)
        for session in selected:
            checkpoint();adapter.active_source=session.context.session
            detailed=capture and captured<5
            if capture and not detailed and owner.retain_details:owner.finish_detail_capture()
            if detailed:captured+=1
            def bars():
                for i in range(session.first_bar,session.end_bar):
                    if i%1000==0:checkpoint()
                    yield replace(catalogue.bars[i],bar_number=i-session.first_bar+1)
            final=None;events=[]
            for value in execute(bars(),strategy,config,account_control=adapter,continuation=continuation,
                    completion='require_flat',capture_decisions=detailed,capture_risk=detailed):
                final=value
                if detailed and type(value) is not EquityPoint:events.append(dict(event_type=type(value).__name__,**json_native(asdict(value))))
            if type(final) is not EquityPoint or final.position_contracts:
                raise ValueError('Native generic replay must finish actually flat; no boundary liquidation is invented.')
            continuation=ExecutionContinuation(config.initial_capital,final.cash_balance)
            if detailed:captures.append(dict(source_session=str(session.context.session),target_session=str(mapping[session.context.session]),events=events))
            if owner.retain_details:
                provenance[str(mapping[session.context.session])]=dict(path_index=schedule['path_index'],draw_slot=draw['slot'],
                    source_session=str(session.context.session),target_session=str(mapping[session.context.session]))
                mappings.append(dict(source_session=str(session.context.session),target_session=str(mapping[session.context.session]),
                    observed_source_bars=session.end_bar-session.first_bar,processed_execution_bars=session.end_bar-session.first_bar,no_op_observed_bars_skipped=0))
            if terminal_early_exit:
                terminal=(owner.phase=='funded' and owner.account_outcome!='open') or (owner.phase=='evaluation' and
                    (owner.pass_date is not None or (getattr(owner,'first_attempt_only',False) and owner.attempts and owner.attempts[0]['outcome']!='open')))
            if terminal:break
        if terminal:break
    if terminal:owner.omit_terminal_sessions()
    result=owner.finish_replay()
    if capture:result['detail_capture']=dict(maximum_source_sessions=5,captured_source_sessions=captured,
        complete=len(owner._visited_sessions)<=captured,financial_outcomes_complete=True,all_requested_paths_retained=True)
    for name,field in (('control_events','session'),('trace','date'),('sizing_decisions','session')):
        for row in result.get(name,[]):row.update(provenance.get(row.get(field),{}))
    return dict(result=result,source_model_clock_mapping=mappings,captures=captures,
        schedule_sha256=schedule['schedule_sha256'],catalogue_sha256=catalogue.catalogue_sha256,
        preparation=dict(version='generic-controlled-bars-v1',intermediate_mtm_retained=False))


def run_prepared_path(catalogue,schedule,owner,strategy_factory,config,target_contexts,*,preparation,checkpoint=lambda:None,capture=False,terminal_early_exit=False):
    """Same account/fill owners, checked observed event inputs, no MTM claim."""
    from .native_draws import _ClockView
    from ..execution import execute,EquityPoint,ExecutionContinuation
    from datetime import date
    if preparation.catalogue is not catalogue or preparation.config!=config:
        raise ValueError('Prepared execution source/configuration differs.')
    if not preparation.accelerated:
        return run_generic_path(catalogue,schedule,owner,config,target_contexts,
            preparation=preparation,checkpoint=checkpoint,capture=capture,terminal_early_exit=terminal_early_exit)
    continuation=None;mappings=[];provenance={};captures=[];terminal=False;captured_sessions=0
    for draw in schedule['draws']:
        block=catalogue.blocks[draw['source_block_index']]
        selected=catalogue.sessions[block.first_session:block.first_session+draw['used_sessions']]
        mapping={s.context.session:date.fromisoformat(d) for s,d in zip(selected,draw['target_sessions'],strict=True)}
        for source_day,target_day in mapping.items():
            if not owner.retain_details:continue
            provenance[str(target_day)]=dict(path_index=schedule['path_index'],draw_slot=draw['slot'],source_session=str(source_day),target_session=str(target_day))
        adapter=PreparedClockView(owner,{s.context.session:s.context for s in selected},target_contexts,mapping)
        for session in selected:
            if terminal:break
            checkpoint();adapter.active_source=session.context.session;path=None;processed=0;final=None
            detailed=capture and captured_sessions<5
            if capture and not detailed and owner.retain_details:owner.finish_detail_capture()
            if detailed:
                captured_sessions+=1
                strategy=preparation.legacy.strategy(session.first_bar,checkpoint)
                values=(replace(catalogue.bars[i],bar_number=i-session.first_bar+1) for i in range(session.first_bar,session.end_bar))
                events=[]
                for value in execute(values,strategy,config,account_control=adapter,continuation=continuation,completion='require_flat',capture_decisions=True,capture_risk=True):
                    final=value
                    if type(value) is not EquityPoint:events.append(value)
                processed=session.end_bar-session.first_bar
                from .native_control import json_native
                from dataclasses import asdict
                captures.append(dict(source_session=str(session.context.session),target_session=str(mapping[session.context.session]),events=[dict(event_type=type(e).__name__,**json_native(asdict(e))) for e in events]))
            elif not preparation.has_offers(session):
                # Compiler proved this flat source session has no causal entry,
                # independent of account quantity. Run real calendar/account
                # transitions, without constructing a no-op execution account.
                from .native_control import ExecutionSnapshot
                cash=continuation.trading_cash if continuation is not None else config.initial_capital
                first_stamp,last_stamp=preparation.session_endpoints[session.first_bar]
                before=ExecutionSnapshot(first_stamp,1,config.initial_capital,cash,None)
                after=ExecutionSnapshot(last_stamp,session.end_bar-session.first_bar,config.initial_capital,cash,None)
                adapter.begin_session(session.context,before);adapter.end_session(session.context,after)
                final=EquityPoint(session.end_bar-session.first_bar,last_stamp,cash,subtract(cash,config.initial_capital),Decimal(0),cash,0)
            else:
                path=preparation.session_path(session,adapter)
                for value in execute(path,path,config,account_control=adapter,continuation=continuation,completion='require_flat',prepared_path=path):final=value
            if type(final) is not EquityPoint or final.position_contracts:raise ValueError('Prepared native source did not finish actually flat.')
            continuation=ExecutionContinuation(config.initial_capital,final.cash_balance)
            if path is not None:processed=path.processed
            if owner.retain_details:mappings.append(dict(source_session=str(session.context.session),target_session=str(mapping[session.context.session]),
                observed_source_bars=session.end_bar-session.first_bar,processed_execution_bars=processed,
                no_op_observed_bars_skipped=session.end_bar-session.first_bar-processed))
            if terminal_early_exit:
                terminal=(owner.phase=='funded' and owner.account_outcome!='open') or (owner.phase=='evaluation' and (owner.pass_date is not None or (getattr(owner,'first_attempt_only',False) and owner.attempts and owner.attempts[0]['outcome']!='open')))
        if terminal:break
    if terminal:owner.omit_terminal_sessions()
    result=owner.finish_replay()
    if capture:result['detail_capture']=dict(maximum_source_sessions=5,captured_source_sessions=captured_sessions,
        complete=len(owner._visited_sessions)<=captured_sessions,financial_outcomes_complete=True,all_requested_paths_retained=True)
    for name,field in (('control_events','session'),('trace','date'),('sizing_decisions','session')):
        for row in result.get(name,[]):row.update(provenance.get(row.get(field),dict(path_index=schedule['path_index'],draw_slot=None,source_session=None,target_session=row.get(field))))
    return dict(result=result,source_model_clock_mapping=mappings,captures=captures,
        schedule_sha256=schedule['schedule_sha256'],catalogue_sha256=catalogue.catalogue_sha256,
        preparation=dict(version=VERSION,intermediate_mtm_retained=False))


class NativeSchedulePreparation:
    """Versioned, index-addressed V2 common uniforms and complete source pools.

    A float64 PCG64 uniform belongs to [seed, phase, path_index], then slot order.
    Changing policy or historical weights never changes these coordinates. Every
    requested path is retained; cache overflow regenerates identical row values.
    """
    VERSION='native-percentage-schedule-v2'
    MAX_UNIFORM_BYTES=32*1024*1024
    def __init__(self,catalogue,contexts,parameters,*,phase,seed,simulations,start,cutoff):
        import numpy as np
        from .native_draws import build_schedule,_hash
        self.catalogue=catalogue;self.contexts=contexts;self.phase=phase;self.seed=seed;self.simulations=simulations
        self.start=start;self.cutoff=cutoff
        from .native_control import NativeSessionInventory
        self.contexts=NativeSessionInventory(contexts,start,cutoff)
        base=build_schedule(catalogue,contexts,parameters,phase=phase,seed=seed,path_index=0,start_date=start,cutoff_date_exclusive=cutoff)
        self.templates=base['draws'];self.pools={r['pool_id']:r['indices'] for r in base['pools']}
        self.pool_slots={key:np.asarray([i for i,t in enumerate(self.templates) if t['pool_id']==key],dtype=np.int32) for key in self.pools}
        self.uniforms=None;n=len(self.templates)
        if simulations*n*8<=self.MAX_UNIFORM_BYTES:self.uniforms=np.asarray([self.uniform(i) for i in range(simulations)])
        self.identity=_hash(dict(version=self.VERSION,catalogue=catalogue.catalogue_sha256,phase=phase,seed=seed,
            simulations=simulations,start=str(start),cutoff=str(cutoff),contexts=[str(d) for d in contexts],pools=self.pools,
            rng='PCG64 SeedSequence([seed,phase_index,path_index]); float64 random per slot; floor(u*total_weight)'))

    def uniform(self,index):
        import numpy as np
        return np.random.default_rng(np.random.SeedSequence([self.seed,0 if self.phase=='evaluation' else 1,index])).random(len(self.templates))

    def paths(self,weights=None,*,_first=0,_end=None):
        import numpy as np
        from .native_draws import NativeHistoryPoolUnavailable
        from hashlib import sha256
        tables={}
        for key,pool in self.pools.items():
            w=np.ones(len(pool),dtype=np.int64) if weights is None else np.asarray([weights['origin_counts'][i] for i in pool],dtype=np.int64)
            cdf=np.cumsum(w);total=int(cdf[-1])
            if not total:raise NativeHistoryPoolUnavailable('Historical native source pool has zero origin weight; no redraw or uniform fallback.')
            tables[key]=(np.asarray(pool,dtype=np.int32),cdf,total)
        for first in range(_first,self.simulations if _end is None else _end,128):
            end=min(first+128,self.simulations,self.simulations if _end is None else _end)
            uniforms=self.uniforms[first:end] if self.uniforms is not None else np.asarray([self.uniform(i) for i in range(first,end)])
            chosen=np.empty(uniforms.shape,dtype=np.int32)
            for key,(pool,cdf,total) in tables.items():
                slots=self.pool_slots[key]
                chosen[:,slots]=pool[np.searchsorted(cdf,np.floor(uniforms[:,slots]*total).astype(np.int64),side='right')]
            for offset,row in enumerate(chosen):
                index=first+offset
                draws=NativeDrawSequence(self.catalogue,self.templates,row)
                yield dict(version=self.VERSION,path_index=index,phase=self.phase,seed=self.seed,start_date=str(self.start),
                    cutoff_date_exclusive=str(self.cutoff),draws=draws,
                    schedule_sha256=sha256(self.identity.encode()+index.to_bytes(8,'little')+row.tobytes()).hexdigest(),
                    catalogue_sha256=self.catalogue.catalogue_sha256,source_block_indices=row.tolist())


from dataclasses import dataclass
@dataclass(frozen=True)
class NativeStrategyFactory:
    parameters:object
    config:object
    symbol:str
    def __call__(self):
        from ..strategy_sizing import definition_for_parameters
        return definition_for_parameters(self.parameters).create(self.parameters,self.config,instrument_symbol=self.symbol)



def worker_programme(programme,directory,*,checkpoint=lambda:None):
    """Serialize prepared numerical inputs, excluding mutable strategies/warmups."""
    from dataclasses import replace
    import copy
    result=copy.copy(programme)
    result.catalogue=replace(programme.catalogue,bars=NativeBarSequence(programme.catalogue,directory,checkpoint=checkpoint))
    result.checked=result.catalogue;result.legacy=None
    result.schedule_patterns={};result.native_layouts={}
    result.factory=NativeStrategyFactory(programme.parameters,programme.config,programme.factory().instrument_symbol)
    return result


_loaded_contexts={}
def _native_batch(task):
    """Existing Runtime worker; one context load, multiple full account paths."""
    from pathlib import Path
    from hashlib import sha256
    import pickle
    from time import monotonic
    filename,expected,first,end,settings=task
    if filename not in _loaded_contexts:
        raw=Path(filename).read_bytes()
        if sha256(raw).hexdigest()!=expected:raise ValueError('Native worker context changed.')
        if len(_loaded_contexts)>=2:_loaded_contexts.pop(next(iter(_loaded_contexts)))
        _loaded_contexts[filename]=pickle.loads(raw)
    context=_loaded_contexts[filename];programme=context['programme'];pattern=context['pattern']
    rows=[];next_check=0.
    def checkpoint():
        nonlocal next_check
        if monotonic()>=next_check:
            if Path(context['stop_file']).exists():raise RuntimeError('Native account execution stopped.')
            next_check=monotonic()+.1
    for schedule in pattern.paths(context.get('weights'),_first=first,_end=end):
        index=schedule['path_index']
        checkpoint()
        output=_run_one(programme,pattern,schedule,settings,capture=False,checkpoint=checkpoint)
        rows.append(output)
    return rows


def _make_native_owner(pattern,settings):
    from .phase_profiles import EvaluationProfile,FundedProfile,SizingConfiguration
    from .evaluation_optimization import SequentialRetry
    from .phase_search import PhaseCalendar
    common=dict(max_micros=settings['max_micros'],session_contexts=pattern.contexts,start_date=pattern.start,cutoff_date_exclusive=pattern.cutoff)
    sizing=SizingConfiguration(**settings['sizing'])
    if pattern.phase=='funded':
        from .funded_profiles import NativeFundedController
        owner=NativeFundedController(FundedProfile(**settings['profile']),sizing,settings['micros'],**common,
            receipt_delay_calendar_days=settings['receipt_delay_calendar_days'],receipt_amount_convention=settings['receipt_amount_convention'])
        owner.prepared_execution=True;return owner
    from .evaluation_profiles import NativeEvaluationController
    raw=dict(settings['calendar']);raw['start_dates']=tuple(raw['start_dates']);raw['closures']=tuple(raw.get('closures',()))
    owner=NativeEvaluationController(EvaluationProfile(**settings['profile']),sizing,settings['micros'],**common,
        calendar=PhaseCalendar(**raw),retry=SequentialRetry(**settings['retry']))
    owner.prepared_execution=True
    owner.first_attempt_only=settings['profile']['profile_id']=='apex-50k-eod'
    return owner


def _run_one(programme,pattern,schedule,settings,*,capture,checkpoint):
    owner=_make_native_owner(pattern,settings)
    owner.set_detail_capture(capture)
    output=run_prepared_path(programme.catalogue,schedule,owner,programme.factory,programme.config,pattern.contexts,
        preparation=programme,checkpoint=checkpoint,capture=capture,terminal_early_exit=True)
    result=output['result']
    if not capture:
        for key in ('control_events','trace','sizing_decisions'):result.pop(key,None)
        result['sizing']={'summary':result['sizing']['summary']}
        if pattern.phase=='evaluation':
            result['attempts_started']=len(result['attempts'])
            result['attempts']=result['attempts'][:1]
            result.pop('cash_ledger',None)
    if not capture:
        output.pop('source_model_clock_mapping',None);output.pop('captures',None)
    output['path_index']=schedule['path_index']
    output['schedule']=dict(path_index=schedule['path_index'],**({'source_block_indices':schedule['source_block_indices']} if settings.get('retain_schedule_indices',True) else {}),schedule_sha256=schedule['schedule_sha256'])
    return output


def run_prepared_accounts(programme,pattern,settings,*,capture_paths,checkpoint,progress,weights=None,workspace=None,parallel=True):
    """Native account draws on the existing bounded pool, no extra scheduler."""
    from tempfile import TemporaryDirectory
    from pathlib import Path
    from hashlib import sha256
    from .parallel import map_reported
    from time import monotonic
    import pickle
    settings={**settings,'retain_schedule_indices':capture_paths>0}
    records=[];started=monotonic();last=0.
    if not parallel:
        return [_run_one(programme,pattern,s,settings,capture=s['path_index']<capture_paths,checkpoint=checkpoint) for s in pattern.paths(weights)]
    # Keep bounded original-engine evidence for selected first path IDs.
    schedules=pattern.paths(weights)
    for index in range(capture_paths):
        checkpoint();records.append(_run_one(programme,pattern,next(schedules),settings,capture=True,checkpoint=checkpoint))
    remaining=pattern.simulations-capture_paths
    if not remaining:return records
    with TemporaryDirectory(prefix='aq-native-accounts-') as temp:
        directory=Path(temp);stop=directory/'stop'
        prepared=worker_programme(programme,directory/'source',checkpoint=checkpoint)
        context=dict(programme=prepared,pattern=pattern,weights=weights,stop_file=str(stop))
        # The pattern contains source identity/indexes only; replace its catalogue
        # with the same checked lazy source to avoid serializing raw bar history.
        import copy
        context['pattern']=copy.copy(pattern);context['pattern'].catalogue=prepared.catalogue
        raw=pickle.dumps(context,protocol=pickle.HIGHEST_PROTOCOL);path=directory/'context';path.write_bytes(raw)
        signature=sha256(raw).hexdigest()
        tasks=[(str(path),signature,i,min(i+32,pattern.simulations),settings) for i in range(capture_paths,pattern.simulations,32)]
        def notify(done,total,workers,pids):
            nonlocal last
            now=monotonic()
            if done not in (0,total) and now-last<1:return
            complete=capture_paths+min(remaining,done*32);elapsed=now-started;rate=complete/elapsed if complete else None
            progress(dict(stage='native_execution',phase=pattern.phase,micros=settings['micros'],
                sizing_label=settings.get('sizing_label'),completed=complete,total=pattern.simulations,unit='account paths',
                worker_count=workers,active_workers=0 if complete==pattern.simulations else workers,
                elapsed_seconds=round(elapsed,2),eta_seconds=(pattern.simulations-complete)/rate if rate else None))
            last=now
        for batch in map_reported(_native_batch,tasks,checkpoint=checkpoint,notify=notify,cancel=stop.touch):records.extend(batch)
    return sorted(records,key=lambda r:r['path_index'])


class NativeDrawSequence:
    def __init__(self,catalogue,templates,indices):self.catalogue=catalogue;self.templates=templates;self.indices=indices
    def __iter__(self):
        for slot,index in enumerate(self.indices):
            template=self.templates[slot];block=self.catalogue.blocks[int(index)]
            selected=self.catalogue.sessions[block.first_session:block.first_session+template['used_sessions']]
            yield dict(slot=slot,source_block_index=int(index),used_sessions=template['used_sessions'],
                source_sessions=[str(s.context.session) for s in selected],target_sessions=template['target_sessions'])


def prepared_forecast_outputs(catalogue,contexts,strategy_factory,config,profile,sizing,micros,forecast,*,
        phase,max_micros,checkpoint,progress,preparation=None,origin_weights=None,parallel=True,**options):
    """Shared execution dispatch; phase owners retain all metric calculations."""
    from dataclasses import asdict
    from .phase_profiles import native_forecast_layout
    from .sizing_search import axis
    calendar,cohorts=native_forecast_layout(forecast,contexts,catalogue,preparation=preparation)
    if len(cohorts)!=1:raise ValueError('Prepared independent percentage research currently requires one declared scenario start. Use separate frozen start-date assessments for sensitivity.')
    start,first,cutoff,dates=cohorts[0]
    if preparation is None:preparation=NativeEventPreparation(catalogue,strategy_factory,config,checkpoint=checkpoint)
    from ..optimization_cache import digest
    key=(phase,forecast.seed,forecast.simulations,str(first),str(cutoff),digest(dict(calendar=forecast.calendar,early_closes=forecast.early_closes,model=forecast.model)))
    if not hasattr(preparation,'schedule_patterns'):preparation.schedule_patterns={}
    if key not in preparation.schedule_patterns:
        preparation.schedule_patterns[key]=NativeSchedulePreparation(catalogue,dates,strategy_factory().parameters,
            phase=phase,seed=forecast.seed,simulations=forecast.simulations,start=first,cutoff=cutoff)
    pattern=preparation.schedule_patterns[key]
    settings=dict(profile=asdict(profile),sizing=asdict(sizing),micros=micros,max_micros=max_micros,
        sizing_label=axis(dict(micros=micros,sizing=asdict(sizing)))['label'],calendar=asdict(calendar),**options)
    rows=run_prepared_accounts(preparation,pattern,settings,capture_paths=forecast.capture_paths,
        checkpoint=checkpoint,progress=progress,weights=origin_weights,parallel=parallel)
    return rows


from functools import lru_cache
@lru_cache(maxsize=16)
def _guard_template(parameters,config,symbol,calendar_sha256):
    instance=VwapPullbackRiskSizing(parameters,execution_config=config,instrument_symbol=symbol)
    if instance._calendar.sha256!=calendar_sha256:raise ValueError('Prepared native source calendar changed.')
    return instance


from .native_draws import _ClockView
class PreparedClockView(_ClockView):
    """Constant UTC shift within matched CME sessions; no DST transition is open."""
    def __init__(self,*args):
        super().__init__(*args)
        self.shifts={day:self.target[target].scheduled_close_utc-self.source[day].scheduled_close_utc for day,target in self.mapping.items()}
        self.active_source=None
    def stamp(self,value):return None if value is None else value+self.shifts[self.active_source]
    def session_context(self,stamp):return self.source[self.active_source]
    def risk_orders(self,snapshot):
        return replace(self.owner.risk_orders(self.snapshot(snapshot)),session=self.active_source)


def quantity_summary(forecast):
    """All pre-sizing opportunities; quantity quantiles cover admitted entries."""
    from collections import Counter
    import math
    counts=Counter();reasons=Counter();decisions=skips=halts=caps=budget_count=0;requested=Decimal(0);admitted_risk=Decimal(0)
    for path in forecast['paths']:
        summary=path['sizing_summary'];decisions+=summary['decision_count'];skips+=summary['skipped_count']
        halts+=summary.get('account_halted_count',0);caps+=summary.get('cap_binding_count',0);budget_count+=summary.get('risk_budget_count',0)
        from ..decimal_math import add
        requested=add(requested,Decimal(summary.get('total_requested_risk_budget','0')));admitted_risk=add(admitted_risk,Decimal(summary.get('total_admitted_planned_risk','0')))
        counts.update({int(k):v for k,v in summary['quantity_counts'].items()});reasons.update(summary['reason_counts'])
    admitted=sum(v for k,v in counts.items() if k>0)
    def quantile(p):
        threshold=max(1,math.ceil(admitted*p));seen=0
        for q,n in sorted(counts.items()):
            if q<=0:continue
            seen+=n
            if seen>=threshold:return q
    cap_reasons={key:value for key,value in reasons.items() if key.endswith('_cap')}
    # A decision can bind multiple caps; this sum is intentionally not a rate.
    return dict(opportunities=decisions-halts,all_recorded_opportunities=decisions,account_halted_opportunities=halts,admitted_entries=admitted,skipped_entries=skips-halts,
        skipped_rate=(skips-halts)/(decisions-halts) if decisions>halts else None,cap_binding_count=caps,cap_binding_rate=caps/(decisions-halts) if decisions>halts else None,
        mean_requested_risk_budget=str(requested/budget_count) if budget_count else None,mean_admitted_planned_risk=str(admitted_risk/budget_count) if budget_count else None,
        mean_quantity=sum(q*n for q,n in counts.items() if q>0)/admitted if admitted else None,
        median_quantity=quantile(.5) if admitted else None,p95_quantity=quantile(.95) if admitted else None,
        minimum_quantity=min((q for q in counts if q>0),default=None),maximum_quantity=max((q for q in counts if q>0),default=None),
        quantity_counts=dict(sorted(counts.items())),reason_counts=dict(reasons),cap_binding_reason_counts=cap_reasons,
        scope='Every eligible pre-sizing opportunity on every native point path. Quantity distribution covers admitted submissions, with fills/cancellations separate. Account-halted opportunities are not sizing-budget skips.')


class NativeBarSequence:
    """Read-only exact source rows shared by workers, without per-session unpickle.

    Records retain UTC microseconds, original row numbers and all nine original
    CSV fields through an interned string table. Decimal values reconstruct from
    the original strings; there is no float conversion or synthetic OHLC/volume.
    """
    def __init__(self,catalogue,directory,*,checkpoint=lambda:None):
        from pathlib import Path
        from hashlib import sha256
        from datetime import datetime,timezone
        import struct
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        path=directory/'observed.rows';self.length=len(catalogue.bars);self.strings=[];labels={};digest=sha256();self.tick_features={}
        epoch=datetime(1970,1,1,tzinfo=timezone.utc)
        with path.open('wb') as stream:
            buffer=bytearray()
            for index,bar in enumerate(catalogue.bars):
                if index%1000==0:checkpoint()
                if len(bar.source_fields)!=9:raise ValueError('Prepared source requires all nine original CSV fields.')
                if bar.tick_window is not None:self.tick_features[index]=(bar.tick_window,bar.flow)
                indices=[]
                for value in bar.source_fields:
                    if value not in labels:labels[value]=len(self.strings);self.strings.append(value)
                    indices.append(labels[value])
                delta=bar.timestamp_utc-epoch;stamp=(delta.days*86400+delta.seconds)*1000000+delta.microseconds
                buffer.extend(struct.pack('<qq9I',stamp,bar.bar_number,*indices))
                if len(buffer)>=1024*1024:stream.write(buffer);digest.update(buffer);buffer.clear()
            if buffer:stream.write(buffer);digest.update(buffer)
        self.strings=tuple(self.strings);self.filename=str(path);self.signature=digest.hexdigest();self._mapping=None;self._file=None;self._cache={}
    def __len__(self):return self.length
    def __getstate__(self):return {**self.__dict__,'_mapping':None,'_file':None,'_cache':{}}
    def close(self):
        if self._mapping is not None:self._mapping.close();self._mapping=None
        if self._file is not None:self._file.close();self._file=None
        self._cache.clear()
    def __del__(self):self.close()
    def __getitem__(self,index):
        if isinstance(index,slice):return tuple(self[i] for i in range(*index.indices(self.length)))
        if index<0:index+=self.length
        if not 0<=index<self.length:raise IndexError(index)
        if index in self._cache:return self._cache[index]
        import mmap,struct
        from hashlib import sha256
        from datetime import datetime,timedelta,timezone
        from ..strategy import Bar
        if self._mapping is None:
            self._file=open(self.filename,'rb');digest=sha256()
            while chunk:=self._file.read(1024*1024):digest.update(chunk)
            if digest.hexdigest()!=self.signature:raise ValueError('Native exact source spool changed.')
            self._mapping=mmap.mmap(self._file.fileno(),0,access=mmap.ACCESS_READ)
        stamp,number,*indices=struct.unpack_from('<qq9I',self._mapping,index*52)
        fields=tuple(self.strings[i] for i in indices)
        bar=Bar(number,datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(microseconds=stamp),fields[0],fields[1],*map(Decimal,fields[2:]),fields)
        if index in self.tick_features:
            from dataclasses import replace
            bar=replace(bar,tick_window=self.tick_features[index][0],flow=self.tick_features[index][1])
        if len(self._cache)>=128:self._cache.pop(next(iter(self._cache)))
        self._cache[index]=bar;return bar
    def __iter__(self):
        for index in range(self.length):yield self[index]
