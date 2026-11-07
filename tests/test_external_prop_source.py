"""External observed-mark sources use the ordinary local prop workflow."""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import io
import json
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.backtest_runs import RunStore
from alphaquest.canonical_trades import TradeExportError, parse_trade_export
from alphaquest.prop.commissions import adapt
from alphaquest.prop.external_source import admission, capabilities
from alphaquest.prop.lucid_engine import trade_result
from alphaquest.prop.native_analysis import day_book, prepare, resolved_settings
from alphaquest.prop.native_engine import risk_hit
from alphaquest.prop.source import prepare_source
from alphaquest.trade_imports import save_import
from test_canonical_trades import envelope, raw
from test_prop_analysis_api import wait
from test_trade_imports import IMPORTS, save, snapshot


SETTINGS = dict(COMMISSION_MODE='source', SLOTS='1', MAX_TOTAL_NQ='0.1', BLOCK_DAYS='1')


def declared_export():
    doc = envelope()
    doc['manifest']['execution']['sizing_path_invariance'] = 'exporter_declared'
    return doc


def prepared(tmp_path, document=None, **overrides):
    runs = RunStore(tmp_path)
    content = raw(document or declared_export())
    record, created = save_import(runs, content, 'SYNTHETIC-ordered-marks.json')
    assert created
    source, rows = prepare_source(runs, record['id'], '')
    settings = resolved_settings(dict(SETTINGS, **overrides))
    original = deepcopy(rows)
    adapt(source, rows, settings)
    return runs, record, source, rows, settings, original


@pytest.mark.parametrize('instrument', ['MNQ', 'NQ'])
def test_source_cost_normalization_retains_net_and_ordered_jumps_once(tmp_path, instrument):
    doc = declared_export()
    if instrument == 'NQ':
        doc['manifest']['instrument'].update(symbol='NQ', point_value='20')
        doc['manifest']['dataset']['contract'] = 'NQH26'
        trade = doc['payload']['trades'][0]
        for key in ('reference_gross_pnl', 'slippage_cost', 'gross_pnl', 'net_pnl',
                    'entry_commission', 'exit_commission', 'total_commissions'):
            trade[key] = str(Decimal(trade[key])*10)
        for key in ('mae', 'mfe'):
            trade['excursions'][key] = str(Decimal(trade['excursions'][key])*10)
        for event in doc['payload']['risk_events']:
            for key in ('cumulative_realized_gross', 'commissions_charged', 'marked_trade_net_equity'):
                event[key] = str(Decimal(event[key])*10)
    runs, record, source, rows, settings, original = prepared(tmp_path, doc)
    row = rows[0]
    # One MNQ receives $2 net and observed maximum loss $3. Fees/slippage
    # already occur in source net; neither is charged a second time.
    assert Decimal(row['simulation_net_per_mnq']) == 2
    assert Decimal(row['simulation_mae_per_nq'])/10 == 3
    assert Decimal(row['simulation_commission_per_mnq']) == 1
    assert [(Decimal(value), jump) for value, jump in json.loads(row['simulation_adverse_path_per_nq'])] == [(5, True), (30, True)]
    assert not source['commission_simulation']['applied']
    assert row['source_net_pnl'] == ('4' if instrument == 'MNQ' else '40')
    assert row['measured_mae'] is None and row['measured_mfe'] is None
    assert all(row[key] == value for key, value in original[0].items())
    assert json.loads(row['ordered_events_json']) == doc['payload']['risk_events']
    assert (runs.root/record['id']/'source.json').read_bytes() == raw(doc)
    grid, days, split = day_book(rows, settings)
    assert [str(d.date()) for d in grid] == ['2026-01-05', '2026-01-06']
    assert split == 1 and days == [[(20., 30., ((5., True), (30., True)))], []]
    path = days[0][0][2]
    assert risk_hit(path, 0., 1., -2., -100.) == (1, -3.)
    assert risk_hit(path, 0., 1., -2., -2.5) == (2, -3.)
    assert trade_result(days[0][0], 0., 1., -2., -100.) == (-3., 1)
    # Interpolating a continuous threshold would erase the observed overshoot.
    assert risk_hit(tuple((loss, False) for loss, _ in path), 0., 1., -2., -100.) == (1, -2.)


