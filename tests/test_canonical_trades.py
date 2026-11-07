from copy import deepcopy
from decimal import getcontext, localcontext
from hashlib import sha256
import json

import pytest

from alphaquest.canonical_trades import (SCHEMA_VERSION, TradeExportError, canonical_payload_sha256,
                              parse_trade_export, project_native_source)


def envelope():
    trade = dict(trade_id='mc-42', side='long', quantity=2,
        entry_time_utc='2026-01-05T15:00:00Z', exit_time_utc='2026-01-05T15:02:00Z',
        entry_reference_price='100', exit_reference_price='102', entry_fill_price='100.25', exit_fill_price='101.75',
        entry_commission='1', exit_commission='1', total_commissions='2',
        reference_gross_pnl='8', slippage_cost='2', gross_pnl='6', net_pnl='4',
        entry_reason='test entry', exit_reason='test exit', entry_bar_number=None, exit_bar_number=None,
        sizing_decision=dict(timestamp_utc='2026-01-05T14:59:00Z', reference_price='100', execution_timing='next_open'),
        initial_stop=dict(price='99', known_at_utc='2026-01-05T14:59:00Z', basis='strategy_decision'),
        stop_updates=[dict(price='100', known_at_utc='2026-01-05T15:01:00Z', basis='submitted_order')],
        excursions=dict(basis='observed_marks_net_equity', mae='6', mfe='6',
                        mae_time_utc='2026-01-05T15:00:30Z', mfe_time_utc='2026-01-05T15:01:30Z'))
    events = []
    for index, (stamp, kind, mark, net, stop) in enumerate([
        ('15:00:00', 'open', '100.25', '-1', None),
        ('15:00:30', 'mark', '99', '-6', None),
        ('15:01:00', 'stop_update', '100', '-2', '100'),
        ('15:01:30', 'mark', '102', '6', None),
        ('15:02:00', 'close', '101.75', '4', None)], 1):
        events.append(dict(trade_id='mc-42', sequence=index, timestamp_utc=f'2026-01-05T{stamp}Z', kind=kind,
                           current_quantity=0 if kind == 'close' else 2, mark_price=mark, stop_price=stop,
                           cumulative_realized_gross='6' if kind == 'close' else '0',
                           commissions_charged='2' if kind == 'close' else '1', marked_trade_net_equity=net))
    return dict(schema_version=SCHEMA_VERSION, export_id='synthetic-precise-evidence',
        manifest=dict(origin='multicharts_dotnet', exporter_build='fixture-1',
            platform=dict(edition='MultiCharts .NET', build='declared synthetic', bitness=64),
            strategy=dict(id='SYNTHETIC', parameters={'threshold':'0.5'}, implementation_sha256='1'*64),
            dataset=dict(name='SYNTHETIC', sha256='2'*64, contract='MNQH26', adjustment='none'),
            instrument=dict(symbol='MNQ', currency='USD', tick_size='0.25', point_value='2'),
            initial_capital='10000',
            time=dict(timestamp_basis='actual_fill', source_timezone='America/Chicago', session_convention='cme_chicago_1700_v1', bar_interval_seconds=None),
            coverage=dict(start_utc='2026-01-05T00:00:00Z', end_utc='2026-01-06T22:00:00Z',
                          sessions=['2026-01-05','2026-01-06'], calendar_id='synthetic-explicit-calendar', calendar_sha256='3'*64,
                          completion='exporter_declared_complete'),
            research=dict(phase='is', declaration='Synthetic source only', prior_access='unknown'),
            execution=dict(position_model='nonoverlapping_constant_quantity_round_trips', sizing_path_invariance='unverified',
                           cost_basis='actual_per_trade', fill_assumption='synthetic actual fills', assumptions=[]),
            risk=dict(basis='ordered_marks', coverage='complete', units='whole_trade_account_currency',
                      equity_basis='actual_fill_pnl_less_commissions_charged', observation_claim='exporter_declared')),
        payload=dict(trades=[trade], risk_events=events),
        completion=dict(status='complete', trade_count=1, event_count=5, payload_sha256='0'*64))


