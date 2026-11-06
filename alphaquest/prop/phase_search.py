"""Phase-neutral calendar and saved-IS candidate admission."""
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
from .adapter import canonical, source_record
from .phase_profiles import prepare_phase_source

@dataclass(frozen=True)
class PhaseCalendar:
    start_dates: tuple[str, ...]
    coverage_end: str
    closures: tuple[str, ...] = ()
    timezone: str = 'America/Chicago'
    version: str = 'user-declared-weekdays-v1'

    def __post_init__(self):
        if not isinstance(self.start_dates, tuple) or not isinstance(self.closures, tuple):
            raise ValueError('Calendar dates must be immutable tuples.')
        for value in (*self.start_dates, self.coverage_end, *self.closures):
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError('Calendar dates must use canonical YYYY-MM-DD format.')
        if not 1 <= len(self.start_dates) <= 366 or len(set(self.start_dates)) != len(self.start_dates):
            raise ValueError('Use 1–366 distinct target start dates.')
        starts = [date.fromisoformat(s) for s in self.start_dates]
        end = date.fromisoformat(self.coverage_end)
        if not max(starts) <= end or (end - min(starts)).days > 40000:
            raise ValueError('Calendar coverage must contain the start cohort and span at most 40,000 days.')
        if self.timezone != 'America/Chicago':
            raise ValueError('Only the CME America/Chicago session-date convention is supported.')
        if not isinstance(self.version, str) or not self.version or len(set(self.closures)) != len(self.closures):
            raise ValueError('A calendar version and unique full-session closures are required.')
        for closure in self.closures:
            if not min(starts) <= date.fromisoformat(closure) <= end:
                raise ValueError('Closure is outside declared calendar coverage.')


def check_candidates(runs, search, assessment=None):
    """Reconcile every source before queueing; admit only comparable saved IS."""
    rows = []
    common = None
    for candidate in search.candidates:
        record = source_record(runs, candidate.source.source_backtest_id)
        metadata = record['run_metadata']
        research = metadata.get('research') or {}
        if assessment:
            selected = next((r for r in assessment['sources'] if r['source_id'] == record['id']
                and r['frozen_manifest']['configuration']['micros'] == candidate.micros), None)
            if selected is None:
                raise ValueError('Assessment source is outside the frozen family.')
            saved = selected['frozen_manifest']['source']['backtest']
            if (research.get('phase') != 'oos' or research.get('parent_run_id') != saved['id']
                    or metadata['strategy'] != saved['run_metadata']['strategy']
                    or metadata['dataset'] != saved['run_metadata']['dataset']
                    or record['execution_settings'] != saved['execution_settings']
                    or research['plan'] != saved['run_metadata']['research']['plan']):
                raise ValueError('OOS source must retain its frozen IS parent, strategy, split and execution costs.')
            expected = dict(selected['frozen_manifest']['configuration'])
            expected['source'] = dict(expected['source'], source_backtest_id=record['id'])
            expected['period'] = dict(first_session=research['plan']['oos_start'], last_session=research['plan']['oos_end'])
            if canonical(asdict(candidate)) != canonical(expected):
                raise ValueError('Assessment parameters, size, profile, costs, sampling and window are frozen.')
        elif research.get('phase') != 'is':
            raise ValueError('Phase selection requires a declared IS backtest/trial; OOS and undeclared sources reject.')
        snapshot, _, _ = prepare_phase_source(runs, candidate.source, candidate.profile,
            candidate.micros, candidate.simulation, candidate.period, candidate.costs)
        protocol = dict(dataset=metadata['dataset'], period=snapshot['profile_research_period'],
            execution=record['execution_settings'], costs=asdict(candidate.costs))
        # Research IDs/strategy IDs may differ; the actual split must not.
        protocol['research_windows'] = {k: research['plan'][k] for k in ('is_start', 'is_end', 'oos_start', 'oos_end')}
        if common is not None and canonical(protocol) != canonical(common):
            raise ValueError('Candidates require identical dataset, research windows, source costs and execution protocol.')
        common = protocol
        manifest = dict(configuration=asdict(candidate), strategy=metadata['strategy'],
                        source=snapshot)
        # Retain the full source for audit, but administrative automatic joint
        # reports must not influence phase candidate keys or tie presentation.
        numerical = deepcopy(manifest)
        numerical['source'].pop('manifest_sha256')
        numerical['source']['backtest']['run_metadata'].pop('automatic_prop_analysis', None)
        key = sha256(canonical(numerical).encode()).hexdigest()
        access = dict(status='unavailable', attempts=None)
        origins = []
        if hasattr(runs, 'connect'):
            with runs.connect() as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='optimization_trials'").fetchone():
                    origins = [dict(optimization_id=id, trial=trial) for id,trial in db.execute(
                        "SELECT optimization_id,trial FROM optimization_trials WHERE json_extract(payload,'$.run_id')=? ORDER BY optimization_id,trial",
                        (record['id'],)).fetchall()]
                exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='oos_attempts'").fetchone()
                if exists:
                    history = db.execute('SELECT id,parent_run_id,run_id,status,created_at FROM oos_attempts WHERE strategy_id=? AND source_sha256=? ORDER BY created_at,id',
                        (metadata['strategy']['id'], metadata['dataset']['sha256'])).fetchall()
                    access = dict(status='recorded', attempts=[dict(zip(('id','parent_run_id','run_id','status','created_at'), r)) for r in history],
                        interpretation='Access history only; no OOS prices, metrics or outcomes enter selection. No untouched-OOS claim.')
        rows.append(dict(candidate_id=key, manifest=manifest, status='compatible', prior_access=access, origin_trials=origins))
    keys = [r['candidate_id'] for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate candidate definitions; remove duplicates explicitly.')
    return sorted(rows, key=lambda r: r['candidate_id'])


def capture_inputs(runs, staged, search, calculations):
    """Seal source inputs once through the existing report directory."""
    import shutil
    from pathlib import Path
    from .adapter import digest
    from .phase_profiles import verify_phase_source
    captured = set()
    for candidate in search.candidates:
        id = candidate.source.source_backtest_id
        if id in captured:
            continue
        captured.add(id)
        folder = staged/'inputs'/id
        folder.mkdir(parents=True)
        for name in ('trades.csv', 'intratrade_risk.csv'):
            path = runs.root/id/name
            if path.is_file(): shutil.copyfile(path, folder/name)
    for row in calculations['candidates']:
        c = next(c for c in search.candidates if canonical(asdict(c)) == canonical(row['manifest']['configuration']))
        snapshot = row['manifest']['source']
        verify_phase_source(runs, c.source, snapshot)
        folder = staged/'inputs'/c.source.source_backtest_id
        if digest(folder/'trades.csv') != snapshot['trades_sha256']:
            raise ValueError('Captured source changed during publication.')
        if snapshot.get('native_risk') and digest(folder/'intratrade_risk.csv') != snapshot['native_risk']['sha256']:
            raise ValueError('Captured risk changed during publication.')
        export = snapshot['excursion_input']
        if export['path']:
            target = staged/('input-export-'+export['sha256']+Path(export['path']).suffix)
            if not target.exists(): shutil.copyfile(export['path'], target)
            if digest(target) != export['sha256']: raise ValueError('Captured export changed during publication.')
