"""One durable job/report catalogue. Completed reports publish by atomic rename."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import RLock
from uuid import UUID, uuid4
import zipfile
from .adapter import canonical
from .native_analysis import run_analysis
from .parallel import Runtime


def seal_report(staged, result, id, created):
    """Build the normal durable report/downloads, without catalogue access."""
    from .adapter import digest
    result.update(id=id,created_at_utc=created,status='complete')
    files={}
    for p in staged.rglob('*'):
        if p.is_symlink():raise ValueError('Analysis output contains a symbolic link.')
        if p.is_file():files[str(p.relative_to(staged))]=dict(bytes=p.stat().st_size,sha256=digest(p))
    if sum(v['bytes'] for v in files.values())>128*1024*1024:
        raise ValueError('Analysis output exceeds 128 MiB; no completed result was published.')
    result['files']=files
    (staged/'report.json').write_text(canonical(result),encoding='utf-8')
    with zipfile.ZipFile(staged/'analysis.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for p in staged.rglob('*'):
            if p.is_file() and p.name!='analysis.zip':archive.write(p,str(p.relative_to(staged)))


def request_key(snapshot, settings):
    from ..optimization_cache import engine_identity
    from .native_analysis import model_version
    return sha256(canonical(dict(source=snapshot,settings=settings,model_version=model_version(settings),engine_identity=engine_identity())).encode()).hexdigest()


def sealed_checks(directory):
    from .adapter import digest
    return {name:digest(directory/name) for name in ('report.json','analysis.zip')}


class AnalysisStore:
    def __init__(self,directory,*,recover_interrupted=True):
        self.root=Path(directory)/'prop_analyses';self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'catalog.sqlite3';self.lock=RLock()
        self.worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix='prop-analysis')
        self.runtime=Runtime()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, source_id TEXT NOT NULL, created TEXT NOT NULL, status TEXT NOT NULL, progress TEXT NOT NULL, error TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS analysis_report_checks (id TEXT PRIMARY KEY REFERENCES analyses(id), payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS analysis_sources (analysis_id TEXT NOT NULL, source_id TEXT NOT NULL, PRIMARY KEY(analysis_id,source_id))')
            db.execute('CREATE INDEX IF NOT EXISTS analysis_sources_by_source ON analysis_sources(source_id)')
            db.execute('INSERT OR IGNORE INTO analysis_sources SELECT id,source_id FROM analyses')
            db.execute('CREATE TABLE IF NOT EXISTS calculation_reuse (key TEXT PRIMARY KEY,engine TEXT NOT NULL,id TEXT NOT NULL,sha256 TEXT NOT NULL)')
            from ..research_campaigns import initialize
            initialize(db)
            if recover_interrupted:
                db.execute("UPDATE analyses SET status='error',error='Application stopped before publication; run again.',progress='Interrupted' WHERE status IN ('queued','running')")
                db.execute("UPDATE campaign_assessments SET payload=json_set(payload,'$.status','error',"
                           "'$.error','Application stopped during OOS launch. Inspect retained ordinary OOS attempts; launch a new manual assessment.') "
                           "WHERE json_extract(payload,'$.status')='launching'")

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=30)
        try:
            with db:yield db
        finally:db.close()

    def close(self):
        self.worker.shutdown(wait=True)
        self.runtime.close()

    def get(self,id):
        with self.connect() as db:
            db.row_factory=sqlite3.Row;row=db.execute('SELECT * FROM analyses WHERE id=?',(id,)).fetchone()
        return dict(row) if row else None

    def list(self,source):
        with self.connect() as db:
            db.row_factory=sqlite3.Row;rows=db.execute('SELECT a.* FROM analyses a WHERE a.source_id=? OR EXISTS (SELECT 1 FROM analysis_sources s WHERE s.analysis_id=a.id AND s.source_id=?) ORDER BY created DESC LIMIT 100',(source,source)).fetchall()
        return [dict(row) for row in rows]

    def active_sources(self):
        with self.connect() as db:
            return {r[0] for r in db.execute("SELECT source_id FROM analyses WHERE status IN ('queued','running') UNION SELECT s.source_id FROM analysis_sources s JOIN analyses a ON a.id=s.analysis_id WHERE a.status IN ('queued','running') UNION SELECT source_id FROM campaign_sources")}

    def delete(self, id):
        """Delete one inactive analysis; roll back file staging on SQL failure."""
        import shutil
        id=UUID(id).hex
        destination=self.root/id;staged=self.root/('.deleted-'+id);moved=False
        with self.lock:
            try:
                with self.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    record=db.execute('SELECT status FROM analyses WHERE id=?',(id,)).fetchone()
                    if db.execute('SELECT 1 FROM campaign_analyses WHERE analysis_id=?', (id,)).fetchone():
                        raise ValueError('This report is referenced by an immutable research campaign and cannot be deleted.')
                    if record and record[0] in ('queued','running'):
                        raise ValueError('This prop analysis is queued or running. Wait for it to finish before deleting.')
                    if destination.is_symlink() or staged.is_symlink():
                        raise OSError('Refusing to delete a symbolic-link prop report directory.')
                    if not record and not staged.exists():return False
                    if record:
                        if staged.exists():
                            if destination.exists():raise OSError('Conflicting staged deletion; no report files were removed.')
                            staged.rename(destination)
                        if destination.exists():destination.rename(staged);moved=True
                    db.execute('DELETE FROM calculation_reuse WHERE id=?',(id,))
                    db.execute('DELETE FROM analysis_report_checks WHERE id=?',(id,))
                    db.execute('DELETE FROM analysis_sources WHERE analysis_id=?',(id,))
                    db.execute('DELETE FROM analyses WHERE id=?',(id,))
            except BaseException:
                if moved:staged.rename(destination)
                raise
            if staged.exists():
                try:shutil.rmtree(staged)
                except OSError as exc:
                    raise OSError(f'Prop report removed from the catalogue, but file cleanup failed. Retry Delete for {id}.') from exc
        return True

    def submit(self,runs,request):
        # Deletion takes this same lock through the pending-job check and removal.
        with self.lock:return self._submit(runs,request)

    def submit_evaluation(self, runs, search):
        return self.submit_phase(runs, search)

    def submit_native(self, datasets, runs, request):
        """A native strategy rerun uses this catalogue and its ordinary worker."""
        from .native_replay import check_replay
        from ..optimization_cache import digest
        with self.lock:
            checks = check_replay(datasets, runs, request)
            key = digest(dict(request=request.model_dump(), source_check=checks))
            with self.connect() as db:
                row = db.execute("SELECT id,status FROM analyses WHERE request_hash=? AND status IN ('queued','running','complete') ORDER BY created DESC LIMIT 1", (key,)).fetchone()
                if row:
                    valid = row[1] != 'complete' or self.fingerprint(row[0]) is not None
                    if valid and row[1] == 'complete':
                        from ..optimization_cache import artifacts
                        report = json.loads((self.root/row[0]/'report.json').read_text())
                        child = runs.get(report['native_backtest_id'])
                        valid = child is not None and artifacts(runs.root, child) == report['native_backtest_artifacts']
                    if valid:
                        return self.get(row[0])
                id = uuid4().hex
                db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',
                    (id, key, request.source_backtest_id, datetime.now(timezone.utc).isoformat(), 'queued', 'Queued native '+request.phase+' replay', None))
                db.execute('INSERT INTO analysis_sources VALUES (?,?)', (id, request.source_backtest_id))
            self.worker.submit(self._run_native, datasets, runs, id, request, checks)
            return self.get(id)

    def _run_native(self, datasets, runs, id, request, checks):
        from .native_replay import run_replay
        from ..optimization_cache import artifacts
        try:
            self._update(id, 'running', 'Checking native source and account-control contract')
            with TemporaryDirectory(prefix='.pending-', dir=self.root) as temp:
                staged = Path(temp)/'report'; staged.mkdir()
                result = run_replay(self, datasets, runs, id, request, checks, staged)
                result['native_backtest_artifacts'] = artifacts(runs.root, result['native_backtest'])
                seal_report(staged, result, id, self.get(id)['created'])
                staged.rename(self.root/id)
            with self.connect() as db:
                db.execute('INSERT INTO analysis_report_checks VALUES (?,?)', (id, canonical(sealed_checks(self.root/id))))
                db.execute("UPDATE analyses SET status='complete',progress='Saved native phase replay ready' WHERE id=?", (id,))
        except Exception as exc:
            self._update(id, 'error', 'Native phase replay failed', f'{type(exc).__name__}: {exc}')

    def submit_funded(self, runs, search):
        return self.submit_phase(runs, search)

    def _reserve_phase(self, runs, search, *, campaign_checks=None, assessment=None,
                       training_context=None, inline=False):
        """Shared checked reservation; callers hold the catalogue mutation lock."""
        from .phase_dispatch import module_for_mode
        from .phase_search import check_candidates, validate_phase_work
        if assessment is not None and training_context is not None:
            raise ValueError('A phase source cannot be both nested training and manual assessment.')
        module = module_for_mode(search.mode)
        phase = 'Funded' if search.mode == 'funded_optimization' else 'Evaluation'
        validate_phase_work(search, len(training_context['session_inventory']) if training_context else None)
        if assessment or training_context:
            checks = check_candidates(runs, search, assessment, training_context=training_context)
        else:
            checks = module.check_search(runs, search)
        if campaign_checks is not None:
            if [c['candidate_id'] for c in checks] != [c['candidate_id'] for c in campaign_checks]:
                raise ValueError('Campaign source identity changed before queueing.')
            checks = campaign_checks
        key = module.search_key(search, checks)
        if assessment:
            key = sha256(canonical(dict(search=key, assessment=assessment)).encode()).hexdigest()
        if training_context:
            key = sha256(canonical(dict(search=key, training_context=training_context)).encode()).hexdigest()
        with self.connect() as db:
            row = db.execute("SELECT id,status FROM analyses WHERE request_hash=? AND status IN ('queued','running','complete') ORDER BY created DESC LIMIT 1", (key,)).fetchone()
            if row:
                try: valid = row[1] != 'complete' or self.fingerprint(row[0]) is not None
                except (OSError, ValueError, KeyError): valid = False
                if valid:
                    if inline and row[1] != 'complete':
                        raise ValueError('This internal phase calculation is already active; it cannot be queued behind its parent.')
                    if training_context:
                        report = json.loads((self.root/row[0]/'report.json').read_text())
                        if report.get('training_context') != training_context:
                            raise ValueError('Saved phase report training context differs from its immutable request.')
                        db.execute('INSERT OR IGNORE INTO campaign_analyses VALUES (?,?)', (training_context['campaign_id'], row[0]))
                    return self.get(row[0]), checks, False
            id = uuid4().hex
            db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',
                (id, key, search.source_backtest_id, datetime.now(timezone.utc).isoformat(), 'queued', 'Queued '+phase+' search', None))
            db.executemany('INSERT INTO analysis_sources VALUES (?,?)',
                [(id, source) for source in sorted({c.source.source_backtest_id for c in search.candidates})])
            if training_context:
                db.execute('INSERT INTO campaign_analyses VALUES (?,?)', (training_context['campaign_id'], id))
        return self.get(id), checks, True

    def submit_phase(self, runs, search, *, campaign_checks=None, assessment=None):
        """Public phase dispatch retains the existing worker and request meaning."""
        with self.lock:
            record, checks, fresh = self._reserve_phase(runs, search, campaign_checks=campaign_checks, assessment=assessment)
            if fresh:
                self.worker.submit(self._run_phase, runs, record['id'], search, checks, assessment)
            return record

    def run_phase_inline(self, runs, search, *, training_context, checkpoint=lambda:None,
                         progress=lambda message:None):
        """Internal nested child: normal durable report, no same-worker wait."""
        if not training_context:
            raise ValueError('Inline nested phase execution requires a server-derived training context.')
        checkpoint()
        with self.lock:
            record, checks, fresh = self._reserve_phase(runs, search, training_context=training_context, inline=True)
        if fresh:
            self._run_phase(runs, record['id'], search, checks, training_context=training_context,
                            checkpoint=checkpoint, progress=progress, raise_errors=True)
        checkpoint()
        return self.get(record['id'])

    def _run_phase(self, runs, id, search, checks, assessment=None, *, training_context=None,
                   checkpoint=lambda:None, progress=lambda message:None, raise_errors=False):
        from .phase_dispatch import module_for_mode
        module = module_for_mode(search.mode)
        optimize = module.optimize_funded if search.mode == 'funded_optimization' else module.optimize_evaluation
        phase = 'Funded' if search.mode == 'funded_optimization' else 'Evaluation'
        def update(message):
            checkpoint()
            self._update(id, 'running', message)
            progress(message)
        try:
            update('Running independent '+phase+' search')
            with TemporaryDirectory(prefix='.pending-', dir=self.root) as temp:
                staged = Path(temp)/'report'; staged.mkdir()
                with self.runtime.activate():
                    options = dict(assessment=True) if assessment else {}
                    if training_context is not None:
                        options['training_context'] = training_context
                    calculations = optimize(runs, search, checks, update, **options)
                if assessment:
                    calculations['assessment'] = assessment
                result = module.write_report(runs, staged, search, checks, calculations)
                if assessment:
                    result['assessment'] = assessment
                    result['settings']['ANALYSIS_MODE'] = search.mode.replace('_optimization', '_assessment')
                    (staged/'frozen_package.json').write_text(canonical(assessment['frozen_package']))
                if training_context is not None:
                    from .phase_search import check_candidates
                    current = check_candidates(runs, search, training_context=training_context)
                    if [c['candidate_id'] for c in current] != [c['candidate_id'] for c in checks]:
                        raise ValueError('Nested training source changed during phase calculation.')
                    result['training_context'] = training_context
                    (staged/'training_context.json').write_text(canonical(training_context))
                checkpoint()
                seal_report(staged, result, id, self.get(id)['created'])
                staged.rename(self.root/id)
            with self.connect() as db:
                db.execute('INSERT INTO analysis_report_checks VALUES (?,?)', (id, canonical(sealed_checks(self.root/id))))
                db.execute("UPDATE analyses SET status='complete',progress=? WHERE id=?", ('Saved '+phase+' search ready', id))
        except Exception as exc:
            self._update(id, 'error', phase+' search failed', f'{type(exc).__name__}: {exc}')
            if raise_errors:
                raise

    def _submit(self,runs,request):
        # Source fingerprint is checked by preparation, and included in the key.
        from .phase_lifecycle import prepare_request, source_snapshots, dated
        snapshot,_,settings=prepare_request(runs,request)
        existing=None
        for source in source_snapshots(snapshot):
            saved=self.check_oos(source,settings,runs)
            if not dated(request):existing=saved
        if existing:return existing
        request={**request,'trade_file':snapshot['excursion_input']['path'] or ''}
        key=request_key(snapshot,settings)
        with self.connect() as db:
            row=db.execute("SELECT id,status FROM analyses WHERE request_hash=? AND status IN ('queued','running','complete') ORDER BY created DESC LIMIT 1",(key,)).fetchone()
            if row:
                try:valid=row[1]!='complete' or self.fingerprint(row[0]) is not None
                except (OSError,ValueError,KeyError):valid=False
                if valid:return self.get(row[0])
            id=uuid4().hex
            db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(id,key,request['source_backtest_id'],datetime.now(timezone.utc).isoformat(),'queued','Queued',None))
            db.executemany('INSERT INTO analysis_sources VALUES (?,?)',[(id,source) for source in {s['backtest']['id'] for s in source_snapshots(snapshot)}])
        self.worker.submit(self._run,runs,id,request,snapshot)
        return self.get(id)

    def check_oos(self,snapshot,settings,runs):
        """Keep legacy sources within IS; saved manually executed OOS is usable."""
        record=snapshot['backtest']
        research=record['run_metadata'].get('research') or {}
        if research.get('phase')=='is':return None
        if research.get('phase')!='oos':
            # A pre-policy full-history report must not become a way to tune
            # prop assumptions on a subsequently declared holdout indefinitely.
            with runs.connect() as db:
                exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_plans'").fetchone()
                row=db.execute('SELECT payload FROM research_plans WHERE strategy_id=? AND source_sha256=?',
                    (record['run_metadata']['strategy']['id'],record['run_metadata']['dataset']['sha256'])).fetchone() if exists else None
            if not row:return None
            plan=json.loads(row[0])
            from zoneinfo import ZoneInfo
            zone=ZoneInfo(plan['source_timezone'])
            start=datetime.fromisoformat(record['period_start_utc'].replace('Z','+00:00')).astimezone(zone).date().isoformat()
            end=datetime.fromisoformat(record['period_end_utc'].replace('Z','+00:00')).astimezone(zone).date().isoformat()
            if plan['is_start']<=start<=end<=plan['is_end']:return None
            with self.connect() as db:
                cached=db.execute("SELECT id FROM analyses WHERE source_id=? AND request_hash=? AND status='complete' ORDER BY created DESC LIMIT 1",(record['id'],request_key(snapshot,settings))).fetchone()
            if cached and self.fingerprint(cached[0]) is not None:return self.get(cached[0])
            from ..research import ResearchConflict
            raise ResearchConflict('This legacy report includes data outside the saved IS period. Run a declared IS backtest, then manually select its OOS test; existing saved reports remain readable.')
        automatic=record['run_metadata'].get('automatic_prop_analysis',{})
        saved=self.get(automatic.get('id',''))
        if (saved and saved['source_id']==record['id'] and saved['status']=='complete'
                and saved['request_hash']==request_key(snapshot,settings) and self.fingerprint(saved['id']) is not None):
            return saved
        return None

    def _update(self,id,status,progress,error=None):
        with self.connect() as db:db.execute('UPDATE analyses SET status=?,progress=?,error=? WHERE id=?',(status,progress,error,id))

    def publish_prepared(self, prepared, directory):
        """Publish a worker's standard report through this single catalogue."""
        id=prepared['id'];destination=self.root/id;published=False
        try:
            with self.connect() as db:
                db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(
                    id,prepared['request_hash'],prepared['source_id'],prepared['created_at_utc'],
                    prepared['status'],'Saved report ready' if prepared['status']=='complete' else 'Automatic prop analysis unavailable',
                    prepared.get('reason') if prepared['status']!='complete' else None))
                db.execute('INSERT INTO analysis_sources VALUES (?,?)',(id,prepared['source_id']))
                if prepared['status']=='complete':
                    report=json.loads((Path(directory)/'report.json').read_text())
                    history=report['calculations'].get('history')
                    actual_net=history['totals']['net'] if history else None
                    if (report['id']!=id or report['source']['backtest']['id']!=prepared['source_id']
                            or actual_net!=prepared['historical_net'] or request_key(report['source'],report['settings'])!=prepared['request_hash']):
                        raise ValueError('Prepared prop report differs from its trial metadata.')
                    db.execute('INSERT INTO analysis_report_checks VALUES (?,?)',(id,canonical(sealed_checks(Path(directory)))))
                    Path(directory).rename(destination);published=True
        except BaseException:
            if published:
                import shutil
                shutil.rmtree(destination)
            raise
        if prepared['status']=='complete':self.index_calculations(id)
        return self.get(id)

    def index_calculations(self,id):
        try:self._index_calculations(id)
        except (OSError,ValueError,KeyError,sqlite3.Error):
            import logging
            logging.getLogger(__name__).warning('Could not index optional prop calculation reuse',exc_info=True)

    def _index_calculations(self,id):
        from ..optimization_cache import engine_identity
        directory=self.root/id
        report=json.loads((directory/'report.json').read_bytes())
        key=report.get('runtime',{}).get('calculation_key')
        if not key:return
        sha=report['files']['calculations.json']['sha256']
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO calculation_reuse VALUES (?,?,?,?)',(key,engine_identity(),id,sha))

    def calculation_snapshot(self):
        try:return self._calculation_snapshot()
        except (OSError,ValueError,sqlite3.Error):
            import logging
            logging.getLogger(__name__).warning('Prop calculation reuse unavailable',exc_info=True)
            return {}

    def _calculation_snapshot(self):
        from ..optimization_cache import engine_identity
        with self.connect() as db:
            rows=db.execute("SELECT c.key,c.id,c.sha256 FROM calculation_reuse c JOIN analyses a ON a.id=c.id WHERE c.engine=? AND a.status='complete' ORDER BY a.created DESC LIMIT 512",(engine_identity(),)).fetchall()
        return {key:dict(id=id,path=str(self.root/id/'calculations.json'),sha256=sha) for key,id,sha in rows}

    def summary(self, id, record=None):
        record=record if record is not None else self.get(id)
        if not record:return None
        result=dict(id=id,status=record['status'],historical_net=None,reason=record['error'],error=record['error'])
        if record['status']=='complete':
            try:
                raw=(self.root/id/'report.json').read_bytes()
                with self.connect() as db:
                    saved=db.execute('SELECT payload FROM analysis_report_checks WHERE id=?',(id,)).fetchone()
                if saved and sha256(raw).hexdigest()!=json.loads(saved[0])['report.json']:
                    raise ValueError('Saved prop report failed its integrity check; configure a new analysis.')
                report=json.loads(raw)
            except (OSError,ValueError) as exc:
                return dict(result,status='error',error=str(exc),reason=str(exc))
            calculations=report.get('calculations',{})
            history=calculations.get('history')
            result.update(historical_net=history['totals']['net'] if history else None,
                          reason=calculations.get('unavailable'),settings=report.get('settings',{}))
        return result

    def discard_prepared(self, prepared):
        """Rollback this freshly published analysis if its backtest could not save."""
        import shutil
        with self.connect() as db:
            row=db.execute('SELECT source_id,created,request_hash FROM analyses WHERE id=?',(prepared['id'],)).fetchone()
            expected=(prepared['source_id'],prepared['created_at_utc'],prepared['request_hash'])
            if row!=expected:raise ValueError('Refusing to remove an unrelated prop analysis.')
            shutil.rmtree(self.root/prepared['id'],ignore_errors=True)
            db.execute('DELETE FROM analysis_report_checks WHERE id=?',(prepared['id'],))
            db.execute('DELETE FROM analysis_sources WHERE analysis_id=?',(prepared['id'],))
            db.execute('DELETE FROM analyses WHERE id=?',(prepared['id'],))

    def fingerprint(self, id):
        from .adapter import digest
        record=self.get(id)
        if not record:return None
        result=dict(record=record,files={})
        if record['status']=='complete':
            with self.connect() as db:
                saved=db.execute('SELECT payload FROM analysis_report_checks WHERE id=?',(id,)).fetchone()
            if not saved or sealed_checks(self.root/id)!=json.loads(saved[0]):return None
            report=json.loads((self.root/id/'report.json').read_text())
            for name in [*report['files'],'report.json','analysis.zip']:
                path=(self.root/id/name).resolve()
                if not path.is_relative_to((self.root/id).resolve()):raise ValueError('Invalid prop report artifact.')
                result['files'][name]=digest(path)
                if name in report['files'] and result['files'][name]!=report['files'][name]['sha256']:return None
        return result

    def _run(self,runs,id,request,expected_source):
        try:
            self._update(id,'running','Preparing source')
            with TemporaryDirectory(prefix='.pending-',dir=self.root) as temp:
                staged=Path(temp)/'report';staged.mkdir()
                from .calculation_cache import use
                with self.runtime.activate(),use(self.calculation_snapshot()):
                    result=run_analysis(runs,request,staged,lambda msg:self._update(id,'running',msg))
                if canonical(result['source'])!=canonical(expected_source):
                    raise ValueError('Source changed after submission.')
                self._update(id,'running','Publishing local calculation report and downloads')
                seal_report(staged,result,id,self.get(id)['created'])
                staged.rename(self.root/id)
            with self.connect() as db:
                db.execute('INSERT INTO analysis_report_checks VALUES (?,?)',(id,canonical(sealed_checks(self.root/id))))
                db.execute("UPDATE analyses SET status='complete',progress='Saved report ready' WHERE id=?",(id,))
            self.index_calculations(id)
        except Exception as exc:
            self._update(id,'error','Operation failed',f'{type(exc).__name__}: {exc}')
        # Explicit batch refreshes attach their saved results after ordinary
        # report publication. A link failure must not invalidate that report.
        try:
            from ..optimization_prop import synchronize
            synchronize(runs, self, id)
        except (sqlite3.Error,OSError,ValueError):
            import logging
            logging.getLogger(__name__).exception('Could not publish Lucid batch links; retry Refresh unavailable Lucid results.')
