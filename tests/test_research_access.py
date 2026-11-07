"""Independent access-boundary probes; no production source changes."""
from uuid import uuid4

from fastapi.testclient import TestClient

from alphaquest.app import create_app
import pytest


RAW=(b'Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol\n'
     b'01/05/2026,00:30,100,101,99,100,1,1,0\n')


def upload(client, zone):
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-timezone-alias.csv',
        name='SYNTHETIC timezone alias',symbol='MNQ',tick_size='.25',point_value='2',
        source_timezone=zone,disclosure='metadata_only'),content=RAW)
    assert response.status_code==201,response.text
    return response.json()


def reservation_request():
    return dict(request_id=uuid4().hex,first_session='2026-01-05',last_session='2026-01-05',
        market_domain='CME:NASDAQ100',external_access='declared_not_inspected')


def test_timezone_alias_must_not_disclose_reserved_identical_rows(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        original=upload(client,'UTC')
        body=reservation_request()
        response=client.post('/api/datasets/'+original['id']+'/research-reservations',json=body)
        assert response.status_code==201,response.text
        alias=upload(client,'Pacific/Kiritimati')
        assert alias['sha256']==original['sha256']
        assert alias['start']=='2026-01-04T10:30:00Z'
        response=client.get('/api/datasets/'+alias['id']+'/csv')
        assert response.status_code==409, 'Identical reserved raw observations were exposed under a shifted session: '+response.text


def test_prior_timezone_alias_access_must_preclude_clean_reservation(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        alias=upload(client,'Pacific/Kiritimati')
        assert client.get('/api/datasets/'+alias['id']+'/csv').status_code==200
        original=upload(client,'UTC')
        response=client.post('/api/datasets/'+original['id']+'/research-reservations/preview',json=reservation_request())
        assert response.status_code==200,response.text
        assert response.json()['access']['status']!='ELIGIBLE_UNDER_DECLARED_LOCAL_SCOPE', response.text


def test_protected_rows_reject_before_prepared_cache_hit(tmp_path):
    from alphaquest.prepared_data import prepare_data
    from alphaquest.research_folds import SessionDateRange
    from alphaquest.research import ResearchConflict
    class ForbiddenCache:
        def restore(self,*args):
            pytest.fail('Protected range reached cache restoration')
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        original=upload(client,'UTC')
        response=client.post('/api/datasets/'+original['id']+'/research-reservations',json=reservation_request())
        assert response.status_code==201,response.text
        with pytest.raises(ResearchConflict,match='protected final sessions'):
            prepare_data(client.app.state.store,original['id'],SessionDateRange.parse('2026-01-05','2026-01-05'),
                tmp_path/'should-not-exist.bin',cache=ForbiddenCache())
        assert not (tmp_path/'should-not-exist.bin').exists()


def test_metadata_inventory_does_not_leak_scope_into_later_reader(tmp_path):
    from alphaquest.backtest_data import read_selected_bars
    from alphaquest.research_folds import inventory_sessions,SessionDateRange
    from alphaquest.research import ResearchConflict
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        original=upload(client,'UTC')
        response=client.post('/api/datasets/'+original['id']+'/research-reservations',json=reservation_request())
        assert response.status_code==201,response.text
        inventory=inventory_sessions(client.app.state.store,original['id'],minimum_sessions=1)
        assert inventory['sessions']==['2026-01-05']
        assert not any(key in inventory for key in ('bars','prices','Open','Close'))
        with pytest.raises(ResearchConflict,match='protected final sessions'):
            with read_selected_bars(client.app.state.store,original['id'],SessionDateRange.parse('2026-01-05','2026-01-05')):
                pytest.fail('Metadata-only context leaked into a selected price reader')


def test_failed_started_reader_is_permanent_access(tmp_path):
    from alphaquest.backtest_data import read_bars
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        original=upload(client,'UTC')
        with pytest.raises(RuntimeError,match='deliberate consumer failure'):
            with read_bars(client.app.state.store,original['id']) as bars:
                assert next(bars).close==100
                raise RuntimeError('deliberate consumer failure')
        response=client.post('/api/datasets/'+original['id']+'/research-reservations/preview',json=reservation_request())
        assert response.status_code==200,response.text
        assert response.json()['access']['status']=='PREVIOUSLY_ACCESSED'


def test_existing_cli_reader_cannot_bypass_application_reservation(tmp_path):
    import subprocess,sys
    database=tmp_path/'datasets.sqlite3'
    with TestClient(create_app(database)) as client:
        original=upload(client,'UTC')
        response=client.post('/api/datasets/'+original['id']+'/research-reservations',json=reservation_request())
        assert response.status_code==201,response.text
        result=subprocess.run([sys.executable,'-m','alphaquest.backtest_data','--database',str(database),
            '--dataset-id',original['id'],'--limit','1'],capture_output=True,text=True,timeout=20)
        assert result.returncode!=0 and 'protected final sessions' in result.stderr, result.stdout+result.stderr
