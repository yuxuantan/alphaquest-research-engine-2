"""Causal planned-loss arithmetic and research R diagnostics; no account engine.

Amounts use the report's instrument and costs. R describes a completed trade
against its pre-entry plan, never an equity curve or a new screening verdict.
"""
from collections import Counter
from datetime import date,datetime,timedelta
from decimal import Decimal,InvalidOperation,localcontext
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

VERSION='planned-net-r-v1'
METRIC_COLUMNS=('planned_net_r_mean','planned_net_r_median','planned_net_r_total','risk_coverage_pct')


def decimal(value):
    if isinstance(value,bool):raise ValueError('Risk amounts must be finite decimal numbers.')
    try:result=Decimal(str(value))
    except (InvalidOperation,TypeError,ValueError) as exc:raise ValueError('Risk amounts must be finite decimal numbers.') from exc
    if not result.is_finite():raise ValueError('Risk amounts must be finite decimal numbers.')
    return result


def planned_unit_loss(reference,stop,side,*,tick_size,point_value,entry_slippage_ticks=0,
                      stop_exit_slippage_ticks=0,commission_per_side=0):
    """Instrument-aware pre-entry stop plan; costs are not another P&L debit."""
    from .decimal_math import add,subtract,multiply
    reference,stop,tick,point,commission=map(decimal,(reference,stop,tick_size,point_value,commission_per_side))
    if side not in ('long','short') or tick<=0 or point<=0 or commission<0:
        raise ValueError('Invalid risk direction, instrument or commission.')
    if any(type(v) is not int or v<0 for v in (entry_slippage_ticks,stop_exit_slippage_ticks)):
        raise ValueError('Planning slippage must be nonnegative whole ticks.')
    with localcontext() as ctx:
        ctx.prec=max(80,sum(len(v.as_tuple().digits)+abs(v.as_tuple().exponent) for v in (reference,stop,tick,point,commission))+32)
        if reference%tick or stop%tick:raise ValueError('Risk prices must obey the declared tick grid.')
    distance=multiply(subtract(reference,stop),Decimal(1 if side=='long' else -1))
    if distance<=0:raise ValueError('Initial stop must be adverse to the known decision reference.')
    return add(multiply(add(distance,multiply(tick,Decimal(entry_slippage_ticks+stop_exit_slippage_ticks))),point),multiply(Decimal(2),commission))


def _stamp(value):
    stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('Risk timestamps require an explicit timezone.')
    return stamp


def trade_diagnostic(trade,execution):
    id=trade['trade_id'];stop=trade.get('initial_stop');decision=trade.get('sizing_decision')
    result=dict(trade_id=id,available=False,net_pnl=str(trade['net_pnl']),planned_net_r=None)
    if stop is None:return dict(result,reason='initial_stop_unavailable')
    if decision is None:return dict(result,reason='sizing_decision_unavailable')
    try:
        known,decided,entry=map(_stamp,(stop['known_at_utc'],decision['timestamp_utc'],trade['entry_time_utc']))
        if known>decided or decided>entry:raise ValueError('Initial stop was not known at the entry decision.')
        if decision['execution_timing']=='next_open' and decided>=entry:
            raise ValueError('Next-open entry must follow its sizing decision.')
        quantity=decimal(trade['quantity'])
        if quantity<=0 or quantity!=quantity.to_integral_value():raise ValueError('Filled quantity must be a positive whole contract count.')
        unit=planned_unit_loss(decision['reference_price'],stop['price'],trade['side'],
            tick_size=execution['tick_size'],point_value=execution['point_value'],
            entry_slippage_ticks=execution['slippage_ticks'],stop_exit_slippage_ticks=execution['slippage_ticks'],
            commission_per_side=execution['commission_per_contract_per_side'])
        with localcontext() as ctx:
            ctx.prec=80;total=unit*quantity;value=decimal(trade['net_pnl'])/total
            fill_distance=(decimal(trade['entry_fill_price'])-decimal(stop['price']))*(1 if trade['side']=='long' else -1)
        return dict(result,available=True,reason=None,decision_reference_price=decision['reference_price'],
            initial_stop_price=stop['price'],initial_stop_known_at_utc=stop['known_at_utc'],
            sizing_decision_time_utc=decision['timestamp_utc'],quantity=int(quantity),point_value=execution['point_value'],
            planned_risk_per_contract=str(unit),planned_total_risk=str(total),planned_net_r=str(value),
            actual_fill_to_initial_stop_distance=str(fill_distance),initial_stop_adverse_to_actual_fill=fill_distance>0,
            actual_fill_is_diagnostic_only=True)
    except (ValueError,KeyError,TypeError,InvalidOperation) as exc:
        return dict(result,reason='invalid_initial_risk',detail=str(exc))


