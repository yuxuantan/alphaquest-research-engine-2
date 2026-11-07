"""Independent actual-controller cash oracles for staged pair orchestration."""
from copy import deepcopy
from dataclasses import replace
from datetime import date,timedelta
from decimal import Decimal,localcontext

import pytest

from alphaquest.execution import execute
from alphaquest.prop.evaluation_profiles import NativeEvaluationController
from alphaquest.prop.funded_profiles import NativeFundedController
from alphaquest.prop.evaluation_optimization import SequentialRetry
from alphaquest.prop.phase_profiles import EvaluationProfile,FundedProfile,rule_version
from alphaquest.prop.phase_search import PhaseCalendar
from alphaquest.session_calendar import load_calendar,session_date
from test_native_forecast_profiles import CONFIG,SIZING,context,factory
from native_replay_fixtures import bars

from alphaquest.prop.frozen_pairs import PairComparisonRequest,derive_continuation,seal
from alphaquest.prop.cash_ledger import merge_pair_cash


def input_request(**overrides):
    reference=dict(campaign_id='a'*32,package_sha256='b'*64,candidate_id='c'*64,source_backtest_id='d'*32)
    return dict(request_id='e'*32,window=dict(first_session='2026-01-05',cutoff_date_exclusive='2026-01-19'),
        pairs=[dict(id='Predeclared pair',evaluation=reference,funded=dict(reference,campaign_id='f'*32))],**overrides)


def test_strict_pair_contract_has_no_selector_budget_or_authorization_override():
    parsed=PairComparisonRequest.model_validate(input_request())
    assert parsed.replacement=='none' and len(parsed.pairs)==1
    for change in (dict(selector='net_cash_winner'),dict(monthly_budget='100'),dict(final_authorization='token'),dict(replacement='repeat')):
        with pytest.raises(ValueError):PairComparisonRequest.model_validate(input_request(**change))
    duplicate=input_request();duplicate['pairs'].append(dict(duplicate['pairs'][0],id='Alias'))
    with pytest.raises(ValueError,match='Duplicate'):PairComparisonRequest.model_validate(duplicate)
    bad=input_request();bad['window']['cutoff_date_exclusive']='2026-01-05'
    with pytest.raises(ValueError):PairComparisonRequest.model_validate(bad)


def actual_pair(cutoff):
    first=date(2026,1,5);end=date.fromisoformat(cutoff);calendar=load_calendar(symbol='MNQ')
    source=[bar for bar in bars(days=10,payout=True) if session_date(bar.timestamp_utc)<end]
    contexts={day:context(day,calendar,modeled=False) for day in sorted({session_date(bar.timestamp_utc) for bar in source})}
    version=rule_version('apex-50k-eod')
    evaluation=NativeEvaluationController(EvaluationProfile('apex-50k-eod',version,'30','40'),SIZING,3,
        session_contexts=contexts,start_date=first,cutoff_date_exclusive=end,
        calendar=PhaseCalendar((str(first),),cutoff),retry=SequentialRetry(activation_delay_sessions=1))
    for _ in execute(source,factory(),CONFIG,account_control=evaluation,completion='require_flat'):pass
    result=evaluation.finish_replay()
    binding=seal(dict(window=dict(first_session=str(first),cutoff_date_exclusive=cutoff),
        observed_sessions=[str(day) for day in contexts],policies=dict(funded=dict(package_sha256='a'*64))),'binding_sha256')
    continuation=derive_continuation(binding,result,'evaluation-child')
    funded_result=None
    if continuation:
        ready=date.fromisoformat(continuation['window']['first_session'])
        retained=[replace(bar,bar_number=i) for i,bar in enumerate((v for v in source if session_date(v.timestamp_utc)>=ready),1)]
        owner=NativeFundedController(FundedProfile('apex-50k-eod',version),SIZING,3,
            session_contexts={day:ctx for day,ctx in contexts.items() if day>=ready},
            start_date=ready,cutoff_date_exclusive=end,receipt_delay_calendar_days=2)
        for _ in execute(retained,factory(),CONFIG,account_control=owner,completion='require_flat'):pass
        funded_result=owner.finish_replay()
    cash=merge_pair_cash(result,funded_result,first_session=str(first),cutoff_date_exclusive=cutoff,
        child_ids=dict(evaluation='evaluation-child',funded='funded-child'))
    return result,funded_result,continuation,cash


