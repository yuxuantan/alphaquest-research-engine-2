from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import pytest

from alphaquest.forward_contracts import FundedObservationPlan, AccountCoverage
from alphaquest.forward_comparison import boundary, check_observation_plan, compare_observation, iso
from alphaquest.forward_reconcile import stamp
from tests.test_forward_comparison import comparison_fixture

from tests.forward_comparison_fixtures import prospective_observation, coverage_events_for_binding

@pytest.mark.parametrize('seal,wall', [
    ('2026-11-10T23:59:00Z', '2026-11-10T23:59:00Z'),
    ('2027-03-01T00:00:00Z', '2027-03-01T00:00:00Z'),
    ('2027-11-01T00:00:00Z', '2027-11-01T00:00:00Z'),
    ('2030-12-31T23:59:59Z', '2027-11-01T00:00:00Z'),
    ('2026-11-08T00:00:00Z', '2031-06-09T23:59:59Z'),
])
def test_prospective_synthetic_scope_preserves_original_model_and_cash(seal, wall):
    declaration, policy, original_binding, _, _, _ = comparison_fixture()
    policy['policy_selection_sealed_at_utc'] = seal
    application = {'result': {'economic_selection': {'sealed_at_utc': seal}}}
    original_package = deepcopy(policy['package'])
    plan, created = prospective_observation(application, policy['package'], wall_clock_utc=wall)
    assert stamp(created) > max(stamp(seal), stamp(wall))
    checked = check_observation_plan(FundedObservationPlan.model_validate(plan), policy, declared_at_utc=created)
    start, end = boundary(plan['first_session'], plan['cutoff_date_exclusive'])
    assert start > stamp(created)
    assert checked['relative_calendar_pattern'] == original_binding['relative_calendar_pattern']
    assert checked['original_window']['first_session'] == '2026-01-27'
    assert policy['package'] == original_package
    events, asof = coverage_events_for_binding(checked, complete=True)
    AccountCoverage.model_validate(events[-1])
    assert stamp(events[0]['event_time_utc']) == start
    assert stamp(events[-1]['event_time_utc']) == end
    records = [dict(sequence=i, event=e, received_at_utc=iso(end+timedelta(seconds=1))) for i,e in enumerate(events,1)]
    result = compare_observation(declaration, policy, checked, records, asof, monitor_created_at_utc=created, conformance={'status':'MATCH'})
    assert result['status'] == 'SYNTHETIC_SCOPE_COMPARISON', result['reasons']
    assert Decimal(result['metrics']['expected_trader_receipts']) == 1500
    assert Decimal(result['metrics']['observed_trader_receipts']) == 50
    assert Decimal(result['metrics']['observed_minus_expected']) == -1450
    assert not result['production_qualified']


def test_original_fixed_creation_rejects_later_real_seal():
    _, policy, binding, _, _, created = comparison_fixture()
    policy['policy_selection_sealed_at_utc'] = '2026-11-10T00:00:00Z'
    with pytest.raises(ValueError, match='sealed before'):
        check_observation_plan(FundedObservationPlan.model_validate(binding['plan']), policy, declared_at_utc=created)
