"""Malformed persisted timezone metadata cannot reach price or cache access."""
from copy import deepcopy

import pytest

from test_backtest_api import client, save_fixture
from alphaquest.backtest_data import DateRange, DatasetReadError, read_selected_bars
from alphaquest.prepared_data import prepare_data
from alphaquest.research_access import coverage
from alphaquest.research_folds import SessionDateRange


@pytest.mark.parametrize('zone', [None, 42, 'Not/AZone', 'missing'], ids=['null','nonstring','unknown','missing'])
@pytest.mark.parametrize('window', ['full','civil','session'])
@pytest.mark.parametrize('reader', ['prepared','selected'])
def test_invalid_timezone_rejects_before_any_price_or_cache_access(client, tmp_path, monkeypatch, zone, window, reader):
    dataset=save_fixture(client); source=client.app.state.store
    assert source.research_access is not None
    malformed=deepcopy(dataset)
    if zone=='missing': malformed.pop('source_timezone')
    else: malformed['source_timezone']=zone
    monkeypatch.setattr(source,'get',lambda _:deepcopy(malformed))
    accessed=[]
    def forbidden(*args,**kwargs):
        accessed.append(True)
        pytest.fail('Invalid saved timezone reached price bytes or derived-cache access')
    monkeypatch.setattr(source,'open_snapshot',forbidden,raising=False)
    monkeypatch.setattr(source,'iter_csv',forbidden)
    monkeypatch.setattr(client.app.state.runs.replay_cache,'restore',forbidden)
    dates=(None if window=='full' else
        DateRange.parse('2026-01-05','2026-01-05') if window=='civil' else
        SessionDateRange.parse('2026-01-05','2026-01-05'))
    output=tmp_path/'forbidden-bars.bin'
    with pytest.raises(DatasetReadError,match='saved source timezone'):
        if reader=='prepared':
            prepare_data(source,dataset['id'],dates,output,cache=client.app.state.runs.replay_cache)
        else:
            with read_selected_bars(source,dataset['id'],dates):
                pytest.fail('Malformed source was yielded to a consumer')
    assert not accessed and not output.exists()


@pytest.mark.parametrize('zone', [None, 42, 'Not/AZone', 'missing'], ids=['null','nonstring','unknown','missing'])
def test_full_access_coverage_validates_timezone_without_date_range(zone):
    dataset=dict(start='2026-01-05T00:00:00Z',end='2026-01-06T00:00:00Z')
    if zone!='missing':dataset['source_timezone']=zone
    with pytest.raises(DatasetReadError,match='saved source timezone'):
        coverage(dataset)
