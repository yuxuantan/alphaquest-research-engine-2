"""Independent adversarial causal, exposure and exact-fill oracles."""
from copy import deepcopy
from decimal import Decimal
from tests.test_forward_reconcile import declaration,event,fixture,records,time
from alphaquest.forward_reconcile import reconcile


def end(position=0,balance=None,price='100',start=13):
    return [event(start,'position',signed_quantity=position,**({'account_balance':balance} if balance is not None else {})),
        event(start+1,'market',price=price),event(start+2,'heartbeat'),event(start+3,'connection',status='connected')]


def test_cancelled_protective_order_fill_is_unresolved():
    data=fixture()[:7]
    data += [event(7,'protection',protective_order_id='p1',order_id='o1',protection_type='stop',side='sell',quantity=2,trigger_price='99.5',status='cancelled'),
        event(8,'fill',fill_id='stop-fill',order_id='p1',side='sell',quantity=2,price='99.5',commission='1',execution_kind='synthetic')]
    result=reconcile(declaration(),records(data+end(balance='49996',price='99.5')),time(25))
    assert result['advisory']['state']=='PAUSED',result


def test_partial_protection_fills_accumulate_against_declared_quantity():
    data=fixture()[:7]
    data += [event(n,'fill',fill_id='stop-fill-'+str(n),order_id='p1',side='sell',quantity=1,price='99.5',commission='.5',execution_kind='synthetic') for n in (7,8,9)]
    result=reconcile(declaration(require_protective_stop=False),records(data+end(position=-1,balance='49995.5',price='99.5')),time(25))
    assert result['advisory']['state']=='PAUSED',result


def test_supplied_position_average_is_reconciled_against_actual_lots():
    data=fixture()[:7]+[event(7,'position',signed_quantity=2,average_entry_price='999',account_balance='49999'),
        event(8,'market',price='100'),event(9,'heartbeat'),event(10,'connection',status='connected')]
    result=reconcile(declaration(),records(data),time(25))
    assert result['advisory']['state']=='PAUSED',result


def test_intent_without_any_order_is_not_an_active_reconciled_signal():
    data=fixture()[:3]+end(balance='50000')
    result=reconcile(declaration(),records(data),time(50))
    assert result['advisory']['state']!='ACTIVE',result
    assert any('order' in code or 'signal' in code for code in result['advisory']['reasons']),result


def test_equal_time_unsequenced_market_marks_do_not_pick_a_final_equity():
    data=fixture()[:7]+[event(7,'position',signed_quantity=2,average_entry_price='100',account_balance='49999')]
    mark1=event(8,'market',price='100');mark1['source_sequence']=None
    mark2=event(9,'market',price='90');mark2.update(source_sequence=None,event_time_utc=mark1['event_time_utc'])
    tail=[event(10,'heartbeat'),event(11,'connection',status='connected')]
    first=reconcile(declaration(),records(data+[mark1,mark2]+tail),time(25))
    second=reconcile(declaration(),records(data+[mark2,mark1]+tail),time(25))
    assert first['metrics']['net_trading_equity']==second['metrics']['net_trading_equity'],(first['metrics'],second['metrics'])
    assert first['metrics']['net_trading_equity'] is None and first['metrics']['max_observed_drawdown'] is None


def test_old_episode_stop_is_not_silently_bound_to_new_entry_intent():
    data=[e for e in fixture() if e['kind']!='protection' or e['status']!='cancelled']
    data += [event(17,'signal',signal_id='s3',side='buy',quantity=2,reference_price='101',stop_price='98'),
        event(18,'intent',intent_id='i3',signal_id='s3',side='buy',quantity=2,reference_price='101',stop_price='98'),
        event(19,'order',order_id='o3',intent_id='i3',side='buy',quantity=2,execution_kind='synthetic'),
        event(20,'order_status',order_id='o3',status='acknowledged'),
        event(21,'fill',fill_id='f3',order_id='o3',side='buy',quantity=2,price='101',commission='1',execution_kind='synthetic')]
    data+=end(position=2,balance='50001',price='101',start=22)
    rows=records(data)
    for row in rows:row['received_at_utc']=time(30)
    result=reconcile(declaration(),rows,time(40))
    assert result['advisory']['state']=='PAUSED',result
    assert any('protect' in code or 'stop' in code for code in result['advisory']['reasons']),result


def test_partial_fill_commission_and_slippage_independent_exact_math():
    data=fixture()
    first=deepcopy(data[5]);first.update(quantity=1,commission='.25')
    second=deepcopy(first);second.update(event_id='entry-part-two',fill_id='f1-part-two',price='100.5')
    exit1=deepcopy(data[11]);exit1.update(quantity=1,commission='.25')
    exit2=deepcopy(exit1);exit2.update(event_id='exit-part-two',fill_id='f2-part-two',price='101.5')
    data=data[:5]+[first,second]+data[6:11]+[exit1,exit2]+data[12:]
    for i,e in enumerate(data):e.update(event_time_utc=time(i),source_sequence=i+1)
    data[-4]['account_balance']='50003'
    result=reconcile(declaration(),records(data),time(25));m=result['metrics']
    assert Decimal(m['gross_realized_pnl'])==4 and Decimal(m['commissions'])==1
    assert Decimal(m['net_realized_pnl'])==3 and Decimal(m['net_trading_equity'])==50003
    assert m['completed_flat_to_flat_trades']==1 and m['signed_position']==0
    assert result['advisory']['state']=='ACTIVE',result
    assert result['reconciliation']['costs']['slippage_deducted_again'] is False


def test_pre_entry_market_mark_does_not_create_a_held_position_peak():
    data=fixture()[:7]+[event(7,'position',signed_quantity=2,average_entry_price='100',account_balance='49999'),
        event(8,'market',price='100'),event(9,'heartbeat'),event(10,'connection',status='connected')]
    prior=event(0,'market',price='110');prior.update(event_id='earlier-flat-market',event_time_utc='2026-01-05T14:59:59Z',source_sequence=None)
    result=reconcile(declaration(),records([prior]+data),time(25))
    # Only actual entry commission ($1), then the first mark while held at100.
    # Earlier110 while flat is not an observed profitable mark on the position.
    assert result['metrics']['max_observed_drawdown'] in (None,'1'),result['metrics']
