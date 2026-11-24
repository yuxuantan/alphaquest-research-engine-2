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


def test_unknown_phase_remains_strict():
    value=search();value.conservative_objective=None
    assert validate_phase_work(value)['funded_path_calendar_days']==1280
    value.mode='unknown'
    with pytest.raises(ValueError):validate_phase_work(value)


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_plain_saved_paths_are_not_capped_by_size_count_or_total_work(phase):
    candidate=SimpleNamespace(simulation=SimpleNamespace(simulations=20000),
        profile=SimpleNamespace(profile_id='lucidflex-50k'))
    value=SimpleNamespace(mode=phase+'_optimization',candidates=(candidate,)*40,
        horizon_calendar_days=365,conservative_objective=None)
    estimate=validate_phase_work(value)
    assert estimate['estimated_capture_bytes']>100*1024*1024
    if phase=='funded':assert estimate['funded_path_calendar_days']==292000000


def test_large_saved_report_can_publish_without_changing_legacy_bound(tmp_path):
    import json
    from zipfile import ZipFile
    from alphaquest.prop.store import seal_report
    size=129*1024*1024
    with (tmp_path/'paths.json').open('wb') as stream:stream.truncate(size)
    with pytest.raises(ValueError,match='128 MiB'):seal_report(tmp_path,{},'id','created')
    seal_report(tmp_path,{},'id','created',size_limit_bytes=None)
    report=json.loads((tmp_path/'report.json').read_text())
    assert report['files']['paths.json']['bytes']==size
    with ZipFile(tmp_path/'analysis.zip') as archive:assert archive.getinfo('paths.json').file_size==size


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
