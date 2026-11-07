"""exact reconciliation of supplied forward events; never fabricates fills."""
from collections import defaultdict,deque
from datetime import datetime,timedelta
from decimal import Decimal,localcontext
from hashlib import sha256
import json

from .forward_contracts import MonitorDeclaration,EventBatch,utc


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))
def digest(value):return sha256(canonical(value).encode()).hexdigest()
def stamp(value):return datetime.fromisoformat(utc(value).replace('Z','+00:00'))
def money(value):return format(value,'f')


def effective_records(records):
    """Append-only correction chains; original receive clocks remain audit facts."""
    active={};seen={}
    for row in sorted(records,key=lambda value:value['sequence']):
        event=row['event'];id=event['event_id']
        if id in seen:
            if seen[id]!=event:raise ValueError('An event ID has conflicting immutable content.')
            continue
        target=event.get('supersedes_event_id')
        if target:
            if target not in active:raise ValueError('Correction target must be an active earlier event; forks are unsupported.')
            previous=active.pop(target)['event']
            if event['kind']!='void' and previous['kind']!=event['kind']:
                raise ValueError('A correction must retain its event kind; use an explicit void otherwise.')
        seen[id]=event
        if event['kind']!='void':active[id]=row
    return list(active.values())


def reconcile(declaration,records,as_of_utc,*,pause_latched=False,retired=False,acknowledged_incident_sequence=0):
    """Report observed facts and unresolved links, with advisory thresholds only.

    Money is calculated from exact supplied fills. Position bookkeeping uses
    FIFO lots; completed flat-to-flat episodes are the only trade-level edge
    observation units. Slippage is diagnostic and never deducted again.
    """
    if type(declaration) is not MonitorDeclaration:raise ValueError('Validated declaration required.')
    with localcontext() as ctx:
        ctx.prec=128
        return _reconcile(declaration,records,as_of_utc,pause_latched=pause_latched,retired=retired,acknowledged_incident_sequence=acknowledged_incident_sequence)


