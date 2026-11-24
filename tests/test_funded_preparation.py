"""Exact dated-path parity, independent schedules and bounded worker preparation."""
from dataclasses import replace
from datetime import date,timedelta

import numpy as np
import pytest

from alphaquest.prop.funded_profiles import DatedFundedPreparation,_dated_funded_paths
from alphaquest.prop.phase_profiles import FundedProfile,SimulationConfig,SamplingConfig,rule_version
from alphaquest.prop.phase_search import PhaseCalendar


def config(profile='apex-50k-eod',*,starts=('2026-11-13','2026-11-14'),closures=('2026-11-26',)):
    return (FundedProfile(profile,rule_version(profile)),SimulationConfig(16,42,40),
            SamplingConfig(5),PhaseCalendar(starts,'2037-01-01',closures))


def run(days,profile,simulation,sampling,calendar,preparation,*,horizon=90,delay=2,chronological=False,checkpoint=lambda:None):
    return _dated_funded_paths(days,profile,10,horizon,calendar,delay,simulation,sampling,
        chronological=chronological,checkpoint=checkpoint,preparation=preparation)


def test_index_prefix_matches_independent_scalar_mt19937_and_reuses_readonly_values():
    preparation=DatedFundedPreparation()
    for seed,path,length,block,count in ((42,0,23,5,70),(43,7,19,10,9),(42,1,11,1,0)):
        rng=np.random.RandomState(np.random.SeedSequence([seed,path]).generate_state(1)[0])
        expected=[]
        while len(expected)<count:
            first=int(rng.randint(length))
            expected.extend((first+i)%length for i in range(block))
        assert list(preparation.indices(seed,path,length,block,count))==expected[:count]
        before=preparation.bytes_used
        assert list(preparation.indices(seed,path,length,block,count))==expected[:count]
        assert preparation.bytes_used==before
    buffers=[v for v in preparation._entries.values() if isinstance(v,bytes)]
    assert buffers and all(memoryview(v).readonly and memoryview(v).cast('i').itemsize==4 for v in buffers)
    assert all(type(i) is int for i in preparation.indices(42,0,23,5,70))


def test_budget_fallback_retains_full_stream_and_admitted_prefix_without_thrashing():
    preparation=DatedFundedPreparation(max_bytes=600)
    admitted=list(preparation.indices(42,0,17,5,8));before=preparation.bytes_used
    assert before<=600
    # New declarations cannot evict the retained prefix or truncate the stream.
    streamed=list(next_stream for _,next_stream in zip(range(100),preparation.indices(42,1,17,5,10000)))
    zero=DatedFundedPreparation(0)
    assert streamed==list(next_stream for _,next_stream in zip(range(100),zero.indices(42,1,17,5,10000)))
    assert list(preparation.indices(42,0,17,5,8))==admitted
    assert preparation.bytes_used==before and zero.bytes_used==0
    assert preparation.calendar(('v','America/Chicago','2037-01-01',('2026-11-13',),()),'2026-11-13',3650,lambda:None) is None
    assert preparation.bytes_used<=preparation.max_bytes
    with pytest.raises(ValueError):DatedFundedPreparation(DatedFundedPreparation.MAX_BYTES+1)


def test_calendar_key_captures_closures_and_version_with_independent_weekend_oracle():
    preparation=DatedFundedPreparation()
    base=('v1','America/Chicago','2037-01-01',('2026-11-13',),())
    left,count=preparation.calendar(base,'2026-11-13',5,lambda:None)
    expected=[date(2026,11,13)+timedelta(days=i) for i in range(5)]
    assert [row[0] for row in left]==expected
    assert [row[1] for row in left]==[True,False,False,True,True] and count==3
    changed=(*base[:4],('2026-11-16',))
    right,other_count=preparation.calendar(changed,'2026-11-13',5,lambda:None)
    assert [r[1] for r in right]==[True,False,False,False,True] and other_count==2
    before=preparation.bytes_used
    assert preparation.calendar(base,'2026-11-13',5,lambda:None)==(left,count)
    assert preparation.bytes_used==before
    preparation.calendar(('v2',*base[1:]),'2026-11-13',5,lambda:None)
    assert preparation.bytes_used>before


