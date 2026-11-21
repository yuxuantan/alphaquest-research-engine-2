"""Record exact Portfolio replay parity for a reviewed instrumentation-only transition."""
import json

from ..artifact_reads import read_hash
from ..optimization_cache import digest
from ..strategies.registry import get_strategy
from .adapter import canonical

VERSION = 'portfolio-native-source-parity-v1'
# e764df9 -> d6c1676 adds the optional observe_entry hook to execution.py.
# The hook is unset in Portfolio. Other strategy fingerprint inputs are identical.
REVIEWED_TRANSITION = (
    '99ed195a33b55c1e89a84c46e37c083906e4f791e76fae4a7d14d83b32648235',
    '357177f864d80815ed154dcb865f07c7e1e184a7de37bfe91a06d793ef3cad11',
)


def replay_proof(runs, original_ids, replay_ids):
    if len(set((*original_ids, *replay_ids))) != 4:
        raise ValueError('Use four distinct original and replay reports.')
    phases = {}
    for phase, original_id, replay_id in zip(('is', 'oos'), original_ids, replay_ids, strict=True):
        original, replay = runs.get(original_id), runs.get(replay_id)
        if original is None or replay is None:
            raise ValueError(f'{phase.upper()} parity reports are unavailable.')
        before, after = original['run_metadata'], replay['run_metadata']
        previous, current = before['strategy'], after['strategy']
        current_sha = get_strategy(previous['id']).description()['source_sha256']
        transition = (previous['source_sha256'], current['source_sha256'])
        if transition != REVIEWED_TRANSITION or current_sha != transition[1]:
            raise ValueError('The strategy fingerprint transition has no reviewed Portfolio equivalence.')
        if dict(previous, source_sha256=current_sha) != current:
            raise ValueError(f'{phase.upper()} replay differs in strategy or session behavior.')
        for key in ('dataset', 'instrument', 'selection', 'execution_scenario', 'instrument_overrides'):
            if before.get(key) != after.get(key):
                raise ValueError(f'{phase.upper()} replay differs in {key.replace("_", " ")}.')
        for key in ('execution_settings', 'period_start_utc', 'period_end_utc', 'summary'):
            if original.get(key) != replay.get(key):
                raise ValueError(f'{phase.upper()} replay differs in {key.replace("_", " ")}.')
        old_research, new_research = before['research'], after['research']
        if (old_research['phase'] != phase or new_research['phase'] != phase
                or old_research['plan'] != new_research['plan']):
            raise ValueError(f'{phase.upper()} replay differs in its research split.')
        if phase == 'oos' and (
            old_research.get('parent_run_id') != original_ids[0]
            or new_research.get('parent_run_id') != replay_ids[0]
        ):
            raise ValueError('The OOS reports must retain their respective IS parents.')
        checks = {}
        for filename in ('trades.csv', 'equity.csv'):
            expected = read_hash(runs.root / original_id / filename)
            actual = read_hash(runs.root / replay_id / filename)
            if expected != actual:
                raise ValueError(f'{phase.upper()} replay differs in {filename}.')
            checks[filename] = actual
        phases[phase] = dict(original_id=original_id, replay_id=replay_id,
            original_manifest_sha256=digest(original), replay_manifest_sha256=digest(replay),
            matching_files=checks)
    return dict(version=VERSION, original_strategy_sha256=REVIEWED_TRANSITION[0],
        current_strategy_sha256=REVIEWED_TRANSITION[1], phases=phases)


def record_parity(runs, source, replay_is, replay_oos):
    """Link existing immutable reports without changing the qualified campaign."""
    original_ids = (source['source_backtest_id'], source['oos_report_id'])
    proof = replay_proof(runs, original_ids, (replay_is, replay_oos))
    with runs.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS portfolio_source_parity (
            is_id TEXT NOT NULL, oos_id TEXT NOT NULL, proof TEXT NOT NULL,
            PRIMARY KEY (is_id, oos_id, proof)
        )''')
        db.execute('INSERT OR IGNORE INTO portfolio_source_parity VALUES (?, ?, ?)',
            (*original_ids, canonical(proof)))
    return verified_parity(runs, source)


def verified_parity(runs, source):
    original_ids = (source['source_backtest_id'], source['oos_report_id'])
    with runs.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='portfolio_source_parity'").fetchone():
            return None
        rows = db.execute(
            'SELECT proof FROM portfolio_source_parity WHERE is_id=? AND oos_id=? ORDER BY rowid',
            original_ids).fetchall()
    for (value,) in rows:
        try:
            saved = json.loads(value)
            replay_ids = tuple(saved['phases'][p]['replay_id'] for p in ('is', 'oos'))
            actual = replay_proof(runs, original_ids, replay_ids)
            if saved == actual:
                return actual
        except (KeyError, TypeError, OSError, ValueError):
            continue
    return None
