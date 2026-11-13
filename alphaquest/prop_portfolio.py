"""Prop Sim portfolio mode on the existing AnalysisStore and saved parent records."""
from dataclasses import asdict
from datetime import date,datetime,timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID,uuid4

from fastapi import APIRouter,Request
from pydantic import BaseModel,ConfigDict,Field,StrictInt,StrictBool,model_validator,field_validator

from .campaign_broad import invoke
from .prop_sim import Selection,qualified,PROFILES
from .prop.sizing import SizingPolicy
from .prop.adapter import canonical
from .prop.store import AnalysisCancelled,seal_report,sealed_checks

router=APIRouter(prefix='/api/prop-sim/portfolio',tags=['Prop Sim portfolio'])


class PortfolioRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID
    selections:list[Selection]=Field(min_length=1,max_length=4)
    profile_id:str='lucidflex-50k'
    daily_loss_limit:StrictBool=True
    evaluation_consistency_percent:StrictInt=40
    evaluation_price:str='80.50'
    activation_fee:str='0'
    commission_per_mnq_side:str='0.50'
    monthly_cap:str='500'
    maximum_accounts:StrictInt=Field(default=2,ge=1,le=4)
    placements:list[str]=Field(default_factory=lambda:['separate','shared'])
    evaluation_policy:SizingPolicy
    funded_policy:SizingPolicy
    receipt_delay_calendar_days:StrictInt=Field(default=2,ge=0,le=365)
    is_start:str|None=None
    is_end:str|None=None
    oos_start:str|None=None
    oos_end:str|None=None

    @model_validator(mode='before')
    @classmethod
    def defaults(cls,value):
        if isinstance(value,dict) and value.get('evaluation_consistency_percent')==50 and 'evaluation_price' not in value:
            raise ValueError('Declare the actual purchase fee including the 50% consistency add-on.')
        if isinstance(value,dict) and value.get('profile_id') in PROFILES:
            value=dict(value);p=PROFILES[value['profile_id']]
            for name,key in [('evaluation_price','price'),('activation_fee','activation'),('commission_per_mnq_side','commission')]:value.setdefault(name,p[key])
        return value

    @field_validator('evaluation_price','activation_fee','monthly_cap','commission_per_mnq_side')
    @classmethod
    def amounts(cls,value):
        from .prop.cash_ledger import cash
        cash(value);return value

    @model_validator(mode='after')
    def valid(self):
        from .prop.cash_ledger import cash
        if self.profile_id not in PROFILES:raise ValueError('Unsupported prop account.')
        for key in ('evaluation_price','activation_fee','monthly_cap'):cash(getattr(self,key))
        if not Decimal(self.commission_per_mnq_side).is_finite() or not 0<=Decimal(self.commission_per_mnq_side)<=100:raise ValueError('Invalid MNQ commission.')
        if self.profile_id=='apex-50k-eod' and not self.daily_loss_limit:raise ValueError('Apex requires its DLL.')
        if self.profile_id=='lucidflex-50k' and Decimal(self.activation_fee)!=0:raise ValueError('LucidFlex activation is zero.')
        if self.evaluation_consistency_percent not in (40,50):raise ValueError('Evaluation consistency must be 40 or 50.')
        if self.profile_id=='apex-50k-eod' and self.evaluation_consistency_percent!=40:raise ValueError('The consistency add-on is LucidFlex only.')
        if not self.placements or set(self.placements)-{'separate','shared'} or len(set(self.placements))!=len(self.placements):raise ValueError('Select separate, shared, or both placements once.')
        for phase in ('evaluation','funded'):
            p=getattr(self,phase+'_policy');cap=PROFILES[self.profile_id]['limits'][phase]
            if p.maximum_contracts>cap or p.contracts is not None and p.contracts>cap:raise ValueError('Sizing exceeds the account phase ceiling.')
        if len({canonical(s.model_dump(mode='json')) for s in self.selections})!=len(self.selections):raise ValueError('Duplicate strategy configurations.')
        return self


