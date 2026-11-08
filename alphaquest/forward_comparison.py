"""A single supplied Funded observation versus its frozen conditional model.

Calendar transport, coverage and platform adherence are explicit supplied claims.
No observation selects a policy or changes the saved model's original forecast.
"""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from .forward_reconcile import digest, stamp, effective_records, reconcile
from .session_calendar import session_date


LIMITATIONS = [
    'One supplied account path supports a descriptive difference, not calibration or proof of expected-value accuracy.',
    'Coverage, account identity, provider state and platform implementation are supplied claims, not independently verified broker evidence.',
    'A transported model retains its original absolute forecast dates; calendar-pattern stationarity is an explicit assumption, not an established future law.',
    'Payout eligibility, request timing, approval and platform payout implementation remain UNVERIFIED; observed cash may differ from the model without asserting provider conformance.',
    'Monte Carlo uncertainty remains conditional simulation error; it is not a prediction interval for this observation.',
]


def boundary(first, cutoff):
    zone = ZoneInfo('America/Chicago')
    opening = datetime.combine(date.fromisoformat(first)-timedelta(days=1), time(17), zone)
    ending = datetime.combine(date.fromisoformat(cutoff), time(), zone)
    return opening.astimezone(timezone.utc), ending.astimezone(timezone.utc)


def iso(value): return value.isoformat().replace('+00:00', 'Z')


def _pattern(first, cutoff, sessions, early):
    origin = date.fromisoformat(first)
    return dict(start_weekday=origin.weekday(), horizon_calendar_days=(date.fromisoformat(cutoff)-origin).days,
        open_session_offsets=[(date.fromisoformat(day)-origin).days for day in sessions],
        early_close_offsets={str((date.fromisoformat(day)-origin).days):clock for day,clock in sorted(early.items())},
        timezone='America/Chicago', boundary_law='CME session opening 17:00 prior civil date; receipts by Chicago civil date; exclusive local midnight cutoff')


def saved_cash_contract(package):
    """Read the exact saved model share, never refresh provider rules."""
    unknown=dict(status='UNKNOWN',reason='The selected saved payout share is absent, ambiguous or unverifiable.')
    config=package.get('configuration') or {};profile=config.get('profile')
    reviews=[r for r in (package.get('provider_rules') or {}).get('profiles',[]) if r.get('phase')=='funded' and r.get('profile')==profile]
    if len(reviews)!=1:return unknown
    review=reviews[0]
    if review.get('sha256')!=digest({k:v for k,v in review.items() if k!='sha256'}):return unknown
    fields=[f for f in review.get('fields',[]) if f.get('field') in ('payout_policy','payout_amount') and isinstance(f.get('model_value'),dict) and 'trader_share' in f['model_value']]
    if len(fields)!=1 or not isinstance(fields[0].get('model_value'),dict):return unknown
    value=fields[0]['model_value'];raw=value.get('trader_share')
    try:
        if type(raw) not in (str,int,float):return unknown
        share=Decimal(str(raw))
        if not share.is_finite() or not 0<share<=1:return unknown
    except Exception:return unknown
    return dict(status='CAPTURED_MODEL_SHARE',trader_share=str(share),profile=deepcopy(profile),
        review_sha256=review['sha256'],model_field=fields[0]['field'],payout_policy_model=deepcopy(value),
        payout_eligibility_request_and_approval_implementation='UNVERIFIED')


