"""Trade-close strategy diagnostics at an allocation frozen in Prop Desk."""

import csv
from datetime import timezone
from decimal import Decimal
from pathlib import Path

import numpy as np

from ..optimization_cache import digest
from . import desk, desk_basket
from .adapter import canonical, digest as file_digest
from .phase_profiles import verify_phase_source

MODE = 'prop_desk_diagnostics'
VERSION = 'prop-desk-diagnostics-v1'
STANDALONE_VERSION = 'prop-desk-diagnostics-standalone-v1'
CONE_PATHS, MATRIX_PATHS, SEED = 2000, 10000, 42
HORIZONS = (10, 20, 30, 50, 100)
PERCENTILES = (5, 25, 50, 75, 95)
MODEL = dict(
    trade_basis='Standalone saved closed trades in chronological exit order. '
                'No shared-account overlap, provider caps, stops or payouts.',
    cost_basis='Saved net P&L, commission and slippage scaled linearly to the selected whole MNQ. '
               'NQ converts at 10 MNQ per contract. Costs are already included in net P&L.',
    sampling='Independent trade draws with replacement (NumPy PCG64). Linear pointwise percentiles.',
    cone_paths=CONE_PATHS, matrix_paths=MATRIX_PATHS, seed=SEED, matrix_seed=SEED + 1,
    minimum_is_trades=2, minimum_matrix_trades=2,
    drawdown_basis='USD below the running high from zero after each closed trade. '
                   'The historical peak carries across the split. A return to the peak closes '
                   'the episode. Any active episode is open at the last observed trade.',
    matrix_basis='Independent held-out trade draws. Compare current drawdown depth to '
                 'maximum drawdown from zero and the last N held-out trades to simulated sums.',
)
STATUS_BASIS = ('Retrospective held-out review. Warning and Critical use the 95th-percentile '
                'maximum drawdown of simulated 10- and 100-trade sequences. Drawdown starts at zero '
                'at the held-out boundary. A new high clears the status. Critical eases to Warning '
                'after recovering half of the deepest drawdown since that high. Thresholds use '
                'the entire held-out window. Status does not enter sizing or ranking.')


def selection(parent, terms):
    """Resolve membership, weights and sizing only from a verified parent."""
    config = parent['configuration']
    size, combo_id, source_id = terms['micros'], terms['combination'], terms['source_backtest_id']
    if 'optimizer' in parent:
        search = parent['optimizer']
        combo = next((item for item in search['combinations'] if item['id'] == combo_id), None)
        if combo is None:
            raise ValueError('Select a saved Optimise combination.')
        members = [config['members'][index] for index in combo['members']]
        sizes = combo['sizes']
    elif 'basket' in parent and combo_id is None:
        members, sizes = config['members'], parent['basket']['sizes']
    elif 'basket' not in parent and combo_id is None:
        members = [dict(source_backtest_id=config['source_backtest_id'], weight=1)]
        sizes = [dict(micros=config['micros'], allocation={'micros': [config['micros']]})]
    else:
        raise ValueError('A Simulation result has no Optimise combination.')
    row = next((item for item in sizes if item['micros'] == size), None)
    if row is None:
        raise ValueError('Select a tested total MNQ from this report.')
    index = next((i for i, member in enumerate(members) if member['source_backtest_id'] == source_id), None)
    if index is None:
        raise ValueError('Select a strategy in the saved Simulation or Optimise row.')
    target = 1 if terms.get('size_basis') == 'standalone' else row['allocation']['micros'][index]
    if not target:
        raise ValueError('This strategy has a zero target at the selected size. Inspect a larger tested size.')
    member = members[index]
    sources = parent['sources'] if 'sources' in parent else {'is': [parent['source']]}
    snapshots = {}
    for role, key in (('is', 'source_backtest_id'), ('oos', 'oos_backtest_id')):
        if member.get(key):
            snapshot = next((item for item in sources.get(role, [])
                             if item['backtest']['id'] == member[key]), None)
            if snapshot is None:
                raise ValueError(f'The parent report has no saved {role.upper()} source fingerprint.')
            snapshots[role] = snapshot
    return member, snapshots, target


def verify_sources(runs, snapshots):
    for snapshot in snapshots.values():
        verify_phase_source(runs, desk.SavedTradeSource(snapshot['backtest']['id']), snapshot)


