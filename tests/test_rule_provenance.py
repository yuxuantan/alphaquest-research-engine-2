"""Current document review cannot certify a historical model or live account."""
from copy import deepcopy
from dataclasses import replace

import pytest

from alphaquest.prop.phase_profiles import EvaluationProfile, FundedProfile, rule_version
from alphaquest.prop.rule_provenance import profile_review, readiness, VERSION
from alphaquest.prop.native_engine import Rules
from alphaquest.prop.lucid_engine import Rules as LucidRules


def profile(firm, phase):
    version = rule_version(firm)
    return EvaluationProfile(firm, version, '30', '0') if phase == 'evaluation' else FundedProfile(firm, version)


@pytest.mark.parametrize('firm', ['apex-50k-eod', 'lucidflex-50k'])
@pytest.mark.parametrize('phase', ['evaluation', 'funded'])
def test_complete_dated_review_retained_gaps_and_phase_independence(firm, phase):
    review = profile_review(profile(firm, phase), phase)
    fields = {f['field']:f for f in review['fields']}
    assert review['provider_effective_at'] is None
    assert any(f['status'] == 'VERIFIED_DOCUMENT' for f in fields.values())
    assert all(f['gap'] for f in fields.values() if f['status'] == 'UNVERIFIED')
    assert all(f['source_url'].startswith('https://') for f in fields.values() if f['status'] == 'VERIFIED_DOCUMENT')
    if phase == 'funded':
        assert not {'activation_fee', 'evaluation_purchase_price', 'retry_policy'} & fields.keys()
    else:
        assert 'payout_amount' not in fields and 'receipt_and_termination' not in fields
    gate = readiness(dict(version=VERSION, profiles=[review]))
    assert gate['status'] == 'UNVERIFIED' and gate['production_qualified'] is False
    assert gate['reasons']
    damaged = deepcopy(review); damaged['fields'][0]['model_value'] = 'different account'
    assert 'rule_review_integrity' in readiness(dict(version=VERSION, profiles=[damaged]))['reasons']


def test_document_review_does_not_silently_change_preserved_rules():
    apex = Rules(); lucid = LucidRules()
    assert apex.inactivity_window == 21 and apex.consistency == .5
    assert apex.ladder == (1500, 1500, 2000, 2500, 2500, 3000)
    assert lucid.inactivity_calendar_days == 30
    review = profile_review(profile('apex-50k-eod', 'funded'), 'funded')
    fields = {f['field']:f for f in review['fields']}
    assert fields['inactivity']['model_value']['session_window'] == apex.inactivity_window
    assert fields['payout_qualification']['model_value']['best_day_fraction_at_most'] == apex.consistency
    assert fields['payout_policy']['model_value']['caps'] == list(apex.ladder)
    assert all(fields[k]['status'] == 'UNVERIFIED' for k in ('inactivity','payout_qualification','payout_policy'))


def test_unknown_historical_review_or_wrong_phase_never_recertified():
    p = profile('apex-50k-eod', 'evaluation')
    with pytest.raises(ValueError, match='historical'):
        profile_review(replace(p, rule_version='old-snapshot'), 'evaluation')
    with pytest.raises(ValueError, match='matching explicit phase'):
        profile_review(p, 'funded')
    for value in (None, {}, dict(version='old-snapshot', production_qualified=True)):
        assert readiness(value)['production_qualified'] is False
