"""Editable broker schedules and source-to-MNQ commission replacement.

The account model orders MNQ, including at multiples of ten. Source costs are
reconciled first; this module never edits the source or invents measured risk.
"""
from decimal import Decimal
import json
import re

SCHEDULE_URL = 'https://apextraderfunding.com/help-center/rithmic/rithmic-commissions-instruments/'
SCHEDULE_DATE = '2026-10-29'
# USD per contract per side, copied from the cited Apex Rithmic schedule.
RITHMIC = {symbol: rate for symbols, rate in (
    ('ES NKD NQ YM EMD RTY', '1.99'),
    ('6A 6B 6C 6E 6J 6S 6N', '2.36'),
    ('HE LE GF ZC ZW ZS ZM ZL', '2.79'),
    ('CL NG HO RB', '1.98'), ('QM', '1.96'), ('QG', '1.26'),
    ('GC SI HG PL PA', '2.31'), ('MES MYM MNQ M2K MCL', '0.51'),
    ('SIL MGC', '0.76'), ('M6A M6E', '0.42'), ('MBT', '2.76'), ('MET', '0.46'),
) for symbol in symbols.split()}


def catalog():
    return dict(broker='Rithmic', currency='USD', unit='per contract per side',
                checked_on=SCHEDULE_DATE, source_url=SCHEDULE_URL, rates=RITHMIC)


def source_instrument(record):
    metadata = record['run_metadata']
    symbol = str(metadata['dataset'].get('symbol') or metadata.get('full_dataset', {}).get('symbol') or '').strip().upper()
    # Accept continuous and dated contracts, but never guess from a file name.
    for root in ('MNQ', 'NQ'):
        if re.fullmatch(root + r'(?:[!@#12]*|[FGHJKMNQUVXZ]\d{1,4}|[. ]CME)?', symbol):
            return root
    return ''


def adapt(snapshot, rows, settings):
    """Keep source columns immutable and add inspectable simulation amounts."""
    record = snapshot['backtest']
    detected = source_instrument(record)
    instrument = detected if settings['SOURCE_INSTRUMENT'] == 'auto' else settings['SOURCE_INSTRUMENT']
    policy = dict(broker=settings['COMMISSION_BROKER'], simulated_instrument='MNQ',
                  source_instrument=instrument or None, detected_source_instrument=detected or None,
                  schedule=catalog(), per_side=settings['COMMISSION_PER_SIDE'],
                  mode=settings['COMMISSION_MODE'])
    snapshot['commission_simulation'] = policy
    if instrument:
        if detected and detected != instrument:
            raise ValueError('Selected source instrument conflicts with the saved dataset symbol.')
        point_value = Decimal(str(record['execution_settings']['point_value']))
        if point_value != (Decimal(20) if instrument == 'NQ' else Decimal(2)):
            raise ValueError('Source instrument point value must be USD 20 for NQ or USD 2 for MNQ. Check the saved backtest instrument settings.')
    if settings['COMMISSION_MODE'] == 'source' or not instrument:
        if (settings['COMMISSION_MODE'] == 'override' or settings['COMMISSION_PER_SIDE']) and not instrument and settings['COMMISSION_MODE'] != 'source':
            raise ValueError('Select NQ or MNQ as the source instrument before overriding commission. Other source instruments are not supported by this NQ/MNQ model.')
        if instrument == 'MNQ':
            for row in rows:
                factor = Decimal(10) / Decimal(row['quantity'])
                net = Decimal(row['source_net_pnl']) * factor
                raw_mae = row.get('ohlc_mae_upper') or row.get('measured_mae')
                row.update(simulation_net_per_nq=str(net), simulation_mae_per_nq=str(Decimal(raw_mae) * factor if raw_mae is not None else max(Decimal(0), -net)))
                if row.get('ohlc_adverse_path') is not None:
                    row['simulation_adverse_path_per_nq'] = json.dumps([[str(Decimal(amount)*factor),gap] for amount,gap in json.loads(row['ohlc_adverse_path'])])
        policy.update(applied=False, explanation='Retains source net costs, normalized to the source instrument when identified. Source instrument is unidentified or source-cost mode was selected; broker MNQ commission has not been applied.')
        return
    rate = settings['COMMISSION_PER_SIDE']
    if rate == '':
        if settings['COMMISSION_BROKER'] != 'Rithmic':
            raise ValueError('Enter an explicit per-side MNQ commission for this broker.')
        rate = RITHMIC['MNQ']
    target = Decimal(rate)
    # Existing kernel uses ten micro units per reference NQ contract.
    factor = Decimal(1) if instrument == 'NQ' else Decimal(10)
    totals = dict(source_commission=Decimal(0), source_net=Decimal(0),
                  simulated_commission=Decimal(0), simulated_net=Decimal(0))
    for row in rows:
        q = Decimal(row['quantity'])
        old_net = Decimal(row['source_net_pnl']) / q * factor
        old_fee = Decimal(row['source_commission']) / q * factor
        new_fee = target * 20
        net = old_net + old_fee - new_fee
        delta = new_fee - old_fee
        row.update(simulation_net_per_nq=str(net), simulation_commission_per_nq=str(new_fee),
                   source_net_per_nq=str(old_net), source_commission_per_nq=str(old_fee),
                   simulation_net_per_mnq=str(net / 10), simulation_commission_per_mnq=str(new_fee / 10))
        totals['source_commission'] += old_fee
        totals['source_net'] += old_net
        totals['simulated_commission'] += new_fee
        totals['simulated_net'] += net
        raw_mae = row.get('ohlc_mae_upper') or row.get('measured_mae')
        if raw_mae is None:
            row['simulation_mae_per_nq'] = str(max(Decimal(0), -net))
            continue
        # Stored frontiers omit dominated marks and do not label entry vs exit
        # commissions. Reserve the larger adjustment across one/two fee sides.
        # This is conservative, not an exact repriced tick path. Include the
        # new entry fee and actual realized exit even if absent from the source.
        reserve = max(delta / 2, delta)
        mae = max(Decimal(0), Decimal(raw_mae) / q * factor + reserve, -net, new_fee / 2)
        row['simulation_mae_per_nq'] = str(mae)
        if row.get('ohlc_adverse_path') is not None:
            path = [[str(new_fee / 2), True]] if new_fee > 0 else []
            high = new_fee / 2
            for amount, gap in json.loads(row['ohlc_adverse_path']):
                loss = max(Decimal(0), Decimal(amount) / q * factor + reserve)
                if loss > high:
                    path.append([str(loss), gap]); high = loss
            if -net > high:
                path.append([str(-net), True]); high = -net
            row['simulation_adverse_path_per_nq'] = json.dumps(path, separators=(',', ':'))
            row['simulation_mae_per_nq'] = str(high)
    policy.update(applied=True, per_side=rate, round_turn=str(target * 2),
                  source_to_nq_factor=str(factor),
                  formula='(source net + actual source commission) / source quantity * source-to-NQ factor / 10 - 2 * MNQ per-side rate, per simulated MNQ round turn. Source slippage retained.',
                  risk_policy='Captured/measured source excursions remain unchanged. Simulation uses conservative commission-adjusted bounds, reserving max(one-side fee delta, round-turn fee delta), entry commission and realized exit loss. These are not measured repriced MAE/MFE. Close-only sources retain a realized-loss fallback.',
                  normalization='Totals below sum one NQ-equivalent exposure per source trade; divide by ten for one MNQ.',
                  totals_per_nq={k: str(v) for k, v in totals.items()})
