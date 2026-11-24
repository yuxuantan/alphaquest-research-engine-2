"""Independent budget/outcome oracles for the explicit saved-stop model."""
from decimal import Decimal
import pytest
from alphaquest.prop.sizing import choose_quantity
from alphaquest.prop.phase_profiles import SizingConfiguration
from alphaquest.prop.saved_trade_simulation import MODEL


def configuration(percent='.5',reference='initial_configured_capital'):
    return SizingConfiguration(dict(kind='percentage_risk',risk_percent=percent,reference=reference,maximum_contracts=40),
        '50000',dict(tick_size='.25',commission_per_contract_per_side='.5'),MODEL)


def metadata():
    return dict(source_trade_id='1',side='long',entry_time_utc='2026-01-05T15:01:00Z',
        sizing_decision=dict(timestamp_utc='2026-01-05T15:00:00Z',reference_price='100',execution_timing='next_open'),
        initial_stop=dict(price='95',known_at_utc='2026-01-05T15:00:00Z',basis='submitted_order'),previous_source_exit_utc=None)


@pytest.mark.parametrize('floor,daily,reasons',[
    ('-2000','-1000',[]),('-125','-1000',['account']),('-2000','-125',['daily']),
    ('-250','-1000',['account']),('-2000','-250',['daily']),('-125','-125',['account','daily']),
    ('-2000',None,[])])
def test_requested_budget_must_fit_before_rounding_or_provider_cap(floor,daily,reasons):
    from alphaquest.prop.sizing_runtime import decision_risk_from_metadata
    c=configuration();s=dict(initial_configured_capital='50000',equity_change_from_initial='0',account_floor_from_initial=floor,
        daily_floor_from_initial=daily,provider_max_contracts=1,user_max_contracts=40)
    d=choose_quantity(c.policy,s,decision_risk_from_metadata(metadata()),c.planning_execution,reject_budget_at_floor=True)
    assert Decimal(d['risk_budget'])==250 and Decimal(d['planned_risk_per_mnq'])==11
    assert d['quantity']==(0 if reasons else 1)
    for reason in reasons:assert 'requested_budget_reaches_'+reason+'_limit' in d['reasons']


def test_size_uses_known_stop_and_costs_not_future_fill_or_mae():
    from alphaquest.prop.sizing_runtime import resolve_runtime,before_trade
    c=configuration();args=c.kernel_arguments();runtime=resolve_runtime(args['sizing_policy'],args['sizing_context'],None)
    # These are bounded outcomes from the source adapter. MAE never enters sizing.
    a=before_trade(runtime,(800.,0.,(),True,metadata()),0.,-2000.,-1000.,40,40,'evaluation',1,1)
    b=before_trade(runtime,(-110.,110.,(),True,metadata()),0.,-2000.,-1000.,40,40,'evaluation',1,1)
    assert a['quantity']==b['quantity']==22  # floor(250 / (5*2 + 2*.5))
    assert Decimal(a['decision']['planned_total_risk'])==242


@pytest.mark.parametrize('profile',['apex','lucid'])
def test_saved_admission_prevents_floor_hit_and_keeps_provider_rules(profile):
    from alphaquest.prop import native_engine,lucid_engine
    c=configuration();trace=[];args=c.kernel_arguments()
    trade=(-110.,110.,(),True,metadata()) # -$11 per MNQ, bounded planned stop loss
    kernel=native_engine if profile=='apex' else lucid_engine
    if profile=='apex':r=kernel.evaluation_session([trade]*8,0.,0.,40,**args,trace=trace.append)
    else:r=kernel.evaluation_session([trade]*8,0.,0.,0.,0,0,40,**args,trace=trace.append)
    assert all(d['account_hit']==0 for d in trace)
    assert trace[-1]['quantity']==0
    assert any('requested_budget_reaches_daily_limit' in d['reasons'] for d in trace)
    assert len(trace)==8


def test_missing_stop_or_future_stop_is_rejected():
    from alphaquest.prop.sizing_runtime import decision_risk_from_metadata
    m=metadata();m['initial_stop']=None
    with pytest.raises(ValueError,match='causal'):decision_risk_from_metadata(m)
    m=metadata();m['initial_stop']['known_at_utc']='2026-01-05T15:02:00Z'
    with pytest.raises(ValueError,match='known'):decision_risk_from_metadata(m)


def test_bounded_outcomes_ignore_mae_and_expose_every_clipped_loss(monkeypatch):
    from alphaquest.prop.saved_trade_simulation import adapt_saved_trades
    from native_replay_fixtures import parameter_values
    from copy import deepcopy
    snap=dict(backtest=dict(run_metadata=dict(strategy=dict(id='vwap_pullback_risk_sizing',parameters=parameter_values()))),
        commission_simulation=dict(per_side='.5',source_instrument='MNQ'))
    plan=metadata()
    monkeypatch.setattr('alphaquest.prop.saved_trade_simulation.causal_plans',lambda *args:({'1':plan},dict(method='SYNTHETIC unit fixture')))
    row=dict(trade_id=1,entry_utc=plan['entry_time_utc'],exit_utc='2026-01-05T15:05:00Z',simulation_net_per_nq='-900',measured_mae='999999999')
    outcomes=[]
    for mae in ('0','999999999'):
        s=deepcopy(snap);rows=[dict(row,measured_mae=mae)]
        adapt_saved_trades(None,s,rows,configuration())
        outcomes.append(rows[0]['simulation_net_per_nq'])
        assert s['saved_trade_simulation']['bounded_loss_count']==1
        assert not s['saved_trade_simulation']['mae_used']
    assert outcomes==['-110.00','-110.00']


