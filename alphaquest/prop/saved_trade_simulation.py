"""Saved opportunities with causal stop sizing and an explicit bounded-loss law.

This is an economic approximation, not native execution parity. The source
strategy is run at most once to recover missing causal plans, never per path.
Provider rules, cash, sampling and selection remain in the existing owners.
"""
from collections import OrderedDict
from copy import deepcopy
import csv
import json
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
from threading import RLock

from .adapter import canonical, digest

MODEL = 'saved-trade-stop-budget-v1'
ACCOUNT_MODEL = 'saved-trade-account-policies-v2'
ASSUMPTIONS = dict(model=MODEL,
    opportunities='Frozen nonoverlapping saved trades; skipped opportunities do not reveal new setups or change later signals.',
    sizing='Known submission reference and initial protective stop, whole MNQ rounded down, declared loss-side costs included. Never realized MAE or a future entry fill.',
    admission='Requested dollar budget must be strictly below both remaining account and enabled daily allowances; reject rather than shrink the budget. Provider quantity caps still apply.',
    fills='Protective stop active immediately; never widened beyond the initial risk; exact modeled stop and account-limit fills. No gap overshoot, latency or liquidity model.',
    outcomes='Saved price outcomes scaled linearly, source commission replaced once; negative outcomes bounded by planned stop loss. MAE and intratrade paths are not used.',
    limitations='A counterfactual saved-opportunity model, not reconstructed execution. Breaches are largely prevented by construction; low breach probability is not evidence of live gap resilience.')
_cache = OrderedDict()
_lock = RLock()


def assumptions(sizing):
    if sizing.execution_model==MODEL:return deepcopy(ASSUMPTIONS)
    return dict(model=ACCOUNT_MODEL,trade_handling=deepcopy(sizing.trade_handling),
        opportunities=ASSUMPTIONS['opportunities'],sizing=ASSUMPTIONS['sizing'],fills=ASSUMPTIONS['fills'],
        admission='Intended whole-position stop risk after provider/user caps. Skip at either remaining allowance, or enter with exact account-limit exits, as frozen per phase.',
        outcomes='Saved outcomes with bounded stop losses. Account-limit exits use cost-adjusted captured source excursions, capped at the assumed immediate protective stop; MAE never sizes an entry.',
        limitations='Frozen saved opportunities; no alternative setups. OHLC excursions are model estimates or conservative bounds, not measured tick paths. Exact limit fills exclude gaps and liquidity risk.')


class PathProgress:
    """Throttled completed-path metadata; never changes the financial work."""
    def __init__(self,callback,sizing,label=None):
        from time import monotonic
        self.callback,self.started,self.last=callback,monotonic(),0
        self.label=label or (f"{sizing.policy['contracts']} MNQ" if sizing.policy['kind']=='fixed_contracts' else str(sizing.policy['risk_percent'])+'% · '+sizing.policy['reference'].replace('_',' '))

    def __call__(self,completed,total):
        from time import monotonic
        now=monotonic()
        if now-self.last<1 and completed not in (0,total):return
        self.last=now;elapsed=now-self.started
        self.callback(dict(stage='saved_trade_execution',sizing_label=self.label,completed=completed,total=total,
            unit='account paths',worker_count=1,active_workers=0 if completed==total else 1,
            elapsed_seconds=round(elapsed,2),eta_seconds=round(elapsed*(total-completed)/completed,2) if completed>=8 else None))


def enabled(sizing):
    return sizing is not None and sizing.execution_model in (MODEL,ACCOUNT_MODEL)


