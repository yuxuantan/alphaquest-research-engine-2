"""Display reuse must preserve exact ordering and never become selection authority."""
import hashlib
import json
import os
import sqlite3
from decimal import Decimal

import pytest

from alphaquest import artifact_reads, campaign_narrow
from alphaquest.narrow_read_cache import AssessmentView, ViewChanged
from test_campaign_narrow import narrow_workflow, narrow_start
from test_research_workflow import client


def test_request_hash_reuse_and_mid_request_changes(tmp_path, monkeypatch):
    path=tmp_path/'evidence.csv';path.write_bytes(b'original')
    original=artifact_reads.file_digest;calls=[]
    def counted(source,*args):
        calls.append(source.name);return original(source,*args)
    monkeypatch.setattr(artifact_reads,'file_digest',counted)
    expected=hashlib.sha256(b'original').hexdigest()
    with artifact_reads.verified_reads():
        assert artifact_reads.read_hash(path)==expected
        with artifact_reads.verified_reads():assert artifact_reads.read_hash(path)==expected
    assert len(calls)==1
    with artifact_reads.verified_reads():assert artifact_reads.read_hash(path)==expected
    assert len(calls)==2
    with pytest.raises(ValueError,match='changed during verification'):
        with artifact_reads.verified_reads():
            artifact_reads.read_hash(path)
            saved=path.stat();path.write_bytes(b'modified')
            os.utime(path,ns=(saved.st_atime_ns,saved.st_mtime_ns))
            artifact_reads.read_hash(path)


def test_compact_order_is_global_exact_decimal_null_last_and_stable(client):
    """Synthetic table fixture: no invented backtest or qualification evidence."""
    store=client.app.state.optimizations
    job=dict(id='f'*32,completed_trials=65,total_trials=65,status='complete',
             axes={'ordered':[1,2]},metric_columns=['total_net_pnl'])
    rows=[dict(trial=i,run_id=f'{i:032x}',parameters={'ordered':i%2},
               metrics={'total_net_pnl':None if i==65 else '1.00000000000000000000000000'+str(i%9)})
          for i in range(1,66)]
    with store.runs.connect() as db:
        db.execute('INSERT INTO optimizations VALUES (?,?,?)',(job['id'],'synthetic-table-only',json.dumps(job)))
        db.executemany('INSERT INTO optimization_trials VALUES (?,?,?)',
                       [(job['id'],row['trial'],json.dumps(row)) for row in rows])
    for direction,sign in [('asc',1),('desc',-1)]:
        expected=sorted(rows,key=lambda row:(row['metrics']['total_net_pnl'] is None,
            Decimal(row['metrics']['total_net_pnl'] or 0)*sign,row['trial']))
        for offset,limit in [(0,65),(0,50),(50,15)]:
            result=store.page(job,'total_net_pnl',direction,offset,limit,0,order_only=True)
            assert result['trials']==[row['trial'] for row in expected[offset:offset+limit]]
            assert result['trials']==[row['trial'] for row in store.page(job,'total_net_pnl',direction,offset,limit,0)['items']]
    with pytest.raises(ValueError):store.page(job,'SQL injection','asc',0,50,0,order_only=True)


