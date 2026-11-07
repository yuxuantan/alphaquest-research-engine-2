"""Validated external marks adapted to existing EOD account transitions.

All retained adverse marks are jumps: no interpolated account-stop fill or
unobserved favorable sequence is manufactured. This is a declared-path model,
not measured broker liquidation or tick-completeness certification.
"""
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json
import re

import pandas as pd

from .adapter import canonical


VERSION = 'external-ordered-mark-scenario-v1'


def admission(source):
    m = source['manifest']
    if m['execution']['sizing_path_invariance'] != 'exporter_declared':
        return 'External source sizing-path invariance is unverified. Supply an explicit exporter declaration or rerun the strategy for each quantity; fixed-path scaling is not assumed.'
    if m['instrument']['currency'] != 'USD':
        return 'The current prop account model requires USD trade and risk values.'
    symbol = m['instrument']['symbol'].upper()
    match = re.fullmatch(r'(MNQ|NQ)(?:[!@#12]*|[FGHJKMNQUVXZ]\d{1,4}|[. ]CME)?', symbol)
    if not match or Decimal(m['instrument']['point_value']) != (Decimal(2) if match[1] == 'MNQ' else Decimal(20)) or Decimal(m['instrument']['tick_size']) != Decimal('.25'):
        return 'External prop analysis requires an identified NQ/MNQ instrument with matching tick size and USD point value.'
    if m['research']['phase'] not in ('is', 'oos'):
        return 'Declare the external source research phase and prior access before prop analysis.'
    if m['time']['timestamp_basis'] != 'actual_fill':
        return 'External prop replay requires actual-fill timestamps, not bar-labelled or unknown timing.'
    if not source['capabilities']['ordered_marks_available']:
        return 'Complete ordered risk marks are required; measured MAE/MFE alone cannot establish account-limit crossing order.'
    if not source['validation']['ordered_path_covers_reported_extrema']:
        return 'Reported excursions extend beyond the ordered marks. Their crossing sequence is unknown; supply the missing ordered observations.'
    if len({t['quantity'] for t in source['trades']}) != 1:
        return 'This external fixed-path increment requires one constant source quantity.'
    dates = m['coverage']['sessions']
    expected = [str(d.date()) for d in pd.bdate_range(dates[0], dates[-1])]
    if not 2 <= len(dates) <= 20000 or dates != expected:
        return 'The current EOD model requires an explicitly declared complete inventory of 2–20,000 weekdays, including known no-trade dates. Missing sessions are not invented.'
    from .phase_lifecycle import instant, session_date
    for t in source['trades']:
        if session_date(instant(t['entry_time_utc'])) != session_date(instant(t['exit_time_utc'])):
            return 'External EOD replay requires intraday-flat trades; overnight account state is unsupported.'
    return None


def capabilities(source):
    reason = admission(source)
    return {**source['capabilities'], 'prop_analysis':reason is None,
            'prop_analysis_modes':['annualized'] if reason is None else [],
            'prop_analysis_reason':reason or 'Eligible for the existing annualized EOD model under the disclosed exporter path/calendar assumptions. Independent phase selection and dated replay integration remain pending; no live readiness is certified.'}


