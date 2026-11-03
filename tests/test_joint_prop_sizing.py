"""Independent pair economics, truncation bounds and training-only selection."""
from decimal import Decimal

import pytest

from alphaquest.prop.joint_sizing import rank, score_pair, pass_probability_upper, acquisition_bound


def evaluation(size, probability, days, price=80):
    return dict(evaluation_micros=size,pass_rate=probability,passed=int(probability*3000),
        simulations=3000,cost_per_funded=price/probability,replacement_days=days,
        status='calibrated',cost_se=0.,replacement_days_se=0.)


def funded(size, receipts, days, censored=0, upper=None):
    return dict(micros=size,sims=3000,**{'E[payout]':receipts,'days alive':days,'SE':0.},
        censored_paths=censored,receipts_upper_bound=receipts if upper is None else upper,
        lifetime_se=0.,receipts_lifetime_covariance=0.)


def test_joint_winner_differs_from_highest_pass_fastest_funding_and_largest_payout():
    evaluations=[evaluation(1,1.,100),evaluation(2,.5,20),evaluation(3,.2,10)]
    profiles=[funded(1,1000,20),funded(2,3000,200)]
    rows,best,blocked=rank(evaluations,profiles)
    assert len(rows)==6 and not blocked
    for row in rows:
        e=evaluations[row['evaluation_micros']-1];f=profiles[row['funded_micros']-1]
        expected=Decimal(261)*(Decimal(f['E[payout]'])-Decimal(80)/Decimal(str(e['pass_rate'])))/(Decimal(f['days alive'])+Decimal(e['replacement_days']))
        assert row['slot_year']==float(expected)
    assert (best['evaluation_micros'],best['funded_micros'],best['slot_year'])==(2,1,5481.)
    assert max(evaluations,key=lambda e:e['pass_rate'])['evaluation_micros']==1
    assert min(evaluations,key=lambda e:e['replacement_days'])['evaluation_micros']==3
    assert max(profiles,key=lambda f:f['E[payout]'])['micros']==2


def test_negative_scores_remain_negative_and_exact_ties_choose_smaller_exposure():
    _,best,blocked=rank([evaluation(2,1,10),evaluation(1,1,10)],[funded(2,0,20),funded(1,0,20)])
    assert best['slot_year']==-696 and not blocked
    assert (best['evaluation_micros'],best['funded_micros'])==(1,1)


def test_censored_lifetimes_are_bounded_not_assumed_closed_or_silently_dropped():
    rows,best,blocked=rank([evaluation(1,1,10)],[funded(1,1000,20),funded(2,0,20000,1,9000)])
    assert best['funded_micros']==1 and not blocked # Maximum unresolved return is provably lower.
    assert rows[1]['slot_year'] is None and rows[1]['upper_bound']==pytest.approx(261*8920/20010)
    _,_,blocked=rank([evaluation(1,1,10)],[funded(1,100,200),funded(2,0,20,1,9000)])
    assert blocked # An unresolved candidate could win.
    row=score_pair(evaluation(1,1,10),funded(1,0,20000,1,0))
    assert row['upper_bound']==0 and row['slot_year'] is None # Negative numerator can approach zero over an unknown lifetime.


def test_unresolved_acquisition_cannot_be_discarded_to_claim_an_optimum():
    e=dict(evaluation(2,.5,10),status='unavailable',reason='censored',replacement_days=None)
    rows,best,blocked=rank([evaluation(1,1,10),e],[funded(1,1000,20)])
    assert blocked and best is not None
    assert rows[1]['slot_year'] is None and rows[1]['reason']=='censored'


def rare_evaluation(passed=2, simulations=3000):
    return dict(evaluation(3,passed/simulations,10,price=49),passed=passed,simulations=simulations,
        screening_passed=passed,status='unavailable',reason='10,000 funding attempts without a pass',
        replacement_days=None,evaluation_price=49.,activation_fee=129.,activation_days=1,
        evaluation_censored_paths=0)


def test_actual_trial_four_economic_bounds_remove_the_blanket_veto():
    # Immutable saved trial-4 expected values; these are qualification oracles
    # in tests, never production calculation inputs.
    complete=dict(evaluation(40,.2689,24.47735,price=49),activation_fee=129.)
    complete['cost_per_funded']=49/.2689+129
    rows,best,blocked=rank([rare_evaluation(),complete],[funded(8,856.075,45.70835)],payout_cap=13000.)
    expected=Decimal(261)*(Decimal('856.075')-(Decimal(49)/Decimal('.2689')+Decimal(129)))/(Decimal('45.70835')+Decimal('24.47735'))
    assert not blocked and (best['evaluation_micros'],best['funded_micros'])==(40,8)
    assert best['slot_year']==pytest.approx(float(expected))
    excluded=rows[0]
    assert excluded['status']=='excluded' and excluded['upper_bound']==0
    assert excluded['acquisition_cost_lower_bound']>13000
    assert excluded['acquisition_days'] is None and excluded['slot_year'] is None
    assert excluded['calibration_reason']=='10,000 funding attempts without a pass'


def test_optimistic_acquisition_bound_cannot_hide_a_negative_or_zero_competitor():
    for receipts in (0,80):
        _,best,blocked=rank([rare_evaluation(),evaluation(1,1,10)],
            [funded(8,receipts,20)],payout_cap=13000.)
        assert best['slot_year']<=0 and blocked