def reconcile_payout_cash(rows,contract):
    """Conserve linked gross withdrawals and net entitlement, without recharging."""
    result=dict(status='UNRESOLVED',reasons=[],requests=[],model_contract=contract)
    if contract.get('status')!='CAPTURED_MODEL_SHARE':
        result['reasons']=['Saved payout share authority is unknown.'];return result
    events=[r['event'] for r in sorted(rows,key=lambda r:(stamp(r['event']['event_time_utc']),r['event'].get('source_sequence') or 0,r['sequence'])) if r['event']['kind']=='cash']
    index={e['cash_event_id']:i for i,e in enumerate(events)}
    if len(index)!=len(events):result['reasons'].append('Duplicate cash identifiers prevent a conserved payout path.')
    requests={e['cash_event_id']:e for e in events if e['category']=='payout_request'}
    for event in events:
        if event['category'] in ('provider_deduction','trader_receipt') and event.get('related_cash_event_id') not in requests:
            result['reasons'].append('Every deduction and receipt needs a known correlated request.')
    with localcontext() as context:
        context.prec=128;share=Decimal(contract['trader_share'])
        for id,request in requests.items():
            deductions=[e for e in events if e['category']=='provider_deduction' and e.get('related_cash_event_id')==id]
            receipts=[e for e in events if e['category']=='trader_receipt' and e.get('related_cash_event_id')==id]
            if len(deductions)!=1:
                result['reasons'].append('Each modeled payout request needs exactly one known correlated gross account deduction.');continue
            deduction=deductions[0];gross=Decimal(deduction['amount']);entitlement=gross*share
            expected=(Decimal(request['amount']) if request.get('request_amount_basis')=='trader_entitlement' else
                Decimal(request['expected_trader_amount']) if request.get('expected_trader_amount') is not None else None)
            basis=request.get('request_amount_basis')
            if basis not in ('gross_withdrawal','trader_entitlement') or expected is None:
                result['reasons'].append('The request amount basis and trader entitlement must be known.')
            if basis=='gross_withdrawal' and Decimal(request['amount'])!=gross:
                result['reasons'].append('The declared gross withdrawal differs from the correlated account deduction.')
            if expected is not None and expected!=entitlement:
                result['reasons'].append('Declared trader entitlement differs from gross deduction times the saved trader share.')
            if index[id]>index[deduction['cash_event_id']] or any(index[deduction['cash_event_id']]>index[e['cash_event_id']] for e in receipts):
                result['reasons'].append('A payout must have causal request, deduction and receipt ordering.')
            paid=sum((Decimal(e['amount']) for e in receipts),Decimal(0))
            if paid>entitlement:result['reasons'].append('Actual receipts exceed the conserved trader entitlement.')
            result['requests'].append(dict(request_id=id,gross_account_deduction=str(gross),trader_share=str(share),
                trader_entitlement=str(entitlement),actual_receipts=str(paid),pending_entitlement=str(entitlement-paid)))
    result['reasons']=sorted(set(result['reasons']))
    if not result['reasons']:result['status']='RECONCILED_WITH_SAVED_SHARE'
    return result


