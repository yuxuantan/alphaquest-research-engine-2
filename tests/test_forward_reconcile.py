from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from alphaquest.forward_contracts import MonitorDeclaration,EventBatch,Control,Assessment
from alphaquest.forward_reconcile import reconcile,effective_records

BASE=datetime(2026,1,5,15,tzinfo=timezone.utc)
def time(n):return (BASE+timedelta(seconds=n)).isoformat().replace('+00:00','Z')
def declaration(**thresholds):
    return MonitorDeclaration(monitor_id=uuid4().hex,name='SYNTHETIC independent forward arithmetic',observation_kind='synthetic_harness',
        source={'source_id':'fixture','label':'SYNTHETIC supplied events'},instrument={'symbol':'MNQ','tick_size':'.25','point_value':'2'},thresholds=thresholds)
def event(n,kind,**values):return dict(event_id='event-'+str(n),source_sequence=n+1,event_time_utc=time(n),kind=kind,**values)
def fixture():
    return [event(0,'position',signed_quantity=0,account_balance='50000'),
        event(1,'signal',signal_id='s1',side='buy',quantity=2,reference_price='100',stop_price='99.5'),
        event(2,'intent',intent_id='i1',signal_id='s1',side='buy',quantity=2,reference_price='100',stop_price='99.5'),
        event(3,'order',order_id='o1',intent_id='i1',side='buy',quantity=2,execution_kind='synthetic'),
        event(4,'order_status',order_id='o1',status='acknowledged'),
        event(5,'fill',fill_id='f1',order_id='o1',side='buy',quantity=2,price='100',commission='1',execution_kind='synthetic'),
        event(6,'protection',protective_order_id='p1',order_id='o1',protection_type='stop',side='sell',quantity=2,trigger_price='99.5',status='active'),
        event(7,'signal',signal_id='s2',side='sell',quantity=2,reference_price='101'),
        event(8,'intent',intent_id='i2',signal_id='s2',side='sell',quantity=2,reference_price='101'),
        event(9,'order',order_id='o2',intent_id='i2',side='sell',quantity=2,execution_kind='synthetic'),
        event(10,'order_status',order_id='o2',status='acknowledged'),
        event(11,'fill',fill_id='f2',order_id='o2',side='sell',quantity=2,price='101',commission='1',execution_kind='synthetic'),
        event(12,'protection',protective_order_id='p1',order_id='o1',protection_type='stop',side='sell',quantity=2,trigger_price='99.5',status='cancelled'),
        event(13,'position',signed_quantity=0,account_balance='50002'),event(14,'market',price='101'),event(15,'heartbeat'),
        event(16,'connection',status='connected')]
def records(events):
    batch=EventBatch(batch_id=uuid4().hex,source_id='fixture',events=events)
    return [dict(sequence=i+1,received_at_utc=time(20),event=e.model_dump(mode='json')) for i,e in enumerate(batch.events)]


def test_exact_fill_commission_net_and_causal_latency_without_fill_simulation():
    value=reconcile(declaration(),records(fixture()),time(25));metrics=value['metrics']
    assert Decimal(metrics['gross_realized_pnl'])==4
    assert Decimal(metrics['commissions'])==2
    assert Decimal(metrics['net_realized_pnl'])==2
    assert Decimal(metrics['net_trading_equity'])==50002
    assert metrics['completed_flat_to_flat_trades']==1 and metrics['signed_position']==0
    assert value['advisory']['state']=='ACTIVE'
    assert [r['seconds'] for r in value['reconciliation']['latency']['measurements']]==[2,1,2,2,1,2]
    assert not value['reconciliation']['costs']['slippage_deducted_again']


