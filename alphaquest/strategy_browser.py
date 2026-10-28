"""Disposable, paged strategy/dataset/run index over saved products only."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import sqlite3
from threading import Lock
from zoneinfo import ZoneInfo

from .strategies.registry import list_strategies

METRICS=('total_net_pnl','max_drawdown_amount','trades_taken','win_rate_pct')


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def numeric(value):
    try:
        result=Decimal(value)
        if result.is_finite():return (0,result)
    except InvalidOperation:pass
    return (1,value)


def full_source(saved):
    keys=('id','name','sha256','source_timezone','row_count','start','end','symbol')
    result={k:saved.get(k) for k in keys}
    zone=ZoneInfo(result['source_timezone'])
    for source,target in (('start','start_date'),('end','end_date')):
        value=result[source]
        result[target]=datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(zone).date().isoformat() if value else None
    result['full_range_available']=bool(result['start_date'] and result['end_date'])
    return result


class StrategyBrowser:
    def __init__(self,runs,datasets,analyses):
        self.runs,self.datasets,self.analyses=runs,datasets,analyses
        self.lock=Lock()
        with runs.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS library_datasets (
                    id TEXT PRIMARY KEY,strategy_id TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS library_runs (
                    run_id TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
                    group_id TEXT NOT NULL REFERENCES library_datasets(id),
                    phase TEXT NOT NULL,parent_id TEXT,comparison_key TEXT NOT NULL,
                    prop_id TEXT,prop_status TEXT,historical_net TEXT,payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS library_dataset_runs ON library_runs(group_id);
                CREATE INDEX IF NOT EXISTS library_oos_parent ON library_runs(parent_id,group_id,comparison_key,phase);
            ''')

    def sync(self):
        with self.lock:
            sources=None
            while True:
                with self.runs.connect() as db:
                    missing=db.execute('''SELECT r.id,r.manifest,
                        (SELECT t.optimization_id FROM optimization_trials t
                         WHERE json_extract(t.payload,'$.run_id')=r.id ORDER BY t.rowid LIMIT 1)
                        FROM runs r LEFT JOIN library_runs i ON i.run_id=r.id
                        WHERE i.run_id IS NULL LIMIT 500''').fetchall()
                if not missing:break
                if sources is None:
                    sources={d['id']:d for d in self.datasets.list()}
                    by_content={(d['sha256'],d['source_timezone']):d for d in sources.values()}
                indexed=[];grouped={}
                for id,raw,batch in missing:
                    record=json.loads(raw);meta=record['run_metadata'];saved=meta['dataset'];strategy=meta['strategy']['id']
                    live=sources.get(saved['id']) or by_content.get((saved['sha256'],saved['source_timezone']))
                    if live and (live['sha256'],live['source_timezone'])!=(saved['sha256'],saved['source_timezone']):live=None
                    # Full dates come only from full dataset metadata. IS run
                    # selection and research-plan bounds are never substitutes.
                    snapshot=full_source(live or meta.get('full_dataset') or saved)
                    instrument=meta.get('instrument',{}).get('symbol')
                    if instrument is None:instrument=(live or {}).get('symbol','')
                    instrument=(instrument or '').strip().upper()
                    group=digest([strategy,saved['sha256'],saved['source_timezone'],instrument])
                    group_data=dict(id=group,strategy_id=strategy,instrument=instrument or 'Unspecified',dataset=snapshot)
                    research=meta.get('research',{});phase=research.get('phase','legacy')
                    comparison=digest([meta['strategy'].get('source_sha256'),meta['strategy']['parameters'],record['execution_settings'],research.get('plan')])
                    automatic=meta.get('automatic_prop_analysis',{});prop_id=automatic.get('id')
                    summary=self.analyses.summary(prop_id) if prop_id else None
                    status=summary['status'] if summary else 'deleted' if prop_id else None
                    net=summary.get('historical_net') if summary else None
                    payload=dict(id=id,created_at_utc=record['created_at_utc'],strategy_id=strategy,
                                 dataset_id=saved['id'],dataset_name=saved['name'],parameters=meta['strategy']['parameters'],
                                 execution_settings=record['execution_settings'],selection=meta.get('selection',{}),
                                 research_phase=phase,parent_id=research.get('parent_run_id'),
                                 metrics={k:record['summary'].get(k) for k in METRICS},batch_id=batch,
                                 prop_model=automatic.get('model_version'))
                    if group not in grouped or snapshot['full_range_available']:
                        grouped[group]=(group,strategy,json.dumps(group_data),snapshot['full_range_available'])
                    indexed.append((id,group,phase,research.get('parent_run_id'),comparison,prop_id,status,json.dumps(net) if net is not None else None,json.dumps(payload),id))
                with self.runs.connect() as db:
                    db.executemany('INSERT OR IGNORE INTO library_datasets VALUES (?,?,?)',[row[:3] for row in grouped.values()])
                    db.executemany('UPDATE library_datasets SET payload=? WHERE id=?',[(row[2],row[0]) for row in grouped.values() if row[3]])
                    db.executemany('INSERT OR IGNORE INTO library_runs SELECT ?,?,?,?,?,?,?,?,? WHERE EXISTS(SELECT 1 FROM runs WHERE id=?)',indexed)
            # Explicit report deletion must invalidate cached scores and links.
            with self.analyses.connect() as db:statuses=dict(db.execute('SELECT id,status FROM analyses'))
            with self.runs.connect() as db:
                props=db.execute('SELECT run_id,prop_id,prop_status FROM library_runs WHERE prop_id IS NOT NULL').fetchall()
                for run_id,prop_id,previous in props:
                    current=statuses.get(prop_id,'deleted')
                    if current!=previous:
                        summary=self.analyses.summary(prop_id) if current!='deleted' else None
                        net=summary.get('historical_net') if summary else None
                        db.execute('UPDATE library_runs SET prop_status=?,historical_net=? WHERE run_id=?',(summary['status'] if summary else current,json.dumps(net) if net is not None else None,run_id))

    def strategies(self):
        self.sync()
        registered={s['id']:s for s in list_strategies()}
        with self.runs.connect() as db:
            stats={id:(groups,count) for id,groups,count in db.execute('''SELECT d.strategy_id,COUNT(DISTINCT d.id),COUNT(*)
                FROM library_datasets d JOIN library_runs r ON r.group_id=d.id GROUP BY d.strategy_id''')}
        return dict(items=[dict(id=id,name=id.replace('_',' ').title(),registered=id in registered,
                                datasets=stats.get(id,(0,0))[0],reports=stats.get(id,(0,0))[1])
                           for id in sorted(registered.keys()|stats.keys())])

    def dataset_groups(self,strategy,offset,limit):
        self.sync()
        if strategy not in {s['id'] for s in self.strategies()['items']}:return None
        with self.runs.connect() as db:
            total=db.execute('SELECT COUNT(DISTINCT d.id) FROM library_datasets d JOIN library_runs r ON r.group_id=d.id WHERE d.strategy_id=?',(strategy,)).fetchone()[0]
            rows=db.execute('''SELECT d.payload,COUNT(*),SUM(r.phase='is'),SUM(r.phase='oos')
                FROM library_datasets d JOIN library_runs r ON r.group_id=d.id WHERE d.strategy_id=?
                GROUP BY d.id ORDER BY json_extract(d.payload,'$.instrument') COLLATE NOCASE,
                json_extract(d.payload,'$.dataset.start_date'),d.id LIMIT ? OFFSET ?''',(strategy,limit,offset)).fetchall()
        available={(d['sha256'],d['source_timezone']):d['id'] for d in self.datasets.list()}
        items=[]
        for raw,count,insample,oos in rows:
            item=json.loads(raw);source=item['dataset'];item.update(reports=count,is_reports=insample,oos_reports=oos,
                available_dataset_id=available.get((source['sha256'],source['source_timezone'])))
            items.append(item)
        return dict(strategy_id=strategy,items=items,total=total,offset=offset,limit=limit)

    @staticmethod
    def public(row):
        payload=json.loads(row['payload']);payload['historical_net']=json.loads(row['historical_net']) if row['historical_net'] is not None else None
        payload['prop_id']=row['prop_id'];payload['prop_status']=row['prop_status']
        return payload

    def reports(self,strategy,group,offset,limit,sort,direction):
        self.sync()
        with self.runs.connect() as db:
            db.row_factory=sqlite3.Row
            found=db.execute('SELECT payload FROM library_datasets WHERE id=? AND strategy_id=?',(group,strategy)).fetchone()
            if not found:return None
            total_runs=db.execute('SELECT COUNT(*) FROM library_runs WHERE group_id=?',(group,)).fetchone()[0]
            if not total_runs:return None
            db.create_collation('EXACT_DECIMAL',lambda a,b:(numeric(a)>numeric(b))-(numeric(a)<numeric(b)))
            parameter_rows=db.execute('''SELECT p.key,COUNT(DISTINCT (CASE WHEN p.type IN ('true','false') THEN 'boolean:'||p.type ELSE CAST(p.value AS TEXT) END) COLLATE EXACT_DECIMAL),COUNT(*)
                FROM library_runs r,json_each(json_extract(r.payload,'$.parameters')) p
                WHERE r.group_id=? GROUP BY p.key ORDER BY p.key''',(group,)).fetchall()
            parameters=[r[0] for r in parameter_rows];varying=[r[0] for r in parameter_rows if r[1]>1 or r[2]<total_runs]
            # Join only explicit, matching IS parents. A deleted/mismatched
            # parent leaves an honest OOS-only row, never guessed IS metrics.
            child="c.group_id=i.group_id AND c.phase='oos' AND c.parent_id=i.run_id AND c.comparison_key=i.comparison_key AND i.phase='is'"
            primary="i.group_id=? AND (i.phase!='oos' OR NOT EXISTS(SELECT 1 FROM library_runs p WHERE p.run_id=i.parent_id AND p.group_id=i.group_id AND p.comparison_key=i.comparison_key AND p.phase='is'))"
            cte=f'''WITH entries AS (SELECT i.*,
                (SELECT c.payload FROM library_runs c WHERE {child} ORDER BY json_extract(c.payload,'$.created_at_utc') DESC,c.run_id LIMIT 1) AS child_payload,
                (SELECT c.historical_net FROM library_runs c WHERE {child} ORDER BY json_extract(c.payload,'$.created_at_utc') DESC,c.run_id LIMIT 1) AS child_net
                FROM library_runs i WHERE {primary})'''
            args=[]
            if sort=='created_at_utc':expression="json_extract(payload,'$.created_at_utc')";collation='BINARY'
            elif sort.startswith('param.') and sort[6:] in parameters:
                expression='json_extract(payload,?)';args=['$.parameters.'+sort[6:]];collation='EXACT_DECIMAL'
            elif sort in {f'{phase}.{metric}' for phase in ('is','oos') for metric in (*METRICS,'historical_net')}:
                phase,metric=sort.split('.')
                if metric=='historical_net':expression="CASE WHEN phase='is' THEN historical_net END" if phase=='is' else "CASE WHEN phase='oos' THEN historical_net ELSE child_net END"
                elif phase=='is':expression="CASE WHEN phase='is' THEN json_extract(payload,?) END";args=['$.metrics.'+metric]
                else:expression="CASE WHEN phase='oos' THEN json_extract(payload,?) ELSE json_extract(child_payload,?) END";args=['$.metrics.'+metric]*2
                collation='EXACT_DECIMAL'
            else:raise ValueError('Unknown run sort column.')
            if direction not in ('asc','desc'):raise ValueError('Sort direction must be asc or desc.')
            total=db.execute(cte+' SELECT COUNT(*) FROM entries',(group,)).fetchone()[0]
            order=f'({expression} IS NULL) ASC,CAST({expression} AS TEXT) COLLATE {collation} {direction.upper()},run_id ASC'
            rows=db.execute(cte+' SELECT * FROM entries ORDER BY '+order+' LIMIT ? OFFSET ?',(group,*args,*args,limit,offset)).fetchall()
            items=[]
            for row in rows:
                parent=self.public(row);children=[]
                if row['phase']=='is':
                    children=[self.public(c) for c in db.execute("SELECT * FROM library_runs WHERE group_id=? AND phase='oos' AND parent_id=? AND comparison_key=? ORDER BY json_extract(payload,'$.created_at_utc') DESC,run_id",(group,row['run_id'],row['comparison_key']))]
                items.append(dict(id=parent['id'],parameters=parent['parameters'],created_at_utc=parent['created_at_utc'],
                                  phase=row['phase'],insample=parent if row['phase']=='is' else None,
                                  oos=children if row['phase']=='is' else [parent] if row['phase']=='oos' else [],
                                  legacy=parent if row['phase']=='legacy' else None))
        return dict(group=json.loads(found[0]),items=items,total=total,offset=offset,limit=limit,
                    parameter_columns=parameters,varying_parameters=varying,sort=sort,direction=direction)
