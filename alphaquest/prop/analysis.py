"""Analysis orchestration over the isolated numerical model; no HTTP or plots."""
from dataclasses import asdict
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
import platform
import subprocess
import math
import numpy as np
import pandas as pd
from .adapter import adapt, canonical
from .model import NotebookModel
from .settings import DEFAULTS, PRESETS, NOTEBOOK_SHA256, MODEL_VERSION, validate

AVAILABLE_INCREMENT = 3
NOTEBOOK = Path(__file__).resolve().parents[2]/'docs/notebooks/PropFirm_MonteCarlo_Apex50K_2508.ipynb'


def clean(value):
    if isinstance(value,np.ndarray):return clean(value.tolist())
    if isinstance(value,np.generic):return clean(value.item())
    if isinstance(value,(float,int)) and not isinstance(value,bool):
        if isinstance(value,float) and not math.isfinite(value):return None
        return value
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,(pd.Timestamp,)):return value.isoformat()
    return value


def prepare(runs,source_id,overrides,preset='source',pricing='notebook'):
    validate(overrides)
    if preset not in ('source','notebook') or pricing not in PRESETS:raise ValueError('Unknown settings/pricing preset.')
    s={**DEFAULTS,**PRESETS[pricing],**overrides}
    frame,snapshot,source_overrides=adapt(runs,source_id,s)
    resolved={**DEFAULTS,**(source_overrides if preset=='source' else {}),**PRESETS[pricing],**overrides}
    # Cell 8b binds STAGED_SIMS to the resolved PROP_MC_SIMS, not SWEEP_SIMS.
    if 'STAGED_SIMS' not in overrides:resolved['STAGED_SIMS']=resolved['PROP_MC_SIMS']
    validate(resolved)
    date_count=len(pd.date_range(frame['date'].min(),frame['date'].max(),freq='B'))
    selected=frame if resolved['OOS_START_DATE'] is None else frame[frame.datetime>=resolved['OOS_START_DATE']]
    n_days=len(pd.date_range(selected['date'].min(),selected['date'].max(),freq='B'))
    split=round(n_days*(1-resolved['VALIDATION_SPLIT']))
    if resolved['VALIDATION_SPLIT']>0 and not 0<split<n_days:raise ValueError('Holdout would create an empty train/validation weekday pool; set VALIDATION_SPLIT=0 or select more history.')
    if date_count>20000:raise ValueError('Source exceeds 20,000-weekday resource bound.')
    return frame,snapshot,resolved,dict(preset=preset,pricing=pricing,source_derived_overrides=source_overrides if preset=='source' else {},pricing_overrides=PRESETS[pricing],user_overrides=overrides)


def statistics(m):
    p=m.df_sim.profit_net_usd
    return dict(trades=len(p),win_rate=float((p>0).mean()),average_net=float(p.mean()),total_net=float(p.sum()),ev_r=float(m.df_sim.r_mult.mean()),average_winner=float(m.winners.mean()) if len(m.winners) else None,average_loser=float(m.losers.mean()) if len(m.losers) else None,
        bootstrap_usd_ci=[m.lo,m.hi],bootstrap_r_ci=[m.rlo,m.rhi],p_ev_usd_nonpositive=float((m.b_usd<=0).mean()),p_ev_r_nonpositive=float((m.b_r<=0).mean()),bootstrap_sims=10000,bootstrap_seed=42)


def histogram(values, bins=40):
    values=np.asarray(values);values=values[np.isfinite(values)]
    if not len(values):return dict(counts=[],edges=[])
    counts,edges=np.histogram(values,bins=bins)
    return dict(counts=counts,edges=edges)


