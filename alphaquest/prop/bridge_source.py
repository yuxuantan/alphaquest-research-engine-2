"""Reconcile a Bridge trade export with an existing immutable native backtest.

The extra export supplies measured excursions absent from native trade storage.
It never replaces native P&L or changes the source backtest.
"""
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from zoneinfo import ZoneInfo

from .adapter import source_record, canonical, digest
from ..decimal_math import add, subtract
from hashlib import sha256

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def export_trades(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in ('.xlsx', '.xlsm'):
        raise ValueError('Select an existing MultiCharts XLSX trade export for The Bridge.')
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Trade export exceeds the 32 MiB input limit.')
    with zipfile.ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist()) > 64 * 1024 * 1024:
            raise ValueError('Expanded trade export exceeds the 64 MiB input limit.')
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(s.itertext()) for s in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        book = ET.fromstring(archive.read('xl/workbook.xml'))
        targets = {r.attrib['Id']: r.attrib['Target'] for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        sheet = next((s for s in book.findall('m:sheets/m:sheet', NS) if s.attrib['name'].strip().lower() == 'list of trades'), None)
        if sheet is None:
            raise ValueError('Trade export needs a List of Trades worksheet.')
        target = targets[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
        target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        if '..' in Path(target).parts:
            raise ValueError('Invalid worksheet path.')
        header, records = None, []
        for row in ET.fromstring(archive.read(target)).findall('m:sheetData/m:row', NS):
            cells = {}
            for c in row:
                v = c.find('m:v', NS)
                value = v.text if v is not None else ''.join(c.find('m:is', NS).itertext()) if c.find('m:is', NS) is not None else ''
                if c.attrib.get('t') == 's':
                    value = strings[int(value)]
                cells[''.join(x for x in c.attrib['r'] if x.isalpha())] = value
            if header is None:
                if 'Trade #' in cells.values():
                    header = {k: v.strip() for k, v in cells.items()}
                continue
            r = {header[k]: v for k, v in cells.items() if k in header}
            if not r.get('Trade #'):
                continue  # MultiCharts exit rows are not additional trades.
            if len(records) >= 100000:
                raise ValueError('Trade export exceeds 100,000 trades.')
            try:
                serial = float(r['Date'])
                stamp = datetime(1899, 12, 30) + timedelta(days=serial)
                # Excel/openpyxl timestamps have millisecond rounding. Native
                # repository fills are second resolution; allow only sub-ms noise.
                rounded = stamp.replace(microsecond=0) + timedelta(seconds=stamp.microsecond >= 500000)
                if abs((stamp - rounded).total_seconds()) > .001:
                    raise ValueError('Trade export timestamp has unsupported subsecond precision.')
                stamp = rounded
            except (ValueError, OverflowError):
                try:
                    stamp = datetime.fromisoformat(r['Date'])
                except ValueError as exc:
                    raise ValueError('Trade export dates must be Excel timestamps or ISO timestamps.') from exc
            if stamp.tzinfo is not None:
                raise ValueError('Export timestamps must be timezone-naive with an explicit export timezone.')
            records.append(dict(trade_id=int(r['Trade #']), direction=r.get('Type'), entry=stamp,
                                contracts=Decimal(r['Contracts']), net=Decimal(r['Profit ($)']),
                                mae=abs(Decimal(r['Drawdown ($)'])) if r.get('Drawdown ($)') else None,
                                mfe=abs(Decimal(r['Run-up ($)'])) if r.get('Run-up ($)') else None))
    if not records:
        raise ValueError('Trade export contains no entry rows.')
    return records


def prepare_source(runs, source_id, trade_file, export_timezone='America/Chicago'):
    record=source_record(runs,source_id)
    native_path=runs.root/source_id/'trades.csv'
    native_hash=digest(native_path)
    native=[]
    with native_path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if len(native)>=100000:raise ValueError('Native source exceeds 100,000 trades.')
            native.append(row)
    if not native:raise ValueError('Empty source backtest; no trades or excursions are fabricated.')
    if len(native)!=record['summary']['trades_taken']:raise ValueError('Native trade count differs from its saved summary.')
    totals={k:Decimal(0) for k in ('reference_gross_pnl','slippage_cost','total_commissions','gross_pnl','net_pnl')}
    quantities=set()
    for row in native:
        q=Decimal(row['contracts']);quantities.add(q)
        values={k:Decimal(row[k]) for k in totals}
        if not q.is_finite() or q<=0 or any(not x.is_finite() for x in values.values()):raise ValueError('Invalid native quantity or cost.')
        if subtract(subtract(values['reference_gross_pnl'],values['slippage_cost']),values['total_commissions'])!=values['net_pnl'] or subtract(values['gross_pnl'],values['total_commissions'])!=values['net_pnl']:
            raise ValueError('Native source per-trade costs do not reconcile.')
        for k in totals:totals[k]=add(totals[k],values[k])
    if len(quantities)!=1:raise ValueError('Variable source quantities are not supported by this Bridge adapter.')
    if len({r['trade_number'] for r in native})!=len(native):raise ValueError('Duplicate native trade IDs.')
    for k,target in [('net_pnl','total_net_pnl'),('gross_pnl','total_gross_pnl'),('total_commissions','total_commissions'),('slippage_cost','total_slippage_cost')]:
        if totals[k]!=Decimal(record['summary'][target]):raise ValueError('Native source totals differ from the saved backtest.')
    snapshot=dict(backtest=record,trades_sha256=native_hash,manifest_sha256=sha256(canonical(record).encode()).hexdigest(),
                  source_timezone=record['run_metadata']['dataset']['source_timezone'],
                  excursion_provenance='Native trades contain no measured excursions. The matched export supplies measured MAE/MFE; the portal inserts no synthetic excursions.',
                  reconciliation=dict(source_totals={k:str(v) for k,v in totals.items()},source_count=len(native),exact_source_arithmetic=True),
                  filtering='The portal passes all matched entry rows unchanged; The Bridge applies and reports its own filtering and session conventions.')
    if not trade_file:
        raise ValueError('Select the matching original trade export. The Bridge uses its measured excursions; native backtest trades do not contain them.')
    path = Path(trade_file).expanduser().resolve()
    before = digest(path)
    try:
        exported = export_trades(path)
    except (zipfile.BadZipFile, ET.ParseError, KeyError, InvalidOperation, IndexError) as exc:
        raise ValueError('Unreadable or incomplete MultiCharts trade export.') from exc
    if len(exported) != len(native):
        raise ValueError('Trade export count differs from the completed backtest.')
    zone = ZoneInfo(export_timezone)
    seen, comparisons = set(), []
    by_id = {int(r['trade_number']): r for r in native}
    for e in exported:
        id = e['trade_id']
        if id in seen or id not in by_id:
            raise ValueError('Trade export has duplicate or mismatched trade IDs.')
        seen.add(id)
        n = by_id[id]
        if e['direction'] not in ('EntryLong', 'EntryShort') or ('short' if e['direction'] == 'EntryShort' else 'long') != n['side']:
            raise ValueError(f'Trade {id}: export direction differs from source.')
        utc = e['entry'].replace(tzinfo=zone).astimezone(timezone.utc)
        if utc != datetime.fromisoformat(n['entry_time_utc'].replace('Z', '+00:00')):
            raise ValueError(f'Trade {id}: export entry time differs from source UTC; check export timezone.')
        if e['contracts'] != Decimal(n['contracts']) or not e['net'].is_finite() or subtract(e['net'],Decimal(n['net_pnl'])).copy_abs() > Decimal('0.00000001'):
            raise ValueError(f'Trade {id}: export quantity or net P&L differs from source.')
        if any(v is not None and not v.is_finite() for v in (e['mae'], e['mfe'])):
            raise ValueError(f'Trade {id}: non-finite excursion.')
        comparisons.append(dict(trade_id=id, entry_utc=n['entry_time_utc'], source_net_pnl=n['net_pnl'], export_net_pnl=str(e['net']),
                                quantity=n['contracts'], measured_mae=str(e['mae']) if e['mae'] is not None else None,
                                measured_mfe=str(e['mfe']) if e['mfe'] is not None else None))
    if before != digest(path) or snapshot['trades_sha256'] != digest(native_path):
        raise ValueError('Source changed during checking.')
    snapshot['bridge_input'] = dict(path=str(path), filename=path.name, sha256=before, export_timezone=export_timezone,
                                   matched_trades=len(comparisons), measured_mae_count=sum(e['mae'] is not None for e in exported),
                                   measured_mfe_count=sum(e['mfe'] is not None for e in exported),
                                   cost_contract='Export net P&L matches saved backtest net P&L, including source commission and slippage. The Bridge adds no trading costs.')
    return snapshot, comparisons


def matching_exports(runs, source_id):
    """Suggest only fully reconciled reports; never select an unrelated export."""
    matches = []
    for path in sorted((Path.home() / 'Downloads').glob('*Strategy Performance Report*.xlsx'))[:32]:
        try:
            snapshot, _ = prepare_source(runs, source_id, str(path))
            matches.append(snapshot['bridge_input'])
        except (ValueError, KeyError, OSError, zipfile.BadZipFile, ET.ParseError):
            continue
    return matches
