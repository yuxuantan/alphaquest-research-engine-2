"""Follow-up boundaries after seven original staged fixes."""
from copy import deepcopy
from tests.test_forward_reconcile import declaration,event,fixture,records,time
from alphaquest.forward_reconcile import reconcile


def test_unknown_cost_basis_does_not_become_fifo_after_one_lot_is_closed():
    data=fixture()
    first=deepcopy(data[5]);first.update(quantity=1,commission='0')
    second=deepcopy(first);second.update(event_id='entry-part-two',fill_id='f1-part-two',price='110')
    out=[]
    for row in data[7:12]:
        row=deepcopy(row)
        if 'quantity' in row:row['quantity']=1
        if row['kind']=='fill':row.update(price='110',commission='0')
        out.append(row)
    tail=[event(14,'position',signed_quantity=1,average_entry_price='105'),
        event(15,'market',price='110'),event(16,'heartbeat'),event(17,'connection',status='connected')]
    data=data[:5]+[first,second]+out+tail
    for i,row in enumerate(data):row.update(event_time_utc=time(i),source_sequence=i+1)
    result=reconcile(declaration(require_protective_stop=False,maximum_slippage_ticks='1000'),records(data),time(25))
    assert 'average_entry_price_mismatch' not in result['advisory']['reasons'],result
    assert 'position_cost_basis_unknown' in result['advisory']['reasons'],result


def test_recovery_does_not_claim_fresh_health_when_no_heartbeat_is_observed():
    data=[row for row in fixture() if row['kind']!='heartbeat']
    result=reconcile(declaration(),records(data),time(25),pause_latched=True)
    assert result['advisory']['state']=='PAUSED'
    assert result['recovery']['eligible_for_acknowledgement'] is False,result


def test_conflicting_same_time_connection_states_never_choose_active_from_insertion_order():
    data=fixture()[:-1]
    connected=fixture()[-1];connected['source_sequence']=None
    disconnected=deepcopy(connected);disconnected.update(event_id='disconnect-tie',status='disconnected')
    left=reconcile(declaration(),records(data+[connected,disconnected]),time(25))
    right=reconcile(declaration(),records(data+[disconnected,connected]),time(25))
    assert left['advisory']['state']==right['advisory']['state']=='PAUSED',(left['advisory'],right['advisory'])
