"""Canonical exports in the ordinary RunStore, without invented price bars."""
import csv
from datetime import datetime, timezone
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from .canonical_trades import parse_trade_export
from .drawdown import Drawdown
from .execution import _holding_minutes
from .optimization_cache import engine_identity
from .reporting import EQUITY_FIELDS, TRADE_FIELDS, json_value


VERSION = 'canonical-trade-import-v1'
SOURCE_FILES = {'source': 'source.json', 'canonical_source': 'canonical_source.json',
                'trades': 'trades.csv', 'equity': 'equity.csv'}


class ImportConflict(ValueError):
    pass


def external(record):
    return record.get('run_metadata', {}).get('source', {}).get('kind') == 'external_trade_export'


def instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _json(value):
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                      allow_nan=False, default=json_value).encode('utf-8') + b'\n'


def summarize(source):
    """Trade-close metrics only; declaration bounds do not become observed bars."""
    manifest, trades = source['manifest'], source['trades']
    with localcontext(Context(prec=512)):
        initial = Decimal(manifest['initial_capital'])
        balance = initial
        tracker = Drawdown(initial, instant(manifest['coverage']['start_utc']))
        equity = [dict(trade_number=0, exit_time_utc=None, net_pnl='0', equity=str(initial))]
        winning = losing = 0
        for ordinal, trade in enumerate(trades, 1):
            net = Decimal(trade['net_pnl'])
            balance += net
            winning += net > 0
            losing += net < 0
            tracker.observe(instant(trade['exit_time_utc']), balance)
            equity.append(dict(trade_number=ordinal, exit_time_utc=trade['exit_time_utc'],
                               net_pnl=trade['net_pnl'], equity=str(balance)))
        totals = source['validation']['totals']
        summary = dict(initial_capital=str(initial), final_equity=str(balance),
            trades_taken=len(trades), winning_trades=winning, losing_trades=losing,
            breakeven_trades=len(trades)-winning-losing,
            win_rate_pct=str(Context(prec=28).divide(Decimal(winning*100), Decimal(len(trades)))) if trades else None,
            total_gross_pnl=totals['gross_pnl'], total_slippage_cost=totals['slippage_cost'],
            total_commissions=totals['total_commissions'], total_net_pnl=totals['net_pnl'],
            ending_position_contracts=0, **tracker.finish(instant(manifest['coverage']['end_utc'])))
    return json.loads(_json(summary)), equity


def limitations(source):
    from .prop.external_source import capabilities
    return [
        'Imported trade-close results use supplied fills and exact per-trade costs. No local price bars, per-bar equity or benchmark were invented.',
        'Source/code/calendar identities, research access and export completeness are exporter declarations, not independently verified history.',
        'Drawdown is measured at completed-trade closes over the declared coverage interval. It is not intratrade account drawdown.',
        'Ordered marks, measured extrema and missing risk remain distinct. Mark completeness, live fills and sizing-path invariance are unverified.',
        capabilities(source)['prop_analysis_reason'],
    ]


def preview_import(raw, filename):
    from .prop.external_source import capabilities
    source = parse_trade_export(raw)
    summary, _ = summarize(source)
    return dict(status='compatible', filename=Path(filename).name,
                source=source['source'], manifest=source['manifest'], validation=source['validation'],
                summary=summary, capabilities=capabilities(source), limitations=limitations(source))


def verify_import_artifacts(runs, record):
    """Read saved results without rerunning validation or summary calculations."""
    if not external(record):
        raise ValueError('This report is not an external trade import.')
    folder = runs.root/record['id']
    if (folder/'report.json').read_bytes() != _json(record):
        raise ValueError('Imported report file and catalogue metadata no longer agree.')
    expected = record.get('source_artifacts', {})
    for name in SOURCE_FILES.values():
        path = folder/name
        if path.is_symlink() or not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected.get(name):
            raise ValueError('Imported source artifact is missing or changed: '+name)


def verify_import(runs, record):
    """Reconcile canonical inputs afresh at a new calculation boundary."""
    verify_import_artifacts(runs, record)
    folder = runs.root/record['id']
    raw = (folder/'source.json').read_bytes()
    source = parse_trade_export(raw)
    saved = json.loads((folder/'canonical_source.json').read_bytes())
    core = ('normalized_version', 'source', 'manifest', 'trades', 'risk_events', 'native_risk')
    if any(source[key] != saved.get(key) for key in core):
        raise ValueError('Saved canonical projection differs from the immutable original export.')
    validation_keys = ('trade_count', 'event_count', 'totals', 'exact_arithmetic')
    if (source['source'] != record['run_metadata']['source']
            or source['manifest'] != record['run_metadata']['external_manifest']
            or any(source['validation'][key] != record['run_metadata']['source_validation'].get(key) for key in validation_keys)
            or summarize(source)[0] != record['summary']):
        raise ValueError('Imported report no longer reconciles to the original export.')
    return source