def prepare(runs, analyses, terms, datasets, parent, parent_sha):
    member, snapshots, target = selection(parent, terms)
    verify_sources(runs, snapshots)
    record = desk_basket.checked_record(runs, member['source_backtest_id'], 'is')
    records = {'is': record}
    if 'oos' in snapshots:
        records['oos'] = desk_basket.checked_record(runs, member['oos_backtest_id'], 'oos', record)
    dataset = record['run_metadata']['dataset']
    current = datasets.get(dataset['id'])
    if not current or current['sha256'] != dataset['sha256']:
        raise ValueError('The original saved strategy dataset is unavailable or its identity changed.')
    inventory = desk_basket.inventory_sessions(datasets, dataset['id'], minimum_sessions=1)
    windows = {role: desk_basket.period([source], inventory, role) for role, source in records.items()}
    if 'oos' in windows and windows['oos'][0] <= windows['is'][-1]:
        raise ValueError('The strategy OOS window must follow its IS window.')
    profile = desk.FundedProfile(parent['configuration']['profile_id'],
                                desk.rule_version(parent['configuration']['profile_id']))
    ledger, captures = {}, {}
    for role, source in records.items():
        capture, book = desk_basket.source_book(runs, analyses, source, profile, windows[role])
        if any(capture[key] != snapshots[role][key] for key in ('manifest_sha256', 'trades_sha256')):
            raise ValueError(f'The saved {role.upper()} source changed while preparing diagnostics.')
        captures[role] = capture
        rows = [(day, row) for day, trades in book.items() for row in trades]
        ledger[role] = [
            dict(role=role, session=day, source_backtest_id=source['id'], source_trade_id=row['id'],
                 entry_utc=row['entry'].astimezone(timezone.utc).isoformat(),
                 exit_utc=row['exit'].astimezone(timezone.utc).isoformat(), target_mnq=target,
                 commission=str(row['commission'] * target), slippage=str(row['slippage'] * target),
                 net_pnl=str(row['net'] * target))
            for day, row in sorted(rows, key=lambda item: (item[1]['exit'], int(item[1]['id'])))
        ]
    if len(ledger['is']) < MODEL['minimum_is_trades']:
        raise ValueError('Strategy diagnostics require at least two standalone closed IS trades.')
    if ledger.get('oos') and ledger['is'][-1]['exit_utc'] > ledger['oos'][0]['exit_utc']:
        raise ValueError('IS and OOS trade closes must be chronological across the saved split.')
    verify_sources(runs, snapshots)
    standalone = terms.get('size_basis') == 'standalone'
    identity = dict(model_version=STANDALONE_VERSION if standalone else VERSION, parent_report_sha256=parent_sha,
                    configuration=dict(terms, allocated_mnq=target, weight=member['weight']),
                    model=MODEL, implementation_sha256=file_digest(Path(__file__)), numpy_version=np.__version__,
                    dataset=inventory['source'], windows=windows, ledger_sha256=digest(ledger))
    return dict(identity=identity, ledger=ledger, snapshots=captures, dataset=current)


def history(ledger):
    equity = peak = Decimal(0)
    start = 0
    active = None
    episodes, curve = [], []
    for number, row in enumerate(ledger, 1):
        equity += Decimal(row['net_pnl'])
        if equity >= peak:
            if active is not None:
                episodes.append(dict(active, recovered_at=number, through_trade=number,
                                     duration_trades=number - active['peak_trade']))
                active = None
            peak, start = equity, number
        else:
            depth = peak - equity
            if active is None:
                active = dict(peak_trade=start, trough_trade=number, depth=depth)
            elif depth > active['depth']:
                active.update(trough_trade=number, depth=depth)
        curve.append(dict(trade=number, role=row['role'], date=row['exit_utc'],
                          equity=float(equity), drawdown=float(equity - peak)))
    if active is not None:
        episodes.append(dict(active, recovered_at=None, through_trade=len(curve),
                             duration_trades=len(curve) - active['peak_trade']))
    for episode in episodes:
        episode['depth'] = float(episode['depth'])
    return dict(curve=curve, episodes=episodes, net=float(equity),
                maximum_drawdown=max((row['depth'] for row in episodes), default=0),
                current_drawdown=curve[-1]['drawdown'],
                longest_drawdown_trades=max((row['duration_trades'] for row in episodes), default=0))