def test_correction_preserves_original_records_and_recomputes_new_snapshot():
    original=records(fixture());before=deepcopy(original)
    replacement=deepcopy(original[11]['event']);replacement.update(event_id='corrected-fill',price='100.5',supersedes_event_id='event-11',correction_reason='Correct supplied execution price')
    original.append(dict(sequence=len(original)+1,received_at_utc=time(22),event=replacement))
    result=reconcile(declaration(),original,time(25))
    assert original[:-1]==before
    assert Decimal(result['metrics']['gross_realized_pnl'])==2 and Decimal(result['metrics']['net_realized_pnl'])==0
    assert len(effective_records(original))==len(before)
    assert 'account_balance_mismatch' in result['advisory']['reasons']


def test_unknown_tie_retains_position_but_withholds_path_dependent_money():
    data=fixture();data[5]['event_time_utc']=data[6]['event_time_utc'];data[5]['source_sequence']=None
    result=reconcile(declaration(),records(data),time(25))
    assert result['advisory']['state']=='PAUSED'
    assert result['metrics']['gross_realized_pnl'] is None and result['metrics']['max_observed_drawdown'] is None
    assert result['metrics']['signed_position']==0
    assert Decimal(result['metrics']['commissions'])==2


def test_missing_protection_stale_data_and_advisory_latch():
    data=fixture()[:6]+[event(14,'market',price='100'),event(15,'heartbeat'),event(16,'connection',status='connected')]
    result=reconcile(declaration(),records(data),time(25))
    assert result['advisory']['state']=='PAUSED' and 'missing_protective_stop' in result['advisory']['reasons']
    stale=reconcile(declaration(),records(fixture()),time(100))
    assert {'stale_market_data','stale_heartbeat'}<=set(stale['advisory']['reasons'])
    recovered=reconcile(declaration(),records(fixture()),time(25),pause_latched=True)
    assert recovered['advisory']['state']=='PAUSED' and recovered['advisory']['recovery_required']
    assert recovered['advisory']['order_placement_enabled'] is False


def test_request_deduction_receipt_are_distinct_cash_facts():
    data=fixture()+[event(17,'cash',cash_event_id='request',category='payout_request',amount='50',request_amount_basis='trader_entitlement'),
        event(18,'cash',cash_event_id='deduction',category='provider_deduction',amount='60',related_cash_event_id='request'),
        event(19,'cash',cash_event_id='receipt',category='trader_receipt',amount='50',related_cash_event_id='request')]
    result=reconcile(declaration(),records(data),time(25));m=result['metrics']
    assert Decimal(m['net_realized_pnl'])==2 and Decimal(m['trader_receipts'])==50
    assert Decimal(m['provider_deductions'])==60 and Decimal(m['provider_balance_from_observed_ledger'])==49942
    assert Decimal(m['pending_receipt_amount'])==0


@pytest.mark.parametrize('bad',[float('nan'),1,'NaN','Infinity','1e3',{},'0.'+'0'*21+'1'])
def test_bad_money_fails_strict_contract(bad):
    data=fixture();data[5]['commission']=bad
    with pytest.raises(ValueError):records(data)


def test_unverified_actual_mode_needs_policy_and_server_receive_clock_is_not_input():
    d=declaration().model_dump(mode='json');d['observation_kind']='actual_import'
    with pytest.raises(ValueError):MonitorDeclaration.model_validate(d)
    data=fixture();data[5]['received_at_utc']=time(5)
    with pytest.raises(ValueError):records(data)
    with pytest.raises(ValueError):Control(request_id=uuid4().hex,action='resume',reason='No current acknowledgement')


def test_duplicate_id_different_payload_and_correction_fork_reject():
    rows=records(fixture());changed=deepcopy(rows[5]);changed['event']['price']='999';changed['sequence']=100
    with pytest.raises(ValueError,match='conflicting'):effective_records(rows+[changed])
    replacement=deepcopy(rows[5]);replacement['event'].update(event_id='repair',supersedes_event_id='event-5',correction_reason='repair');replacement['sequence']=100
    second=deepcopy(replacement);second['sequence']=101;second['event']['event_id']='fork'
    with pytest.raises(ValueError,match='active earlier'):effective_records(rows+[replacement,second])