def metadata(request,body):
    from .prop.portfolio_search import family
    from .prop.phase_lifecycle import instant,session_date
    sources=[qualified(request,s) for s in body.selections]
    native=[request.app.state.runs.get(s['source_backtest_id']) for s in sources]
    from .strategies.registry import get_strategy
    for record in native:
        if record['run_metadata']['strategy']['id']!='vwap_pullback_risk_sizing':raise ValueError('This native portfolio increment supports the VWAP strategy with causal stop admission.')
        params=get_strategy(record['run_metadata']['strategy']['id']).parameters(record['run_metadata']['strategy']['parameters'])
        if not params.use_eod_flat or params.use_vol_sizing:raise ValueError('Use EOD Flat must be enabled and strategy-local Vol Sizing disabled; portfolio policy owns quantity.')
    ids={r['run_metadata']['dataset']['id'] for r in native}
    if len(ids)!=1:raise ValueError('Portfolio comparisons require one synchronized saved NQ/MNQ dataset.')
    bounds={}
    for role in ('is','oos'):
        records=[request.app.state.runs.get(s['source_backtest_id' if role=='is' else 'oos_report_id']) for s in sources]
        first=max(max(s['plan'][role+'_start'],str(session_date(instant(r['period_start_utc'])))) for s,r in zip(sources,records))
        last=min(min(s['plan'][role+'_end'],str(session_date(instant(r['period_end_utc'])))) for s,r in zip(sources,records))
        start=getattr(body,role+'_start') or first;end=getattr(body,role+'_end') or last
        if date.fromisoformat(start).isoformat()!=start or date.fromisoformat(end).isoformat()!=end:raise ValueError('Use canonical ISO dates.')
        if not first<=start<=end<=last:raise ValueError('Portfolio '+role.upper()+' window lies outside common qualified coverage.')
        if date.fromisoformat(end)<date.fromisoformat(start):raise ValueError('Invalid portfolio dates.')
        bounds[role]=dict(start=start,end=end)
    if bounds['is']['end']>=bounds['oos']['start']:raise ValueError('IS must precede OOS.')
    allocations=family(len(sources),body.maximum_accounts,body.placements)
    return dict(status='compatible',sources=sources,windows=bounds,allocation_count=len(allocations),allocations=allocations,
        interpretation='Select the best observed IS net-cash allocation, freeze it, then run the same allocation on OOS and the stitched full period. Shared accounts admit one position at a time. No future forecast or provider certification.')


def launch(request,body):
    store=request.app.state.prop_analyses;id=body.request_id.hex
    with store.lock:
        with store.connect() as db:
            if db.execute('SELECT 1 FROM workflow_prop_sim_deletions WHERE id=?',(id,)).fetchone():
                raise ValueError('This portfolio request was deleted; use a new request ID.')
            old=db.execute('SELECT payload FROM workflow_prop_simulations WHERE id=?',(id,)).fetchone()
        if old:
            old=json.loads(old[0])
            if old.get('portfolio',{}).get('request')!=body.model_dump(mode='json'):raise ValueError('Request ID belongs to a different portfolio configuration.')
            job=store.get(old['portfolio']['analysis_id'])
            if job['status'] in ('queued','running','complete'):return old
            checked=metadata(request,body);aid=uuid4().hex
            old['portfolio']['analysis_id']=aid
            old['portfolio'].setdefault('attempts',[job['id']]).append(aid)
            old['portfolio']['implementation']=implementation()
            saved=old
            with store.connect() as db:
                db.execute('UPDATE workflow_prop_simulations SET payload=? WHERE id=?',(canonical(saved),id))
                db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(aid,sha256(canonical(saved['configuration']).encode()).hexdigest(),
                    checked['sources'][0]['source_backtest_id'],datetime.now(timezone.utc).isoformat(),'queued','Queued explicit portfolio retry',None))
                db.execute('INSERT INTO phase_analysis_control(analysis_id) VALUES (?)',(aid,))
                db.executemany('INSERT OR IGNORE INTO analysis_sources VALUES (?,?)',[(aid,s[k]) for s in checked['sources'] for k in ('source_backtest_id','oos_report_id')])
            store.worker.submit(run,request.app,saved,checked);return saved
        checked=metadata(request,body);aid=uuid4().hex
        saved=dict(id=id,created_at_utc=datetime.now(timezone.utc).isoformat(),configuration=dict(body.model_dump(mode='json'),mode='portfolio'),
            qualification=checked['sources'][0],portfolio_sources=checked['sources'],campaign_ids={},
            portfolio=dict(analysis_id=aid,attempts=[aid],implementation=implementation(),windows=checked['windows'],allocation_count=checked['allocation_count']))
        # The saved request excludes the mode tag accepted only by the parent reader.
        saved['portfolio']['request']=body.model_dump(mode='json')
        with store.connect() as db:
            db.execute('INSERT INTO workflow_prop_simulations VALUES (?,?,?)',(id,saved['created_at_utc'],canonical(saved)))
            db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(aid,sha256(canonical(saved['configuration']).encode()).hexdigest(),
                checked['sources'][0]['source_backtest_id'],saved['created_at_utc'],'queued','Queued portfolio allocation and replacement cash flow',None))
            db.execute('INSERT INTO phase_analysis_control(analysis_id) VALUES (?)',(aid,))
            db.executemany('INSERT OR IGNORE INTO analysis_sources VALUES (?,?)',[(aid,s[k]) for s in checked['sources'] for k in ('source_backtest_id','oos_report_id')])
        store.worker.submit(run,request.app,saved,checked)
    return saved