def _reconcile(d,records,as_of_utc,*,pause_latched,retired,acknowledged_incident_sequence):
    asof=stamp(as_of_utc);cfg=d.thresholds;point=Decimal(d.instrument.point_value);tick=Decimal(d.instrument.tick_size)
    initial=Decimal(d.initial_balance);rows=effective_records(records);issues=[];signals={};intents={};orders={};fills={};protective={};protection_intents={}
    lots=deque();position=0;realized=Decimal(0);fees=Decimal(0);mark=None;market_time=None;heartbeat=None;connection=None
    peak=initial;max_dd=Decimal(0);episode_start=None;episode_net_start=None;episodes=[];latencies=[];slippages=[]
    cash={key:Decimal(0) for key in ('payout_request','provider_deduction','trader_receipt','evaluation_purchase_fee','activation_fee')}
    cash_ids={};intent_orders=defaultdict(list);protection_gaps=[];unprotected_since=None;latest_position=None
    processed=[];seen_sequence={};ingestion_late=[];ambiguous_path=False;last_sequence=None;last_fill=None;ambiguous_times=set();mark_ambiguous=False;current_record_sequence=0;initial_state_known=False;cost_basis_ambiguous=False
    execution_kind={'synthetic_harness':'synthetic','paper':'paper','actual_import':'actual'}[d.observation_kind]
    def issue(code,severity,event=None,**details):
        value=dict(code=code,severity=severity,event_id=event.get('event_id') if event else None,details=details,
            observed_through_sequence=current_record_sequence)
        if value not in issues:issues.append(value)
    def on_grid(value,event,field):
        result=Decimal(value)
        if result%tick!=0:issue('price_off_tick_grid','PAUSED',event,field=field,value=value,tick_size=str(tick))
        return result
    def stop_covered():
        if not position:return True
        side='sell' if position>0 else 'buy'
        remaining=defaultdict(int);covered=defaultdict(int)
        for lot in lots:remaining[lot['order_id']]+=abs(lot['quantity'])
        for p in protective.values():
            if p['status']=='active' and p['protection_type']=='stop' and p['side']==side:
                covered[p['order_id']]+=max(0,p['quantity']-p['filled_quantity'])
        return sum(min(quantity,covered[parent]) for parent,quantity in remaining.items())>=abs(position)
    def measure_gap(now):
        nonlocal unprotected_since
        covered=stop_covered()
        if cfg.require_protective_stop and position and not covered:
            if unprotected_since is None:unprotected_since=now
        elif unprotected_since is not None:
            duration=(now-unprotected_since).total_seconds()
            protection_gaps.append(dict(start_utc=utc(unprotected_since.isoformat()),end_utc=utc(now.isoformat()),seconds=duration))
            if duration>getattr(cfg,'maximum_unprotected_seconds',5):issue('protective_order_gap','PAUSED',seconds=duration)
            unprotected_since=None
    def equity():
        if position and (mark is None or mark_ambiguous):return None
        open_pnl=sum((mark-lot['price'])*lot['quantity']*point for lot in lots) if lots else Decimal(0)
        return initial+realized-fees+open_pnl
    groups=defaultdict(list)
    for row in rows:
        event=row['event'];when=stamp(event['event_time_utc']);received=stamp(row['received_at_utc'])
        if when>received+timedelta(seconds=cfg.maximum_clock_skew_seconds):issue('event_clock_ahead_of_receiver','WATCH',event)
        if when<=asof:groups[when].append(row)
        if received>when:ingestion_late.append((received-when).total_seconds())
    ordered=[]
    for when,group in sorted(groups.items()):
        economic=[r for r in group if r['event']['kind']!='heartbeat']
        sequences=[r['event'].get('source_sequence') for r in economic]
        if len(economic)>1 and (None in sequences or len(set(sequences))!=len(sequences)):
            ambiguous_path=True
            ambiguous_times.add(when)
            issue('unresolved_equal_timestamp_order','PAUSED',event_ids=[r['event']['event_id'] for r in economic])
            # Observed fills still affect risk position; do not claim their exact
            # trade/realized path is causally reconciled under this ambiguity.
        ordered.extend(sorted(group,key=lambda r:(r['event'].get('source_sequence') or 0,r['sequence'])))
    for row in ordered:
        current_record_sequence=row['sequence']
        e=row['event'];kind=e['kind'];when=stamp(e['event_time_utc']);processed.append(e['event_id'])
        seq=e.get('source_sequence')
        if seq is not None:
            if last_sequence is not None and seq<last_sequence:
                ambiguous_path=True;issue('source_sequence_time_conflict','PAUSED',e,previous_sequence=last_sequence)
            last_sequence=seq
            if seq in seen_sequence:issue('duplicate_source_sequence','PAUSED',e,other_event_id=seen_sequence[seq])
            seen_sequence[seq]=e['event_id']
        if kind=='signal':
            if e['signal_id'] in signals:issue('duplicate_signal','PAUSED',e,signal_id=e['signal_id'])
            else:signals[e['signal_id']]=e
            for field in ('reference_price','stop_price','target_price'):
                if e.get(field) is not None:on_grid(e[field],e,field)
        elif kind=='intent':
            if e['intent_id'] in intents:issue('duplicate_intent','PAUSED',e,intent_id=e['intent_id'])
            else:intents[e['intent_id']]=e
            parent=signals.get(e['signal_id'])
            if parent is None:issue('missing_or_noncausal_signal','PAUSED',e,signal_id=e['signal_id'])
            elif parent['side']!=e['side'] or parent['quantity']!=e['quantity']:issue('signal_intent_mismatch','WATCH',e)
            for field in ('reference_price','limit_price','stop_price','target_price'):
                if e.get(field) is not None:on_grid(e[field],e,field)
        elif kind=='order':
            if e['execution_kind']!=execution_kind:issue('execution_provenance_mismatch','PAUSED',e)
            if e['order_id'] in orders:issue('duplicate_order','PAUSED',e,order_id=e['order_id'])
            else:orders[e['order_id']]=dict(e,filled_quantity=0,status='submitted')
            parent=intents.get(e['intent_id'])
            if parent is None:issue('missing_or_noncausal_intent','PAUSED',e,intent_id=e['intent_id'])
            elif parent['side']!=e['side'] or parent['quantity']!=e['quantity']:issue('order_intent_mismatch','PAUSED',e)
            intent_orders[e['intent_id']].append(e['order_id'])
            if len(set(intent_orders[e['intent_id']]))>1:issue('duplicate_orders_for_intent','PAUSED',e,intent_id=e['intent_id'])
            if parent and (signal:=signals.get(parent['signal_id'])):
                seconds=(when-stamp(signal['event_time_utc'])).total_seconds();latencies.append(dict(kind='signal_to_order',seconds=seconds,event_id=e['event_id']))
                if seconds>cfg.maximum_signal_to_order_seconds:issue('signal_order_latency','WATCH',e,seconds=seconds)
        elif kind=='order_status':
            order=orders.get(e['order_id'])
            if order is None:issue('unknown_order_status','PAUSED',e)
            else:
                if order['status'] in ('cancelled','rejected') and e['status']!=order['status']:
                    issue('order_terminal_state_reopened','PAUSED',e)
                order['status']=e['status']
                if e['status']=='acknowledged':
                    seconds=(when-stamp(order['event_time_utc'])).total_seconds();latencies.append(dict(kind='order_ack',seconds=seconds,event_id=e['event_id']))
                    if seconds>cfg.maximum_order_ack_seconds:issue('order_ack_latency','WATCH',e,seconds=seconds)
        elif kind=='protection_intent':
            on_grid(e['trigger_price'],e,'trigger_price')
            if e['order_id'] not in orders:issue('unknown_protection_intent_parent','PAUSED',e)
            protection_intents[e['protective_order_id']]=e
        elif kind=='protection':
            on_grid(e['trigger_price'],e,'trigger_price')
            if e['order_id'] not in orders:issue('unknown_protected_entry_order','PAUSED',e)
            old=protective.get(e['protective_order_id'])
            filled=old['filled_quantity'] if old else 0
            if old and any(old[key]!=e[key] for key in ('order_id','side','protection_type')):
                issue('protective_order_identity_changed','PAUSED',e)
            protective[e['protective_order_id']]=dict(e,filled_quantity=filled)
            if e['status']=='active':
                intended=protection_intents.get(e['protective_order_id'])
                parent=orders.get(e['order_id']);intent=intents.get(parent.get('intent_id')) if parent else None
                expected=(intended['trigger_price'] if intended else intent.get('stop_price' if e['protection_type']=='stop' else 'target_price') if intent else None)
                if expected is not None and Decimal(expected)!=Decimal(e['trigger_price']):
                    issue(e['protection_type']+'_price_mismatch','PAUSED',e,expected=expected,observed=e['trigger_price'])
                if intended and any(intended[key]!=e[key] for key in ('order_id','side','quantity','protection_type')):
                    issue('protective_order_intent_mismatch','PAUSED',e)
        elif kind=='fill':
            if e['fill_id'] in fills:issue('duplicate_fill','PAUSED',e,fill_id=e['fill_id']);continue
            fills[e['fill_id']]=e;last_fill=when
            if e['execution_kind']!=execution_kind:issue('execution_provenance_mismatch','PAUSED',e)
            price=on_grid(e['price'],e,'price');fee=Decimal(e['commission']);qty=e['quantity'];order=orders.get(e['order_id'])
            protection=protective.get(e['order_id'])
            reference=None
            if order is None and protection is None:issue('unmatched_fill','PAUSED',e,order_id=e['order_id'])
            elif order is not None:
                order['filled_quantity']+=qty
                if order['filled_quantity']>order['quantity']:issue('order_overfilled','PAUSED',e)
                if order['side']!=e['side']:issue('fill_side_mismatch','PAUSED',e)
                if order['status'] in ('cancelled','rejected'):issue('fill_after_cancel_or_rejection','PAUSED',e)
                seconds=(when-stamp(order['event_time_utc'])).total_seconds();latencies.append(dict(kind='order_to_fill',seconds=seconds,event_id=e['event_id']))
                if seconds>cfg.maximum_fill_latency_seconds:issue('fill_latency','WATCH',e,seconds=seconds)
                intent=intents.get(order['intent_id'])
                if intent:
                    reference=Decimal(intent['reference_price'])
                    if intent['order_type']=='limit' and ((e['side']=='buy' and price>Decimal(intent['limit_price'])) or(e['side']=='sell' and price<Decimal(intent['limit_price']))):issue('fill_outside_limit','PAUSED',e)
            else:
                reference=Decimal(protection['trigger_price'])
                if protection['status'] in ('cancelled','rejected','filled'):issue('protective_fill_after_terminal_status','PAUSED',e)
                protection['filled_quantity']+=qty
                if protection['side']!=e['side'] or protection['filled_quantity']>protection['quantity']:issue('protective_fill_mismatch','PAUSED',e)
                if not any(lot['order_id']==protection['order_id'] and lot['quantity']*(1 if e['side']=='buy' else -1)<0 for lot in lots):
                    issue('protective_fill_without_parent_exposure','PAUSED',e)
                if protection['filled_quantity']>=protection['quantity']:protection['status']='filled'
            if reference is not None:
                slippage=(price-reference)*(1 if e['side']=='buy' else -1)/tick
                slippages.append(dict(fill_id=e['fill_id'],ticks=money(slippage),reference_price=money(reference)))
                if slippage>Decimal(cfg.maximum_slippage_ticks):issue('slippage_threshold','WATCH',e,ticks=money(slippage))
            if cfg.maximum_commission_per_contract_side is not None and fee>Decimal(cfg.maximum_commission_per_contract_side)*qty:
                issue('commission_threshold','WATCH',e,commission=money(fee))
            if position==0:episode_start=e['event_time_utc'];episode_net_start=realized-fees
            fees+=fee;delta=qty if e['side']=='buy' else -qty;remaining=delta
            while lots and remaining*lots[0]['quantity']<0:
                lot=lots[0];closed=min(abs(remaining),abs(lot['quantity']));sign=1 if lot['quantity']>0 else -1
                realized+=(price-lot['price'])*closed*point*sign
                lot['quantity']-=closed*sign;remaining+=closed*sign
                if not lot['quantity']:lots.popleft()
            if remaining:lots.append(dict(quantity=remaining,price=price,order_id=e['order_id']))
            position+=delta
            if len({lot['price'] for lot in lots})>1:cost_basis_ambiguous=True
            if not position:cost_basis_ambiguous=False
            # An actual fill is a contemporaneous observed price. A market mark
            # from before this exposure cannot manufacture a profitable peak.
            mark=price;mark_ambiguous=when in ambiguous_times
            if abs(position)>cfg.maximum_position_contracts:issue('exposure_limit','PAUSED',e,signed_quantity=position)
            if position==0 and episode_start is not None:
                episodes.append(dict(start_utc=episode_start,end_utc=e['event_time_utc'],net_pnl=money(realized-fees-episode_net_start)))
                episode_start=episode_net_start=None
        elif kind=='position':
            latest_position=e
            if not fills:
                initial_state_known=initial_state_known or (e['signed_quantity']==0 and e.get('account_balance') is not None and Decimal(e['account_balance'])==initial)
            if e['signed_quantity']!=position:issue('position_state_mismatch','PAUSED',e,from_fills=position,observed=e['signed_quantity'])
            basis_known=d.source.position_cost_basis=='fifo' or not cost_basis_ambiguous
            if position and e.get('average_entry_price') is not None and not ambiguous_path:
                if basis_known:
                    observed=Decimal(e['average_entry_price']);weighted=sum(abs(lot['quantity'])*lot['price'] for lot in lots)
                    if observed*abs(position)!=weighted:issue('average_entry_price_mismatch','PAUSED',e,observed=e['average_entry_price'])
                else:issue('position_cost_basis_unknown','WATCH',e)
            if e.get('account_balance') is not None and not ambiguous_path and (not position or d.source.position_cost_basis=='fifo') and Decimal(e['account_balance'])!=initial+realized-fees-cash['provider_deduction']:
                issue('account_balance_mismatch','PAUSED',e,from_observed_ledger=money(initial+realized-fees-cash['provider_deduction']),observed=e['account_balance'])
        elif kind=='market':mark=on_grid(e['price'],e,'price');market_time=when;mark_ambiguous=when in ambiguous_times
        elif kind=='heartbeat':heartbeat=when
        elif kind=='connection':connection=e
        elif kind=='cash':
            if e['cash_event_id'] in cash_ids:issue('duplicate_cash_event','PAUSED',e);continue
            cash_ids[e['cash_event_id']]=e;cash[e['category']]+=Decimal(e['amount'])
        measure_gap(when)
        marked=equity()
        if marked is not None and not ambiguous_path:
            peak=max(peak,marked);max_dd=max(max_dd,peak-marked)
            if max_dd>Decimal(cfg.maximum_drawdown_cash):issue('drawdown_limit','PAUSED',e,drawdown=money(max_dd))
    measure_gap(asof)
    if not initial_state_known:issue('initial_flat_account_state_unverified','PAUSED')
    if unprotected_since is not None:
        elapsed=(asof-unprotected_since).total_seconds()
        issue('missing_protective_stop','PAUSED' if elapsed>getattr(cfg,'maximum_unprotected_seconds',5) else 'WATCH',seconds=elapsed,position=position)
    if cfg.require_position_snapshot and latest_position is None:issue('missing_position_snapshot','WATCH')
    elif cfg.require_position_snapshot and last_fill and stamp(latest_position['event_time_utc'])<last_fill:issue('position_snapshot_precedes_latest_fill','WATCH')
    for name,observed,limit in [('market_data',market_time,cfg.maximum_market_data_age_seconds),('heartbeat',heartbeat,cfg.maximum_heartbeat_age_seconds)]:
        if observed is None:issue('missing_'+name,'WATCH')
        elif (asof-observed).total_seconds()>limit:issue('stale_'+name,'PAUSED',age_seconds=(asof-observed).total_seconds())
    if connection is None:issue('connection_status_unknown','WATCH')
    elif connection['status']!='connected':issue('connection_'+connection['status'],'PAUSED')
    for signal in signals.values():
        matching=[i for i in intents.values() if i['signal_id']==signal['signal_id']]
        submitted=any(intent_orders[i['intent_id']] for i in matching)
        if not submitted and (asof-stamp(signal['event_time_utc'])).total_seconds()>cfg.maximum_signal_to_order_seconds:
            issue('missed_signal','WATCH',signal)
    live_parents={lot['order_id'] for lot in lots}
    for protection in protective.values():
        if protection['status']=='active' and protection['order_id'] not in live_parents:
            issue('orphan_active_protection','PAUSED',protection)
    for order in orders.values():
        if order['status']=='submitted' and (asof-stamp(order['event_time_utc'])).total_seconds()>cfg.maximum_order_ack_seconds:
            issue('missing_order_acknowledgement','WATCH',order)
    if cfg.minimum_rolling_mean_net_per_trade is not None and len(episodes)>=cfg.minimum_trades_for_edge_check:
        history=episodes[-cfg.edge_window_trades:];total=sum(Decimal(e['net_pnl']) for e in history)
        if total<Decimal(cfg.minimum_rolling_mean_net_per_trade)*len(history):issue('observed_edge_deterioration','WATCH',completed_episodes=len(history),net_total=money(total))
    pending=Decimal(0);pending_known=True
    receipts=defaultdict(lambda:Decimal(0))
    for event in cash_ids.values():
        if event['category']=='trader_receipt':
            related=event.get('related_cash_event_id');request=cash_ids.get(related)
            if not request or request['category']!='payout_request':
                issue('receipt_request_correlation_unknown','WATCH',event);pending_known=False
            else:receipts[related]+=Decimal(event['amount'])
    for id,event in cash_ids.items():
        if event['category']=='payout_request':
            expected=(Decimal(event['expected_trader_amount']) if event.get('expected_trader_amount') is not None else
                Decimal(event['amount']) if event.get('request_amount_basis')=='trader_entitlement' else None)
            if event.get('request_amount_basis')=='gross_withdrawal' and expected is not None and expected>Decimal(event['amount']):
                issue('trader_entitlement_exceeds_gross_request','PAUSED',event,
                    gross_request=event['amount'],declared_trader_entitlement=event['expected_trader_amount'])
                expected=None;pending_known=False
            if expected is None:
                pending_known=False;issue('request_trader_entitlement_unknown','WATCH',event)
            else:
                pending+=max(Decimal(0),expected-receipts[id])
                if receipts[id]>expected:issue('receipt_exceeds_declared_entitlement','WATCH',event)
    knowledge=max((stamp(r['received_at_utc']) for r in records),default=asof)
    if knowledge>asof:issue('retrospective_import_not_known_at_assessment_time','WATCH')
    marked=equity();current_dd=peak-marked if marked is not None and not ambiguous_path else None
    if abs(position)>cfg.maximum_position_contracts:issue('current_exposure_limit','PAUSED',position=position)
    if current_dd is not None and current_dd>Decimal(cfg.maximum_drawdown_cash):issue('current_drawdown_limit','PAUSED',drawdown=money(current_dd))
    historical_codes={'protective_order_gap','drawdown_limit','exposure_limit'}
    for item in issues:
        item['historical_incident']=item['code'] in historical_codes
        item['acknowledged']=item['historical_incident'] and 0<item['observed_through_sequence']<=acknowledged_incident_sequence
    health_unknown={'missing_market_data','missing_heartbeat','missing_position_snapshot','position_snapshot_precedes_latest_fill',
        'connection_status_unknown','event_clock_ahead_of_receiver','position_cost_basis_unknown'}
    blockers=[i for i in issues if i['severity']=='PAUSED' and not i['historical_incident'] or i['code'] in health_unknown]
    pause_now=any(i['severity']=='PAUSED' and not i['acknowledged'] for i in issues)
    state='RETIRED' if retired else 'PAUSED' if pause_latched or pause_now else 'WATCH' if issues else 'ACTIVE'
    net=realized-fees;marked=equity()
    return dict(observation_kind=d.observation_kind,as_of_utc=utc(as_of_utc),knowledge_cutoff_utc=utc(knowledge.isoformat()),
        retrospective_import=knowledge>asof,
        advisory=dict(state=state,reasons=sorted({i['code'] for i in issues}),automatic_pause_latched=pause_latched or pause_now,
            recovery_required=pause_latched or pause_now,enforcement='advisory_only',order_placement_enabled=False),
        recovery=dict(current_blockers=blockers,acknowledged_incident_sequence=acknowledged_incident_sequence,
            eligible_for_acknowledgement=not blockers),
        reconciliation=dict(status='UNRESOLVED' if any(i['severity']=='PAUSED' for i in issues) else 'RECONCILED',issues=issues,
            signals=list(signals.values()),orders=list(orders.values()),fills=list(fills.values()),protection=list(protective.values()),
            position=dict(signed_quantity=position,supplied_snapshot=latest_position,initial_flat_account_state_verified=initial_state_known,
                scope='Position derived from supplied fills; mismatched or missing initial evidence prevents a reconciled whole-account claim.'),latency=dict(measurements=latencies,received_delays_seconds=ingestion_late),
            costs=dict(slippage=slippages,commission_deducted_once=True,slippage_deducted_again=False),protection_gaps=protection_gaps),
        metrics=dict(completed_flat_to_flat_trades=len(episodes) if not ambiguous_path and initial_state_known else None,episodes=episodes if not ambiguous_path and initial_state_known else [],gross_realized_pnl=money(realized) if not ambiguous_path and initial_state_known else None,commissions=money(fees),net_realized_pnl=money(net) if not ambiguous_path and initial_state_known else None,
            net_trading_equity=money(marked) if marked is not None and initial_state_known else None,max_observed_drawdown=money(max_dd) if not ambiguous_path and initial_state_known else None,current_observed_drawdown=money(current_dd) if current_dd is not None and initial_state_known else None,signed_position=position,
            trader_receipts=money(cash['trader_receipt']),payout_requests=money(cash['payout_request']),provider_deductions=money(cash['provider_deduction']),
            evaluation_purchase_fees=money(cash['evaluation_purchase_fee']),activation_fees=money(cash['activation_fee']),
            net_trader_cash=money(cash['trader_receipt']-cash['evaluation_purchase_fee']-cash['activation_fee']),
            provider_balance_from_observed_ledger=money(initial+net-cash['provider_deduction']) if not ambiguous_path and initial_state_known else None,
            pending_receipt_amount=money(pending) if pending_known else None),
        effective_event_ids=processed,readiness=dict(production_qualified=False,direct_execution_integration=False),
        limitations=['Supplied timestamped observations, not verified broker integration or historical-backtest trade adaptation.',
            'State is advisory only; AlphaQuest does not prevent broker orders.',
            'FIFO bookkeeping and completed flat-to-flat episodes are declared reconciliation conventions, not broker tax-lot claims.',
            'Observed edge thresholds are descriptive; no future mean or provider qualification is inferred.'])
