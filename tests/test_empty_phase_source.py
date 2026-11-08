"""Observed native no-trade windows are distinct from fabricated source data."""
import json
import pytest

from alphaquest.app import create_app
from alphaquest.prop.source import prepare_source
from research_fixtures import ResearchClient
from test_prop_phases import save_source


def test_empty_native_source_requires_internal_opt_in_and_conservation(tmp_path):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        source = save_source(client, green=100, days=2)
        assert source['summary']['trades_taken'] == 0
        runs = client.app.state.runs
        with pytest.raises(ValueError, match='Empty source'):
            prepare_source(runs, source['id'], '')
        snapshot, trades = prepare_source(runs, source['id'], '', allow_empty=True)
        assert trades == [] and snapshot['reconciliation']['source_count'] == 0
        assert set(snapshot['reconciliation']['source_totals'].values()) == {'0'}
        with pytest.raises(ValueError, match='Empty source'):
            prepare_source(runs, source['id'], '/tmp/not-an-excursion-export.csv', allow_empty=True)
        with runs.connect() as db:
            original = db.execute('SELECT manifest FROM runs WHERE id=?', (source['id'],)).fetchone()[0]
            value = json.loads(original); value['summary']['total_net_pnl'] = '1'
            db.execute('UPDATE runs SET manifest=? WHERE id=?', (json.dumps(value), source['id']))
        with pytest.raises(ValueError, match='totals differ'):
            prepare_source(runs, source['id'], '', allow_empty=True)
