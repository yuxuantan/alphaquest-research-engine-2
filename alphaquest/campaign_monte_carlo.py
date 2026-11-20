"""Retrospective, full-period P&L sanity checks over frozen IS + OOS reports.

Uses the normal AnalysisStore catalogue, worker, cancellation and sealed artifacts.
It neither replays prices nor changes IS selections or OOS verdicts.
"""
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import shutil
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

import numpy as np
from fastapi import APIRouter, Request, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from .worker_limits import DEFAULT_WORKERS, MAX_WORKERS

from .campaign_broad import invoke
from .campaign_oos import context, results
from .decimal_math import add, subtract
from .market_equity import equity_rows, SourceDate
from .optimization_cache import artifacts, digest


POLICY = dict(version='campaign-full-period-monte-carlo-v2', paths=5000, seed=42,
              block_lengths=[5,20], minimum_observed_days=100, minimum_closed_trades=100,
              profit_quantile=.05, drawdown_quantile=.95,
              method='stationary circular daily P&L bootstrap with replacement',
              quantile_method='linear', units='account currency units; unchanged frozen size',
              day_boundary='last observed bar of source-local calendar date')
RULES = [
    'At least 100 observed source dates and 100 closed trades across IS + OOS.',
    '5th-percentile full-period net profit > 0 under both 5-day and 20-day mean block lengths.',
]
LIMITATIONS = ('Retrospective sanity check using already observed IS and OOS; not another holdout or proof of a future edge. '
              'Bootstrap assumes the pooled daily P&L is representative and sufficiently stationary. '
              'Daily-close drawdown excludes intraday excursions and differs from native bar-close MTM drawdown. '
              'All observed source dates, including dates without trades, are retained; absent dates are not invented. '
              'Paths use fixed frozen size, existing net costs, no compounding, margin rules or prop-account rules. '
              'No additional costs are deducted. Results are conditional on the saved observations; Monte Carlo error is not future uncertainty.')
DIAGNOSTICS = ('Mean/median profit and median/95th-percentile drawdown are diagnostics, not pass/fail gates. '
               'The historical drawdown percentile is the percentage of simulated drawdowns below it, with half weight for ties. '
               'A low percentile describes a favorable historical drawdown within this model; it is not a p-value or proof of selection luck. '
               'Drawdown/account-risk limits belong in subsequent sizing and account assessment.')
SAMPLING_FIELDS = ('paths','seed','block_lengths','method','units','day_boundary')


def summarize(observed, totals, losses, block):
    """One assessment contract for fresh simulations and sealed saved outcomes."""
    totals,losses = np.asarray(totals,dtype=np.float64),np.asarray(losses,dtype=np.float64)
    if (len(totals)!=POLICY['paths'] or len(losses)!=POLICY['paths']
            or not np.isfinite(totals).all() or not np.isfinite(losses).all() or np.any(losses<0)):
        raise ValueError('Incomplete or invalid saved Monte Carlo path outcomes.')
    lower = float(np.quantile(totals,POLICY['profit_quantile'],method=POLICY['quantile_method']))
    probability = float(np.mean(totals>0))
    historical_dd = observed['daily_close_max_drawdown']
    upper = float(np.quantile(losses,POLICY['drawdown_quantile'],method=POLICY['quantile_method']))
    checks = [dict(label='Positive lower-tail net profit',passed=lower>0,actual=lower,required='5th percentile > 0')]
    return dict(mean_block_days=block,net_profit_p05=lower,net_profit_mean=float(np.mean(totals)),
                net_profit_median=float(np.median(totals)),max_drawdown_median=float(np.median(losses)),
                max_drawdown_p95=upper,historical_drawdown_percentile_pct=float(100*(np.mean(losses<historical_dd)+.5*np.mean(losses==historical_dd))),
                max_drawdown_p95_over_observed=upper/historical_dd if historical_dd>0 else None,
                profitable_paths_pct=probability*100,
                profitable_paths_mc_se_pp=100*(probability*(1-probability)/POLICY['paths'])**.5,
                checks=checks,qualifies=lower>0)


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS campaign_sanity_jobs (analysis_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, oos_job_id TEXT NOT NULL)')


