"""New maintained-activity model, with explicit historical enforcement checks."""
from dataclasses import replace
from datetime import date,timedelta
import pytest
from alphaquest.prop import lucid_engine,lucid_backend
from alphaquest.prop.phase_profiles import (EvaluationProfile,FundedProfile,SimulationConfig,
    EvaluationSamplingConfig,SamplingConfig,rule_version,profile_settings,SourceCosts)
from alphaquest.prop.evaluation_profiles import calendar_evaluation_paths
from alphaquest.prop.funded_profiles import _dated_funded_paths
from alphaquest.prop.evaluation_optimization import SequentialRetry
from alphaquest.prop.phase_search import PhaseCalendar


@pytest.mark.parametrize('mode',['python','compiled'])
def test_no_synthetic_trades_costs_profit_or_winning_days(mode,monkeypatch):
    monkeypatch.setenv('ALPHAQUEST_PROP_BACKEND',mode)
    kernel=lucid_backend.module()
    account=kernel.FundedAccount()
    for day in range(100):
        if date(2026,1,5).__add__(timedelta(days=day)).weekday()<5:account.advance([],1,calendar_day=day)
        else:assert not account.expire_inactive(day)
    assert account.outcome=='open' and account.equity==0
    assert account.qualifying==0 and account.payouts==account.withdrawals==[]
    assert account.last_activity==0 and account.trades_consumed==0
    historical=kernel.FundedAccount(rules=kernel.Rules(inactivity_enforced=True))
    assert historical.expire_inactive(30) and historical.outcome=='inactive'
    result=kernel.evaluation_session([],0.,0.,0.,0,100,1)
    assert result==(0.,0.,0.,0,'open',0,0)
    assert kernel.evaluation_session([],0.,0.,0.,0,100,1,inactivity_enforced=True)[4]=='inactive'
    sim=kernel.evaluation([[]],1,8,42,deadline=60)
    assert sim['outcomes'].tolist()==['timeout']*8
    assert sim['days'].tolist()==[60]*8 and sim['attempts'].tolist()==[1]*8


def test_dated_evaluation_keeps_open_attempt_and_only_real_purchase_fees():
    profile=EvaluationProfile('lucidflex-50k',rule_version('lucidflex-50k'),'80.50','0')
    args=dict(days=[[]],profile=profile,micros=1,simulation=SimulationConfig(8,42,40),
        sampling=EvaluationSamplingConfig(5,8,42),retry=SequentialRetry(max_calendar_days=65),
        calendar=PhaseCalendar(('2026-01-05',),'2027-01-01'))
    rows,_=calendar_evaluation_paths(**args)
    assert all(p['outcome']=='calendar_guard' and p['censored'] and p['observed_calendar_days']==65 for p in rows)
    assert all(p['attempts_started']==1 and p['paid_fees']==80.5 and p['attempts'][0]['equity']==0 for p in rows)
    assert all(p['attempts'][0]['outcome']=='open' for p in rows)
    legacy,_=calendar_evaluation_paths(**dict(args,profile=replace(profile,lucid_inactivity_enforced=True)))
    assert all(p['attempts_started']>1 and p['paid_fees']>80.5 for p in legacy)


@pytest.mark.parametrize('enforced',[False,True])
def test_dated_funded_inactivity_follows_frozen_profile(enforced):
    profile=FundedProfile('lucidflex-50k',rule_version('lucidflex-50k'),lucid_inactivity_enforced=enforced)
    rows,_,rules=_dated_funded_paths([[]],profile,1,90,PhaseCalendar(('2026-01-05',),'2027-01-01'),2,
        SimulationConfig(8,42,40),SamplingConfig(5))
    assert rules.inactivity_enforced is enforced
    assert all(p['outcome']==('inactive' if enforced else 'open') for p in rows)
    assert all(p['equity']==0 and p['cash_received']==0 and not p['payout_events'] for p in rows)
    if not enforced:assert all(p['observed_calendar_days']==90 and p['lifetime_censored'] for p in rows)


def test_profile_version_rules_and_admission_are_explicit():
    from alphaquest.prop_sim import account_defaults
    from alphaquest.prop.lucid_rules import ACTIVITY_ASSUMPTION
    defaults=account_defaults('lucidflex-50k')
    assert defaults['evaluation_rules']['inactivity_calendar_days'] is None
    assert defaults['funded_rules']['inactivity_calendar_days'] is None
    assert defaults['funded_rules']['inactivity_enforced'] is False
    assert defaults['activity_assumption']==ACTIVITY_ASSUMPTION
    assert 'maintained-activity' in defaults['rule_version']
    assert 'small commissions are omitted' in defaults['notes']
    p=FundedProfile('lucidflex-50k','alphaquest-lucidflex50k-eod-v4-acquisition-bounds')
    with pytest.raises(ValueError,match='historical rules are not silently upgraded'):profile_settings(p,SourceCosts())
    with pytest.raises(ValueError,match='must be boolean'):
        profile_settings(replace(p,rule_version=rule_version('lucidflex-50k'),lucid_inactivity_enforced='false'),SourceCosts())
    apex=account_defaults('apex-50k-eod')
    assert apex['evaluation_rules']['expiry_weekdays']==21
    assert apex['funded_rules']['inactivity_window']==21
