import json
from pathlib import Path
import pytest
from test_backtest_api import client,body,save_fixture
from alphaquest.replay_cache import ReplayCache
from alphaquest.prepared_data import prepare_data
from alphaquest.backtest_data import DateRange,DatasetReadError


def test_cache_reuses_exact_bars_and_rejects_poisoned_copy_and_changed_source(client,tmp_path,monkeypatch):
    source=client.app.state.store;dataset=save_fixture(client);cache=client.app.state.runs.replay_cache
    paths=[tmp_path/f'bars-{i}.bin' for i in range(4)]
    first=prepare_data(source,dataset['id'],None,paths[0],cache=cache)
    assert not first.cache_hit
    from alphaquest import backtest_data
    original=backtest_data._iter_bars
    def no_parse(*args):
        raise AssertionError('unexpected parse')
        yield
    monkeypatch.setattr(backtest_data,'_iter_bars',no_parse)
    second=prepare_data(source,dataset['id'],None,paths[1],cache=cache)
    assert second.cache_hit and paths[0].read_bytes()==paths[1].read_bytes()
    monkeypatch.setattr(backtest_data,'_iter_bars',original)
    from alphaquest.database import connection
    with connection(cache.path) as db:name=db.execute('SELECT name FROM streams WHERE key=?',(first.cache_key,)).fetchone()[0]
    (cache.root/name).write_bytes(b'not a pickle; must never decode')
    third=prepare_data(source,dataset['id'],None,paths[2],cache=cache)
    assert not third.cache_hit and paths[0].read_bytes()==paths[2].read_bytes()
    # A cached prior parse must never mask a changed source file.
    monkeypatch.setattr(source,'iter_csv',lambda _:iter([b'changed']))
    monkeypatch.setattr(source,'open_snapshot',None,raising=False)
    with pytest.raises(DatasetReadError,match='bytes do not match'):
        prepare_data(source,dataset['id'],None,paths[3],cache=cache)


def test_cache_bound_eviction_and_parameter_namespace(tmp_path):
    cache=ReplayCache(tmp_path/'cache',limit=6)
    a=tmp_path/'a';a.write_bytes(b'abcd')
    cache.save('a',a,{'kind':'bars'});cache.save('b',a,{'kind':'feature'})
    assert cache.restore('a',tmp_path/'miss') is None
    assert cache.restore('b',tmp_path/'hit')=={'kind':'feature'}
    assert sum(p.stat().st_size for p in cache.root.glob('*.bin'))<=6


def test_normal_backtest_warm_cache_is_durable_and_csv_exact(client):
    dataset=save_fixture(client);request=body(dataset['id'])
    reports=[];diagnostics=[]
    for use in (False,True,True):
        response=client.post('/api/backtests',json={**request,'reuse_prepared':use})
        assert response.status_code==201,response.text
        record=response.json();reports.append(record)
        diagnostics.append(client.get('/api/backtests/'+record['id']+'/performance').json())
    assert 'source_cache_hit' not in diagnostics[0]['details']
    assert diagnostics[1]['details']['source_cache_hit'] is False
    assert diagnostics[2]['details']['source_cache_hit'] is True
    for report in reports[1:]:
        assert report['summary']==reports[0]['summary']
        for kind in ('trades','equity'):
            assert client.get('/api/backtests/'+report['id']+'/exports/'+kind).content==client.get('/api/backtests/'+reports[0]['id']+'/exports/'+kind).content
    (client.app.state.runs.root.parent/'prepared-cache-verification.json').write_text(json.dumps(dict(ids=[r['id'] for r in reports],diagnostics=diagnostics,all_csv_equal=True),indent=2))


def test_declared_features_survive_new_workspace_without_running_builders(client,tmp_path):
    from alphaquest.strategies.registry import get_strategy
    from alphaquest.strategy_features import prepare_features
    from dataclasses import replace,asdict
    from decimal import Decimal
    from types import SimpleNamespace
    dataset=save_fixture(client);cache=client.app.state.runs.replay_cache
    prepared=prepare_data(client.app.state.store,dataset['id'],None,tmp_path/'bars.bin',cache=cache)
    definition=get_strategy('vwap_pullback_risk_sizing')
    values={k:str(v) if isinstance(v,Decimal) else v for k,v in asdict(definition.module.Parameters()).items()}
    cold=tmp_path/'cold';warm=tmp_path/'warm';cold.mkdir();warm.mkdir()
    first=prepare_features(definition,prepared,[values],cold,workers=0,cache=cache)
    def forbidden(*args):raise AssertionError('pure builder ran on a hit')
    altered=replace(definition,acceleration=SimpleNamespace(features=tuple(replace(f,build=forbidden) for f in definition.acceleration.features)))
    second=prepare_features(altered,prepared,[values],warm,workers=0,cache=cache)
    assert len(first)==len(second)==3
    assert {k:p.read_bytes() for k,p in first.items()}=={k:p.read_bytes() for k,p in second.items()}


def test_cold_and_warm_preparation_read_original_bytes_once(client,tmp_path,monkeypatch):
    dataset=save_fixture(client);source=client.app.state.store
    original=source.iter_csv;calls=[]
    def read(id):
        calls.append(id)
        yield from original(id)
    monkeypatch.setattr(source,'iter_csv',read)
    for i in range(2):
        prepared=prepare_data(source,dataset['id'],None,tmp_path/f'bars-{i}.bin',cache=client.app.state.runs.replay_cache)
        assert prepared.cache_hit is bool(i)
        assert len(calls)==i+1


@pytest.mark.parametrize('zone',[None,'Not/AZone'])
def test_invalid_saved_source_timezone_rejects_before_cache_lookup(client,tmp_path,monkeypatch,zone):
    dataset=save_fixture(client);source=client.app.state.store
    monkeypatch.setattr(source,'get',lambda _:dict(dataset,source_timezone=zone))
    with pytest.raises(DatasetReadError,match='timezone'):
        prepare_data(source,dataset['id'],None,tmp_path/'bars.bin',cache=client.app.state.runs.replay_cache)
