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

AVAILABLE_INCREMENT = 1
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
    # At increment 1, path samples use the full sample. Cell 9 uses validation
    # after cell 8 in a complete top-to-bottom execution; later increments do so.
    m.cell_13()
    result=dict(statistics=statistics(m),daily=m.daily_full.to_dict('records'),trades=m.df_sim.to_dict('records'),evaluation=m.res,
        paths=dict(equity=m.paths,outcomes=m.outcomes,seed=m.SEED+5000,sample=m.SAMPLE_NAME),
        engine=dict(requested=settings['ENGINE'],effective=m.ENGINE,measured_excursion_coverage=0.,provenance='No measured excursions; trade fallback; synthetic bag MAE is realized loss, zero for winners.'),
        rules=asdict(m.CHALLENGE),deadline_pool=m.DEADLINE_POOL,
        samples=dict(main='full filtered sample',downstream=m.SAMPLE_NAME,split_weekday_index=m._SPLIT_I),
        seed_streams=dict(bootstrap_fixed=42,main=m.SEED,paths=m.SEED+5000,degradation_fixed=20240101))
    result["charts"]=dict(days_to_pass=histogram(m.res["days_to_pass"]),drawdown=histogram(m.res.get("max_dds",m.res.get("max_dds_all"))))
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