def test_unresolved_candidate_with_affordable_cost_stays_ambiguous():
    e=rare_evaluation(300)
    rows,_,blocked=rank([e,evaluation(1,1,10)],[funded(8,1000,20)],payout_cap=13000.)
    assert blocked and rows[0]['status']=='bounded_acquisition' and rows[0]['upper_bound']>0


def test_censored_evaluations_are_possible_passes_and_zero_refined_passes_keep_the_bound():
    e=dict(rare_evaluation(),passed=0,simulations=20000)
    rows,_,blocked=rank([e,evaluation(1,1,10)],[funded(8,1000,20)],payout_cap=13000.)
    assert not blocked and rows[0]['status']=='excluded'
    e.update(evaluation_censored_paths=20000)
    assert acquisition_bound(e,2)['pass_probability_upper']==1
    rows,_,blocked=rank([e,evaluation(1,1,10)],[funded(8,1000,20)],payout_cap=13000.)
    assert blocked and rows[0]['status']=='bounded_acquisition'


def test_exact_binomial_bound_matches_independent_closed_forms_and_probability_sum():
    import math
    # Zero successes: (1-p)^n = alpha. All but one: 1-p^n = alpha.
    assert pass_probability_upper(0,20000,40)==pytest.approx(1-(.05/40)**(1/20000),abs=1e-15)
    assert pass_probability_upper(9,10,2)==pytest.approx((1-.05/2)**(1/10),abs=1e-14)
    assert pass_probability_upper(10,10,2)==1
    p=Decimal(str(pass_probability_upper(2,3000,40)))
    cdf=sum(Decimal(math.comb(3000,k))*p**k*(1-p)**(3000-k) for k in range(3))
    assert float(cdf)==pytest.approx(.05/40,rel=1e-9)
    assert pass_probability_upper(2,3000,40)>pass_probability_upper(2,3000,1)


def test_rare_pass_refinement_keeps_failed_timing_unknown_and_never_retries_chain(monkeypatch):
    import numpy as np
    from alphaquest.prop import native_analysis as model
    from alphaquest.prop.joint_sizing import _refine_evaluation
    previous=rare_evaluation()
    def simulate(days,size,count,seed,block,settings,**kwargs):
        assert count==20000 and seed==46 and not kwargs.get('chain')
        return dict(outcomes=np.array(['blown']*20000),days=np.ones(20000))
    monkeypatch.setattr(model,'evaluation_model',simulate)
    result=_refine_evaluation(([[(-1.,1.)]],previous,model.resolved_settings({}),5,40,['a','b']))
    assert result['passed']==0 and result['screening_passed']==2
    assert result['replacement_days'] is None and result['funding_chain_simulations']==0
    assert result['funding_chain_failure_reason']=='10,000 funding attempts without a pass'
    assert acquisition_bound(result,40)['acquisition_cost_lower_bound']>13000


def test_uncertainty_accounts_for_acquisition_cost_time_and_funded_covariance():
    e=dict(evaluation(1,.5,20),cost_se=5.,replacement_days_se=2.)
    f=dict(funded(1,1000,30),SE=10.,lifetime_se=3.,receipts_lifetime_covariance=4.)
    row=score_pair(e,f)
    denominator=Decimal(50);net=Decimal(840)
    variance=(Decimal(261)/denominator)**2*125+(Decimal(261)*net/denominator**2)**2*13-2*Decimal(261)**2*net/denominator**3*4
    assert row['slot_year_se']==pytest.approx(float(variance.sqrt()))


def test_analytical_zero_receipt_bound_has_no_invented_lifetime_or_simulation_count():
    from alphaquest.prop.native_analysis import _funded_profile
    from alphaquest.prop.lucid_backend import Rules
    # Even skipping -$1000 losses cannot make more than $149 at one MNQ.
    profile=_funded_profile(([[(1490.,0.),(-10000.,10000.)]],1,5,Rules(),40,3000,42))
    assert profile['method']=='analytical_zero_payout_bound'
    assert profile['sims']==0 and profile['requested_simulations']==3000
    assert profile['days alive'] is None and profile['receipts_upper_bound']==0
    row=score_pair(evaluation(1,1,10),profile)
    assert row['slot_year'] is None and row['upper_bound']==0
    # Exactly $150 is not excluded by the strict bound. Subsequent losses can
    # still blow the account; those outcomes must actually be simulated.
    boundary=_funded_profile(([[(1500.,0.),(-100000.,100000.)]],1,5,Rules(),40,3000,42))
    assert boundary['method']=='monte_carlo' and boundary['sims']==3000
    assert boundary['lifetime_complete'] and boundary['E[payout]']==0


def test_csv_preserves_different_analytical_and_sampled_profile_fields():
    import csv,io
    from alphaquest.prop.native_analysis import csv_text
    rows=list(csv.DictReader(io.StringIO(csv_text([dict(micros=1,method='analytical_zero_payout_bound',sims=0),
        dict(micros=2,method='monte_carlo',sims=3000,censored_paths=0)]))))
    assert rows[0]['sims']=='0' and rows[0]['censored_paths']==''
    assert rows[1]['censored_paths']=='0'
