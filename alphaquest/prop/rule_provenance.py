"""Dated primary-document review; never a live input or a numerical rule patch.

The review date is not a provider effective date. Historical reports retain
their captured reviews; absent/unknown reviews fail closed for readiness.
"""
from dataclasses import asdict
from hashlib import sha256
from .adapter import canonical

VERSION = 'provider-rule-review-2026-11-08-v1'
REVIEWED_AT = '2026-11-08'
APEX = 'https://apextraderfunding.com/help-center/'
LUCID = 'https://support.lucidtrading.com/en/articles/'
SOURCES = dict(
    apex_evaluation=APEX+'eod-accounts/eod-evaluations/',
    apex_expiry=APEX+'billing/evaluation-plan-fees-and-access-explained/',
    apex_activation=APEX+'billing/pa-activation-process-deadline-explained/',
    apex_drawdown=APEX+'eod-trailing-drawdown-accounts/eod-drawdown-explained/',
    apex_scaling=APEX+'additional-helpful-items/scaling-levels-pa-explained/',
    apex_payouts=APEX+'eod-trailing-drawdown-accounts/eod-payouts/',
    apex_inactivity=APEX+'billing/inactivity-policy-on-performance-accounts-pa/',
    apex_settlement=APEX+'additional-helpful-items/payout-method-information/',
    lucid_evaluation=LUCID+'12945790-lucidflex-evaluation-account',
    lucid_funded=LUCID+'12945795-lucidflex-funded-account',
    lucid_drawdown=LUCID+'12945815-lucidflex-drawdown',
    lucid_scaling=LUCID+'12945808-lucidflex-scaling-plan',
    lucid_customization=LUCID+'16226050-lucidflex-customization',
    lucid_payouts=LUCID+'12945796-lucidflex-payouts',
    lucid_inactivity=LUCID+'11404632-inactivity-policy')


def _field(name, model, observation, source, *, gap=None, kind='provider_rule'):
    return dict(field=name, model_value=model, primary_observation=observation,
        source_url=SOURCES[source] if source else None, reviewed_at=REVIEWED_AT,
        provider_effective_at=None, status='UNVERIFIED' if gap else 'VERIFIED_DOCUMENT',
        kind=kind, gap=gap, scope='Published wording only; account entitlement and numerical provider parity not verified')