def check_observation_plan(plan, policy, *, declared_at_utc):
    """Bind a prospective declared observation to a single saved model cohort."""
    p = plan.model_dump(mode='json') if hasattr(plan, 'model_dump') else deepcopy(plan)
    package = policy.get('package') or {}
    if package.get('phase') != 'funded': raise ValueError('A matched observation requires an authoritative Funded package.')
    forecast = policy.get('training_forecast') or {}
    mean = (forecast.get('metrics') or {}).get('expected_funded_cash_payouts_within_horizon')
    if forecast.get('status')!='estimated' or mean is None or not Decimal(str(mean)).is_finite(): raise ValueError('The frozen Funded receipt mean is unresolved.')
    if Decimal(p['initial_balance']) != 50000 or p['currency'] != 'USD': raise ValueError('A fresh $50,000 USD account is required.')
    window, calendar = package.get('outer_window') or {}, package.get('calendar') or {}
    first, cutoff = window.get('first_session'), window.get('cutoff_date_exclusive')
    if not first or not cutoff or calendar.get('start_dates') != [first]:
        raise ValueError('Only one complete saved start cohort can be compared; a pooled forecast cannot be reduced post hoc.')
    if calendar.get('timezone') != 'America/Chicago' or not window.get('sessions'):
        raise ValueError('The frozen model calendar is incomplete or unsupported.')
    if package.get('receipt_amount_convention') != 'kernel_entitlement_unrounded':
        raise ValueError('The frozen receipt amount convention is unsupported for supplied comparison.')
    receipt_delay = package.get('receipt_delay_calendar_days')
    if type(receipt_delay) is not int or receipt_delay < 0: raise ValueError('The frozen receipt delay is unknown.')
    native = package.get('native_execution') or {}
    early = native.get('early_closes') or {}
    early = {day:clock for day,clock in early.items() if first <= day < cutoff}
    source_pattern = _pattern(first,cutoff,window['sessions'],early)
    target_pattern = _pattern(p['first_session'],p['cutoff_date_exclusive'],p['open_sessions'],p['early_closes'])
    if not 1 <= source_pattern['horizon_calendar_days'] <= 365 or source_pattern != target_pattern:
        raise ValueError('Observed calendar must preserve the saved weekday, civil horizon, open-session offsets and declared early-close pattern.')
    if p['calendar_alignment'] == 'exact_saved_dates' and (p['first_session'] != first or p['cutoff_date_exclusive'] != cutoff):
        raise ValueError('Exact calendar comparison requires the original saved absolute dates.')
    if p['calendar_alignment'] == 'declared_pattern_translation' and not p.get('transport_assumption','').strip():
        raise ValueError('A calendar translation requires an explicit prospective model-transport assumption.')
    start, end = boundary(p['first_session'],p['cutoff_date_exclusive'])
    if start < stamp(declared_at_utc): raise ValueError('Declare the observation before the complete first target session opens.')
    selected = policy.get('policy_selection_sealed_at_utc')
    if not selected or stamp(selected) > stamp(declared_at_utc): raise ValueError('Policy selection must be sealed before the observation declaration.')
    result = dict(version='funded-observation-binding-v1',plan=p,plan_sha256=digest(p),
        package_sha256=package['package_sha256'],candidate_id=package['candidate_id'],
        frozen_forecast=deepcopy(forecast),original_window=deepcopy(window),original_calendar=deepcopy(calendar),
        original_early_closes=early,relative_calendar_pattern=source_pattern,
        coverage_start_utc=iso(start),coverage_cutoff_utc=iso(end),declared_at_utc=declared_at_utc,
        calendar_alignment=p['calendar_alignment'],transport_assumption=p.get('transport_assumption'),
        receipt_delay_calendar_days=receipt_delay,receipt_amount_convention=package['receipt_amount_convention'],
        provider_rules_sha256=digest(package.get('provider_rules')),cash_contract=saved_cash_contract(package),supplied_claims_verified=False)
    result['binding_sha256'] = digest(result)
    return result


