"""Training-only acquisition calibration and independent ranking/leakage checks."""
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from alphaquest.prop import native_analysis as model


def chosen(passed=750):return dict(micros=12,passed=passed,simulations=3000)


def test_training_cost_and_time_are_derived_without_holdout_or_fixed_defaults(monkeypatch):
    train=[[(500.,40.)]];calls=[]
    def chain(days,size,sims,seed,block,**kwargs):
        assert days is train
        calls.append((size,sims,seed,block,kwargs))
        return dict(days=np.array([11,21,31])) # includes activation in the engine
    monkeypatch.setattr(model,'evaluation',chain)
    result=model.training_economics(train,chosen(),model.resolved_settings({}),5,40,['2020-01-01','2020-12-31'])
    assert result['status']=='calibrated'
    assert result['pass_rate']==.25 and result['cost_per_funded']==325 # 49/.25+129
    assert result['evaluations_per_funded']==4 and result['replacement_days']==21
    assert result['activation_days']==1 and result['sample']==['2020-01-01','2020-12-31']
    assert calls==[(12,20000,45,5,dict(chain=True,max_micros=40))]


def test_no_training_passes_never_launch_chain_or_substitute_a_probability(monkeypatch):
    monkeypatch.setattr(model,'evaluation',lambda *a,**k:pytest.fail('No successful training evaluation; no chain may launch'))
    result=model.training_economics([],chosen(0),model.resolved_settings({}),5,40,['a','b'])
    assert result['status']=='unavailable' and result['pass_rate']==0
    assert result['funding_chain_simulations']==0
    assert result['cost_per_funded'] is None and result['replacement_days'] is None
    assert 'No training evaluation passed' in result['reason']


def test_training_funding_time_bound_does_not_fall_back_to_five_days(monkeypatch):
    def bound(*a,**k):raise ValueError('No pass within the 10,000-attempt funding-time bound; acquisition time is unavailable.')
    monkeypatch.setattr(model,'evaluation',bound)
    result=model.training_economics([],chosen(),model.resolved_settings({}),5,40,['a','b'])
    assert result['status']=='unavailable' and result['replacement_days'] is None
    assert result['cost_per_funded']==325 and 'funding time is unavailable' in result['reason']


def test_acquisition_cost_can_reverse_the_size_ranking_using_independent_decimal_math(monkeypatch):
    def accounts(days,size,sims,seed,block,**kwargs):
        assert sims==3000 and seed==42
        payout,life=(1000.,100) if size==5 else (600.,40)
        return [SimpleNamespace(payouts=[(5,payout)],day=life,outcome='open') for _ in range(sims)]
    monkeypatch.setattr(model,'funded',accounts)
    winners=[]
    for rate in (.525,.21745):
        cost=49/rate+129
        economics=dict(pass_rate=rate,cost_per_funded=cost,replacement_days=5.)
        rows=[model._funded_size(([],size,5,model.Rules(),40,economics)) for size in (5,20)]
        for row,payout,life in zip(rows,(1000,600),(100,40)):
            expected=Decimal(261)*(Decimal(payout)-(Decimal(49)/Decimal(str(rate))+Decimal(129)))/(Decimal(life)+Decimal(5))
            assert row['slot_year']==pytest.approx(float(expected))
            assert row['acquisition_cost']==cost and row['evaluation_pass_rate']==rate
        winners.append(max(rows,key=lambda r:r['slot_year'])['micros'])
    assert winners==[20,5] # Cost is common, but the faster account replaces more often.


def source(training=3000,holdout=3000):
    rows=[]
    for index,day in enumerate(pd.bdate_range('2026-01-05',periods=8)):
        entry=day.to_pydatetime().replace(hour=18,tzinfo=timezone.utc)
        net=training if index<4 else holdout
        rows.append(dict(trade_id=index+1,entry_utc=entry.isoformat(),exit_utc=(entry+timedelta(minutes=1)).isoformat(),
                         source_net_pnl=str(net),export_net_pnl=None,quantity='1',measured_mae=str(max(0,-net)),measured_mfe=None))
    return rows


def settings():return model.resolved_settings(dict(MAX_TOTAL_NQ='0.3',OUT_OF_SAMPLE_FROM='2026-01-09'))


def test_actual_standard_count_simulations_freeze_selection_before_any_holdout_changes(monkeypatch):
    original=model.evaluation;calls=[];fitted=[]
    original_funded=model._funded_size
    def fit(value):
        fitted.append(value[1])
        return original_funded(value)
    monkeypatch.setattr(model,'_funded_size',fit)
    def observe(days,size,sims,seed,block,**kwargs):
        if seed==43:assert fitted==[1,2,3], 'Funded size must be selected before holdout runs'
        calls.append((seed,kwargs.get('chain',False)))
        return original(days,size,sims,seed,block,**kwargs)
    monkeypatch.setattr(model,'evaluation',observe)
    results=[]
    for heldout in (3000,1500,0):
        calls.clear();fitted.clear();r=model.calculate(source(holdout=heldout),settings());results.append(r)
        assert r['training_economics']['pass_rate']==1
        assert r['training_economics']['simulations']==3000
        assert r['training_economics']['funding_chain_simulations']==20000
        assert r['training_economics']['cost_per_funded']==178
        assert r['training_economics']['replacement_days']==11
        assert r['funded']['selected']['micros']==3 and r['funded']['selected']['sims']==20000
        assert r['funded']['selection_economics']==r['training_economics']
        assert r['history']['acquisition_economics']==dict(source='training',cost_per_funded=178.,replacement_days=11.)
        assert all(row['sims']==3000 and row['replacement_days']==11 for row in r['funded']['sweep'])
        assert calls.index((45,True))<calls.index((43,False))
    assert results[0]['evaluation']['days_to_funded']==11
    assert results[1]['evaluation']['days_to_funded']==21
    assert results[2]['evaluation']['pass_rate']==0 and results[2]['evaluation']['cost_per_funded'] is None
    assert results[0]['training_economics']==results[1]['training_economics']==results[2]['training_economics']
    assert results[0]['funded']['sweep']==results[1]['funded']['sweep']==results[2]['funded']['sweep']


def test_good_holdout_cannot_rescue_no_training_passes():
    r=model.calculate(source(training=0,holdout=3000),settings())
    assert r['evaluation']['pass_rate']==1 # Validation is still reported independently.
    assert r['training_economics']['pass_rate']==0
    assert r['funded'] is None and r['history'] is None
    assert 'No training evaluation passed' in r['unavailable']


def test_holdout_funding_time_bound_does_not_undo_training_selection(monkeypatch):
    original=model.evaluation
    def bounded(days,size,sims,seed,block,**kwargs):
        if seed==44:raise ValueError('No pass within the 10,000-attempt funding-time bound; acquisition time is unavailable.')
        return original(days,size,sims,seed,block,**kwargs)
    monkeypatch.setattr(model,'evaluation',bounded)
    r=model.calculate(source(),settings())
    assert r['funded']['selected']['micros']==3 and r['history'] is not None
    assert r['evaluation']['days_to_funded'] is None
    assert r['training_economics']['replacement_days']==11
    assert 'timing_unavailable' in r['evaluation']
