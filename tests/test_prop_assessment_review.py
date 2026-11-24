"""Independent economic verdicts, cash funnels and covered-start boundaries."""
from datetime import date
import pytest
from alphaquest.prop.assessment_review import AssessmentLimits, distribution, review, start_plan, start_summary


def row(phase='evaluation'):
    return dict(status='estimated',manifest=dict(configuration=dict(
        period=dict(first_session='2025-01-01',last_session='2025-12-31'),
        profile=dict(profile_id='lucidflex-50k')),
        source=dict(backtest=dict(summary=dict(trades_taken=100)))),
        metrics=dict(cost_per_funded=200.,expected_calendar_days_to_funded=30.,
            expected_funded_cash_payouts_within_horizon=300.),
        is_comparison=dict(cost_per_funded=dict(is_value=100.,oos_value=200.),
            pass_probability=dict(is_value=.8,oos_value=.7)))


def policy(phase='evaluation',**overrides):
    limits=(dict(maximum_cost_per_funded='200',maximum_calendar_days_to_funded=30)
        if phase=='evaluation' else dict(minimum_funded_receipts='300'))
    limits.update(overrides)
    return dict(limits=AssessmentLimits(**limits).for_phase(phase).model_dump(),
        policy_sha256='independent-unit-oracle',declaration_timing='before_first_prop_oos_result')


def test_economic_limits_equality_warning_failure_and_inconclusive_are_distinct():
    r=row();p=policy()
    result=review(r,'evaluation',p,None)
    assert result['verdict']=='PASS' and result['watch']
    assert result['is_changes'][1]['percentage_points']==pytest.approx(-10)
    r['metrics']['cost_per_funded']=200.01
    assert review(r,'evaluation',p,None)['verdict']=='FAIL'
    r['status']='unresolved'
    assert review(r,'evaluation',p,None)['verdict']=='INCONCLUSIVE'
    r=row();r['manifest']['source']['backtest']['summary']['trades_taken']=29
    assert review(r,'evaluation',p,None)['verdict']=='INCONCLUSIVE'
    r=row('funded');p=policy('funded')
    assert review(r,'funded',p,90)['verdict']=='PASS'
    assert review(r,'funded',p,366)['verdict']=='INCONCLUSIVE'
    r['constraint_violations']=['breach_probability']
    assert review(r,'funded',p,90)['verdict']=='FAIL'


@pytest.mark.parametrize('bad',['NaN','Infinity','0','-1','1000000001'])
def test_nonpositive_or_nonfinite_limits_reject(bad):
    with pytest.raises(ValueError):AssessmentLimits(maximum_cost_per_funded=bad)


def test_phase_isolation_and_no_implicit_business_limits():
    with pytest.raises(ValueError):AssessmentLimits().for_phase('evaluation')
    with pytest.raises(ValueError):AssessmentLimits(minimum_funded_receipts='1',maximum_cost_per_funded='1').for_phase('funded')
    with pytest.raises(ValueError):AssessmentLimits(account_start_count=True)
    with pytest.raises(ValueError):AssessmentLimits().for_phase('unknown')


def test_cash_quantiles_include_zeros_and_pending_request_is_not_a_receipt():
    r=row('funded');r['paths']=[dict(cash_received=0,days_to_first_payout=None,payout_events=[]),
        dict(cash_received=100,days_to_first_payout=5,payout_events=[dict(trader_cash_received=100),dict(trader_cash_received=0)]),
        dict(cash_received=0,days_to_first_payout=None,payout_events=[dict(trader_cash_received=0)])]
    s=distribution(r,'funded')
    assert s['probability_zero_received_cash']==2/3
    assert s['cash_quantiles']==dict(p10=0,median=0,p90=100)
    assert s['payout_milestones'][0]==dict(payout=1,probability_requested=2/3,probability_received=1/3)
    assert s['payout_milestones'][1]==dict(payout=2,probability_requested=1/3,probability_received=0)
    assert len(s['payout_milestones'])==5
    assert s['first_receipt_observations']==1
    assert s['first_receipt_calendar_days_conditional_on_receipt']==dict(median=5,p75=5,p90=5)


def test_evaluation_quantile_and_start_ranges_do_not_drop_censored_paths():
    r=row();r['paths']=[dict(calendar_days_to_funded=2),dict(calendar_days_to_funded=None)]
    assert distribution(r,'evaluation')['p90_calendar_days'] is None
    paths=[dict(result=dict(acquisition_completed=True,censored=False,paid_fees=80,calendar_days_to_funded=2)),
        dict(result=dict(acquisition_completed=False,censored=True,paid_fees=160,calendar_days_to_funded=None))]
    s=start_summary(paths,'evaluation')
    assert s['funded']==1 and s['window_censored']==1
    assert s['calendar_days_to_funded'] is None
    assert s['paid_fees']==dict(minimum=80,median=120,maximum=160)


def test_starts_are_evenly_spaced_covered_weekdays_not_outcome_dependent():
    period=dict(first_session='2026-01-01',last_session='2026-01-30')
    plan=start_plan(period,10,3,('2026-01-01',))
    assert plan['starts']==['2026-01-02','2026-01-12','2026-01-21']
    for start in plan['starts']:
        assert (date.fromisoformat(period['last_session'])-date.fromisoformat(start)).days>=9
    assert start_plan(period,31,3)['status']=='insufficient_coverage'
    s=start_summary([dict(result=dict(cash_received=0,pending_cash=50,outcome='blown')),
        dict(result=dict(cash_received=200,pending_cash=0,outcome='open'))],'funded')
    assert s['cash_received']==dict(minimum=0,median=100,maximum=200)
    assert s['zero_receipt_starts']==1 and s['outcomes']==dict(blown=1,open=1)