def describe_results(rows):
    """Expose the saved law and quantity counters on normal phase result rows."""
    for row in rows:
        provenance=row.get('provenance') or row.get('component',{}).get('provenance',{})
        model=provenance.get('source',{}).get('saved_trade_simulation')
        if model:
            row['simulation_model']={k:deepcopy(v) for k,v in model.items() if k not in ('causal_plans','causal_plan_provenance','bounded_losses')}
            summary=deepcopy(provenance.get('sizing',{}).get('summary',{}))
            counts={int(q):n for q,n in summary.get('quantity_counts',{}).items() if int(q)>0}
            admitted=sum(counts.values());n=summary.get('decision_count',0)
            def quantile(p):
                from math import ceil
                target=ceil(admitted*p);seen=0
                for q,count in sorted(counts.items()):
                    seen+=count
                    if seen>=target:return q
            summary.update(opportunities=n,all_recorded_opportunities=n,source_trade_count=model.get('source_trades'),account_halted_opportunities=None,admitted_entries=admitted,
                skipped_entries=summary.get('skipped_count',0),skipped_rate=summary.get('skipped_count',0)/n if n else None,
                mean_quantity=sum(q*count for q,count in counts.items())/admitted if admitted else None,
                median_quantity=quantile(.5) if admitted else None,p95_quantity=quantile(.95) if admitted else None,
                minimum_quantity=min(counts) if counts else None,maximum_quantity=max(counts) if counts else None,
                cap_binding_rate=summary.get('cap_bound_count',0)/n if n else None,
                mean_requested_risk_budget=str(Decimal(summary.get('total_requested_risk_budget','0'))/summary['risk_budget_count']) if summary.get('risk_budget_count') else None,
                mean_admitted_planned_risk=str(Decimal(summary.get('total_admitted_planned_risk','0'))/n) if n else None,
                scope='Monte Carlo visited eligible opportunities, not unique historical trades. After pass, termination or mandatory pause, later opportunities are excluded. Quantity/risk/exit rates cover admitted entries; skip rate covers visited opportunities.')
            for name in ('account_limit_exit','daily_limit_exit','account_breach_exit','risk_budget_override'):
                summary[name+'_rate']=summary.get(name+'_count',0)/admitted if admitted else None
            risk_count=summary.get('actual_risk_count',0)
            summary['mean_actual_risk_percent']=str(Decimal(summary.get('total_actual_risk_percent','0'))/risk_count) if risk_count else None
            row['quantity_summary']=summary
    return rows


class _Plans:
    """Observe submitted facts before the ordinary engine consumes an entry."""
    def __init__(self, strategy, tick):
        self.strategy,self.tick=strategy,tick
        self.pending={};self.filled=[]

    def __getattr__(self, name):
        return getattr(self.strategy,name)

    def on_bar(self,bar,position):
        from ..strategy import EntryIntent,StopEntriesIntent
        from ..strategy_sizing import initial_risk_intent
        intent=self.strategy.on_bar(bar,position)
        entries=((intent,bar.close),) if type(intent) is EntryIntent else intent.orders if type(intent) is StopEntriesIntent else ()
        if entries:
            self.pending={}
            for entry,reference in entries:
                planned=initial_risk_intent(entry,reference,self.tick)
                self.pending[entry.side]=dict(side=entry.side,reason=entry.reason,
                    sizing_decision=dict(timestamp_utc=bar.timestamp_utc.isoformat(),reference_price=str(reference),execution_timing=entry.timing),
                    initial_stop=dict(price=str(planned.initial_stop),known_at_utc=bar.timestamp_utc.isoformat(),basis='submitted_order'))
        return intent

    def entry(self,intent,bar,reference):
        plan=self.pending.get(intent.side)
        if plan is None or plan['reason']!=intent.reason:
            raise ValueError('Saved trade has no matching causal submitted stop plan.')
        self.filled.append(deepcopy(plan))