def raw(document=None, *, seal=True, indent=None):
    document = deepcopy(document or envelope())
    if seal:
        document['completion']['payload_sha256'] = canonical_payload_sha256(document['payload'])
    return json.dumps(document, ensure_ascii=False, separators=(',',':') if indent is None else None, indent=indent).encode()


def setpath(document, path, value):
    keys = path.split('.')
    obj = document
    for key in keys[:-1]:
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    key = int(keys[-1]) if isinstance(obj, list) else keys[-1]
    obj[key] = value


def test_exact_complete_source_preserves_all_fields_and_costs_once():
    original = raw()
    result = parse_trade_export(original)
    assert result['source']['raw_sha256'] == sha256(original).hexdigest()
    assert result['source']['raw_bytes'] == len(original)
    assert result['trades'] == envelope()['payload']['trades']
    assert result['risk_events'] == envelope()['payload']['risk_events']
    assert result['validation']['totals'] == dict(reference_gross_pnl='8', slippage_cost='2', total_commissions='2', gross_pnl='6', net_pnl='4')
    assert result['manifest']['coverage']['sessions'] == ['2026-01-05','2026-01-06']  # no-trade session survives
    assert result['manifest']['research']['phase'] == 'is'
    assert result['capabilities']['ordered_marks_available']
    assert result['capabilities']['risk_based_sizing_inputs_available']
    for key in ('prop_analysis','controlled_oos','native_replay','bar_equity','nested_research','tick_completeness_verified','calendar_coverage_verified'):
        assert result['capabilities'][key] is False
    assert result['native_risk'] is None


def test_raw_hash_preserves_whitespace_but_payload_hash_is_versioned_canonical():
    compact, pretty = parse_trade_export(raw()), parse_trade_export(raw(indent=2))
    assert compact['source']['raw_sha256'] != pretty['source']['raw_sha256']
    assert compact['source']['payload_sha256'] == pretty['source']['payload_sha256']
    doc = envelope()
    doc['payload']['trades'][0]['gross_pnl'] = '6.0'
    assert parse_trade_export(raw(doc))['source']['payload_sha256'] != compact['source']['payload_sha256']