def _write_csv(path, names, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def _trade_rows(trades):
    for ordinal, trade in enumerate(trades, 1):
        row = {name: trade[name] for name in TRADE_FIELDS if name in trade}
        row.update(trade_number=ordinal, external_trade_id=trade['trade_id'], contracts=trade['quantity'],
            exit_deadline_utc=None,
            actual_holding_minutes=str(_holding_minutes(instant(trade['entry_time_utc']), instant(trade['exit_time_utc']))))
        yield row


def save_import(runs, raw, filename):
    from .prop.external_source import capabilities
    source = parse_trade_export(raw)
    summary, equity = summarize(source)
    manifest, provenance = source['manifest'], source['source']
    # Parsing takes place before the existing publication/detail lock. The lock
    # serializes duplicate imports without a new catalogue or storage system.
    with runs.detail_lock:
        with runs.connect() as db:
            row = db.execute("SELECT manifest FROM runs WHERE json_extract(manifest,'$.run_metadata.source.kind')='external_trade_export' "
                             "AND json_extract(manifest,'$.run_metadata.source.export_id')=?",
                             (provenance['export_id'],)).fetchone()
        if row:
            record = json.loads(row[0])
            if record['run_metadata']['source']['raw_sha256'] != provenance['raw_sha256']:
                raise ImportConflict('This export ID is already saved with different bytes. Preserve the original and provide a new exporter ID for a new export.')
            verify_import_artifacts(runs, record)
            return record, False
        id = uuid4().hex
        instrument, dataset, coverage = manifest['instrument'], manifest['dataset'], manifest['coverage']
        descriptor = dict(id=None, name=dataset['name'], filename=Path(filename).name,
            sha256=dataset['sha256'], source_timezone=manifest['time']['source_timezone'], row_count=None,
            **instrument, instrument_settings={k:instrument[k] for k in ('tick_size','point_value')},
            contract=dataset['contract'], adjustment=dataset['adjustment'])
        record = dict(id=id, format_version=3, report_kind='external_trade_export', status='complete',
            created_at_utc=datetime.now(timezone.utc).isoformat(), period_start_utc=coverage['start_utc'],
            period_end_utc=coverage['end_utc'], timestamp_convention=manifest['time']['timestamp_basis'],
            execution_assumption=manifest['execution']['fill_assumption'],
            execution_settings=dict(initial_capital=manifest['initial_capital'], tick_size=instrument['tick_size'],
                point_value=instrument['point_value'], commission_per_contract_per_side=None, slippage_ticks=None),
            run_metadata=dict(source=provenance, external_manifest=manifest, source_validation=source['validation'],
                dataset=descriptor, instrument=instrument,
                strategy=dict(id=manifest['strategy']['id'], parameters=manifest['strategy']['parameters'],
                              source_sha256=manifest['strategy']['implementation_sha256']),
                research={**manifest['research'], 'coverage':coverage, 'origin':'exporter_declaration'},
                selection=dict(kind='external_trade_coverage', row_count=None, from_date=None, to_date=None),
                importer=dict(version=VERSION, engine_identity=engine_identity())),
            summary=summary, capabilities=capabilities(source), limitations=limitations(source),
            reconciliation=dict(total_net_equals_sum_trade_net=True, gross_minus_commissions_equals_net=True,
                final_equity_equals_initial_plus_net=True, final_position_flat=True,
                observed_bar_count=None, expected_bar_count=None, completeness='exporter_declared'),
            report_storage=dict(detail='compact', compression='none', per_bar_equity_retained=False,
                trades='all', equity_csv='initial_and_trade_close'),
            artifacts=dict(report='report.json', trades_csv='trades.csv', equity_csv='equity.csv',
                source_json='source.json', canonical_source_json='canonical_source.json'))
        with TemporaryDirectory(prefix='.pending-import-', dir=runs.root) as pending:
            output = Path(pending)/id
            output.mkdir()
            (output/'source.json').write_bytes(raw)
            (output/'canonical_source.json').write_bytes(_json(source))
            _write_csv(output/'trades.csv', TRADE_FIELDS+['external_trade_id'], _trade_rows(source['trades']))
            _write_csv(output/'equity.csv', EQUITY_FIELDS, equity)
            record['source_artifacts'] = {name:sha256((output/name).read_bytes()).hexdigest() for name in SOURCE_FILES.values()}
            (output/'report.json').write_bytes(_json(record))
            try:
                return runs.complete(id, output, record), True
            except sqlite3.IntegrityError:
                # The catalogue's partial unique index serializes export IDs
                # across processes as well as this instance's lock.
                with runs.connect() as db:
                    saved = db.execute("SELECT manifest FROM runs WHERE json_extract(manifest,'$.run_metadata.source.kind')='external_trade_export' "
                        "AND json_extract(manifest,'$.run_metadata.source.export_id')=?", (provenance['export_id'],)).fetchone()
                if saved is None:
                    raise
                existing = json.loads(saved[0])
                if existing['run_metadata']['source']['raw_sha256'] != provenance['raw_sha256']:
                    raise ImportConflict('This export ID was concurrently saved with different bytes.') from None
                verify_import_artifacts(runs, existing)
                return existing, False
