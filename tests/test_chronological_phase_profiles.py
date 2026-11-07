"""Independent actual-date retry/cash oracles using the existing account kernels.

Admission is replaced only in these numerical unit tests; full artifact/freeze
checks run in normal-product robust economic API tests.
"""
from datetime import date,timedelta
from decimal import Decimal
import pytest
from alphaquest.prop.phase_search import PhaseCalendar
from alphaquest.prop.phase_profiles import EvaluationProfile,FundedProfile,SizingConfiguration,rule_version
from alphaquest.prop.evaluation_optimization import SequentialRetry
from types import SimpleNamespace
from alphaquest.prop.phase_profiles import ReplayWindow, ResearchPeriod, observed_session_grid
from alphaquest.prop import phase_profiles, evaluation_profiles, funded_profiles
from alphaquest.prop.cash_ledger import dated_settlement


# Unit fixtures supply an admitted source book; immutable normal-product source
# admission is exercised separately through the robust economic API tests.
@pytest.fixture(autouse=True)
def admitted_book(monkeypatch):
    def prepare(*args, **kwargs):
        return {'unit_fixture': True}, CURRENT_BOOK.copy(), {}
    monkeypatch.setattr(phase_profiles,'prepare_chronological_source',prepare)
    monkeypatch.setattr(phase_profiles,'verify_frozen_replay',lambda *a,**k:None)
    monkeypatch.setattr(evaluation_profiles,'verify_phase_source',lambda *a,**k:None)
    monkeypatch.setattr(funded_profiles,'verify_phase_source',lambda *a,**k:None)


CURRENT_BOOK={}


def install(sessions):
    CURRENT_BOOK.clear()
    for session in sessions:
        values=[]
        for id,trade in zip(session.source_trade_ids,session.trades):
            if len(trade)==5: values.append(trade)
            else: values.append((*trade,True,dict(source_trade_id=id,side=None,entry_time_utc=session.session+'T15:00:00Z',sizing_decision=None,initial_stop=None)))
        CURRENT_BOOK[session.session]=values


def replay_evaluation(spec,sessions):
    install(sessions)
    return evaluation_profiles.replay_evaluation_profile(None,None,spec.profile,spec.micros,spec.window,spec.calendar,
        retry=spec.retry,max_micros=spec.max_micros,sizing=spec.sizing,frozen_binding=BINDING)


def replay_funded(spec,sessions):
    install(sessions)
    return funded_profiles.replay_funded_profile(None,None,spec.profile,spec.micros,spec.window,spec.calendar,
        receipt_delay_calendar_days=spec.receipt_delay_calendar_days,receipt_amount_convention=spec.receipt_amount_convention,
        max_micros=spec.max_micros,sizing=spec.sizing,frozen_binding=BINDING)


def settlement(day,entitlement,gross,lag,convention,cutoff):
    return dated_settlement(day,entitlement,gross,lag,cutoff,convention)


BINDING={'outer_fold_index':1,'candidate_id':'synthetic-unit-choice'}


def dates(start,end):
    a,b=map(date.fromisoformat,(start,end))
    return [str(a+timedelta(days=i)) for i in range((b-a).days) if (a+timedelta(days=i)).weekday()<5]


def book(end,by_day,start='2026-01-05'):
    result=[]
    for stamp in dates(start,end):
        trades=tuple(by_day.get(stamp,[]))
        result.append(SimpleNamespace(session=stamp,trades=trades,source_trade_ids=tuple(t[4]['source_trade_id'] if len(t)>4 else f'{stamp}-{i}' for i,t in enumerate(trades))))
    return tuple(result)


def trade(net,adverse=0):return (float(net),float(adverse),((float(adverse),True),))


def evaluation(end='2026-01-10',**kwargs):
    return SimpleNamespace(window=ReplayWindow('2026-01-05',end),calendar=PhaseCalendar(('2026-01-05',),'2027-01-01'),
        profile=EvaluationProfile('apex-50k-eod',rule_version('apex-50k-eod'),'30','40'),micros=10,max_micros=40,
        retry=SequentialRetry(),sizing=kwargs.get('sizing'))


