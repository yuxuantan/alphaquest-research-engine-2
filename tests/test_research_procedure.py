"""Independent terminal window/outcome gates; no phase calculation mocks."""
from datetime import date,timedelta
from decimal import Decimal

import pytest

from alphaquest.research_folds import FoldSettings
from alphaquest.research_procedure import FinalEvidenceRules,terminal_plan,assess_final_outcomes


def days(n):return [(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(n)]


@pytest.mark.parametrize('mode,expected',[('rolling',days(14)[4:12]),('expanding',days(14)[:12])])
def test_terminal_uses_recent_complete_train_with_declared_gap(mode,expected):
    settings=FoldSettings(outer_train_sessions=8,outer_test_sessions=2,inner_train_sessions=2,
        inner_validation_sessions=2,minimum_inner_folds=2,minimum_outer_folds=2,purge_sessions=1,embargo_sessions=1,mode=mode)
    value=terminal_plan(days(14),days(16)[14:],settings,origin_session=days(14)[0])
    assert value['train']['sessions']==expected
    assert value['excluded']==dict(purge_sessions=[days(14)[12]],embargo_sessions=[days(14)[13]])
    assert value['test']['sessions']==days(16)[14:]
    assert 'index' not in value and 'outer_fold_index' not in value
    assert all(inner['validation']['last_session']<value['test']['first_session'] for inner in value['inner'])
    with pytest.raises(ValueError,match='origin'):
        terminal_plan(days(14),days(16)[14:],settings,origin_session=days(14)[1])
    with pytest.raises(ValueError,match='cannot enter'):
        terminal_plan(days(14),days(14)[-2:],settings,origin_session=days(14)[0])


@pytest.mark.parametrize('bad',[True,3,{},'NaN','Infinity','-1','not money'])
def test_optional_final_receipt_threshold_rejects_malformed(bad):
    with pytest.raises(ValueError):FinalEvidenceRules(minimum_funded_trader_receipts=bad)


def test_final_outcome_gates_are_explicit_per_member_without_reselection():
    replay=dict(status='complete',items=[dict(phase='evaluation',candidate_id='a',frozen_package_sha256='a'*64,
        result=dict(acquisition_completed=False,censored=True)),dict(phase='funded',candidate_id='b',frozen_package_sha256='b'*64,
        result=dict(cash_received='0.25'))])
    assert assess_final_outcomes(replay,FinalEvidenceRules())['status']=='COMPLETE_UNRESELECTED_ASSESSMENT'
    result=assess_final_outcomes(replay,FinalEvidenceRules(require_evaluation_completed_acquisition=True,minimum_funded_trader_receipts='0.250000000000000001'))
    assert result['status']=='FAILED_VERIFICATION_CRITERIA'
    assert [row['candidate_id'] for row in result['members']]==['a','b']
    assert all(row['failures'] for row in result['members'])
    assert result['no_reselection']