@pytest.mark.parametrize('path,value,match', [
    ('schema_version','unknown','schema'), ('completion.status','partial','Partial'),
    ('completion.trade_count',2,'count'), ('completion.event_count',4,'count'),
    ('manifest.initial_capital','0','positive'), ('manifest.initial_capital',10000,'decimal string'),
    ('manifest.initial_capital','NaN','decimal string'), ('manifest.initial_capital','1e5','decimal string'),
    ('manifest.initial_capital',' 10000','decimal string'), ('manifest.initial_capital','+10000','decimal string'),
    ('manifest.initial_capital','01','decimal string'), ('manifest.initial_capital','0.'+'1'*65,'decimal places'),
    ('manifest.dataset.sha256',None,'SHA-256'), ('manifest.strategy.implementation_sha256',None,'SHA-256'),
    ('manifest.instrument.currency','usd','currency'), ('manifest.instrument.point_value','0','positive'),
    ('manifest.time.source_timezone','Mars/Olympus','timezone'), ('manifest.time.session_convention','utc','convention'),
    ('manifest.time.timestamp_basis','bar_close','bar_interval'), ('manifest.platform.bitness',True,'bitness'),
    ('manifest.coverage.sessions',['2026-01-06','2026-01-05'],'chronological'),
    ('manifest.coverage.sessions',['2026-01-05','2026-01-05','2026-01-06'],'chronological'),
    ('manifest.coverage.sessions',['2026-01-06'],'endpoints'),
    ('manifest.coverage.calendar_sha256','no','SHA-256'),
    ('manifest.research.phase','untouched','phase'), ('manifest.execution.position_model','partial_exits','position model'),
    ('manifest.risk.equity_basis','reference_less_fees','equity/cost'),
    ('payload.trades.0.quantity',True,'integer'), ('payload.trades.0.quantity',0,'integer'),
    ('payload.trades.0.entry_time_utc','2026-01-05T15:00:00','UTC'),
    ('payload.trades.0.entry_time_utc','2026-01-05T23:00:00+08:00','UTC'),
    ('payload.trades.0.exit_time_utc','2026-01-05T14:00:00Z','ordered'),
    ('payload.trades.0.net_pnl','2','net once'), ('payload.trades.0.slippage_cost','4','Slippage'),
    ('payload.trades.0.entry_fill_price','100.50','Actual fills'), ('payload.trades.0.entry_commission','2','Per-side'),
    ('payload.trades.0.entry_bar_number',1,'both'),
    ('payload.trades.0.initial_stop.known_at_utc','2026-01-05T14:59:30Z','sizing decision'),
    ('payload.trades.0.initial_stop.price','101','adverse side'),
    ('payload.trades.0.sizing_decision.timestamp_utc','2026-01-05T15:00:01Z','cannot follow'),
    ('payload.trades.0.sizing_decision.execution_timing','same_close','entry timestamp'),
    ('payload.trades.0.stop_updates.0.price','100.25','provenance'),
    ('payload.trades.0.excursions.mae','0','opening costs'),
    ('payload.trades.0.excursions.mfe','7','reconcile exactly'),
    ('payload.trades.0.excursions.mae_time_utc','2026-01-04T15:00:00Z','holding interval'),
    ('payload.risk_events.0.kind','mark','opening and terminal'),
    ('payload.risk_events.1.current_quantity',1,'quantity'),
    ('payload.risk_events.1.cumulative_realized_gross','1','partial realization'),
    ('payload.risk_events.1.marked_trade_net_equity','-7','Mark equity'),
    ('payload.risk_events.1.commissions_charged','2','fees'),
    ('payload.risk_events.1.mark_price',None,'mark price'),
    ('payload.risk_events.1.trade_id','other','unknown trade'),
    ('payload.risk_events.1.sequence',1,'sequence'),
    ('payload.risk_events.2.stop_price',None,'stop_price'),
    ('payload.risk_events.4.marked_trade_net_equity','3','Terminal event'),
])
def test_strict_contract_rejections(path, value, match):
    doc = envelope()
    setpath(doc,path,value)
    with pytest.raises(TradeExportError, match=match):
        parse_trade_export(raw(doc))


def test_unknown_keys_duplicate_keys_bad_json_and_float_tokens_reject():
    doc = envelope(); doc['payload']['trades'][0]['invented_stop'] = '99'
    with pytest.raises(TradeExportError, match='unknown'):
        parse_trade_export(raw(doc))
    for value in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1.5}', b'not-json', b'\xff', b''):
        with pytest.raises(TradeExportError):
            parse_trade_export(value)
    with pytest.raises(TradeExportError, match='bytes'):
        parse_trade_export(raw().decode())


def test_changed_payload_rejected_without_matching_completion_hash():
    doc=json.loads(raw()); doc['payload']['trades'][0]['entry_reason']='changed'
    with pytest.raises(TradeExportError, match='SHA-256'):
        parse_trade_export(raw(doc,seal=False))


def test_duplicate_and_overlapping_trades_reject():
    for duplicate_id in (True,False):
        doc=envelope(); copy=deepcopy(doc['payload']['trades'][0])
        if not duplicate_id: copy['trade_id']='different'
        doc['payload']['trades'].append(copy); doc['completion']['trade_count']=2
        with pytest.raises(TradeExportError, match='Duplicate|nonoverlapping'):
            parse_trade_export(raw(doc))


def test_missing_unknown_partial_risk_are_distinct_and_do_not_fabricate_stops():
    for basis in ('missing','unknown'):
        doc=envelope(); doc['manifest']['risk'].update(basis=basis,coverage=basis,observation_claim=basis)
        doc['payload']['risk_events']=[]; doc['completion']['event_count']=0
        doc['payload']['trades'][0].update(excursions=None, initial_stop=None, stop_updates=[], sizing_decision=None)
        result=parse_trade_export(raw(doc))
        assert result['manifest']['risk']['basis']==basis
        assert not result['capabilities']['initial_stops_available']
        assert not result['capabilities']['sizing_decisions_available']
        assert not result['capabilities']['ordered_marks_available']
        assert result['trades'][0]['initial_stop'] is None
    doc=envelope(); doc['manifest']['risk']['coverage']='partial'
    assert parse_trade_export(raw(doc))['capabilities']['prop_analysis'] is False