def funded(end='2026-01-14',firm='apex-50k-eod',q=3,**kwargs):
    return SimpleNamespace(window=ReplayWindow('2026-01-05',end),calendar=PhaseCalendar(('2026-01-05',),'2027-01-01'),
        profile=FundedProfile(firm,rule_version(firm)),micros=q,max_micros=40,receipt_delay_calendar_days=4,
        receipt_amount_convention='kernel_entitlement_unrounded',sizing=kwargs.get('sizing'))


def test_evaluation_complete_activation_keeps_no_trade_day_and_stops_before_funded():
    events={'2026-01-05':[trade(1000)],'2026-01-07':[trade(2000)],'2026-01-09':[trade(999999)]}
    r=replay_evaluation(evaluation(),book('2026-01-10',events))
    assert r['evaluation_passed'] and r['acquisition_completed'] and r['ready_date']=='2026-01-09'
    assert Decimal(r['paid_fees'])==70 and Decimal(r['net_cash'])==-70
    assert [item['date'] for item in r['trace']]==['2026-01-05','2026-01-06','2026-01-07','2026-01-08']
    assert r['trace'][-1]['event']=='activation_wait' and r['trace'][-1]['executed']==0
    assert r['trace'][1]['executed']==0 and r['calendar_days_to_funded']==4
    assert {e['event'] for e in r['cash_ledger']}=={'evaluation_purchase','evaluation_passed','activation_payment','funded_ready'}


def test_pass_does_not_imply_activation_payment_or_acquisition_inside_cutoff():
    end='2026-01-08';events={'2026-01-05':[trade(1000)],'2026-01-07':[trade(2000)]}
    r=replay_evaluation(evaluation(end),book(end,events))
    assert r['evaluation_passed'] and not r['acquisition_completed'] and r['censored']
    assert Decimal(r['paid_fees'])==30 and Decimal(r['pending_activation'])==40


def test_sequential_actual_date_retry_wait_does_not_consume_or_resample_intervening_winners():
    end='2026-01-13';spec=evaluation(end);spec.retry=SequentialRetry(retry_delay_calendar_days=2)
    events={'2026-01-05':[trade(-2100,2100)],'2026-01-06':[trade(999999)],'2026-01-07':[trade(999999)],'2026-01-08':[trade(3000)]}
    r=replay_evaluation(spec,book(end,events))
    assert [a['purchase_date'] for a in r['attempts']]==['2026-01-05','2026-01-08']
    assert [a['outcome'] for a in r['attempts']]==['blown','passed']
    assert [x['date'] for x in r['trace'] if x['event']=='evaluation_session']==['2026-01-05','2026-01-08']
    assert [(x['date'],x['executed']) for x in r['trace'] if x['event']=='retry_wait']==[('2026-01-06',0),('2026-01-07',0)]
    assert r['observations']==dict(source_opportunities=4,visited=2,unvisited=2)
    assert r['trace'][0]['equity_after']==-2100
    assert r['ready_date']=='2026-01-12' and r['calendar_days_to_funded']==7
    assert Decimal(r['paid_fees'])==100 and Decimal(r['net_cash'])==-100


def test_retry_guard_retains_failed_fee_without_fabricating_funded_time():
    spec=evaluation();spec.retry=SequentialRetry(max_attempts=1)
    r=replay_evaluation(spec,book('2026-01-10',{'2026-01-05':[trade(-2100,2100)]}))
    assert r['outcome']=='attempt_guard_censored' and r['calendar_days_to_funded'] is None
    assert Decimal(r['paid_fees'])==30 and len(r['attempts'])==1


@pytest.mark.parametrize('end,received,pending',[('2026-01-13',0,1500),('2026-01-14',1500,0)])
def test_apex_funded_receipt_cutoff_and_cash_conservation(end,received,pending):
    events={stamp:[trade(3000)] for stamp in dates('2026-01-05','2026-01-10')}
    r=replay_funded(funded(end),book(end,events))
    assert Decimal(r['trading_profit'])==4500 and Decimal(r['gross_account_deductions'])==1500
    assert Decimal(r['equity'])==3000 and Decimal(r['cash_received'])==received and Decimal(r['pending_cash'])==pending
    assert r['payout_events'][0]['request_date']=='2026-01-09' and r['payout_events'][0]['receipt_date']=='2026-01-13'
    assert r['lifetime_censored'] and r['horizon_observations_complete']


