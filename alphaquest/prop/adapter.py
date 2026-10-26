"""Deterministic, exact-cost adapter over immutable completed backtest trades."""
import csv
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo
from datetime import datetime
import pandas as pd


def digest(path):
    h=sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',',':'), allow_nan=False)


def source_record(runs, run_id):
    with runs.connect() as conn:
        row=conn.execute('SELECT manifest FROM runs WHERE id=?',(UUID(run_id).hex,)).fetchone()
    if not row:raise ValueError('Completed source backtest not found.')
    record=json.loads(row[0])
    if record.get('status')!='complete':raise ValueError('Source must be completed.')
    return record


def adapt(runs, run_id, settings):
    record=source_record(runs,run_id)
    path=runs.root/record['id']/'trades.csv'
    before=digest(path)
    with path.open(newline='') as f: rows=list(csv.DictReader(f))
    if len(rows)>100000:raise ValueError('Source exceeds 100,000-trade resource bound; no trades were truncated.')
    if len(rows)!=record['summary']['trades_taken']:raise ValueError('Source trade count differs from saved summary.')
    zone=ZoneInfo(record['run_metadata']['dataset']['source_timezone'])
    totals={k:Decimal(0) for k in ('reference_gross_pnl','slippage_cost','total_commissions','gross_pnl','net_pnl')}
    mapped=[]; excluded=[]
    with localcontext() as ctx:
        ctx.prec=80
        for row in rows:
            q=Decimal(row['contracts'])
            if not q.is_finite() or q<=0:raise ValueError('Source contains invalid quantity.')
            vals={k:Decimal(row[k]) for k in totals}
            if not all(v.is_finite() for v in vals.values()):raise ValueError('Source contains non-finite P&L.')
            if vals['reference_gross_pnl']-vals['slippage_cost']-vals['total_commissions']!=vals['net_pnl'] or vals['gross_pnl']-vals['total_commissions']!=vals['net_pnl']:raise ValueError('Source per-trade costs do not reconcile.')
            for k in totals:totals[k]+=vals[k]
            stamp=datetime.fromisoformat(row['entry_time_utc'].replace('Z','+00:00'))
            if stamp.utcoffset() is None:raise ValueError('Source entry timestamp must include UTC offset.')
            native=stamp.astimezone(zone).replace(tzinfo=None)
            r=dict(trade_id=int(row['trade_number']),direction=row['side'].upper(),datetime=native.isoformat(),contracts=float(q),profit_usd=float(vals['reference_gross_pnl']),
                source_entry_utc=row['entry_time_utc'],source_exit_utc=row['exit_time_utc'],source_quantity=row['contracts'],source_net_pnl=row['net_pnl'],source_reference_gross_pnl=row['reference_gross_pnl'],source_commissions=row['total_commissions'],source_slippage=row['slippage_cost'])
            if r['direction'] not in ('LONG','SHORT'):raise ValueError('Unknown source direction.')
            if native.weekday()>=5: excluded.append(dict(trade_id=r['trade_id'],reason='weekend',datetime=r['datetime']))
            else:mapped.append(r)
        for k,summary in [('net_pnl','total_net_pnl'),('gross_pnl','total_gross_pnl'),('total_commissions','total_commissions'),('slippage_cost','total_slippage_cost')]:
            if totals[k]!=Decimal(record['summary'][summary]):raise ValueError(f'Source {k} does not reconcile to saved summary.')
        quantities={r['source_quantity'] for r in mapped}
        if len(quantities)>1 and not settings['ALLOW_VARIABLE_CONTRACTS']:raise ValueError('Variable source quantities rejected; ALLOW_VARIABLE_CONTRACTS explicitly divides out strategy sizing.')
        if not mapped:raise ValueError('No weekday trades; statistics unavailable. No trades fabricated.')
        # Notebook normalization occurs BEFORE OOS filtering.
        for r in mapped:
            r['profit_usd']/=r['contracts'];r['contracts']=1.0
        cut=settings['OOS_START_DATE']
        selected=[r for r in mapped if cut is None or r['datetime']>=cut]
        excluded += [dict(trade_id=r['trade_id'],reason='before OOS_START_DATE',datetime=r['datetime']) for r in mapped if cut is not None and r['datetime']<cut]
        if not selected:raise ValueError('No trades on or after OOS_START_DATE; statistics unavailable.')
        execution=record['execution_settings']
        commission=Decimal(execution['commission_per_contract_per_side'])*2
        nominal_slip=Decimal(execution['tick_size'])*Decimal(execution['point_value'])*execution['slippage_ticks']*2
        normalized={k:sum((Decimal(r[src])/Decimal(r['source_quantity']) for r in selected),Decimal(0)) for k,src in [('gross','source_reference_gross_pnl'),('net','source_net_pnl'),('commission','source_commissions'),('slippage','source_slippage')]}
        effective_slip=normalized['slippage']/len(selected)
        if normalized['commission']!=commission*len(selected):raise ValueError('Saved commission settings differ from actual trade costs.')
        reconciliation=dict(source_totals={k:str(v) for k,v in totals.items()},filtered_normalized_totals={k:str(v) for k,v in normalized.items()},round_trip_commission=str(commission),nominal_round_trip_slippage=str(nominal_slip),effective_round_trip_slippage=str(effective_slip),source_count=len(rows),filtered_count=len(selected),excluded_count=len(excluded),exact_source_arithmetic=True,
            baseline_residual=str(normalized['gross']-normalized['commission']-normalized['slippage']-normalized['net']),
            slippage_contract='Saved setting round trip; if limit fills differ, observed mean per normalized trade reconciles aggregate baseline. Per-trade analysis costs remain the notebook constant formula.')
    if before!=digest(path):raise ValueError('Source changed during adaptation.')
    frame=pd.DataFrame(mapped)
    frame['datetime']=pd.to_datetime(frame['datetime']);frame['date']=frame['datetime'].dt.normalize()
    snapshot=dict(backtest=record,trades_sha256=before,manifest_sha256=sha256(canonical(record).encode()).hexdigest(),source_timezone=str(zone),timestamp_mapping='entry UTC → saved source timezone → timezone-naive; no prop-session remapping',excursion_provenance='No measured MAE/MFE in saved trade storage; fallback MAE=realized loss is not measured.',excluded=excluded,reconciliation=reconciliation)
    overrides=dict(COMMISSION_PER_CONTRACT=float(commission),SLIPPAGE_PER_CONTRACT=float(effective_slip))
    return frame,snapshot,overrides