def execute(frame,settings,increment=1,progress=lambda _:None):
    m=NotebookModel();m.overrides=settings;m.cell_2();m.df=frame.copy(deep=True)
    progress('Trade statistics and 10,000-draw bootstrap confidence intervals')
    m.cell_4();m.HAS_EXCURSIONS=False;m.EXCURSION_COVERAGE=0.
    m.cell_6();m.cell_8();m.cell_9()
    progress('Main evaluation Monte Carlo')
    m.cell_10()
    main_statistics=statistics(m)
    if increment>=2:
        progress('Train/validation size sweep and staged sizing')
        m.cell_11();m.cell_12()
    # At increment 1, path samples use the full sample. Cell 9 uses validation
    # after cell 8 in a complete top-to-bottom execution; later increments do so.
    m.cell_13()
    result=dict(statistics=main_statistics,daily=m.daily_full.to_dict('records'),trades=m.df_sim.to_dict('records'),evaluation=m.res,
        paths=dict(equity=m.paths,outcomes=m.outcomes,seed=m.SEED+5000,sample=m.SAMPLE_NAME),
        engine=dict(requested=settings['ENGINE'],effective=m.ENGINE,measured_excursion_coverage=0.,provenance='No measured excursions; trade fallback; synthetic bag MAE is realized loss, zero for winners.'),
        rules=asdict(m.CHALLENGE),deadline_pool=m.DEADLINE_POOL,
        samples=dict(main='full filtered sample',downstream=m.SAMPLE_NAME,split_weekday_index=m._SPLIT_I),
        seed_streams=dict(bootstrap_fixed=42,main=m.SEED,paths=m.SEED+5000,degradation_fixed=20240101))
    if increment>=2:
        m.cell_15()
        staged=[dict(stage1_nc=row[0],stage2_nc=m._opt_nc,pass_rate=row[1],ci_low=row[2],ci_high=row[3],delta_vs_flat=row[1]-m._p_flat) for row in m._rows]
        if m._best_staged[2]>m._hi_f:staging_verdict='HELPS'
        elif m._best_staged[3]<m._lo_f:staging_verdict='HURTS'
        else:staging_verdict='No significant difference'
        result['sizing']=dict(sweep=m.sweep_data,selected=m._best,validation=m._val,
            train_weekdays=m._SPLIT_I if m.VALIDATION_SPLIT>0 else len(m.TRADE_BAG_FULL),validation_weekdays=len(m.TRADE_BAG),
            sample=m.SAMPLE_NAME,staged=staged,staged_raw=m._rows,flat_pass_rate=m._p_flat,
            flat_ci=[m._lo_f,m._hi_f],staged_verdict=staging_verdict,ci_overlap_sizes=m._tied,
            selection_limitation='CI overlap is notebook tie language, not proof of equivalence; staged selection reuses validation; staged engine omits DLL.')
        result['attempts']=dict(
            independent=[dict(attempts=n,probability=1-(1-m.res['pass_rate'])**n) for n in (1,2,3,4)],
            independent_sample='Main full-filtered sample, cell 10',
            correlated=[dict(attempts=n,fees=n*m.ATTEMPT_FEE,**{f'rho_{rho:g}':m._p_within_n(m._p_att,n,rho) for rho in m.RHO_GRID}) for n in range(1,m.N_MAX_ATT+1)],
            correlated_sample=m.SAMPLE_NAME,pass_probability=m._p_att,attempt_fee=m.ATTEMPT_FEE,
            attempts_to_80={str(rho):next((n for n in range(1,m.N_MAX_ATT+1) if m._p_within_n(m._p_att,n,rho)>=.8),None) for rho in m.RHO_GRID})
        result['seed_streams'].update(sweep=m.SEED+2000,validation=m.SEED+2600,staged=m.SEED+15000)
    result["charts"]=dict(days_to_pass=histogram(m.res["days_to_pass"]),drawdown=histogram(m.res.get("max_dds",m.res.get("max_dds_all"))))
    if increment>=3:
        progress('Funded first-payout sweep and selected-size detail')
        m.cell_17();m.cell_18();m.cell_19()
        result['funded']=dict(sweep=m.payout_sweep,selected=m.best,detail=m.detail,sample=m.SAMPLE_NAME,
            selection_fallback=not any(row['blown_rate']<=m.MAX_BLOWN_RATE for row in m.payout_sweep),
            rules={k:getattr(m,k) for k in ('RULE_SET','PAYOUT_QUAL_DAYS','PAYOUT_DAY_THR','PAYOUT_MIN_TRADED','CONSISTENCY_LIMIT','PAYOUT_CAP','PAYOUT_MIN_BALANCE','PAYOUT_MIN_WITHDRAWAL','PAYOUT_SAFETY_NET','PAYOUT_MAX_DD','PAYOUT_DD_LOCK','PAYOUT_SPLIT','INACTIVITY_WINDOW_TD','INACTIVITY_MIN_QUAL','INACTIVITY_PROFIT_THR','INACTIVITY_ON','PAYOUT_MAX_HORIZON')})
        result['charts'].update(first_payout=histogram(m.detail['payouts']),qualifying_days=histogram(m.detail['days_to_qualify']))
        result['seed_streams'].update(funded_sweep=m.SEED+8000,funded_detail=m.SEED+9000)
    return clean(result)


def run_analysis(runs,source_id,overrides,preset,pricing,increment,progress):
    if sha256(NOTEBOOK.read_bytes()).hexdigest()!=NOTEBOOK_SHA256:raise ValueError('Pinned notebook hash mismatch.')
    frame,snapshot,settings,origins=prepare(runs,source_id,overrides,preset,pricing)
    output=execute(frame,settings,increment,progress)
    try:app_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=NOTEBOOK.parents[2],stderr=subprocess.DEVNULL,text=True).strip()
    except (OSError,subprocess.CalledProcessError):app_commit='unavailable'
    return dict(format_version=1,model_version=MODEL_VERSION,notebook_sha256=NOTEBOOK_SHA256,
        application_commit=app_commit,implementation_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},
        runtime=dict(python=platform.python_version(),numpy=version('numpy'),pandas=version('pandas')),
        source=snapshot,input_sha256=sha256(frame.to_csv(index=False).encode()).hexdigest(),settings=settings,setting_origins=origins,literal_notebook_defaults=DEFAULTS,increment=increment,**output)