def test_complete_and_partial_path_cannot_omit_terminal_event():
    for coverage in ('complete','partial'):
        doc=envelope(); doc['manifest']['risk']['coverage']=coverage
        doc['payload']['risk_events'].pop(); doc['completion']['event_count']=4
        with pytest.raises(TradeExportError,match='opening and terminal'):
            parse_trade_export(raw(doc))


def test_measured_extrema_are_preserved_without_fabricated_ordered_path():
    doc=envelope(); doc['manifest']['risk']['basis']='measured_extrema'
    doc['payload']['risk_events']=[]; doc['completion']['event_count']=0
    doc['payload']['trades'][0]['excursions']['basis']='exporter_reported_net_equity'
    result=parse_trade_export(raw(doc))
    assert result['risk_events']==[]
    assert result['trades'][0]['excursions']['mae']=='6'
    assert not result['capabilities']['prop_analysis']


def test_negative_prices_and_actual_gap_use_decision_stop_not_future_entry_reference():
    doc=envelope(); trade=doc['payload']['trades'][0]
    # Translate all actual/reference/mark prices by -101; differences and cash remain identical.
    from decimal import Decimal
    for name in ('entry_reference_price','exit_reference_price','entry_fill_price','exit_fill_price'):
        trade[name]=str(Decimal(trade[name])-101)
    trade['initial_stop']['price']='-2'; trade['sizing_decision']['reference_price']='-1'
    trade['stop_updates'][0]['price']='-1'
    for event in doc['payload']['risk_events']:
        event['mark_price']=str(Decimal(event['mark_price'])-101)
        if event['stop_price'] is not None: event['stop_price']='-1'
    assert parse_trade_export(raw(doc))['validation']['totals']['net_pnl']=='4'
    # A large gap through a previously known stop is evidence, not a reason to
    # retroactively alter the historical sizing decision or fabricate a stop.
    trade['sizing_decision']['reference_price']='1'
    trade['initial_stop']['price']='0'
    result=parse_trade_export(raw(doc))
    assert result['trades'][0]['initial_stop']['price']=='0'
    assert result['trades'][0]['entry_reference_price']=='-1'


def test_zero_trade_complete_source_preserves_calendar_and_has_no_sizing_evidence():
    doc=envelope(); doc['payload']={'trades':[],'risk_events':[]}
    doc['completion'].update(trade_count=0,event_count=0)
    result=parse_trade_export(raw(doc))
    assert result['validation']['trade_count']==0
    assert result['validation']['totals']['net_pnl']=='0'
    assert not result['capabilities']['initial_stops_available']
    assert result['manifest']['coverage']['sessions']==['2026-01-05','2026-01-06']


def test_precision_is_independent_of_callers_decimal_context():
    with localcontext() as context:
        context.prec=2
        before=getcontext().prec
        result=parse_trade_export(raw())
        assert result['validation']['totals']['net_pnl']=='4'
        assert getcontext().prec==before


def test_native_projection_uses_real_report_preserves_risk_and_no_invented_stop(tmp_path):
    from fastapi.testclient import TestClient
    from alphaquest.app import create_app
    from test_robust_research_api import save_grid
    from alphaquest.backtest_runs import RunStore
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,_,records=save_grid(client)
        store=RunStore(tmp_path)
        source_id=records[0]['id']
        folder=store.root/source_id
        before={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}
        result=project_native_source(store,source_id)
        assert result['source']['kind']=='native_backtest'
        assert result['validation']['trade_count']==records[0]['summary']['trades_taken']
        assert result['validation']['totals']['net_pnl']==records[0]['summary']['total_net_pnl']
        assert result['manifest']['coverage']['sessions'] is None  # no inferred calendar
        assert result['native_risk'] is not None
        assert all(t['initial_stop'] is None for t in result['trades'])
        if records[0].get('execution_decisions'):
            assert all(t['sizing_decision'] is not None and t['stop_provenance'] == 'not_declared_by_strategy' for t in result['trades'])
        else:
            assert all(t['sizing_decision'] is None for t in result['trades'])
        assert all(t['native_fields']['exit_deadline_utc'] is not None for t in result['trades'])
        assert before=={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}
        assert result['source']['artifact_sha256']['trades.csv']==sha256(before['trades.csv']).hexdigest()
        with pytest.raises(TradeExportError,match='UUID'):
            project_native_source(store,'../not-a-run')
        # An artifact with changed net cannot become a normalized native source.
        path=folder/'trades.csv'
        path.write_bytes(before['trades.csv'].replace(b',300,',b',301,',1))
        try:
            if path.read_bytes()!=before['trades.csv']:
                with pytest.raises(ValueError): project_native_source(store,source_id)
        finally:
            path.write_bytes(before['trades.csv'])