def held_out_status(rows, warning, critical):
    peak = deepest = previous_depth = 0
    peak_trade = None
    state = 'OK'
    transitions = []
    for row in history(rows)['curve']:
        equity, depth = row['equity'], -row['drawdown']
        next_state, reason = state, None
        if equity > peak:
            peak, deepest, peak_trade = equity, 0, row['trade']
            next_state, reason = 'OK', 'New high'
        else:
            deepest = max(deepest, depth)
            if state == 'Critical' and depth <= deepest / 2:
                next_state, reason = 'Warning', 'Recovered half of the deepest drawdown'
            elif state != 'Critical' and previous_depth <= critical < depth:
                next_state, reason = 'Critical', 'Crossed the 100-trade drawdown line'
            elif state == 'OK' and depth > warning:
                next_state, reason = 'Warning', 'Crossed the 10-trade drawdown line'
        if next_state != state:
            transitions.append(dict(trade=row['trade'], date=row['date'], status=next_state,
                                    drawdown=-depth, reason=reason))
            state = next_state
        previous_depth = depth
    return dict(status=state, drawdown=-previous_depth, deepest_since_high=-deepest, peak_trade=peak_trade,
                warning_line=-warning, critical_line=-critical, transitions=transitions, basis=STATUS_BASIS)


def cone(is_values, horizon, rng, paths, observed):
    """Keep all trade steps in the simulation and bound chart detail for long histories."""
    values = np.asarray(is_values)
    cumulative = np.zeros(paths)
    steps = set(np.linspace(0, horizon, min(801, horizon + 1), dtype=int))
    columns = [dict(trade=0, bands=[0] * len(PERCENTILES))]
    for step in range(1, horizon + 1):
        cumulative += values[rng.integers(len(values), size=paths)]
        if step in steps:
            columns.append(dict(trade=step, bands=np.percentile(cumulative, PERCENTILES, method='linear').tolist()))
    return dict(horizon_trades=horizon, percentiles=PERCENTILES, points=columns,
                observed_endpoint_percentile=None if observed is None else
                float(np.mean(cumulative < observed) * 100))


def matrix(values, current_depth, rng, paths):
    values = np.asarray(values)
    samples = values[rng.integers(len(values), size=(paths, max(HORIZONS)))]
    equity = np.cumsum(samples, axis=1)
    depths = np.maximum.accumulate(np.maximum(0, np.maximum.accumulate(equity, axis=1)) - equity, axis=1)
    rows = []
    for horizon in HORIZONS:
        loss = depths[:, horizon - 1]
        net = equity[:, horizon - 1]
        observed = float(values[-horizon:].sum()) if len(values) >= horizon else None
        rows.append(dict(trades=horizon, drawdown_usd=(-np.percentile(loss, [5, 50, 95], method='linear')).tolist(),
                         drawdown_percentile=float(np.mean(loss < current_depth) * 100),
                         sum_usd=np.percentile(net, [5, 50, 95], method='linear').tolist(), observed_sum=observed,
                         sum_percentile=None if observed is None else float(np.mean(net < observed) * 100)))
    return rows


def calculate(prepared, staged):
    ledger = prepared['ledger']
    rows = ledger['is'] + ledger.get('oos', [])
    with (staged / 'strategy_trades.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    history_result = history(rows)
    is_values = [float(row['net_pnl']) for row in ledger['is']]
    oos_values = [float(row['net_pnl']) for row in ledger.get('oos', [])]
    observed = float(sum(Decimal(row['net_pnl']) for row in ledger.get('oos', []))) if oos_values else None
    cone_rng = np.random.Generator(np.random.PCG64(SEED))
    matrix_rng = np.random.Generator(np.random.PCG64(SEED + 1))
    bands = cone(is_values, len(oos_values) or len(is_values), cone_rng, CONE_PATHS, observed)
    draws = (matrix(oos_values, -history_result['current_drawdown'],
                    matrix_rng, MATRIX_PATHS)
             if len(oos_values) >= MODEL['minimum_matrix_trades'] else [])
    result = dict(**history_result, cone=bands, matrix=draws, matrix_horizons=HORIZONS,
                  is_trades=len(is_values), oos_trades=len(oos_values), observed_oos_net=observed,
                  is_net=history_result['curve'][len(is_values) - 1]['equity'])
    if prepared['identity']['model_version'] == STANDALONE_VERSION and draws:
        result['held_out_status'] = held_out_status(
            ledger['oos'], -draws[0]['drawdown_usd'][-1], -draws[-1]['drawdown_usd'][-1])
    (staged / 'strategy_diagnostics.json').write_text(canonical(result), encoding='utf-8')
    return {key: result[key] for key in ('net', 'maximum_drawdown', 'current_drawdown',
                                          'longest_drawdown_trades', 'is_trades', 'oos_trades')}
