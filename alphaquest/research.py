"""Editable chronological splits and durable, explicit holdout execution history."""
import csv
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import io
import json
from tempfile import TemporaryFile
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StrictInt, StrictFloat, model_validator
from typing import Literal

from .backtest_data import DateRange, DatasetReadError

class SplitDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["dates", "percentage"]
    is_start: StrictStr | None = None
    is_end: StrictStr | None = None
    oos_start: StrictStr | None = None
    oos_end: StrictStr | None = None
    is_percent: StrictInt | StrictFloat | None = Field(default=None, gt=0, lt=100)

    @model_validator(mode="after")
    def complete(self):
        dates = (self.is_start, self.is_end, self.oos_start, self.oos_end)
        if self.mode == "percentage":
            if self.is_percent is None or any(v is not None for v in dates):
                raise ValueError("Percentage mode requires only is_percent, strictly between 0 and 100.")
        elif not all(dates) or self.is_percent is not None:
            raise ValueError("Date mode requires IS start/end and OOS start/end, without is_percent.")
        return self


class ResearchConflict(ValueError):
    pass


def dates_for(plan, phase="is"):
    return DateRange.parse(plan[f"{phase}_start"], plan[f"{phase}_end"])


def metadata(plan, phase="is", **extra):
    return dict(phase=phase, plan=plan, **extra)


