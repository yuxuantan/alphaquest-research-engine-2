"""Finite IS-only allocation search and frozen observed cash-flow assessment."""
from datetime import datetime,timezone
from decimal import Decimal
from hashlib import sha256
from itertools import product
from pathlib import Path
import pickle
import json
from tempfile import TemporaryDirectory

from .adapter import canonical
from .parallel import map_reported
from .portfolio_lifecycle import run_lineup

def family(strategies,maximum_accounts,placements):
    result=[dict(placement='separate',counts=[0]*strategies)]
    if 'separate' in placements:
        result += [dict(placement='separate',counts=list(v)) for v in product(range(maximum_accounts+1),repeat=strategies) if 0<sum(v)<=maximum_accounts]
    if 'shared' in placements:
        result += [dict(placement='shared',weights=list(v),accounts=n) for v in product(range(5),repeat=strategies) if sum(v)==4 for n in range(1,maximum_accounts+1)]
    return result


def _trial(task):
    filename,expected,allocation,index=task
    raw=Path(filename).read_bytes()
    if sha256(raw).hexdigest()!=expected:raise ValueError('Portfolio worker input changed.')
    context=pickle.loads(raw)
    marker=Path(context['cancel_file'])
    def checkpoint():
        if marker.exists():raise RuntimeError('Portfolio allocation stopped.')
    progress_file=Path(filename).parent/(str(index)+'.json')
    def progress(value):
        temporary=progress_file.with_suffix('.tmp');temporary.write_text(json.dumps(value));temporary.replace(progress_file)
    result=run_lineup(context,allocation,checkpoint=checkpoint,progress=progress)
    progress_file.unlink(missing_ok=True)
    return result


def optimize(context,allocations,checkpoint,progress):
    with TemporaryDirectory(prefix='aq-portfolio-search-') as directory:
        filename=Path(directory)/'context.pkl';marker=Path(directory)/'stop'
        raw=pickle.dumps(dict(context,cancel_file=str(marker)),protocol=pickle.HIGHEST_PROTOCOL);filename.write_bytes(raw)
        tasks=[(str(filename),sha256(raw).hexdigest(),a,i) for i,a in enumerate(allocations)]
        last_write=0.
        def notify(completed,total,workers,pids):
            nonlocal last_write
            from time import monotonic
            now=monotonic()
            if now-last_write<1 and completed!=total:return
            active=[]
            for p in Path(directory).glob('*.json'):
                try:
                    v=json.loads(p.read_text());active.append(f"allocation {int(p.stem)+1}: {v['completed']}/{v['total']} calendar days")
                except (OSError,ValueError,KeyError):continue
            progress(f'Portfolio IS allocation · {completed}/{total} lineups · {workers} workers'+(' · '+'; '.join(active) if active else ''))
            last_write=now
        rows=map_reported(_trial,tasks,checkpoint=checkpoint,notify=notify,cancel=marker.touch)
    def accounts(row):
        a=row['allocation'];return sum(a['counts']) if a['placement']=='separate' else a['accounts']
    winner=min(rows,key=lambda r:(-Decimal(r['cash']['net_cash']),accounts(r),canonical(r['allocation'])))
    frozen=dict(version='native-portfolio-allocation-v1',allocation=winner['allocation'],is_net_cash=winner['cash']['net_cash'],
        evaluation_sizing=context['evaluation_sizing'].policy,funded_sizing=context['funded_sizing'].policy,
        monthly_cap=context['monthly_cap'],sources=context['sources'],selected_at_utc=datetime.now(timezone.utc).isoformat(),
        objective='Maximum observed IS trader receipts minus actual paid Evaluation and activation fees; zero-purchase baseline included',
        limits='Finite integer account allocations and 25% shared risk-share grid; fixed declared per-trade policies. No global optimality or future profit claim.')
    frozen['sha256']=sha256(canonical(frozen).encode()).hexdigest()
    return dict(frozen=frozen,candidates=rows,winner=winner)
