"""Finite IS-only allocation search and frozen observed cash-flow assessment."""
from datetime import datetime,timezone
from decimal import Decimal
from hashlib import sha256
from itertools import combinations, islice, product, zip_longest
from pathlib import Path
import pickle
import json
from tempfile import TemporaryDirectory

from pydantic import BaseModel, ConfigDict, StrictInt, model_validator

from .adapter import canonical
from .parallel import map_reported
from .portfolio_lifecycle import run_lineup
from .sizing import SizingPolicy
from .sizing_search import PercentageGrid

PHASES=('evaluation','funded')


class FixedGrid(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    minimum:StrictInt
    maximum:StrictInt
    step:StrictInt

    @model_validator(mode='after')
    def validate_range(self):
        if not 1<=self.minimum<=self.maximum<=60 or self.step<1 or (self.maximum-self.minimum)%self.step:
            raise ValueError('Enter a positive whole-MNQ range with endpoints aligned to the step.')
        return self


def sizing_policies(grid):
    if 'reference' in grid:
        spec=PercentageGrid.model_validate(grid)
        policies=(SizingPolicy(kind='percentage_risk',risk_percent=value,reference=spec.reference,
            maximum_contracts=spec.maximum_contracts,constrain_to_account_cushion=spec.constrain_to_account_cushion,
            constrain_to_daily_cushion=spec.constrain_to_daily_cushion) for value in spec.values())
    else:
        spec=FixedGrid.model_validate(grid)
        policies=(SizingPolicy(kind='fixed_contracts',contracts=value,maximum_contracts=spec.maximum)
            for value in range(spec.minimum,spec.maximum+1,spec.step))
    return [policy.model_dump(mode='json') for policy in policies]

def family(strategies,maximum_accounts,placements):
    result=[dict(placement='separate',counts=[0]*strategies)]
    if 'separate' in placements:
        result += [dict(placement='separate',counts=list(v)) for v in product(range(maximum_accounts+1),repeat=strategies) if 0<sum(v)<=maximum_accounts]
    if 'shared' in placements:
        result += [dict(placement='shared',weights=list(v),accounts=n) for v in product(range(5),repeat=strategies) if sum(v)==4 for n in range(1,maximum_accounts+1)]
    return result


def members(plan):
    if plan['placement']=='separate':
        return tuple(index for index,count in enumerate(plan['counts']) if count)
    return tuple(plan['members'])


def optimized_search(strategies,maximum_accounts,placements,axes,budget):
    baseline=dict(placement='separate',counts=[0]*strategies)
    layouts=[baseline]
    if 'separate' in placements:
        layouts.extend(dict(placement='separate',counts=list(v))
            for v in product(range(maximum_accounts+1),repeat=strategies) if 0<sum(v)<=maximum_accounts)
    if 'shared' in placements:
        for count in range(1,maximum_accounts+1):
            for length in range(2,strategies+1):
                layouts.extend(dict(placement='shared',members=list(group),accounts=count)
                    for group in combinations(range(strategies),length))
            if 'separate' not in placements:
                layouts.extend(dict(placement='shared',members=[i],accounts=count) for i in range(strategies))
    full_size=sum((len(axes[0])*len(axes[1]))**len(members(layout)) for layout in layouts)
    return dict(layouts=layouts,axes=axes,configurations=strategies,grid_size=full_size,
        replay_limit=min(full_size,budget),method='full_grid' if full_size<=budget else 'bounded_multi_start')


def materialize(search,layout,positions):
    axes=search['axes']
    policies=[None]*search['configurations']
    for i,(evaluation,funded) in zip(members(layout),positions):
        policies[i]=dict(evaluation=axes[0][evaluation],funded=axes[1][funded])
    return dict(layout,sizing=policies)


def full_family(search):
    axes=search['axes']
    sizes=list(product(range(len(axes[0])),range(len(axes[1]))))
    for layout in search['layouts']:
        for positions in product(sizes,repeat=len(members(layout))):
            yield materialize(search,layout,positions)


def seed_plans(search):
    layouts=search['layouts']
    yield materialize(search,layouts[0],())
    comparison=sorted(layouts[1:],key=lambda row:(account_count(row),len(members(row))!=1,
        len(members(row))!=search['configurations'],row['placement'],members(row)))
    middle=tuple(len(axis)//2 for axis in search['axes'])
    limits=tuple(len(axis)-1 for axis in search['axes'])
    variants=(middle,(0,0),limits,(0,limits[1]),(limits[0],0))
    # Visit each strategy alone and a joint account before adding more slots.
    for layout in comparison:
        if account_count(layout)==1:
            yield materialize(search,layout,[middle]*len(members(layout)))
    for coordinates in variants:
        for layout in comparison:
            yield materialize(search,layout,[coordinates]*len(members(layout)))


def neighboring_plans(search,plan):
    positions={i:tuple(axis.index(plan['sizing'][i][phase]) for axis,phase in zip(search['axes'],PHASES))
        for i in members(plan)}
    layout={key:value for key,value in plan.items() if key!='sizing'}
    middle=tuple(len(axis)//2 for axis in search['axes'])
    layouts=(materialize(search,other,[positions.get(i,middle) for i in members(other)])
        for other in sorted(search['layouts'],key=lambda row:(abs(account_count(row)-account_count(layout)),row['placement']!=layout['placement']))
        if other!=layout and members(other))
    moves=[]
    for index,pair in positions.items():
        for phase,coordinate in enumerate(pair):
            for neighbor in sorted({0,coordinate-1,coordinate+1,len(search['axes'][phase])-1}):
                if neighbor==coordinate or not 0<=neighbor<len(search['axes'][phase]):continue
                updated=list(pair);updated[phase]=neighbor
                moves.append((index,tuple(updated)))
    singles=(materialize(search,layout,[updated if i==index else pair for i,pair in positions.items()])
        for index,updated in moves)
    pairs=(materialize(search,layout,[p if i==a else q if i==b else pair for i,pair in positions.items()])
        for (a,p),(b,q) in combinations(moves,2) if a!=b)
    for group in zip_longest(singles,layouts,pairs):
        yield from (plan for plan in group if plan is not None)


def account_count(plan):
    return sum(plan['counts']) if plan['placement']=='separate' else plan['accounts']


def rank(row):
    return -Decimal(row['cash']['net_cash']),account_count(row['allocation']),canonical(row['allocation'])


def bounded_search(search,evaluate):
    rows=[];seen=set();limit=search['replay_limit'];seeds=iter(seed_plans(search))
    def unseen(plans):
        for plan in plans:
            key=canonical(plan)
            if key not in seen:
                seen.add(key);yield plan
    rows.extend(evaluate(list(islice(unseen(seeds),min(limit,max(search['configurations']+2,limit//3)))),0))
    while len(rows)<limit:
        leaders=[r for r in sorted(rows,key=rank) if account_count(r['allocation'])][:3]
        # Interleave leaders and move types so one neighborhood cannot consume
        # the entire budget before another is tried.
        neighborhoods=[neighboring_plans(search,r['allocation']) for r in leaders]
        plans=(plan for group in zip_longest(seeds,*neighborhoods) for plan in group if plan is not None)
        batch=list(islice(unseen(plans),min(8,limit-len(rows))))
        if not batch:
            batch=list(islice(unseen(full_family(search)),limit-len(rows)))
        if not batch:break
        rows.extend(evaluate(batch,len(rows)))
    return rows


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


def optimize(context,allocations,checkpoint,progress,*,search=None):
    with TemporaryDirectory(prefix='aq-portfolio-search-') as directory:
        filename=Path(directory)/'context.pkl';marker=Path(directory)/'stop'
        raw=pickle.dumps(dict(context,cancel_file=str(marker)),protocol=pickle.HIGHEST_PROTOCOL);filename.write_bytes(raw)
        expected=sha256(raw).hexdigest()
        target=search['replay_limit'] if search else len(allocations)
        def evaluate(plans,offset):
            tasks=[(str(filename),expected,plan,offset+i) for i,plan in enumerate(plans)]
            last_write=0.
            def notify(completed,total,workers,pids):
                nonlocal last_write
                from time import monotonic
                now=monotonic()
                if now-last_write<1 and completed!=total:return
                active=[]
                for p in sorted(Path(directory).glob('*.json')):
                    try:
                        v=json.loads(p.read_text());active.append(f"plan {int(p.stem)+1}: {v['completed']}/{v['total']} calendar days")
                    except (OSError,ValueError,KeyError):continue
                progress(f'Portfolio IS search · {offset+completed}/{target} plans · {workers} workers'+(' · '+'; '.join(active) if active else ''))
                last_write=now
            return map_reported(_trial,tasks,checkpoint=checkpoint,notify=notify,cancel=marker.touch)
        if not search:rows=evaluate(allocations,0)
        elif search['method']=='full_grid':rows=evaluate(full_family(search),0)
        else:rows=bounded_search(search,evaluate)
    winner=min(rows,key=rank)
    frozen=dict(version='native-portfolio-allocation-v1',allocation=winner['allocation'],is_net_cash=winner['cash']['net_cash'],
        evaluation_sizing=context['evaluation_sizing'].policy,funded_sizing=context['funded_sizing'].policy,
        monthly_cap=context['monthly_cap'],sources=context['sources'],selected_at_utc=datetime.now(timezone.utc).isoformat(),
        objective='Maximum observed IS trader receipts minus actual paid Evaluation and activation fees; zero-purchase baseline included',
        limits='Finite integer account allocations and 25% shared risk-share grid; fixed declared per-trade policies. No global optimality or future profit claim.')
    if search:
        frozen.update(version='native-portfolio-allocation-v2',evaluation_sizing=None,funded_sizing=None,
            search={key:search[key] for key in ('method','grid_size','replay_limit')},
            limits='Finite native chronological search. The bounded search selects the best tested plan.')
        frozen['search']['tested']=len(rows)
        frozen['signal_priority']='selection_order'
    frozen['sha256']=sha256(canonical(frozen).encode()).hexdigest()
    return dict(frozen=frozen,candidates=rows,winner=winner)