def drawdowns(paths):
    """Include starting P&L zero when finding additive daily-close drawdowns."""
    equity = np.cumsum(paths, axis=1)
    peaks = np.maximum(0, np.maximum.accumulate(equity, axis=1))
    return equity[:,-1], np.max(peaks-equity, axis=1)


def stationary_indices(rng, count, days, mean_block):
    positions = np.arange(days)[None,:]
    restart = rng.random((count,days)) < 1/mean_block
    restart[:,0] = True
    last = np.maximum.accumulate(np.where(restart,positions,0),axis=1)
    starts = rng.integers(0,days,size=(count,days))
    return (np.take_along_axis(starts,last,axis=1)+positions-last) % days


def _path_chunk(value):
    pnl,state,count,block,marker=value
    if Path(marker).exists():raise RuntimeError('Monte Carlo stopped')
    rng=np.random.Generator(np.random.PCG64());rng.bit_generator.state=state
    indices=stationary_indices(rng,count,len(pnl),block)
    net,dd=drawdowns(pnl[indices])
    if not np.isfinite(net).all() or not np.isfinite(dd).all():raise ValueError('Simulation arithmetic exceeded supported finite values.')
    return net.tolist(),dd.tolist()


def assess(daily, trades, *, progress=lambda *args:None):
    """Bounded-memory simulation; same seeded schedules for every candidate."""
    pnl = np.asarray([float(row['net_pnl']) for row in daily],dtype=np.float64)
    if not len(pnl) or not np.isfinite(pnl).all():raise ValueError('Invalid saved daily P&L.')
    historical_net, historical_dd = drawdowns(pnl[None,:])
    observed = dict(days=len(pnl),closed_trades=trades,net_profit=float(historical_net[0]),
                    daily_close_max_drawdown=float(historical_dd[0]))
    evidence = len(pnl)>=POLICY['minimum_observed_days'] and trades>=POLICY['minimum_closed_trades']
    scenarios, paths = [], []
    for block in POLICY['block_lengths']:
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([POLICY['seed'],block])))
        totals, losses = [], []
        from .prop.path_parallel import available
        if available():
            from .prop.parallel import map_reported
            from copy import deepcopy
            with TemporaryDirectory(prefix='aq-monte-carlo-') as temporary:
                marker=Path(temporary)/'stop';tasks=[]
                for start in range(0,POLICY['paths'],128):
                    count=min(128,POLICY['paths']-start)
                    progress(block,0,POLICY['paths'])
                    tasks.append((pnl,deepcopy(rng.bit_generator.state),count,block,str(marker)))
                    # Advance the identical original stream; children calculate
                    # each batch from its captured state, regardless of cores.
                    stationary_indices(rng,count,len(pnl),block)
                completed=0
                def arrived(value):
                    nonlocal completed
                    completed+=len(value[0])
                values=map_reported(_path_chunk,tasks,
                    checkpoint=lambda:progress(block,completed,POLICY['paths']),
                    notify=lambda *args:None,cancel=marker.touch,on_result=arrived)
                for net,dd in values:totals.extend(net);losses.extend(dd)
        else:
            for start in range(0,POLICY['paths'],128):
                count = min(128,POLICY['paths']-start)
                progress(block,start,POLICY['paths'])
                indices = stationary_indices(rng,count,len(pnl),block)
                net, dd = drawdowns(pnl[indices])
                if not np.isfinite(net).all() or not np.isfinite(dd).all():raise ValueError('Simulation arithmetic exceeded supported finite values.')
                totals.extend(net.tolist());losses.extend(dd.tolist())
        progress(block,POLICY['paths'],POLICY['paths'])
        scenario=summarize(observed,totals,losses,block)
        scenario['qualifies'] = evidence and scenario['qualifies']
        scenarios.append(scenario)
        paths.extend(dict(mean_block_days=block,path=i+1,net_profit=net,max_drawdown=dd) for i,(net,dd) in enumerate(zip(totals,losses)))
    return dict(observed=observed,evidence_passed=evidence,scenarios=scenarios,
                qualifies=evidence and all(s['qualifies'] for s in scenarios)), paths


