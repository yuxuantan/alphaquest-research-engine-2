"""Strict aq-trade-export-v1 ingestion and lossless native source projection.

This module does not publish a report, synthesize bars/stops, certify exporter
coverage, or implement prop risk replay. All amounts are whole-trade account
currency. Actual fills include slippage; net subtracts commissions only.
"""
from __future__ import annotations

import csv
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Context, Decimal, Inexact, InvalidOperation, Overflow, localcontext
from hashlib import sha256
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA_VERSION = 'aq-trade-export-v1'
NORMALIZED_VERSION = 'aq-canonical-trade-source-v1'
SESSION_CONVENTION = 'cme_chicago_1700_v1'
MAX_EXPORT_BYTES = 32 * 1024 * 1024
MAX_TRADES = 100_000
MAX_EVENTS = 1_000_000
_DECIMAL = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_UTC = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)\Z')
ZERO = Decimal(0)
MONEY_FIELDS = ('reference_gross_pnl', 'slippage_cost', 'total_commissions', 'gross_pnl', 'net_pnl')


class TradeExportError(ValueError):
    """The export is not a complete, reconciled supported source."""


def _require(condition, message):
    if not condition:
        raise TradeExportError(message)


def _object(value, keys, path):
    _require(type(value) is dict, f'{path} must be an object.')
    missing, extra = set(keys) - value.keys(), value.keys() - set(keys)
    _require(not missing and not extra, f'{path} fields differ: missing={sorted(missing)}, unknown={sorted(extra)}.')
    return value


def _text(value, path, *, nullable=False):
    if value is None and nullable:
        return value
    _require(type(value) is str and 0 < len(value) <= 4096 and value.strip() == value and '\x00' not in value,
             f'{path} must be nonempty text without outer whitespace.')
    return value


def _enum(value, choices, path):
    _require(type(value) is str and value in choices, f'{path} must be one of {sorted(choices)}.')
    return value


def _integer(value, path, *, minimum=0, maximum=1_000_000_000):
    _require(type(value) is int and minimum <= value <= maximum, f'{path} must be an integer from {minimum} to {maximum}.')
    return value


def _decimal(value, path, *, nonnegative=False, positive=False):
    _require(type(value) is str and len(value) <= 196 and _DECIMAL.fullmatch(value) is not None,
             f'{path} must be a finite plain decimal string (no exponent).')
    number = Decimal(value)
    _require(len(number.as_tuple().digits) <= 128 and -number.as_tuple().exponent <= 64,
             f'{path} exceeds 128 digits or 64 decimal places.')
    _require(not nonnegative or number >= ZERO, f'{path} must be nonnegative.')
    _require(not positive or number > ZERO, f'{path} must be positive.')
    return number


def _timestamp(value, path):
    _require(type(value) is str and _UTC.fullmatch(value) is not None, f'{path} must be an explicit UTC timestamp.')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise TradeExportError(f'{path} is not a valid UTC timestamp.') from exc


def _hash(value, path, *, nullable=False):
    _require((nullable and value is None) or (type(value) is str and _SHA.fullmatch(value) is not None),
             f'{path} must be a lower-case SHA-256 digest' + (' or null.' if nullable else '.'))


def _session(stamp):
    local = stamp.astimezone(ZoneInfo('America/Chicago'))
    return (local.replace(tzinfo=None) + timedelta(hours=7)).date().isoformat()


def _json_tree(value, path='value', depth=0):
    _require(depth <= 32, f'{path} exceeds the JSON nesting limit.')
    _require(type(value) in (dict, list, str, int, bool, type(None)), f'{path} contains unsupported JSON values; decimals must be strings.')
    if type(value) is dict:
        for key, item in value.items():
            _text(key, f'{path} key')
            _json_tree(item, f'{path}.{key}', depth + 1)
    elif type(value) is list:
        for item in value:
            _json_tree(item, path, depth + 1)
    elif type(value) is str:
        _require(len(value) <= 16384 and '\x00' not in value, f'{path} text is too long or contains NUL.')
    elif type(value) is int:
        _require(abs(value) <= 10**18, f'{path} integer is too large; use a decimal string.')


def canonical_payload_sha256(payload: dict) -> str:
    """Hash exact v1 canonical payload UTF-8; this is not the raw file hash.

    Object keys are sorted, arrays retain order, whitespace is absent, Unicode
    stays UTF-8, and decimal strings retain their exact spelling.
    """
    _require(type(payload) is dict, 'Canonical payload must be an object.')
    _json_tree(payload, 'payload')
    return sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                             allow_nan=False).encode('utf-8')).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f'Duplicate JSON key: {key}.')
        result[key] = value
    return result


def _bad_number(value):
    raise TradeExportError('JSON floating-point and non-finite numbers are unsupported; use decimal strings.')


