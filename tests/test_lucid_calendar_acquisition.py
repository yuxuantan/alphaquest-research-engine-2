"""Independent calendar/cash oracles for the saved-signal Lucid Evaluation owner."""
from alphaquest.prop.evaluation_profiles import calendar_evaluation_paths
from alphaquest.prop.evaluation_optimization import SequentialRetry
from alphaquest.prop.phase_profiles import EvaluationProfile,SimulationConfig,EvaluationSamplingConfig,rule_version
from alphaquest.prop.phase_search import PhaseCalendar


def run(days,*,dll=True,start='2026-11-13',closures=(),guard=15,attempts=10,enforce_inactivity=False):
    profile=EvaluationProfile('lucidflex-50k',rule_version('lucidflex-50k'),'80.50','0',dll,lucid_inactivity_enforced=enforce_inactivity)
    return calendar_evaluation_paths(days,profile,10,SimulationConfig(8,42,40),EvaluationSamplingConfig(5,8,42),
        SequentialRetry(activation_delay_sessions=0,max_calendar_days=guard,max_attempts=attempts),
        PhaseCalendar((start,),'2027-01-31',closures))[0]


def test_consistency_weekends_closures_and_zero_activation():
    # Three +1000 sessions: Friday, Monday, Tuesday. Next-session readiness Wednesday.
    for paths,days in [(run([[(1000.,0.)]]),5),(run([[(1000.,0.)]],closures=('2026-11-16',)),6)]:
        assert all(p['acquisition_completed'] and p['paid_fees']==80.5 and p['paid_activation_fees']==0 for p in paths)
        assert all(p['observed_calendar_days']==days and p['attempts_started']==1 for p in paths)
        assert all(p['attempts'][0]['sessions']==3 for p in paths)


def test_calendar_inactivity_and_guard_are_distinct():
    paths=run([[]],guard=40,attempts=1,enforce_inactivity=True)
    assert all(p['attempts'][0]['terminal_date']=='2026-12-13' and p['attempts'][0]['outcome']=='inactive' for p in paths)
    assert all(p['outcome']=='attempt_guard' and p['paid_fees']==80.5 and not p['acquisition_completed'] for p in paths)
    paths=run([[(100.,0.)]],guard=5)
    assert all(p['attempts'][0]['outcome']=='open' and p['censored'] and p['observed_calendar_days']==5 for p in paths)


def test_daily_loss_variant_and_paid_retry_cost():
    days=[[(-1500.,1500.),(2000.,0.)]]
    on=run(days,dll=True,start='2026-11-16',guard=15,attempts=2)
    assert all(p['attempts'][0]['outcome']=='blown' and p['attempts_started']==2 and p['paid_fees']==161 for p in on)
    off=run(days,dll=False,start='2026-11-16')
    assert all(p['acquisition_completed'] and p['paid_fees']==80.5 and p['attempts'][0]['sessions']==6 for p in off)


def test_calendar_guard_contract_rejects_ignored_weekday_limit():
    import pytest
    from alphaquest.prop.evaluation_optimization import EvaluationCandidate,EvaluationSearch
    from alphaquest.prop.phase_profiles import SavedTradeSource
    id='a'*32;profile=EvaluationProfile('lucidflex-50k',rule_version('lucidflex-50k'),'80.50','0')
    with pytest.raises(ValueError,match='computational horizon|weekday guard'):
        c=EvaluationCandidate(SavedTradeSource(id),profile,1,simulation=SimulationConfig(8,42,40),
            sampling=EvaluationSamplingConfig(5,8,42,computational_horizon_weekdays=10))
        EvaluationSearch(id,(c,),PhaseCalendar(('2026-11-16',),'2037-01-01'))
