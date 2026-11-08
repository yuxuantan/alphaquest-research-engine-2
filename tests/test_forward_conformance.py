"""Independent sizing arithmetic for supplied forward decision contexts."""
from copy import deepcopy
from decimal import Decimal
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import pytest
from alphaquest.forward_reconcile import reconcile
from tests.test_forward_reconcile import declaration,fixture,time
from alphaquest.forward_conformance import evaluate_policy_conformance
from alphaquest.forward_contracts import SizingDecision


def frozen(kind='fixed_dollar_risk',**changes):
    policy=dict(kind=kind,**({'risk_dollars':'100'} if kind=='fixed_dollar_risk' else {'contracts':3} if kind=='fixed_contracts' else {'risk_percent':'.2','reference':'current_account_balance'}));policy.update(changes)
    import alphaquest.prop.sizing as implementation
    return dict(package=dict(package_sha256='a'*64,implementation=dict(files={'sizing.py':sha256(Path(implementation.__file__).read_bytes()).hexdigest()}),configuration=dict(micros=40,simulation=dict(max_micros=40),
        sizing=dict(policy=policy,initial_configured_capital='50000',planning_execution=dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0')))))


def event(n,kind,**fields):return dict(event_id=f'e{n}',event_time_utc=time(n),source_sequence=n+1,kind=kind,**fields)
def records(events):
    from alphaquest.forward_contracts import EventBatch
    from uuid import uuid4
    result=[]
    for i,e in enumerate(events):
        # Invalid decision probes must reach the assessor; normal events use the
        # same strict schema/defaults as the product importer.
        value=deepcopy(e) if e['kind']=='sizing_decision' else EventBatch(batch_id=uuid4().hex,source_id='fixture',events=[e]).events[0].model_dump(mode='json')
        result.append(dict(sequence=i+1,received_at_utc=time(200),event=value))
    return result


def known(n=2,*,qty=10,signal='s',position='e0',balance='50000',stop='95',action='trade',**changes):
    value=event(n,'sizing_decision',signal_id=signal,position_event_id=position,context_known_at_utc=time(0),
        account_state=dict(initial_configured_capital='50000',equity_change_from_initial=str(Decimal(balance)-50000),
            account_floor_from_initial='-2000',daily_floor_from_initial=None,provider_max_contracts=20,user_max_contracts=40),
        execution_timing='next_open',side='long',decision_reference_price='100',initial_stop_price=stop,
        initial_stop_known_at_utc=time(1),submitted_quantity=qty,action=action)
    value.update(changes);return value


def simple(qty=10,**decision):
    return [event(0,'position',signed_quantity=0,account_balance='50000'),
        event(1,'signal',signal_id='s',side='buy',quantity=max(1,qty),reference_price='100',stop_price='95'),
        known(qty=qty,action='trade' if qty else 'skip',**decision),
        *([event(3,'intent',intent_id='i',signal_id='s',side='buy',quantity=qty,reference_price='100',stop_price='95')] if qty else []),
        event(5,'market',price='100'),event(6,'heartbeat'),event(7,'connection',status='connected')]


def assess(events,policy=None):
    rs=records(events);d=declaration(require_protective_stop=False,maximum_position_contracts=40)
    base=reconcile(d,rs,time(250))
    return evaluate_policy_conformance(policy or frozen(),rs,time(250),reconciliation=base)


@pytest.mark.parametrize('kind,changes,quantity,denominator',[
    ('fixed_contracts',{},3,None),('fixed_dollar_risk',{},10,None),
    ('percentage_risk',dict(reference='initial_configured_capital'),10,'50000'),
    ('percentage_risk',dict(reference='current_account_balance'),10,'50000'),
    ('percentage_risk',dict(reference='available_drawdown_cushion',risk_percent='1'),2,'2000')])
def test_all_policy_bases_use_known_stop_and_named_denominator(kind,changes,quantity,denominator):
    result=assess(simple(quantity),frozen(kind,**changes));assert result['status']=='MATCH',result
    row=result['decisions'][0];assert row['recalculated']['quantity']==quantity
    assert row['recalculated']['denominator_value']==denominator
    assert row['received_after_decision'] and not result['supplied_context_independently_verified']


def test_frozen_costs_caps_rounding_and_known_zero_skip():
    policy=frozen();policy['package']['configuration']['sizing']['planning_execution'].update(
        commission_per_contract_per_side='.5',entry_slippage_ticks=1,stop_exit_slippage_ticks=1)
    result=assess(simple(8),policy);assert result['status']=='MATCH',result
    assert Decimal(result['decisions'][0]['recalculated']['planned_risk_per_mnq'])==12
    result=assess(simple(3),frozen(maximum_contracts=3));assert result['status']=='MATCH'
    assert result['decisions'][0]['recalculated']['requested_contracts']==10
    assert result['decisions'][0]['recalculated']['reasons']==['policy_cap']
    result=assess(simple(0),frozen(risk_dollars='1'));assert result['status']=='MATCH',result
    assert result['accepted_skip_signal_ids']==['s']
    assert Decimal(result['decisions'][0]['recalculated']['planned_total_risk'])==0


def test_three_actual_prior_balances_and_variable_stops_recompute_percentage():
    events=[];balance=Decimal(50000);offset=0
    for index,(quantity,stop,exit_price,net) in enumerate([(10,'95','95',-100),(9,'95','110',180),(5,'90','110',100)]):
        sid=f's{index}';oid=f'o{index}';closing=f'c{index}'
        events += [event(offset,'position',signed_quantity=0,account_balance=str(balance)),
            event(offset+1,'signal',signal_id=sid,side='buy',quantity=quantity,reference_price='100',stop_price=stop),
            known(offset+2,qty=quantity,signal=sid,position=f'e{offset}',balance=str(balance),stop=stop,
                context_known_at_utc=time(offset),initial_stop_known_at_utc=time(offset+1)),
            event(offset+3,'intent',intent_id=f'i{index}',signal_id=sid,side='buy',quantity=quantity,reference_price='100',stop_price=stop),
            event(offset+4,'order',order_id=oid,intent_id=f'i{index}',side='buy',quantity=quantity,execution_kind='synthetic'),
            event(offset+5,'order_status',order_id=oid,status='acknowledged'),
            event(offset+6,'fill',fill_id=f'f{index}',order_id=oid,side='buy',quantity=quantity,price='100',commission='0',execution_kind='synthetic'),
            event(offset+7,'signal',signal_id=closing,side='sell',quantity=quantity,reference_price=exit_price),
            event(offset+8,'intent',intent_id=f'j{index}',signal_id=closing,side='sell',quantity=quantity,reference_price=exit_price),
            event(offset+9,'order',order_id=f'x{index}',intent_id=f'j{index}',side='sell',quantity=quantity,execution_kind='synthetic'),
            event(offset+10,'order_status',order_id=f'x{index}',status='acknowledged'),
            event(offset+11,'fill',fill_id=f'y{index}',order_id=f'x{index}',side='sell',quantity=quantity,price=exit_price,commission='0',execution_kind='synthetic')]
        balance+=net;offset+=20
    events += [event(offset,'position',signed_quantity=0,account_balance=str(balance)),event(offset+1,'market',price='110'),event(offset+2,'heartbeat'),event(offset+3,'connection',status='connected')]
    result=assess(events,frozen('percentage_risk'));assert result['status']=='MATCH',result
    assert [row['recalculated']['quantity'] for row in result['decisions']]==[10,9,5]
    assert [Decimal(row['recalculated']['denominator_value']) for row in result['decisions']]==[50000,49900,50080]
    assert balance==50180


def test_fixed_quantity_deviation_is_not_hidden_by_consistent_supplied_orders():
    policy=frozen('fixed_contracts');events=fixture()
    result=assess(events,policy)
    assert result['status']=='MISMATCH',result
    assert len(result['decisions'])==1 # The2-contract closing order is not a new entry.
    assert result['decisions'][0]['reasons']==['fixed_policy_quantity_mismatch']
    policy['package']['configuration']['sizing']['policy']['contracts']=2
    result=assess(events,policy);assert result['status']=='MATCH',result


@pytest.mark.parametrize('damage', ['missing_context','wrong_cap','wrong_balance','future_context','future_stop','wrong_stop','daily_floor_unknown','actual_fill_field','duplicate_decision'])
def test_unverifiable_or_noncausal_decision_context_is_not_a_match(damage):
    events=simple();policy=frozen();decision=events[2]
    if damage=='missing_context':events.pop(2)
    elif damage=='wrong_cap':decision['account_state']['user_max_contracts']=60
    elif damage=='wrong_balance':decision['account_state']['equity_change_from_initial']='1'
    elif damage=='future_context':decision['context_known_at_utc']=time(10)
    elif damage=='future_stop':decision['initial_stop_known_at_utc']=time(10)
    elif damage=='wrong_stop':decision['initial_stop_price']='96'
    elif damage=='daily_floor_unknown':policy['package']['configuration']['sizing']['policy']['constrain_to_daily_cushion']=True
    elif damage=='actual_fill_field':decision['actual_entry_fill_price']='120'
    elif damage=='duplicate_decision':events.insert(3,dict(decision,event_id='another-decision',source_sequence=100))
    result=assess(events,policy);assert result['status']=='INSUFFICIENT_EVIDENCE',result


def test_wrong_quantity_and_skip_with_an_intent_are_explicit_mismatches():
    assert assess(simple(9))['status']=='MISMATCH'
    events=simple(0);events.insert(3,event(3,'intent',intent_id='i',signal_id='s',side='buy',quantity=1,reference_price='100',stop_price='95'))
    result=assess(events,frozen(risk_dollars='1'))
    assert result['status']=='MISMATCH' and not result['accepted_skip_signal_ids']


def test_provider_deduction_requires_new_causal_balance_snapshot():
    events=simple();events.insert(1,event(0,'cash',cash_event_id='w',category='provider_deduction',amount='100'))
    # Unique clocks/sequences, but old position snapshot predates withdrawal.
    for i,e in enumerate(events):e.update(event_id=f'e{i}',event_time_utc=time(i),source_sequence=i+1)
    decision=next(e for e in events if e['kind']=='sizing_decision');decision.update(position_event_id='e0',context_known_at_utc=time(0),initial_stop_known_at_utc=time(2))
    result=assess(events);assert result['status']=='INSUFFICIENT_EVIDENCE',result
    assert 'balance_changed_since_supplied_context' in result['reasons']


def test_schema_has_no_quantity_or_date_coercion():
    for change in (dict(submitted_quantity=True),dict(submitted_quantity='10'),dict(action='skip'),dict(context_known_at_utc=time(10)),dict(actual_fill='101')):
        with pytest.raises(ValueError):SizingDecision.model_validate(dict(known(),**change))


def test_withdrawal_reconciles_new_balance_before_next_percentage_decision():
    events=[event(0,'position',signed_quantity=0,account_balance='50000'),
        event(1,'cash',cash_event_id='withdrawal',category='provider_deduction',amount='100'),
        event(2,'position',signed_quantity=0,account_balance='49900'),
        event(3,'signal',signal_id='s',side='buy',quantity=9,reference_price='100',stop_price='95'),
        known(4,qty=9,balance='49900',position='e2',context_known_at_utc=time(2),initial_stop_known_at_utc=time(3)),
        event(5,'intent',intent_id='i',signal_id='s',side='buy',quantity=9,reference_price='100',stop_price='95')]
    result=assess(events,frozen('percentage_risk'));assert result['status']=='MATCH',result
    assert Decimal(result['decisions'][0]['recalculated']['denominator_value'])==49900
    assert result['decisions'][0]['recalculated']['quantity']==9


def test_low_cushion_floor_touch_minimum_and_short_direction():
    events=simple(1);events[2]['account_state']['account_floor_from_initial']='-15'
    result=assess(events,frozen(constrain_to_account_cushion=True))
    assert result['status']=='MATCH' and result['decisions'][0]['recalculated']['caps']['account_cushion']==1
    events=simple(0);events[2]['account_state']['account_floor_from_initial']='0'
    result=assess(events);assert result['status']=='MATCH'
    assert 'supplied_account_or_daily_floor_touched' in result['decisions'][0]['recalculated']['reasons']
    result=assess(simple(0),frozen(risk_dollars='15',minimum_contracts=2));assert result['status']=='MATCH'
    assert result['decisions'][0]['recalculated']['requested_contracts']==1
    events=simple(10)
    for row in events:
        if row['kind'] in ('signal','intent'):row.update(side='sell',stop_price='105')
        if row['kind']=='sizing_decision':row.update(side='short',initial_stop_price='105')
    assert assess(events)['status']=='MATCH'


def test_partial_fills_do_not_change_fixed_submitted_quantity_or_classify_exits_as_entries():
    events=fixture()
    for e in events:
        if e.get('quantity')==2:e['quantity']=3
        if e['kind']=='fill':e['commission']='1.5'
        if e['kind']=='position' and e.get('account_balance')=='50002':e['account_balance']='50003'
    opening=events[5];opening.update(quantity=1,commission='.5')
    second=dict(opening,event_id='second-fill',fill_id='f1-b',quantity=2,commission='1')
    events.insert(6,second)
    for i,e in enumerate(events):e.update(event_time_utc=time(i),source_sequence=i+1)
    result=assess(events,frozen('fixed_contracts'))
    assert result['status']=='MATCH' and len(result['decisions'])==1,result
    assert result['decisions'][0]['recalculated']['quantity']==3


def test_missing_ledger_verification_and_ambiguous_order_never_certify_dynamic_state():
    values=records(simple())
    result=evaluate_policy_conformance(frozen(),values,time(250))
    assert result['status']=='INSUFFICIENT_EVIDENCE'
    events=simple();events[2].update(event_time_utc=events[1]['event_time_utc'],source_sequence=None)
    assert assess(events)['status']=='INSUFFICIENT_EVIDENCE'


def test_no_decision_match_is_only_vacuous_arithmetic_not_coverage_or_edge():
    result=assess([event(0,'position',signed_quantity=0,account_balance='50000')])
    assert result['status']=='MATCH' and result['decisions']==[]
    assert result['broker_implementation_verified'] is False
    assert result['supplied_context_independently_verified'] is False


def test_later_received_correction_cannot_repair_an_earlier_decision():
    events=simple(9);original=events[2]
    correction=dict(original,event_id='later-correction',supersedes_event_id=original['event_id'],
        correction_reason='Claim corrected quantity',submitted_quantity=10)
    values=records(events);values.append(dict(sequence=len(values)+1,received_at_utc=time(300),event=correction))
    baseline=reconcile(declaration(require_protective_stop=False),values,time(250))
    result=evaluate_policy_conformance(frozen(),values,time(250),reconciliation=baseline)
    assert result['status']!='MATCH'
    assert result['excluded_late_received_event_ids']==['later-correction']
    assert result['decisions'][0]['supplied']['submitted_quantity']==9
    assert not result['accepted_skip_signal_ids']


@pytest.mark.parametrize('saved', [None,'0'*64])
def test_changed_or_missing_frozen_sizing_law_preserves_observations_but_withholds_comparison(saved):
    policy=frozen()
    if saved is None:policy['package']['implementation']['files'].pop('sizing.py')
    else:policy['package']['implementation']['files']['sizing.py']=saved
    result=assess(simple(),policy)
    assert result['status']=='INSUFFICIENT_EVIDENCE'
    assert result['reasons']==['frozen_sizing_implementation_missing_or_changed']
    assert result['sizing_implementation']['saved_sha256']==saved
    assert len(result['sizing_implementation']['current_sha256'])==64
    assert result['decisions']==[]


def test_completed_financial_horizon_export_is_known_at_later_assessment_clock():
    values=records(simple()) # Received200, financial horizon100, assessment250.
    baseline=reconcile(declaration(require_protective_stop=False),values,time(100))
    assert baseline['retrospective_import'] is True
    result=evaluate_policy_conformance(frozen(),values,time(250),reconciliation=baseline)
    assert result['status']=='MATCH',result
    assert result['decisions'][0]['recalculated']['quantity']==10


def test_flat_reentry_context_uses_commission_net_balance_after_partial_fills():
    events=fixture() # Two contracts: gross4, commissions2, exact flat balance50002.
    opening=events[5];opening.update(quantity=1,commission='.5')
    extra=dict(opening,event_id='partial-entry',fill_id='partial-entry',quantity=1,commission='.5',event_time_utc=time(5.5))
    events.append(extra)
    first=known(qty=2,position='event-0',stop='99.5',signal='s1')
    first.update(event_id='decision-first',event_time_utc=time(1.5))
    events.append(first)
    events.extend([event(17,'signal',signal_id='next',side='buy',quantity=4,reference_price='100',stop_price='99.75'),
        known(18,qty=4,signal='next',position='event-13',balance='50002',stop='99.75',
            context_known_at_utc=time(13),initial_stop_known_at_utc=time(17)),
        event(19,'intent',intent_id='next-order-intent',signal_id='next',side='buy',quantity=4,reference_price='100',stop_price='99.75')])
    events.sort(key=lambda e:datetime.fromisoformat(e['event_time_utc'].replace('Z','+00:00')))
    for i,e in enumerate(events):e['source_sequence']=i+1
    result=assess(events,frozen('percentage_risk',risk_percent='.004'))
    assert result['status']=='MATCH',result
    by_signal={row['signal_id']:row for row in result['decisions']}
    assert Decimal(by_signal['next']['recalculated']['denominator_value'])==50002
    assert by_signal['next']['recalculated']['quantity']==4
    assert Decimal(by_signal['next']['recalculated']['planned_risk_per_mnq'])==Decimal('.5')