def test_short_direction_and_price_improvement_reconcile_exactly():
    from decimal import Decimal
    doc=envelope(); trade=doc['payload']['trades'][0]; trade['side']='short'
    # Reflect every price about 100: the short earns the same exact net.
    for name in ('entry_reference_price','exit_reference_price','entry_fill_price','exit_fill_price'):
        trade[name]=str(200-Decimal(trade[name]))
    trade['initial_stop']['price']='101'; trade['stop_updates'][0]['price']='100'
    for event in doc['payload']['risk_events']:
        event['mark_price']=str(200-Decimal(event['mark_price']))
    result=parse_trade_export(raw(doc))
    assert result['validation']['totals']['net_pnl']=='4'
    # Favorable slippage is signed savings, never an extra net deduction.
    doc=envelope(); trade=doc['payload']['trades'][0]
    doc['manifest']['risk'].update(basis='missing',coverage='missing',observation_claim='missing')
    doc['payload']['risk_events']=[]; doc['completion']['event_count']=0
    trade.update(entry_fill_price='99.75',exit_fill_price='102.25',gross_pnl='10',slippage_cost='-2',net_pnl='8',excursions=None)
    assert parse_trade_export(raw(doc))['validation']['totals']['net_pnl']=='8'


def test_cme_evening_coverage_uses_chicago_dst_not_source_timezone():
    doc=envelope(); doc['manifest']['time']['source_timezone']='Asia/Singapore'
    doc['manifest']['coverage'].update(start_utc='2026-03-08T22:00:00Z',end_utc='2026-03-10T21:00:00Z',sessions=['2026-03-09','2026-03-10'])
    blob=raw(doc).replace(b'2026-01-05T',b'2026-03-09T')
    parsed=json.loads(blob)
    result=parse_trade_export(raw(parsed))
    assert result['manifest']['coverage']['sessions']==['2026-03-09','2026-03-10']
    parsed['manifest']['coverage']['start_utc']='2026-03-08T21:59:00Z'
    with pytest.raises(TradeExportError,match='endpoints'):
        parse_trade_export(raw(parsed))


def test_extrema_timestamp_must_be_an_observed_extreme_not_only_inside_trade():
    doc=envelope(); doc['payload']['trades'][0]['excursions']['mae_time_utc']='2026-01-05T15:01:00Z'
    with pytest.raises(TradeExportError,match='actual event'):
        parse_trade_export(raw(doc))


def test_next_trade_sizing_cannot_use_account_state_before_previous_trade_settlement():
    doc=envelope()
    doc['manifest']['risk'].update(basis='missing',coverage='missing',observation_claim='missing')
    doc['payload']['risk_events']=[]; doc['completion']['event_count']=0
    first=doc['payload']['trades'][0]; first.update(excursions=None,stop_updates=[])
    second=deepcopy(first); second.update(trade_id='second',entry_time_utc='2026-01-05T15:03:00Z',exit_time_utc='2026-01-05T15:05:00Z')
    second['sizing_decision']['timestamp_utc']='2026-01-05T15:01:00Z'
    doc['payload']['trades'].append(second); doc['completion']['trade_count']=2
    with pytest.raises(TradeExportError,match='previous trade settlement'):
        parse_trade_export(raw(doc))
    second['sizing_decision']['timestamp_utc']='2026-01-05T15:02:00Z'
    assert parse_trade_export(raw(doc))['validation']['totals']['net_pnl']=='8'


