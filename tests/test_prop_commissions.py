"""Independent cost arithmetic, risk boundaries and broker/source validation."""
from copy import deepcopy
from decimal import Decimal
import json

import pytest

from alphaquest.prop.commissions import adapt, catalog, source_instrument
from alphaquest.prop.native_analysis import resolved_settings, day_book
from alphaquest.prop.native_engine import FundedAccount


def source(symbol='NQ', point='20', net='1986.02', fee='3.98', quantity='1', path=None):
    snapshot=dict(backtest=dict(run_metadata=dict(dataset=dict(symbol=symbol)),execution_settings=dict(point_value=point)))
    row=dict(trade_id=1,entry_utc='2026-01-05T18:00:00Z',exit_utc='2026-01-05T18:01:00Z',
             quantity=quantity,source_net_pnl=net,source_commission=fee,source_slippage='10',
             export_net_pnl=None,measured_mae=None,measured_mfe=None)
    if path is not None:
        row.update(ohlc_mae_upper=path[-1][0] if path else '0',ohlc_adverse_path=json.dumps(path))
    return snapshot,[row]


def test_rithmic_rates_and_cost_replacement_at_all_candidate_sizes():
    assert catalog()['rates']['NQ']=='1.99' and catalog()['rates']['MNQ']=='0.51'
    snapshot,rows=source();original=deepcopy(rows)
    adapt(snapshot,rows,resolved_settings({}))
    # Source: $2,000 price P&L - $10 slippage - $3.98 commission.
    # One MNQ: $200 - $1 - $1.02 = $197.98 (not $198.602).
    for size in (1,10,25,40):
        actual=Decimal(rows[0]['simulation_net_per_nq'])*size/10
        assert actual==Decimal('197.98')*size
        assert Decimal(rows[0]['simulation_commission_per_nq'])*size/10==Decimal('1.02')*size
    assert all(rows[0][k]==v for k,v in original[0].items())
    assert snapshot['commission_simulation']['totals_per_nq']['simulated_net']=='1979.80'


@pytest.mark.parametrize('rate,expected', [('0','1990.00'),('0.7','1976.00'),('1.99','1950.20')])
def test_custom_broker_override_and_zero_commission(rate,expected):
    snapshot,rows=source()
    adapt(snapshot,rows,resolved_settings(dict(COMMISSION_BROKER='My broker',COMMISSION_PER_SIDE=rate)))
    assert Decimal(rows[0]['simulation_net_per_nq'])==Decimal(expected)


def test_native_mnq_quantity_normalizes_once_and_retains_costs_once():
    snapshot,rows=source('MNQ','2',net='395.96',fee='2.04',quantity='2')
    adapt(snapshot,rows,resolved_settings({}))
    assert Decimal(rows[0]['simulation_net_per_nq'])==Decimal('1979.80')
    assert snapshot['commission_simulation']['source_to_nq_factor']=='10'
    snapshot,rows=source('MNQ','2',net='395.96',fee='2.04',quantity='2')
    adapt(snapshot,rows,resolved_settings(dict(COMMISSION_MODE='source')))
    assert Decimal(rows[0]['simulation_net_per_nq'])==Decimal('1979.80')
    assert snapshot['commission_simulation']['applied'] is False


def test_close_only_realized_risk_and_costs_can_cross_account_floor():
    snapshot,rows=source(net='-994')
    adapt(snapshot,rows,resolved_settings({}))
    assert Decimal(rows[0]['simulation_net_per_nq'])==Decimal('-1000.22')
    _,days,_=day_book(rows,resolved_settings({}))
    old=FundedAccount(equity=-1000);old.advance([(-994.,994.)],10)
    new=FundedAccount(equity=-1000);new.advance(days[0],10)
    assert old.outcome=='open' and new.outcome=='blown'


def test_captured_path_uses_conservative_reserve_and_keeps_source_observations():
    snapshot,rows=source(net='-994',path=[['1.99',True],['100',False],['994',True]])
    original=deepcopy(rows)
    adapt(snapshot,rows,resolved_settings({}))
    assert rows[0]['ohlc_adverse_path']==original[0]['ohlc_adverse_path']
    assert json.loads(rows[0]['simulation_adverse_path_per_nq'])==[
        ['5.10',True],['8.21',True],['106.22',False],['1000.22',True]]
    assert rows[0]['simulation_mae_per_nq']=='1000.22'
    # With a lower rate, the one-side reduction is the conservative bound.
    snapshot,rows=source(path=[['10',True]])
    adapt(snapshot,rows,resolved_settings(dict(COMMISSION_PER_SIDE='0')))
    assert Decimal(rows[0]['simulation_mae_per_nq'])==Decimal('8.01')


def test_measured_excursions_are_preserved_and_not_claimed_remeasured():
    snapshot,rows=source();rows[0].update(measured_mae='20',measured_mfe='2100')
    adapt(snapshot,rows,resolved_settings({}))
    assert rows[0]['measured_mae']=='20' and rows[0]['measured_mfe']=='2100'
    assert Decimal(rows[0]['simulation_mae_per_nq'])==Decimal('26.22')
    assert 'not measured' in snapshot['commission_simulation']['risk_policy']


@pytest.mark.parametrize('symbol', ['NQ','NQ1!','NQZ26','MNQ','MNQH2027'])
def test_source_symbol_detection(symbol):
    snapshot,_=source(symbol)
    assert source_instrument(snapshot['backtest'])==('MNQ' if symbol.startswith('M') else 'NQ')


def test_source_symbol_in_immutable_full_dataset_metadata():
    snapshot,_=source('')
    snapshot['backtest']['run_metadata']['full_dataset']=dict(symbol='NQ')
    assert source_instrument(snapshot['backtest'])=='NQ'


def test_unknown_source_is_explicit_and_cannot_silently_ignore_an_override():
    snapshot,rows=source('CUSTOM');original=deepcopy(rows)
    adapt(snapshot,rows,resolved_settings({}))
    assert rows==original and snapshot['commission_simulation']['applied'] is False
    with pytest.raises(ValueError,match='Select NQ or MNQ'):
        adapt(snapshot,rows,resolved_settings(dict(COMMISSION_PER_SIDE='0.7')))
    adapt(snapshot,rows,resolved_settings(dict(SOURCE_INSTRUMENT='NQ',COMMISSION_PER_SIDE='0.7')))
    assert snapshot['commission_simulation']['applied']


@pytest.mark.parametrize('change', [dict(COMMISSION_PER_SIDE='NaN'),dict(COMMISSION_PER_SIDE='-1'),
    dict(COMMISSION_PER_SIDE=0.51),dict(COMMISSION_PER_SIDE='inf'),dict(COMMISSION_MODE='invalid'),
    dict(SOURCE_INSTRUMENT='ES'),dict(COMMISSION_BROKER='')])
def test_invalid_settings_reject(change):
    with pytest.raises(ValueError):resolved_settings(change)


def test_mismatched_identity_or_point_value_and_missing_custom_rate_reject():
    for symbol,point,overrides in [('NQ','2',{}),('NQ','20',dict(SOURCE_INSTRUMENT='MNQ')),
                                 ('NQ','20',dict(COMMISSION_BROKER='Other'))]:
        snapshot,rows=source(symbol,point)
        with pytest.raises(ValueError):adapt(snapshot,rows,resolved_settings(overrides))