def implementation():
    from .session_calendar import calendar_path
    import os
    root=Path(__file__).parent
    result={name:sha256((root/name).read_bytes()).hexdigest() for name in (
        'prop_portfolio.py','prop/portfolio_sources.py','prop/portfolio_search.py','prop/portfolio_lifecycle.py','prop/portfolio_cash.py',
        'execution.py','prop/native_control.py','prop/evaluation_profiles.py','prop/funded_profiles.py','prop/sizing.py',
        'prop/native_engine.py','prop/lucid_engine.py','prop/native_money.py','prop/cash_ledger.py','strategy.py',
        'strategies/vwap_pullback_risk_sizing.py','strategies/vwap_features.py','strategies/registry.py',
        'decimal_math.py','session_calendar.py','intratrade.py','execution_scenarios.py','decision_capture.py','strategy_features.py')}
    result[os.path.relpath(calendar_path(),root)]=sha256(calendar_path().read_bytes()).hexdigest()
    from .prop import native_backend,lucid_backend
    for backend in (native_backend,lucid_backend):
        selected=Path(backend.module().__file__)
        result[os.path.relpath(selected,root)]=sha256(selected.read_bytes()).hexdigest()
    return result


def recover(app):
    from types import SimpleNamespace
    store=app.state.prop_analyses
    with store.connect() as db:parents=[json.loads(r[0]) for r in db.execute("SELECT payload FROM workflow_prop_simulations WHERE json_extract(payload,'$.configuration.mode')='portfolio'")]
    for saved in parents:
        job=store.get(saved['portfolio']['analysis_id'])
        if job and job['status']=='error' and job['progress']=='Interrupted' and saved['portfolio']['implementation']==implementation():
            with store.connect() as db:control=db.execute('SELECT stop_requested FROM phase_analysis_control WHERE analysis_id=?',(job['id'],)).fetchone()
            if control and control[0]:continue
            try:launch(SimpleNamespace(app=app),PortfolioRequest.model_validate(saved['portfolio']['request']))
            except (ValueError,KeyError):continue


