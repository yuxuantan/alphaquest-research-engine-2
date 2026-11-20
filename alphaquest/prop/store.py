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


def seal_report(staged, result, id, created, *, size_limit_bytes=128*1024*1024):
    """Build the normal durable report/downloads, without catalogue access."""
    from .adapter import digest
    result.update(id=id,created_at_utc=created,status='complete')
    files={}
    for p in staged.rglob('*'):
        if p.is_symlink():raise ValueError('Analysis output contains a symbolic link.')
        if p.is_file():files[str(p.relative_to(staged))]=dict(bytes=p.stat().st_size,sha256=digest(p))
    if size_limit_bytes is not None and sum(v['bytes'] for v in files.values())>size_limit_bytes:
        raise ValueError('Analysis output exceeds 128 MiB; no completed result was published.')
    result['files']=files
    report_text=canonical(result)
    if size_limit_bytes is not None and sum(v['bytes'] for v in files.values())+len(report_text.encode('utf-8'))>size_limit_bytes:
        raise ValueError('Analysis artifacts and embedded report exceed 128 MiB; no completed result was published. The archive is a separate compressed copy.')
    (staged/'report.json').write_text(report_text,encoding='utf-8')
    with zipfile.ZipFile(staged/'analysis.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for p in staged.rglob('*'):
            if p.is_file() and p.name!='analysis.zip':archive.write(p,str(p.relative_to(staged)))
    from ..prop_report_storage import compact
    compact(staged,sealed_checks(staged),logical_files=files)


def request_key(snapshot, settings):
    from ..optimization_cache import engine_identity
    from .native_analysis import model_version
    return sha256(canonical(dict(source=snapshot,settings=settings,model_version=model_version(settings),engine_identity=engine_identity())).encode()).hexdigest()


def sealed_checks(directory):
    from .adapter import digest
    return {name:digest(directory/name) for name in ('report.json','analysis.zip')}


class AnalysisCancelled(Exception):
    """A cooperative stop never publishes a partial candidate population."""


class AnalysisStore:
    def __init__(self,directory,*,recover_interrupted=True):
        self.root=Path(directory)/'prop_analyses';self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'catalog.sqlite3';self.lock=RLock()
        self.worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix='prop-analysis')
        self.runtime=Runtime()
        self.phase_finished=lambda id:None
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, source_id TEXT NOT NULL, created TEXT NOT NULL, status TEXT NOT NULL, progress TEXT NOT NULL, error TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS analysis_report_checks (id TEXT PRIMARY KEY REFERENCES analyses(id), payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS phase_analysis_control (analysis_id TEXT PRIMARY KEY, stop_requested INTEGER NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS analysis_compute (analysis_id TEXT PRIMARY KEY, workers INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS phase_analysis_progress (analysis_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS historical_refit_checkpoints (analysis_id TEXT NOT NULL, context_key TEXT NOT NULL, replicate INTEGER NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY(analysis_id,context_key,replicate))')
            db.execute('CREATE INDEX IF NOT EXISTS historical_refits_by_context ON historical_refit_checkpoints(context_key)')
            db.execute('CREATE TABLE IF NOT EXISTS analysis_sources (analysis_id TEXT NOT NULL, source_id TEXT NOT NULL, PRIMARY KEY(analysis_id,source_id))')
            from ..campaign_monte_carlo import initialize as initialize_sanity
            initialize_sanity(db)
            from ..prop_sim import initialize as initialize_prop_sim
            initialize_prop_sim(db)
            db.execute('CREATE INDEX IF NOT EXISTS analysis_sources_by_source ON analysis_sources(source_id)')
            db.execute('CREATE TABLE IF NOT EXISTS lifecycle_comparisons (request_id TEXT PRIMARY KEY, declaration TEXT NOT NULL, checked TEXT NOT NULL, analysis_id TEXT NOT NULL UNIQUE)')
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
            detail=db.execute('SELECT payload FROM phase_analysis_progress WHERE analysis_id=?',(id,)).fetchone()
        return dict(row,progress_details=json.loads(detail[0]) if detail else None) if row else None

    def list(self,source):
        with self.connect() as db:
            db.row_factory=sqlite3.Row;rows=db.execute('SELECT a.* FROM analyses a WHERE a.source_id=? OR EXISTS (SELECT 1 FROM analysis_sources s WHERE s.analysis_id=a.id AND s.source_id=?) ORDER BY created DESC LIMIT 100',(source,source)).fetchall()
        return [dict(row) for row in rows]

    def active_sources(self):
        with self.connect() as db:
            sources = {r[0] for r in db.execute("SELECT source_id FROM analyses WHERE status IN ('queued','running') UNION SELECT s.source_id FROM analysis_sources s JOIN analyses a ON a.id=s.analysis_id WHERE a.status IN ('queued','running') OR EXISTS (SELECT 1 FROM lifecycle_comparisons p WHERE p.analysis_id=a.id) UNION SELECT source_id FROM campaign_sources")}
            sources.update(r[0] for r in db.execute("SELECT s.source_id FROM analysis_sources s JOIN workflow_prop_simulations p ON EXISTS (SELECT 1 FROM json_each(p.payload,'$.portfolio.attempts') j WHERE j.value=s.analysis_id)"))
            sources.update(r[0] for r in db.execute("SELECT s.source_id FROM analysis_sources s JOIN workflow_prop_simulations p "
                "ON EXISTS (SELECT 1 FROM json_each(p.payload,'$.configuration.selections') j WHERE json_extract(j.value,'$.monte_carlo_id')=s.analysis_id) "
                "WHERE json_extract(p.payload,'$.preparation.status') IN ('queued','running')"))
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='forward_source_refs'").fetchone():
                sources.update(r[0] for r in db.execute('SELECT source_id FROM forward_source_refs'))
            return sources

    def source_references(self, source, *, db=None):
        """Explain existing deletion pins without changing their ownership."""
        if db is None:
            with self.connect() as connection:
                return self.source_references(source, db=connection)
        refs = [dict(kind='campaign', id=r[0]) for r in db.execute(
            'SELECT campaign_id FROM campaign_sources WHERE source_id=? ORDER BY campaign_id', (source,))]
        refs.extend(dict(kind='running_analysis', id=r[0]) for r in db.execute(
            "SELECT a.id FROM analyses a WHERE a.status IN ('queued','running') AND "
            '(a.source_id=? OR EXISTS (SELECT 1 FROM analysis_sources s WHERE s.analysis_id=a.id AND s.source_id=?)) ORDER BY a.id',
            (source, source)))
        refs.extend(dict(kind='lifecycle_comparison', id=r[0]) for r in db.execute(
            'SELECT DISTINCT p.request_id FROM lifecycle_comparisons p JOIN analysis_sources s '
            'ON s.analysis_id=p.analysis_id WHERE s.source_id=? ORDER BY p.request_id', (source,)))
        refs.extend(dict(kind='prop_portfolio',id=r[0]) for r in db.execute(
            "SELECT DISTINCT p.id FROM workflow_prop_simulations p JOIN analysis_sources s "
            "ON EXISTS (SELECT 1 FROM json_each(p.payload,'$.portfolio.attempts') j WHERE j.value=s.analysis_id) WHERE s.source_id=?",(source,)))
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='forward_source_refs'").fetchone():
            refs.extend(dict(kind='forward_monitor', id=r[0]) for r in db.execute(
                'SELECT monitor_id FROM forward_source_refs WHERE source_id=? ORDER BY monitor_id', (source,)))
        return refs

    def deletion_check(self, db, id, *, releasing_campaigns=(),releasing_prop_sim=None):
        """Shared metadata-only guards; callers may release their own links atomically."""
        record=db.execute('SELECT status FROM analyses WHERE id=?',(id,)).fetchone()
        parents={r[0] for r in db.execute("SELECT id FROM workflow_prop_simulations p WHERE EXISTS (SELECT 1 FROM json_each(p.payload,'$.portfolio.attempts') j WHERE j.value=?)",(id,))}
        if parents-{releasing_prop_sim}:raise ValueError('This report is retained by a saved Prop Sim portfolio.')
        if db.execute('SELECT 1 FROM campaign_sanity_jobs WHERE analysis_id=?',(id,)).fetchone():
            raise ValueError('This final Monte Carlo assessment is retained by its workflow history.')
        owners={r[0] for r in db.execute('SELECT campaign_id FROM campaign_analyses WHERE analysis_id=?',(id,))}
        owners.update(r[0] for r in db.execute('SELECT id FROM research_campaigns WHERE analysis_id=?',(id,)))
        if owners-set(releasing_campaigns):
            raise ValueError('This report is referenced by an immutable research campaign and cannot be deleted.')
        for table in ('forward_assessments','forward_report_refs'):
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                if db.execute(f'SELECT 1 FROM {table} WHERE analysis_id=?',(id,)).fetchone():
                    raise ValueError('This report is retained by a forward monitor and cannot be deleted.')
        if record and record[0] in ('queued','running'):
            raise ValueError('This prop analysis is queued or running. Stop it or wait for completion before deleting.')
        return record

    def load_refits(self, context_key, total):
        """Verified completed work only; never publish partial qualification."""
        with self.connect() as db:
            records=db.execute('SELECT c.replicate,c.payload,c.sha256 FROM historical_refit_checkpoints c '
                'JOIN analyses a ON a.id=c.analysis_id WHERE c.context_key=?', (context_key,)).fetchall()
        rows={}
        for index,payload,expected in records:
            if sha256(payload.encode()).hexdigest()!=expected:
                raise ValueError('Historical refit checkpoint checksum changed; completed work was not reused.')
            row=json.loads(payload)
            if not 0<=index<total or row['replicate']['replicate']!=index:
                raise ValueError('Historical refit checkpoint index changed.')
            if index in rows:
                if any(rows[index][key]!=row[key] for key in ('replicate','precision','history_keys')):
                    raise ValueError('Historical refit checkpoints disagree for the same immutable input.')
                row['preparation_cache_bytes']=max(row['preparation_cache_bytes'],rows[index]['preparation_cache_bytes'])
            rows[index]=row
        return rows

    def save_refits(self, id, context_key, rows):
        if not rows:return
        values=[]
        for row in rows:
            payload=canonical(row)
            values.append((id,context_key,row['replicate']['replicate'],payload,sha256(payload.encode()).hexdigest()))
        with self.lock,self.connect() as db:
            db.executemany('INSERT OR REPLACE INTO historical_refit_checkpoints VALUES (?,?,?,?,?)',values)

    def remove_catalogue_record(self, db, id):
        """Release one report's catalogue/cache rows within the caller transaction."""
        for table,key in (('calculation_reuse','id'),('analysis_report_checks','id'),
                ('historical_refit_checkpoints','analysis_id'),('analysis_sources','analysis_id'),('phase_analysis_control','analysis_id'),('phase_analysis_progress','analysis_id'),('analysis_compute','analysis_id'),('analyses','id')):
            db.execute(f'DELETE FROM {table} WHERE {key}=?',(id,))

    def delete(self, id):
        """Delete one inactive analysis; roll back file staging on SQL failure."""
        import shutil
        id=UUID(id).hex
        destination=self.root/id;staged=self.root/('.deleted-'+id);moved=False
        with self.lock:
            try:
                with self.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    record=self.deletion_check(db,id)
                    if destination.is_symlink() or staged.is_symlink():
                        raise OSError('Refusing to delete a symbolic-link prop report directory.')
                    if not record and not staged.exists():return False
                    if record:
                        if staged.exists():
                            if destination.exists():raise OSError('Conflicting staged deletion; no report files were removed.')
                            staged.rename(destination)
                        if destination.exists():destination.rename(staged);moved=True
                    self.remove_catalogue_record(db,id)
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

    def submit_pairs(self, datasets, runs, campaigns, request):
        """Bind an explicit pair declaration to one normal durable analysis."""
        from .phase_lifecycle import check_frozen_pairs
        from ..research import ResearchConflict
        from ..optimization_cache import digest
        declaration = canonical(request.model_dump(mode='json'))
        with self.lock:
            with self.connect() as db:
                previous = db.execute('SELECT declaration,checked,analysis_id FROM lifecycle_comparisons WHERE request_id=?',
                    (request.request_id,)).fetchone()
            if previous and previous[0] != declaration:
                raise ResearchConflict('Pair request ID is already bound to another declaration. Use a new request ID for a changed comparison.')
            checked = check_frozen_pairs(datasets, runs, campaigns, request)
            captured = canonical(checked)
            if previous:
                if captured != previous[1]:
                    raise ResearchConflict('Frozen pair inputs or implementation changed; the original comparison is preserved.')
                id = previous[2];record = self.get(id)
                if record is None:
                    raise ResearchConflict('This comparison was deleted; its request ID cannot be reused.')
                if record['status'] in ('queued', 'running'):
                    return record
                if record['status'] == 'complete':
                    if self.fingerprint(id) is None or not self.native_children_unchanged(runs, id):
                        raise ResearchConflict('Saved comparison or captured native child identity changed.')
                    return record
                if (self.root/id).exists():
                    raise ResearchConflict('An interrupted comparison has retained publication files; inspect them before making a new request.')
                with self.connect() as db:
                    db.execute("UPDATE analyses SET status='queued',progress='Queued exact frozen-pair retry',error=NULL WHERE id=?", (id,))
                    db.execute('UPDATE phase_analysis_control SET stop_requested=0 WHERE analysis_id=?', (id,))
            else:
                id = uuid4().hex
                sources = {policy['source']['id'] for pair in checked['pairs'] for policy in pair['policies'].values()}
                sources.update(policy['configuration']['source']['source_backtest_id']
                    for pair in checked['pairs'] for policy in pair['policies'].values())
                first = request.pairs[0].evaluation.source_backtest_id
                with self.connect() as db:
                    db.execute('INSERT INTO lifecycle_comparisons VALUES (?,?,?,?)',
                        (request.request_id, declaration, captured, id))
                    db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',
                        (id, digest(dict(request=request.model_dump(mode='json'),check=checked)), first,
                         datetime.now(timezone.utc).isoformat(), 'queued', 'Queued predefined lifecycle comparison', None))
                    db.executemany('INSERT INTO analysis_sources VALUES (?,?)', [(id, source) for source in sorted(sources)])
                    db.execute('INSERT INTO phase_analysis_control(analysis_id) VALUES (?)', (id,))
            self.worker.submit(self._run_pairs, datasets, runs, campaigns, id, request, checked)
            return self.get(id)

    def _run_pairs(self, datasets, runs, campaigns, id, request, checked):
        from .phase_lifecycle import run_frozen_pairs
        reserved = []
        def checkpoint():
            with self.connect() as db:
                row = db.execute('SELECT stop_requested FROM phase_analysis_control WHERE analysis_id=?', (id,)).fetchone()
            if row and row[0]:
                raise AnalysisCancelled('Lifecycle comparison stopped; no partial pair population was published.')
        def reserve_child(child):
            with self.lock, self.connect() as db:
                db.execute('INSERT INTO analysis_sources VALUES (?,?)', (id, child))
            reserved.append(child)
        def progress(message):
            checkpoint();self._update(id, 'running', message)
        try:
            progress('Checking frozen pair sources and actual chronological continuation')
            with TemporaryDirectory(prefix='.pending-', dir=self.root) as temp:
                staged = Path(temp)/'report';staged.mkdir()
                with self.runtime.activate():
                    calculations = run_frozen_pairs(datasets, runs, campaigns, request, checked,
                        analysis_id=id, reserve_child=reserve_child, checkpoint=checkpoint, progress=progress)
                result = dict(format_version=8, model_version='alphaquest-frozen-pair-v1',
                    engine='AlphaQuest local native strategy and independent phase controllers',
                    request=request.model_dump(mode='json'), settings=dict(ANALYSIS_MODE=request.mode),
                    source=dict(backtest=checked['pairs'][0]['policies']['evaluation']['source']),
                    source_check=checked, calculations=calculations,
                    implementation=dict(engine_identity=checked['pairs'][0]['binding']['engine_identity']),
                    production_qualified=False)
                (staged/'request.json').write_text(canonical(result['request']))
                (staged/'source_check.json').write_text(canonical(checked))
                (staged/'results.json').write_text(canonical(calculations))
                import csv
                ledger = []
                for number, pair in enumerate(calculations['pairs'], 1):
                    folder=staged/'pairs'/str(number);folder.mkdir(parents=True)
                    for phase in ('evaluation', 'funded'):
                        (folder/(phase+'_package.json')).write_text(canonical(checked['pairs'][number-1]['policies'][phase]['package']))
                        (folder/(phase+'_result.json')).write_text(canonical(pair[phase]))
                    (folder/'pair_binding.json').write_text(canonical(pair['pair_binding']))
                    (folder/'continuation_binding.json').write_text(canonical(pair['continuation_binding']))
                    (folder/'cash.json').write_text(canonical(pair['cash']))
                    ledger.extend(dict(pair_id=pair['id'], **event) for event in pair['cash']['cash_ledger'])
                (staged/'cash_ledger.json').write_text(canonical(ledger))
                columns = sorted({key for event in ledger for key in event})
                with (staged/'cash_ledger.csv').open('w', newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader();writer.writerows(ledger)
                self.capture_native_children(runs, staged, result, reserved)
                with self.lock:
                    checkpoint()
                    seal_report(staged, result, id, self.get(id)['created'])
                    checkpoint()
                    staged.rename(self.root/id)
                    with self.connect() as db:
                        db.execute('INSERT INTO analysis_report_checks VALUES (?,?)', (id, canonical(sealed_checks(self.root/id))))
                        db.execute("UPDATE analyses SET status='complete',progress='Saved predefined lifecycle comparison ready' WHERE id=?", (id,))
        except AnalysisCancelled as exc:
            self._update(id, 'cancelled', 'Comparison stopped; retry the exact declaration', str(exc))
        except Exception as exc:
            self._update(id, 'error', 'Predefined lifecycle comparison failed', f'{type(exc).__name__}: {exc}')
        finally:
            with self.lock, self.connect() as db:
                for child in reserved:
                    if runs.get(child) is None:
                        db.execute('DELETE FROM analysis_sources WHERE analysis_id=? AND source_id=?', (id,child))

    def submit_funded(self, runs, search):
        return self.submit_phase(runs, search)

    def _reserve_phase(self, runs, search, *, campaign_checks=None, assessment=None,
                       training_context=None, inline=False, datasets=None, prepared_checks=None, guard=None):
        """Shared checked reservation; callers hold the catalogue mutation lock."""
        from .phase_dispatch import module_for_mode
        from .phase_search import check_candidates, validate_phase_work
        if assessment is not None and training_context is not None:
            raise ValueError('A phase source cannot be both nested training and manual assessment.')
        module = module_for_mode(search.mode)
        phase = 'Funded' if search.mode == 'funded_optimization' else 'Evaluation'
        validate_phase_work(search, len(training_context['session_inventory']) if training_context else None)
        if assessment and assessment.get('kind')=='is_robustness' and getattr(search,'conservative_objective',None) is not None:
            bound=validate_phase_work(search)
            blocks={1,5,20,*[c.sampling.block_weekdays for c in search.candidates]}
            if bound['estimated_capture_bytes']*(len(blocks)+2)>100*1024*1024:
                raise ValueError('Robustness report is too large; reduce diagnostic paths or frozen choices.')
        if prepared_checks is not None:
            if guard is None or assessment or training_context:raise ValueError('Only guarded ordinary IS checks may be prepared before reservation.')
            guard();checks=prepared_checks
        elif assessment or training_context:
            checks = check_candidates(runs, search, assessment, training_context=training_context, datasets=datasets)
        else:
            checks = module.check_search(runs, search, datasets=datasets)
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
                if valid and row[1]=='complete' and getattr(search,'native_execution',None) is not None:
                    valid=self.native_children_unchanged(runs,row[0])
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
            db.execute('INSERT INTO phase_analysis_control(analysis_id) VALUES (?)',(id,))
            if training_context:
                db.execute('INSERT INTO campaign_analyses VALUES (?,?)', (training_context['campaign_id'], id))
        return self.get(id), checks, True

    def cancel_phase(self, id):
        with self.lock:
            with self.connect() as db:
                row=db.execute('SELECT a.status FROM analyses a JOIN phase_analysis_control c ON c.analysis_id=a.id WHERE a.id=?',(id,)).fetchone()
                if row is None:
                    raise ValueError('This analysis does not support cooperative phase cancellation.')
                if row[0] not in ('queued','running'):
                    raise ValueError('Only queued or running phase analyses can be cancelled.')
                db.execute('UPDATE phase_analysis_control SET stop_requested=1 WHERE analysis_id=?',(id,))
                db.execute("UPDATE analyses SET progress='Stop requested; waiting for the next safe calculation boundary' WHERE id=?",(id,))
            return self.get(id)

    def submit_phase(self, runs, search, *, campaign_checks=None, assessment=None, datasets=None, prepared_checks=None, guard=None, workers=None):
        """Public phase dispatch retains the existing worker and request meaning."""
        selected=self.runtime.workers if workers is None else workers
        from .parallel import CAPACITY
        if type(selected) is not int or not 1<=selected<=CAPACITY:raise ValueError('Invalid parallel worker count.')
        with self.lock:
            record, checks, fresh = self._reserve_phase(runs, search, campaign_checks=campaign_checks, assessment=assessment, datasets=datasets,
                prepared_checks=prepared_checks,guard=guard)
            if fresh:
                with self.connect() as db:db.execute('INSERT INTO analysis_compute VALUES (?,?)',(record['id'],selected))
                self.worker.submit(self._run_phase, runs, record['id'], search, checks, assessment, datasets=datasets)
            return record

    def run_phase_inline(self, runs, search, *, training_context, checkpoint=lambda:None,
                         progress=lambda message:None, datasets=None):
        """Internal nested child: normal durable report, no same-worker wait."""
        if not training_context:
            raise ValueError('Inline nested phase execution requires a server-derived training context.')
        checkpoint()
        with self.lock:
            record, checks, fresh = self._reserve_phase(runs, search, training_context=training_context, inline=True, datasets=datasets)
        if fresh:
            self._run_phase(runs, record['id'], search, checks, training_context=training_context,
                            checkpoint=checkpoint, progress=progress, raise_errors=True, datasets=datasets)
        checkpoint()
        return self.get(record['id'])

    def _run_phase(self, runs, id, search, checks, assessment=None, *, training_context=None,
                   checkpoint=lambda:None, progress=lambda message:None, raise_errors=False, datasets=None):
        from .phase_dispatch import module_for_mode
        module = module_for_mode(search.mode)
        optimize = module.optimize_funded if search.mode == 'funded_optimization' else module.optimize_evaluation
        phase = 'Funded' if search.mode == 'funded_optimization' else 'Evaluation'
        reserved_children=[];reused_children=[]
        def reserve_child(child_id):
            with self.lock,self.connect() as db:
                db.execute('INSERT INTO analysis_sources VALUES (?,?)',(id,child_id))
                if assessment:
                    db.execute('INSERT OR IGNORE INTO campaign_sources VALUES (?,?)',(assessment['campaign_id'],child_id))
            reserved_children.append(child_id)
        parent_checkpoint=checkpoint
        def checkpoint():
            parent_checkpoint()
            with self.connect() as db:
                row=db.execute('SELECT stop_requested FROM phase_analysis_control WHERE analysis_id=?',(id,)).fetchone()
            if row and row[0]:
                raise AnalysisCancelled('Phase search stopped; no partial result was published. Run again to replay the same complete declaration.')
        def update(message):
            checkpoint()
            details=message if isinstance(message,dict) else None
            if details:
                label=details.get('sizing_label') or f"{details['micros']} MNQ"
                stage=({'complementary_evidence':'Complementary evidence','native_execution':'Native account execution','saved_trade_execution':'Saved-trade account simulation','native_preparation':'Preparing native source'}.get(details.get('stage'),'Historical confidence'))
                message=(f"{stage} · {label} · {details['completed']:,}/{details['total']:,} {details.get('unit','resamples')} · {details['worker_count']} workers")
            self._update(id, 'running', message,progress_details=details)
            progress(message)
        try:
            update('Running independent '+phase+' search')
            with TemporaryDirectory(prefix='.pending-', dir=self.root) as temp:
                staged = Path(temp)/'report'; staged.mkdir()
                with self.connect() as db:compute=db.execute('SELECT workers FROM analysis_compute WHERE analysis_id=?',(id,)).fetchone()
                with self.runtime.activate(workers=compute[0] if compute else None):
                    options = dict(assessment=assessment,checkpoint=checkpoint) if assessment else dict(checkpoint=checkpoint)
                    if getattr(search, 'native_execution', None) is not None:
                        if assessment is not None:
                            options['assessment'] = dict(assessment,analysis_id=id)
                            options['reserve_child'] = reserve_child
                        options['datasets'] = datasets
                        options['checkpoint'] = checkpoint
                    if training_context is not None:
                        options['training_context'] = training_context
                    review_options = assessment.get('prop_sim_review') if assessment else None
                    base = review_options.get('base_report') if review_options else None
                    def verified_base():
                        from .phase_dispatch import implementations_compatible
                        fingerprint = self.fingerprint(base['analysis_id'])
                        if not fingerprint or fingerprint['files']['report.json'] != base['sha256']:
                            raise ValueError('Saved OOS report changed; no numerical results were reused.')
                        report = json.loads((self.root/base['analysis_id']/'report.json').read_text())
                        if (report.get('assessment', {}).get('frozen_package') != assessment['frozen_package']
                                or report['calculations'].get('assessment_kind') not in ('oos','qualification','forward_review')
                                or not implementations_compatible(report['implementation'], module.implementation_identity())):
                            raise ValueError('Saved OOS report does not match the frozen numerical package.')
                        original = {r['candidate_id']:r['manifest'] for r in report['calculations']['candidates']}
                        if original != {c['candidate_id']:c['manifest'] for c in checks}:
                            raise ValueError('Saved OOS candidate/source identity changed; no results were reused.')
                        if getattr(search,'native_execution',None) is not None and not self.native_children_unchanged(runs,report['id']):raise ValueError('Saved OOS native child capture changed.')
                        return report
                    if base:
                        from copy import deepcopy
                        update('Reusing verified OOS numerical results; applying declared review')
                        previous=verified_base();calculations = deepcopy(previous['calculations'])
                        reused_children=list(previous.get('native_backtests',{}))
                        with self.connect() as db:
                            for child in reused_children:db.execute('INSERT OR IGNORE INTO analysis_sources VALUES (?,?)',(id,child))
                    else:
                        calculations = optimize(runs, search, checks, update, **options)
                    if review_options:
                        if review_options.get('qualification'):
                            from .oos_qualification import qualify
                            calculations=qualify(calculations,search,assessment,runs,checks,checkpoint,update,staged,self,analysis_id=id,datasets=datasets)
                        else:
                            from .assessment_review import enrich
                            # A business-policy review can reuse the point paths
                            # of a qualification without inheriting its verdict.
                            for key in list(calculations):
                                if key.startswith('qualification_') or key=='forward_execution_review':calculations.pop(key)
                            for row in calculations['candidates']:row.pop('prop_qualification',None)
                            calculations = enrich(calculations, search, assessment, runs, checks, checkpoint, update,datasets=datasets)
                if assessment:
                    calculations['assessment'] = assessment
                result = module.write_report(runs, staged, search, checks, calculations)
                if reserved_children or reused_children:
                    self.capture_native_children(runs, staged, result, [*reserved_children,*reused_children])

                if assessment:
                    result['assessment'] = assessment
                    result['settings']['ANALYSIS_MODE'] = search.mode.replace('_optimization', '_assessment')
                    (staged/'frozen_package.json').write_text(canonical(assessment['frozen_package']))
                    if review_options and review_options.get('qualification'):
                        (staged/'qualification_policy.json').write_text(canonical(calculations['qualification_policy']))
                        (staged/'oos_qualification.json').write_text(canonical([
                            dict(candidate_id=r['candidate_id'],frozen_candidate_id=r['frozen_candidate_id'],
                                micros=r['configuration']['micros'],qualification=r['prop_qualification']) for r in calculations['candidates']]))
                        if 'qualification_bootstrap' in calculations:
                            (staged/'historical_bootstrap.json').write_text(canonical(calculations['qualification_bootstrap']))
                        if 'qualification_complementary' in calculations:
                            (staged/'complementary_evidence.json').write_text(canonical(calculations['qualification_complementary']))
                        if calculations.get('account_start_sensitivity') is not None:
                            (staged/'account_start_sensitivity.json').write_text(canonical(calculations['account_start_sensitivity']))
                        if calculations.get('forward_execution_review') is not None:
                            (staged/'forward_execution_review.json').write_text(canonical(calculations['forward_execution_review']))
                    elif review_options:
                        (staged/'assessment_policy.json').write_text(canonical(calculations['assessment_policy']))
                        (staged/'economic_assessment.json').write_text(canonical([
                            dict(candidate_id=r['candidate_id'],micros=r['configuration']['micros'],
                                 economic_assessment=r['economic_assessment'],outcome_summary=r['outcome_summary'])
                            for r in calculations['candidates']]))
                        if calculations.get('account_start_sensitivity') is not None:
                            (staged/'account_start_sensitivity.json').write_text(canonical(calculations['account_start_sensitivity']))
                if training_context is not None:
                    from .phase_search import check_candidates
                    current = check_candidates(runs, search, training_context=training_context, datasets=datasets)
                    if [c['candidate_id'] for c in current] != [c['candidate_id'] for c in checks]:
                        raise ValueError('Nested training source changed during phase calculation.')
                    result['training_context'] = training_context
                    (staged/'training_context.json').write_text(canonical(training_context))
                # Stop admission and completed publication share the same lock:
                # an accepted cancellation cannot race with a completed report.
                with self.lock:
                    checkpoint()
                    if assessment and review_options:
                        if review_options.get('qualification'):
                            from .oos_qualification import implementation
                        else:
                            from .assessment_review import implementation
                        if review_options['implementation'] != implementation():
                            raise ValueError('Review implementation changed before publication.')
                        if base: verified_base()
                        if review_options.get('forward_capture'):
                            from ..prop_sim_forward import verified_observation
                            verified_observation(review_options['forward_capture'],review_options['simulation_id'],phase.lower(),base['analysis_id'],self)
                    size_limit = (128*1024*1024 if (getattr(search,'native_execution',None) is not None and not search.native_execution.prepared_execution)
                                  or getattr(search,'conservative_objective',None) is not None else None)
                    seal_report(staged, result, id, self.get(id)['created'],size_limit_bytes=size_limit)
                    staged.rename(self.root/id)
                    with self.connect() as db:
                        db.execute('INSERT INTO analysis_report_checks VALUES (?,?)', (id, canonical(sealed_checks(self.root/id))))
                        db.execute("UPDATE analyses SET status='complete',progress=? WHERE id=?", ('Saved '+phase+' search ready', id))
                        db.execute('DELETE FROM historical_refit_checkpoints WHERE analysis_id=?',(id,))
        except AnalysisCancelled as exc:
            self._update(id,'cancelled','Phase search stopped; run again from the saved declaration',str(exc))
            if raise_errors:raise
        except Exception as exc:
            self._update(id, 'error', phase+' search failed', f'{type(exc).__name__}: {exc}')
            if raise_errors:
                raise
        finally:
            with self.lock,self.connect() as db:
                for child_id in reserved_children:
                    if runs.get(child_id) is None:
                        db.execute('DELETE FROM analysis_sources WHERE analysis_id=? AND source_id=?',(id,child_id))
                        if assessment:db.execute('DELETE FROM campaign_sources WHERE campaign_id=? AND source_id=?',(assessment['campaign_id'],child_id))
            self.phase_finished(id)

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

    def _update(self,id,status,progress,error=None,*,progress_details=None):
        with self.connect() as db:
            db.execute('UPDATE analyses SET status=?,progress=?,error=? WHERE id=?',(status,progress,error,id))
            if progress_details is not None:
                db.execute('INSERT OR REPLACE INTO phase_analysis_progress VALUES (?,?)',(id,canonical(progress_details)))
            elif status=='running':db.execute('DELETE FROM phase_analysis_progress WHERE analysis_id=?',(id,))

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

    def capture_native_children(self, runs, staged, result, children):
        """One capture contract for actual native children across analysis modes."""
        import shutil
        from .adapter import digest
        from ..optimization_cache import artifacts
        result['native_backtests']={}
        for child_id in children:
            child=runs.get(child_id)
            if child is None:raise ValueError('Native controlled child was not published.')
            hashes=artifacts(runs.root,child)
            folder=staged/'native_backtests'/child_id;folder.mkdir(parents=True)
            capture={}
            for name,expected in hashes.items():
                if name=='shared_holding_day':
                    from ..market_equity import holding_path
                    source=holding_path(runs.root/child_id,child['market_benchmark'])
                    target='shared_holding_day.csv'
                else:source=runs.root/child_id/name;target=name
                destination=folder/target;destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,destination)
                if digest(destination)!=expected:raise ValueError('Native child changed during report capture.')
                capture[name]=str(destination.relative_to(staged))
            (folder/'manifest.json').write_text(canonical(child))
            result['native_backtests'][child_id]=dict(record=child,artifact_sha256=hashes,captured_files=capture)

    def native_children_unchanged(self, runs, id):
        """Live child links must still agree with the immutable report capture."""
        from ..optimization_cache import artifacts
        try:
            report=json.loads((self.root/id/'report.json').read_text())
            return all((child:=runs.get(child_id)) is not None
                and canonical(child)==canonical(saved['record'])
                and artifacts(runs.root,child)==saved['artifact_sha256']
                for child_id,saved in report.get('native_backtests',{}).items())
        except (OSError,ValueError,KeyError):
            return False

    def fingerprint(self, id):
        from ..prop_report_storage import digest
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