def test_verified_views_exact_order_invalidation_and_selection_authority(client, monkeypatch):
    _,workflow,_=narrow_workflow(client)
    prefix='/api/campaign-workflows/'+workflow['id']
    job=narrow_start(client,prefix,1);runs=client.app.state.runs
    params=dict(broad_trial=1,limit=100)
    original=campaign_narrow.assessment;calls=[]
    def counted(*args,**kwargs):
        calls.append(args[1]['trial']);return original(*args,**kwargs)
    monkeypatch.setattr(campaign_narrow,'assessment',counted)
    hash_calls=[];hash_original=artifact_reads.file_digest
    def hash_counted(source,*args):
        hash_calls.append(source.name);return hash_original(source,*args)
    monkeypatch.setattr(artifact_reads,'file_digest',hash_counted)
    cold=client.get(prefix+'/narrow/results',params=params).json()
    assert len(calls)==4 and cold['view_token']
    assert hash_calls and len(hash_calls)==len(set(hash_calls))
    assert [r['trial'] for r in cold['items'] if r['selectable']]==[2,3]
    calls.clear()
    warm=client.get(prefix+'/narrow/results',params=params).json()
    assert warm==cold and calls==[]
    cache=runs.replay_cache
    with runs.connect() as db:
        manifests_before=db.execute('SELECT id,manifest FROM runs ORDER BY id').fetchall()
    with sqlite3.connect(cache.path) as db:
        name=next(name for name,metadata in db.execute('SELECT name,metadata FROM streams')
                  if json.loads(metadata).get('token')==cold['view_token'] and json.loads(metadata).get('trial')==4)
    (cache.root/name).write_bytes(b'corrupt disposable view')
    assert client.get(prefix+'/narrow/results',params=params).json()==cold
    assert calls==[4];calls.clear()
    with runs.connect() as db:
        assert db.execute('SELECT id,manifest FROM runs ORDER BY id').fetchall()==manifests_before
    for key in ['trial','run_id',*['param.'+p for p in job['axes']],*job['metric_columns']]:
        for direction in ('asc','desc'):
            expected=client.app.state.optimizations.page(job,key,direction,0,100,0)
            ordered=client.get(prefix+'/narrow/results',params=dict(params,sort=key,direction=direction,
                order_only=True,view_token=cold['view_token']))
            assert ordered.status_code==200,ordered.text
            assert ordered.json()['trials']==[r['trial'] for r in expected['items']]
            assert 'items' not in ordered.json()
    assert calls==[]
    assert client.get(prefix+'/narrow/results',params=dict(params,order_only=True)).status_code==409
    assert client.get(prefix+'/narrow/results',params=dict(params,order_only=True,view_token='stale')).status_code==409
    # Unrelated job activity does not evict an unchanged assessment view.
    with runs.connect() as db:
        db.execute('CREATE TABLE unrelated_progress (progress INTEGER)')
        db.execute('INSERT INTO unrelated_progress VALUES (1)')
    assert client.get(prefix+'/narrow/results',params=params).json()==cold
    assert calls==[]
    state=client.get(prefix+'/narrow',params={'broad_trial':1}).json()['state']
    selected=client.patch(prefix+'/narrow/selection',json=dict(broad_trial=1,job_id=job['id'],revision=state['revision'],trials=[2]))
    assert selected.status_code==200,selected.text
    calls.clear()
    overlay=client.get(prefix+'/narrow/results',params=params).json()
    assert calls==[] and overlay['items'][1]['selected'] and overlay['view_token']==cold['view_token']
    # Changing bytes with the same size and restored mtime still invalidates via ctime.
    row=cold['items'][1];path=runs.root/row['run_id']/'trades.csv'
    saved=path.stat();data=path.read_bytes();path.write_bytes(data.replace(b',',b';',1))
    os.utime(path,ns=(saved.st_atime_ns,saved.st_mtime_ns))
    stale=client.get(prefix+'/narrow/results',params=dict(params,order_only=True,view_token=cold['view_token']))
    assert stale.status_code==409
    changed=client.get(prefix+'/narrow/results',params=params).json()
    assert changed['view_token']!=cold['view_token'] and not changed['items'][1]['qualifies']
    rejected=client.post(prefix+'/narrow/confirm',json=dict(broad_trial=1,job_id=job['id'],revision=selected.json()['revision']))
    assert rejected.status_code==409
    # Trial payload changes and concurrent publications cannot reuse a stale snapshot.
    with runs.connect() as db:
        rows=[json.loads(raw) for raw, in db.execute('SELECT payload FROM optimization_trials WHERE optimization_id=? ORDER BY trial',(job['id'],))]
        altered=dict(rows[0],metrics=dict(rows[0]['metrics'],total_net_pnl='0'))
        db.execute('UPDATE optimization_trials SET payload=? WHERE optimization_id=? AND trial=1',(json.dumps(altered),job['id']))
    with pytest.raises(ViewChanged,match='trials changed'):
        AssessmentView(runs,job['id'],{},job=job,rows=rows)
    with AssessmentView(runs,job['id'],{}) as view:
        with runs.connect() as db:
            stress_id=rows[0]['screening']['cost_stress']['run_id']
            manifest=json.loads(db.execute('SELECT manifest FROM runs WHERE id=?',(stress_id,)).fetchone()[0])
            manifest['summary']['total_net_pnl']='123'
            db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(manifest),stress_id))
        with pytest.raises(ViewChanged):view.finish()
