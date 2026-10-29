"""Independent arithmetic, provenance, durability and research-boundary checks."""

import csv
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.execution import execute
from alphaquest.market_benchmark import BenchmarkSettings, MarketBenchmark, comparison_preview
from alphaquest.reporting import generate_report
from alphaquest.strategy import Bar, CloseIntent, EntryIntent, ExecutionConfig


FIXTURES = Path(__file__).parent / 'fixtures/market_benchmark'
EXPECTED = json.loads((FIXTURES / 'expected.json').read_text())
SPLIT = dict(mode='dates', is_start='2026-01-05', is_end='2026-01-06', oos_start='2026-01-07', oos_end='2026-01-08')


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        yield client


def save(client):
    response = client.post('/api/datasets', params=dict(filename='SYNTHETIC-holding-IS-OOS.csv', name='SYNTHETIC holding comparison', source_timezone='UTC', tick_size='.25', point_value='20', symbol='SYNTHETIC'), content=(FIXTURES / 'SYNTHETIC-holding-IS-OOS.csv').read_bytes())
    assert response.status_code == 201, response.text
    return response.json()


def request_body(dataset, contracts=1):
    return dict(dataset_id=dataset['id'], strategy_id='consecutive_green_hold', strategy_parameters=dict(green_bar_count=1, hold_minutes=2, contracts=1), execution_settings=EXPECTED['settings'], sample_split=SPLIT, market_benchmark=dict(contracts=contracts), reuse_results=False)


def start(client, contracts=1):
    dataset = save(client)
    response = client.post('/api/backtests', json=request_body(dataset, contracts))
    assert response.status_code == 201, response.text
    return dataset, response.json()


def test_hand_calculated_equity_drawdowns_and_costs(client):
    dataset, run = start(client)
    base = f"/api/backtests/{run['id']}"
    result = client.get(base + '/market-benchmark').json()
    wanted = EXPECTED['is']
    for name in ('strategy', 'holding'):
        account = result['accounts'][name]
        assert Decimal(account['net_pnl']) == Decimal(wanted[name + '_net_pnl'])
        assert Decimal(account['max_drawdown_amount']) == Decimal(wanted[name + '_max_drawdown'])
        assert [Decimal(p[name + '_equity']) for p in result['chart']['items']] == list(map(Decimal, wanted[name + '_equity']))
        assert Decimal(account['total_commissions']) == 2
        assert Decimal(account['total_slippage_cost']) == 10
    assert Decimal(result['accounts']['holding']['return_pct']) == Decimal('1.88')
    assert Decimal(result['accounts']['holding']['max_drawdown_pct']) == Decimal('22000') / Decimal('10014')
    assert Decimal(run['summary']['max_drawdown_amount']) == 0  # Old trade-close metric remains distinct.
    assert Decimal(result['excess_net_pnl']) == -20
    assert result['observed_bar_count'] == 4  # 1000+ OOS prices were never read into IS.
    assert result['source']['dataset']['sha256'] == dataset['sha256']
    assert result['source']['research']['phase'] == 'is'
    assert result['source']['selection']['row_count'] == 4
    assert result['executable_futures_performance'] == 'unverified'
    assert result['source_checks']['roll_prices_and_costs'] == 'not recorded'
    assert Decimal(result['monthly'][0]['holding_net_pnl']) == 188
    assert result['yearly'][0]['holding_net_pnl'] == result['monthly'][0]['holding_net_pnl']
    assert Decimal(result['holding_trade']['entry_fill_price']) == Decimal('100.25')
    assert Decimal(result['holding_trade']['exit_fill_price']) == Decimal('109.75')