@pytest.mark.parametrize('cutoff,received,pending,net',[('2026-01-19','1500','0','1430'),('2026-01-18','0','1500','-70')])
def test_real_native_pair_receipt_exclusive_cutoff_and_actual_fees(cutoff,received,pending,net):
    evaluation,funded,binding,cash=actual_pair(cutoff)
    assert evaluation['pass_date']=='2026-01-08'
    assert evaluation['eligibility_date']=='2026-01-09' and evaluation['ready_date']=='2026-01-12'
    assert Decimal(evaluation['paid_fees'])==70
    assert binding['estimand']=='remaining_horizon_chronological_continuation'
    assert funded['payout_events'][0]['request_date']=='2026-01-16'
    assert funded['payout_events'][0]['receipt_date']=='2026-01-18'
    assert Decimal(funded['trading_profit'])==4500 and Decimal(funded['equity'])==3000
    assert Decimal(cash['cash_received'])==Decimal(received)
    assert Decimal(cash['pending_cash'])==Decimal(pending)
    assert Decimal(cash['net_trader_cash'])==Decimal(net)
    assert Decimal(cash['gross_account_deductions'])==1500
    assert all(event['native_backtest_id'] for event in cash['cash_ledger'])


def test_ready_at_cutoff_never_starts_funded_and_keeps_all_paid_fees():
    evaluation,funded,binding,cash=actual_pair('2026-01-12')
    assert Decimal(evaluation['paid_fees'])==70 and not evaluation['acquisition_completed']
    assert funded is None and binding is None
    assert Decimal(cash['net_trader_cash'])==-70 and Decimal(cash['cash_received'])==0


def test_never_acquired_has_actual_negative_cash_no_funded_observations():
    evaluation,funded,binding,cash=actual_pair('2026-01-08')
    assert Decimal(evaluation['paid_fees'])==30 and not evaluation['evaluation_passed']
    assert funded is binding is None and Decimal(cash['net_trader_cash'])==-30


def test_cash_merge_fails_on_relabelled_equity_double_charge_and_future_receipts():
    evaluation=dict(paid_evaluation_fees='30.01',paid_activation_fees='40.02',paid_fees='70.03',
        cash_ledger=[dict(date='2026-01-05',event='evaluation_purchase',cash_delta='-30.01'),
                     dict(date='2026-01-06',event='activation_payment',cash_delta='-40.02')])
    funded=dict(cash_received='1500.11',pending_cash='0',gross_account_deductions='1500.11',
        raw_trader_entitlement='1500.11',provider_retained_share='0',receipt_rounding_delta='0',
        cash_ledger=[dict(date='2026-01-10',event='account_deduction',cash_delta='0'),
                     dict(date='2026-01-11',event='trader_receipt',cash_delta='1500.11')])
    kwargs=dict(first_session='2026-01-05',cutoff_date_exclusive='2026-01-12',child_ids=dict(evaluation='e',funded='f'))
    with localcontext() as ctx:
        ctx.prec=3
        assert merge_pair_cash(evaluation,funded,**kwargs)['net_trader_cash']=='1430.08'
    for changed in (dict(funded,cash_received='3000.11'),dict(funded,cash_ledger=[dict(funded['cash_ledger'][1],event='account_equity')]),
                    dict(funded,cash_ledger=[dict(funded['cash_ledger'][1],date='2026-01-12')]),
                    dict(funded,cash_ledger=[dict(funded['cash_ledger'][0],cash_delta='-1500.11'),funded['cash_ledger'][1]])):
        with pytest.raises(ValueError):merge_pair_cash(evaluation,changed,**kwargs)


def test_continuation_rejects_forged_readiness_or_changed_pair_binding():
    binding=seal(dict(window=dict(first_session='2026-01-05',cutoff_date_exclusive='2026-01-19'),
        observed_sessions=['2026-01-12'],policies=dict(funded=dict(package_sha256='a'*64))),'binding_sha256')
    result=dict(phase='evaluation',mode='native_historical_chronological_replay',acquisition_completed=True,
        ready_date='2026-01-12',cash_ledger=[dict(event='funded_ready',date='2026-01-12')])
    assert derive_continuation(binding,result,'child')['window']['first_session']=='2026-01-12'
    bad=deepcopy(binding);bad['window']['cutoff_date_exclusive']='2026-01-20'
    with pytest.raises(ValueError,match='hash'):derive_continuation(bad,result,'child')
    with pytest.raises(ValueError,match='ready event'):derive_continuation(binding,dict(result,ready_date='2026-01-13'),'child')
    with pytest.raises(ValueError,match='Uncompleted'):derive_continuation(binding,dict(result,acquisition_completed=False),'child')
