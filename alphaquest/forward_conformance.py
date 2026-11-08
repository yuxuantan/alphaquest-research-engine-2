"""Local sizing arithmetic under supplied causal state; no broker certification.

Uses the existing sizing selector. The forward reconciler owns fill/fee/cash
bookkeeping; this module only checks prior position snapshots and decision links.
"""
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path

from alphaquest.forward_reconcile import effective_records, stamp
from alphaquest.prop.sizing import SizingPolicy, AccountSizingState, KnownDecisionRisk, PlanningExecution, choose_quantity
from alphaquest.prop import sizing as sizing_implementation
from alphaquest.forward_contracts import SizingDecision

LIMITATIONS=[
    'Account floors, provider caps and their known-at clocks are supplied claims; arithmetic agreement does not independently verify them.',
    'Actual later entry fills and outcomes are never sizing inputs. Planned stop risk is not a gap guarantee.',
    'Platform strategy eligibility and broker enforcement are not verified. This check does not place, cancel or block orders.',
]


def evaluate_policy_conformance(policy_snapshot, records, as_of_utc, *, reconciliation=None):
    """Return complete effective decision diagnostics without changing records.

    MATCH concerns only supported local arithmetic or unchanged fixed requested
    quantity. No-decision/no-entry paths are vacuous matches, not edge evidence.
    """
    with localcontext() as ctx:
        ctx.prec=256
        return _evaluate(policy_snapshot,records,as_of_utc,reconciliation=reconciliation)


