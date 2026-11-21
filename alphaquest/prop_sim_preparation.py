"""Responsive Prop Sim admission on the existing worker/catalogue and Runtime.

Preparation is mutable parent-job metadata, never another financial result store.
Only verified, unchanged qualification evidence enters the disposable ReplayCache.
CPU-heavy reads run in the existing bounded process pool without recovery hooks.
"""
from concurrent.futures import Future, ProcessPoolExecutor, TimeoutError
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import multiprocessing as mp
from pathlib import Path
from stat import S_ISLNK
from tempfile import TemporaryDirectory
from threading import Lock, RLock
from types import SimpleNamespace
from uuid import UUID

from .prop.adapter import canonical
from .prop.parallel import CAPACITY

ACTIVE = ('queued', 'running')


def now():
    return datetime.now(timezone.utc).isoformat()


def read_context(directory):
    """Existing store readers, without constructors that recover or start jobs."""
    from .datasets import DatasetStore
    from .backtest_runs import RunStore
    from .campaign_workflow import CampaignWorkflowStore
    from .optimization import OptimizationStore
    from .prop.store import AnalysisStore
    from .research_campaigns import CampaignStore
    from .replay_cache import ReplayCache
    root = Path(directory).resolve()
    datasets = object.__new__(DatasetStore); datasets.path = root/'datasets.sqlite3'
    runs = object.__new__(RunStore); runs.path = root/'backtests.sqlite3'; runs.root = root/'backtest_runs'
    runs.replay_cache = ReplayCache(root/'.replay_cache')
    datasets.replay_cache = runs.replay_cache
    analyses = object.__new__(AnalysisStore); analyses.path = root/'prop_analyses/catalog.sqlite3'
    analyses.root = root/'prop_analyses'; analyses.lock = RLock()
    workflows = object.__new__(CampaignWorkflowStore); workflows.runs = runs
    optimizations = object.__new__(OptimizationStore); optimizations.runs = runs; optimizations.prop_analyses = analyses
    campaigns = CampaignStore(runs, analyses, optimizations, datasets)
    state = SimpleNamespace(store=datasets, runs=runs, prop_analyses=analyses,
        campaign_workflows=workflows, optimizations=optimizations, campaigns=campaigns,
        qualification_worker=True)
    return SimpleNamespace(app=SimpleNamespace(state=state))


