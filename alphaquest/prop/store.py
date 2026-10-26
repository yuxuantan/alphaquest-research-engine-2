"""One durable job/report catalogue. Completed reports publish by atomic rename."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import csv
import io
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Lock
from uuid import uuid4
import zipfile
from .adapter import canonical
from .native_analysis import run_analysis


class AnalysisStore:
    def __init__(self,directory):
        self.root=Path(directory)/'prop_analyses';self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'catalog.sqlite3';self.lock=Lock()
        self.worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix='prop-analysis')
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, source_id TEXT NOT NULL, created TEXT NOT NULL, status TEXT NOT NULL, progress TEXT NOT NULL, error TEXT)')
            db.execute("UPDATE analyses SET status='error',error='Application stopped before publication; run again.',progress='Interrupted' WHERE status IN ('queued','running')")

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=30)
        try:
            with db:yield db
        finally:db.close()

    def close(self):self.worker.shutdown(wait=True)

    def get(self,id):
        with self.connect() as db:
            db.row_factory=sqlite3.Row;row=db.execute('SELECT * FROM analyses WHERE id=?',(id,)).fetchone()
        return dict(row) if row else None

    def list(self,source):
        with self.connect() as db:
            db.row_factory=sqlite3.Row;rows=db.execute('SELECT * FROM analyses WHERE source_id=? ORDER BY created DESC LIMIT 100',(source,)).fetchall()
        return [dict(row) for row in rows]

    def submit(self,runs,request):
        # Source fingerprint is checked by preparation, and included in the key.
        from .native_analysis import prepare
        snapshot,_,settings=prepare(runs,request['source_backtest_id'],request.get('trade_file'),request['settings'],request['export_timezone'])
        request={**request,'trade_file':snapshot['excursion_input']['path']}
        key=sha256(canonical(dict(request=request,source=snapshot,settings=settings)).encode()).hexdigest()
        with self.lock,self.connect() as db:
            row=db.execute("SELECT id FROM analyses WHERE request_hash=? AND status IN ('queued','running')",(key,)).fetchone()
            if row:return self.get(row[0])
            id=uuid4().hex
            db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(id,key,request['source_backtest_id'],datetime.now(timezone.utc).isoformat(),'queued','Queued',None))
        self.worker.submit(self._run,runs,id,request,(snapshot['trades_sha256'],snapshot['excursion_input']['sha256']))
        return self.get(id)

    def _update(self,id,status,progress,error=None):
        with self.connect() as db:db.execute('UPDATE analyses SET status=?,progress=?,error=? WHERE id=?',(status,progress,error,id))

    def _run(self,runs,id,request,expected_source):
        try:
            self._update(id,'running','Preparing source')
            with TemporaryDirectory(prefix='.pending-',dir=self.root) as temp:
                staged=Path(temp)/'report';staged.mkdir()
                result=run_analysis(runs,request,staged,lambda msg:self._update(id,'running',msg))
                if (result['source']['trades_sha256'],result['source']['excursion_input']['sha256'])!=expected_source:
                    raise ValueError('Source changed after submission.')
                result.update(id=id,created_at_utc=self.get(id)['created'],status='complete')
                self._update(id,'running','Publishing local calculation report and downloads')
                files={}
                for p in staged.rglob('*'):
                    if p.is_symlink():raise ValueError('Analysis output contains a symbolic link.')
                    if p.is_file():
                        from .adapter import digest
                        files[str(p.relative_to(staged))]=dict(bytes=p.stat().st_size,sha256=digest(p))
                if sum(v['bytes'] for v in files.values())>128*1024*1024:
                    raise ValueError('Analysis output exceeds 128 MiB; no completed result was published.')
                result['files']=files
                (staged/'report.json').write_text(canonical(result),encoding='utf-8')
                with zipfile.ZipFile(staged/'analysis.zip','w',zipfile.ZIP_DEFLATED) as archive:
                    for p in staged.rglob('*'):
                        if p.is_file() and p.name!='analysis.zip':archive.write(p,str(p.relative_to(staged)))
                staged.rename(self.root/id)
            self._update(id,'complete','Saved report ready')
        except Exception as exc:
            self._update(id,'error','Operation failed',f'{type(exc).__name__}: {exc}')
