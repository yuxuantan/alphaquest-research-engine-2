"""Source-based calendar boundaries and causal streaming qualifications."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import csv
import io
from pathlib import Path
import pytest

from alphaquest.session_calendar import CT, calendar_path, load_calendar, resolve_calendar, session_date
from alphaquest.execution import Trade, execute
from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing, source_fingerprint
from test_vwap_pullback import CONFIG, bar, parameters, scenario
from test_inferred_session_close import retime


@pytest.mark.parametrize('day,close,cutoff',[
 ('2021-01-18','12:00','11:55'),('2021-09-06','12:00','11:55'),
 ('2024-01-15','12:00','11:55'),('2024-09-02','12:00','11:55'),
 ('2024-07-03','12:15','12:10'),('2024-11-29','12:15','12:10'),
 ('2021-04-02','08:15','08:10'),('2023-04-07','08:15','08:10'),
 ('2018-12-05','08:30','08:25'),('2025-01-09','08:30','08:25'),
 ('2026-04-03','08:15','08:10'),('2021-12-31','16:00','15:55')])
def test_reviewed_notice_expectations(day,close,cutoff):
 plan=load_calendar().plan(date.fromisoformat(day))
 assert plan.close.strftime('%H:%M')==close
 assert plan.cutoff.strftime('%H:%M')==cutoff


def test_configured_cutoff_caps_calendar_and_chicago_dst_is_not_a_fixed_offset():
 calendar=load_calendar()
 for day in ('2024-01-15','2024-09-02'):
  assert calendar.plan(date.fromisoformat(day),1130).cutoff.strftime('%H:%M')=='11:30'
 assert calendar.plan(date(2024,1,15)).cutoff.astimezone(timezone.utc).hour==17
 assert calendar.plan(date(2024,9,2)).cutoff.astimezone(timezone.utc).hour==16


@pytest.mark.parametrize('symbol', ['NQ', 'nq', ' NQ ', '@NQ', 'NQ1!', 'NQ2!', 'NQZ26', 'NQH2026', 'NQ.CME', 'NQ CME'])
def test_reviewed_calendar_resolves_only_explicit_nq_symbols(symbol):
    assert resolve_calendar(symbol)['id'] == 'cme_nq'


@pytest.mark.parametrize('symbol', ['', None, 'ES', 'CL', 'MNQ', 'ofb_bars_NQ', 'NQ_fake'])
def test_unsupported_symbols_never_receive_the_nq_calendar(symbol):
    with pytest.raises(ValueError, match='No reviewed session calendar'):
        resolve_calendar(symbol)


@pytest.mark.parametrize('value', [0, -1, 1441, True, 2.5])
def test_close_buffer_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parameters(close_buffer_minutes=value)
    with pytest.raises(ValueError, match='Close buffer minutes'):
        load_calendar().plan(date(2024, 1, 15), close_buffer_minutes=value)


def test_editable_buffer_preserves_eod_cap_and_changes_early_deadline():
    calendar = load_calendar()
    assert calendar.plan(date(2024, 1, 16), 1545, 10).cutoff.strftime('%H:%M') == '15:45'
    assert calendar.plan(date(2024, 1, 15), 1545, 10).cutoff.strftime('%H:%M') == '11:50'
    assert calendar.plan(date(2024, 1, 15), 1545, 1).cutoff.strftime('%H:%M') == '11:59'
    assert calendar.plan(date(2024, 12, 25), 1545, 10).cutoff is None


def test_api_saves_editable_buffer_and_auto_calendar_without_reusing_different_fills(tmp_path):
    from research_fixtures import ResearchClient
    from alphaquest.app import create_app
    from test_inferred_session_close import buffer_rows, csv_bytes, request_body
    with ResearchClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        saved = client.post('/api/datasets', params=dict(filename='unrelated.csv', name='SYNTHETIC buffer arithmetic',
            symbol='NQZ26', source_timezone='UTC', tick_size='.25', point_value='20'), content=csv_bytes(buffer_rows()))
        assert saved.status_code == 201, saved.text
        records = []
        for minutes, net, label in [(5, '88.00', '18:00:00Z'), (10, '28.00', '17:51:00Z')]:
            response = client.post('/api/backtests', json=request_body(saved.json()['id'], close_buffer_minutes=minutes))
            assert response.status_code == 201, response.text
            record = response.json(); records.append(record)
            assert record['summary']['total_net_pnl'] == net
            flatten = record['run_metadata']['strategy']['session_flattening']
            assert flatten['minutes_before_close'] == minutes
            assert flatten['calendar_id'] == 'cme_nq' and flatten['instrument_symbol'] == 'NQZ26'
            assert record['run_metadata']['strategy']['parameters']['close_buffer_minutes'] == minutes
            trade = client.get(f"/api/backtests/{record['id']}/trades").json()['items'][0]
            assert trade['exit_time_utc'].endswith(label)
        assert records[0]['id'] != records[1]['id']
        assert client.get(f"/api/backtests/{records[0]['id']}").json() == records[0]
        ranges = {name: dict(start=value, end=value, step='0' if type(value) is str else 0)
                  for name, value in request_body(saved.json()['id'])['strategy_parameters'].items()}
        ranges['close_buffer_minutes'] = dict(start=5, end=10, step=5)
        from test_optimization import start, wait_job
        body = request_body(saved.json()['id']); body.pop('strategy_parameters')
        job = wait_job(client, start(client, {**body, 'method': 'exhaustive', 'workers': 2, 'parameter_ranges': ranges}))
        assert job['status'] == 'complete', job
        results = client.get(f"/api/optimizations/{job['id']}/results").json()['items']
        assert {row['parameters']['close_buffer_minutes']: row['metrics']['total_net_pnl'] for row in results} == {5: '88.00', 10: '28.00'}


@pytest.mark.parametrize('symbol', ['', 'CL', 'MNQ'])
def test_api_rejects_unsupported_calendar_before_publishing_or_queuing(tmp_path, symbol):
    from research_fixtures import ResearchClient
    from alphaquest.app import create_app
    from test_inferred_session_close import buffer_rows, csv_bytes, request_body
    with ResearchClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        saved = client.post('/api/datasets', params=dict(filename='NQ.csv', name='SYNTHETIC explicit instrument boundary',
            symbol=symbol, source_timezone='UTC', tick_size='.25', point_value='20'), content=csv_bytes(buffer_rows()))
        assert saved.status_code == 201, saved.text
        body = request_body(saved.json()['id'])
        failed = client.post('/api/backtests', json=body)
        assert failed.status_code == 422 and 'No reviewed session calendar' in failed.text
        values = body.pop('strategy_parameters')
        ranges = {name: dict(start=value, end=value, step='0' if type(value) is str else 0) for name, value in values.items()}
        ranges['use_eod_flat'] = dict(start=False, end=True, step=1)
        failed = client.post('/api/optimizations', json={**body, 'method': 'exhaustive', 'parameter_ranges': ranges})
        assert failed.status_code == 422 and 'No reviewed session calendar' in failed.text
        assert client.get('/api/backtests').json()['total'] == 0
        assert client.get('/api/optimizations').json()['total'] == 0
        from alphaquest.run_backtest import run_saved_dataset
        from alphaquest.backtest_config import RunSettings
        from research_fixtures import declaration
        output = tmp_path / 'unsupported-cli-report'
        with pytest.raises(ValueError, match='No reviewed session calendar'):
            run_saved_dataset(client.app.state.store, saved.json()['id'], output,
                parameters(use_eod_flat=True), RunSettings(CONFIG.initial_capital, CONFIG.slippage_ticks,
                    CONFIG.commission_per_contract_per_side), strategy_id='vwap_pullback_risk_sizing',
                sample_split=declaration(saved.json()['id']))
        assert not output.exists()
        values['use_eod_flat'] = False
        allowed = client.post('/api/backtests', json={**body, 'strategy_parameters': values})
        assert allowed.status_code == 201, allowed.text


def test_holiday_evening_uses_next_session_and_weekends_are_closed():
 calendar=load_calendar()
 assert calendar.plan(date(2024,12,25)).cutoff is None
 stamp=datetime(2024,12,25,17,1,tzinfo=CT)
 assert session_date(stamp)==date(2024,12,26)
 assert calendar.plan(session_date(stamp)).allows(stamp)
 assert not calendar.plan(date(2024,12,28)).allows(datetime(2024,12,28,9,tzinfo=CT))


@pytest.mark.parametrize('day',[date(2015,12,31),date(2026,11,3),date(2027,1,4)])
def test_unknown_coverage_rejects(day):
 with pytest.raises(ValueError,match='does not cover'):
  load_calendar().plan(day)


def test_calendar_blocks_a_morning_signal_on_a_full_closure():
 rows=[retime(row,date(2024,3,29)) for row in scenario()]
 events=list(execute(rows,VwapPullbackRiskSizing(parameters(use_eod_flat=True),execution_config=CONFIG),CONFIG))
 assert not [event for event in events if isinstance(event,Trade)]


def test_no_future_bar_is_pulled_before_current_decision_and_suffix_does_not_move_cutoff():
 p=parameters(use_eod_flat=True)
 rows=scenario()
 decisions=[]
 strategy=VwapPullbackRiskSizing(p,execution_config=CONFIG)
 original=strategy.on_bar
 def observed(current,position):
  result=original(current,position);decisions.append((current.bar_number,result));return result
 strategy.on_bar=observed
 def guarded():
  for index,row in enumerate(rows):
   if index:assert decisions[-1][0]==rows[index-1].bar_number
   yield row
 list(execute(guarded(),strategy,CONFIG))
 first_cutoff=strategy.session_flattening['examples'][0]['order_cutoff']
 shortened=VwapPullbackRiskSizing(p,execution_config=CONFIG)
 list(execute(rows[:123],shortened,CONFIG))
 assert shortened.session_flattening['examples'][0]['order_cutoff']==first_cutoff
 assert shortened.session_flattening['lookahead'] is False


def test_pending_entry_does_not_jump_into_a_later_session():
 from test_inferred_session_close import session_rows
 rows=session_rows()[:122]
 rows.append(retime(bar(123,17,1),date(2024,1,15)))
 events=list(execute(rows,VwapPullbackRiskSizing(parameters(use_eod_flat=True),execution_config=CONFIG),CONFIG))
 assert not [event for event in events if isinstance(event,Trade)]


@pytest.mark.parametrize('change',[
 {'closure_type':'full_close','close_time_local':'12:00'},
 {'close_time_local':'25:00'}, {'timezone':'CST'}, {'coverage_end':'2026-12-31'},
 {'source_url':''}, {'verified_on':'11/02/2026'},])
def test_invalid_file_rejected_instead_of_silent_regular_hours(tmp_path,change):
 rows=list(csv.DictReader(calendar_path().open()))
 rows[1].update(change)
 p=tmp_path/'bad.csv'
 with p.open('w',newline='') as stream:
  writer=csv.DictWriter(stream,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
 with pytest.raises(ValueError,match='Invalid NQ session calendar'):load_calendar(p)


def test_csv_snapshot_is_immutable_and_calendar_edits_change_strategy_identity(tmp_path,monkeypatch):
 import alphaquest.session_calendar as module
 import alphaquest.strategies.vwap_pullback_risk_sizing as strategy_module
 raw=calendar_path().read_bytes()
 p=tmp_path/'calendar.csv';p.write_bytes(raw)
 snapshot=load_calendar(p)
 original=source_fingerprint()
 p.write_bytes(raw.replace(b'No session ending',b'Reviewed session ending',1))
 assert snapshot.sha256!=load_calendar(p).sha256
 monkeypatch.setattr(strategy_module,'calendar_path',lambda:p)
 assert source_fingerprint()!=original
 p.unlink()
 assert snapshot.plan(date(2024,1,15)).cutoff.hour==11
 with pytest.raises(ValueError,match='Invalid NQ session calendar'):load_calendar(p)


def test_report_metadata_stays_bound_to_the_snapshot_used_for_trading(tmp_path, monkeypatch):
    import alphaquest.strategies.vwap_pullback_risk_sizing as module
    raw = calendar_path().read_bytes()
    path = tmp_path / 'calendar.csv'
    path.write_bytes(raw)

    def read_then_replace_file():
        snapshot = load_calendar(path)
        # A concurrent manual update changes the file after this read. The
        # running strategy must describe its original snapshot, not the new file.
        path.write_bytes(raw.replace(b'No session ending', b'Reviewed session ending', 1))
        return snapshot

    monkeypatch.setattr(module, 'load_calendar', read_then_replace_file)
    strategy = VwapPullbackRiskSizing(parameters(use_eod_flat=True), execution_config=CONFIG)
    saved = strategy.session_flattening['calendar']
    assert saved == strategy._calendar.metadata()
    assert saved['sha256'] != load_calendar(path).sha256
