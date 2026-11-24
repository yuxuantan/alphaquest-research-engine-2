"""Analytical signal, execution, calendar, and paired-source oracles."""
import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import io
from math import log, sqrt
from pathlib import Path
import re

import pytest

from alphaquest.backtest_data import DateRange, read_selected_bars
from alphaquest.datasets import COLUMNS, PAIRED_COLUMNS, DatasetStore, InvalidDataset, validate_csv
from alphaquest.execution import Trade, execute
from alphaquest.pair_relative_strength import pair
from alphaquest.prepared_data import prepare_data
from alphaquest.strategies.relative_strength import CT, HOLIDAYS, Parameters, RelativeStrength
from alphaquest.strategies.registry import get_strategy
from alphaquest.strategy import ExecutionConfig


DATES = ('11/20/2025', '11/21/2025', '11/24/2025', '11/25/2025', '11/26/2025',
         '11/27/2025', '11/28/2025', '12/01/2025', '12/02/2025')
CONFIG = ExecutionConfig(D(10000), D('.25'), D(20), 0, D(0))


def product_fixture(direction=1, outcome='target', late_check=False):
    """Synthetic data with prior RTH ranges of exactly 20 and a final independent shock."""
    rows = [','.join(PAIRED_COLUMNS)]
    for date in DATES:
        base = datetime.strptime(date, '%m/%d/%Y').replace(hour=8, minute=30)
        for slot in range(-1, 391):
            open_ = close = 20000 + (0, 1, 0, -1)[slot % 4]
            es = 5000 + (.25 if slot % 2 else 0)
            high, low = 20010, 19990
            if date in DATES[5:7] and slot == 30:
                open_ = close = 20400
                high = 20410  # An ineligible date's extreme must never enter the range average.
            if date == DATES[7]:
                if slot == 30 and late_check:
                    continue
                if slot >= 30 + late_check:
                    open_ = close = 20000 + direction * 100
                    high, low = close + 1, close - 1
                if slot == 31 + late_check:
                    high, low = close + 30, close - 30  # Both levels touched before either is active.
                if slot == 32 + late_check:
                    if outcome == 'target':
                        high, low = (close + 20, close - 1) if direction == 1 else (close + 1, close - 20)
                    if outcome == 'stop':
                        high, low = (close + 1, close - 12) if direction == 1 else (close + 12, close - 1)
                if slot == 390:
                    close += direction * 5
                    high, low = max(high, close), min(low, close)
            rows.append(','.join(map(str, (date, (base + timedelta(minutes=slot)).strftime('%H:%M'),
                        open_, high, low, close, 1, 1, 0, es))))
    return ('\n'.join(rows) + '\n').encode(), '2025-11-20', '2025-12-01', '2025-12-02'


def save(store, raw):
    return store.save(raw, validate_csv(raw, 'synthetic-relative-strength.csv', CT.key), 'SYNTHETIC Relative Strength', 'NQ')


def stamp(minutes):
    return datetime(2025, 12, 1, 9, minutes, tzinfo=CT).astimezone(timezone.utc)


def test_embedded_calendars_match_supplied_source():
    source = Path('docs/strategies/relative_strength.pl').read_text()
    codes = [int(n) for n in re.findall(r'Hol(?:Full|Early)\[\d+\] = (\d+)', source)]
    assert len(codes) == 207
    net = Path('multicharts/OFB_RelStrength_Signal.cs').read_text().split('private static readonly HashSet<int> Holidays')[1].split('};')[0]
    assert HOLIDAYS == set(codes) == {int(n) for n in re.findall(r'\b\d{7}\b', net)}
    description = get_strategy('relative_strength').description()
    trade_dir, = [parameter for parameter in description['parameters'] if parameter['name'] == 'trade_dir']
    assert trade_dir['refinement_kind'] == 'categorical'


