from dataclasses import asdict,replace
import json
import numpy as np
import pytest
from alphaquest.prop import native_backend as backend,native_engine as reference
from test_backtest_api import client,body
from test_automatic_prop import save_history,expected_cash


@pytest.mark.parametrize('seed,block,micros',[(42,1,1),(42,5,9),(43,10,25),(44,5,40)])
def test_compiled_model_matches_every_reference_account_and_rng_result(seed,block,micros):
    assert backend.compiled is not None,'Build the optional compiled backend for qualification'
    accelerated=backend.compiled
    days=[[(800.,0.),(-350.,600.),(0.,0.)],[],[(-2700.,2700.),(450.,0.)],[(1700.,100.),(900.,0.)]]
    left=reference.evaluation(days,micros,120,seed,block)
    right=accelerated.evaluation(days,micros,120,seed,block)
    assert all(np.array_equal(left[k],right[k]) for k in left)
    for approval in (True,False):
        rules=replace(reference.Rules(),approval_day_counts=approval)
        left=reference.funded(days,micros,120,seed,block,horizon=261,rules=rules)
        right=accelerated.funded(days,micros,120,seed,block,horizon=261,rules=rules)
        assert [asdict(a) for a in left]==[asdict(a) for a in right]
    for engine in (reference,accelerated):
        a=engine.FundedAccount(equity=100.,high=2100.,locked=True);a.advance([(0.,0.)],1)
        assert a.outcome=='blown'
    left=reference.evaluation([[(800.,0.)],[],[(-500.,500.)]],25,100,seed,block,chain=True)
    right=accelerated.evaluation([[(800.,0.)],[],[(-500.,500.)]],25,100,seed,block,chain=True)
    assert all(np.array_equal(left[k],right[k]) for k in left)


def test_missing_compiled_backend_has_explicit_reference_fallback(monkeypatch):
    monkeypatch.setattr(backend,'compiled',None)
    monkeypatch.setenv('ALPHAQUEST_PROP_BACKEND','auto')
    assert backend.identity()['name']=='python'
    monkeypatch.setenv('ALPHAQUEST_PROP_BACKEND','compiled')
    with pytest.raises(RuntimeError,match='Rebuild'):backend.module()


def test_standard_count_portal_calculations_match_reference_exactly(client,monkeypatch,tmp_path):
    dataset=save_history(client);request=body(dataset['id'])
    request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=1)
    request['execution_settings'].update(slippage_ticks=0,commission_per_contract_per_side='0')
    results=[];reports=[]
    for mode in ('python','compiled'):
        monkeypatch.setenv('ALPHAQUEST_PROP_BACKEND',mode)
        response=client.post('/api/backtests',json=request);assert response.status_code==201,response.text
        record=response.json();id=record['run_metadata']['automatic_prop_analysis']['id']
        report=client.get('/api/prop-analyses/'+id+'/downloads/report.json').json()
        expected_cash(report);reports.append(report)
        assert report['runtime']['native_kernel']['name']==mode
        timing=client.get('/api/backtests/'+record['id']+'/performance').json()
        results.append(dict(mode=mode,run_id=record['id'],prop_id=id,performance=timing))
    assert reports[0]['calculations']==reports[1]['calculations']
    (tmp_path/'compiled-verification.json').write_text(json.dumps(dict(all_calculations_exact=True,standard_counts_preserved=True,expected_historical_net=352880,runs=results),indent=2))
