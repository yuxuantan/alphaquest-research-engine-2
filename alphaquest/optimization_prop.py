"""Explicit account-specific refreshes; immutable trials and normal reports.

Links are an append-only index in the existing backtest catalogue. Calculations
and downloads live exclusively in AnalysisStore. GETs only read saved links.
"""
from collections import Counter
from datetime import datetime, timezone
import json
import logging
from pathlib import Path

from .optimization_cache import digest
from .prop.adapter import digest as file_digest
from .prop.native_analysis import prepare, model_version, kernel_identity

logger = logging.getLogger(__name__)
# Storage/UI changes do not invalidate an independently verified calculation.
# These files and the exact native kernel identify the numerical implementation.
CALCULATION_FILES = ('native_analysis.py', 'joint_sizing.py', 'lucid_engine.py', 'lucid_rules.py',
    'native_engine.py', 'native_backend.py', 'lucid_backend.py', 'source.py',
    'adapter.py', 'commissions.py', 'parallel.py')


def initialize(runs, analyses):
    with runs.connect() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS optimization_prop_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                optimization_id TEXT NOT NULL,
                trial INTEGER NOT NULL,
                analysis_id TEXT,
                payload TEXT NOT NULL,
                account TEXT NOT NULL DEFAULT 'lucid',
                FOREIGN KEY(optimization_id,trial) REFERENCES optimization_trials(optimization_id,trial) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS optimization_prop_links_trial
                ON optimization_prop_links(optimization_id,trial,id);
            CREATE INDEX IF NOT EXISTS optimization_prop_links_analysis
                ON optimization_prop_links(analysis_id);
        ''')
        if 'account' not in {row[1] for row in db.execute('PRAGMA table_info(optimization_prop_links)')}:
            db.execute("ALTER TABLE optimization_prop_links ADD COLUMN account TEXT NOT NULL DEFAULT 'lucid'")
        db.execute('CREATE INDEX IF NOT EXISTS optimization_prop_links_account ON optimization_prop_links(optimization_id,trial,account,id)')
    synchronize_pending(runs, analyses)


def revision(runs, job_id):
    with runs.connect() as db:
        return db.execute('SELECT COALESCE(MAX(id),0) FROM optimization_prop_links WHERE optimization_id=?', (job_id,)).fetchone()[0]


def append(runs, job_id, trial, payload, account='lucid'):
    with runs.connect() as db:
        db.execute('INSERT INTO optimization_prop_links(optimization_id,trial,analysis_id,payload,account) VALUES (?,?,?,?,?)',
                   (job_id, trial, payload.get('id'), json.dumps(payload, allow_nan=False), account))


def latest(runs, job_id, snapshot=None, account='lucid'):
    snapshot = revision(runs, job_id) if snapshot is None else snapshot
    with runs.connect() as db:
        rows = db.execute('''SELECT trial,payload FROM optimization_prop_links l WHERE optimization_id=? AND id=
            (SELECT MAX(id) FROM optimization_prop_links WHERE optimization_id=l.optimization_id AND trial=l.trial AND account=l.account AND id<=?)
            AND account=?''', (job_id, snapshot, account)).fetchall()
    return {trial: json.loads(payload) for trial, payload in rows}


def status(store, job, account='lucid'):
    metric, _, _ = account_fields(account)
    links = latest(store.runs, job['id'], account=account)
    with store.runs.connect() as db:
        trials = [json.loads(row[0]) for row in db.execute('SELECT payload FROM optimization_trials WHERE optimization_id=?', (job['id'],))]
    counts = Counter()
    for row in trials:
        link = links.get(row['trial'])
        value = link.get('historical_net') if link else row['metrics'].get(metric)
        counts['available' if value is not None else 'unavailable'] += 1
        if link:
            counts['refreshed'] += value is not None
            counts['pending'] += link['status'] in ('queued', 'running')
            counts['failed'] += link['status'] == 'error'
    return dict(total=len(trials), revision=revision(store.runs, job['id']),
        **{key: counts[key] for key in ('available', 'unavailable', 'refreshed', 'pending', 'failed')})


def read_verified(analyses, analysis_id):
    if analyses.fingerprint(analysis_id) is None:raise ValueError('Saved prop report failed its integrity check.')
    return json.loads((analyses.root / analysis_id / 'report.json').read_text())


def compatible(report, snapshot, settings):
    root = Path(__file__).parent / 'prop'
    return (report.get('model_version') == model_version(settings)
        and report.get('calculations', {}).get('model_version') == model_version(settings)
        and report.get('source') == snapshot and report.get('settings') == settings
        and report.get('runtime', {}).get('native_kernel') == kernel_identity(settings)
        and all(report.get('implementation_sha256', {}).get(name) == file_digest(root / name) for name in CALCULATION_FILES)
        and (report.get('runtime', {}).get('calculation_reused_from') is None
             or report.get('implementation_sha256', {}).get('calculation_cache.py') == file_digest(root / 'calculation_cache.py')))


def find_current(analyses, source_id, snapshot, settings):
    for record in analyses.list(source_id):
        if record['status'] != 'complete':continue
        try:
            report = json.loads((analyses.root / record['id'] / 'report.json').read_text())
            if compatible(report, snapshot, settings) and analyses.fingerprint(record['id']) is not None:
                return record, report
        except (OSError, ValueError, KeyError):continue
    return None


def complete_payload(analyses, payload):
    record = analyses.get(payload['id'])
    if record is None:return dict(payload, status='error', reason='The refreshed prop analysis was deleted.')
    if record['status'] in ('queued', 'running'):return None
    result = dict(payload, status=record['status'], reason=record.get('error'), historical_net=None)
    if record['status'] == 'complete':
        report = read_verified(analyses, record['id'])
        identity = payload['identity']
        if (digest(report['source']) != identity['source'] or digest(report['settings']) != identity['settings']
                or report['model_version'] != identity['model_version']
                or report.get('calculations', {}).get('model_version') != identity['model_version']
                or report['runtime']['native_kernel'] != identity['kernel']):
            raise ValueError('Refreshed prop report differs from its checked source, settings or model.')
        history = report['calculations'].get('history')
        result.update(historical_net=history['totals']['net'] if history else None,
                      reason=report['calculations'].get('unavailable'), report_sha256=file_digest(analyses.root / record['id'] / 'report.json'))
    return result


def synchronize(runs, analyses, analysis_id):
    """Publish saved analysis results into pending links; never calculate."""
    with analyses.lock:
        with runs.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='optimization_prop_links'").fetchone():return
            rows = db.execute('''SELECT optimization_id,trial,payload,account FROM optimization_prop_links l
                WHERE analysis_id=? AND id=(SELECT MAX(id) FROM optimization_prop_links
                WHERE optimization_id=l.optimization_id AND trial=l.trial AND account=l.account)''', (analysis_id,)).fetchall()
        for job_id, trial, raw, account in rows:
            payload = json.loads(raw)
            if payload['status'] not in ('queued', 'running'):continue
            try:result = complete_payload(analyses, payload)
            except (ValueError, OSError, KeyError) as exc:result = dict(payload, status='error', reason=str(exc), historical_net=None)
            if result is not None:append(runs, job_id, trial, result, account)


def synchronize_pending(runs, analyses):
    with runs.connect() as db:
        ids = [row[0] for row in db.execute('''SELECT DISTINCT analysis_id FROM optimization_prop_links l
            WHERE json_extract(payload,'$.status') IN ('queued','running') AND analysis_id IS NOT NULL
            AND id=(SELECT MAX(id) FROM optimization_prop_links WHERE optimization_id=l.optimization_id AND trial=l.trial AND account=l.account)''')]
    for analysis_id in ids:synchronize(runs, analyses, analysis_id)


def account_fields(account):
    if account=='apex':return 'historical_net','Apex','Apex EOD'
    if account=='lucid':return 'lucid_historical_net','Lucid','LucidFlex'
    raise ValueError('Unknown prop account; choose Apex or Lucid.')


def account_profiles(job):
    primary=job.get('default_prop_profile') or {}
    profiles={}
    if primary.get('settings',{}).get('ACCOUNT_TYPE')=='Apex EOD':profiles['apex']=primary
    for item in primary.get('companions',[]):
        if item['settings'].get('ACCOUNT_TYPE')=='LucidFlex':profiles['lucid']=item
    return profiles


def all_status(store, job):
    accounts={account:status(store,job,account) for account in account_profiles(job)}
    return dict(accounts=accounts,pending=sum(s['pending'] for s in accounts.values()),revision=revision(store.runs,job['id']))


def refresh_all(store, job_id):
    job=store.get(job_id)
    if job is None:raise LookupError('Backtest activity not found.')
    accounts={account:refresh(store,job_id,account) for account in account_profiles(job)}
    if not accounts:raise ValueError('This activity has no saved prop account settings.')
    return dict(all_status(store,store.get(job_id)),**{key:sum(s[key] for s in accounts.values()) for key in ('queued','reused','already_pending','blocked')})


def refresh(store, job_id, account='lucid'):
    metric,label,account_type=account_fields(account)
    synchronize_pending(store.runs, store.prop_analyses)
    analyses = store.prop_analyses
    counts = Counter()
    # Same lock order as source/activity deletion. Once queued, the normal
    # AnalysisStore job protects its source until publication is complete.
    with analyses.lock, store.runs.detail_lock:
        job = store.get(job_id)
        if job is None:raise LookupError('Backtest activity not found.')
        if job['status'] in ('queued', 'running', 'deleting'):
            raise ValueError(f'Wait for the backtest activity to finish before refreshing {label}.')
        profile = account_profiles(job).get(account)
        if not profile:raise ValueError(f'This activity has no saved {label} account settings.')
        links = latest(store.runs, job_id, account=account)
        with store.runs.connect() as db:
            trials = [json.loads(row[0]) for row in db.execute('SELECT payload FROM optimization_trials WHERE optimization_id=? ORDER BY trial', (job_id,))]
        for row in trials:
            previous = links.get(row['trial'])
            value = previous.get('historical_net') if previous else row['metrics'].get(metric)
            if value is not None:continue
            if previous and previous['status'] in ('queued', 'running'):
                counts['already_pending'] += 1
                continue
            original = (row.get('prop_analysis') or {}) if account=='apex' else (row.get('prop_companions') or [{}])[0]
            payload = dict(id=None, status='incompatible', historical_net=None, reason=None,
                source_id=row['run_id'], original_analysis_id=original.get('id'),
                model_version=model_version(profile['settings']),account=account,created_at=datetime.now(timezone.utc).isoformat())
            try:
                settings = profile['settings']
                trade_file = ''
                export_timezone='America/Chicago'
                record = analyses.get(original.get('id', ''))
                if record and record['status'] == 'complete':
                    old = read_verified(analyses, record['id'])
                    if old['source']['backtest']['id'] != row['run_id']:raise ValueError(f'Original {label} report belongs to a different backtest.')
                    settings = old['settings']
                    if settings.get('ACCOUNT_TYPE')!=account_type:raise ValueError('Original report has a different prop account type.')
                    trade_file = old['source']['excursion_input']['path'] or ''
                    export_timezone=old['source']['excursion_input']['export_timezone']
                snapshot, _, settings = prepare(store.runs, row['run_id'], trade_file, settings, export_timezone)
                analyses.check_oos(snapshot, settings, store.runs)
                payload.update(identity=dict(source=digest(snapshot), settings=digest(settings),
                    model_version=model_version(settings), kernel=kernel_identity(settings)), model_version=model_version(settings))
                found = find_current(analyses, row['run_id'], snapshot, settings)
                if found:
                    payload.update(id=found[0]['id'], status='queued')
                    result = complete_payload(analyses, payload)
                    append(store.runs, job_id, row['trial'], result, account)
                    counts['reused'] += 1
                else:
                    request = dict(source_backtest_id=row['run_id'], trade_file=trade_file,
                                   export_timezone=export_timezone, settings=settings)
                    # We hold AnalysisStore.lock across queueing and link capture;
                    # its completion hook takes the same lock before publishing.
                    record = analyses._submit(store.runs, request)
                    payload.update(id=record['id'], status=record['status'])
                    if record['status'] == 'complete':payload = complete_payload(analyses, dict(payload, status='queued'))
                    append(store.runs, job_id, row['trial'], payload, account)
                    counts['queued'] += record['status'] in ('queued', 'running')
                    counts['reused'] += record['status'] == 'complete'
            except (ValueError, OSError, KeyError) as exc:
                payload.update(status='incompatible', reason=str(exc))
                append(store.runs, job_id, row['trial'], payload, account)
                counts['blocked'] += 1
    return dict(status(store, job, account), **{key: counts[key] for key in ('queued', 'reused', 'already_pending', 'blocked')})
