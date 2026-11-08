from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import pytest

from alphaquest.forward_contracts import FundedObservationPlan, AccountCoverage
from alphaquest.forward_comparison import check_observation_plan, compare_observation, boundary, iso
from alphaquest.forward_reconcile import stamp, digest
from tests.test_forward_reconcile import declaration


def comparison_fixture():
    d=declaration()
    plan=FundedObservationPlan(first_session='2026-11-10',cutoff_date_exclusive='2026-11-17',
        open_sessions=['2026-11-10','2026-11-11','2026-11-12','2026-11-13','2026-11-16'],early_closes={},
        calendar_alignment='declared_pattern_translation',transport_assumption='Synthetic same-weekday calendar-pattern scenario; stationarity is not verified.',account_id='synthetic-funded')
    policy=dict(policy_selection_sealed_at_utc='2026-11-08T00:00:00Z',training_forecast=dict(status='estimated',
        metrics=dict(expected_funded_cash_payouts_within_horizon=1500.0,probability_first_payout=1.0,account_breach_probability=0.0)),
        package=dict(phase='funded',package_sha256='a'*64,candidate_id='b'*64,
        outer_window=dict(first_session='2026-01-27',cutoff_date_exclusive='2026-02-03',sessions=['2026-01-27','2026-01-28','2026-01-29','2026-01-30','2026-02-02']),
        calendar=dict(start_dates=['2026-01-27'],timezone='America/Chicago'),receipt_delay_calendar_days=0,
        receipt_amount_convention='kernel_entitlement_unrounded'))
    profile=dict(profile_id='apex-50k-eod',rule_version='synthetic-saved-rule')
    review=dict(phase='funded',profile=profile,fields=[dict(field='payout_policy',model_value=dict(trader_share=1))])
    review['sha256']=digest(review)
    policy['package'].update(configuration=dict(profile=profile),provider_rules=dict(profiles=[review]))
    created='2026-11-09T00:00:00Z';binding=check_observation_plan(plan,policy,declared_at_utc=created)
    start,end=boundary(plan.first_session,plan.cutoff_date_exclusive)
    events=[]
    def add(kind,when,**values):
        events.append(dict(kind=kind,event_id='event-'+str(len(events)),event_time_utc=iso(when),source_sequence=len(events)+1,**values))
    add('position',start,signed_quantity=0,account_balance='50000')
    add('connection',start,status='connected')
    add('market',start,price='100')
    add('heartbeat',start)
    # This is supplied cash evidence, not a claim that the modeled provider
    # would approve this request. Platform implementation remains unverified.
    add('cash',end-timedelta(hours=1),cash_event_id='request',category='payout_request',amount='50',request_amount_basis='trader_entitlement')
    add('cash',end-timedelta(minutes=59),cash_event_id='deduction',category='provider_deduction',amount='50',related_cash_event_id='request')
    add('cash',end-timedelta(minutes=58),cash_event_id='receipt',category='trader_receipt',amount='50',related_cash_event_id='request')
    add('position',end,signed_quantity=0,account_balance='49950')
    add('market',end,price='100')
    add('heartbeat',end)
    add('account_coverage',end,plan_sha256=binding['plan_sha256'],package_sha256='a'*64,account_id=plan.account_id,
        first_session=plan.first_session,cutoff_date_exclusive=plan.cutoff_date_exclusive,coverage='complete',fresh_account=True,
        initial_balance='50000',currency='USD',frozen_policy_followed=True,terminal_status='active_at_cutoff',
        terminal_at_utc=None,replacement_accounts=0,pending_trader_cash='0',complete_through_utc=iso(end),statement='Complete deterministic synthetic fixture; no broker verification.')
    AccountCoverage.model_validate(events[-1])
    records=[dict(sequence=i,event=e,received_at_utc=iso(end+timedelta(seconds=1))) for i,e in enumerate(events,1)]
    return d,policy,binding,records,iso(end+timedelta(seconds=2)),created


def compare(fixture=None,**kw):
    d,p,b,r,t,created=fixture or comparison_fixture()
    return compare_observation(d,p,b,r,t,monitor_created_at_utc=created,conformance=kw.get('conformance',dict(status='MATCH')))