def test_oos_freezes_quantity_detail_preserves_it_and_no_read_replay(client, monkeypatch):
    dataset, run = start(client, contracts=2)
    base = f"/api/backtests/{run['id']}"
    result = client.get(base + '/market-benchmark').json()
    assert Decimal(result['accounts']['holding']['net_pnl']) == 376
    detail = client.post(base + '/detailed')
    assert detail.status_code == 201, detail.text
    assert detail.json()['market_benchmark']['settings'] == {'contracts': 2}
    assert client.get('/api/backtests/' + detail.json()['id'] + '/market-benchmark').json()['accounts'] == result['accounts']
    response = client.post(base + '/oos', json=dict(request_id=str(uuid4()), market_benchmark=dict(contracts=9)))
    assert response.status_code == 422
    response = client.post(base + '/oos', json=dict(request_id=str(uuid4())))
    assert response.status_code == 201, response.text
    oos = response.json()
    comparison = client.get('/api/backtests/' + oos['id'] + '/market-benchmark').json()
    assert comparison['settings'] == {'contracts': 2}
    assert comparison['source']['research']['phase'] == 'oos'
    assert comparison['source']['research']['parent_run_id'] == run['id']
    assert comparison['observed_bar_count'] == 4
    assert Decimal(comparison['accounts']['holding']['net_pnl']) == 776
    root = client.app.state.runs.root / run['id']
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    monkeypatch.setattr('alphaquest.backtest_api.execute', lambda *a, **kw: pytest.fail('Reopening must not replay a strategy'))
    monkeypatch.setattr(client.app.state.store, 'iter_csv', lambda *a, **kw: pytest.fail('Reopening must not read source prices'))
    assert client.delete('/api/datasets/' + dataset['id']).status_code == 204
    assert client.get(base + '/market-benchmark').json() == result
    for kind, name in [('market_benchmark', 'market_benchmark.json'), ('market_equity', 'market_equity.csv')]:
        download = client.get(base + '/exports/' + kind)
        assert download.status_code == 200
        assert download.content == before[name]
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


@pytest.mark.parametrize('quantity', [True, False, 0, -1, 1.0, '2', 9007199254740992])
def test_invalid_quantity_publishes_nothing(client, quantity):
    dataset = save(client)
    assert client.post('/api/backtests', json=request_body(dataset, quantity)).status_code == 422
    assert client.get('/api/backtests').json()['total'] == 0


@pytest.mark.parametrize('name,kind', [('market_equity.csv', 'market_equity'), ('market_benchmark.json', 'market_benchmark')])
def test_corruption_is_rejected_without_recalculation(client, name, kind):
    _, run = start(client)
    folder = client.app.state.runs.root / run['id']
    path = folder / name
    path.write_bytes(path.read_bytes() + b'\n')
    base = f"/api/backtests/{run['id']}"
    assert client.get(base + '/market-benchmark').status_code == 500
    assert client.get(base + '/exports/' + kind).status_code == 500
    assert client.get(base + '/trades').status_code == 200


def test_legacy_unavailable_and_chart_request_boundaries(client):
    _, run = start(client)
    with client.app.state.runs.connect() as db:
        record = json.loads(db.execute('SELECT manifest FROM runs WHERE id=?', (run['id'],)).fetchone()[0])
        record.pop('market_benchmark')
        db.execute('UPDATE runs SET manifest=? WHERE id=?', (json.dumps(record), run['id']))
    root = client.app.state.runs.root / run['id']
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    base = f"/api/backtests/{run['id']}"
    assert 'predates' in client.get(base + '/market-benchmark').json()['unavailable']
    assert client.get(base + '/exports/market_benchmark').status_code == 404
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}
    for limit in (0, 15, 2001, 'bad'):
        assert client.get(base + '/market-benchmark?max_points=' + str(limit)).status_code == 422
    assert client.get('/api/backtests/' + 'a' * 32 + '/market-benchmark').status_code == 404


class EnterThenHold:
    def __init__(self, side='long', timing='same_close', quantity=1):
        self.side, self.timing, self.quantity = side, timing, quantity

    def on_bar(self, bar, position):
        if bar.bar_number == 1:
            return EntryIntent(self.quantity, 'test', side=self.side, timing=self.timing)

    def on_finish(self, bar, position):
        return CloseIntent('end') if position else None