def test_lucid_receipt_after_breach_is_kept_without_replacement_or_equity_payout():
    end='2026-01-14';events={stamp:[trade(200)] for stamp in dates('2026-01-05','2026-01-10')}
    events.update({'2026-01-12':[trade(-600,600)],'2026-01-13':[trade(999999)]})
    r=replay_funded(funded(end,'lucidflex-50k',10),book(end,events))
    assert r['terminal_date']=='2026-01-12' and r['outcome']=='blown'
    assert Decimal(r['equity'])==-100 and Decimal(r['cash_received'])==450 and Decimal(r['gross_account_deductions'])==500
    assert r['payout_events'][0]['provider_retained_share']=='50.0'
    assert '2026-01-13' not in [t['date'] for t in r['trace']]
    assert len(r['payout_events'])==1 and r['observed_sessions']==6


def causal_trade(day,net):
    return (*trade(net*10,max(0,-net*10)),True,dict(source_trade_id=day,side='long',entry_time_utc=day+'T15:01:00Z',
        sizing_decision=dict(timestamp_utc=day+'T15:00:00Z',reference_price='100',execution_timing='next_open'),
        initial_stop=dict(price='95',known_at_utc=day+'T15:00:00Z',basis='strategy_decision')))


def test_dynamic_chronology_changes_quantity_using_prior_day_only():
    sizing=SizingConfiguration(policy=dict(kind='percentage_risk',risk_percent='0.2',reference='current_account_balance'),
        initial_configured_capital='50000',planning_execution=dict(tick_size='.25',commission_per_contract_per_side='0'))
    spec=funded('2026-01-07',q=40,sizing=sizing)
    r=replay_funded(spec,book('2026-01-07',{'2026-01-05':[causal_trade('2026-01-05',-10)],'2026-01-06':[causal_trade('2026-01-06',20)]}))
    assert [d['quantity'] for d in r['sizing_decisions']]==[10,9] and Decimal(r['equity'])==80
    assert [t['date'] for t in r['trace']]==['2026-01-05','2026-01-06']


def test_observed_inventory_uses_exact_dates_and_rejects_hidden_trade_or_duplicate():
    period=ResearchPeriod('2026-01-05','2026-01-07')
    grid=observed_session_grid([],period,['2026-01-05','2026-01-07'])
    assert [str(d.date()) for d in grid]==['2026-01-05','2026-01-07']
    for bad in [['2026-01-07','2026-01-05'],['2026-01-05','2026-01-05'],[]]:
        with pytest.raises(ValueError):observed_session_grid([],period,bad)
    row={'entry_utc':'2026-01-06T15:00:00Z','exit_utc':'2026-01-06T15:01:00Z'}
    with pytest.raises(ValueError,match='outside'):observed_session_grid([row],period,['2026-01-05','2026-01-07'])
    assert len(observed_session_grid([],period,None))==3


@pytest.mark.parametrize('end,state',[('2026-01-31','open'),('2026-02-03','expired')])
def test_no_trade_sessions_distinguish_unfinished_attempt_from_provider_expiry(end,state):
    r=replay_evaluation(evaluation(end),book(end,{}))
    assert r['attempts'][0]['outcome']==state and not r['evaluation_passed']
    assert r['attempts'][0]['sessions']==(20 if state=='open' else 21)
    assert Decimal(r['paid_fees'])==30


def test_cent_rounding_and_unrounded_forecast_scenarios_are_explicit():
    args=(date(2026,1,5),Decimal('450.005'),Decimal('500.005'),0)
    bank=settlement(*args,'usd_cents_half_up',date(2026,1,6))
    forecast=settlement(*args,'kernel_entitlement_unrounded',date(2026,1,6))
    assert bank['trader_amount']=='450.01' and bank['rounding_delta']=='0.005'
    assert forecast['trader_amount']=='450.005' and forecast['rounding_delta']=='0.000'


