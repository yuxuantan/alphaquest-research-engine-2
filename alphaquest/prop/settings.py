"""Historical notebook defaults; active local model settings live in native_analysis."""
from datetime import date
import math

NOTEBOOK_SHA256 = 'f79b6c6cc54e7bd64d619bb684ec4c6537c7bcf1d1e1d3f6d5bd6e74c908f89b'
MODEL_VERSION = 'notebook-apex50k-2508-v1'
DEFAULTS = dict(
    INSTRUMENT='NQ', MINI_LABEL='MINI', MICRO_LABEL='MICRO', MICRO_PER_MINI=10,
    ALLOW_VARIABLE_CONTRACTS=False, BOOTSTRAP_BLOCK=1, VALIDATION_SPLIT=.30,
    NUM_CONTRACTS=1, RISK_PER_CONTRACT=1500., COMMISSION_PER_CONTRACT=2.25,
    SLIPPAGE_PER_CONTRACT=5., PROP_MC_SIMS=20000, SWEEP_SIMS=5000,
    EVAL_WINDOW='calendar', EVAL_WINDOW_CALENDAR_DAYS=30, MAX_TRADING_DAYS=21,
    OOS_START_DATE='2023-01-01', SWEEP_CONTRACTS=[.3,.5,.7,1.,1.1,1.3,1.5,1.7,2.],
    SEED=42, ENGINE='excursion', BUFFER_LEVEL=1000., STAGE1_FRACS=[.25,.5,.75],
    STAGED_MODE='dynamic', STAGED_SIMS=20000, N_SPAGHETTI=300,
    RHO_GRID=[0.,.15,.30,.50], N_MAX_ATT=6, ATTEMPT_FEE=100.,
    RULE_SET='apex40', PAYOUT_MIN_BALANCE=2600., PAYOUT_MIN_WITHDRAWAL=500.,
    PAYOUT_DD_LOCK=100., PAYOUT_SPLIT=1., INACTIVITY_WINDOW_TD=22,
    INACTIVITY_MIN_QUAL=2, INACTIVITY_PROFIT_THR=50., INACTIVITY_ON=True,
    PAYOUT_MAX_HORIZON=250, PAYOUT_SIMS=20000, PAYOUT_SWEEP_SIMS=5000,
    PAYOUT_CONTRACTS=[.2,.3,.4,.5,.6,.7,.8,.9,1.,1.1,1.2,1.3,1.4,1.5,1.7,2.],
    BLOWN_COST=150., MAX_BLOWN_RATE=.50,
    PAYOUT_LADDER=[1500.,1500.,2000.,2500.,2500.,3000.],
    LIFETIME_HORIZON=2000, LIFETIME_SIMS=10000, LIFETIME_SWEEP_SIMS=4000,
    EVAL_FEE=100., PA_ACTIVATION=140.,
)
PRESETS = {'notebook': {}, '49+129': {'ATTEMPT_FEE':49.,'EVAL_FEE':49.,'PA_ACTIVATION':129.},
           '109+0': {'ATTEMPT_FEE':109.,'EVAL_FEE':109.,'PA_ACTIVATION':0.}}


def validate(overrides):
    if not isinstance(overrides, dict) or set(overrides) - DEFAULTS.keys():
        raise ValueError('Unknown analysis setting; use the notebook setting names.')
    for k,v in overrides.items():
        d=DEFAULTS[k]
        if k=='OOS_START_DATE':
            if v is not None:
                if not isinstance(v,str): raise ValueError('OOS_START_DATE must be an ISO date or null.')
                date.fromisoformat(v)
        elif isinstance(d,bool):
            if type(v) is not bool: raise ValueError(f'{k} must be boolean.')
        elif isinstance(d,str):
            if not isinstance(v,str) or not 1<=len(v)<=80: raise ValueError(f'Invalid {k}.')
        elif isinstance(d,list):
            if not isinstance(v,list) or not 1<=len(v)<=64: raise ValueError(f'{k} needs 1–64 entries.')
            if any(type(x) not in (int,float) or not math.isfinite(x) or x<0 or x>100000 for x in v):raise ValueError(f'Invalid {k} entries.')
            if k=='RHO_GRID' and any(x>=1 for x in v):raise ValueError('Correlations must be below 1.')
            if k in ('SWEEP_CONTRACTS','PAYOUT_CONTRACTS') and any(x<=0 for x in v):raise ValueError('Sizes must be positive.')
        else:
            if type(v) not in (int,float) or not math.isfinite(v) or v<0 or v>100000:raise ValueError(f'Invalid {k}.')
            if isinstance(d,int) and type(v) is not int:raise ValueError(f'{k} must be an integer.')
            if (k.endswith('SIMS') or k in ('BOOTSTRAP_BLOCK','MAX_TRADING_DAYS','EVAL_WINDOW_CALENDAR_DAYS','MICRO_PER_MINI','N_SPAGHETTI','N_MAX_ATT','PAYOUT_MAX_HORIZON','LIFETIME_HORIZON','INACTIVITY_WINDOW_TD','RISK_PER_CONTRACT','NUM_CONTRACTS')) and v<=0:raise ValueError(f'{k} must be positive.')
    s={**DEFAULTS,**overrides}
    if not 0<=s['VALIDATION_SPLIT']<1:raise ValueError('VALIDATION_SPLIT must be in [0, 1).')
    if not 0<=s['MAX_BLOWN_RATE']<=1 or not 0<=s['PAYOUT_SPLIT']<=1:raise ValueError('Rates must be in [0, 1].')
    for k,choices in dict(ENGINE=['daily','trade','excursion'],EVAL_WINDOW=['calendar','fixed'],STAGED_MODE=['dynamic','ratchet'],RULE_SET=['apex40','legacy']).items():
        if s[k] not in choices:raise ValueError(f'Invalid {k}.')
    if s['N_SPAGHETTI']>300 or s['PAYOUT_MAX_HORIZON']>10000 or s['LIFETIME_HORIZON']>10000 or s['MAX_TRADING_DAYS']>1000 or s['EVAL_WINDOW_CALENDAR_DAYS']>1000 or s['N_MAX_ATT']>100:raise ValueError('Chart/horizon limits exceeded; requested counts are never reduced.')
    return overrides