def test_full_precision_prices_and_money_cannot_round_under_tiny_ambient_context():
    doc=envelope(); trade=doc['payload']['trades'][0]
    doc['manifest']['risk'].update(basis='missing',coverage='missing',observation_claim='missing')
    doc['payload']['risk_events']=[]; doc['completion']['event_count']=0
    trade.update(quantity=1,entry_reference_price='123456789012345678901234567890.125',
                 exit_reference_price='123456789012345678901234567891.375',
                 entry_fill_price='123456789012345678901234567890.375',
                 exit_fill_price='123456789012345678901234567891.125',
                 reference_gross_pnl='2.5',gross_pnl='1.5',slippage_cost='1',total_commissions='0.5',
                 entry_commission='0.25',exit_commission='0.25',net_pnl='1',excursions=None,
                 initial_stop=None,stop_updates=[],sizing_decision=None)
    with localcontext() as context:
        context.prec=2; context.Emax=2; context.Emin=-2
        result=parse_trade_export(raw(doc))
        assert result['validation']['totals']['net_pnl']=='1'
        assert (getcontext().prec,getcontext().Emax,getcontext().Emin)==(2,2,-2)


def test_global_event_ownership_requires_close_before_next_open_at_tied_timestamp():
    from datetime import datetime, timedelta
    doc=envelope()
    second=deepcopy(doc['payload']['trades'][0]); second['trade_id']='second'
    events=deepcopy(doc['payload']['risk_events'])
    def advance(value):
        return (datetime.fromisoformat(value.replace('Z','+00:00'))+timedelta(minutes=2)).isoformat().replace('+00:00','Z')
    for name in ('entry_time_utc','exit_time_utc'):second[name]=advance(second[name])
    second['sizing_decision'].update(timestamp_utc=second['entry_time_utc'],execution_timing='same_close')
    second['initial_stop']['known_at_utc']=second['entry_time_utc']
    second['stop_updates'][0]['known_at_utc']=advance(second['stop_updates'][0]['known_at_utc'])
    for name in ('mae_time_utc','mfe_time_utc'):second['excursions'][name]=advance(second['excursions'][name])
    for event in events:
        event['trade_id']='second';event['timestamp_utc']=advance(event['timestamp_utc']);event['sequence']+=5
    first=deepcopy(doc['payload']['risk_events'])
    doc['payload']['trades'].append(second)
    doc['payload']['risk_events']=first+events
    doc['completion'].update(trade_count=2,event_count=10)
    assert parse_trade_export(raw(doc))['validation']['totals']['net_pnl']=='8'
    doc['payload']['risk_events']=first[:-1]+[events[0],first[-1]]+events[1:]
    for sequence,event in enumerate(doc['payload']['risk_events'],1):event['sequence']=sequence
    with pytest.raises(TradeExportError,match='previous position closes'):
        parse_trade_export(raw(doc))


@pytest.mark.parametrize('mae,mfe',[('1','4'),('6','4'),('1','6')])
def test_exporter_reported_extrema_cannot_understate_supplied_observed_marks(mae,mfe):
    doc=envelope()
    doc['payload']['trades'][0]['excursions'].update(basis='exporter_reported_net_equity',mae=mae,mfe=mfe,mae_time_utc=None,mfe_time_utc=None)
    with pytest.raises(TradeExportError,match='understate'):
        parse_trade_export(raw(doc))


def test_larger_reported_extrema_preserve_unknown_path_as_explicit_gap():
    doc=envelope()
    doc['payload']['trades'][0]['excursions'].update(basis='exporter_reported_net_equity',mae='10',mfe='12',mae_time_utc=None,mfe_time_utc=None)
    result=parse_trade_export(raw(doc))
    assert result['trades'][0]['excursions']['mae']=='10'
    assert result['trades'][0]['excursions']['mfe']=='12'
    assert result['risk_events']==doc['payload']['risk_events']
    assert result['validation']['unobserved_extrema_trade_ids']==['mc-42']
    assert result['validation']['ordered_path_covers_reported_extrema'] is False
    assert 'cannot be reconstructed' in result['validation']['risk_path_disclosure']
    assert result['capabilities']['prop_analysis'] is False
