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