def causal_plans(runs,snapshot):
    """Verify stored plans or reconstruct once with exact completed-trade parity.

    Cache only derived metadata, keyed by immutable inputs plus current strategy
    and execution identities. Every use still verifies source/dataset identity.
    No original report is edited and no synthetic stop is invented.
    """
    from pathlib import Path
    record=snapshot['backtest'];root=runs.root/record['id']
    with (root/'trades.csv').open(newline='') as stream:trades=list(csv.DictReader(stream))
    if record.get('execution_decisions'):
        from ..decision_capture import read_decision_evidence,SIDE_CAR
        evidence=read_decision_evidence(root/SIDE_CAR,record['execution_decisions'],trades,record['execution_settings'])
        plans={key:dict(side=trades[int(key)-1]['side'],sizing_decision=value['sizing_decision'],initial_stop=value['initial_stop'])
               for key,value in evidence['trades'].items()}
        return plans,dict(method='verified_saved_decisions',sha256=record['execution_decisions']['sha256'])
    from ..datasets import DatasetStore
    from ..strategies.registry import get_strategy
    from ..strategy import ExecutionConfig
    from ..execution import execute,Trade
    from ..backtest_data import read_selected_bars,DateRange
    from ..execution_scenarios import resolve_execution_scenario,restore_scenario_config
    from tempfile import TemporaryDirectory
    from .. import execution
    from ..optimization_cache import engine_identity
    definition=get_strategy(record['run_metadata']['strategy']['id'])
    parameters=definition.parameters(record['run_metadata']['strategy']['parameters'])
    definition.sizing.require(parameters,'fixed_contracts')
    datasets=DatasetStore(runs.root.parent/'datasets.sqlite3')
    dataset=datasets.get(record['run_metadata']['dataset']['id'])
    if dataset is None or any(dataset.get(k)!=v for k,v in record['run_metadata']['dataset'].items()):
        raise ValueError('Saved-trade causal reconstruction requires the unchanged original dataset.')
    strategy_identity=json.loads(json.dumps(definition.provenance(parameters),default=str))
    key=canonical(dict(root=str(root),source=snapshot['manifest_sha256'],trades=snapshot['trades_sha256'],
        strategy=strategy_identity,execution=digest(Path(execution.__file__)),adapter=digest(Path(__file__)),engine=engine_identity()))
    cache_key=sha256(('saved-causal-stop-plans:'+key).encode()).hexdigest()
    with _lock:
        h=sha256()
        for chunk in datasets.iter_csv(dataset['id']):h.update(chunk)
        if h.hexdigest()!=dataset.get('csv_sha256',dataset['sha256']):
            raise ValueError('Original dataset bytes changed; causal stop plans cannot be reused.')
        if key in _cache:
            _cache.move_to_end(key);return deepcopy(_cache[key])
        with TemporaryDirectory(prefix='aq-causal-stop-plans-') as temporary:
            path=Path(temporary)/'plans.json'
            restored=runs.replay_cache.restore(cache_key,path)
            if restored==dict(kind='saved-causal-stop-plans-v1',identity=cache_key):
                try:
                    cached=json.loads(path.read_text())
                    plans,proof=cached['plans'],cached['proof']
                    if (set(plans)=={str(t['trade_number']) for t in trades}
                            and sha256(canonical(plans).encode()).hexdigest()==proof['sha256']
                            and proof['strategy']==strategy_identity):
                        result=(plans,proof);_cache[key]=deepcopy(result)
                        while len(_cache)>4:_cache.popitem(last=False)
                        return result
                except (ValueError,KeyError,TypeError):pass
        config=ExecutionConfig(**{k:(v if k=='slippage_ticks' else Decimal(v)) for k,v in record['execution_settings'].items()})
        scenario=record['run_metadata'].get('execution_scenario')
        if scenario is not None:
            baseline,inherited=restore_scenario_config(scenario)
            if resolve_execution_scenario(baseline,inherited)[0]!=config:raise ValueError('Saved execution scenario changed.')
            config,fills=resolve_execution_scenario(baseline,inherited)
        else:config,fills=resolve_execution_scenario(config,None)
        strategy=_Plans(definition.create(parameters,config,instrument_symbol=dataset.get('symbol')),config.tick_size)
        selection=record['run_metadata']['selection']
        period=DateRange.parse(selection.get('from_date'),selection.get('to_date'))
        actual=[]
        with read_selected_bars(datasets,dataset['id'],period) as selected:
            for event in execute(selected.bars,strategy,config,fill_assumptions=fills,observe_entry=strategy.entry):
                if type(event) is Trade:
                    def serial(v):
                        return v.isoformat().replace('+00:00','Z') if hasattr(v,'tzinfo') else '' if v is None else str(v)
                    actual.append({k:serial(v) for k,v in asdict(event).items()})
        if actual!=trades or len(strategy.filled)!=len(trades):
            raise ValueError('Causal stop reconstruction differs from saved trades. A new qualified campaign backtest is required; old evidence is preserved.')
        plans={str(i):{k:v for k,v in plan.items() if k!='reason'} for i,plan in enumerate(strategy.filled,1)}
        result=(plans,dict(method='one_verified_source_replay',strategy=strategy_identity,
            sha256=sha256(canonical(plans).encode()).hexdigest(),matched_trades=len(trades)))
        with TemporaryDirectory(prefix='aq-causal-stop-plans-') as temporary:
            path=Path(temporary)/'plans.json';path.write_text(canonical(dict(plans=plans,proof=result[1])))
            runs.replay_cache.save(cache_key,path,dict(kind='saved-causal-stop-plans-v1',identity=cache_key))
        _cache[key]=deepcopy(result)
        while len(_cache)>4:_cache.popitem(last=False)
        return result


