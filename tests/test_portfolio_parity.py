"""Portfolio can reuse a reviewed code transition with both exact saved replays."""
from copy import deepcopy
import sqlite3

import pytest

from alphaquest.prop.portfolio_parity import REVIEWED_TRANSITION, record_parity, verified_parity


class Reports:
    def __init__(self, root):
        self.root = root
        self.records = {}

    def connect(self):
        return sqlite3.connect(self.root / 'runs.sqlite3')

    def get(self, identifier):
        return self.records.get(identifier)


def test_reviewed_parity_requires_both_windows_and_detects_changed_evidence(tmp_path, monkeypatch):
    from alphaquest.prop import portfolio_parity
    from types import SimpleNamespace
    old, current = REVIEWED_TRANSITION
    stamp = {'value': current}
    monkeypatch.setattr(portfolio_parity, 'get_strategy',
                        lambda key: SimpleNamespace(description=lambda: {'source_sha256': stamp['value']}))
    runs = Reports(tmp_path)
    source = dict(source_backtest_id='old-is', oos_report_id='old-oos')
    for role in ('is', 'oos'):
        for prefix, sha in [('old', old), ('replay', current)]:
            name = f'{prefix}-{role}'
            root = tmp_path / name
            root.mkdir()
            for filename in ('trades.csv', 'equity.csv'):
                (root / filename).write_text(f'synthetic,fixture,{role}\n')
            runs.records[name] = dict(summary={'total_net_pnl': '12'},
                execution_settings={'point_value': '20'},
                run_metadata=dict(dataset={'id': 'dataset', 'sha256': 'saved-dataset'}, selection={'row_count': 12},
                    strategy=dict(id='twin_continuation', source_sha256=sha, parameters={'test': 3}),
                    research=dict(plan={'is_start': '2024-01-01'}, phase=role,
                        parent_run_id=f'{prefix}-is' if role=='oos' else None)))
    assert verified_parity(runs, source) is None
    replay = runs.records.pop('replay-oos')
    with pytest.raises(ValueError, match='OOS parity reports are unavailable'):
        record_parity(runs, source, 'replay-is', 'replay-oos')
    runs.records['replay-oos'] = deepcopy(replay)
    runs.records['replay-oos']['run_metadata']['research']['parent_run_id'] = 'old-is'
    with pytest.raises(ValueError, match='respective IS parents'):
        record_parity(runs, source, 'replay-is', 'replay-oos')
    runs.records['replay-oos'] = replay
    saved = record_parity(runs, source, 'replay-is', 'replay-oos')
    assert saved['phases']['is']['replay_id'] == 'replay-is'
    assert saved['phases']['oos']['replay_id'] == 'replay-oos'
    assert verified_parity(runs, source) == saved
    stamp['value'] = 'future-hash'
    assert verified_parity(runs, source) is None
    stamp['value'] = current
    (tmp_path/'replay-oos'/'equity.csv').write_text('changed\n')
    assert verified_parity(runs, source) is None