def file_stamp(path):
    try:
        s = path.lstat()
        stamp=(str(path), s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if S_ISLNK(s.st_mode):
            target=path.stat()
            stamp+=(str(path.resolve()),target.st_dev,target.st_ino,target.st_size,target.st_mtime_ns,target.st_ctime_ns)
        return stamp
    except FileNotFoundError:
        return (str(path), None)


def evidence_identity(request, selection=None):
    """Cheap metadata/stat invalidation; content was hashed on the verified miss.

    ctime/inode catch replacement or edits even when size/mtime are restored.
    Unrelated backtest progress writes are absent from the cache identity; source
    workflow, job, trial and run-manifest rows remain explicit inputs.
    """
    from .optimization_cache import engine_identity
    state = request.app.state
    with state.prop_analyses.connect() as db:
        mc = db.execute('SELECT c.workflow_id,c.oos_job_id,a.id,a.status,a.request_hash,s.payload,a.created '
            'FROM campaign_sanity_jobs c JOIN analyses a ON a.id=c.analysis_id '
            'LEFT JOIN analysis_report_checks s ON s.id=a.id ORDER BY a.created,a.id').fetchall()
    latest = {(r[0],r[1]):r for r in mc}
    with state.runs.connect() as db:
        # Snapshot the selected campaign rows, not the SQLite file clock. Other
        # grids publish progress/trials in this same catalogue during verification.
        # Their writes do not alter the source being admitted.
        db.execute('BEGIN')
        index = db.execute('SELECT workflow_id,job_id FROM campaign_oos_state ORDER BY workflow_id').fetchall()
        scope = [UUID(selection['workflow_id']).hex] if selection else [r[0] for r in index]
        # Listing must notice new/current MC assessments, without watching bars
        # and progress in workflows that cannot yet contribute any configuration.
        workflows = scope if selection else [w for w,job in index if latest.get((w,job),[None]*4)[3]=='complete']
        ids = set(); catalogue = []
        for workflow in workflows:
            rows = db.execute("SELECT id,manifest FROM runs WHERE json_extract(manifest,'$.run_metadata.research.workflow_id')=? "
                'OR id IN (SELECT run_id FROM campaign_workflow_runs WHERE workflow_id=?) ORDER BY id', (workflow,workflow)).fetchall()
            ids.update(r[0] for r in rows)
            jobs = db.execute('SELECT job_id FROM campaign_broad_jobs WHERE workflow_id=? UNION '
                'SELECT job_id FROM campaign_narrow_jobs WHERE workflow_id=? UNION '
                'SELECT job_id FROM campaign_oos_jobs WHERE workflow_id=? ORDER BY job_id', (workflow,workflow,workflow)).fetchall()
            catalogue.append(dict(workflow_id=workflow,
                workflow=db.execute('SELECT id,identity,strategy_id,dataset_id,payload FROM campaign_workflows WHERE id=?',(workflow,)).fetchall(),
                membership=db.execute('SELECT run_id FROM campaign_workflow_runs WHERE workflow_id=? ORDER BY run_id',(workflow,)).fetchall(),
                broad=db.execute('SELECT payload FROM campaign_broad_state WHERE workflow_id=?',(workflow,)).fetchall(),
                narrow=db.execute('SELECT broad_trial,payload FROM campaign_narrow_state WHERE workflow_id=? ORDER BY broad_trial',(workflow,)).fetchall(),
                oos=db.execute('SELECT job_id FROM campaign_oos_state WHERE workflow_id=?',(workflow,)).fetchall(),
                runs=rows,jobs=[dict(id=job[0],
                    record=db.execute('SELECT payload FROM optimizations WHERE id=?',job).fetchall(),
                    trials=db.execute('SELECT trial,payload FROM optimization_trials WHERE optimization_id=? ORDER BY trial',job).fetchall()) for job in jobs]))
    files = [file_stamp(p) for p in (state.store.path, Path(str(state.store.path)+'-wal'))]
    for id in sorted(ids):
        directory = state.runs.root/id
        files.append(file_stamp(directory))
        files.extend(file_stamp(p) for p in sorted(directory.rglob('*')))
    for row in mc:
        if row[0] not in workflows: continue
        directory = state.prop_analyses.root/row[2]
        files.append(file_stamp(directory))
        files.extend(file_stamp(p) for p in sorted(directory.rglob('*')))
    return sha256(canonical(dict(engine=engine_identity(), workflows=workflows, catalogue=catalogue, files=files,
        index=[r for r in index if r[0] in scope],
        monte_carlo=[r for r in mc if r[0] in scope])).encode()).hexdigest()


def cached(request, operation, payload, calculate):
    """Checksum-verified, bounded, disposable metadata; never a source of truth."""
    selection = payload if operation == 'qualified' else None
    before = evidence_identity(request, selection)
    key = sha256(canonical(['portal-qualified-v2', operation, payload, before]).encode()).hexdigest()
    cache = request.app.state.runs.replay_cache
    with TemporaryDirectory(prefix='aq-qualification-') as temporary:
        path = Path(temporary)/'verified.json'
        restored = cache.restore(key, path)
        if restored == dict(kind='portal-qualified-v2', identity=before):
            try:
                value = json.loads(path.read_text())
                if value['identity'] == before and value['operation'] == operation:
                    return value['result'], before
            except (ValueError, KeyError, TypeError): pass
        result = calculate()
        if evidence_identity(request, selection) != before:
            raise ValueError('Campaign/source evidence changed during verification. Retry with the current source.')
        path.unlink(missing_ok=True)
        path.write_text(canonical(dict(identity=before, operation=operation, result=result)))
        cache.save(key, path, dict(kind='portal-qualified-v2', identity=before))
    return result, before


def qualified_cached(request, selection):
    from .prop_sim import _qualified_verified
    return cached(request, 'qualified', selection.model_dump(mode='json'),
        lambda: _qualified_verified(request, selection))[0]


def warm_saved_source_plans(request,checked):
    """Compile already-accessed campaign templates, never sizing OOS outcomes.

    The original OOS campaign trades were already used by admission/Monte Carlo.
    This only verifies causal metadata against those same immutable trades. It
    neither tests a prop size nor ranks/changes the frozen family or a verdict.
    """
    candidates=[c for phase in checked['phases'].values() for c in phase['request']['candidates']]
    if not any((c.get('sizing') or {}).get('execution_model') for c in candidates):return
    from .prop.source import prepare_source
    from .prop.saved_trade_simulation import causal_plans
    for id in (checked['source']['source_backtest_id'],checked['source']['oos_report_id']):
        snapshot,_=prepare_source(request.app.state.runs,id,'')
        causal_plans(request.app.state.runs,snapshot)


def execute(directory, operation, payload):
    """Picklable Runtime task; no app startup, recovery or financial simulation."""
    from .prop_sim import Configuration, candidates, _check
    request = read_context(directory)
    if operation == 'qualified':
        from .prop_sim import Selection
        return dict(result=qualified_cached(request,Selection.model_validate(payload)))
    if operation == 'candidates':
        result, token = cached(request, operation, payload, lambda: candidates(request))
        return dict(result=result, token=token)
    if operation == 'check':
        body = Configuration.model_validate(payload)
        before = evidence_identity(request)
        checked, definitions = _check(request, body)
        warm_saved_source_plans(request,checked)
        if evidence_identity(request) != before:
            raise ValueError('Source evidence changed during preparation. Run again with unchanged inputs.')
        return dict(checked=checked, definitions={k:v.model_dump(mode='json') for k,v in definitions.items()}, token=before)
    raise ValueError('Unknown Prop Sim preparation task.')


class PreparationCancelled(Exception): pass


class PropSimPreparation:
    def __init__(self, app):
        self.app = app; self.request = SimpleNamespace(app=app)
        self.analyses = app.state.prop_analyses; self.pending = set(); self.closed = False
        self.inflight = {}; self.inflight_lock = Lock()
        self.candidates_task = None

    async def candidates_async(self):
        # Waiting browsers share one asynchronous waiter, rather than occupying
        # all HTTP thread-pool slots behind the same verification process.
        import asyncio
        from starlette.concurrency import run_in_threadpool
        if self.candidates_task is None or self.candidates_task.done():
            self.candidates_task=asyncio.create_task(run_in_threadpool(self.candidates))
        return await asyncio.shield(self.candidates_task)

    def execute(self, operation, payload, checkpoint=lambda:None):
        return self._execute(operation,payload,checkpoint)

    def qualified(self,selection):
        return self.execute('qualified',selection.model_dump(mode='json'))['result']

    def _execute(self, operation, payload, checkpoint=lambda:None):
        """Reuse the Runtime pool and CPU reservations, including one-worker mode."""
        runtime = self.analyses.runtime
        with runtime.parallel_slots(1):
            with runtime.pool_lock:
                if runtime.pool is None:
                    runtime.pool = ProcessPoolExecutor(max_workers=CAPACITY, mp_context=mp.get_context('spawn'))
                future = runtime.pool.submit(execute, str(self.app.state.runs.path.parent), operation, payload)
            stopped = False
            while True:
                try: result = future.result(timeout=.25); break
                except TimeoutError:
                    try: checkpoint()
                    except PreparationCancelled:
                        stopped = True
                        if future.cancel(): raise
            # Drain active work before returning the shared CPU reservation.
            if stopped: raise PreparationCancelled()
            checkpoint()
            return result

    def candidates(self):
        # Concurrent navigations share one in-flight read. No numerical work is
        # performed by polling; the child reuses verified unchanged cache entries.
        with self.inflight_lock:
            future = self.inflight.get('candidates'); owner = future is None
            if owner: future = self.inflight['candidates'] = Future()
        if not owner: return deepcopy(future.result())
        try:
            value = self.execute('candidates', {})['result']; future.set_result(value)
            return deepcopy(value)
        except BaseException as exc:
            future.set_exception(exc); raise
        finally:
            with self.inflight_lock: self.inflight.pop('candidates', None)

    def check(self, body):
        from .research_campaigns import CampaignRequest
        value = self.execute('check', body.model_dump(mode='json'))
        return value['checked'], {k:CampaignRequest.model_validate(v) for k,v in value['definitions'].items()}

    def _read(self, id):
        with self.analyses.connect() as db:
            row = db.execute('SELECT payload FROM workflow_prop_simulations WHERE id=?', (id,)).fetchone()
        return json.loads(row[0]) if row else None

    def _write(self, saved):
        with self.analyses.connect() as db:
            db.execute('UPDATE workflow_prop_simulations SET payload=? WHERE id=?', (json.dumps(saved), saved['id']))

    def queue(self, body):
        from .prop_sim import Configuration, public
        id = body.request_id.hex
        existing=self._read(id)
        if existing and existing.get('preparation',{}).get('status')=='complete':
            if Configuration.model_validate(existing['configuration']).model_dump(mode='json')!=body.model_dump(mode='json'):
                raise ValueError('This request ID already belongs to different settings.')
            jobs=[self.app.state.campaigns.progress(cid) for cid in existing['campaign_ids'].values()]
            if jobs and all(job['status'] in (*ACTIVE,'complete') for job in jobs) and not existing.get('automation',{}).get('stop_requested'):
                # Verification waits outside the catalogue lock; completed reports
                # retain their normal sealed-file/source guards.
                self.qualified(body.selections[0])
                for job in jobs:
                    if job['status']=='complete' and (not self.analyses.fingerprint(job['analysis_id']) or not self.analyses.native_children_unchanged(self.app.state.runs,job['analysis_id'])):
                        raise ValueError('Saved phase evidence changed; preserve this simulation and create a new one.')
                return public(self.request,id)
        with self.analyses.lock:
            with self.analyses.connect() as db:
                if db.execute('SELECT 1 FROM workflow_prop_sim_deletions WHERE id=?', (id,)).fetchone():
                    raise ValueError('This simulation was deleted. Use a new request ID.')
            saved = self._read(id)
            if saved:
                if Configuration.model_validate(saved['configuration']).model_dump(mode='json') != body.model_dump(mode='json'):
                    raise ValueError('This request ID already belongs to different settings.')
                if saved.get('preparation', {}).get('status') in ACTIVE:
                    self.schedule(id); return public(self.request, id)
            else:
                with self.app.state.runs.connect() as db:
                    row = db.execute('SELECT strategy_id,payload FROM campaign_workflows WHERE id=?', (body.selections[0].workflow_id.hex,)).fetchone()
                if not row: raise ValueError('Campaign workflow is unavailable.')
                declaration = json.loads(row[1])['declaration']
                with self.analyses.connect() as db:
                    source = db.execute('SELECT source_id FROM analyses WHERE id=?', (body.selections[0].monte_carlo_id.hex,)).fetchone()
                saved = dict(id=id, created_at_utc=now(), configuration=body.model_dump(mode='json'),
                    qualification=dict(source_backtest_id=source[0] if source else None, strategy_id=row[0], dataset=declaration['dataset']),
                    campaign_ids={}, disclosure='Qualification and source preparation are pending; no phase has started.')
            saved['preparation'] = dict(status='queued', progress='Queued source qualification and preparation',
                stop_requested=False, started_at_utc=None, finished_at_utc=None, error=None)
            with self.analyses.connect() as db:
                db.execute('INSERT INTO workflow_prop_simulations VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                    (id, saved['created_at_utc'], json.dumps(saved)))
            self.schedule(id)
        return public(self.request, id)

    def schedule(self, id):
        with self.analyses.lock:
            if self.closed or id in self.pending: return
            self.pending.add(id)
            self.analyses.worker.submit(self._prepare, id)

    def recover(self):
        with self.analyses.connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM workflow_prop_simulations WHERE json_extract(payload,'$.preparation.status') IN ('queued','running')")]
        for id in ids: self.schedule(id)

    def stop(self, id):
        with self.analyses.lock:
            saved = self._read(id)
            if not saved or saved.get('preparation', {}).get('status') not in ACTIVE: return False
            p = saved['preparation']; p['stop_requested'] = True; p['stop_requested_at_utc']=now();p['progress'] = 'Stopping source preparation…'
            if p['status'] == 'queued': p.update(status='cancelled', finished_at_utc=now())
            self._write(saved)
            return True

    def _prepare(self, id):
        from .prop_sim import Configuration
        from .prop_sim_automation import initial_state
        from .research_campaigns import CampaignRequest
        def checkpoint():
            saved = self._read(id)
            if not saved or saved['preparation']['stop_requested']: raise PreparationCancelled()
        try:
            with self.analyses.lock:
                saved = self._read(id)
                if not saved or saved['preparation']['status'] not in ACTIVE: return
                checkpoint(); saved['preparation'].update(status='running', started_at_utc=now(),
                    progress='Verifying campaign qualification and preparing phase sources'); self._write(saved)
            value = self.execute('check', saved['configuration'], checkpoint)
            body = Configuration.model_validate(saved['configuration'])
            def guard():
                checkpoint()
                if evidence_identity(self.request) != value['token']:
                    raise ValueError('Campaign/source evidence changed before queueing. Start again with the current source.')
            definitions = {p:CampaignRequest.model_validate(d) for p,d in value['definitions'].items()}
            # Only publication/reservation is locked; all verification already
            # ran in a separate bounded process and remains guarded at commit.
            with self.analyses.lock:
                guard(); saved = self._read(id)
                for phase, definition in definitions.items():
                    self.app.state.campaigns.create(definition, checked_manifest=value['checked']['phases'][phase], guard=guard)
                    saved['campaign_ids'][phase] = definition.campaign_id
                    with self.analyses.connect() as db:
                        db.execute('INSERT OR IGNORE INTO workflow_prop_sim_phases VALUES (?,?,?)',(id,phase,definition.campaign_id))
                    self._write(saved)
                saved.update(qualification=value['checked']['source'], disclosure=value['checked']['disclosure'])
                if body.automatic and not saved.get('automation'): saved['automation'] = initial_state()
                self._write(saved)
                for phase, cid in saved['campaign_ids'].items():
                    self.app.state.campaigns.run(cid, prepared_checks=value['checked']['phases'][phase]['source_checks'], guard=guard)
                saved = self._read(id); saved['preparation'].update(status='complete', progress='Sources verified; phase searches queued', finished_at_utc=now()); self._write(saved)
            if body.automatic: self.app.state.prop_sim_automation.resume(id)
        except Exception as exc:
            with self.analyses.lock:
                saved = self._read(id)
                if saved:
                    for cid in saved['campaign_ids'].values():
                        job=self.app.state.campaigns.get(cid).get('analysis')
                        if job and job['status'] in ACTIVE:self.analyses.cancel_phase(job['id'])
                    saved['preparation'].update(status='cancelled' if isinstance(exc, PreparationCancelled) else 'error',
                        error=None if isinstance(exc, PreparationCancelled) else f'{type(exc).__name__}: {exc}',
                        progress='Preparation cancelled' if isinstance(exc, PreparationCancelled) else 'Source preparation failed', finished_at_utc=now())
                    self._write(saved)
        finally:
            with self.analyses.lock: self.pending.discard(id)

    def close(self):
        self.closed = True