def test_exact_cash_delta_and_supplied_only_single_path():
    out=compare()
    assert out['status']=='SYNTHETIC_SCOPE_COMPARISON',out['reasons']
    assert Decimal(out['metrics']['observed_trader_receipts'])==50
    assert Decimal(out['metrics']['expected_trader_receipts'])==1500
    assert Decimal(out['metrics']['observed_minus_expected'])==-1450
    assert out['observation_count']==1 and not out['coverage']['independently_verified']
    assert out['frozen_scope']['window']['first_session']=='2026-01-27'
    assert out['calendar_alignment']['observed_plan']['first_session']=='2026-11-10'
    assert out['no_future_certification'] and not out['production_qualified']


@pytest.mark.parametrize('field,value',[('coverage','partial'),('fresh_account',False),('frozen_policy_followed',False),('replacement_accounts',1),('pending_trader_cash',None),('pending_trader_cash','1'),('account_id','other'),('package_sha256','f'*64)])
def test_missing_or_conflicting_coverage_withholds(field,value):
    fixture=list(comparison_fixture());fixture[3][-1]['event'][field]=value
    assert compare(fixture)['status']=='NOT_COMPARABLE'


def test_cash_exactly_cutoff_is_excluded_and_pending_preserved():
    fixture=list(comparison_fixture());r=fixture[3];end=stamp(fixture[2]['coverage_cutoff_utc'])
    receipt=next(row for row in r if row['event'].get('cash_event_id')=='receipt')
    receipt['event']['event_time_utc']=iso(end)
    receipt['event']['source_sequence']=7
    r[-1]['event']['pending_trader_cash']='50'
    out=compare(fixture)
    assert out['status']=='SYNTHETIC_SCOPE_COMPARISON',out['reasons']
    assert Decimal(out['metrics']['observed_trader_receipts'])==0
    assert Decimal(out['metrics']['pending_trader_cash'])==50
    assert out['actual_observation']['excluded_cash_event_ids']==[receipt['event']['event_id']]


def test_correction_retains_prior_report_and_changed_receipt_delta():
    fixture=list(comparison_fixture());before=compare(fixture);r=fixture[3]
    original=next(row for row in r if row['event'].get('cash_event_id')=='receipt')
    corrected=deepcopy(original);corrected['sequence']=len(r)+1;corrected['event'].update(event_id='receipt-correction',supersedes_event_id=original['event']['event_id'],correction_reason='Correct supplied receipt',amount='25')
    r.append(corrected);r[-2]['event']['pending_trader_cash']='25'
    out=compare(fixture)
    assert out['status']=='SYNTHETIC_SCOPE_COMPARISON',out['reasons']
    assert Decimal(out['metrics']['observed_minus_expected'])==-1475
    assert Decimal(before['metrics']['observed_trader_receipts'])==50


def test_unknown_or_mismatched_policy_arithmetic_withholds():
    for status in ['MISMATCH','INSUFFICIENT_EVIDENCE']:
        assert compare(conformance=dict(status=status))['status']=='NOT_COMPARABLE'


def test_prospective_guard_cannot_be_bypassed_by_corrections_or_early_assessment():
    fixture=list(comparison_fixture());fixture[4]=fixture[2]['coverage_start_utc']
    assert compare(fixture)['status']=='NOT_COMPARABLE'
    fixture=list(comparison_fixture());fixture[-1]=fixture[2]['coverage_cutoff_utc']
    assert compare(fixture)['status']=='NOT_COMPARABLE'