def test_override_replaces_one_open_side_and_two_close_sides_exactly(tmp_path):
    _, _, source, rows, settings, original = prepared(tmp_path, COMMISSION_MODE='override', COMMISSION_PER_SIDE='1')
    row = rows[0]
    # Original 2 MNQ gross $6 -> $3 per MNQ; new round-turn fee $2 -> net $1.
    # Lowest mark gross -$2.50 per MNQ minus ONE $1 entry fee -> adverse $3.50.
    assert Decimal(row['simulation_net_per_mnq']) == 1
    assert Decimal(row['simulation_commission_per_mnq']) == 2
    assert Decimal(row['simulation_mae_per_nq'])/10 == Decimal('3.5')
    assert json.loads(row['simulation_adverse_path_per_nq']) == [['10', True], ['35', True]]
    assert source['commission_simulation']['applied']
    assert all(row[key] == value for key, value in original[0].items())
    _, days, _ = day_book(rows, settings)
    assert risk_hit(days[0][0][2], 0., 1., -2., -100.) == (1, -3.5)


def test_declared_no_trade_edges_remain_in_the_source_grid(tmp_path):
    doc = declared_export()
    doc['manifest']['coverage'].update(start_utc='2026-01-02T00:00:00Z', end_utc='2026-01-07T22:00:00Z',
        sessions=['2026-01-02', '2026-01-05', '2026-01-06', '2026-01-07'])
    _, _, _, rows, settings, _ = prepared(tmp_path, doc)
    grid, days, split = day_book(rows, settings)
    assert [str(d.date()) for d in grid] == doc['manifest']['coverage']['sessions']
    assert [len(day) for day in days] == [0, 1, 0, 0]
    assert split == 2


def test_observed_diagnostics_and_costs_ignore_ambient_decimal_precision(tmp_path):
    doc = declared_export()
    with localcontext(Context(prec=512)):
        extra = Decimal('0.12345678901234567890123456789')
        trade = doc['payload']['trades'][0]
        for key in ('entry_commission', 'total_commissions'):
            trade[key] = str(Decimal(trade[key])+extra)
        trade['net_pnl'] = str(Decimal(trade['net_pnl'])-extra)
        trade['excursions']['mae'] = str(Decimal(6)+extra)
        trade['excursions']['mfe'] = str(Decimal(6)-extra)
        for event in doc['payload']['risk_events']:
            event['commissions_charged'] = str(Decimal(event['commissions_charged'])+extra)
            event['marked_trade_net_equity'] = str(Decimal(event['marked_trade_net_equity'])-extra)
        expected_net = (Decimal(4)-extra)/2
        expected_mae = (Decimal(6)+extra)/2
        expected_mae_per_nq = expected_mae*10
    with localcontext() as context:
        context.prec = 1
        _, _, _, rows, _, _ = prepared(tmp_path, doc)
        assert rows[0]['observed_mark_mae'] == trade['excursions']['mae']
        assert Decimal(rows[0]['simulation_net_per_mnq']) == expected_net
        assert Decimal(rows[0]['simulation_mae_per_nq']) == expected_mae_per_nq


def second_trade_with_quantity(doc, quantity):
    trade = deepcopy(doc['payload']['trades'][0])
    def later(value):
        return (datetime.fromisoformat(value.replace('Z', '+00:00'))+timedelta(minutes=5)).isoformat().replace('+00:00', 'Z')
    trade['trade_id'] = 'second'; trade['quantity'] = quantity
    for key in ('entry_time_utc', 'exit_time_utc'):
        trade[key] = later(trade[key])
    trade['sizing_decision']['timestamp_utc'] = later(trade['sizing_decision']['timestamp_utc'])
    trade['initial_stop']['known_at_utc'] = later(trade['initial_stop']['known_at_utc'])
    for stop in trade['stop_updates']:
        stop['known_at_utc'] = later(stop['known_at_utc'])
    for key in ('mae_time_utc', 'mfe_time_utc'):
        trade['excursions'][key] = later(trade['excursions'][key])
    factor = Decimal(quantity)/2
    for key in ('reference_gross_pnl', 'slippage_cost', 'gross_pnl', 'net_pnl',
                'entry_commission', 'exit_commission', 'total_commissions'):
        trade[key] = str(Decimal(trade[key])*factor)
    for key in ('mae', 'mfe'):
        trade['excursions'][key] = str(Decimal(trade['excursions'][key])*factor)
    events = deepcopy(doc['payload']['risk_events'])
    for event in events:
        event.update(trade_id='second', sequence=event['sequence']+5, timestamp_utc=later(event['timestamp_utc']),
                     current_quantity=0 if event['kind'] == 'close' else quantity)
        for key in ('cumulative_realized_gross', 'commissions_charged', 'marked_trade_net_equity'):
            event[key] = str(Decimal(event[key])*factor)
    doc['payload']['trades'].append(trade); doc['payload']['risk_events'].extend(events)
    doc['completion'].update(trade_count=2, event_count=10)