def _evaluate(snapshot,records,as_of_utc,*,reconciliation):
    result=dict(status='INSUFFICIENT_EVIDENCE',reasons=[],decisions=[],accepted_skip_signal_ids=[],
        broker_implementation_verified=False,strategy_implementation_verified=False,
        supplied_context_independently_verified=False,limitations=list(LIMITATIONS))
    package=(snapshot or {}).get('package') or {}
    if not package:
        result.update(status='UNBOUND_SYNTHETIC',reasons=['no_authoritative_frozen_policy']);return result
    current_sizing_sha256=sha256(Path(sizing_implementation.__file__).read_bytes()).hexdigest()
    saved_sizing_sha256=((package.get('implementation') or {}).get('files') or {}).get('sizing.py')
    result['sizing_implementation']=dict(saved_sha256=saved_sizing_sha256,current_sha256=current_sizing_sha256)
    if saved_sizing_sha256!=current_sizing_sha256:
        result['reasons']=['frozen_sizing_implementation_missing_or_changed'];return result
    config=package.get('configuration') or snapshot.get('configuration') or {}
    try:
        user_cap=min(config['micros'],config['simulation']['max_micros'])
        if type(user_cap) is not int or not 0<=user_cap<=60:raise ValueError('cap')
        sizing=config.get('sizing')
        policy=SizingPolicy.model_validate(sizing['policy'] if sizing else dict(kind='fixed_contracts',contracts=config['micros']))
        initial=Decimal(sizing['initial_configured_capital']) if sizing else Decimal(50000)
        execution=PlanningExecution.model_validate(sizing['planning_execution']) if sizing else None
        if initial!=50000:raise ValueError('initial')
    except (KeyError,TypeError,ValueError) as exc:
        result['reasons']=['unsupported_or_incomplete_frozen_sizing_configuration'];return result
    dynamic=policy.kind!='fixed_contracts' or policy.constrain_to_account_cushion or policy.constrain_to_daily_cushion
    # Corrections received later cannot retroactively repair a decision at an
    # earlier assessment knowledge clock. Filter receipt clocks before resolving
    # the correction chain, preserving the earlier effective version.
    known_records=[r for r in records if stamp(r['received_at_utc'])<=stamp(as_of_utc)]
    rows=[r for r in effective_records(known_records) if stamp(r['event']['event_time_utc'])<=stamp(as_of_utc)]
    result['excluded_late_received_event_ids']=[r['event']['event_id'] for r in records
        if stamp(r['received_at_utc'])>stamp(as_of_utc)]
    rows.sort(key=lambda r:(stamp(r['event']['event_time_utc']),r['event'].get('source_sequence') or 0,r['sequence']))
    by_id={r['event']['event_id']:r for r in rows};groups=defaultdict(list)
    for r in rows:
        if r['event']['kind']!='heartbeat':groups[stamp(r['event']['event_time_utc'])].append(r)
    ambiguous=any(len(g)>1 and (any(r['event'].get('source_sequence') is None for r in g)
        or len({r['event'].get('source_sequence') for r in g})!=len(g)) for g in groups.values())
    ledger=(reconciliation or {}).get('reconciliation') or {}
    issues=ledger.get('issues',[])
    ledger_bad={i['code'] for i in issues if i['code'] in {
        'unresolved_equal_timestamp_order','source_sequence_time_conflict','duplicate_source_sequence',
        'duplicate_fill','unmatched_fill','order_overfilled','fill_side_mismatch','protective_fill_mismatch',
        'position_state_mismatch','account_balance_mismatch','initial_flat_account_state_unverified'}}
    # A financial horizon can end before an exported statement is received.
    # Only evidence unavailable at THIS assessment knowledge clock blocks the
    # supplied arithmetic; the parent's financial cutoff remains separate.
    knowledge=(reconciliation or {}).get('knowledge_cutoff_utc')
    if knowledge and stamp(knowledge)>stamp(as_of_utc):
        ledger_bad.add('retrospective_import_not_known_at_assessment_time')
    if ambiguous:ledger_bad.add('unresolved_equal_timestamp_order')
    signals={};decisions=defaultdict(list);intents=defaultdict(list);before={};latest=None
    position=0;last_exit=None;last_balance_change=None;last_sequence=None
    for index,r in enumerate(rows):
        e=r['event'];kind=e['kind'];sequence=e.get('source_sequence')
        if sequence is not None:
            if last_sequence is not None and sequence<=last_sequence:ledger_bad.add('source_sequence_time_conflict')
            last_sequence=sequence
        before[e['event_id']]=dict(position=position,position_event_id=latest,
            last_balance_change=last_balance_change,last_exit=last_exit,index=index)
        if kind=='signal':signals[e['signal_id']]=e
        elif kind=='sizing_decision':decisions[e['signal_id']].append(e)
        elif kind=='intent':intents[e['signal_id']].append(e)
        elif kind=='position':latest=e['event_id']
        elif kind=='fill':
            position+=e['quantity']*(1 if e['side']=='buy' else -1)
            if position==0:last_exit=e['event_time_utc']
            last_balance_change=index
        elif kind=='cash' and e['category']=='provider_deduction':last_balance_change=index
    problems=[]
    def diagnostic(signal_id,event=None):
        return dict(signal_id=signal_id,event_id=event.get('event_id') if event else None,
            status='INSUFFICIENT_EVIDENCE',reasons=[],supplied=deepcopy(event),recalculated=None)
    for signal_id in sorted(set(signals)|set(decisions)|set(intents)):
        signal=signals.get(signal_id);ds=decisions[signal_id];related=intents[signal_id]
        # Closing/reducing intents use their actual open position, not a fresh
        # entry sizing policy. Reversals/pyramiding remain unsupported.
        entry=[]
        for intent in related:
            prior=before[intent['event_id']]['position'];signed=intent['quantity']*(1 if intent['side']=='buy' else -1)
            if prior==0:entry.append(intent)
            elif prior*signed>0 or abs(signed)>abs(prior):
                row=diagnostic(signal_id,intent);row['reasons']=['pyramiding_or_reversal_not_supported'];problems.append(row)
        if not ds and not entry:
            if related:continue
            # A signal with no decision/order is not a verified skip.
            if signal:
                row=diagnostic(signal_id,signal);row['reasons']=['missing_decision_or_entry_intent'];problems.append(row)
            continue
        row=diagnostic(signal_id,ds[0] if ds else entry[0]);problems.append(row)
        if signal is None:row['reasons']=['missing_signal'];continue
        if len(ds)>1 or len(entry)>1:row['reasons']=['ambiguous_multiple_decisions_or_entry_intents'];continue
        if not ds:
            if dynamic:row['reasons']=['missing_causal_sizing_decision'];continue
            # Fixed request comparison does not invent an observed provider cap.
            expected=min(policy.contracts,policy.maximum_contracts,user_cap)
            if expected<policy.minimum_contracts:expected=0
            quantity=entry[0]['quantity']
            row.update(status='MATCH' if quantity==expected and signal['quantity']==quantity else 'MISMATCH',
                recalculated=dict(quantity=expected,action='trade' if expected else 'skip',
                    scope='fixed_requested_quantity_without_unobserved_provider_adjustments'))
            if row['status']=='MISMATCH':row['reasons']=['fixed_policy_quantity_mismatch']
            continue
        try:
            event=SizingDecision.model_validate(ds[0]).model_dump(mode='json')
            decision_time=stamp(event['event_time_utc']);b=before[event['event_id']]
            state=AccountSizingState.model_validate(event['account_state'])
            row['received_after_decision']=stamp(by_id[event['event_id']]['received_at_utc'])>decision_time
            if ledger_bad:raise ValueError('unreconciled_prior_position_or_cash_evidence')
            if not ledger.get('position',{}).get('initial_flat_account_state_verified'):
                raise ValueError('missing_reconciled_initial_flat_state')
            if b['position']!=0:raise ValueError('position_open_at_sizing_decision')
            source=by_id.get(event['position_event_id'])
            if not source or source['event']['kind']!='position' or b['position_event_id']!=event['position_event_id']:
                raise ValueError('missing_or_stale_predecision_position_snapshot')
            supplied_position=source['event'];position_index=before[supplied_position['event_id']]['index']
            if supplied_position['signed_quantity']!=0 or supplied_position.get('account_balance') is None:
                raise ValueError('predecision_snapshot_must_be_flat_with_known_balance')
            if not stamp(supplied_position['event_time_utc'])<=stamp(event['context_known_at_utc'])<=decision_time:
                raise ValueError('noncausal_predecision_context')
            if b['last_balance_change'] is not None and b['last_balance_change']>position_index:
                raise ValueError('balance_changed_since_supplied_context')
            if state.initial_configured_capital!=initial or state.user_max_contracts!=user_cap:
                raise ValueError('context_differs_from_frozen_capital_or_user_cap')
            if state.initial_configured_capital+state.equity_change_from_initial!=Decimal(supplied_position['account_balance']):
                raise ValueError('context_balance_differs_from_reconciled_snapshot')
            if stamp(signal['event_time_utc'])>decision_time:raise ValueError('signal_after_decision')
            if event['side']!=('long' if signal['side']=='buy' else 'short') or Decimal(event['decision_reference_price'])!=Decimal(signal['reference_price']):
                raise ValueError('decision_signal_side_or_reference_mismatch')
            risk=None
            if event['initial_stop_price'] is not None:
                if signal.get('stop_price') is None or Decimal(signal['stop_price'])!=Decimal(event['initial_stop_price']):
                    raise ValueError('decision_signal_stop_mismatch')
                if stamp(event['initial_stop_known_at_utc'])>stamp(signal['event_time_utc']):raise ValueError('signal_contains_not_yet_known_stop')
                risk=KnownDecisionRisk(sizing_decision_time_utc=event['event_time_utc'],
                    initial_stop_known_at_utc=event['initial_stop_known_at_utc'],previous_source_exit_utc=b['last_exit'],
                    execution_timing=event['execution_timing'],side=event['side'],
                    decision_reference_price=event['decision_reference_price'],initial_stop_price=event['initial_stop_price'])
            if policy.constrain_to_daily_cushion and state.daily_floor_from_initial is None:
                raise ValueError('daily_cushion_guard_requires_known_daily_floor')
            expected=choose_quantity(policy,state,risk,execution)
            if state.equity_change_from_initial<=state.account_floor_from_initial or (state.daily_floor_from_initial is not None and state.equity_change_from_initial<=state.daily_floor_from_initial):
                expected=dict(expected,quantity=0,action='skip',planned_total_risk='0' if expected['planned_risk_per_mnq'] else None,
                    reasons=expected['reasons']+['supplied_account_or_daily_floor_touched'])
            row['recalculated']=expected
            mismatches=[]
            if event['submitted_quantity']!=expected['quantity'] or event['action']!=expected['action']:
                mismatches.append('submitted_quantity_or_action_differs_from_frozen_policy')
            if event['action']=='trade':
                if signal['quantity']!=event['submitted_quantity']:mismatches.append('signal_decision_quantity_mismatch')
                if not entry:raise ValueError('accepted_decision_missing_entry_intent')
                intent=entry[0]
                if before[intent['event_id']]['index']<b['index']:raise ValueError('entry_intent_precedes_sizing_decision')
                if intent['quantity']!=event['submitted_quantity']:mismatches.append('intent_decision_quantity_mismatch')
            elif related:mismatches.append('skipped_signal_has_submitted_intent')
            row['status']='MISMATCH' if mismatches else 'MATCH';row['reasons']=mismatches
            if row['status']=='MATCH' and event['action']=='skip':result['accepted_skip_signal_ids'].append(signal_id)
        except (KeyError,TypeError,ValueError) as exc:
            row['reasons']=[str(exc)]
    result['decisions']=problems
    if ledger_bad:
        result['reasons'].append('unreconciled_position_or_cash_path')
        result['accepted_skip_signal_ids']=[]
    result['reasons']+=sorted({reason for row in problems for reason in row['reasons']})
    result['status']='MISMATCH' if any(r['status']=='MISMATCH' for r in problems) else 'INSUFFICIENT_EVIDENCE' if result['reasons'] or any(r['status']!='MATCH' for r in problems) else 'MATCH'
    return result