def test_unknown_request_entitlement_does_not_fabricate_pending_receipt():
    from tests.test_forward_reconcile import event
    data=fixture()+[event(17,'cash',cash_event_id='gross-request',category='payout_request',amount='1000',request_amount_basis='gross_withdrawal'),
        event(18,'cash',cash_event_id='deduction',category='provider_deduction',amount='1000',related_cash_event_id='gross-request'),
        event(19,'cash',cash_event_id='receipt',category='trader_receipt',amount='900',related_cash_event_id='gross-request')]
    unknown=reconcile(declaration(),records(data),time(25))
    assert unknown['metrics']['pending_receipt_amount'] is None
    assert Decimal(unknown['metrics']['trader_receipts'])==900
    data[-3]['expected_trader_amount']='900'
    known=reconcile(declaration(),records(data),time(25))
    assert Decimal(known['metrics']['pending_receipt_amount'])==0
    assert Decimal(known['metrics']['provider_deductions'])==1000


def test_missing_initial_account_state_never_invents_whole_account_profit():
    value=reconcile(declaration(),records(fixture()[1:]),time(25))
    assert 'initial_flat_account_state_unverified' in value['advisory']['reasons']
    assert value['metrics']['net_realized_pnl'] is None
    assert value['metrics']['commissions']=='2' and value['metrics']['signed_position']==0


def test_prefill_position_without_balance_retains_original_verified_anchor():
    data=fixture();extra=event(0,'position',signed_quantity=0)
    extra.update(event_id='second-flat-snapshot',event_time_utc=time(0).replace('00Z','00.500000Z'),source_sequence=2)
    for row in data[1:]:row['source_sequence']+=1
    data.insert(1,extra)
    result=reconcile(declaration(),records(data),time(25))
    assert result['advisory']['state']=='ACTIVE',result
    assert result['reconciliation']['position']['initial_flat_account_state_verified']
    assert Decimal(result['metrics']['net_realized_pnl'])==2


@pytest.mark.parametrize('bad',[0,1,'false',None])
def test_order_placement_capability_is_strict_false(bad):
    value=declaration().model_dump(mode='json');value['order_placement_enabled']=bad
    with pytest.raises(ValueError):MonitorDeclaration.model_validate(value)


def test_inconsistent_gross_request_entitlement_is_retained_and_pending_withheld():
    data=fixture()+[event(17,'cash',cash_event_id='request',category='payout_request',amount='1000',request_amount_basis='gross_withdrawal',expected_trader_amount='1500'),
        event(18,'cash',cash_event_id='receipt',category='trader_receipt',amount='600',related_cash_event_id='request')]
    result=reconcile(declaration(),records(data),time(25))
    assert result['advisory']['state']=='PAUSED'
    assert 'trader_entitlement_exceeds_gross_request' in result['advisory']['reasons']
    assert result['metrics']['pending_receipt_amount'] is None
    assert Decimal(result['metrics']['payout_requests'])==1000 and Decimal(result['metrics']['trader_receipts'])==600


def test_net_trader_cash_subtracts_paid_acquisition_fees_not_provider_deductions():
    data=fixture()+[event(17,'cash',cash_event_id='request',category='payout_request',amount='50',request_amount_basis='trader_entitlement'),
        event(18,'cash',cash_event_id='receipt',category='trader_receipt',amount='50',related_cash_event_id='request'),
        event(19,'cash',cash_event_id='eval',category='evaluation_purchase_fee',amount='30'),
        event(20,'cash',cash_event_id='activate',category='activation_fee',amount='40'),
        event(21,'cash',cash_event_id='deduct',category='provider_deduction',amount='60',related_cash_event_id='request')]
    rows=records(data)
    for row in rows:row['received_at_utc']=time(22)
    result=reconcile(declaration(),rows,time(25))
    assert Decimal(result['metrics']['net_trader_cash'])==-20
    assert Decimal(result['metrics']['net_realized_pnl'])==2
    assert Decimal(result['metrics']['provider_deductions'])==60