@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
@pytest.mark.parametrize('budget',[0,600,32*1024*1024])
def test_all_path_events_and_schedule_hashes_match_streaming_on_cold_warm_and_changed_books(profile,budget):
    p,sim,sampling,calendar=config(profile)
    preparation=DatedFundedPreparation(budget)
    books=[([[(1600.,80.)],[],[(-400.,600.)],[(900.,100.)],[(1700.,0.)]]*8),
           ([[(1200.,0.)],[(-2200.,2600.)],[],[(1700.,100.)]]*7)]
    for days in (books[0],books[0],books[1]):
        expected=run(days,p,sim,sampling,calendar,DatedFundedPreparation(0))
        assert run(days,p,sim,sampling,calendar,preparation)==expected
        assert len(expected[0])==sim.simulations
        assert preparation.bytes_used<=budget


@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_zero_trade_closed_dates_and_pending_receipt_cutoff_have_independent_outcomes(profile):
    p,sim,sampling,calendar=config(profile,starts=('2026-11-16',),closures=())
    cache=DatedFundedPreparation()
    # Five $1,600 profitable sessions qualify a full first payout. A 100-day
    # lag puts all receipts outside this ten-day horizon, retaining deductions.
    days=[[(1600.,0.)]]*20
    paths,_,_=run(days,p,sim,sampling,calendar,cache,horizon=10,delay=100)
    assert all(row['cash_received']==0 and row['pending_cash']>0 and row['gross_account_deductions']>0 for row in paths)
    assert all(not event['received_within_horizon'] for row in paths for event in row['payout_events'])
    assert run(days,p,sim,sampling,calendar,cache,horizon=10,delay=100)==run(days,p,sim,sampling,calendar,DatedFundedPreparation(0),horizon=10,delay=100)
    empty,_,_=run([[]]*40,p,sim,sampling,calendar,cache,horizon=90)
    assert all(row['cash_received']==row['pending_cash']==0 and row['outcome']=='inactive' for row in empty)
    assert run([[]]*40,p,sim,sampling,calendar,cache,horizon=90)==run([[]]*40,p,sim,sampling,calendar,DatedFundedPreparation(0),horizon=90)


def test_chronological_paths_never_use_prepared_random_indices_and_respect_coverage(monkeypatch):
    p,sim,sampling,calendar=config(starts=('2026-11-16',),closures=())
    cache=DatedFundedPreparation()
    monkeypatch.setattr(cache,'indices',lambda *a:pytest.fail('Chronological replay sampled random source indices'))
    days=[[(1600.,0.)]]*80
    assert run(days,p,sim,sampling,calendar,cache,chronological=True)==run(days,p,sim,sampling,calendar,DatedFundedPreparation(0),chronological=True)
    with pytest.raises(ValueError,match='does not cover'):
        run([[]],p,sim,sampling,calendar,cache,chronological=True)


def test_stop_is_checked_while_preparing_calendar_and_during_warm_account_paths():
    p,sim,sampling,calendar=config(starts=('2026-11-16',),closures=())
    class Stop(Exception):pass
    calls=0
    def stop():
        nonlocal calls
        calls+=1
        if calls==2:raise Stop()
    with pytest.raises(Stop):run([[]]*40,p,sim,sampling,calendar,DatedFundedPreparation(),horizon=3650,checkpoint=stop)
    cache=DatedFundedPreparation()
    run([[]]*40,p,sim,sampling,calendar,cache)
    calls=0
    with pytest.raises(Stop):run([[]]*40,p,sim,sampling,calendar,cache,checkpoint=stop)


def test_preparation_implementation_is_part_of_frozen_funded_identity():
    from alphaquest.prop.funded_optimization import implementation_identity
    from alphaquest.prop.phase_dispatch import implementations_compatible
    current=implementation_identity()
    previous=dict(current,files=dict(current['files'],**{'funded_profiles.py':'previous numerical owner'}))
    assert 'funded_profiles.py' in current['files']
    assert not implementations_compatible(previous,current)
