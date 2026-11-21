"""Disposable, source-bound IS Narrow assessment views; never selection authority."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .artifact_reads import stamp
from .optimization_cache import artifact_paths, digest, engine_identity

VERSION='narrow-assessment-view-v1'


class ViewChanged(Exception):
    pass


class MemoRuns:
    """One metadata read per native report within an assessment request."""
    def __init__(self,runs):self.runs=runs;self.records={}
    def __getattr__(self,name):return getattr(self.runs,name)
    def get(self,id):
        if id not in self.records:self.records[id]=self.runs.get(id)
        return self.records[id]


class AssessmentView:
    def __init__(self,runs,job_id,inputs,*,job=None,rows=None):
        self.runs=runs;self.job_id=job_id;self.inputs=inputs
        self.cache=getattr(runs,'replay_cache',None);self.pending=[]
        self.temporary=TemporaryDirectory(prefix='aq-narrow-view-')
        try:self.token=self.snapshot(expected_job=job,expected_rows=rows)
        except BaseException:
            self.temporary.cleanup();raise
    def __enter__(self):return self
    def __exit__(self,*exc):self.temporary.cleanup()

    def snapshot(self,*,expected_job=None,expected_rows=None):
        with self.runs.connect() as db:
            db.execute('BEGIN')
            saved=db.execute('SELECT payload FROM optimizations WHERE id=?',(self.job_id,)).fetchone()
            if not saved:raise ViewChanged('This Narrow job was removed. Reload its results.')
            job=json.loads(saved[0])
            rows=db.execute('SELECT trial,payload FROM optimization_trials WHERE optimization_id=? ORDER BY trial',(self.job_id,)).fetchall()
            ids=set()
            for _,raw in rows:
                row=json.loads(raw);ids.add(row['run_id'])
                stress=(row.get('screening') or {}).get('cost_stress',{}).get('run_id')
                if stress:ids.add(stress)
            manifests={};ordered=sorted(ids)
            for offset in range(0,len(ordered),400):
                chunk=ordered[offset:offset+400]
                manifests.update(db.execute('SELECT id,manifest FROM runs WHERE id IN ('+','.join('?' for _ in chunk)+')',chunk).fetchall())
        paths=set();records=[]
        for id in ordered:
            raw=manifests.get(id);records.append((id,raw))
            if raw is None:continue
            try:paths.update(artifact_paths(self.runs.root,json.loads(raw)).values())
            except (ValueError,KeyError,OSError,TypeError):
                # Invalid metadata cannot qualify; assessment retains its error.
                # The raw manifest remains an input so repairing it is a miss.
                continue
        job_fields=('id','status','completed_trials','total_trials','results_snapshot_rowid','axes',
            'strategy','dataset','research','execution_settings','engine_identity')
        if expected_job is not None and any(job.get(k)!=expected_job.get(k) for k in job_fields):
            raise ViewChanged('Narrow job changed while loading. Reload its results.')
        if expected_rows is not None and digest([json.loads(raw) for _,raw in rows])!=digest(sorted(expected_rows,key=lambda row:row['trial'])):
            raise ViewChanged('Narrow trials changed while loading. Reload its results.')
        return digest(dict(version=VERSION,implementation=engine_identity(),inputs=self.inputs,
            job={k:job.get(k) for k in job_fields},rows=rows,manifests=records,
            files=[stamp(path) for path in sorted(paths)]))

    def check(self,expected=None):
        if (expected is not None and expected!=self.token) or self.snapshot()!=self.token:
            raise ViewChanged('Narrow source evidence changed. Reload the verified results before sorting.')

    def assessment(self,row,calculate):
        trial=row['trial'];key=digest([VERSION,self.token,trial]);path=Path(self.temporary.name)/(str(trial)+'.json')
        metadata=dict(kind=VERSION,token=self.token,trial=trial)
        if self.cache and self.cache.restore(key,path)==metadata:
            try:
                saved=json.loads(path.read_text())
                if saved['token']==self.token and saved['trial']==trial:return deepcopy(saved['admission'])
            except (ValueError,KeyError,TypeError):pass
        admission=calculate()
        # Re-check the whole input snapshot before publishing any new view entry.
        # Publication is deferred to finish() to avoid repeating this per row.
        self.pending.append((key,path,metadata,dict(token=self.token,trial=trial,admission=admission)))
        return admission

    def finish(self):
        self.check()
        if self.cache:
            for key,path,metadata,value in getattr(self,'pending',[]):
                path.unlink(missing_ok=True);path.write_text(json.dumps(value,sort_keys=True))
                self.cache.save(key,path,metadata)
