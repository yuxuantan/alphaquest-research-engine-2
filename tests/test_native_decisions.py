"""Staged native decision evidence; all fixture expectations are independent."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path

import pytest

from alphaquest.decision_capture import DecisionEvent, DecisionRecorder, SIDE_CAR, VERSION
from alphaquest.execution import EquityPoint, ExecutionError, Trade, execute
from alphaquest.reporting import ReportError, generate_report
from alphaquest.strategy import Bar, BracketIntent, CloseIntent, EntryIntent, ExecutionConfig

D=Decimal
START=datetime(2026,1,5,15,tzinfo=timezone.utc)
CONFIG=ExecutionConfig(D('10000'),D('.25'),D('2'),1,D('1'))


def bar(number,close='100',*,open=None,low=None,high=None):
    close=D(close);opening=D(open) if open is not None else close
    lower=D(low) if low is not None else min(opening,close)
    upper=D(high) if high is not None else max(opening,close)
    stamp=START+timedelta(minutes=number-1)
    return Bar(number,stamp,stamp.strftime('%m/%d/%Y'),stamp.strftime('%H:%M'),opening,upper,lower,close,D(1),D(0),D(0),())


class Scheduled:
    def __init__(self,orders,*,allow=True,finish=True):self.orders=orders;self.allow=allow;self.finish=finish
    def on_bar(self,bar,position):return self.orders.get(bar.bar_number)
    def allow_entry_fill(self,bar):return self.allow
    def on_finish(self,bar,position):return CloseIntent('end_of_data') if self.finish and position else None


def source():
    return [bar(1),bar(2,'106',open='105',low='104',high='107'),
            bar(3,'107',open='106',low='105',high='108'),bar(4,'108',open='107',low='107',high='109')]


def strategy():
    return Scheduled({1:EntryIntent(2,'signal',timing='next_open',initial_stop=D('99')),
                      2:BracketIntent(D('99'),D('110')),3:BracketIntent(D('100'),D('110')),
                      4:CloseIntent('exit')})


def only_decisions(events):return [event for event in events if type(event) is DecisionEvent]




def test_causal_initial_stop_and_decision_price_separate_from_actual_gap_fill(tmp_path):
    events=list(execute(source(),strategy(),CONFIG,capture_risk=True,capture_decisions=True))
    decisions=only_decisions(events)
    assert [event.kind for event in decisions]==['entry_decision','entry_fill','bracket_submission','bracket_submission','trade_close']
    signal,filled,first_bracket,updated,closed=decisions
    assert (signal.decision_id,signal.trade_number,signal.bar_number,signal.timestamp_utc,signal.reference_price,signal.stop_price)==(1,None,1,START,D('100'),D('99'))
    assert signal.execution_timing=='next_open' and signal.fill_price is None and signal.net_pnl is None
    assert (filled.trade_number,filled.bar_number,filled.timestamp_utc,filled.reference_price,filled.fill_price)==(1,2,START+timedelta(minutes=1),D('105'),D('105.25'))
    assert first_bracket.timestamp_utc==filled.timestamp_utc and first_bracket.stop_price==D('99')
    assert updated.stop_price==D('100') and updated.bar_number==3
    assert closed.net_pnl==D('6')
    report=generate_report(events,tmp_path/'captured',CONFIG,expected_bar_count=4,capture_risk=True,capture_decisions=True)
    data=(tmp_path/'captured'/SIDE_CAR).read_bytes()
    assert report['execution_decisions']['sha256']==sha256(data).hexdigest()
    assert report['execution_decisions']['version']==VERSION
    assert report['execution_decisions']['events']==5 and report['execution_decisions']['filled_trades']==1
    assert report['execution_decisions']['quantity_path_policy']=='native_rerun_required'
    records=[json.loads(line) for line in data.splitlines()]
    assert records[0]['initial_stop_activation'].startswith('metadata_only')
    assert records[0]['bracket_activation']=='next_observed_bar_only'
    assert records[1]['reference_price']=='100' and records[2]['fill_price']=='105.25'
    assert records[-1]['kind']=='completion' and records[-1]['status']=='complete'


def test_original_trade_equity_and_risk_csv_bytes_unchanged_with_capture(tmp_path):
    baseline=list(execute(source(),strategy(),CONFIG,capture_risk=True))
    captured=list(execute(source(),strategy(),CONFIG,capture_risk=True,capture_decisions=True))
    assert [asdict(event) for event in captured if type(event) is not DecisionEvent]==[asdict(event) for event in baseline]
    first=generate_report(baseline,tmp_path/'baseline',CONFIG,capture_risk=True)
    second=generate_report(captured,tmp_path/'capture',CONFIG,capture_risk=True,capture_decisions=True)
    assert first['summary']==second['summary']
    for name in ('trades.csv','equity.csv','intratrade_risk.csv'):
        assert (tmp_path/'baseline'/name).read_bytes()==(tmp_path/'capture'/name).read_bytes()
    assert not (tmp_path/'baseline'/SIDE_CAR).exists()




def test_future_bar_mutation_cannot_change_saved_decision_or_initial_stop():
    first=only_decisions(list(execute(source(),strategy(),CONFIG,capture_decisions=True)))[0]
    mutated=source();mutated[1]=bar(2,'109',open='108',low='107',high='109')
    other=only_decisions(list(execute(mutated,strategy(),CONFIG,capture_decisions=True)))
    assert other[0]==first
    assert other[1].fill_price==D('108.25')


def test_capture_does_not_prefetch_future_bar_before_signal_evidence():
    advanced=[]
    def bars():
        advanced.append(1);yield bar(1)
        advanced.append(2);yield bar(2,'101')
    events=execute(bars(),Scheduled({1:EntryIntent(1,'signal',timing='next_open',initial_stop=D(99))}),CONFIG,capture_decisions=True)
    assert type(next(events)) is EquityPoint
    decision=next(events)
    assert type(decision) is DecisionEvent and decision.kind=='entry_decision'
    assert advanced==[1]
    list(events)
    assert advanced==[1,2]


@pytest.mark.parametrize('timing',['same_close','next_open'])
def test_absent_initial_stop_remains_missing_despite_later_bracket(timing,tmp_path):
    orders={1:EntryIntent(1,'no causal stop',timing=timing),2:BracketIntent(D('99'),D('110'))}
    events=list(execute([bar(1),bar(2,'101'),bar(3,'102')],Scheduled(orders),CONFIG,capture_decisions=True))
    decisions=only_decisions(events)
    assert decisions[0].stop_price is None
    assert next(e for e in decisions if e.kind=='bracket_submission').stop_price==D('99')
    generate_report(events,tmp_path/'report',CONFIG,capture_decisions=True)


@pytest.mark.parametrize('cancelled', ['guard','eof'])
def test_unfilled_signals_retained_without_fake_trade_or_future_fill(cancelled,tmp_path):
    bars=[bar(1)] if cancelled=='eof' else [bar(1),bar(2)]
    strategy=Scheduled({1:EntryIntent(1,'signal',timing='next_open',initial_stop=D('99'))},allow=cancelled!='guard')
    events=list(execute(bars,strategy,CONFIG,capture_decisions=True))
    decisions=only_decisions(events)
    assert [event.kind for event in decisions]==['entry_decision','entry_cancelled']
    assert decisions[1].reason==('end_of_data_before_fill' if cancelled=='eof' else 'entry_guard_rejected')
    assert decisions[1].trade_number is None and decisions[1].fill_price is None
    report=generate_report(events,tmp_path/'report',CONFIG,capture_decisions=True)
    assert report['summary']['trades_taken']==0
    assert report['execution_decisions']['cancelled_decisions']==1


@pytest.mark.parametrize('side,stop',[('long','100'),('long','101'),('short','100'),('short','99')])
def test_initial_stop_wrong_side_rejects_before_future_fill(side,stop):
    strategy=Scheduled({1:EntryIntent(1,'bad metadata',side=side,timing='next_open',initial_stop=D(stop))})
    with pytest.raises(ExecutionError,match='adverse'):
        list(execute([bar(1),bar(2)],strategy,CONFIG,capture_decisions=True))


@pytest.mark.parametrize('stop',[float('nan'),D('NaN'),D('Infinity'),'99',True])
def test_initial_stop_requires_finite_decimal(stop):
    with pytest.raises(ValueError,match='finite Decimal'):
        EntryIntent(1,'signal',initial_stop=stop)


def test_report_rejects_missing_or_mismatched_capture(tmp_path):
    captured=list(execute(source(),strategy(),CONFIG,capture_decisions=True))
    with pytest.raises(ReportError,match='capture_decisions'):
        generate_report(captured,tmp_path/'wrong-mode',CONFIG)
    baseline=list(execute(source(),strategy(),CONFIG))
    with pytest.raises(ValueError,match='coverage'):
        generate_report(baseline,tmp_path/'missing',CONFIG,capture_decisions=True)
    modified=[replace(e,reference_price=D('999')) if type(e) is DecisionEvent and e.kind=='entry_fill' else e for e in captured]
    with pytest.raises(ValueError,match='entry outcome differs'):
        generate_report(modified,tmp_path/'modified',CONFIG,capture_decisions=True)
    assert not (tmp_path/'missing').exists() and not (tmp_path/'modified').exists()


@pytest.mark.parametrize('short',[False,True])
def test_real_vwap_signal_captures_stop_before_next_open_without_changing_trade(short,tmp_path):
    from test_vwap_pullback import scenario,parameters,CONFIG as vwap_config
    from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
    bars=scenario(short=short)
    strategy=VwapPullbackRiskSizing(parameters(trade_longs=not short,trade_shorts=short),execution_config=vwap_config)
    events=list(execute(bars,strategy,vwap_config,capture_risk=True,capture_decisions=True))
    decisions=only_decisions(events)
    signal,filled,bracket,closed=decisions
    assert signal.kind=='entry_decision' and signal.bar_number==122
    assert signal.reference_price==D('92' if short else '108')
    assert signal.stop_price==D('110' if short else '90')
    assert filled.fill_price==D('84.75' if short else '115.25')
    assert filled.bar_number==123 and signal.timestamp_utc<filled.timestamp_utc
    assert bracket.kind=='bracket_submission' and bracket.bar_number==123
    assert closed.net_pnl==D('293')
    report=generate_report(events,tmp_path/'report',vwap_config,capture_risk=True,capture_decisions=True)
    assert report['summary']['total_net_pnl']==D('293')


def native_report(tmp_path,*,capture=True):
    from uuid import uuid4
    from alphaquest.backtest_runs import RunStore
    runs=RunStore(tmp_path)
    id=uuid4().hex
    events=execute(source(),strategy(),CONFIG,capture_risk=True,capture_decisions=capture)
    metadata=dict(dataset=dict(id='synthetic-dataset',name='SYNTHETIC',sha256='1'*64,source_timezone='UTC'),strategy=dict(id='synthetic',parameters={}))
    output=tmp_path/'pending'
    report=generate_report(events,output,CONFIG,capture_risk=True,capture_decisions=capture,metadata=metadata)
    record=runs.complete(id,output,report)
    return runs,record


def test_canonical_native_projection_reads_exact_causal_sidecar_and_keeps_historical_missing(tmp_path):
    from alphaquest.canonical_trades import project_native_source
    runs,record=native_report(tmp_path/'new')
    before={p.name:p.read_bytes() for p in (runs.root/record['id']).iterdir()}
    projected=project_native_source(runs,record['id'])
    trade=projected['trades'][0]
    assert trade['sizing_decision']==dict(timestamp_utc=START.isoformat().replace('+00:00','Z'),reference_price='100',execution_timing='next_open')
    assert trade['initial_stop']==dict(price='99',known_at_utc=START.isoformat().replace('+00:00','Z'),basis='strategy_decision')
    assert trade['decision_evidence']['entry_outcome']['fill_price']=='105.25'
    assert trade['stop_updates']==[dict(price='99',known_at_utc=(START+timedelta(minutes=1)).isoformat().replace('+00:00','Z'),basis='submitted_order'),dict(price='100',known_at_utc=(START+timedelta(minutes=2)).isoformat().replace('+00:00','Z'),basis='submitted_order')]
    assert projected['source']['artifact_sha256'][SIDE_CAR]==sha256(before[SIDE_CAR]).hexdigest()
    assert projected['capabilities']['quantity_path_policy']=='native_rerun_required'
    assert projected['capabilities']['sizing_path_invariance_verified'] is False
    assert before=={p.name:p.read_bytes() for p in (runs.root/record['id']).iterdir()}
    old_runs,old_record=native_report(tmp_path/'old',capture=False)
    old=project_native_source(old_runs,old_record['id'])
    assert old['trades'][0]['sizing_decision'] is None and old['trades'][0]['initial_stop'] is None
    assert old['native_decisions'] is None


@pytest.mark.parametrize('mutation',['hash','missing','future_signal','fill_mismatch','completion','duplicate_key'])
def test_native_sidecar_tamper_or_partial_never_becomes_sizing_evidence(tmp_path,mutation):
    from alphaquest.decision_capture import read_decision_evidence
    import csv
    runs,record=native_report(tmp_path)
    path=runs.root/record['id']/SIDE_CAR
    with (runs.root/record['id']/'trades.csv').open() as stream:trades=list(csv.DictReader(stream))
    description=dict(record['execution_decisions'])
    content=path.read_bytes()
    if mutation=='missing':
        path.unlink()
    elif mutation=='hash':
        path.write_bytes(content+b'\n')
    elif mutation=='duplicate_key':
        path.write_bytes(content.replace(b'"sequence":1',b'"sequence":1,"sequence":1',1));description['sha256']=sha256(path.read_bytes()).hexdigest()
    else:
        rows=[json.loads(line) for line in content.splitlines()]
        if mutation=='future_signal':rows[1]['timestamp_utc']='2026-01-05T15:02:00Z'
        elif mutation=='fill_mismatch':rows[2]['fill_price']='999'
        elif mutation=='completion':rows.pop()
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows));description['sha256']=sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):read_decision_evidence(path,description,trades,record['execution_settings'])