def saved_source_pair(client):
    from unittest.mock import patch
    import test_percentage_automatic as fixture
    from native_replay_fixtures import source_bytes
    def compact(**kw):
        raw=source_bytes(**kw).decode().splitlines()
        return ('\n'.join([raw[0]]+[r for r in raw[1:] if '13:00'<=r.split(',')[1]<='15:05' or r.split(',')[1] in ('22:00','23:01')])+'\n').encode()
    import alphaquest.research_api as research
    original=research.run_oos_impl
    async def without_legacy(*a,**kw):return await original(*a,**dict(kw,automatic_prop=False))
    with patch.object(fixture,'source_bytes',compact),patch.object(research,'run_oos_impl',without_legacy):return fixture.native_source_pair(client)


@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_one_click_saved_percentage_is_oos_uses_no_native_paths(tmp_path,monkeypatch,profile):
    from alphaquest.app import create_app
    from research_fixtures import ResearchClient
    from test_percentage_automatic import install_admission_fixture,configuration
    from test_prop_sim_automatic import wait_automatic
    import json
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        source=saved_source_pair(client);install_admission_fixture(monkeypatch,source)
        def forbidden(*a,**kw):raise AssertionError('Retired native percentage route invoked')
        monkeypatch.setattr('alphaquest.prop.native_search.check_native_candidates',forbidden)
        monkeypatch.setattr('alphaquest.prop.native_preparation.prepared_forecast_outputs',forbidden)
        response=client.post('/api/prop-sim',json=configuration(source,profile))
        assert response.status_code==202,response.text
        saved=wait_automatic(client,response.json()['id'],timeout=180)
        assert all(p['stage']=='complete' for p in saved['automation']['phases'].values()),saved
        for phase in ('evaluation','funded'):
            state=saved['automation']['phases'][phase]
            campaign=client.app.state.campaigns.get(saved['campaign_ids'][phase])
            assert campaign['manifest']['request']['native_execution'] is None
            if profile=='lucidflex-50k':
                assert all(c['profile']['lucid_inactivity_enforced'] is False for c in campaign['manifest']['request']['candidates'])
                assert 'maintained-activity' in campaign['manifest']['request']['candidates'][0]['profile']['rule_version']
            is_report=client.get(f"/api/prop-sim/{saved['id']}/results/{phase}").json()
            assert all(r['simulation_model']['model']==MODEL and r['quantity_summary']['opportunities']>0 for r in is_report['calculations']['candidates'])
            report=client.get(f"/api/prop-sim/{saved['id']}/validation/{phase}/{state['oos_request_id']}").json()
            for row in report['calculations']['candidates']:
                assert row['configuration']['sizing']['execution_model']==MODEL
                assert row['simulation_model']['model']==MODEL
                assert row['quantity_summary']['decision_count']>0
                assert row['prop_qualification']['historical_replicates']==0
            (tmp_path/(phase+'-report.json')).write_text(json.dumps(report,indent=2))
            id=campaign['analysis_id']
            assert client.get('/api/prop-analyses/'+id+'/downloads/saved_trade_model.json').status_code==200
            # Exercise the actual complementary branch even though the short
            # product fixture correctly fails production history minima.
            from alphaquest.prop.phase_dispatch import module_for
            from alphaquest.prop.complementary_assessment import Runner
            from alphaquest.prop import native_engine,lucid_engine,native_backend,lucid_backend
            search=module_for(phase).parse_request(campaign['manifest']['request'])
            kernel=lucid_engine if profile=='lucidflex-50k' else native_engine
            original=kernel.before_trade;seen=[]
            def observed(runtime,*a,**kw):
                seen.append(runtime['strict_budget']);return original(runtime,*a,**kw)
            with monkeypatch.context() as m:
                m.setattr(kernel,'before_trade',observed)
                m.setattr(lucid_backend.module() if profile=='lucidflex-50k' else native_backend.module(),'before_trade',observed)
                runner=Runner(client.app.state.runs,client.app.state.store,search,lambda:None,lambda v:None)
                for options in ({},{'extra_cost':True},{'block':1},{'block':10}):
                    result=runner.run(search.candidates[0],8,9,**options)
                    assert len(result['paths'])==8
                assert seen and all(seen)
        if profile=='apex-50k-eod':
            # Old single-entry sources can be recovered without changing a report.
            from alphaquest.prop.source import prepare_source
            from alphaquest.prop.saved_trade_simulation import causal_plans
            snap,_=prepare_source(client.app.state.runs,source['source_backtest_id'],'')
            expected,_=causal_plans(client.app.state.runs,snap)
            snap['backtest'].pop('execution_decisions')
            actual,proof=causal_plans(client.app.state.runs,snap)
            assert proof['method']=='one_verified_source_replay'
            assert {k:v['initial_stop']['price'] for k,v in actual.items()}=={k:v['initial_stop']['price'] for k,v in expected.items()}
            from datetime import datetime
            assert all(datetime.fromisoformat(actual[k]['initial_stop']['known_at_utc'])==datetime.fromisoformat(v['initial_stop']['known_at_utc'].replace('Z','+00:00')) for k,v in expected.items())
            import alphaquest.prop.saved_trade_simulation as adapter
            adapter._cache.clear()
            def no_replay(*a,**kw):raise AssertionError('Verified causal plans should reuse the existing bounded replay cache')
            monkeypatch.setattr('alphaquest.execution.execute',no_replay)
            cached,again=causal_plans(client.app.state.runs,snap)
            assert cached==actual and again==proof