def test_funded_readiness_exactly_at_cutoff_is_pending_after_paid_activation():
    end='2026-01-09'
    r=replay_evaluation(evaluation(end),book(end,{'2026-01-07':[trade(3000)]}))
    assert r['ready_date']==end and not r['acquisition_completed'] and r['censored']
    assert r['activation_paid'] and Decimal(r['paid_fees'])==70 and Decimal(r['pending_activation'])==0
    assert r['calendar_days_to_funded'] is None
    assert 'funded_ready' not in [e['event'] for e in r['cash_ledger']]


def test_last_observed_session_pass_does_not_invent_future_activation_calendar():
    end='2026-01-10';spec=evaluation(end)
    spec.calendar=PhaseCalendar(('2026-01-05',),end)
    r=replay_evaluation(spec,book(end,{'2026-01-09':[trade(3000)]}))
    assert r['evaluation_passed'] and r['eligibility_date'] is None and r['ready_date'] is None
    assert Decimal(r['paid_fees'])==30 and Decimal(r['pending_activation'])==40


def test_calendar_guard_during_activation_is_censoring_not_provider_failure():
    end='2026-01-14';spec=evaluation(end)
    spec.retry=SequentialRetry(max_calendar_days=3)
    r=replay_evaluation(spec,book(end,{'2026-01-07':[trade(3000)]}))
    assert r['outcome']=='activation_pending' and r['calendar_guard_truncates_window'] and r['censored']
    assert r['effective_observation_cutoff_exclusive']=='2026-01-08'
    assert Decimal(r['paid_fees'])==30 and Decimal(r['pending_activation'])==40


@pytest.mark.parametrize('end,acquired',[('2026-01-10',True),('2026-01-07',False)])
def test_readiness_at_retry_guard_matches_forecast_but_outer_cutoff_stays_exclusive(end,acquired):
    from alphaquest.prop.evaluation_optimization import acquisition_metrics
    from alphaquest.prop.phase_profiles import EvaluationSamplingConfig
    spec=evaluation(end);spec.retry=SequentialRetry(max_calendar_days=2)
    forecast=acquisition_metrics(SimpleNamespace(outcomes=['passed'],duration_weekdays=[1],
        censoring=SimpleNamespace(censored_paths=0)),spec.profile,spec.retry,spec.calendar,
        EvaluationSamplingConfig(chain_simulations=2))
    assert forecast['status']=='estimated' and forecast['metrics']['expected_calendar_days_to_funded']==2
    r=replay_evaluation(spec,book(end,{'2026-01-05':[trade(3000)],'2026-01-07':[trade(999999)]}))
    assert r['ready_date']=='2026-01-07' and r['acquisition_completed'] is acquired
    assert r['readiness_guard_inclusive'] and r['calendar_days_to_funded']==(2 if acquired else None)
    assert r['censored'] is not acquired and Decimal(r['paid_fees'])==70
    assert all(item['date']<'2026-01-07' for item in r['trace'])
    guard_events=[item for item in r['cash_ledger'] if item['date']=='2026-01-07']
    assert [item['event'] for item in guard_events]==(['funded_ready'] if acquired else [])
    assert all(Decimal(item['cash_delta'])==0 for item in guard_events)


def test_funded_observed_zero_trade_sessions_close_without_cash_or_fabricated_risk():
    end='2026-01-14'
    r=replay_funded(funded(end),book(end,{}))
    assert r['outcome']=='open' and r['observed_sessions']==7 and r['lifetime_censored']
    assert Decimal(r['cash_received'])==Decimal(r['pending_cash'])==Decimal(r['equity'])==0
    assert r['payout_events']==r['cash_ledger']==r['sizing_decisions']==[]
    assert r['sizing']['configuration'] is None and r['sizing']['summary']['decision_count']==0
    assert all(t['executed']==0 and t['decision_floor_state'] is None for t in r['trace'])