def profile_review(profile, phase):
    from .phase_profiles import EvaluationProfile, FundedProfile, rule_version
    expected = EvaluationProfile if phase == 'evaluation' else FundedProfile if phase == 'funded' else None
    if expected is None or type(profile) is not expected:
        raise ValueError('Rule review requires the matching explicit phase profile.')
    if profile.rule_version != rule_version(profile.profile_id):
        raise ValueError('No current review can certify an unknown historical rule version.')
    lucid = profile.profile_id == 'lucidflex-50k'
    fields = []
    if lucid:
        fields.append(_field('drawdown', dict(amount=2000, eod=True, lock_profit=100),
            '50K EOD loss allowance is 2000; the floor locks at 50100, including after a payout request.', 'lucid_drawdown'))
        fields.append(_field('daily_loss', 1200 if profile.daily_loss_limit else None,
            'DLL can be enabled in both phases; hitting it pauses the session. DLL-off removes the daily cap.',
            'lucid_customization', gap='The fixed 1200 amount and behavior above the trailing floor were not independently established on this page.' if profile.daily_loss_limit else None))
        fields.append(_field('inactivity', dict(calendar_days=30, minimum_absolute_closed_result=1),
            'At least one profit or loss of 1 dollar is required within 30 calendar days.', 'lucid_inactivity',
            gap='Exact account creation time, inclusive boundary and enforcement timing remain unverified.'))
        if phase == 'evaluation':
            fields.extend([
                _field('target_and_consistency', dict(target=3000, maximum_best_day_fraction=.4, max_micros=40),
                    '50K target 3000, 40% standard consistency, maximum 40 micros; 50% is a separate add-on.', 'lucid_evaluation'),
                _field('expiry', None, 'The evaluation has no pass deadline or monthly rebilling.', 'lucid_evaluation'),
                _field('activation_fee', profile.activation_fee, 'The published activation fee is zero.', 'lucid_evaluation',
                    gap=None if profile.activation_fee in ('0','0.0','0.00') else 'The saved fee differs from the published zero activation fee.'),
                _field('activation_timing', 'saved session delay', 'Published upgrade timing is 5–30 minutes after qualifying.', 'lucid_evaluation',
                    gap='Session-level activation is a modeling assumption; eligibility/review timing is not reproduced.')])
        else:
            fields.extend([
                _field('consistency', None, 'Funded LucidFlex has no consistency requirement.', 'lucid_funded'),
                _field('contract_limits', [[0,20],[1000,30],[2000,40]],
                    '50K funded tiers allow 20, 30 and 40 micros at profit thresholds 0, 1000 and 2000, updated after each session.', 'lucid_scaling'),
                _field('payout_amount', dict(qualifying_days=5, daily_profit=150, minimum=500, maximum=2000, fraction=.5, trader_share=.9, max_payouts=5),
                    '50K: five 150-dollar days, positive cycle profit, 500 minimum, half of profit capped at 2000, 90% trader share, five payouts before live transition.', 'lucid_payouts'),
                _field('payout_approval', 'immediate request and deduction',
                    'Balance losses before processing can deny a request; deduction follows approval and disbursement is within two business days.', 'lucid_payouts',
                    gap='Approval and denial are not simulated. Fixed calendar receipt lag and payment after closure are unverified assumptions.'),
                _field('payout_clock', 'observed eligible trade mark if DLL-on; otherwise session close',
                    'DLL-on allows requests 18:00–15:45 ET and pauses trading; DLL-off uses end-of-day requests.', 'lucid_customization',
                    gap='Observed marks cannot establish unobserved intratrade eligibility or actual approval time.')])
    else:
        fields.append(_field('drawdown', dict(amount=2000, eod=True, touch_breaches=True),
            '50K drawdown is 2000, updated from the highest close and enforced intraday; touching the floor closes the account.', 'apex_drawdown'))
        if phase == 'evaluation':
            fields.extend([
                _field('target_and_limits', dict(target=3000, daily_loss=1000, max_micros=60, consistency=None),
                    '50K evaluation target 3000, DLL 1000, six minis, no consistency or minimum-day requirement.', 'apex_evaluation'),
                _field('expiry', dict(sessions=21), 'Access expires after 30 calendar days, including weekends and holidays.', 'apex_expiry',
                    gap='The preserved kernel expires after 21 sampled/observed sessions. This differs from a purchase-timestamp 30-calendar-day expiry.'),
                _field('evaluation_trail_platform', 'uncapped EOD trail until passing',
                    'Tradovate trails indefinitely; Rithmic/Wealthcharts lock the evaluation floor at target balance.', 'apex_drawdown',
                    gap='The profile does not select or certify a platform-specific rule variant.'),
                _field('activation', 'automatic after declared session delay',
                    'Pass processing follows market close; activation must be completed within seven calendar days after official pass status.', 'apex_activation',
                    gap='Automatic modeled activation does not reproduce approval timing, account access or the activation deadline.')])
        else:
            fields.extend([
                _field('funded_floor_lock', 100, 'The funded floor stops at starting balance plus 100.', 'apex_drawdown'),
                _field('contract_and_daily_limits', [[0,20,1000],[1500,30,1000],[3000,40,2000],[6000,40,3000]],
                    'Prior-close tiers apply next session: 2/3/4/4 minis with DLL 1000/1000/2000/3000; ten micros equal one mini.', 'apex_scaling',
                    gap='The published last two rows overlap at 5999; the preserved model uses 6000 for the final threshold.'),
                _field('inactivity', dict(qualifying_days=2, daily_profit=50, session_window=21),
                    'Two days with at least 50 net profit are required in each rolling 30-calendar-day window.', 'apex_inactivity',
                    gap='The preserved account kernel uses 21 sessions, not a rolling 30-calendar-day clock.'),
                _field('payout_qualification', dict(days=5, daily_profit=250, safety_net=2100, best_day_fraction_at_most=.5),
                    '50K requests require five 250-dollar days, profit above a 2100 safety net and no single day at 50% or more of cycle profit.', 'apex_payouts',
                    gap='The kernel accepts exactly 50%; the current published wording excludes that boundary.'),
                _field('payout_policy', dict(request_full_cap_only=True, caps=[1500,1500,2000,2500,2500,3000], trader_share=1),
                    'Requests start at 500; six sequential 50K caps are 1500, 1500, 2000, 2500, 2500, 3000 with 100% trader share.', 'apex_payouts',
                    gap='Waiting for each full cap is an explicit request policy, not the provider minimum-eligible request policy.', kind='model_assumption'),
                _field('payout_approval', dict(immediate=True, approval_day_counts=profile.approval_day_counts),
                    'The generic payout page describes review, transfer and bank delays plus possible balance-related denial.', 'apex_settlement',
                    gap='That generic page mixes legacy eligibility wording; current EOD approval timing and approval-day treatment remain unverified.')])
    if phase == 'evaluation':
        fields.append(_field('evaluation_purchase_price', profile.evaluation_price,
            'Saved user-supplied purchase price; no account-specific checkout quote was obtained.', None,
            gap='Price, discounts, taxes and account-specific activation terms require current checkout evidence.', kind='user_assumption'))
        if not lucid:
            fields.append(_field('activation_fee', profile.activation_fee, 'Saved user-supplied activation fee.', None,
                gap='Current account-specific activation price was not independently verified.', kind='user_assumption'))
        fields.append(_field('retry_policy', 'saved sequential retry with fresh purchase and declared delay',
            'Research policy, not a promise of account availability or approval.', None,
            gap='Reset economics, purchase limits and operational delays are not certified.', kind='model_assumption'))
    else:
        fields.append(_field('receipt_and_termination', 'saved fixed calendar lag; pending claims may settle after account termination',
            'Receipt schedules are conditional modeling assumptions; requests and deductions are not bank receipts.', None,
            gap='No bank settlement or post-termination payment entitlement has been verified.', kind='model_assumption'))
    fields.append(_field('execution_and_entitlement', 'source-based local account calculation',
        'No live account, broker entitlement, execution or provider numerical parity is certified.', None,
        gap='Observed bar/mark risk and scale-invariant opportunities need separate deployment qualification.', kind='integration_boundary'))
    value = dict(version=VERSION, profile=asdict(profile), phase=phase, reviewed_at=REVIEWED_AT,
        provider_effective_at=None, fields=fields, status='UNVERIFIED', production_qualified=False,
        historical_policy='Capture this review with each report. Never refresh historical reports or infer rules for dates before this review.',
        interpretation='VERIFIED_DOCUMENT means published wording was checked; it does not certify model parity or a live account.')
    value['sha256'] = sha256(canonical(value).encode()).hexdigest()
    return value