def test_plan_rejects_calendar_cohort_horizon_or_posthoc_declaration():
    _,policy,binding,_,_,created=comparison_fixture();p=binding['plan']
    for mutate in [lambda q:q['open_sessions'].pop(),lambda q:q.update(cutoff_date_exclusive='2026-11-18'),
                   lambda q:q.update(early_closes={'2026-11-10':'12:00'}),lambda q:q.update(calendar_alignment='exact_saved_dates',transport_assumption=None)]:
        q=deepcopy(p);mutate(q)
        with pytest.raises(ValueError):check_observation_plan(FundedObservationPlan.model_validate(q),policy,declared_at_utc=created)
    changed=deepcopy(policy);changed['package']['calendar']['start_dates'].append('2026-01-28')
    with pytest.raises(ValueError,match='cohort'):check_observation_plan(FundedObservationPlan.model_validate(p),changed,declared_at_utc=created)
    with pytest.raises(ValueError,match='before'):check_observation_plan(FundedObservationPlan.model_validate(p),policy,declared_at_utc=binding['coverage_cutoff_utc'])


def test_strict_claims_and_dates():
    _,_,b,r,_,_=comparison_fixture()
    for change in [dict(fresh_account=1),dict(replacement_accounts=True),dict(pending_trader_cash=0),dict(initial_balance='NaN')]:
        value=deepcopy(r[-1]['event']);value.update(change)
        with pytest.raises(ValueError):AccountCoverage.model_validate(value)
    for change in [dict(open_sessions=list(reversed(b['plan']['open_sessions']))),dict(first_session='2026-11-1'),dict(transport_assumption='')]:
        value=deepcopy(b['plan']);value.update(change)
        with pytest.raises(ValueError):FundedObservationPlan.model_validate(value)


def test_cash_before_first_civil_date_cannot_inflate_the_model_horizon():
    fixture=list(comparison_fixture());r=fixture[3];start=stamp(fixture[2]['coverage_start_utc'])
    for row in r:
        if row['event']['kind']=='cash':row['event']['event_time_utc']=iso(start+timedelta(hours=1,seconds=row['sequence']))
    out=compare(fixture)
    assert out['status']=='NOT_COMPARABLE'
    assert any('Pre-origin civil-date cash' in reason for reason in out['reasons'])
    assert Decimal(out['scope_reconciliation']['metrics']['trader_receipts'])==50


def test_not_yet_received_correction_cannot_replace_known_history_for_comparison():
    fixture=list(comparison_fixture());r=fixture[3]
    original=next(row for row in r if row['event'].get('cash_event_id')=='receipt')
    correction=deepcopy(original);correction['sequence']=len(r)+1
    correction['received_at_utc']=iso(stamp(fixture[4])+timedelta(days=1))
    correction['event'].update(event_id='future-received-correction',supersedes_event_id=original['event']['event_id'],correction_reason='Received later',amount='25')
    r.append(correction)
    out=compare(fixture)
    assert out['status']=='NOT_COMPARABLE'
    assert any('knowledge clock' in reason for reason in out['reasons'])


def test_breach_is_an_observed_outcome_not_a_reason_to_drop_pending_cash():
    fixture=list(comparison_fixture());r=fixture[3];end=stamp(fixture[2]['coverage_cutoff_utc'])
    receipt=next(row for row in r if row['event'].get('cash_event_id')=='receipt')
    receipt['event']['event_time_utc']=iso(end+timedelta(hours=1))
    r[-1]['event'].update(terminal_status='breached',terminal_at_utc=iso(end-timedelta(minutes=30)),pending_trader_cash='50')
    out=compare(fixture)
    assert out['status']=='SYNTHETIC_SCOPE_COMPARISON',out['reasons']
    assert out['metrics']['observed_breach'] is True
    assert Decimal(out['metrics']['observed_trader_receipts'])==0
    assert Decimal(out['metrics']['pending_trader_cash'])==50


def test_ambiguous_cash_tie_and_missing_closing_snapshot_withhold():
    for mode in ['tie','closing']:
        fixture=list(comparison_fixture());r=fixture[3]
        if mode=='tie':
            money=[row for row in r if row['event']['kind']=='cash']
            money[1]['event']['event_time_utc']=money[0]['event']['event_time_utc']
            money[1]['event'].pop('source_sequence')
        else:r[:]=[row for row in r if not(row['event']['kind']=='position' and row['event'].get('account_balance')=='49950')]
        assert compare(fixture)['status']=='NOT_COMPARABLE'