def capture_period(runs, report, phase, plan):
    folder = runs.root/report['id']
    previous = Decimal(report['summary']['initial_capital'])
    dates = SourceDate(report['run_metadata']['dataset']['source_timezone'])
    closes = {}
    for point in equity_rows(folder,report['market_benchmark']):
        if int(point['bar_number']):closes[dates(point['timestamp_utc'])]=Decimal(point['strategy_equity'])
    daily = []
    for day,equity in sorted(closes.items()):
        if not plan[phase+'_start']<=day<=plan[phase+'_end']:raise ValueError('Daily equity extends outside the frozen research window.')
        daily.append(dict(date=day,period=phase,net_pnl=str(subtract(equity,previous))))
        previous = equity
    expected = Decimal(report['summary']['total_net_pnl'])
    if not daily or subtract(previous,Decimal(report['summary']['initial_capital']))!=expected:
        raise ValueError('Daily equity does not reconcile to native net P&L.')
    trade_net, trade_count = Decimal(0), 0
    with (folder/report['artifacts']['trades_csv']).open(newline='') as stream:
        for row in csv.DictReader(stream):
            trade_net=add(trade_net,Decimal(row['net_pnl']));trade_count+=1
    if trade_net!=expected or trade_count!=report['summary']['trades_taken']:
        raise ValueError('Saved trades do not reconcile to native net P&L and trade count.')
    return daily,trade_count,dict(run_id=report['id'],manifest_sha256=digest(report),artifacts=artifacts(runs.root,report))


def source_snapshot(request, workflow_id, job_id):
    saved,_,identity,job,_ = context(request,workflow_id,job_id)
    if not job or job['status']!='complete':raise ValueError('Complete OOS before running the final Monte Carlo sanity check.')
    outcome = results(request,workflow_id,job_id)
    if any(i['status']=='unavailable' for i in outcome['items']):raise ValueError('OOS evidence is unavailable or changed; Monte Carlo cannot qualify it.')
    plan = saved['declaration']['plan']
    if plan['is_end']>=plan['oos_start']:raise ValueError('IS and OOS windows must be ordered and non-overlapping.')
    candidates = []
    for item in outcome['items']:
        if not item['qualifies']:continue
        daily, count, proofs = [], 0, []
        for phase,id in [('is',item['is_run_id']),('oos',item['run_id'])]:
            report = request.app.state.runs.get(id)
            if report['run_metadata']['strategy']['parameters']!=item['parameters']:raise ValueError('IS/OOS parameters differ.')
            rows,n,proof = capture_period(request.app.state.runs,report,phase,plan)
            daily.extend(rows);count+=n;proofs.append(proof)
        if len({r['date'] for r in daily})!=len(daily):raise ValueError('IS/OOS daily observations overlap.')
        candidates.append(dict(candidate=item['trial'],broad_trial=item['broad_trial'],narrow_trial=item['narrow_trial'],
                               parameters=item['parameters'],daily=daily,closed_trades=count,sources=proofs,
                               oos_admission=item['admission']))
    if not candidates:raise ValueError('No verified OOS-passing configurations are available.')
    return dict(workflow_id=workflow_id,oos_job_id=job_id,frozen_identity=identity,policy=POLICY,rules=RULES,
                limitations=LIMITATIONS,diagnostics=DIAGNOSTICS,plan=plan,unobserved_split_gap_calendar_days=(date.fromisoformat(plan['oos_start'])-date.fromisoformat(plan['is_end'])).days-1,
                numpy_version=np.__version__,calculation_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),candidates=candidates)