def _manifest(m):
    _object(m, ('origin', 'exporter_build', 'platform', 'strategy', 'dataset', 'instrument', 'time',
                'coverage', 'research', 'execution', 'risk', 'initial_capital'), 'manifest')
    _enum(m['origin'], {'alphaquest', 'multicharts_dotnet', 'external'}, 'manifest.origin')
    _text(m['exporter_build'], 'manifest.exporter_build')
    _decimal(m['initial_capital'], 'manifest.initial_capital', positive=True)
    p = _object(m['platform'], ('edition', 'build', 'bitness'), 'manifest.platform')
    for name in ('edition', 'build'):
        _text(p[name], 'platform.' + name)
    _require(p['bitness'] is None or type(p['bitness']) is int and p['bitness'] in (32, 64), 'platform.bitness must be 32, 64 or null.')
    s = _object(m['strategy'], ('id', 'parameters', 'implementation_sha256'), 'manifest.strategy')
    _text(s['id'], 'strategy.id')
    _require(type(s['parameters']) is dict, 'strategy.parameters must be an object.')
    _hash(s['implementation_sha256'], 'strategy.implementation_sha256')
    d = _object(m['dataset'], ('name', 'sha256', 'contract', 'adjustment'), 'manifest.dataset')
    for name in ('name', 'contract', 'adjustment'):
        _text(d[name], 'dataset.' + name)
    _hash(d['sha256'], 'dataset.sha256')
    i = _object(m['instrument'], ('symbol', 'currency', 'tick_size', 'point_value'), 'manifest.instrument')
    _text(i['symbol'], 'instrument.symbol')
    _require(type(i['currency']) is str and re.fullmatch('[A-Z]{3}', i['currency']) is not None, 'instrument.currency must be an uppercase three-letter code.')
    _decimal(i['tick_size'], 'instrument.tick_size', positive=True)
    point_value = _decimal(i['point_value'], 'instrument.point_value', positive=True)
    t = _object(m['time'], ('timestamp_basis', 'source_timezone', 'session_convention', 'bar_interval_seconds'), 'manifest.time')
    _enum(t['timestamp_basis'], {'actual_fill', 'bar_open', 'bar_close', 'unknown'}, 'time.timestamp_basis')
    _text(t['source_timezone'], 'time.source_timezone')
    try:
        ZoneInfo(t['source_timezone'])
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise TradeExportError('Unknown source timezone.') from exc
    _require(t['session_convention'] == SESSION_CONVENTION, 'Unsupported session convention.')
    if t['bar_interval_seconds'] is not None:
        _integer(t['bar_interval_seconds'], 'time.bar_interval_seconds', minimum=1)
    if t['timestamp_basis'] in ('bar_open', 'bar_close'):
        _require(t['bar_interval_seconds'] is not None, 'Bar timestamp basis requires bar_interval_seconds.')
    c = _object(m['coverage'], ('start_utc', 'end_utc', 'sessions', 'calendar_id', 'calendar_sha256', 'completion'), 'manifest.coverage')
    start, end = _timestamp(c['start_utc'], 'coverage.start_utc'), _timestamp(c['end_utc'], 'coverage.end_utc')
    _require(start < end, 'Coverage must have positive duration.')
    _text(c['calendar_id'], 'coverage.calendar_id')
    _hash(c['calendar_sha256'], 'coverage.calendar_sha256')
    _require(c['completion'] == 'exporter_declared_complete', 'Coverage must be explicitly exporter_declared_complete.')
    sessions = c['sessions']
    _require(type(sessions) is list and 0 < len(sessions) <= 100_000, 'Coverage requires a nonempty bounded session inventory.')
    previous = None
    for value in sessions:
        try:
            _require(type(value) is str and date.fromisoformat(value).isoformat() == value, 'Sessions must use exact ISO dates.')
        except ValueError as exc:
            raise TradeExportError('Sessions must use exact ISO dates.') from exc
        _require(previous is None or value > previous, 'Sessions must be unique and strictly chronological.')
        _require(_session(start) <= value <= _session(end), 'Declared session lies outside coverage interval.')
        previous = value
    _require(sessions[0] == _session(start) and sessions[-1] == _session(end), 'Coverage endpoints must belong to declared first/last sessions.')
    r = _object(m['research'], ('phase', 'declaration', 'prior_access'), 'manifest.research')
    _enum(r['phase'], {'is', 'oos', 'unspecified'}, 'research.phase')
    _text(r['declaration'], 'research.declaration')
    _enum(r['prior_access'], {'unknown', 'accessed', 'exporter_declared_unaccessed'}, 'research.prior_access')
    e = _object(m['execution'], ('position_model', 'sizing_path_invariance', 'cost_basis', 'fill_assumption', 'assumptions'), 'manifest.execution')
    _require(e['position_model'] == 'nonoverlapping_constant_quantity_round_trips', 'Unsupported position model.')
    _enum(e['sizing_path_invariance'], {'unverified', 'exporter_declared'}, 'execution.sizing_path_invariance')
    _require(e['cost_basis'] == 'actual_per_trade', 'Unsupported cost basis.')
    _text(e['fill_assumption'], 'execution.fill_assumption')
    _require(type(e['assumptions']) is list and len(e['assumptions']) <= 100, 'execution.assumptions must be a bounded list.')
    for value in e['assumptions']:
        _text(value, 'execution.assumptions item')
    risk = _object(m['risk'], ('basis', 'coverage', 'units', 'equity_basis', 'observation_claim'), 'manifest.risk')
    _enum(risk['basis'], {'ordered_marks', 'measured_extrema', 'missing', 'unknown'}, 'risk.basis')
    _enum(risk['coverage'], {'complete', 'partial', 'missing', 'unknown'}, 'risk.coverage')
    _require(risk['units'] == 'whole_trade_account_currency', 'Unsupported risk units.')
    _require(risk['equity_basis'] == 'actual_fill_pnl_less_commissions_charged', 'Unsupported risk equity/cost basis.')
    _enum(risk['observation_claim'], {'exporter_declared', 'missing', 'unknown'}, 'risk.observation_claim')
    if risk['basis'] in ('missing', 'unknown'):
        _require(risk['coverage'] == risk['basis'] and risk['observation_claim'] == risk['basis'], 'Missing and unknown risk must remain distinct declarations.')
    else:
        _require(risk['coverage'] in ('complete', 'partial') and risk['observation_claim'] == 'exporter_declared', 'Observed risk requires an explicit exporter declaration.')
    return point_value, start, end, set(sessions)