@pytest.mark.parametrize('case,reason', [
    ('partial', 'Complete ordered'), ('extrema', 'extend beyond'), ('invariance', 'invariance'),
    ('currency', 'USD'), ('variable_quantity', 'constant source quantity'),
    ('overnight', 'intraday-flat'), ('missing_calendar', 'Missing sessions'),
    ('bar_timestamp', 'actual-fill'), ('measured_only', 'Complete ordered'),
])
def test_canonical_importability_does_not_grant_unsupported_prop_admission(case, reason):
    doc = declared_export()
    if case == 'partial': doc['manifest']['risk']['coverage'] = 'partial'
    elif case == 'extrema':
        doc['payload']['trades'][0]['excursions'].update(basis='exporter_reported_net_equity', mae='7', mae_time_utc=None)
    elif case == 'invariance': doc['manifest']['execution']['sizing_path_invariance'] = 'unverified'
    elif case == 'currency': doc['manifest']['instrument']['currency'] = 'EUR'
    elif case == 'variable_quantity': second_trade_with_quantity(doc, 4)
    elif case == 'overnight':
        doc['payload']['trades'][0]['exit_time_utc'] = '2026-01-06T15:02:00Z'
        doc['payload']['risk_events'][-1]['timestamp_utc'] = '2026-01-06T15:02:00Z'
    elif case == 'missing_calendar':
        doc['manifest']['coverage'].update(end_utc='2026-01-07T22:00:00Z', sessions=['2026-01-05', '2026-01-07'])
    elif case == 'bar_timestamp': doc['manifest']['time'].update(timestamp_basis='bar_close', bar_interval_seconds=60)
    elif case == 'measured_only':
        doc['manifest']['risk']['basis'] = 'measured_extrema'
        doc['payload']['trades'][0]['excursions']['basis'] = 'exporter_reported_net_equity'
        doc['payload']['risk_events'] = []; doc['completion']['event_count'] = 0
    source = parse_trade_export(raw(doc))
    assert reason in admission(source)
    assert not capabilities(source)['prop_analysis']


def test_incomplete_path_cannot_reach_prop_admission():
    doc = declared_export()
    doc['payload']['risk_events'].pop(); doc['completion']['event_count'] -= 1
    with pytest.raises(TradeExportError, match='opening and terminal'):
        parse_trade_export(raw(doc))


def test_external_source_rejects_supplemental_workbook_and_dated_modes(tmp_path):
    runs, record, _, _, _, _ = prepared(tmp_path)
    with pytest.raises(ValueError, match='supplemental'):
        prepare_source(runs, record['id'], '/not-consumed.xlsx')
    with pytest.raises(ValueError, match='instrument conflicts'):
        prepare(runs, record['id'], '', dict(SETTINGS, SOURCE_INSTRUMENT='NQ'))
    for mode in ('dated_lifecycle', 'budgeted_lifecycle'):
        settings = dict(SETTINGS, ANALYSIS_MODE=mode, EVALUATION_MICROS='1', FUNDED_MICROS='1')
        if mode == 'budgeted_lifecycle':
            settings.update(MONTHLY_CAP='100', BUDGET_TIMEZONE='America/Chicago',
                START_DATE='2026-01-05', HORIZON_END='2026-01-06', PAYOUT_RECEIPT_DAYS='0',
                PAYOUT_TIMING_ASSUMPTION='SYNTHETIC unverified immediate receipt.',
                ACTIVATION_DEADLINE_DAYS='7', ACTIVATION_TIMING_ASSUMPTION='SYNTHETIC seven-day deadline.')
        with pytest.raises(ValueError, match='annualized EOD'):
            prepare(runs, record['id'], '', settings)