def compare_observation(declaration,policy,binding,records,as_of_utc,*,monitor_created_at_utc,conformance=None):
    """Evaluate complete declared scope. Unknown evidence never becomes zero."""
    package = policy.get('package') or {}
    base = dict(status='NOT_COMPARABLE',reasons=[],observation_count=0,
        frozen_expectation=deepcopy(policy.get('training_forecast')),
        frozen_scope=dict(phase=package.get('phase'),window=package.get('outer_window'),calendar=package.get('calendar'),
            receipt_delay_calendar_days=package.get('receipt_delay_calendar_days'),receipt_amount_convention=package.get('receipt_amount_convention')),
        metrics=None,coverage=dict(claim='unknown',independently_verified=False),
        limitations=LIMITATIONS,no_future_certification=True,production_qualified=False)
    if not binding:
        base['reasons']=['No prospective complete-lifecycle observation plan was declared.'];return base
    if binding.get('binding_sha256') != digest({k:v for k,v in binding.items() if k!='binding_sha256'}):
        raise ValueError('Captured observation binding changed.')
    if binding['package_sha256']!=package.get('package_sha256') or binding['frozen_forecast']!=policy.get('training_forecast'):
        raise ValueError('Observation binding differs from the captured frozen package or forecast.')
    p=binding['plan'];start=stamp(binding['coverage_start_utc']);end=stamp(binding['coverage_cutoff_utc']);asof=stamp(as_of_utc)
    base.update(plan_sha256=binding['plan_sha256'],calendar_alignment=dict(mode=binding['calendar_alignment'],
        original_window=binding['original_window'],observed_plan=p,relative_pattern=binding['relative_calendar_pattern'],
        assumption=binding['transport_assumption']))
    reasons=base['reasons']
    if start < stamp(monitor_created_at_utc):reasons.append('Observation began before monitor creation and its conservative policy-publication boundary.')
    if asof < end:reasons.append('The full declared observation horizon has not elapsed at this assessment clock.')
    # No correction or void may erase the existence of pre-policy supplied history.
    if any(stamp(row['event']['event_time_utc']) < start for row in records if row['event']['kind'] not in ('heartbeat','connection','void')):
        reasons.append('Supplied economic history predates the prospectively declared observation.')
    rows=effective_records(records)
    if any(stamp(r['received_at_utc'])>asof for r in records):
        reasons.append('The captured correction/event history was not entirely received at the assessment knowledge clock.')
    zone=ZoneInfo('America/Chicago')
    if any(r['event']['kind']=='cash' and stamp(r['event']['event_time_utc']).astimezone(zone).date()<date.fromisoformat(p['first_session']) for r in rows):
        reasons.append('Pre-origin civil-date cash is incompatible with a fresh Funded horizon; it remains preserved in the event ledger.')
    coverage=[row for row in rows if row['event']['kind']=='account_coverage' and stamp(row['event']['event_time_utc'])<=asof and stamp(row['received_at_utc'])<=asof]
    if len(coverage)!=1:
        reasons.append('Exactly one effective completed account-coverage declaration is required.');return base
    row=coverage[0];claim=row['event'];base['attestation_event_id']=claim['event_id']
    equality={'plan_sha256':binding['plan_sha256'],'package_sha256':binding['package_sha256'],'account_id':p['account_id'],
        'first_session':p['first_session'],'cutoff_date_exclusive':p['cutoff_date_exclusive'],'currency':'USD'}
    if any(claim.get(key)!=value for key,value in equality.items()):reasons.append('Coverage identity differs from the predeclared account, policy or interval.')
    if claim.get('coverage')!='complete' or claim.get('fresh_account') is not True or claim.get('frozen_policy_followed') is not True or claim.get('replacement_accounts')!=0 or Decimal(claim['initial_balance'])!=50000:
        reasons.append('Complete coverage of one fresh account following the frozen policy was not supplied.')
    if stamp(claim['complete_through_utc'])!=end or stamp(claim['event_time_utc'])<end or stamp(row['received_at_utc'])<end:
        reasons.append('Coverage completion and original received clocks must span the exact exclusive cutoff.')
    terminal=claim.get('terminal_at_utc')
    if terminal and not start<=stamp(terminal)<end:reasons.append('Terminal account event lies outside the declared horizon.')
    relevant=[r for r in rows if start<=stamp(r['event']['event_time_utc'])<end or (stamp(r['event']['event_time_utc'])==end and r['event']['kind'] in ('position','market','heartbeat','connection'))]
    trade_kinds={'signal','intent','order','order_status','fill','protection_intent','protection','sizing_decision'}
    if any(r['event']['kind'] in trade_kinds and str(session_date(stamp(r['event']['event_time_utc']))) not in p['open_sessions'] for r in relevant):
        reasons.append('Trading observations occur outside the declared compatible open-session calendar.')
    if terminal and any(r['event']['kind'] in trade_kinds and stamp(r['event']['event_time_utc'])>stamp(terminal) for r in relevant):
        reasons.append('Trading observations continue after the declared terminal account outcome; no replacement account is in scope.')
    # Reconcile a derived effective slice; removing correction-link metadata here
    # does not modify any stored row, source byte, receive clock or original event.
    scoped=[]
    for r in relevant:
        if r['event']['kind']=='account_coverage':continue
        v=deepcopy(r);v['event'].pop('supersedes_event_id',None);v['event'].pop('correction_reason',None);scoped.append(v)
    scope=reconcile(declaration,scoped,iso(end))
    if conformance is None:
        from .forward_conformance import evaluate_policy_conformance
        conformance=evaluate_policy_conformance(policy,scoped,as_of_utc,reconciliation=scope)
    if conformance.get('accepted_skip_signal_ids'):
        scope=reconcile(declaration,scoped,iso(end),accepted_skip_signal_ids=conformance['accepted_skip_signal_ids'])
    base['scope_reconciliation']=scope
    issues=scope['reconciliation']['issues']
    allowed={'drawdown_limit','current_drawdown_limit','observed_edge_deterioration','retrospective_import_not_known_at_assessment_time'}
    if any(item['code'] not in allowed for item in issues):reasons.append('The observed account path has unresolved causal, cash, protection, position or health evidence.')
    positions=[r['event'] for r in relevant if r['event']['kind']=='position']
    opening=[e for e in positions if stamp(e['event_time_utc'])==start]
    closing=[e for e in positions if stamp(e['event_time_utc'])==end]
    if len(opening)!=1 or opening[0]['signed_quantity']!=0 or opening[0].get('account_balance') is None or Decimal(opening[0]['account_balance'])!=50000:
        reasons.append('An exact fresh flat $50,000 opening snapshot is required.')
    if len(closing)!=1 or closing[0]['signed_quantity']!=0 or closing[0].get('account_balance') is None or scope['metrics']['signed_position']!=0:
        reasons.append('A reconciled flat closing account snapshot at the exclusive cutoff is required.')
    m=scope['metrics']
    if Decimal(m['evaluation_purchase_fees']) or Decimal(m['activation_fees']):reasons.append('Evaluation/acquisition fees are outside a fresh Funded-only observation.')
    payout_cash=reconcile_payout_cash(scoped,binding.get('cash_contract') or {})
    base['payout_cash_reconciliation']=payout_cash
    if payout_cash['status']!='RECONCILED_WITH_SAVED_SHARE':reasons.extend(payout_cash['reasons'])
    pending=m['pending_receipt_amount']
    if pending is None or claim.get('pending_trader_cash') is None or Decimal(pending)!=Decimal(claim['pending_trader_cash']):
        reasons.append('Pending trader entitlement is unknown or does not reconcile to the completion declaration.')
    if not conformance or conformance.get('status')!='MATCH':reasons.append('Local supplied decision arithmetic is incomplete or differs from the frozen policy.')
    base['policy_conformance']=conformance
    base['coverage']=dict(claim=claim['coverage'],independently_verified=False,coverage_start_utc=iso(start),cutoff_date_exclusive_utc=iso(end),
        statement=claim['statement'],terminal_status=claim['terminal_status'],terminal_at_utc=terminal,
        receiver_clock_provenance=getattr(declaration.source,'receiver_clock_provenance','server_wall_clock'))
    base['actual_observation']=dict(trader_receipts=m['trader_receipts'],pending_trader_cash=pending,
        evaluation_purchase_fees=m['evaluation_purchase_fees'],activation_fees=m['activation_fees'],as_of_utc=as_of_utc,
        excluded_cash_event_ids=[r['event']['event_id'] for r in rows if r['event']['kind']=='cash' and stamp(r['event']['event_time_utc'])>=end])
    if reasons:return base
    with localcontext() as ctx:
        ctx.prec=128
        metrics=binding['frozen_forecast']['metrics'];expected=Decimal(str(metrics['expected_funded_cash_payouts_within_horizon']));actual=Decimal(m['trader_receipts'])
        base['metrics']=dict(expected_trader_receipts=str(expected),observed_trader_receipts=str(actual),observed_minus_expected=str(actual-expected),
            observed_any_receipt=actual>0,modeled_probability_any_receipt=metrics.get('probability_first_payout'),
            observed_breach=claim['terminal_status']=='breached',modeled_breach_probability=metrics.get('account_breach_probability'),pending_trader_cash=pending)
    base.update(status='SYNTHETIC_SCOPE_COMPARISON' if declaration.observation_kind=='synthetic_harness' else 'SUPPLIED_SCOPE_COMPARISON',observation_count=1)
    return base