def _stop(value, trade, path, *, initial):
    _object(value, ('price', 'known_at_utc', 'basis'), path)
    price = _decimal(value['price'], path + '.price')
    known = _timestamp(value['known_at_utc'], path + '.known_at_utc')
    _enum(value['basis'], {'submitted_order', 'strategy_decision'}, path + '.basis')
    entry, exit = _timestamp(trade['entry_time_utc'], path), _timestamp(trade['exit_time_utc'], path)
    if initial:
        _require(known <= entry, 'Initial stop must be known no later than entry; it cannot be inferred after entry.')
        if trade['sizing_decision'] is not None:
            decision = trade['sizing_decision']
            _require(known <= _timestamp(decision['timestamp_utc'], 'sizing_decision.timestamp_utc'), 'Initial stop must be known by the sizing decision.')
            reference = _decimal(decision['reference_price'], 'sizing_decision.reference_price')
            _require(price < reference if trade['side'] == 'long' else price > reference, 'Initial stop must be on the adverse side of the sizing decision reference price.')
    else:
        _require(entry <= known <= exit, 'Stop update must fall within its trade holding interval.')
    return known


def _trade(trade, point_value, start, end, sessions):
    keys = ('trade_id', 'side', 'quantity', 'entry_time_utc', 'exit_time_utc', 'entry_reference_price',
            'exit_reference_price', 'entry_fill_price', 'exit_fill_price', 'entry_commission', 'exit_commission',
            *MONEY_FIELDS, 'entry_reason', 'exit_reason', 'entry_bar_number', 'exit_bar_number',
            'initial_stop', 'stop_updates', 'excursions', 'sizing_decision')
    _object(trade, keys, 'trade')
    _text(trade['trade_id'], 'trade.trade_id')
    _enum(trade['side'], {'long', 'short'}, 'trade.side')
    quantity = _integer(trade['quantity'], 'trade.quantity', minimum=1, maximum=1_000_000)
    entry, exit = _timestamp(trade['entry_time_utc'], 'trade.entry_time_utc'), _timestamp(trade['exit_time_utc'], 'trade.exit_time_utc')
    _require(start <= entry <= exit <= end, 'Trade timestamps must be ordered and inside declared coverage.')
    _require(_session(entry) in sessions and _session(exit) in sessions, 'Trade session is absent from declared coverage.')
    prices = {name: _decimal(trade[name], name) for name in ('entry_reference_price', 'exit_reference_price', 'entry_fill_price', 'exit_fill_price')}
    money = {name: _decimal(trade[name], name) for name in MONEY_FIELDS}
    entry_fee, exit_fee = (_decimal(trade[name], name, nonnegative=True) for name in ('entry_commission', 'exit_commission'))
    signed = Decimal(quantity if trade['side'] == 'long' else -quantity)
    _require((prices['exit_reference_price'] - prices['entry_reference_price']) * signed * point_value == money['reference_gross_pnl'], 'Reference fills do not reconcile to reference_gross_pnl.')
    _require((prices['exit_fill_price'] - prices['entry_fill_price']) * signed * point_value == money['gross_pnl'], 'Actual fills do not reconcile to gross_pnl.')
    _require(entry_fee + exit_fee == money['total_commissions'], 'Per-side commissions do not reconcile.')
    _require(money['reference_gross_pnl'] - money['slippage_cost'] == money['gross_pnl'], 'Slippage must reconcile reference to actual gross once.')
    _require(money['gross_pnl'] - money['total_commissions'] == money['net_pnl'], 'Actual gross minus commissions must equal net once.')
    for name in ('entry_reason', 'exit_reason'):
        _text(trade[name], name)
    for name in ('entry_bar_number', 'exit_bar_number'):
        if trade[name] is not None:
            _integer(trade[name], name, minimum=1)
    _require((trade['entry_bar_number'] is None) == (trade['exit_bar_number'] is None), 'Bar numbers must both be retained or both absent.')
    if trade['entry_bar_number'] is not None:
        _require(trade['entry_bar_number'] <= trade['exit_bar_number'], 'Native bar identifiers are reversed.')
    decision = trade['sizing_decision']
    if decision is not None:
        _object(decision, ('timestamp_utc', 'reference_price', 'execution_timing'), 'sizing_decision')
        decided = _timestamp(decision['timestamp_utc'], 'sizing_decision.timestamp_utc')
        _decimal(decision['reference_price'], 'sizing_decision.reference_price')
        timing = _enum(decision['execution_timing'], {'same_close', 'next_open', 'observed_open', 'external_declared'}, 'sizing_decision.execution_timing')
        _require(decided <= entry, 'Sizing decision cannot follow entry.')
        if timing == 'same_close':
            _require(decided == entry, 'same_close sizing decision must have the entry timestamp.')
        if timing == 'next_open':
            _require(decided < entry, 'next_open sizing decision must precede the fill timestamp.')
    if trade['initial_stop'] is not None:
        _stop(trade['initial_stop'], trade, 'initial_stop', initial=True)
    _require(type(trade['stop_updates']) is list and len(trade['stop_updates']) <= 100_000, 'stop_updates must be a bounded array.')
    previous = None
    for stop in trade['stop_updates']:
        stamp = _stop(stop, trade, 'stop_update', initial=False)
        _require(previous is None or stamp >= previous, 'Stop updates must retain chronological order.')
        previous = stamp
    excursion = trade['excursions']
    if excursion is not None:
        _object(excursion, ('basis', 'mae', 'mfe', 'mae_time_utc', 'mfe_time_utc'), 'excursions')
        _enum(excursion['basis'], {'observed_marks_net_equity', 'exporter_reported_net_equity'}, 'excursions.basis')
        mae, mfe = _decimal(excursion['mae'], 'excursions.mae', nonnegative=True), _decimal(excursion['mfe'], 'excursions.mfe', nonnegative=True)
        _require(mae >= max(ZERO, -money['net_pnl'], entry_fee) and mfe >= max(ZERO, money['net_pnl']), 'Excursions omit opening costs or terminal realized net.')
        for name in ('mae_time_utc', 'mfe_time_utc'):
            if excursion[name] is not None:
                _require(entry <= _timestamp(excursion[name], name) <= exit, 'Excursion timestamp is outside the holding interval.')
    return entry, exit