def run(app,saved,checked):
    from .prop.portfolio_sources import prepare
    from .prop.portfolio_search import optimize
    from .prop.portfolio_lifecycle import run_lineup
    from .prop.native_analysis import csv_text
    from .optimization_cache import digest
    store=app.state.prop_analyses;aid=saved['portfolio']['analysis_id'];settings=saved['portfolio']['request']
    def checkpoint():
        with store.connect() as db:stop=db.execute('SELECT stop_requested FROM phase_analysis_control WHERE analysis_id=?',(aid,)).fetchone()
        if stop and stop[0]:raise AnalysisCancelled('Portfolio analysis stopped; no partial result published.')
    def progress(message):checkpoint();store._update(aid,'running',message)
    try:
        progress('Checking synchronized portfolio bars and causal sizing')
        from .prop.adapter import digest as file_digest
        numerical={str(p.relative_to(Path(__file__).parent)):file_digest(p) for p in (Path(__file__).parent/'prop').glob('*.py')}
        numerical.update(implementation())
        if saved['portfolio']['implementation']!=implementation():raise ValueError('Portfolio implementation changed after launch; retry this saved configuration.')
        with TemporaryDirectory(prefix='.portfolio-',dir=store.root) as temp,store.runtime.activate():
            staged=Path(temp)/'report';staged.mkdir();windows=checked['windows']
            kwargs=dict(datasets=app.state.store,runs=app.state.runs,qualified=checked['sources'],settings=settings,checkpoint=checkpoint)
            context=prepare(**kwargs,start=windows['is']['start'],end=windows['is']['end'],bar_directory=Path(temp)/'is-bars')
            search=optimize(context,checked['allocations'],checkpoint,progress)
            frozen=dict(search['frozen'],implementation=numerical,configuration=settings,windows=windows,
                calendar=dict(start_dates=context['calendar'].start_dates,coverage_end=context['calendar'].coverage_end,closures=context['calendar'].closures),
                retry=asdict(context['retry']))
            frozen.pop('sha256',None)
            frozen['sha256']=sha256(canonical(frozen).encode()).hexdigest()
            (staged/'portfolio_frozen.json').write_text(canonical(frozen))
            allocation=frozen['allocation']
            results={}
            combined=None
            alternative=None
            if allocation.get('counts') is not None and not any(allocation['counts']):
                invested=[r for r in search['candidates'] if r['allocation'].get('placement')=='shared' or any(r['allocation'].get('counts',[]))]
                if invested:
                    progress('Auditing the best invested IS alternative · not selected for OOS')
                    best=max(invested,key=lambda r:Decimal(r['cash']['net_cash']))
                    alternative=run_lineup(context,best['allocation'],capture=True,checkpoint=checkpoint)
                    (staged/'is_alternative.json').write_text(canonical(alternative))
                    for key in ('cash_ledger','trades','sizing_decisions'):
                        (staged/('is_alternative_'+key+'.csv')).write_text(csv_text(alternative[key]))
            for name,window in [('is',windows['is']),('oos',windows['oos']),('combined',dict(start=windows['is']['start'],end=windows['oos']['end']))]:
                progress('Frozen '+name.upper()+' portfolio · actual replacements and cash receipts')
                if name!='is' and combined is None:
                    combined=prepare(**kwargs,start=windows['is']['start'],end=windows['oos']['end'],bar_directory=Path(temp)/'full-bars')
                if name=='is':current=context
                elif name=='combined':current=combined
                else:
                    from .prop.phase_search import PhaseCalendar
                    current=dict(combined,first=window['start'],last=window['end'],
                        bars=(combined['bars'].subset(window['start'],window['end']) if hasattr(combined['bars'],'subset') else
                            {d:b for d,b in combined['bars'].items() if window['start']<=str(d)<=window['end']}),
                        sessions={d:s for d,s in combined['sessions'].items() if window['start']<=str(d)<=window['end']},
                        calendar=PhaseCalendar((window['start'],),combined['calendar'].coverage_end,tuple(d for d in combined['calendar'].closures if d>=window['start'])))
                results[name]=run_lineup(current,allocation,capture=True,checkpoint=checkpoint,
                    progress=lambda p,name=name:progress(f"Frozen {name.upper()} portfolio · {p['completed']}/{p['total']} calendar days"))
                for key in ('cash_ledger','trades','sizing_decisions','transitions','accounts'):
                    (staged/(name+'_'+key+'.json')).write_text(canonical(results[name][key]))
                    (staged/(name+'_'+key+'.csv')).write_text(csv_text(results[name][key]))
            checkpoint()
            for name,expected in numerical.items():
                if file_digest(Path(__file__).parent/name)!=expected:raise ValueError('Portfolio calculation implementation changed during execution.')
            from .prop.phase_profiles import verify_phase_source
            from .optimization_cache import artifacts
            for source in context['sources']:
                for role in ('is','oos'):
                    record=app.state.runs.get(source[role+'_id'])
                    if digest(record)!=source[role+'_sha256'] or artifacts(app.state.runs.root,record)!=source[role+'_artifacts']:raise ValueError('Portfolio source evidence changed.')
            calculations=dict(analysis_mode='portfolio_cashflow',frozen=frozen,allocation_search=search['candidates'],results=results,abstention_alternative=alternative,
                history=None,assumptions=[checked['interpretation'],'Account owners and execution fills are reused locally; no Bridge runtime.',
                    'Portfolio allocation is fitted on one observed IS history, not a Monte Carlo probability forecast.',
                    'OOS and stitched history retain the same allocation; the fresh OOS scenario starts unfunded.',
                    'Shared accounts allow one position at a time; known-signal priority uses larger risk share then source order. Inactive strategies keep observing prices.',
                    'Account and phase switches start cold strategy state, with no inherited position; Evaluation retries retain the existing controller behavior.',
                    'Monthly fee cap excludes receipts, expires unused allowance and reserves activation before purchase. Pending cash is not received cash.',
                    'Observed NQ reference prices may proxy MNQ execution at point value 2; no measured micro basis or provider execution parity is claimed.'])
            (staged/'allocation_results.json').write_text(canonical(search['candidates']))
            (staged/'source_checks.json').write_text(canonical(dict(sources=context['sources'],coverage=combined['coverage'],
                interpretation='Actual observed bars only. Sparse pre-entry prices remain sparse; every possible daytime holding minute through close is observed. No invented warmup or prices.')))
            report=dict(format_version=5,model_version='native-portfolio-cashflow-v1',source=dict(backtest=dict(id=checked['sources'][0]['source_backtest_id'])),
                settings=dict(ANALYSIS_MODE='portfolio_cashflow'),configuration=saved['configuration'],calculations=calculations,implementation=numerical)
            with store.lock:
                checkpoint();seal_report(staged,report,aid,saved['created_at_utc'],size_limit_bytes=None);staged.rename(store.root/aid)
                with store.connect() as db:
                    db.execute('INSERT INTO analysis_report_checks VALUES (?,?)',(aid,canonical(sealed_checks(store.root/aid))))
                store._update(aid,'complete','Saved portfolio allocation and replacement cash flow ready')
    except AnalysisCancelled as exc:store._update(aid,'cancelled','Portfolio stopped',str(exc))
    except Exception as exc:store._update(aid,'error','Portfolio analysis failed',f'{type(exc).__name__}: {exc}')