def direct_report(tmp_path, prices, strategy=None, initial='10000', settings=None):
    config = ExecutionConfig(Decimal(initial), Decimal('.25'), Decimal('20'), 1, Decimal('1'))
    bars = []
    for i, (opening, close) in enumerate(prices, 1):
        opening, close = Decimal(str(opening)), Decimal(str(close))
        bars.append(Bar(i, datetime(2026, 1, 5, 10, tzinfo=timezone.utc) + timedelta(minutes=i - 1), '', '', opening, max(opening, close), min(opening, close), close, Decimal(0), Decimal(0), Decimal(0), ()))
    metadata = dict(dataset=dict(source_timezone='UTC'), instrument={}, selection={}, strategy={})
    recorder = MarketBenchmark(config, settings, metadata, len(bars))
    events = execute(bars, strategy or EnterThenHold(), config, observe_bar=recorder.set_bar)
    manifest = generate_report(events, tmp_path / 'report', config, expected_bar_count=len(bars), market_benchmark=recorder)
    return manifest, json.loads((tmp_path / 'report/market_benchmark.json').read_text())


@pytest.mark.parametrize('prices,net', [([(100, 100), (100, 90)], '-212'), ([(100, 100), (100, 100)], '-12'), ([(100, 110)], '188')])
def test_falling_flat_and_single_bar_both_fill_costs(tmp_path, prices, net):
    _, result = direct_report(tmp_path, prices)
    assert Decimal(result['accounts']['holding']['net_pnl']) == Decimal(net)


def test_next_open_short_quantity_and_nonpositive_equity(tmp_path):
    manifest, result = direct_report(tmp_path, [(100, 100), (95, 95), (95, 90)], EnterThenHold('short', 'next_open', 3), initial='100')
    assert Decimal(manifest['summary']['total_net_pnl']) == 264  # (94.75 - 90.25) * 20 * 3 - 6
    assert Decimal(result['accounts']['strategy']['net_pnl']) == 264
    assert result['accounts']['strategy']['max_contracts'] == 3
    assert result['accounts']['strategy']['short_trades'] == 1
    assert result['accounts']['holding']['nonpositive_equity'] is True
    assert Decimal(result['accounts']['holding']['minimum_equity']) == -112


def test_zero_trades_compares_to_market_instead_of_omitting_it(tmp_path):
    class Flat:
        def on_bar(self, *a): pass
        def on_finish(self, *a): pass
    _, result = direct_report(tmp_path, [(100, 100), (100, 110)], Flat())
    assert Decimal(result['accounts']['strategy']['net_pnl']) == 0
    assert Decimal(result['accounts']['strategy']['time_in_market_pct']) == 0
    assert Decimal(result['excess_net_pnl']) == -188


