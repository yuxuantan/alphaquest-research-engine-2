"""Strict declaration and honest modeled-calendar metadata."""
from copy import deepcopy
from datetime import date
import pytest
from alphaquest.prop.native_replay import NativeForecastRequest


def declaration(**changes):
    return dict(model='observed_contiguous_blocks_with_prior_prefix_v1', simulations=4,
        seed=1729, block_sessions=1, horizon_calendar_days=9, capture_paths=2,
        calendar=dict(start_dates=['2026-01-19'], coverage_end='2026-01-29', closures=[],
            timezone='America/Chicago', version='explicit-synthetic-weekdays-v1'), **changes)


def test_calendar_has_modeled_provenance_and_shared_close_semantics():
    body = declaration(early_closes={'2026-01-23':'12:15'})
    body['calendar']['closures'] = ['2026-01-26']
    request = NativeForecastRequest(**body)
    calendar = request.target_calendar()
    meta = calendar.metadata()
    assert meta['kind'] == 'modeled' and meta['observed'] is False and meta['exchange_verified'] is False
    assert 'file' not in meta and len(meta['sha256']) == 64
    assert calendar.plan(date(2026,1,23)).cutoff.strftime('%H:%M') == '12:10'
    assert calendar.plan(date(2026,1,26)).close is None
    assert calendar.plan(date(2026,1,27)).close.strftime('%H:%M') == '16:00'


@pytest.mark.parametrize('changes', [dict(simulations=True),dict(simulations=0),dict(simulations=513),
    dict(block_sessions=True),dict(block_sessions=3),dict(seed=-1),dict(seed=2**32),
    dict(capture_paths=5),dict(horizon_calendar_days=True),dict(horizon_calendar_days=0),
    dict(early_closes={'2026-01-23':'16:00'}),dict(early_closes={'2026-01-24':'12:15'}),
    dict(early_closes={'2026-02-02':'12:15'}),dict(early_closes={'20260123':'12:15'}),
    dict(mode='native_optimization')])
def test_forecast_contract_rejects_ambiguous_or_unsupported_inputs(changes):
    body = declaration(); body.update(changes)
    with pytest.raises(ValueError): NativeForecastRequest(**body)


def test_total_paths_equal_start_strata_and_explicit_calendar_identity():
    body = declaration(); body['calendar']['start_dates'] = ['2026-01-19','2026-01-20','2026-01-21']
    body['calendar']['coverage_end'] = '2026-01-31'
    with pytest.raises(ValueError,match='equal number'): NativeForecastRequest(**body)
    body['simulations'] = 6
    request = NativeForecastRequest(**body)
    assert request.simulations == 6
    del body['calendar']['version']
    with pytest.raises(ValueError,match='explicit saved version'): NativeForecastRequest(**body)


def test_out_of_range_horizon_is_validation_error():
    body = declaration(); body['calendar'].update(start_dates=['9999-12-31'],coverage_end='9999-12-31')
    with pytest.raises(ValueError,match='supported calendar dates'): NativeForecastRequest(**body)


@pytest.mark.parametrize('field,value', [(field,value) for field in ['start_dates','closures']
    for value in [{'2026-01-19':{'ignored':'nested fields'}},'2026-01-19',[True],[]]
    if field!='closures' or value!=[]])
def test_calendar_date_containers_are_strict_arrays(field,value):
    body=declaration();body['calendar'][field]=value
    with pytest.raises(ValueError):NativeForecastRequest(**body)


def test_report_publication_size_includes_embedded_json(tmp_path,monkeypatch):
    from alphaquest.prop import store
    # A tiny object can advertise its encoded byte count without allocating a
    # 128 MiB fixture. The actual gate must reject before writing/archiving.
    class OversizedEncoding:
        def __len__(self): return 128*1024*1024+1
    class OversizedReport(str):
        def encode(self,*args,**kwargs): return OversizedEncoding()
    monkeypatch.setattr(store,'canonical',lambda value:OversizedReport('{}'))
    with pytest.raises(ValueError,match='embedded report exceed'):
        store.seal_report(tmp_path,{},'a'*32,'2026-01-26T00:00:00Z')
    assert not (tmp_path/'report.json').exists() and not (tmp_path/'analysis.zip').exists()