def adapt_saved_trades(runs,snapshot,rows,sizing):
    """Attach causal facts and bound outcomes without reading MAE for decisions."""
    from .sizing import DecisionRisk,PlanningExecution,_distance_loss
    from .phase_lifecycle import instant,session_date
    from ..strategies.registry import get_strategy
    record=snapshot['backtest'];saved=record['run_metadata']['strategy']
    definition=get_strategy(saved['id']);definition.sizing.require(definition.parameters(saved['parameters']),'fixed_contracts')
    plans,proof=causal_plans(runs,snapshot)
    planning=PlanningExecution.model_validate(sizing.planning_execution)
    rate=snapshot['commission_simulation'].get('per_side')
    if rate is None or rate=='':raise ValueError('Saved stop-budget simulation requires explicit per-side MNQ commission adaptation.')
    rate=Decimal(str(rate))
    if rate!=planning.commission_per_contract_per_side:
        raise ValueError('Sizing planning commission must equal the saved-trade simulation commission.')
    previous=None;metadata={};bounded=[];coverage={}
    current=sizing.execution_model==ACCOUNT_MODEL
    needs_mae=current and sizing.trade_handling['account_limit_action']=='exit_at_limit'
    for row in sorted(rows,key=lambda r:(r['entry_utc'],int(r['trade_id']))):
        if session_date(instant(row['entry_utc']))!=session_date(instant(row['exit_utc'])):
            raise ValueError('Saved stop-budget simulation requires each source trade to be session-flat.')
        plan=plans[str(row['trade_id'])]
        if plan['initial_stop'] is None:raise ValueError('Saved-trade sizing requires a causal initial protective stop for every trade.')
        item=dict(source_trade_id=str(row['trade_id']),side=plan['side'],entry_time_utc=row['entry_utc'],
            sizing_decision=plan['sizing_decision'],initial_stop=plan['initial_stop'],previous_source_exit_utc=previous)
        from .sizing_runtime import decision_risk_from_metadata
        risk=decision_risk_from_metadata(item)
        if any(v%planning.tick_size for v in (risk.decision_reference_price,risk.initial_stop_price)):
            raise ValueError('Causal stop and reference must obey the executable tick grid.')
        distance=(risk.decision_reference_price-risk.initial_stop_price)*(1 if risk.side=='long' else -1)
        unit=_distance_loss(distance,planning.tick_size,planning.point_value,planning.entry_slippage_ticks,
            planning.stop_exit_slippage_ticks,planning.commission_per_contract_per_side)
        raw=Decimal(row['simulation_net_per_nq'])/10
        net=max(raw,-unit)
        if net!=raw:bounded.append(dict(source_trade_id=str(row['trade_id']),source_net_per_mnq=str(raw),modeled_net_per_mnq=str(net)))
        adverse=max(Decimal(0),-net)*10
        if current:
            measured=row.get('ohlc_mae_upper') is not None or row.get('measured_mae') is not None
            if needs_mae and not measured:
                raise ValueError(f"Account-limit exits require captured source MAE for every trade; trade {row['trade_id']} has only a realized-loss fallback. Rerun the source backtest with intratrade risk capture, or choose Skip trade.")
            basis=snapshot.get('excursion_input',{}).get('risk_policy','measured_trade_export' if measured else 'realized_loss_fallback')
            coverage[basis]=coverage.get(basis,0)+1
            if measured and needs_mae:
                observed=Decimal(row['simulation_mae_per_nq'])
                if not observed.is_finite() or observed<0:raise ValueError('Captured source MAE must be finite and nonnegative.')
                adverse=max(adverse,min(observed,unit*10))
        row.update(simulation_net_per_nq=str(net*10),simulation_mae_per_nq=str(adverse),
            simulation_adverse_path_per_nq='[]',risk_cross_session=False)
        metadata[str(row['trade_id'])]=item;previous=row['exit_utc']
    snapshot['saved_trade_simulation']=dict(**assumptions(sizing),causal_plan_provenance=proof,causal_plans=metadata,
        source_trades=len(rows),bounded_loss_count=len(bounded),bounded_losses=bounded,
        mae_used=needs_mae,excursion_coverage=coverage,alternative_opportunities_generated=False)
    snapshot['phase_suitability']=dict(fixed_quantity=True,risk_covered_trades=len(rows) if needs_mae else 0,
        instrument=snapshot['commission_simulation']['source_instrument'],scaling=ASSUMPTIONS['opportunities'])
    return metadata