@router.post('/check')
async def check(body:PortfolioRequest,request:Request):return await invoke(metadata,request,body)


@router.post('',status_code=202)
async def submit(body:PortfolioRequest,request:Request):return await invoke(launch,request,body)


@router.get('/{id}/results')
async def results(id:UUID,request:Request):
    def read():
        store=request.app.state.prop_analyses
        with store.connect() as db:row=db.execute('SELECT payload FROM workflow_prop_simulations WHERE id=?',(id.hex,)).fetchone()
        if not row:raise KeyError('Portfolio not found.')
        saved=json.loads(row[0]);aid=saved['portfolio']['analysis_id']
        if not store.fingerprint(aid):raise ValueError('Portfolio report is incomplete or changed.')
        report=json.loads((store.root/aid/'report.json').read_text());calc=report['calculations']
        return dict(id=aid,frozen=calc['frozen'],assumptions=calc['assumptions'],allocation_search=calc['allocation_search'],
            abstention_alternative=({k:v for k,v in calc['abstention_alternative'].items() if k in ('allocation','cash','counts','open_accounts')} if calc.get('abstention_alternative') else None),
            results={name:{k:v for k,v in r.items() if k not in ('cash_ledger','trades','sizing_decisions','transitions','pending_settlements','accounts')} for name,r in calc['results'].items()})
    return await invoke(read)