def _events(events, trades, point_value, risk):
    by_id = {trade['trade_id']: trade for trade in trades}
    trade_ordinals = {trade['trade_id']: index for index, trade in enumerate(trades)}
    previous_trade_ordinal = -1
    grouped = {trade['trade_id']: [] for trade in trades}
    previous_key = None
    previous_sequence = 0
    unobserved_extrema_trade_ids = []
    for event in events:
        _object(event, ('trade_id', 'sequence', 'timestamp_utc', 'kind', 'current_quantity', 'mark_price',
                        'stop_price', 'cumulative_realized_gross', 'commissions_charged', 'marked_trade_net_equity'), 'risk_event')
        _text(event['trade_id'], 'risk_event.trade_id')
        _require(event['trade_id'] in by_id, 'Risk event references an unknown trade.')
        ordinal = trade_ordinals[event['trade_id']]
        _require(ordinal >= previous_trade_ordinal, 'Global risk events must retain chronological trade blocks; a new position cannot open before the previous position closes.')
        previous_trade_ordinal = ordinal
        sequence = _integer(event['sequence'], 'risk_event.sequence', minimum=1)
        stamp = _timestamp(event['timestamp_utc'], 'risk_event.timestamp_utc')
        key = (stamp, sequence)
        _require(previous_key is None or key > previous_key, 'Risk events must be globally ordered by UTC timestamp and unique sequence.')
        _require(sequence > previous_sequence, 'Global risk event sequence must strictly increase.')
        previous_key = key
        previous_sequence = sequence
        _enum(event['kind'], {'open', 'mark', 'stop_update', 'close'}, 'risk_event.kind')
        trade = by_id[event['trade_id']]
        _require(_timestamp(trade['entry_time_utc'], 'entry') <= stamp <= _timestamp(trade['exit_time_utc'], 'exit'), 'Risk event is outside its holding interval.')
        quantity = _integer(event['current_quantity'], 'risk_event.current_quantity', maximum=1_000_000)
        realized = _decimal(event['cumulative_realized_gross'], 'risk_event.cumulative_realized_gross')
        fees = _decimal(event['commissions_charged'], 'risk_event.commissions_charged', nonnegative=True)
        net = _decimal(event['marked_trade_net_equity'], 'risk_event.marked_trade_net_equity')
        mark = _decimal(event['mark_price'], 'risk_event.mark_price') if event['mark_price'] is not None else None
        stop_price = _decimal(event['stop_price'], 'risk_event.stop_price') if event['stop_price'] is not None else None
        closing = event['kind'] == 'close'
        _require(quantity == (0 if closing else trade['quantity']), 'Ordered events cannot scale in/out or change quantity.')
        _require(realized == (Decimal(trade['gross_pnl']) if closing else ZERO), 'Unsupported partial realization or unreconciled terminal gross.')
        _require(fees == Decimal(trade['total_commissions'] if closing else trade['entry_commission']), 'Event fees must reconcile to opening or terminal actual fees.')
        _require(mark is not None, 'Each observed event requires its actual mark price.')
        if closing:
            _require(mark == Decimal(trade['exit_fill_price']) and net == Decimal(trade['net_pnl']), 'Terminal event must match actual exit fill and net.')
        else:
            signed = Decimal(trade['quantity'] if trade['side'] == 'long' else -trade['quantity'])
            _require((mark - Decimal(trade['entry_fill_price'])) * signed * point_value - fees == net, 'Mark equity must use actual fills less charged commissions once.')
        if event['kind'] == 'open':
            _require(stamp == _timestamp(trade['entry_time_utc'], 'entry') and mark == Decimal(trade['entry_fill_price']), 'Opening event must match actual entry fill/time.')
        if closing:
            _require(stamp == _timestamp(trade['exit_time_utc'], 'exit'), 'Terminal event must match exit timestamp.')
        _require((stop_price is not None) == (event['kind'] == 'stop_update'), 'Only stop_update events carry stop_price.')
        grouped[event['trade_id']].append(event)
    if risk['basis'] != 'ordered_marks':
        _require(not events, 'Risk events require declared ordered_marks basis.')
    for trade in trades:
        sequence = grouped[trade['trade_id']]
        if risk['basis'] == 'ordered_marks' and risk['coverage'] == 'complete':
            _require(len(sequence) >= 2, 'Complete ordered risk requires opening and terminal events for every trade.')
        if sequence:
            _require(sequence[0]['kind'] == 'open' and sequence[-1]['kind'] == 'close', 'Each supplied event path requires opening and terminal events.')
            _require(all(e['kind'] not in ('open', 'close') for e in sequence[1:-1]), 'Opening and terminal events must occur exactly once.')
            _require(all(a['sequence'] < b['sequence'] for a, b in zip(sequence, sequence[1:])), 'Per-trade event sequences must strictly increase.')
            updates = [e for e in sequence if e['kind'] == 'stop_update']
            _require(len(updates) == len(trade['stop_updates']), 'Stop updates and ordered risk events must have identical coverage.')
            for stop, event in zip(trade['stop_updates'], updates):
                _require(_timestamp(stop['known_at_utc'], 'stop') == _timestamp(event['timestamp_utc'], 'event') and Decimal(stop['price']) == Decimal(event['stop_price']), 'Stop update provenance differs from ordered event.')
            excursion = trade['excursions']
            if excursion:
                values = [Decimal(e['marked_trade_net_equity']) for e in sequence]
                observed_mae, observed_mfe = max(ZERO, -min(values)), max(ZERO, max(values))
                _require(Decimal(excursion['mae']) >= observed_mae and Decimal(excursion['mfe']) >= observed_mfe, 'Reported excursions cannot understate supplied observed mark extrema.')
                if excursion['basis'] == 'exporter_reported_net_equity' and (Decimal(excursion['mae']) > observed_mae or Decimal(excursion['mfe']) > observed_mfe):
                    unobserved_extrema_trade_ids.append(trade['trade_id'])
            if excursion and excursion['basis'] == 'observed_marks_net_equity':
                _require(Decimal(excursion['mae']) == max(ZERO, -min(values)) and Decimal(excursion['mfe']) == max(ZERO, max(values)), 'Observed-mark excursions must reconcile exactly to supplied events.')
                for field, target in (('mae_time_utc', -Decimal(excursion['mae'])), ('mfe_time_utc', Decimal(excursion['mfe']))):
                    if excursion[field] is not None:
                        when = _timestamp(excursion[field], field)
                        _require(any(_timestamp(e['timestamp_utc'], 'event') == when and Decimal(e['marked_trade_net_equity']) == target for e in sequence), 'Observed excursion timestamp must match an actual event at that extreme.')
        elif trade['excursions'] and trade['excursions']['basis'] == 'observed_marks_net_equity':
            raise TradeExportError('Observed-mark excursions require their observed event path.')
        if risk['basis'] == 'measured_extrema' and risk['coverage'] == 'complete':
            _require(trade['excursions'] is not None, 'Complete measured extrema require excursions for every trade.')
        if risk['basis'] in ('missing', 'unknown'):
            _require(trade['excursions'] is None, 'Missing/unknown risk cannot contain declared measured excursions.')
    return unobserved_extrema_trade_ids


