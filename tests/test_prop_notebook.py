from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prop_notebook_reference import reference
from alphaquest.prop.analysis import execute,clean
from alphaquest.prop.settings import DEFAULTS
from alphaquest.prop.model import NotebookModel


def frame():
    stamps=pd.to_datetime(['2024-01-01 10:00','2024-01-01 11:00','2024-01-03 10:00','2024-01-05 10:00','2024-01-08 10:00','2024-01-10 10:00'])
    return pd.DataFrame(dict(trade_id=range(1,7),direction=['LONG']*6,datetime=stamps,date=stamps.normalize(),profit_usd=[800.,-1700.,1000.,600.,-1100.,2200.],contracts=[1.]*6))


def settings(**extra):return {**DEFAULTS,'OOS_START_DATE':None,'PROP_MC_SIMS':64,'N_SPAGHETTI':20,**extra}

@pytest.mark.parametrize('mode',['daily','trade','excursion'])
@pytest.mark.parametrize('block',[1,5,10])
def test_main_exact_against_fresh_notebook(mode,block):
    s=settings(ENGINE=mode,BOOTSTRAP_BLOCK=block)
    actual=execute(frame(),s);expected=reference(frame(),s)
    assert actual['evaluation']==clean(expected['res'])
    assert actual['paths']['equity']==clean(expected['paths'])
    assert actual['daily']==clean(expected['daily_full'].to_dict('records'))
    assert actual['statistics']['bootstrap_usd_ci']==[expected['lo'],expected['hi']]
    assert sum(actual['evaluation'][k] for k in ('passed','fail_dd','fail_time'))==64
    assert actual['engine']['effective']==('trade' if mode=='excursion' else mode)


def test_bounded_bootstrap_preserves_draw_order():
    data=np.arange(317.)
    m=NotebookModel();actual,lo,hi=m.bootstrap_ci(data,sims=10000)
    rng=np.random.default_rng(42);expected=rng.choice(data,size=(10000,len(data)),replace=True).mean(axis=1)
    np.testing.assert_array_equal(actual,expected)


def test_instances_do_not_share_simulation_state():
    first=execute(frame(),settings());execute(frame(),settings(SEED=99,BOOTSTRAP_BLOCK=10))
    assert execute(frame(),settings())==first

@pytest.mark.parametrize('mode',['daily','trade','excursion'])
@pytest.mark.parametrize('split',[0,.3])
def test_sizing_and_attempts_exact(mode,split):
    s=settings(ENGINE=mode,VALIDATION_SPLIT=split,STAGED_SIMS=64)
    actual=execute(frame(),s,2);expected=reference(frame(),s,2)
    assert actual['sizing']['sweep']==clean(expected['sweep_data'])
    assert actual['sizing']['selected']==clean(expected['_best'])
    assert actual['sizing']['validation']==clean(expected['_val'])
    assert actual['sizing']['staged_raw']==clean(expected['_rows'])
    assert actual['sizing']['flat_pass_rate']==expected['_p_flat']
    assert actual['paths']['equity']==clean(expected['paths'])
    assert actual['paths']['outcomes']==clean(expected['outcomes'])
    for row in actual['attempts']['correlated']:
        for rho in s['RHO_GRID']:assert row[f'rho_{rho:g}']==expected['_p_within_n'](expected['_p_att'],row['attempts'],rho)
    assert actual['statistics']['bootstrap_usd_ci']==execute(frame(),s,1)['statistics']['bootstrap_usd_ci']


def test_attempt_probabilities_independent_arithmetic():
    model=NotebookModel()
    assert model._p_within_n(.5,2,0)==.75
    assert model._p_within_n(.5,2,.5)==.625
    assert model._p_within_n(0,6,.3)==0
    assert model._p_within_n(1,6,.3)==1

@pytest.mark.parametrize('mode',['daily','trade','excursion'])
def test_funded_sweep_and_detail_exact(mode):
    s=settings(ENGINE=mode,STAGED_SIMS=64,PAYOUT_SIMS=64,PAYOUT_SWEEP_SIMS=32,PAYOUT_MAX_HORIZON=35,PAYOUT_CONTRACTS=[.3,.7,1.5])
    actual=execute(frame(),s,3);expected=reference(frame(),s,3)
    assert actual['funded']['sweep']==clean(expected['payout_sweep'])
    assert actual['funded']['selected']==clean(expected['best'])
    assert actual['funded']['detail']==clean(expected['detail'])

