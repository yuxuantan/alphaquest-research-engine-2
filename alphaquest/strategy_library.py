"""Disposable instrument index over the existing immutable backtest catalogue."""
from hashlib import sha256
import json
import re
from threading import Lock
from fastapi import APIRouter,HTTPException,Query,Request


class StrategyLibrary:
    def __init__(self,runs,datasets,analyses):
        self.runs,self.datasets,self.analyses=runs,datasets,analyses
        self.lock=Lock()
        with runs.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS strategy_run_index (run_id TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE, group_id TEXT NOT NULL,instrument TEXT NOT NULL,dataset_id TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS strategy_instrument_groups ON strategy_run_index(group_id)')
            db.execute("CREATE INDEX IF NOT EXISTS optimization_trial_run_id ON optimization_trials(json_extract(payload,'$.run_id'))")

    def sync(self):
        with self.lock:
            sources=None
            while True:
                with self.runs.connect() as db:
                    missing=db.execute('SELECT r.id,r.manifest FROM runs r LEFT JOIN strategy_run_index i ON i.run_id=r.id WHERE i.run_id IS NULL LIMIT 500').fetchall()
                if not missing:return
                if sources is None:sources={d['id']:d for d in self.datasets.list()}
                values=[]
                for id,raw in missing:
                    record=json.loads(raw);metadata=record['run_metadata'];dataset=metadata['dataset']
                    instrument=metadata.get('instrument',{}).get('symbol')
                    if instrument is None:instrument=sources.get(dataset['id'],{}).get('symbol','')
                    instrument=(instrument or '').strip().upper()
                    # An unknown symbol cannot establish instrument equivalence.
                    identity='symbol:'+instrument if instrument else 'dataset:'+dataset['id']
                    label=instrument or 'Unspecified · '+dataset['name']
                    values.append((id,sha256(identity.encode()).hexdigest(),label,dataset['id']))
                with self.runs.connect() as db:
                    db.executemany('INSERT OR IGNORE INTO strategy_run_index SELECT ?,?,?,? WHERE EXISTS (SELECT 1 FROM runs WHERE id=?)',[(*row,row[0]) for row in values])

    def groups(self,offset,limit):
        self.sync()
        with self.runs.connect() as db:
            total=db.execute('SELECT COUNT(DISTINCT group_id) FROM strategy_run_index').fetchone()[0]
            rows=db.execute('SELECT i.group_id,i.instrument,COUNT(*),MAX(r.created_at) FROM strategy_run_index i JOIN runs r ON r.id=i.run_id GROUP BY i.group_id,i.instrument ORDER BY i.instrument COLLATE NOCASE,i.group_id LIMIT ? OFFSET ?',(limit,offset)).fetchall()
        return dict(items=[dict(id=id,instrument=instrument,backtests=count,latest_run_utc=latest) for id,instrument,count,latest in rows],total=total,offset=offset,limit=limit)

    def reports(self,group,offset,limit):
        if not re.fullmatch('[0-9a-f]{64}',group):return None
        self.sync()
        with self.runs.connect() as db:
            found=db.execute('SELECT instrument,COUNT(*) FROM strategy_run_index WHERE group_id=? GROUP BY instrument',(group,)).fetchone()
            if not found:return None
            rows=db.execute('SELECT r.manifest,(SELECT t.optimization_id FROM optimization_trials t WHERE json_extract(t.payload,\'$.run_id\')=r.id ORDER BY t.rowid LIMIT 1) FROM runs r JOIN strategy_run_index i ON i.run_id=r.id WHERE i.group_id=? ORDER BY r.created_at DESC,r.id LIMIT ? OFFSET ?',(group,limit,offset)).fetchall()
        items=[]
        for raw,batch in rows:
            record=json.loads(raw);metadata=record['run_metadata'];summary=record['summary']
            prop=metadata.get('automatic_prop_analysis')
            analysis=self.analyses.summary(prop['id']) if prop else None
            items.append(dict(id=record['id'],strategy_id=metadata['strategy']['id'],dataset_id=metadata['dataset']['id'],dataset_name=metadata['dataset']['name'],created_at_utc=record['created_at_utc'],selection=metadata.get('selection',{}),metrics={key:summary.get(key) for key in ('total_net_pnl','trades_taken','max_drawdown_amount')},historical_net=analysis.get('historical_net') if analysis else None,prop_status=analysis.get('status') if analysis else None,batch_id=batch))
        return dict(group=dict(id=group,instrument=found[0]),items=items,total=found[1],offset=offset,limit=limit)


router=APIRouter()


@router.get('/api/strategies/groups')
def groups(request:Request,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100)):
    return request.app.state.strategy_library.groups(offset,limit)


@router.get('/api/strategies/groups/{group_id}/backtests')
def reports(group_id:str,request:Request,offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100)):
    result=request.app.state.strategy_library.reports(group_id,offset,limit)
    if result is None:raise HTTPException(404,'Instrument group not found.')
    return result
