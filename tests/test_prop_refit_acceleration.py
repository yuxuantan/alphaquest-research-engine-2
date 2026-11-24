"""Exact compact/full refits, immutable preparation and durable retry checkpoints."""
from dataclasses import replace
from hashlib import sha256
import json

import numpy as np
import pytest

from alphaquest.prop.evaluation_profiles import calendar_evaluation_paths,DatedEvaluationPreparation
from alphaquest.prop.funded_profiles import _dated_funded_paths,DatedFundedPreparation
from alphaquest.prop.oos_qualification import _means,historical_ratios
from alphaquest.prop.phase_profiles import EvaluationProfile,FundedProfile,rule_version
from alphaquest.prop.phase_search import PhaseCalendar
from alphaquest.prop.store import AnalysisStore
from test_prop_oos_qualification import fixed_search


def configurations(profile,phase):
    search=fixed_search(phase);c=search.candidates[0]
    p=(EvaluationProfile(profile,rule_version(profile),'49','129' if profile=='apex-50k-eod' else '0') if phase=='evaluation'
       else FundedProfile(profile,rule_version(profile)))
    c=replace(c,profile=p);return replace(search,candidates=(c,)),c


@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
@pytest.mark.parametrize('phase',['evaluation','funded'])
@pytest.mark.parametrize('backend',['python','compiled'])
def test_compact_means_and_precision_exactly_match_full_capture(profile,phase,backend,monkeypatch):
    from alphaquest.prop import native_backend,lucid_backend
    if backend=='compiled' and (native_backend.compiled is None or lucid_backend.compiled is None):pytest.skip('Matching optional compiled kernels not installed')
    monkeypatch.setenv('ALPHAQUEST_PROP_BACKEND',backend)
    search,c=configurations(profile,phase)
    search=replace(search,calendar=PhaseCalendar(('2026-11-13','2026-11-14'),'2037-01-01',('2026-11-26',)))
    days=([[(1600.,80.)],[],[(-400.,600.)],[(900.,100.)],[(1700.,0.)]]*8)
    if phase=='funded':
        full,_,_=_dated_funded_paths(days,c.profile,c.micros,search.horizon_calendar_days,search.calendar,search.receipt_delay_calendar_days,c.simulation,c.sampling)
        cash=np.asarray([p['cash_received'] for p in full]);mean=float(cash.mean())
        groups=[cash[[p['start_date']==s for p in full]] for s in search.calendar.start_dates]
        error=float(np.sqrt(sum(np.var(g,ddof=1)/len(g) for g in groups))/len(groups))/mean if mean>0 else None
        expected={'expected_funded_cash_payouts_within_horizon':mean}
    elif profile=='lucidflex-50k':
        full,_=calendar_evaluation_paths(days,c.profile,c.micros,c.simulation,c.sampling,c.retry,search.calendar)
        assert all(p['acquisition_completed'] for p in full)
        arrays={'cost_per_funded':[p['paid_fees'] for p in full],'expected_calendar_days_to_funded':[p['calendar_days_to_funded'] for p in full]}
        expected={k:float(np.mean(v)) for k,v in arrays.items()}
        error=max(float(np.std(v,ddof=1)/np.sqrt(len(v)))/expected[k] for k,v in arrays.items())
    else:
        from alphaquest.prop.native_analysis import evaluation_model
        from alphaquest.prop.phase_profiles import profile_settings
        from alphaquest.prop.evaluation_optimization import acquisition_metrics
        from types import SimpleNamespace
        raw=evaluation_model(days,c.micros,c.simulation.simulations,c.simulation.seed,c.sampling.block_weekdays,profile_settings(c.profile,c.costs),max_micros=c.simulation.max_micros)
        component=SimpleNamespace(outcomes=list(map(str,raw['outcomes'])),duration_weekdays=list(map(int,raw['days'])),censoring=SimpleNamespace(censored_paths=0))
        full=acquisition_metrics(component,c.profile,c.retry,search.calendar,c.sampling)
        expected={k:full['metrics'][k] for k in ('cost_per_funded','expected_calendar_days_to_funded')}
        error=max(full['uncertainty'][se]/expected[k] for k,se in zip(expected,('cost_se','calendar_mean_se')))
    for budget in (0,32*1024*1024):
        ev=DatedEvaluationPreparation(budget);fd=DatedFundedPreparation(budget)
        for _ in range(2):
            assert _means(days,c,search,lambda:None,evaluation_preparation=ev,funded_preparation=fd)==(expected,error)
        assert ev.bytes_used<=budget and fd.bytes_used<=budget