@pytest.mark.parametrize('pnl,outcome,days,payout',[(600,'qualified',5,900),(-1100,'blown',None,0),(0,'closed_inactive',None,0),(100,'timeout',None,0)])
def test_funded_deterministic_boundaries(pnl,outcome,days,payout):
    f=frame();f.profit_usd=pnl
    s=settings(VALIDATION_SPLIT=0,COMMISSION_PER_CONTRACT=0,SLIPPAGE_PER_CONTRACT=0,STAGED_SIMS=8,PAYOUT_SIMS=8,PAYOUT_SWEEP_SIMS=8,PAYOUT_CONTRACTS=[1],PAYOUT_MAX_HORIZON=30)
    # Every weekday has one identical trade, removing bootstrap variability.
    f=f.iloc[:1].copy()
    actual=execute(f,s,3)['funded']['detail']
    assert actual[outcome]==8
    assert actual['expected_payout']==payout
    if days:assert actual['days_to_qualify']==[days]*8

@pytest.mark.parametrize('block',[1,5,10])
def test_lifetime_economics_and_robustness_exact(block):
    s=settings(BOOTSTRAP_BLOCK=block,STAGED_SIMS=32,PAYOUT_SIMS=32,PAYOUT_SWEEP_SIMS=16,PAYOUT_MAX_HORIZON=35,PAYOUT_CONTRACTS=[.3,.7,1.5],LIFETIME_SWEEP_SIMS=16,LIFETIME_HORIZON=55)
    actual=execute(frame(),s,4);expected=reference(frame(),s,4)
    assert actual['lifetime']['sweep']==clean(expected['lifetime_sweep'])
    assert actual['lifetime']['selected']==clean(expected['best_life'])
    assert actual['lifetime']['observations']==clean(expected['_reference_lifetime_observations'])
    assert actual['economics']['acquisition_cost']==clean(expected['_acq_cost'])
    assert actual['economics']['expected_net']==clean(expected['_net'])
    assert actual['economics']['return_multiple']==clean(expected['_mult'])
    assert actual['robustness_raw']==clean(expected['_reference_robustness'])
    assert actual['source_equity']['equity']==clean(expected['_eq'].to_numpy())


def test_lifetime_ladder_independent_arithmetic():
    f=frame().iloc[:1].copy();f.profit_usd=600
    s=settings(VALIDATION_SPLIT=0,COMMISSION_PER_CONTRACT=0,SLIPPAGE_PER_CONTRACT=0,STAGED_SIMS=8,PAYOUT_SIMS=8,PAYOUT_SWEEP_SIMS=8,PAYOUT_CONTRACTS=[1],SWEEP_CONTRACTS=[1],LIFETIME_SWEEP_SIMS=8,LIFETIME_HORIZON=100)
    r=execute(f,s,4)
    # Request every 5 qualified days: first 900, then 1500/2000/2500/2500/3000.
    assert r['lifetime']['selected']['expected_total']==12400
    assert r['lifetime']['selected']['outcome_ct']['ladder_done']==8
    assert r['lifetime']['selected']['avg_days_alive']==30
    assert r['economics']['acquisition_cost']==240
    assert r['economics']['expected_net']==12160
    assert r['economics']['verdict']=='STRONG'


def test_selection_fallbacks_and_zero_pass_economics():
    f=frame().iloc[:1].copy();f.profit_usd=-1100
    s=settings(VALIDATION_SPLIT=0,COMMISSION_PER_CONTRACT=0,SLIPPAGE_PER_CONTRACT=0,STAGED_SIMS=8,PAYOUT_SIMS=8,PAYOUT_SWEEP_SIMS=8,PAYOUT_CONTRACTS=[1,2],LIFETIME_SWEEP_SIMS=8,LIFETIME_HORIZON=50,MAX_BLOWN_RATE=0)
    r=execute(f,s,4);expected=reference(f,s,4)
    assert r['funded']['selection_fallback'] is True
    assert r['lifetime']['selection_fallback'] is True
    assert r['lifetime']['selected']==clean(expected['best_life'])
    assert r['economics']['acquisition_cost'] is None
    assert r['economics']['expected_net'] is None
    assert r['economics']['verdict']=='NEGATIVE EV'
    assert all(x['expected_total']==0 for x in r['lifetime']['sweep'])


def test_measured_excursion_engine_exact_from_notebook():
    # Native saved trades have no measured excursions. Test the extracted
    # excursion engine against the original when explicitly supplied coverage.
    s=settings(ENGINE='excursion')
    m=NotebookModel();m.overrides=s;m.cell_2();m.df=frame();m.cell_4();m.df_sim['mae_usd']=[900,1800,1100,700,1200,2300];m.HAS_EXCURSIONS=True;m.EXCURSION_COVERAGE=1.
    m.cell_6();m.cell_8();m.cell_9();m.cell_10()
    original=reference(frame(),s)
    # Fresh original namespace; swap bag MAE only, preserving original P&L.
    original['TRADE_BAG'][:]=m.TRADE_BAG
    expected=original['simulate_apex_excursion'](m.daily_pool,original['CHALLENGE'],64,1,np.random.default_rng(42))
    assert clean(m.res)==clean(expected)
    assert m.ENGINE=='excursion'