def prepare_external(runs, record, trade_file):
    from ..trade_imports import verify_import
    if trade_file:
        raise ValueError('An imported canonical source already contains its risk evidence; a supplemental legacy workbook cannot replace it.')
    source = verify_import(runs, record)
    reason = admission(source)
    if reason:
        raise ValueError(reason)
    m = source['manifest']
    grouped = {}
    for event in source['risk_events']:
        grouped.setdefault(event['trade_id'], []).append(event)
    rows = []
    for ordinal, t in enumerate(source['trades'], 1):
        events = grouped[t['trade_id']]
        values = [Decimal(e['marked_trade_net_equity']) for e in events]
        rows.append(dict(trade_id=ordinal, external_trade_id=t['trade_id'], entry_utc=t['entry_time_utc'],
            exit_utc=t['exit_time_utc'], source_net_pnl=t['net_pnl'], source_commission=t['total_commissions'],
            source_slippage=t['slippage_cost'], quantity=str(t['quantity']), export_net_pnl=None,
            measured_mae=None, measured_mfe=None, observed_mark_mae=str(max(Decimal(0), min(values).copy_negate())),
            observed_mark_mfe=str(max(Decimal(0), max(values))), ordered_events_json=canonical(events)))
    rows[0]['canonical_sessions_json'] = canonical(m['coverage']['sessions'])
    snapshot = dict(backtest=record, source_kind='external_trade_export',
        trades_sha256=record['source_artifacts']['trades.csv'],
        manifest_sha256=sha256(canonical(record).encode()).hexdigest(), source_timezone=m['time']['source_timezone'],
        canonical_source=source['source'], canonical_manifest=m,
        reconciliation=dict(source_totals=source['validation']['totals'], source_count=len(rows), exact_source_arithmetic=True),
        excursion_provenance='Preserved ordered exporter marks in whole-trade net equity. Every adverse retained mark is treated as an observed jump; no interpolated stop fill or missing path is invented. Completeness and size invariance remain exporter declarations.',
        excursion_input=dict(path=None, filename=None, sha256=None, export_timezone=m['time']['source_timezone'],
            matched_trades=len(rows), measured_mae_count=0, measured_mfe_count=0, ordered_mark_count=len(source['risk_events']),
            risk_policy=VERSION, cost_contract='Actual fills already include slippage; original fees reconcile exactly before explicitly modeled commission replacement.'),
        filtering='All original trades and explicitly declared no-trade weekdays are retained; unsupported missing/session calendars reject.',
        external_assumptions=dict(tick_completeness_verified=False, sizing_invariance_verified=False,
            calendar_verified=False, liquidation='First observed breach mark; every mark is a jump, not an inferred continuous threshold fill.'))
    return snapshot, rows


def adapt_costs(snapshot, rows, settings):
    from .commissions import catalog, source_instrument
    record = snapshot['backtest']
    instrument = source_instrument(record)
    if settings['SOURCE_INSTRUMENT'] not in ('auto', instrument):
        raise ValueError('Selected instrument conflicts with the immutable external source.')
    replacing = settings['COMMISSION_MODE'] != 'source'
    rate = settings['COMMISSION_PER_SIDE']
    if replacing and not rate:
        expected = 'Lucid' if settings['PROP_FIRM'] == 'Lucid' else 'Rithmic'
        if settings['COMMISSION_BROKER'] != expected:
            raise ValueError('Enter an explicit per-side MNQ commission for this broker.')
        rate = catalog(settings['PROP_FIRM'])['rates']['MNQ']
    target = Decimal(rate) if replacing else None
    with localcontext(Context(prec=512)):
        for row in rows:
            factor = Decimal(10 if instrument == 'MNQ' else 1)/Decimal(row['quantity'])
            path, high = [], Decimal(0)
            for event in json.loads(row['ordered_events_json']):
                value = Decimal(event['marked_trade_net_equity'])*factor
                if replacing:
                    value += Decimal(event['commissions_charged'])*factor - target*10*(2 if event['kind'] == 'close' else 1)
                loss = max(Decimal(0), -value)
                if loss > high:
                    path.append([str(loss), True]); high = loss
            fee = target*20 if replacing else Decimal(row['source_commission'])*factor
            net = Decimal(row['source_net_pnl'])*factor + Decimal(row['source_commission'])*factor - fee
            row.update(simulation_net_per_nq=str(net), simulation_mae_per_nq=str(high),
                simulation_adverse_path_per_nq=canonical(path), simulation_net_per_mnq=str(net/10),
                simulation_commission_per_nq=str(fee), simulation_commission_per_mnq=str(fee/10))
    snapshot['commission_simulation'] = dict(mode=settings['COMMISSION_MODE'], applied=replacing,
        source_instrument=instrument, detected_source_instrument=instrument, simulated_instrument='MNQ',
        broker=settings['COMMISSION_BROKER'], per_side=rate if replacing else None, schedule=catalog(settings['PROP_FIRM']),
        explanation='Source actual-fill P&L retains slippage once. Source mode retains observed fees; replacement mode removes each event charged fee and inserts one target side while open, two at close. Net and observed-risk paths use the same exact cost basis.',
        risk_policy=VERSION, formula='Normalize each observed net mark by source quantity and instrument point value; replace only commissions when requested. Existing account kernels scale per-NQ inputs by MNQ quantity/10 once.')


def capture(runs, source_id, destination):
    from ..trade_imports import verify_import
    from .adapter import source_record
    import shutil
    record = source_record(runs, source_id)
    verify_import(runs, record)
    destination.mkdir(parents=True, exist_ok=True)
    for name, expected in record['source_artifacts'].items():
        target = destination/name
        shutil.copyfile(runs.root/source_id/name, target)
        if sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError('External source changed during analysis capture.')