def test_declared_closed_sessions_and_post_terminal_trading_withhold():
    for mode in ['closed','terminal']:
        fixture=list(comparison_fixture());r=fixture[3]
        when='2026-11-14T15:00:00Z' if mode=='closed' else '2026-11-16T15:00:00Z'
        if mode=='terminal':r[-1]['event'].update(terminal_status='breached',terminal_at_utc='2026-11-13T15:00:00Z')
        r.append(dict(sequence=len(r)+1,received_at_utc=r[0]['received_at_utc'],event=dict(kind='signal',event_id='out-of-scope-signal',
            event_time_utc=when,source_sequence=5,signal_id='out',side='buy',quantity=3,reference_price='100')))
        out=compare(fixture)
        assert out['status']=='NOT_COMPARABLE'
        assert any('open-session' in reason or 'terminal account' in reason for reason in out['reasons'])


@pytest.mark.parametrize('case',['undersized','missing','unrelated','duplicate'])
def test_incomplete_gross_deduction_conservation_withholds_matched_scope(case):
    fixture=list(comparison_fixture());r=fixture[3]
    deduction=next(row for row in r if row['event'].get('cash_event_id')=='deduction')
    closing=next(row for row in r if row['event']['kind']=='position' and row['event'].get('account_balance')=='49950')
    if case=='undersized':deduction['event']['amount']='7';closing['event']['account_balance']='49993'
    elif case=='missing':r.remove(deduction);closing['event']['account_balance']='50000'
    elif case=='unrelated':deduction['event']['related_cash_event_id']='other-request'
    else:
        duplicate=deepcopy(deduction);duplicate['sequence']=len(r)+1
        duplicate['event'].update(event_id='second-deduction',cash_event_id='other-deduction',event_time_utc=iso(stamp(deduction['event']['event_time_utc'])+timedelta(seconds=1)),source_sequence=deduction['event']['source_sequence'])
        r.append(duplicate);closing['event']['account_balance']='49900'
    out=compare(fixture)
    assert out['status']=='NOT_COMPARABLE'
    assert out['payout_cash_reconciliation']['status']=='UNRESOLVED'
    assert Decimal(out['scope_reconciliation']['metrics']['trader_receipts'])==50


def test_saved_ninety_percent_share_preserves_gross1000_entitlement900():
    fixture=list(comparison_fixture());d,policy,b,r,t,created=fixture
    profile=dict(profile_id='lucidflex-50k',rule_version='synthetic-saved-rule')
    review=dict(phase='funded',profile=profile,fields=[dict(field='payout_amount',model_value=dict(trader_share=.9))])
    review['sha256']=digest(review)
    policy['package'].update(configuration=dict(profile=profile),provider_rules=dict(profiles=[review]))
    fixture[2]=check_observation_plan(FundedObservationPlan.model_validate(b['plan']),policy,declared_at_utc=created)
    for row in r:
        e=row['event']
        if e.get('cash_event_id')=='request':e.update(amount='1000',request_amount_basis='gross_withdrawal',expected_trader_amount='900')
        if e.get('cash_event_id')=='deduction':e['amount']='1000'
        if e.get('cash_event_id')=='receipt':e['amount']='900'
        if e['kind']=='position' and e.get('account_balance')=='49950':e['account_balance']='49000'
    out=compare(fixture)
    assert out['status']=='SYNTHETIC_SCOPE_COMPARISON',out['reasons']
    assert Decimal(out['metrics']['observed_trader_receipts'])==900
    request,=out['payout_cash_reconciliation']['requests']
    assert Decimal(request['gross_account_deduction'])==1000
    assert Decimal(request['trader_entitlement'])==900 and Decimal(request['pending_entitlement'])==0


def test_missing_saved_share_never_invents_a_gross_net_relationship():
    fixture=list(comparison_fixture());_,policy,b,_,_,created=fixture
    policy['package'].pop('provider_rules')
    fixture[2]=check_observation_plan(FundedObservationPlan.model_validate(b['plan']),policy,declared_at_utc=created)
    out=compare(fixture)
    assert out['status']=='NOT_COMPARABLE'
    assert 'Saved payout share authority is unknown.' in out['reasons']
