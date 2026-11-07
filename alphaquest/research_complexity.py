"""Reviewed parameter roles for signal qualification, not a universal score.

Sizing changes are researched in the prop-policy stage. Display switches and
quantity knobs must not manufacture a stable signal-parameter neighborhood.
"""
from decimal import Decimal


ROLES = {
    'consecutive_green_hold': dict(sizing=['contracts'], diagnostic=[]),
    'vwap_pullback_risk_sizing': dict(
        sizing=['use_vol_sizing', 'position_size', 'mm_capital_usd', 'mm_risk_pct', 'max_contracts'],
        diagnostic=['plot_trade_levels']),
}


def describe_complexity(strategy_id, parameters):
    roles = ROLES.get(strategy_id)
    if roles is None:
        return dict(status='unreviewed', signal_parameters=sorted(parameters),
                    sizing_parameters=[], diagnostic_parameters=[], enabled_optional_filters=[],
                    definition='No reviewed parameter-role classification for this strategy.')
    excluded = set(roles['sizing']) | set(roles['diagnostic'])
    active, inactive = [], []
    if strategy_id == 'vwap_pullback_risk_sizing':
        active = [name for name in ('use_adx_elev', 'use_adx_decay') if parameters[name]]
        active += [name for name in ('min_rr', 'max_stop_points') if Decimal(str(parameters[name])) > 0]
        if not parameters['use_adx_elev']:
            inactive.append('adx_elev_thr')
        if not parameters['use_adx_decay']:
            inactive.append('adx_decay_lb')
        if not parameters['use_adx_elev'] and not parameters['use_adx_decay']:
            inactive.append('adx_len')
        if parameters['stop_mode'] == 2:
            inactive.append('stop_swing_len')
        if not parameters['use_eod_flat']:
            inactive += ['eod_flat_time', 'close_buffer_minutes']
        if Decimal(str(parameters['buffer_amount'])) == 0:
            inactive.append('buffer_mode')
        # max_bars_back stays active: even when an indicator is disabled, the
        # explicit history length still changes the strategy's cold start.
    return dict(status='reviewed', signal_parameters=sorted(set(parameters) - excluded),
                sizing_parameters=roles['sizing'], diagnostic_parameters=roles['diagnostic'],
                enabled_optional_filters=active, inactive_parameters=sorted(inactive),
                definition='Signal-policy parameter count and enabled optional entry filters; descriptive within a strategy, not comparable model complexity or a weighted selection score.')