def _external_capabilities(manifest, trades):
    return dict(native_replay=False, bar_equity=False, market_benchmark=False, controlled_oos=False,
                nested_research=False, prop_analysis=False, prop_analysis_reason='Canonical parsing alone does not grant model replay; a model-specific source check is required.',
                ordered_marks_available=bool(trades) and manifest['risk']['basis'] == 'ordered_marks' and manifest['risk']['coverage'] == 'complete',
                initial_stops_available=bool(trades) and all(t['initial_stop'] is not None for t in trades),
                sizing_decisions_available=bool(trades) and all(t['sizing_decision'] is not None for t in trades),
                risk_based_sizing_inputs_available=bool(trades) and all(t['initial_stop'] is not None and t['sizing_decision'] is not None for t in trades),
                sizing_decision_provenance='exporter_declared_not_independently_verified',
                sizing_path_invariance_verified=False, calendar_coverage_verified=False,
                tick_completeness_verified=False)


def parse_trade_export(raw: bytes) -> dict:
    """Validate immutable raw bytes and return a JSON-safe canonical source.

    Callers must save the *same bytes* under source.raw_sha256. Report-only
    acceptance does not grant prop replay, scaling or untouched-IS capability.
    """
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_EXPORT_BYTES, 'Export must be nonempty bytes no larger than 32 MiB.')
    try:
        document = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                              parse_float=_bad_number, parse_constant=_bad_number)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise TradeExportError('Invalid UTF-8 JSON trade export.') from exc
    _json_tree(document, 'export')
    _object(document, ('schema_version', 'export_id', 'manifest', 'payload', 'completion'), 'export')
    _require(document['schema_version'] == SCHEMA_VERSION, 'Unsupported trade export schema_version.')
    _text(document['export_id'], 'export_id')
    payload = _object(document['payload'], ('trades', 'risk_events'), 'payload')
    trades, events = payload['trades'], payload['risk_events']
    _require(type(trades) is list and len(trades) <= MAX_TRADES, 'Payload trades must be a bounded array.')
    _require(type(events) is list and len(events) <= MAX_EVENTS, 'Payload risk_events must be a bounded array.')
    completion = _object(document['completion'], ('status', 'trade_count', 'event_count', 'payload_sha256'), 'completion')
    _require(completion['status'] == 'complete', 'Partial/incomplete exports cannot be imported.')
    _require(_integer(completion['trade_count'], 'completion.trade_count') == len(trades), 'Completed trade count differs from payload.')
    _require(_integer(completion['event_count'], 'completion.event_count') == len(events), 'Completed event count differs from payload.')
    _hash(completion['payload_sha256'], 'completion.payload_sha256')
    _require(canonical_payload_sha256(payload) == completion['payload_sha256'], 'Canonical payload SHA-256 differs from completion marker.')
    # Bounded 128-digit/64-place inputs and at most three factors need <512
    # digits. Trap rounding so altered caller precision can never accept drift.
    with localcontext(Context(prec=512, traps=[Inexact, InvalidOperation, Overflow])):
        point_value, start, end, sessions = _manifest(document['manifest'])
        seen, previous_exit = set(), None
        for trade in trades:
            entry, exit = _trade(trade, point_value, start, end, sessions)
            _require(trade['trade_id'] not in seen, 'Duplicate trade_id.')
            _require(previous_exit is None or entry >= previous_exit, 'Trades must be chronological, nonoverlapping constant-quantity round trips.')
            if trade['sizing_decision'] is not None and previous_exit is not None:
                _require(previous_exit <= _timestamp(trade['sizing_decision']['timestamp_utc'], 'sizing_decision'), 'Sizing decision predates previous trade settlement.')
            seen.add(trade['trade_id'])
            previous_exit = exit
        unobserved_extrema = _events(events, trades, point_value, document['manifest']['risk'])
        totals = {name: str(sum((Decimal(t[name]) for t in trades), ZERO)) for name in MONEY_FIELDS}
    return dict(normalized_version=NORMALIZED_VERSION,
                source=dict(kind='external_trade_export', schema_version=SCHEMA_VERSION, export_id=document['export_id'],
                            raw_sha256=sha256(raw).hexdigest(), raw_bytes=len(raw), payload_sha256=completion['payload_sha256']),
                manifest=deepcopy(document['manifest']), trades=deepcopy(trades), risk_events=deepcopy(events), native_risk=None,
                capabilities=_external_capabilities(document['manifest'], trades),
                validation=dict(trade_count=len(trades), event_count=len(events), totals=totals, exact_arithmetic=True,
                                completion='exporter_declared_complete', risk_coverage='exporter_declared_not_independently_verified',
                                unobserved_extrema_trade_ids=unobserved_extrema,
                                ordered_path_covers_reported_extrema=bool(trades) and document['manifest']['risk']['basis'] == 'ordered_marks' and document['manifest']['risk']['coverage'] == 'complete' and not unobserved_extrema,
                                risk_path_disclosure=('Reported extrema exceed supplied ordered marks; missing path/order cannot be reconstructed.' if unobserved_extrema else 'Exporter risk coverage is not independently verified.'),
                                costs='Actual fills already incorporate slippage; net subtracts commissions once.'))