def test_normal_import_check_analysis_download_and_reopen(tmp_path, monkeypatch):
    database = tmp_path/'datasets.sqlite3'
    content = raw(declared_export(), indent=2)
    with TestClient(create_app(database)) as client:
        preview = client.post(IMPORTS+'/check', params={'filename':'SYNTHETIC-ordered-marks.json'}, content=content)
        assert preview.status_code == 200, preview.text
        assert preview.json()['capabilities']['prop_analysis']
        assert preview.json()['capabilities']['prop_analysis_modes'] == ['annualized']
        record = save(client, content); source_id = record['id']
        source_folder = client.app.state.runs.root/source_id
        source_before = snapshot(source_folder)
        request = dict(source_backtest_id=source_id, settings=SETTINGS)
        checked = client.post('/api/prop-analyses/check', json=request)
        assert checked.status_code == 200, checked.text
        check = checked.json()
        assert check['matched_trades'] == 1
        assert check['source']['session_grid'] == dict(first='2026-01-05', last='2026-01-06', weekdays=2, train=1, validation=1,
            convention='CME session date: Chicago entry timestamp plus 7 hours; zero-trade weekdays retained')
        assert check['source']['reconciliation']['source_totals']['net_pnl'] == '4'
        submitted = client.post('/api/prop-analyses', json=request)
        assert submitted.status_code == 202, submitted.text
        job = wait(client, submitted.json()['id'])
        assert job['status'] == 'complete', job
        analysis_id = job['id']; url = '/api/prop-analyses/'+analysis_id+'/downloads/'
        saved_report = client.get(url+'report.json').content
        report = json.loads(saved_report)
        assert report['source']['source_kind'] == 'external_trade_export'
        assert report['source']['canonical_source']['raw_sha256'] == sha256(content).hexdigest()
        assert report['calculations']['samples']['weekdays'] == [1, 1]
        assert report['calculations']['evaluation']['pass_rate'] == 0
        assert report['calculations']['evaluation']['passed'] == 0
        assert report['calculations']['funded'] is None
        assert report['source']['external_assumptions']['tick_completeness_verified'] is False
        zipped = client.get(url+'analysis.zip')
        assert zipped.status_code == 200, zipped.text
        with ZipFile(io.BytesIO(zipped.content)) as archive:
            assert archive.read('inputs/external_source/source.json') == content
            canonical = json.loads(archive.read('inputs/external_source/canonical_source.json'))
            assert canonical['risk_events'] == declared_export()['payload']['risk_events']
            assert json.loads(archive.read('calculations.json')) == report['calculations']
        assert snapshot(source_folder) == source_before
        assert client.get('/api/datasets').json() == []
        assert client.get('/api/backtests').json()['total'] == 1
        (tmp_path/'independent-expectations.json').write_text(json.dumps(dict(synthetic=True,
            whole_source_net='4', simulation_net_per_mnq='2', observed_mae_per_mnq='3',
            source_sessions=['2026-01-05', '2026-01-06'], validation_trades=0,
            evaluation_pass_rate=0, funded_result=None, source_id=source_id, analysis_id=analysis_id), indent=2))
    def forbidden(*args, **kwargs):
        raise AssertionError('Reopening a saved report must not resimulate or readapt its source.')
    monkeypatch.setattr('alphaquest.prop.native_analysis.calculate', forbidden)
    monkeypatch.setattr('alphaquest.prop.external_source.adapt_costs', forbidden)
    with TestClient(create_app(database)) as client:
        assert client.get(url+'report.json').content == saved_report
        assert client.get(url+'analysis.zip').content == zipped.content
        assert client.get('/api/backtests/'+source_id+'/exports/source').content == content
        assert snapshot(source_folder) == source_before