def summarize(source):
    """Consume an already verified canonical native source, with honest coverage."""
    record=source['source']['native_manifest'];execution=record['execution_settings'];trades=source['trades']
    rows=[trade_diagnostic(t,execution) for t in trades];valid=[decimal(r['planned_net_r']) for r in rows if r['available']]
    zone=ZoneInfo(record['run_metadata'].get('dataset',{}).get('source_timezone','UTC'))
    first=_stamp(record['period_start_utc']).astimezone(zone).date();last=_stamp(record['period_end_utc']).astimezone(zone).date()
    grouped={}
    for trade,row in zip(trades,rows,strict=True):
        month=_stamp(trade['exit_time_utc']).astimezone(zone).date().replace(day=1)
        grouped.setdefault(month,[]).append(row)
    monthly=[];month=first.replace(day=1)
    with localcontext() as ctx:
        ctx.prec=80
        while month<=last:
            following=date(month.year+(month.month==12),month.month%12+1,1);end=following-timedelta(days=1)
            if first<=month and end<=last:
                members=grouped.get(month,[]);values=[decimal(r['planned_net_r']) for r in members if r['available']]
                monthly.append(dict(month=str(month)[:7],trades=len(members),valid_r_trades=len(values),
                    total_planned_net_r=str(sum(values,Decimal(0))) if len(values)==len(members) else None,
                    mean_planned_net_r=str(sum(values,Decimal(0))/len(values)) if values and len(values)==len(members) else None))
            month=following
        stats=dict(mean_planned_net_r=str(sum(valid,Decimal(0))/len(valid)) if valid else None,
            median_planned_net_r=str(median(valid)) if valid else None,total_planned_net_r=str(sum(valid,Decimal(0))) if valid else None,
            worst_planned_net_r=str(min(valid)) if valid else None,best_planned_net_r=str(max(valid)) if valid else None)
    complete=bool(rows) and len(valid)==len(rows)
    if not complete:stats={key:None for key in stats}
    return dict(version=VERSION,implementation_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        status='complete' if complete else 'partial' if valid else 'unavailable',
        coverage=dict(valid_trades=len(valid),total_trades=len(rows),complete=complete,
            missing_reasons=dict(Counter(r['reason'] for r in rows if not r['available']))),
        summary=stats,complete_months=monthly,trades=rows,source=source['source'],
        division_precision=80,month_basis='Source timezone; complete observed calendar months; zero-trade months retained.',
        definition='Actual net trade P&L / (filled quantity * pre-decision initial-stop loss including declared entry/stop-exit slippage and round-trip commission).',
        interpretation='Planned net R is a closed-trade diagnostic. It is not MTM equity, a resized strategy replay, or a campaign passing criterion. Missing risk is never inferred; full-history summaries require complete coverage.')


def from_report(runs,id):
    from .prop.adapter import source_record
    record=source_record(runs,id)
    capture=record.get('risk_diagnostics')
    if capture is not None:
        raw=(Path(runs.root)/id/'risk_metrics.json').read_bytes()
        if sha256(raw).hexdigest()!=capture['sha256']:raise ValueError('Saved risk diagnostics changed.')
        value=json.loads(raw)
        if value['version']!=capture['version']:raise ValueError('Saved risk diagnostics version differs.')
        for name,expected in value['source']['artifact_sha256'].items():
            if sha256((Path(runs.root)/id/name).read_bytes()).hexdigest()!=expected:raise ValueError('Risk diagnostic source changed.')
        return value
    from .canonical_trades import project_native_source
    return summarize(project_native_source(runs,id,include_intratrade=False))


def from_artifacts(directory,record):
    """Project the writer's verified native decisions; never require MAE data."""
    import csv
    from .decision_capture import SIDE_CAR,read_decision_evidence
    directory=Path(directory)
    with (directory/'trades.csv').open(newline='') as f:rows=list(csv.DictReader(f))
    if len(rows)!=record['summary']['trades_taken']:raise ValueError('Risk diagnostics trade count differs from report.')
    evidence=(read_decision_evidence(directory/SIDE_CAR,record['execution_decisions'],rows,record['execution_settings'])
              if record.get('execution_decisions') is not None else None)
    trades=[]
    for row in rows:
        item=dict(row,trade_id=int(row['trade_number']),quantity=int(row['contracts']),initial_stop=None,sizing_decision=None)
        if evidence is not None:
            decision=evidence['trades'][str(item['trade_id'])]
            item.update(initial_stop=decision['initial_stop'],sizing_decision=decision['sizing_decision'])
        trades.append(item)
    hashes={'trades.csv':sha256((directory/'trades.csv').read_bytes()).hexdigest()}
    if evidence is not None:hashes[SIDE_CAR]=record['execution_decisions']['sha256']
    return summarize(dict(source=dict(native_manifest=record,artifact_sha256=hashes),trades=trades))


def result_metrics(record):
    data=record.get('risk_diagnostics')
    if not data:return dict.fromkeys(METRIC_COLUMNS)
    c=data['coverage'];s=data['summary']
    with localcontext() as ctx:
        ctx.prec=80
        return dict(planned_net_r_mean=s['mean_planned_net_r'],planned_net_r_median=s['median_planned_net_r'],
            planned_net_r_total=s['total_planned_net_r'],risk_coverage_pct=str(Decimal(c['valid_trades'])*100/c['total_trades']) if c['total_trades'] else None)