def reusable_report(store, workflow_id, job_id, snapshot):
    """Reuse only a sealed population bound to exactly the same native evidence."""
    with store.connect() as db:
        ids=[r[0] for r in db.execute("SELECT a.id FROM analyses a JOIN campaign_sanity_jobs c ON c.analysis_id=a.id WHERE c.workflow_id=? AND c.oos_job_id=? AND a.status='complete' ORDER BY a.created DESC",(workflow_id,job_id))]
    for id in ids:
        if not store.fingerprint(id):raise ValueError('Saved Monte Carlo population failed its integrity check.')
        report=json.loads((store.root/id/'report.json').read_text())
        if report['policy'].get('version') not in ('campaign-full-period-monte-carlo-v1',POLICY['version']):continue
        if any(report['policy'].get(k)!=POLICY[k] for k in SAMPLING_FIELDS):continue
        if any(report.get(k)!=snapshot[k] for k in ('frozen_identity','plan')):continue
        fields=('candidate','broad_trial','narrow_trial','parameters','closed_trades','sources','oos_admission')
        if ([{k:c[k] for k in fields} for c in report['candidates']]
                != [{k:c[k] for k in fields} for c in snapshot['candidates']]):continue
        return report
    return None


def reassess_saved(store, report, staged, checkpoint):
    """No new random draws: copy immutable input/outcome files and assess them."""
    id=report['id'];fingerprint=store.fingerprint(id)
    if not fingerprint:raise ValueError('Saved Monte Carlo population failed its integrity check.')
    groups={(c['candidate'],b):([],[]) for c in report['candidates'] for b in POLICY['block_lengths']}
    with (store.root/id/'paths.csv').open(newline='') as stream:
        for index,row in enumerate(csv.DictReader(stream)):
            if index%1000==0:checkpoint()
            key=(int(row['candidate']),int(row['mean_block_days']))
            if key not in groups:raise ValueError('Saved Monte Carlo path has unexpected membership.')
            totals,losses=groups[key]
            if int(row['path'])!=len(totals)+1:raise ValueError('Saved Monte Carlo paths are missing or duplicated.')
            totals.append(float(row['net_profit']));losses.append(float(row['max_drawdown']))
    output=[]
    for candidate in report['candidates']:
        observed=candidate['observed']
        evidence=observed['days']>=POLICY['minimum_observed_days'] and observed['closed_trades']>=POLICY['minimum_closed_trades']
        scenarios=[summarize(observed,*groups[(candidate['candidate'],b)],b) for b in POLICY['block_lengths']]
        for scenario in scenarios:scenario['qualifies']=evidence and scenario['qualifies']
        output.append(dict(**{k:v for k,v in candidate.items() if k not in ('evidence_passed','scenarios','qualifies')},
                           evidence_passed=evidence,scenarios=scenarios,qualifies=evidence and all(s['qualifies'] for s in scenarios)))
    for name in ('daily.csv','paths.csv'):
        shutil.copyfile(store.root/id/name,staged/name)
        if sha256((staged/name).read_bytes()).hexdigest()!=report['files'][name]['sha256']:raise ValueError('Saved Monte Carlo file changed during capture.')
    if store.fingerprint(id)!=fingerprint:raise ValueError('Saved Monte Carlo population changed during reassessment.')
    return output


