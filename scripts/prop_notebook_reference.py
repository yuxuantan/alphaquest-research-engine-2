"""Independent reference execution of pinned notebook source, in a fresh namespace.

Only upload and plotting/presentation are omitted. Original CSV loader, numerical
cells and RNG calls execute directly, with assignments for explicit setting
injection. No production numerical-model imports. Notebook outputs are ignored.
"""
import ast
from contextlib import redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
from uuid import uuid4

NOTEBOOK=Path(__file__).resolve().parents[1]/'docs/notebooks/PropFirm_MonteCarlo_Apex50K_2508.ipynb'
HASH='f79b6c6cc54e7bd64d619bb684ec4c6537c7bcf1d1e1d3f6d5bd6e74c908f89b'


def reference(frame, settings, increment=1):
    raw=NOTEBOOK.read_bytes();assert sha256(raw).hexdigest()==HASH
    cells=json.loads(raw)['cells']
    key='notebook_reference_'+uuid4().hex;module=ModuleType(key);ns=module.__dict__;sys.modules[key]=module
    ns['_overrides']=settings
    ns['_reference_lifetime_observations']=[]
    class Settings(ast.NodeTransformer):
        def __init__(self):self.seen=set()
        def visit_FunctionDef(self,n):
            if n.name=='simulate_funded_lifetime':
                for i,stmt in enumerate(n.body):
                    if isinstance(stmt,ast.Return):
                        n.body.insert(i,ast.parse('_reference_lifetime_observations.append(dict(n_contracts=n_contracts, days_alive=list(days_alive_all), first_payout_days=list(first_payout_days)))').body[0]);break
            return self.generic_visit(n)
        def visit_Import(self,n):
            return None if any(x.name.startswith('matplotlib') for x in n.names) else n
        def visit_ImportFrom(self,n):
            return None if (n.module or '').startswith('matplotlib') else n
        def visit_Expr(self,n):
            return None if 'plt.rcParams' in ast.unparse(n) else n
        def visit_Assign(self,n):
            # Visit nested notebook settings too. Function-body local assignments
            # use no setting names, so numerical internals are left unchanged.
            if len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in settings and n.targets[0].id not in self.seen:
                k=n.targets[0].id
                try:ast.literal_eval(n.value)
                except (ValueError,TypeError):
                    if k != 'STAGED_SIMS':return n
                self.seen.add(k)
                return [n,ast.parse(f'{k} = _overrides.get({k!r}, {k})').body[0]]
            return n
    def cell(i):
        tree=ast.parse(''.join(cells[i]['source']))
        if i in (7,13,15):
            stop=next(j for j,n in enumerate(tree.body) if isinstance(n,ast.Assign) and 'plt.subplots' in ast.unparse(n))
            tree.body=tree.body[:stop]
        tree=Settings().visit(tree);ast.fix_missing_locations(tree)
        with redirect_stdout(io.StringIO()):exec(compile(tree,f'notebook:cell-{i}','exec'),ns)
        if i==4:
            p=ns['df_sim']['profit_net_usd'];w=ns['winners'];l=ns['losers']
            ns['_reference_statistics']=dict(trades=len(p),win_rate=float((p>0).mean()),average_net=float(p.mean()),total_net=float(p.sum()),ev_r=float(ns['df_sim']['r_mult'].mean()),average_winner=float(w.mean()) if len(w) else None,average_loser=float(l.mean()) if len(l) else None,bootstrap_usd_ci=[ns['lo'],ns['hi']],bootstrap_r_ci=[ns['rlo'],ns['rhi']],p_ev_usd_nonpositive=float((ns['b_usd']<=0).mean()),p_ev_r_nonpositive=float((ns['b_r']<=0).mean()),bootstrap_sims=10000,bootstrap_seed=42)
    try:
        with TemporaryDirectory() as temp:
            f=frame.copy()
            # Recreate original source-sized canonical CSV before notebook loader.
            if 'source_quantity' in f:
                f['contracts']=f.source_quantity.astype(float);f['profit_usd']=f.source_reference_gross_pnl.astype(float)
            path=Path(temp)/'canonical.csv';f.to_csv(path,index=False);ns['FILENAME']=str(path)
            for i in (2,3,4,5,6,7,8,9,10):cell(i)
            if increment>=2:
                cell(11);cell(12)
            cell(13)
            if increment>=2:
                cell(14);cell(15)
            if increment>=3:
                for i in (17,18,19):cell(i)
            if increment>=4:
                cell(21)
                # Capture raw results returned inside original cell 16 loop.
                ns['_reference_robustness']=[]
                original=ns['simulate_funded']
                def tracked(*a,**kw):
                    r=original(*a,**kw);ns['_reference_robustness'].append(dict(block=ns['BOOTSTRAP_BLOCK'],evaluation=ns['_e'],funded=r));return r
                ns['simulate_funded']=tracked;cell(22)
            return dict(ns)
    finally:sys.modules.pop(key,None)
