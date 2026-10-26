import csv,json
from pathlib import Path
from decimal import Decimal
import pytest
from alphaquest.backtest_runs import RunStore
from alphaquest.prop.adapter import adapt
from alphaquest.prop.analysis import prepare,execute
from alphaquest.prop.settings import DEFAULTS


def stored(tmp_path,quantities=(2,2,2)):
    store=RunStore(tmp_path);id='a'*32;folder=store.root/id;folder.mkdir()
    stamps=['2024-01-08T00:30:00Z','2024-01-08T15:00:00Z','2024-01-10T15:00:00Z']
    rows=[]
    for i,(stamp,q) in enumerate(zip(stamps,quantities)):
        slip=q*(i if i else 1)
        rows.append(dict(trade_number=i+1,side='long',contracts=q,entry_time_utc=stamp,exit_time_utc=stamp,reference_gross_pnl=20*q,total_commissions=2*q,slippage_cost=slip,gross_pnl=20*q-slip,net_pnl=18*q-slip))
    with (folder/'trades.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    record=dict(id=id,status='complete',summary=dict(trades_taken=3,**{target:str(sum(Decimal(r[src]) for r in rows)) for target,src in [('total_net_pnl','net_pnl'),('total_gross_pnl','gross_pnl'),('total_commissions','total_commissions'),('total_slippage_cost','slippage_cost')]}),run_metadata=dict(dataset=dict(source_timezone='America/New_York')),execution_settings=dict(commission_per_contract_per_side='1',tick_size='.25',point_value='10',slippage_ticks=1))
    with store.connect() as db:db.execute('INSERT INTO runs VALUES (?,?,?)',(id,'2024-01-01',json.dumps(record)))
    return store,id


def test_native_entry_timezone_weekends_and_zero_days(tmp_path):
    store,id=stored(tmp_path);f,s,c,o=prepare(store,id,dict(OOS_START_DATE=None,VALIDATION_SPLIT=0,PROP_MC_SIMS=8))
    assert f.trade_id.tolist()==[2,3]
    assert f.datetime.dt.hour.tolist()==[10,10]
    assert s['excluded']==[dict(trade_id=1,reason='weekend',datetime='2024-01-07T19:30:00')]
    assert s['reconciliation']['filtered_normalized_totals']['net']=='33'
    assert c['SLIPPAGE_PER_CONTRACT']==1.5
    assert c['COMMISSION_PER_CONTRACT']==2
    assert s['reconciliation']['nominal_round_trip_slippage']=='5.00'
    r=execute(f,c)
    assert r['statistics']['total_net']==33
    assert [d['n_trades'] for d in r['daily']]==[1,0,1]
    assert r['trades'][0]['source_entry_utc']=='2024-01-08T15:00:00Z'


def test_variable_quantity_opt_in_before_oos(tmp_path):
    store,id=stored(tmp_path,(2,2,3))
    with pytest.raises(ValueError,match='Variable'):prepare(store,id,dict(OOS_START_DATE='2024-01-10',VALIDATION_SPLIT=0))
    f,s,c,o=prepare(store,id,dict(OOS_START_DATE=None,VALIDATION_SPLIT=0,ALLOW_VARIABLE_CONTRACTS=True,PROP_MC_SIMS=8))
    assert f.profit_usd.tolist()==[20,20]
    assert f.contracts.tolist()==[1,1]
    assert f.source_quantity.tolist()==['2','3']
    assert execute(f,c)['statistics']['total_net']==33


def test_source_arithmetic_rejects_before_monte_carlo(tmp_path):
    store,id=stored(tmp_path);p=store.root/id/'trades.csv';p.write_text(p.read_text().replace('34','35'))
    with pytest.raises(ValueError,match='reconcile'):prepare(store,id,dict(OOS_START_DATE=None,VALIDATION_SPLIT=0))