def test_renewal_prefix_keeps_exact_scalar_stream_past_prefix_and_with_zero_budget():
    for budget in (0,32*1024*1024):
        cache=DatedEvaluationPreparation(budget)
        for limit in (5,64,140):
            for _ in range(2):
                rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([42,7])))
                expected=[int(rng.integers(23)) for _ in range(limit)]
                assert list(cache.renewal_indices(42,7,23,limit))==expected


def test_evaluation_prefix_restores_partial_and_long_block_streams_without_clipping():
    from alphaquest.prop.native_engine import sampled_days
    for budget in (0,600,32*1024*1024):
        cache=DatedEvaluationPreparation(budget)
        for block in (1,5,10):
            for _ in range(2):
                rng=np.random.RandomState(np.random.SeedSequence([42,7,3]).generate_state(1)[0])
                stream=sampled_days(rng,23,block)
                expected=[next(stream) for _ in range(800)]
                actual=cache.evaluation_indices(42,7,23,block,800,3)
                assert [next(actual) for _ in range(800)]==expected
                assert cache.bytes_used<=budget


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_checkpoint_resume_runs_only_missing_refits_with_same_order_and_results(phase,monkeypatch,tmp_path):
    from alphaquest.prop import oos_bootstrap,oos_qualification
    monkeypatch.setitem(oos_qualification.RULES,'historical_replicates',12)
    store=AnalysisStore(tmp_path);search=fixed_search(phase);c=search.candidates[0]
    days=[[(1500.,0.)]]*30;updates=[]
    def insert(id):
        with store.connect() as db:db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(id,id,'a'*32,'2026-11-14','error','Interrupted',None))
    insert('first');insert('retry')
    original=oos_bootstrap._replicate;calls=[]
    class Stop(Exception):pass
    def stop_after(task):
        calls.append(task[2])
        if task[2]==5:raise Stop()
        return original(task)
    monkeypatch.setattr(oos_bootstrap,'_replicate',stop_after)
    try:
        with pytest.raises(Stop):historical_ratios(days,days,c,c,search,lambda:None,updates.append,resume=(store,'first'))
        with store.connect() as db:assert db.execute('SELECT count(*) FROM historical_refit_checkpoints').fetchone()[0]==5
        monkeypatch.setattr(oos_bootstrap,'_replicate',lambda task:(calls.append(task[2]),original(task))[1]);calls.clear()
        actual=historical_ratios(days,days,c,c,search,lambda:None,updates.append,resume=(store,'retry'))
        assert calls==list(range(5,12)) and actual['execution']['reused_resamples']==5
        expected=historical_ratios(days,days,c,c,search,lambda:None,lambda value:None)
        for key in ('replicates','inner_precision_ok','outer_block_weekdays','unique_histories_evaluated'):assert actual[key]==expected[key]
        assert updates[-1]['reused_resamples']==5 and updates[-1]['completed']==12
        # A substantive declaration change cannot reuse the old completed rows.
        calls.clear();changed=replace(c,simulation=replace(c.simulation,seed=43),**({'sampling':replace(c.sampling,chain_seed=43)} if phase=='evaluation' else {}))
        again=historical_ratios(days,days,changed,changed,replace(search,candidates=(changed,)),lambda:None,lambda value:None,resume=(store,'retry'))
        assert again['execution']['reused_resamples']==0 and calls==list(range(12))
        key=actual['execution']['checkpoint_context_sha256']
        with store.connect() as db:db.execute("UPDATE historical_refit_checkpoints SET payload='{}' WHERE context_key=? AND replicate=0",(key,))
        with pytest.raises(ValueError,match='checksum'):store.load_refits(key,12)
        with store.connect() as db:
            store.remove_catalogue_record(db,'first');store.remove_catalogue_record(db,'retry')
            assert db.execute('SELECT count(*) FROM historical_refit_checkpoints').fetchone()[0]==0
    finally:store.close()


@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_compact_unresolved_and_zero_cash_paths_do_not_become_qualifying_means(profile):
    search,c=configurations(profile,'evaluation')
    c=replace(c,retry=replace(c.retry,max_calendar_days=40,max_attempts=1))
    search=replace(search,candidates=(c,))
    assert _means([[]]*40,c,search,lambda:None)==({},None)
    search,c=configurations(profile,'funded')
    assert _means([[]]*40,c,search,lambda:None)==({'expected_funded_cash_payouts_within_horizon':0.},None)
