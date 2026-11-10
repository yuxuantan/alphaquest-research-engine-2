"""Causal native decision provenance, separate from unchanged trade/price data.

An initial stop is decision metadata, never an assertion that a protective
order was active at entry. Brackets become active for the next observed bar.
A changed or skipped quantity may alter strategy state; native rerun is required
until a particular strategy's virtual signal path has been qualified.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import json

VERSION = 'native-entry-decisions-v1'
SIDE_CAR = 'execution_decisions.jsonl'


@dataclass(frozen=True, slots=True)
class DecisionEvent:
    sequence: int
    kind: str
    decision_id: int
    trade_number: int | None
    bar_number: int
    timestamp_utc: datetime
    side: str
    contracts: int
    reference_price: Decimal | None = None
    fill_price: Decimal | None = None
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    net_pnl: Decimal | None = None
    execution_timing: str | None = None
    reason: str = ''


def serial(value):
    if isinstance(value, Decimal) and value.is_finite():
        return str(value)
    if isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() == timedelta(0):
        return value.isoformat().replace('+00:00', 'Z')
    raise TypeError('Unsupported decision evidence value.')


def line(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=serial, allow_nan=False) + '\n'


def require(condition, message):
    if not condition:
        raise ValueError('Invalid native decision evidence: ' + message)


class DecisionRecorder:
    """Single-position streaming validation and durable JSONL serialization."""
    def __init__(self, stream, execution_settings):
        self.stream = stream
        self.sequence = self.decisions = self.filled = self.cancelled = self.closed = self.brackets = 0
        self.pending = self.active = self.fill = None
        self.previous_time = None
        stream.write(line(dict(kind='header', version=VERSION, timestamp_convention='bar_close',
            decision_reference='current_completed_bar_close', initial_stop_basis='strategy_decision',
            initial_stop_activation='metadata_only; protective orders require a bracket_submission',
            bracket_activation='next_observed_bar_only', execution_settings=execution_settings,
            quantity_path_policy='native_rerun_required',
            quantity_path_limitation='Changing/skipping fills can change position callbacks, latches and daily trade limits; no state-independent or virtual signal path is certified.')))

    def observe(self, event, trade=None):
        require(type(event) is DecisionEvent, 'unsupported event type')
        require(type(event.sequence) is int and event.sequence == self.sequence + 1, 'event sequence must be contiguous')
        require(type(event.decision_id) is int and event.decision_id > 0, 'decision ID must be positive')
        require(type(event.bar_number) is int and event.bar_number > 0, 'bar number must be positive')
        require(isinstance(event.timestamp_utc, datetime) and event.timestamp_utc.tzinfo is not None and event.timestamp_utc.utcoffset() == timedelta(0), 'timestamp must be UTC')
        require(self.previous_time is None or event.timestamp_utc >= self.previous_time, 'timestamps must be chronological')
        require(event.side in ('long','short') and type(event.contracts) is int and event.contracts > 0, 'invalid side/quantity')
        for field in ('reference_price','fill_price','stop_price','target_price','net_pnl'):
            value=getattr(event,field)
            require(value is None or isinstance(value,Decimal) and value.is_finite(), 'non-finite decimal')
        require(type(event.reason) is str and event.reason, 'event needs a reason')
        if event.kind == 'entry_decision':
            require(self.pending is None and self.active is None, 'entry decision while another is pending or holding')
            require(event.decision_id == self.decisions + 1 and event.trade_number is None, 'invalid new decision identity')
            require(event.execution_timing in ('same_close','next_open') and event.reference_price is not None, 'entry decision needs current-close reference and timing')
            require(event.fill_price is None and event.target_price is None and event.net_pnl is None, 'decision cannot contain future outcomes')
            if event.stop_price is not None:
                require(event.stop_price < event.reference_price if event.side == 'long' else event.stop_price > event.reference_price, 'initial stop is not adverse to decision price')
            self.decisions += 1; self.pending=event
        elif event.kind in ('entry_fill','entry_cancelled'):
            require(self.pending is not None and self.active is None and event.decision_id == self.pending.decision_id, 'pending decision identity differs')
            require((event.side,event.contracts)==(self.pending.side,self.pending.contracts), 'pending quantity/side differs')
            require(event.stop_price is None and event.target_price is None and event.net_pnl is None and event.execution_timing is None, 'outcome carries unsupported metadata')
            if event.kind == 'entry_fill':
                require(event.trade_number == self.closed + 1 and event.reference_price is not None and event.fill_price is not None, 'filled trade identity/prices missing')
                if self.pending.execution_timing == 'next_open':
                    require(event.timestamp_utc > self.pending.timestamp_utc and event.bar_number > self.pending.bar_number, 'next-open fill cannot occur at or before decision')
                else:
                    require((event.timestamp_utc,event.bar_number,event.reference_price)==(self.pending.timestamp_utc,self.pending.bar_number,self.pending.reference_price), 'same-close outcome differs from decision')
                self.active,self.fill=self.pending,event;self.filled+=1
            else:
                require(event.trade_number is None and event.reference_price is None and event.fill_price is None, 'cancelled signal must not fabricate a fill')
                require(event.reason in ('entry_guard_rejected','end_of_data_before_fill'), 'unknown cancellation policy')
                self.cancelled += 1
            self.pending=None
        elif event.kind in ('bracket_submission','trade_close'):
            require(self.active is not None and self.fill is not None and event.decision_id == self.active.decision_id, 'active decision identity differs')
            require(event.trade_number == self.fill.trade_number and (event.side,event.contracts)==(self.fill.side,self.fill.contracts), 'active trade identity/quantity differs')
            require(event.execution_timing is None, 'only the entry decision declares entry timing')
            if event.kind == 'bracket_submission':
                require(event.stop_price is not None and event.reference_price is not None and event.fill_price is None and event.net_pnl is None, 'bracket has incomplete or future fields')
                require(event.target_price is None or (event.stop_price < event.target_price if event.side == 'long' else event.stop_price > event.target_price), 'bracket order conflicts with side')
                self.brackets += 1
            else:
                require(trade is not None, 'close evidence must follow its completed trade')
                require((event.trade_number,event.timestamp_utc,event.bar_number,event.reference_price,event.fill_price,event.net_pnl,event.side,event.contracts)==
                        (trade.trade_number,trade.exit_time_utc,trade.exit_bar_number,trade.exit_reference_price,trade.exit_fill_price,trade.net_pnl,trade.side,trade.contracts), 'close outcome differs from completed trade')
                require((self.fill.timestamp_utc,self.fill.bar_number,self.fill.reference_price,self.fill.fill_price)==
                        (trade.entry_time_utc,trade.entry_bar_number,trade.entry_reference_price,trade.entry_fill_price), 'entry outcome differs from completed trade')
                require(event.stop_price is None and event.target_price is None, 'close cannot invent a stop')
                self.active=self.fill=None;self.closed+=1
        else:
            raise ValueError('Invalid native decision evidence: unsupported event kind')
        self.sequence=event.sequence;self.previous_time=event.timestamp_utc
        self.stream.write(line(asdict(event)))

    def finish(self, trade_count):
        require(self.pending is None and self.active is None, 'unresolved final signal or open position')
        require(self.filled == self.closed == trade_count and self.decisions == self.filled + self.cancelled, 'coverage does not reconcile to completed trades')
        result=dict(version=VERSION, events=self.sequence, decisions=self.decisions, filled_trades=self.filled,
                    cancelled_decisions=self.cancelled, bracket_submissions=self.brackets,
                    quantity_path_policy='native_rerun_required')
        self.stream.write(line(dict(kind='completion',status='complete',**result)))
        return result


def read_decision_evidence(path, description, trades, execution_settings):
    """Verify a sidecar against completed native trades; never infer absent stops.

    Returned decision prices are observed signal closes. The native fill's
    opening reference/fill prices remain separate outcomes. No sizing policy
    may treat these observed outcomes as pre-entry planning inputs.
    """
    from hashlib import sha256
    from pathlib import Path
    from types import SimpleNamespace
    path=Path(path)
    require(description.get('version') == VERSION, 'unsupported sidecar version')
    require(path.name == SIDE_CAR and not path.is_symlink() and path.is_file(), 'missing or unsafe sidecar path')
    before=sha256(path.read_bytes()).hexdigest()
    require(before == description.get('sha256'), 'sidecar SHA-256 differs')
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key]=value
        return result
    def parse(record):
        try:return json.loads(record,object_pairs_hook=unique)
        except (json.JSONDecodeError,UnicodeDecodeError,RecursionError) as exc:
            raise ValueError('Invalid native decision JSONL.') from exc
    by_id={int(t['trade_number']):t for t in trades}
    require(len(by_id)==len(trades), 'duplicate native trade IDs')
    class Sink:
        def write(self,value):pass
    recorder=None;header=completion=None;projected={};cancelled=[];pending=None
    with path.open(encoding='utf-8',newline='') as stream:
        for ordinal,text in enumerate(stream):
            require(text.endswith('\n'), 'truncated JSONL line')
            value=parse(text)
            require(type(value) is dict, 'records must be objects')
            if ordinal==0:
                header=value
                expected=DecisionRecorder(Sink(),execution_settings)
                capture=__import__('io').StringIO()
                DecisionRecorder(capture,execution_settings)
                require(value==parse(capture.getvalue()), 'header contract or execution settings differ')
                recorder=expected
                continue
            require(completion is None, 'records follow completion marker')
            if value.get('kind')=='completion':
                completion=value
                expected=recorder.finish(len(trades))
                require(value==dict(kind='completion',status='complete',**expected), 'completion counters differ')
                require(all(description.get(key)==item for key,item in expected.items()), 'saved manifest coverage differs')
                continue
            from dataclasses import fields
            require(set(value)=={field.name for field in fields(DecisionEvent)}, 'event fields differ')
            original=dict(value)
            try:
                value['timestamp_utc']=datetime.fromisoformat(value['timestamp_utc'].replace('Z','+00:00'))
                for key in ('reference_price','fill_price','stop_price','target_price','net_pnl'):
                    if value[key] is not None:
                        require(type(value[key]) is str, 'money must remain decimal strings')
                        value[key]=Decimal(value[key])
                event=DecisionEvent(**value)
            except (TypeError,ValueError,ArithmeticError) as exc:
                raise ValueError('Invalid native decision event values.') from exc
            trade=None
            if event.kind=='trade_close':
                require(event.trade_number in by_id, 'unknown completed trade ID')
                row=by_id[event.trade_number]
                trade=SimpleNamespace(**{key:(int(row[key]) if key in ('trade_number','contracts','entry_bar_number','exit_bar_number') else
                    datetime.fromisoformat(row[key].replace('Z','+00:00')) if key in ('entry_time_utc','exit_time_utc') else
                    Decimal(row[key]) if key in ('entry_reference_price','entry_fill_price','exit_reference_price','exit_fill_price','net_pnl') else row[key])
                    for key in ('trade_number','contracts','entry_bar_number','exit_bar_number','entry_time_utc','exit_time_utc','entry_reference_price','entry_fill_price','exit_reference_price','exit_fill_price','net_pnl','side')})
            recorder.observe(event,trade)
            if event.kind=='entry_decision':
                pending=original
            elif event.kind=='entry_fill':
                projected[str(event.trade_number)]=dict(decision_id=event.decision_id,
                    sizing_decision=dict(timestamp_utc=pending['timestamp_utc'],reference_price=pending['reference_price'],execution_timing=pending['execution_timing']),
                    initial_stop=(dict(price=pending['stop_price'],known_at_utc=pending['timestamp_utc'],basis='strategy_decision') if pending['stop_price'] is not None else None),
                    stop_updates=[],entry_decision=pending,entry_outcome=original,bracket_submissions=[],close_outcome=None,
                    quantity_path_policy='native_rerun_required')
                pending=None
            elif event.kind=='bracket_submission':
                record=projected[str(event.trade_number)]
                record['bracket_submissions'].append(original)
                record['stop_updates'].append(dict(price=original['stop_price'],known_at_utc=original['timestamp_utc'],basis='submitted_order'))
            elif event.kind=='trade_close':
                projected[str(event.trade_number)]['close_outcome']=original
            elif event.kind=='entry_cancelled':
                cancelled.append(dict(decision=pending,outcome=original));pending=None
    require(header is not None and completion is not None, 'sidecar lacks header or complete marker')
    require(set(projected)=={str(key) for key in by_id}, 'sidecar trade membership differs')
    require(sha256(path.read_bytes()).hexdigest()==before, 'sidecar changed during verification')
    return dict(header=header,trades=projected,cancelled_decisions=cancelled,completion=completion)