def _plain(value):
    number = Decimal(str(value))
    _require(number.is_finite(), 'Native amount must be finite.')
    return format(number, 'f')


def project_native_source(runs, source_id: str) -> dict:
    """Project existing RunStore evidence without creating missing history.

    Reads catalogue directly to avoid RunStore.get's legacy enrichment write.
    Complete native CSV/risk fields survive under native_fields/native_risk.
    Historical source files do not retain initial stops, so these stay unknown.
    """
    from uuid import UUID
    from alphaquest.prop.source import native_risk

    try:
        normalized_id = UUID(source_id).hex
    except (ValueError, TypeError, AttributeError) as exc:
        raise TradeExportError('Native source ID must be a UUID.') from exc
    with runs.connect() as connection:
        row = connection.execute('SELECT manifest FROM runs WHERE id=?', (normalized_id,)).fetchone()
    _require(row is not None, 'Native source backtest does not exist.')
    record = json.loads(row[0])
    _require(record.get('status') == 'complete', 'Native source report is incomplete.')
    _require(record.get('id') == normalized_id, 'Native catalogue run identity differs.')
    metadata = record.get('run_metadata', {})
    _require(metadata.get('source', {}).get('kind') != 'external_trade_export', 'Use the preserved external export parser for an imported source.')
    folder = Path(runs.root) / normalized_id
    trade_path = folder / 'trades.csv'
    original = trade_path.read_bytes()
    _require(len(original) <= MAX_EXPORT_BYTES, 'Native trade artifact exceeds size limit.')
    import io
    rows = list(csv.DictReader(io.StringIO(original.decode('utf-8'), newline='')))
    _require(len(rows) <= MAX_TRADES and len(rows) == record['summary']['trades_taken'], 'Native source trade count differs from saved summary.')
    risk_rows = native_risk(runs, normalized_id, record, rows)
    decisions = None
    if record.get('execution_decisions') is not None:
        from .decision_capture import SIDE_CAR, read_decision_evidence
        _require(record.get('artifacts', {}).get('execution_decisions_jsonl') == SIDE_CAR, 'Unsupported native decision artifact.')
        decisions = read_decision_evidence(folder / SIDE_CAR, record['execution_decisions'], rows, record['execution_settings'])
    config = record['execution_settings']
    dataset, strategy = metadata.get('dataset', {}), metadata.get('strategy', {})
    start, end = _timestamp(record['period_start_utc'], 'native period_start_utc'), _timestamp(record['period_end_utc'], 'native period_end_utc')
    trades, seen = [], set()
    previous_exit = None
    with localcontext(Context(prec=512, traps=[Inexact, InvalidOperation, Overflow])):
        point_value = _decimal(_plain(config['point_value']), 'native point_value', positive=True)
        for r in rows:
            trade = {name: r[name] for name in (*MONEY_FIELDS, 'entry_reference_price', 'exit_reference_price',
                                               'entry_fill_price', 'exit_fill_price', 'entry_commission', 'exit_commission',
                                               'entry_time_utc', 'exit_time_utc', 'side', 'entry_reason', 'exit_reason')}
            for name in (*MONEY_FIELDS, 'entry_reference_price', 'exit_reference_price', 'entry_fill_price', 'exit_fill_price', 'entry_commission', 'exit_commission'):
                trade[name] = _plain(trade[name])
            trade.update(trade_id=r['trade_number'], quantity=int(r['contracts']), entry_bar_number=int(r['entry_bar_number']),
                         exit_bar_number=int(r['exit_bar_number']), initial_stop=None, stop_updates=[], excursions=None, sizing_decision=None)
            # Native session inventory is not present in historical reports.
            # Validate only known trade timestamps; do not fabricate coverage.
            sessions = {_session(_timestamp(r['entry_time_utc'], 'entry')), _session(_timestamp(r['exit_time_utc'], 'exit'))}
            entry, exit = _trade(trade, point_value, start, end, sessions)
            _require(trade['trade_id'] not in seen and (previous_exit is None or entry >= previous_exit), 'Native source has duplicate/overlapping trades.')
            seen.add(trade['trade_id']); previous_exit = exit
            trade['native_fields'] = dict(r)
            trade['stop_provenance'] = 'not_retained_in_native_trade_artifact'
            if decisions is not None:
                evidence = decisions['trades'][trade['trade_id']]
                trade.update(sizing_decision=evidence['sizing_decision'], initial_stop=evidence['initial_stop'],
                             stop_updates=evidence['stop_updates'], decision_evidence=evidence,
                             stop_provenance='causal_native_entry_decision' if evidence['initial_stop'] is not None else 'not_declared_by_strategy')
            trades.append(trade)
        totals = {name: str(sum((Decimal(t[name]) for t in trades), ZERO)) for name in MONEY_FIELDS}
        for name, summary_name in (('gross_pnl', 'total_gross_pnl'), ('slippage_cost', 'total_slippage_cost'),
                                   ('total_commissions', 'total_commissions'), ('net_pnl', 'total_net_pnl')):
            _require(Decimal(totals[name]) == Decimal(record['summary'][summary_name]), 'Native source totals differ from saved summary.')
        _require(Decimal(record['summary']['initial_capital']) == Decimal(config['initial_capital']), 'Native initial capital differs from execution settings.')
        _require(Decimal(record['summary']['initial_capital']) + Decimal(totals['net_pnl']) == Decimal(record['summary']['final_equity']), 'Native final equity does not reconcile.')
    hashes = {'trades.csv': sha256(original).hexdigest()}
    if decisions is not None:
        hashes['execution_decisions.jsonl'] = record['execution_decisions']['sha256']
    if risk_rows is not None:
        hashes['intratrade_risk.csv'] = record['intratrade_risk']['sha256']
    report_name = record.get('artifacts', {}).get('report')
    if report_name in ('report.json', 'report.json.gz'):
        hashes[report_name] = sha256((folder / report_name).read_bytes()).hexdigest()
    for name, digest in hashes.items():
        _require(sha256((folder / name).read_bytes()).hexdigest() == digest, 'Native source changed while projecting.')
    with runs.connect() as connection:
        current = connection.execute('SELECT manifest FROM runs WHERE id=?', (normalized_id,)).fetchone()
    _require(current is not None and current[0] == row[0], 'Native catalogue identity changed while projecting.')
    manifest = dict(origin='alphaquest', initial_capital=_plain(config['initial_capital']), strategy=deepcopy(strategy),
                    dataset=deepcopy(dataset), instrument={key: dataset.get(key, config.get(key)) for key in ('symbol', 'currency', 'tick_size', 'point_value')},
                    time=dict(timestamp_basis=record.get('timestamp_convention', 'unknown'), source_timezone=dataset.get('source_timezone'), session_convention=SESSION_CONVENTION),
                    coverage=dict(start_utc=record['period_start_utc'], end_utc=record['period_end_utc'], sessions=None,
                                  completion='native_completed_report', session_inventory='not_retained'),
                    research=deepcopy(metadata.get('research', {'phase': 'unspecified'})),
                    execution=dict(settings=deepcopy(config), assumption=record.get('execution_assumption'),
                                   scenario=deepcopy(metadata.get('execution_scenario')), cost_basis='actual_per_trade'),
                    risk=dict(basis='native_held_ohlc_bounds' if risk_rows is not None else 'missing',
                              coverage='complete' if risk_rows is not None else 'missing',
                              description=deepcopy(record.get('intratrade_risk'))))
    return dict(normalized_version=NORMALIZED_VERSION,
                source=dict(kind='native_backtest', source_backtest_id=normalized_id, manifest_sha256=sha256(row[0].encode()).hexdigest(),
                            artifact_sha256=hashes, native_manifest=record), manifest=manifest,
                trades=trades, risk_events=[], native_risk=deepcopy(risk_rows), native_decisions=decisions,
                capabilities=dict(native_replay=bool(dataset.get('id')), bar_equity=record.get('report_storage', {}).get('per_bar_equity_retained', record.get('format_version') == 1),
                                  market_benchmark=bool(record.get('market_benchmark')), controlled_oos=bool(dataset.get('id')),
                                  nested_research=bool(dataset.get('id')), prop_analysis=risk_rows is not None,
                                  prop_analysis_reason='Existing native adapter/profile admission remains required.',
                                  ordered_marks_available=False, initial_stops_available=bool(trades) and all(t['initial_stop'] is not None for t in trades),
                                  sizing_decisions_available=decisions is not None, quantity_path_policy='native_rerun_required',
                                  sizing_path_invariance_verified=False,
                                  calendar_coverage_verified=False, tick_completeness_verified=False),
                validation=dict(trade_count=len(trades), event_count=0, totals=totals, exact_arithmetic=True,
                                completion='native_completed_report', costs='Saved actual net costs are conserved; no costs are charged again.'))