@pytest.mark.parametrize('direction,outcome,minutes,expected,reason', [
    (1, 'target', 2, 20120, 'take_profit'), (-1, 'target', 2, 19880, 'take_profit'),
    (1, 'stop', 2, 20088, 'stop_loss'), (-1, 'stop', 2, 19912, 'stop_loss'),
    (1, 'flat', None, 20105, 'RS.LF'), (-1, 'flat', None, 19895, 'RS.SF'),
    (1, 'target_only', 2, 20120, 'take_profit'), (1, 'stop_only', 2, 20088, 'stop_loss'),
    (1, 'late', 3, 20120, 'take_profit'),
])
def test_execution_from_exact_fill_with_delayed_protection(tmp_path, direction, outcome, minutes, expected, reason):
    late = outcome == 'late'
    raw, start, end, _ = product_fixture(direction, 'target' if late else outcome.split('_')[0], late)
    store = DatasetStore(tmp_path / 'datasets.sqlite3')
    source = save(store, raw)
    params = replace(Parameters(), stop_frac=D(0)) if outcome == 'target_only' else (
        replace(Parameters(), tgt_frac=D(0)) if outcome == 'stop_only' else Parameters())
    dates = DateRange.parse(start, end)
    strategy = RelativeStrength(params)
    with read_selected_bars(store, source['id'], dates) as selected:
        trades = [t for t in execute(selected.bars, strategy, CONFIG) if type(t) is Trade]
    trade, = trades
    assert trade.entry_time_utc == stamp(1 + late)
    assert trade.entry_fill_price == 20000 + direction * 100
    assert trade.exit_time_utc == (stamp(minutes) if minutes else stamp(0) + timedelta(hours=6))
    assert trade.exit_fill_price == expected
    assert trade.entry_reason == ('RS.L' if direction == 1 else 'RS.S')
    assert trade.exit_reason == reason
    assert trade.net_pnl == (expected - trade.entry_fill_price) * direction * 20
    assert strategy.average_range == 20


def test_moments_include_decision_bar_and_compare_to_independent_weighted_sum(tmp_path):
    raw, start, end, _ = product_fixture()
    store = DatasetStore(tmp_path / 'datasets.sqlite3')
    source = save(store, raw)
    prepared = prepare_data(store, source['id'], DateRange.parse(start, end), tmp_path / 'bars')
    strategy = RelativeStrength(Parameters(trade_dir=-1))
    returns = []
    previous = None
    with prepared.selected() as selected:
        for bar in selected.bars:
            now = bar.timestamp_utc.astimezone(CT)
            if previous and now.strftime('%m/%d/%Y') not in DATES[5:7] and (8, 30) < (now.hour, now.minute) <= (15, 0):
                returns.append((10000 * log(float(bar.close / previous.close)),
                                10000 * log(float(bar.es_close / previous.es_close))))
            assert strategy.on_bar(bar, None) is None
            if bar.timestamp_utc == stamp(0):
                break
            previous = bar
    assert len(returns) == strategy.samples == 5 * 390 + 30
    alpha = 2 / 7801
    size = len(returns)
    weights = [(1 - alpha) ** (size - i - 1) * (alpha if i else 1) for i in range(size)]
    cross = sum(w * a * b for w, (a, b) in zip(weights, returns))
    es_sq = sum(w * b**2 for w, (a, b) in zip(weights, returns))
    beta = cross / es_sq
    variance = sum(w * (a - beta * b)**2 for w, (a, b) in zip(weights, returns))
    assert strategy.beta == pytest.approx(beta, rel=1e-9)
    assert strategy.residual_variance == pytest.approx(variance, rel=1e-9)
    assert strategy.anchor_nq == 20000 and strategy.anchor_es == 5000 and strategy.bars_since_anchor == 30
    assert 10000 * log(20100 / 20000) / sqrt(variance * 30) > float(Parameters().z_min)


def test_pairing_checks_source_timezones_alignment_and_old_schema(tmp_path):
    primary = tmp_path / 'nq.csv'
    es = tmp_path / 'es.csv'
    out = tmp_path / 'paired.csv'
    header = ','.join(COLUMNS)
    primary.write_text(f'{header}\n12/01/2025,08:30,100,100,100,100,0,0,0\n12/01/2025,08:31,101,101,101,101,0,0,0\n')
    es_rows = f'{header}\n12/01/2025,14:30,50,50,50,50,0,0,0\n12/01/2025,14:31,51,51,51,51,0,0,0\n'
    es.write_text(es_rows.replace('14:31', '14:32'))
    with pytest.raises(ValueError, match='Unmatched bar 2'):
        pair(primary, es, out, CT.key, 'UTC')
    assert not out.exists()
    es.write_text(es_rows)
    assert pair(primary, es, out, CT.key, 'UTC') == 2
    with pytest.raises(FileExistsError):
        pair(primary, es, out, CT.key, 'UTC')
    paired = out.read_bytes()
    assert validate_csv(paired, 'paired.csv', CT.key)['preview'][1]['ESClose'] == '51'
    with pytest.raises(InvalidDataset, match='ESClose must be positive'):
        validate_csv(paired.replace(b',51\n', b',0\n'), 'paired.csv', CT.key)
    definition = get_strategy('relative_strength')
    with pytest.raises(ValueError, match='requires paired'):
        definition.validate_source(Parameters(), dict(validate_csv(primary.read_bytes(), 'nq.csv'), symbol='NQ'))