class ResearchStore:
    def __init__(self, runs, *, recover_interrupted=True):
        self.runs = runs
        with runs.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS research_days (
                    source_key TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS research_plans (
                    strategy_id TEXT NOT NULL, source_sha256 TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(strategy_id,source_sha256));
                CREATE TABLE IF NOT EXISTS oos_attempts (
                    id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, source_sha256 TEXT NOT NULL,
                    parent_run_id TEXT NOT NULL, run_id TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, error TEXT);
                CREATE INDEX IF NOT EXISTS oos_pair ON oos_attempts(strategy_id,source_sha256);
            """)
            if recover_interrupted:
                db.execute("""UPDATE oos_attempts SET status=CASE WHEN EXISTS
                    (SELECT 1 FROM runs WHERE runs.id=oos_attempts.run_id) THEN 'complete' ELSE 'interrupted' END,
                    error='Application restarted; this request remains in execution history.'
                    WHERE status='running'""")

    def status(self, dataset, strategy_id):
        with self.runs.connect() as db:
            row = db.execute('SELECT payload FROM research_plans WHERE strategy_id=? AND source_sha256=?',
                             (strategy_id, dataset['sha256'])).fetchone()
            attempts = db.execute('SELECT id,parent_run_id,run_id,status,created_at,error,EXISTS(SELECT 1 FROM runs WHERE runs.id=oos_attempts.run_id) FROM oos_attempts WHERE strategy_id=? AND source_sha256=? ORDER BY created_at,id',
                                  (strategy_id, dataset['sha256'])).fetchall()
            legacy=db.execute("""SELECT COUNT(*) FROM runs WHERE json_extract(manifest,'$.run_metadata.dataset.sha256')=?
                AND json_extract(manifest,'$.run_metadata.strategy.id')=? AND json_extract(manifest,'$.run_metadata.research') IS NULL""",
                (dataset['sha256'],strategy_id)).fetchone()[0]
        names = ('id','parent_run_id','run_id','status','created_at','error','report_available')
        # Null limits retain compatibility for API readers without enforcing a cap.
        return dict(plan=json.loads(row[0]) if row else None, budget=None, used=len(attempts),
                    remaining=None, exhausted=False,
                    attempts=[dict(zip(names,a)) for a in attempts],legacy_reports=legacy)

    def days(self, source, dataset):
        key = dataset['sha256'] + ':' + dataset['source_timezone']
        with self.runs.connect() as db:
            row = db.execute('SELECT payload FROM research_days WHERE source_key=?',(key,)).fetchone()
        if row:return json.loads(row[0])
        # Only date/count metadata is inspected here, never OOS prices or outcomes.
        # Hash the immutable snapshot before trusting its previously validated CSV.
        with TemporaryFile(mode='w+b') as snapshot:
            digest=hashlib.sha256();size=0
            for chunk in source.iter_csv(dataset['id']):
                snapshot.write(chunk);digest.update(chunk);size+=len(chunk)
            if size!=dataset['bytes'] or digest.hexdigest()!=dataset['sha256']:
                raise DatasetReadError('Saved CSV bytes do not match the dataset metadata.')
            snapshot.seek(0)
            counts = {}
            parsed = {}
            text = io.TextIOWrapper(snapshot,encoding='utf-8-sig',newline='')
            try:
                rows=csv.reader(text);next(rows)
                for row in rows:
                    day=parsed.get(row[0])
                    if day is None:
                        day=datetime.strptime(row[0],'%m/%d/%Y').date().isoformat();parsed[row[0]]=day
                    counts[day]=counts.get(day,0)+1
            finally:text.detach()
        if sum(counts.values())!=dataset['row_count']:
            raise DatasetReadError('Saved CSV row count does not match the dataset metadata.')
        days=sorted(counts.items())
        with self.runs.connect() as db:
            db.execute('INSERT OR IGNORE INTO research_days VALUES (?,?)',(key,json.dumps(days)))
        return days

    def resolve(self, source, dataset, strategy_id, declaration):
        days=self.days(source,dataset)
        if len(days)<2:raise ValueError('IS/OOS requires at least two distinct trading dates in the dataset source timezone.')
        if declaration.mode=='percentage':
            count=int(Decimal(str(declaration.is_percent))*len(days)/100)
            if not 1<=count<len(days):raise ValueError('This percentage leaves IS or OOS without any trading dates.')
            values=(days[0][0],days[count-1][0],days[count][0],days[-1][0])
        else:values=(declaration.is_start,declaration.is_end,declaration.oos_start,declaration.oos_end)
        is_start,is_end,oos_start,oos_end=values
        dates_for(dict(is_start=is_start,is_end=is_end));dates_for(dict(oos_start=oos_start,oos_end=oos_end),'oos')
        if not days[0][0]<=is_start<=is_end<oos_start<=oos_end<=days[-1][0]:
            raise ValueError('Require dataset start <= IS start <= IS end < OOS start <= OOS end <= dataset end. Dates are inclusive in the source timezone.')
        counts=[sum(n for d,n in days if a<=d<=b) for a,b in ((is_start,is_end),(oos_start,oos_end))]
        if not all(counts):raise ValueError('Both IS and OOS must contain bars; empty ranges are not allowed.')
        plan=dict(strategy_id=strategy_id,source_sha256=dataset['sha256'],source_timezone=dataset['source_timezone'],
                  is_start=is_start,is_end=is_end,oos_start=oos_start,oos_end=oos_end,is_bars=counts[0],oos_bars=counts[1],
                  percentage_basis='chronological whole trading dates; floor(IS% × date count)',version=1)
        return plan

    def claim(self, plan):
        with self.runs.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            pair=(plan['strategy_id'],plan['source_sha256'])
            db.execute('INSERT INTO research_plans VALUES (?,?,?) ON CONFLICT(strategy_id,source_sha256) DO UPDATE SET payload=excluded.payload',(*pair,json.dumps(plan)))

    def reserve(self, plan, parent_run_id, attempt_id):
        with self.runs.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT strategy_id,source_sha256,parent_run_id,run_id,status,error FROM oos_attempts WHERE id=?',(attempt_id,)).fetchone()
            if row:
                if tuple(row[:3])!=(plan['strategy_id'],plan['source_sha256'],parent_run_id):
                    raise ResearchConflict('This OOS request ID has already been used for a different selection.')
                return dict(id=attempt_id,run_id=row[3],status=row[4],error=row[5]),False
            pair=(plan['strategy_id'],plan['source_sha256'])
            stored=db.execute('SELECT manifest FROM runs WHERE id=?',(parent_run_id,)).fetchone()
            saved=json.loads(stored[0]).get('run_metadata',{}).get('research',{}) if stored else {}
            if saved.get('phase')!='is' or saved.get('plan')!=plan:
                raise ResearchConflict('Select a completed IS report with its saved declaration before running OOS.')
            used=db.execute('SELECT COUNT(*) FROM oos_attempts WHERE strategy_id=? AND source_sha256=?',pair).fetchone()[0]
            run_id=uuid4().hex
            db.execute("INSERT INTO oos_attempts VALUES (?,?,?,?,?,'running',?,NULL)",
                       (attempt_id,*pair,parent_run_id,run_id,datetime.now(timezone.utc).isoformat()))
            return dict(id=attempt_id,run_id=run_id,status='running',number=used+1),True

    def finish(self, attempt_id, status, error=None):
        with self.runs.connect() as db:
            db.execute('UPDATE oos_attempts SET status=?,error=? WHERE id=?',(status,error,attempt_id))
