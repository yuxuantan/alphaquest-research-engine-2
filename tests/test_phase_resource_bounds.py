"""Shared preview/source/reservation work limits include historical re-estimation."""
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from alphaquest.prop.funded_optimization import FundedHistoricalMean, parse_request
from alphaquest.prop.phase_search import validate_phase_work
from alphaquest.prop_api import FundedSearchRequest, phase_request


def search(count=2, horizon=10, **configuration):
    return SimpleNamespace(mode='funded_optimization', candidates=tuple(
        SimpleNamespace(simulation=SimpleNamespace(simulations=64)) for _ in range(count)),
        horizon_calendar_days=horizon, conservative_objective=FundedHistoricalMean(**configuration))


def test_combined_path_work_and_source_index_capture_are_counted():
    result = validate_phase_work(search(),60)
    assert result['funded_path_calendar_days'] == (2*64+2*200*64)*10
    assert result['historical_session_indices'] == 2*200*60
    assert validate_phase_work(search(),[60,80])['historical_session_indices'] == 200*140


def test_combined_candidate_refits_reject_even_when_each_candidate_is_bounded():
    value = search(count=2,horizon=2000)
    assert 200*64*2000 < 50_000_000
    with pytest.raises(ValueError,match='including historical refits'):validate_phase_work(value,60)


def test_combined_capture_rejects_before_large_job_and_validates_inventory_counts():
    with pytest.raises(ValueError,match='million session indices'):validate_phase_work(search(),3000)
    for count in ([True,2], [2], [-1,2]):
        with pytest.raises(ValueError,match='observed-session count'):validate_phase_work(search(),count)


def test_legacy_resource_bounds_and_unknown_phase_remain_strict():
    value=search();value.conservative_objective=None
    assert validate_phase_work(value)['funded_path_calendar_days']==1280
    value.mode='unknown'
    with pytest.raises(ValueError):validate_phase_work(value)


def test_public_funded_contract_retains_optional_configuration():
    from alphaquest.prop.phase_profiles import FundedProfile, rule_version
    raw = dict(mode='funded_optimization',source_backtest_id='a'*32,
        candidates=[dict(source={'source_backtest_id':'a'*32},
            profile=asdict(FundedProfile('apex-50k-eod',rule_version('apex-50k-eod'))),micros=3)],
        calendar=dict(start_dates=['2026-01-05'],coverage_end='2026-01-20'),
        horizon_calendar_days=10,receipt_delay_calendar_days=0,
        conservative_objective=asdict(FundedHistoricalMean()))
    public=FundedSearchRequest.model_validate(raw)
    parsed=parse_request(phase_request(public))
    assert parsed.conservative_objective==FundedHistoricalMean()
    public=FundedSearchRequest.model_validate({**raw,'conservative_objective':None})
    assert parse_request(phase_request(public)).conservative_objective is None