def submit(request, workflow_id, job_id, workers=DEFAULT_WORKERS):
    store = request.app.state.prop_analyses
    snapshot = source_snapshot(request,workflow_id,job_id)
    key = digest(snapshot)
    with store.lock:
        with store.connect() as db:
            old = db.execute("SELECT a.id,a.status FROM analyses a JOIN campaign_sanity_jobs c ON c.analysis_id=a.id WHERE a.request_hash=? AND a.status IN ('queued','running','complete') ORDER BY a.created DESC LIMIT 1",(key,)).fetchone()
            if old:
                if old[1]=='complete' and not store.fingerprint(old[0]):raise ValueError('Saved Monte Carlo artifacts changed; retained results cannot be silently replaced.')
                return store.get(old[0])
            reuse=reusable_report(store,workflow_id,job_id,snapshot)
            id=uuid4().hex
            db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(id,key,snapshot['candidates'][0]['sources'][1]['run_id'],datetime.now(timezone.utc).isoformat(),'queued','Queued reassessment of saved Monte Carlo paths' if reuse else 'Queued full-period Monte Carlo',None))
            db.execute('INSERT INTO campaign_sanity_jobs VALUES (?,?,?)',(id,workflow_id,job_id))
            db.executemany('INSERT INTO analysis_sources VALUES (?,?)',[(id,source) for source in sorted({s['run_id'] for c in snapshot['candidates'] for s in c['sources']})])
            db.execute('INSERT INTO phase_analysis_control(analysis_id) VALUES (?)',(id,))
        with store.connect() as db:db.execute('INSERT INTO analysis_compute VALUES (?,?)',(id,workers))
        store.worker.submit(run,store,id,snapshot,reuse)
    return store.get(id)


def run(store, id, snapshot, reuse=None):
    from .prop.store import AnalysisCancelled, seal_report, sealed_checks
    from .prop.adapter import canonical
    def checkpoint():
        with store.connect() as db:
            if db.execute('SELECT stop_requested FROM phase_analysis_control WHERE analysis_id=?',(id,)).fetchone()[0]:raise AnalysisCancelled()
    try:
        checkpoint();store._update(id,'running','Preparing full-period daily P&L')
        with TemporaryDirectory(prefix='.pending-',dir=store.root) as temp:
            staged=Path(temp)/'report';staged.mkdir()
            output=[]
            if reuse:
                store._update(id,'running','Applying current policy to saved Monte Carlo paths; no new simulation')
                output=reassess_saved(store,reuse,staged,checkpoint)
            else:
                with store.connect() as db:compute=db.execute('SELECT workers FROM analysis_compute WHERE analysis_id=?',(id,)).fetchone()
                with store.runtime.activate(workers=compute[0] if compute else None):
                    output=simulate_candidates(store,id,snapshot,staged,checkpoint)
            result=dict(**{k:v for k,v in snapshot.items() if k!='candidates'},kind='campaign_monte_carlo',candidates=output,
                        passed=sum(c['qualifies'] for c in output),total=len(output))
            if reuse:
                result['reused_population']=dict(analysis_id=reuse['id'],policy=reuse['policy'],
                    calculation_sha256=reuse['calculation_sha256'],numpy_version=reuse['numpy_version'],
                    files={k:reuse['files'][k] for k in ('daily.csv','paths.csv')})
            # Cancel and publication serialize through the same existing control lock.
            with store.lock:
                checkpoint();seal_report(staged,result,id,store.get(id)['created']);staged.rename(store.root/id)
                with store.connect() as db:
                    db.execute('INSERT INTO analysis_report_checks VALUES (?,?)',(id,canonical(sealed_checks(store.root/id))))
                    db.execute("UPDATE analyses SET status='complete',progress=? WHERE id=?",(f"Final sanity check complete · {result['passed']}/{result['total']} passed",id))
    except AnalysisCancelled:store._update(id,'cancelled','Monte Carlo stopped; rerun uses the same fixed seed and policy.')
    except Exception as exc:store._update(id,'error','Monte Carlo failed',f'{type(exc).__name__}: {exc}')