def search_review(search):
    phase = 'evaluation' if search.mode == 'evaluation_optimization' else 'funded' if search.mode == 'funded_optimization' else None
    if phase is None:
        raise ValueError('Unknown phase for provider rule review.')
    profiles = {canonical(asdict(c.profile)):c.profile for c in search.candidates}
    return dict(version=VERSION, status='UNVERIFIED', production_qualified=False,
        profiles=[profile_review(profiles[key], phase) for key in sorted(profiles)])


def readiness(review):
    """Missing, tampered or unknown captured reviews cannot authorize deployment."""
    if not isinstance(review, dict) or review.get('version') != VERSION:
        return dict(status='UNVERIFIED', production_qualified=False, reasons=['missing_or_unknown_rule_review'])
    reasons = []
    for profile in review.get('profiles', []):
        unsigned = {k:v for k,v in profile.items() if k != 'sha256'}
        if sha256(canonical(unsigned).encode()).hexdigest() != profile.get('sha256'):
            reasons.append('rule_review_integrity')
        reasons.extend(f"{profile.get('phase')}:{profile.get('profile',{}).get('profile_id')}:{f['field']}" for f in profile.get('fields', []) if f.get('status') != 'VERIFIED_DOCUMENT')
    if not review.get('profiles'):
        reasons.append('missing_profile_review')
    return dict(status='UNVERIFIED', production_qualified=False, reasons=sorted(set(reasons)) or ['live_provider_parity_not_certified'])