def test_streamed_preview_keeps_extremes_of_all_three_series(tmp_path):
    total = 10001
    from alphaquest.market_benchmark import FIELDS
    path = tmp_path / 'market_equity.csv'
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for i in range(total):
            values = {key: '0' for key in FIELDS}
            values.update(bar_number=i, timestamp_utc='', strategy_equity='100', holding_equity='100', excess_net_pnl='0')
            if i == 50: values.update(strategy_equity='120', holding_equity='130', excess_net_pnl='-10')
            if i == 51: values.update(strategy_equity='80', holding_equity='70', excess_net_pnl='10')
            if i == 52: values.update(strategy_equity='119', holding_equity='71', excess_net_pnl='48')
            if i == 53: values.update(strategy_equity='81', holding_equity='129', excess_net_pnl='-48')
            writer.writerow(values)
    descriptor = dict(observed_bar_count=total - 1, equity_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    for limit in (16, 17, 1000, 2000):
        preview = comparison_preview(tmp_path, descriptor, limit)
        ordinals = [p['bar_number'] for p in preview['items']]
        assert len(ordinals) <= limit
        assert ordinals == sorted(set(ordinals))
        assert {0, 50, 51, 52, 53, total - 1} <= set(ordinals)


def test_quantity_affects_reuse_and_corrupt_market_files_invalidate_reuse(client):
    dataset = save(client)
    body = dict(request_body(dataset), reuse_results=True)
    first = client.post('/api/backtests', json=body)
    assert first.status_code == 201
    second = client.post('/api/backtests', json=body)
    assert second.status_code == 200 and second.json()['id'] == first.json()['id']
    changed = client.post('/api/backtests', json=dict(body, market_benchmark=dict(contracts=2)))
    assert changed.status_code == 201 and changed.json()['id'] != first.json()['id']
    assert changed.json()['market_benchmark']['settings'] == {'contracts': 2}
    folder = client.app.state.runs.root / first.json()['id']
    (folder / 'market_equity.csv').write_bytes(b'corrupted')
    fresh = client.post('/api/backtests', json=body)
    assert fresh.status_code == 201 and fresh.json()['id'] != first.json()['id']


def test_vwap_lookahead_preparation_keeps_actual_equity_aligned(client):
    from alphaquest.strategies.registry import get_strategy
    dataset = save(client)
    body = request_body(dataset)
    body.update(strategy_id='vwap_pullback_risk_sizing', strategy_parameters=json.loads(json.dumps(asdict(get_strategy('vwap_pullback_risk_sizing').module.Parameters()), default=str)))
    response = client.post('/api/backtests', json=body)
    assert response.status_code == 201, response.text
    result = client.get('/api/backtests/' + response.json()['id'] + '/market-benchmark').json()
    assert result['observed_bar_count'] == 4
    assert result['source']['strategy']['session_flattening']
    assert [p['close'] for p in result['chart']['items'][1:]] == ['101', '90', '110', '110']
    assert Decimal(result['accounts']['holding']['net_pnl']) == 188


def test_comparison_survives_application_restart(tmp_path):
    database = tmp_path / 'datasets.sqlite3'
    with TestClient(create_app(database)) as client:
        dataset, run = start(client)
        base = '/api/backtests/' + run['id']
        before = client.get(base + '/market-benchmark').json()
        client.delete('/api/datasets/' + dataset['id'])
    with TestClient(create_app(database)) as client:
        assert client.get(base + '/market-benchmark').json() == before
        assert client.get('/api/backtests').json()['total'] == 1


def test_monthly_attribution_uses_source_dates_and_observed_gaps(client):
    source = ('Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol\n'
              '01/31/2026,19:00,100,100,100,100,0,0,0\n'
              '01/31/2026,23:59,100,110,100,110,0,0,0\n'
              '02/01/2026,00:01,110,110,90,90,0,0,0\n'
              '02/01/2026,20:00,90,100,90,100,0,0,0\n'
              '02/02/2026,10:00,100,100,100,100,0,0,0\n')
    response = client.post('/api/datasets', params=dict(filename='SYNTHETIC-months.csv', name='SYNTHETIC source date boundaries', source_timezone='America/New_York', tick_size='.25', point_value='20'), content=source)
    assert response.status_code == 201
    body = request_body(response.json())
    body['strategy_parameters']['green_bar_count'] = 999
    body['sample_split'] = dict(mode='dates', is_start='2026-01-31', is_end='2026-02-01', oos_start='2026-02-02', oos_end='2026-02-02')
    run = client.post('/api/backtests', json=body)
    assert run.status_code == 201, run.text
    result = client.get('/api/backtests/' + run.json()['id'] + '/market-benchmark').json()
    assert result['observed_bar_count'] == 4
    assert [(p['period'], Decimal(p['holding_net_pnl'])) for p in result['monthly']] == [('2026-01', Decimal(194)), ('2026-02', Decimal(-206))]
    assert Decimal(result['yearly'][0]['holding_net_pnl']) == -12


def test_failed_comparison_is_never_published(client, monkeypatch):
    dataset = save(client)
    def broken(*args):
        raise ValueError('Injected report failure')
    monkeypatch.setattr(MarketBenchmark, 'finish', broken)
    assert client.post('/api/backtests', json=request_body(dataset)).status_code == 500
    assert client.get('/api/backtests').json()['total'] == 0
    assert not list(client.app.state.runs.root.glob('*/report.json'))