def simulate_candidates(store,id,snapshot,staged,checkpoint):
    output=[]
    with (staged/'daily.csv').open('w',newline='') as daily_file,(staged/'paths.csv').open('w',newline='') as paths_file:
        daily_writer=csv.DictWriter(daily_file,fieldnames=['candidate','date','period','net_pnl']);daily_writer.writeheader()
        paths_writer=csv.DictWriter(paths_file,fieldnames=['candidate','mean_block_days','path','net_profit','max_drawdown']);paths_writer.writeheader()
        for index,candidate in enumerate(snapshot['candidates'],1):
            def progress(block,done,total):
                checkpoint();store._update(id,'running',f"Candidate {index}/{len(snapshot['candidates'])} · mean block {block} days · {done}/{total} paths")
            measured,paths=assess(candidate['daily'],candidate['closed_trades'],progress=progress)
            daily_writer.writerows(dict(candidate=candidate['candidate'],**r) for r in candidate['daily'])
            paths_writer.writerows(dict(candidate=candidate['candidate'],**r) for r in paths)
            output.append(dict(**{k:v for k,v in candidate.items() if k!='daily'},**measured))
    return output


def detail(request, workflow_id, job_id):
    # Membership validation does not read large source artifacts or rerun calculations.
    _,_,_,oos,_ = context(request,workflow_id,job_id)
    store=request.app.state.prop_analyses
    with store.connect() as db:
        db.row_factory=sqlite3.Row
        rows=db.execute('SELECT a.* FROM analyses a JOIN campaign_sanity_jobs c ON c.analysis_id=a.id WHERE c.workflow_id=? AND c.oos_job_id=? ORDER BY a.created DESC',(workflow_id,job_id)).fetchall()
    job=dict(rows[0]) if rows else None
    report=None
    if job and job['status']=='complete':
        if not store.fingerprint(job['id']):raise ValueError('Saved Monte Carlo report integrity check failed.')
        report=json.loads((store.root/job['id']/'report.json').read_text())
    return dict(policy=POLICY,rules=RULES,limitations=LIMITATIONS,diagnostics=DIAGNOSTICS,job=job,report=report,
                default_workers=DEFAULT_WORKERS,max_workers=MAX_WORKERS,oos_complete=bool(oos and oos['status']=='complete'),history=[dict(r) for r in rows])


class Launch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    job_id: UUID
    workers: StrictInt = Field(default=DEFAULT_WORKERS,ge=1,le=MAX_WORKERS)


router=APIRouter()


@router.get('/api/campaign-workflows/{workflow_id}/oos/monte-carlo')
async def page(workflow_id: UUID, request: Request, job: UUID):
    return await invoke(detail,request,workflow_id.hex,job.hex)


@router.post('/api/campaign-workflows/{workflow_id}/oos/monte-carlo/run',status_code=202)
async def launch(workflow_id: UUID, body: Launch, request: Request):
    return await invoke(submit,request,workflow_id.hex,body.job_id.hex,body.workers)


@router.get('/api/campaign-workflows/{workflow_id}/oos/monte-carlo/jobs/{analysis_id}/download')
async def download(workflow_id: UUID, analysis_id: UUID, request: Request, format: str=Query('json',pattern='^(json|zip|daily|paths)$')):
    store=request.app.state.prop_analyses
    def checked_path():
        with store.connect() as db:
            if not db.execute('SELECT 1 FROM campaign_sanity_jobs WHERE workflow_id=? AND analysis_id=?',(workflow_id.hex,analysis_id.hex)).fetchone():raise KeyError('Monte Carlo job not found in this workflow.')
        record=store.get(analysis_id.hex)
        if record['status']!='complete' or not store.fingerprint(analysis_id.hex):raise ValueError('No intact completed Monte Carlo result is available.')
        return store.root/analysis_id.hex/{'json':'report.json','zip':'analysis.zip','daily':'daily.csv','paths':'paths.csv'}[format]
    path=await invoke(checked_path)
    return FileResponse(path,filename='monte-carlo-'+analysis_id.hex+'-'+path.name)
