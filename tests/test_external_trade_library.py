"""External provenance stays distinct in the existing strategy catalogue."""
from copy import deepcopy
from hashlib import sha256

from fastapi.testclient import TestClient

from alphaquest.app import create_app
from test_canonical_trades import envelope, raw
from test_research_workflow import history


def imported(client, document):
    response = client.post('/api/backtests/imports', params={'filename': 'SYNTHETIC-source.json'}, content=raw(document))
    assert response.status_code == 201, response.text
    return response.json()


def test_external_declared_dataset_hash_never_links_local_market_data(tmp_path):
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        response = client.post('/api/datasets', params=dict(filename='SYNTHETIC-local.csv', name='LOCAL MARKET BARS',
            source_timezone='America/Chicago', symbol='MNQ', tick_size='.25', point_value='2'), content=history())
        assert response.status_code == 201, response.text
        native = response.json()
        document = envelope()
        document['manifest']['dataset']['sha256'] = native['sha256']
        document['manifest']['strategy']['id'] = 'consecutive_green_hold'
        record = imported(client, document)
        before = {p: sha256(p.read_bytes()).hexdigest() for p in client.app.state.runs.root.rglob('*') if p.is_file()}
        groups = client.get('/api/strategies/consecutive_green_hold/datasets').json()['items']
        assert len(groups) == 1
        group = groups[0]
        assert group['source_kind'] == 'external_trade_export'
        assert group['available_dataset_id'] is None
        assert group['dataset']['id'] is None
        assert group['dataset']['name'] == 'SYNTHETIC'
        assert group['dataset']['row_count'] is None
        assert group['dataset']['full_range_available'] is False
        assert group['dataset']['start_date'] is None and group['dataset']['end_date'] is None
        assert group['dataset']['declared_start_utc'] == document['manifest']['coverage']['start_utc']
        assert group['native_replay'] is False
        rows = client.get(f'/api/strategies/consecutive_green_hold/datasets/{group["id"]}/backtests').json()
        assert rows['items'][0]['insample']['id'] == record['id']
        assert rows['items'][0]['insample']['metrics']['total_net_pnl'] == '4'
        assert rows['items'][0]['oos'] == []
        # The older instrument index also supports a null local dataset ID.
        instruments = client.get('/api/strategies/groups').json()['items']
        old = client.get('/api/strategies/groups/' + instruments[0]['id'] + '/backtests').json()['items'][0]
        assert old['dataset_id'] is None and old['source_kind'] == 'external_trade_export'
        assert client.get('/api/datasets').json() == [native]
        assert before == {p: sha256(p.read_bytes()).hexdigest() for p in before}


def test_external_phase_labels_preserved_without_parent_pairs_or_invented_legacy(tmp_path):
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        records = {}
        for phase in ('is', 'oos', 'unspecified'):
            document = envelope(); document['export_id'] += '-' + phase
            document['manifest']['research']['phase'] = phase
            records[phase] = imported(client, document)
        groups = client.get('/api/strategies/SYNTHETIC/datasets').json()['items']
        assert len(groups) == 1
        assert (groups[0]['reports'], groups[0]['is_reports'], groups[0]['oos_reports']) == (3, 1, 1)
        rows = client.get(f'/api/strategies/SYNTHETIC/datasets/{groups[0]["id"]}/backtests').json()['items']
        by_phase = {row['phase']: row for row in rows}
        assert by_phase['is']['insample']['id'] == records['is']['id']
        assert by_phase['is']['oos'] == []
        assert by_phase['oos']['insample'] is None
        assert by_phase['oos']['oos'][0]['id'] == records['oos']['id']
        assert by_phase['unspecified']['unclassified']['id'] == records['unspecified']['id']
        assert all(row['legacy'] is None for row in rows)
        listing = client.get('/api/strategies/library').json()['items']
        strategy = next(row for row in listing if row['id'] == 'SYNTHETIC')
        assert strategy['external_reports'] == strategy['reports'] == 3
        assert client.get('/api/datasets').json() == []


def test_external_contract_currency_and_unknown_data_identity_do_not_merge(tmp_path):
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        base = envelope()
        imported(client, base)
        for suffix, field, value in [('contract', 'contract', 'MNQM26'), ('currency', 'currency', 'EUR')]:
            document = deepcopy(base); document['export_id'] += '-' + suffix
            document['manifest']['instrument' if field == 'currency' else 'dataset'][field] = value
            imported(client, document)
        groups = client.get('/api/strategies/SYNTHETIC/datasets').json()['items']
        assert len(groups) == 3
        assert {group['currency'] for group in groups} == {'USD', 'EUR'}
        assert all(group['available_dataset_id'] is None for group in groups)
