"""Bounded, frozen-size evidence package; no nested historical resampling.

Account transitions remain in the phase owners. Intervals quantify conditional
simulation error only. Chronology and stress scenarios are descriptive evidence,
never independent market observations, historical CIs, or a new sizing search.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import numpy as np
import pandas as pd

from .adapter import canonical

VERSION = 'prop-complementary-evidence-v2'
RULES = dict(version=VERSION, account_paths=5000, stress_paths=1000,
    evaluation_deadlines=[90,180,365], account_starts=24, evaluation_start_horizon=180,
    confidence=.95, maximum_relative_mcse=.05, maximum_probability_half_width=.025,
    minimum_complete_months=12, minimum_closed_trades=100,
    funded_receipts_watch_ratio=.70, evaluation_probability_watch_ratio=.70,
    evaluation_wait_watch_ratio=1.50, stress_retention_watch_ratio=.70,
    stress_blocks=[1,10], additional_mnq_cost_per_side='0.50', historical_replicates=0)
LIMITATIONS = [
    'Simulation intervals condition on the supplied history, empirical sampling law, account rules and execution model. They do not measure historical-estimation uncertainty or future-market confidence.',
    'No nested historical refits or historical non-inferiority confidence intervals are calculated. This evidence package is not equivalent to the historical v1 gate.',
    'Chronological starts may overlap and are dependent scenarios. Stress outcomes are sensitivity checks, not independent samples or confidence bounds.',
    'OOS was already accessed in campaign qualification. No OOS replacement size or strategy is selected.',
    'Evidence ready for paper review is not permission to trade live. Supplied forward execution review and deployment/cash-flow controls remain separate.',
]


def implementation():
    from . import assessment_review, native_account_starts, oos_qualification
    from .. import prop_sim_forward,forward_monitoring
    return dict(version=VERSION, files={p.name:sha256(p.read_bytes()).hexdigest() for p in
        (Path(__file__),Path(assessment_review.__file__),Path(native_account_starts.__file__),Path(oos_qualification.__file__),Path(prop_sim_forward.__file__),Path(forward_monitoring.__file__))})


def covered_starts(period,horizon,closures=()):
    from .assessment_review import start_plan
    eligible=[d for d in pd.bdate_range(period['first_session'],period['last_session'])
        if str(d.date()) not in set(closures) and d.date()+timedelta(days=horizon-1)<=date.fromisoformat(period['last_session'])]
    count=min(RULES['account_starts'],len(eligible))
    return start_plan(period,horizon,max(2,count),closures)


def policy(phase,period,horizon,*,prior_access=True,closures=()):
    if phase not in ('evaluation','funded'):raise ValueError('Unknown independent phase.')
    value=dict(version=VERSION,phase=phase,rules=deepcopy(RULES),implementation=implementation(),
        declared_at_utc=datetime.now(timezone.utc).isoformat(),declaration_timing='retrospective' if prior_access else 'before_first_prop_oos_result',
        start_plan=covered_starts(period,RULES['evaluation_start_horizon'] if phase=='evaluation' else horizon,closures),
        interpretation='Frozen IS choices; bounded account Monte Carlo, chronological starts and predefined stress checks. No nested refits, OOS selection or future confidence claim.')
    value['policy_sha256']=sha256(canonical(value).encode()).hexdigest()
    return value


def estimate(values,*,probability=False):
    """Pointwise conditional MC intervals, never historical or simultaneous CIs."""
    from .native_analysis import wilson
    x=np.asarray(values,dtype=float)
    if len(x)<2 or not np.all(np.isfinite(x)):return dict(mean=None,mc_standard_error=None,interval=None,paths=len(x))
    mean=float(x.mean());se=float(x.std(ddof=1)/np.sqrt(len(x)))
    interval=list(wilson(int(x.sum()),len(x))) if probability else [max(0.,mean-1.96*se),mean+1.96*se]
    return dict(mean=mean,mc_standard_error=se,interval=interval,paths=len(x),
        relative_mcse=se/mean if mean>0 else None,
        precision_ok=(interval[1]-interval[0])/2<=RULES['maximum_probability_half_width'] if probability else
            (se/mean<=RULES['maximum_relative_mcse'] if mean>0 else False))


def normalize_eval(paths,horizon):
    output=[]
    for p in paths:
        completed=p.get('acquisition_completed',p.get('event')=='funded')
        duration=p.get('calendar_days_to_funded',p.get('observed_calendar_days'))
        observed=float(p.get('observed_calendar_days',horizon))
        # An attempt/model guard before the declared observation deadline remains
        # unknown. Merely reaching the deadline without funding is an observation.
        complete_observation=bool(completed) or observed>=horizon
        output.append(dict(path_index=p.get('path_index',p.get('path',len(output))),start_date=p['start_date'],
            funded=bool(completed),calendar_days_to_funded=float(duration) if completed and duration is not None else None,
            observed_days=observed,paid_fees=float(p.get('paid_fees',p.get('cost_accrued',0))),
            capped_wait=min(float(duration) if completed else observed,horizon),
            observation_complete=complete_observation,outcome=p.get('outcome',p.get('event'))))
    return output


def summarize(paths,phase,horizon):
    if phase=='evaluation':
        rows=normalize_eval(paths,horizon)
        complete=all(p['observation_complete'] for p in rows) and bool(rows)
        funded=[p['funded'] and p['calendar_days_to_funded']<=horizon for p in rows]
        times=sorted(p['calendar_days_to_funded'] for p in rows if p['funded'])
        def quantile(q):
            rank=int(np.ceil(len(rows)*q))
            return times[rank-1] if rank and len(times)>=rank and complete else None
        return dict(horizon_calendar_days=horizon,paths=len(rows),observation_complete=complete,
            funded_probability=estimate(funded,probability=True),fees_spent=estimate([p['paid_fees'] for p in rows]),
            capped_wait=estimate([p['capped_wait'] for p in rows]),median_days=quantile(.5),p90_days=quantile(.9),
            unfunded_paths=sum(not p['funded'] for p in rows),early_guard_paths=sum(not p['observation_complete'] for p in rows))
    cash=[float(p['cash_received']) for p in paths]
    complete=bool(paths) and all(p.get('horizon_observations_complete',True) and not p.get('unresolved',False) for p in paths)
    return dict(horizon_calendar_days=horizon,paths=len(paths),observation_complete=complete,
        received_cash=estimate(cash),median_cash=float(np.median(cash)) if cash else None,
        p10_cash=float(np.quantile(cash,.1,method='inverted_cdf')) if cash else None,
        zero_receipts=estimate([v==0 for v in cash],probability=True),
        breach=estimate([p['outcome']=='blown' for p in paths],probability=True),
        pending_cash=estimate([float(p.get('pending_cash',0)) for p in paths]))


def _ratio(after,before):return after/before if after is not None and before is not None and before>0 else None


def insights(primary,stress,starts,phase,evidence,prerequisites,*,optional_breach_cap=None):
    """Server-owned actionable findings; sensitivity watches are not failures."""
    a=primary['is'][-1]['summary'];b=primary['oos'][-1]['summary'];findings=[]
    def add(key,title,state,summary,next_step,**extra):
        findings.append(dict(key=key,title=title,state=state,summary=summary,next_step=next_step,**extra))
    coverage=all(e['passed'] for e in evidence)
    add('coverage','Historical coverage','PASS' if coverage else 'INSUFFICIENT',
        'Coverage minima met.' if coverage else 'Insufficient OOS history or trades.',
        'Continue to the other checks.' if coverage else 'Collect more historical or forward observations; more account paths do not add history.')
    key='funded_probability' if phase=='evaluation' else 'received_cash'
    point=b[key]['mean'];positive=point is not None and point>0
    add('economics','Account economics','PASS' if positive else 'FAIL',
        ('Funding was observed within 365 days.' if phase=='evaluation' else 'Mean received cash is positive over the frozen horizon.') if positive else
        ('No accounts became funded within 365 days.' if phase=='evaluation' else 'No modeled trader cash was received.'),
        'Review expenditure and downside below; positive outcomes alone do not establish profitable replacement economics.' if positive else
        'Do not progress this frozen sizing plan on this evidence. Review account fit in a new IS study.')
    metrics=['funded_probability','fees_spent','capped_wait'] if phase=='evaluation' else ['received_cash','zero_receipts','breach']
    precision=all(s['summary']['observation_complete'] and all(s['summary'][m]['precision_ok'] for m in metrics)
        for role in ('is','oos') for s in primary[role])
    add('precision','Simulation precision','PASS' if precision else 'INSUFFICIENT',
        'Conditional simulation error is within the saved tolerances.' if precision else 'Some estimates are noisy or observations ended before the declared deadline.',
        'Intervals quantify simulation error only; market-history uncertainty remains.' if precision else
        'Inspect the metric intervals and early-guard counts. Additional account paths help numerical noise; they do not resolve missing history or early censoring.')
    probability_ratio=_ratio(b[key]['mean'],a[key]['mean'])
    wait_ratio=_ratio(b['capped_wait']['mean'],a['capped_wait']['mean']) if phase=='evaluation' else None
    watch=probability_ratio is None or probability_ratio<RULES['evaluation_probability_watch_ratio' if phase=='evaluation' else 'funded_receipts_watch_ratio'] or (phase=='evaluation' and (wait_ratio is None or wait_ratio>RULES['evaluation_wait_watch_ratio']))
    add('deterioration','IS → OOS stability','WATCH' if watch else 'PASS',
        ('OOS outcomes deteriorated beyond the saved review guardrails, or the comparison is undefined.' if watch else 'No review guardrail was crossed by the point estimates.'),
        'Investigate the market-period change and paper-test the frozen plan; do not choose replacement sizes from OOS.' if watch else 'Check chronology and stress results before paper execution review.',
        outcome_ratio=probability_ratio,capped_wait_ratio=wait_ratio,guardrails=dict(minimum_outcome_ratio=.7,maximum_wait_ratio=1.5 if phase=='evaluation' else None),
        interpretation='Point-estimate review guardrails, not historical confidence bounds or a statistical non-inferiority test.')
    missing=not starts['paths'];successful=(starts['summary'].get('funded',0) if phase=='evaluation' else len(starts['paths'])-starts['summary'].get('zero_receipt_starts',0))
    add('starts','Account-start sensitivity','INSUFFICIENT' if missing else 'WATCH' if successful<len(starts['paths']) else 'PASS',
        f'{successful} / {len(starts["paths"])} chronological starts '+('became funded.' if phase=='evaluation' else 'received cash.'),
        'Review the worst starting windows and their fee/cash outcomes. Overlapping starts are dependent; this fraction is not a future success probability.' if not missing else
        'There is insufficient full-window coverage for chronological start comparisons.')
    weak=[];unavailable=[]
    for scenario in stress:
        summary=scenario['summary'];base=a if scenario['role']=='is' else b
        ratio=_ratio(summary[key]['mean'],base[key]['mean'])
        scenario['retention_ratio']=ratio
        if not summary['observation_complete'] or ratio is None:unavailable.append(scenario['name'])
        elif ratio<RULES['stress_retention_watch_ratio']:weak.append(scenario['name'])
    add('stress','Stress resilience','INSUFFICIENT' if unavailable else 'WATCH' if weak else 'PASS',
        f'{len(weak)} weak and {len(unavailable)} unresolved of {len(stress)} predefined scenarios.',
        'Review the named weak scenarios before paper testing. Stress checks never select new sizes.' if weak or unavailable else
        'No scenario fell below 70% of the comparable baseline outcome; inspect the full ranges below.',weak_scenarios=weak,unresolved_scenarios=unavailable)
    if phase=='funded' and optional_breach_cap is not None:
        passed=b['breach']['mean'] is not None and b['breach']['mean']<=optional_breach_cap
        add('breach_cap','Declared breach constraint','PASS' if passed else 'FAIL',f'Frozen optional cap: {optional_breach_cap:.2%}.','Preserve the declared cap; do not relax it to obtain a pass.')
    if not prerequisites.get('passed'):status='NO_GO'
    elif any(f['state']=='FAIL' for f in findings):status='NO_GO'
    elif any(f['state']=='INSUFFICIENT' for f in findings):status='INSUFFICIENT_EVIDENCE'
    elif any(f['state']=='WATCH' for f in findings):status='REVIEW_REQUIRED'
    else:status='GO'
    return dict(version=VERSION,status=status,findings=findings,evidence=evidence,checks=[],historical_replicates=0,
        inner_precision_ok=precision,confidence=.95,prerequisites=prerequisites,
        forward_execution=dict(status='PENDING',minimum_sessions=20,minimum_closed_trades=30),limitations=LIMITATIONS,
        interpretation='This is a complementary evidence review of frozen sizes. GO means ready for paper execution review; WATCH requires investigation, not a demonstrated statistical failure. No historical confidence interval or live-trading approval is implied.')


def renewal_paths(outcomes,durations,candidate,calendar,checkpoint):
    """Existing Apex empirical retry owner, including a zero-pass sample."""
    from .native_backend import module
    from .evaluation_profiles import DatedEvaluationPreparation
    paths,_=module().renewal_acquisition(outcomes,durations,Decimal(candidate.profile.evaluation_price),
        Decimal(candidate.profile.activation_fee),candidate.retry,calendar,candidate.sampling,
        preparation=DatedEvaluationPreparation(),summary_only=False,checkpoint=checkpoint)
    return paths


class Runner:
    """Adapt declared scenarios to existing owners; never tune a policy."""
    def __init__(self,runs,datasets,search,checkpoint,progress):
        self.runs,self.datasets,self.search=runs,datasets,search
        self.checkpoint,self.progress=checkpoint,progress;self.cache={};self.started=monotonic();self.last=0
        self.phase=search.mode.removesuffix('_optimization')

    def notify(self,label,completed,total):
        now=monotonic();self.checkpoint()
        if now-self.last<1 and completed!=total:return
        self.last=now
        self.progress(dict(stage='complementary_evidence',sizing_label=label,completed=completed,total=total,
            unit='checks',worker_count=1,active_workers=1,elapsed_seconds=round(now-self.started,2),eta_seconds=None))

    def run(self,candidate,paths,horizon,*,block=None,period=None,extra_cost=False):
        from .phase_profiles import prepare_phase_source,verify_phase_source,SourceCosts
        c=replace(candidate,simulation=replace(candidate.simulation,simulations=paths),
            sampling=replace(candidate.sampling,block_weekdays=block or candidate.sampling.block_weekdays),period=period or candidate.period)
        if hasattr(c.sampling,'chain_simulations'):c=replace(c,sampling=replace(c.sampling,chain_simulations=paths))
        if hasattr(c,'retry'):c=replace(c,retry=replace(c.retry,max_calendar_days=horizon))
        if extra_cost:
            snapshot,_,_=prepare_phase_source(self.runs,c.source,c.profile,c.micros,c.simulation,c.period,c.costs,c.sizing)
            rate=snapshot['commission_simulation']['per_side']
            # The surcharge is an explicit commission/cost stress, not a claim
            # that moving an actual stop/limit fill is equivalent to a fee.
            c=replace(c,costs=SourceCosts(mode='override',instrument=c.costs.instrument,per_side=str(Decimal(str(rate))+Decimal(RULES['additional_mnq_cost_per_side']))))
            if c.sizing is not None:
                c=replace(c,sizing=replace(c.sizing,planning_execution=dict(c.sizing.planning_execution,commission_per_contract_per_side=c.costs.per_side)))
        if self.search.native_execution is not None:
            result=self.native(c,paths,horizon)
        else:
            snapshot,days,settings=prepare_phase_source(self.runs,c.source,c.profile,c.micros,c.simulation,c.period,c.costs,c.sizing)
            if self.phase=='funded':
                from .funded_profiles import _dated_funded_paths
                result,_,_=_dated_funded_paths(days,c.profile,c.micros,horizon,self.search.calendar,
                    self.search.receipt_delay_calendar_days,c.simulation,c.sampling,c.sizing,checkpoint=self.checkpoint)
            elif c.profile.profile_id=='lucidflex-50k':
                from .evaluation_profiles import calendar_evaluation_paths
                result,_=calendar_evaluation_paths(days,c.profile,c.micros,c.simulation,c.sampling,c.retry,self.search.calendar,checkpoint=self.checkpoint,sizing=c.sizing)
            else:
                from .native_analysis import evaluation_model
                raw=evaluation_model(days,c.micros,paths,c.simulation.seed,c.sampling.block_weekdays,settings,max_micros=c.simulation.max_micros,
                    **(c.sizing.kernel_arguments(stage='complementary_attempt_sample') if c.sizing else {}))
                component=SimpleNamespace(outcomes=[str(v) for v in raw['outcomes']],duration_weekdays=[int(v) for v in raw['days']],censoring=SimpleNamespace(censored_paths=0))
                result=renewal_paths(component.outcomes,component.duration_weekdays,c,self.search.calendar,self.checkpoint)
            verify_phase_source(self.runs,c.source,snapshot)
        if len(result)!=paths:raise ValueError('Complementary scenario did not retain every requested account path.')
        return dict(configuration=asdict(c),paths=result,summary=summarize(result,self.phase,horizon))

    def native(self,candidate,paths,horizon):
        from .native_search import candidate_request,prepare_native_candidate,verify_native_candidate
        from .native_replay import check_replay
        from .adapter import source_record
        native=replace(self.search.native_execution,horizon_calendar_days=horizon,capture_paths=1)
        # Source validation covers all observed holding bars. A small preparation
        # plan avoids enumerating every future schedule twice; the phase owner
        # still generates and executes all requested indexed account paths.
        prepared=replace(candidate,simulation=replace(candidate.simulation,simulations=max(8,len(self.search.calendar.start_dates))))
        search=replace(self.search,candidates=(prepared,),source_backtest_id=prepared.source.source_backtest_id,native_execution=native,
            **({'horizon_calendar_days':horizon} if self.phase=='funded' else {}))
        request=candidate_request(search,prepared)
        current=check_replay(self.datasets,self.runs,request,admitted_record=source_record(self.runs,candidate.source.source_backtest_id),
            source_cache=self.cache.setdefault('admission',{}),forecast_cache=self.cache.setdefault('catalogues',{}))
        from .source import prepare_source
        snapshot,_=prepare_source(self.runs,candidate.source.source_backtest_id,'',candidate.source.export_timezone,allow_empty=True)
        check=dict(manifest=dict(configuration=asdict(prepared),native_source_check=current,source=snapshot))
        inputs,_=prepare_native_candidate(self.datasets,self.runs,search,prepared,check,private_admission=True,
            checkpoint=self.checkpoint,cache=self.cache,progress=self.progress)
        inputs['forecast']=inputs['forecast'].model_copy(update={'capture_paths':0,'simulations':paths})
        if self.phase=='evaluation':
            from .evaluation_profiles import forecast_native_evaluation
            forecast=forecast_native_evaluation(**inputs,retry=candidate.retry,chain_sampling=candidate.sampling,checkpoint=self.checkpoint,progress=self.progress)
            result=forecast.get('independent_acquisition',{}).get('paths',forecast['paths'])
            if not result and candidate.profile.profile_id=='apex-50k-eod':
                attempts=[p['attempts'][0] for p in forecast['paths']]
                outcomes=[{'expired':'timeout'}.get(a['outcome'],a['outcome']) for a in attempts]
                if set(outcomes)-{'passed','blown','timeout','inactive'}:raise ValueError('Apex native attempt observations are incomplete.')
                result=renewal_paths(outcomes,[max(1,a['sessions']) for a in attempts],candidate,search.calendar,self.checkpoint)
        else:
            from .funded_profiles import forecast_native_funded,native_funded_metric_paths
            forecast=forecast_native_funded(**inputs,receipt_delay_calendar_days=search.receipt_delay_calendar_days,
                receipt_amount_convention='kernel_entitlement_unrounded',checkpoint=self.checkpoint,progress=self.progress)
            result=native_funded_metric_paths(forecast)
        verify_native_candidate(self.datasets,self.runs,search,prepared,check,private_admission=True,cache=self.cache)
        return result


def qualify(calculations,search,assessment,runs,checks,checkpoint,progress,staged,analyses,*,analysis_id=None,datasets=None):
    from .phase_profiles import SavedTradeSource,ResearchPeriod,verify_phase_source
    from .phase_search import capture_inputs
    from .assessment_review import run_start_sensitivity,distribution
    from .oos_qualification import complete_months
    options=assessment['prop_sim_review'];saved=options['policy'];phase=search.mode.removesuffix('_optimization')
    if options['implementation']!=implementation() or saved['rules']!=RULES:raise ValueError('Complementary assessment implementation or rules changed after declaration.')
    if saved['policy_sha256']!=sha256(canonical({k:v for k,v in saved.items() if k!='policy_sha256'}).encode()).hexdigest():raise ValueError('Assessment policy changed after declaration.')
    reused=calculations.get('qualification_implementation')==implementation() and calculations.get('qualification_rules')==RULES
    runner=Runner(runs,datasets,search,checkpoint,progress);details=[];captures=[];is_candidates=[]
    from .phase_dispatch import module_for
    phase_identity=module_for(phase).implementation_identity()
    configs={canonical(asdict(c)):c for c in search.candidates}
    package=assessment['frozen_package'];fingerprint=analyses.fingerprint(package['analysis_id'])
    if not fingerprint or fingerprint['files']['report.json']!=package['report_sha256']:raise ValueError('Frozen IS report changed before complementary comparison.')
    import json
    is_report=json.loads((analyses.root/package['analysis_id']/'report.json').read_text())
    is_rows={r['candidate_id']:r for r in is_report['calculations']['candidates']}
    for index,row in enumerate(calculations['candidates']):
        checkpoint();check=next(c for c in checks if c['candidate_id']==row['candidate_id']);c=configs[canonical(check['manifest']['configuration'])]
        binding=next(m for m in assessment['sources'] if m['frozen_candidate_id']==check['frozen_candidate_id']);original=binding['frozen_manifest']['configuration']
        ic=replace(c,source=SavedTradeSource(**original['source']),period=ResearchPeriod(**original['period']))
        verify_phase_source(runs,ic.source,binding['frozen_manifest']['source'])
        is_candidates.append(ic);captures.append(dict(candidate_id=check['frozen_candidate_id'],manifest=binding['frozen_manifest']))
        row['outcome_summary']=distribution(row,phase)
        if reused and row.get('prop_qualification',{}).get('version')==VERSION:continue
        months=complete_months(asdict(c.period));trades=check['manifest']['source']['backtest']['summary']['trades_taken']
        evidence=[dict(label='Complete OOS months',actual=months,required=RULES['minimum_complete_months'],passed=months>=RULES['minimum_complete_months']),
            dict(label='Closed OOS source trades',actual=trades,required=RULES['minimum_closed_trades'],passed=trades>=RULES['minimum_closed_trades'])]
        if not all(e['passed'] for e in evidence):
            row['prop_qualification']=dict(version=VERSION,status='INSUFFICIENT_EVIDENCE',evidence=evidence,checks=[],findings=[dict(key='coverage',title='Historical coverage',state='INSUFFICIENT',summary='Insufficient OOS months or source trades; expensive checks were skipped.',next_step='Collect more history or forward observations. Additional simulated paths cannot repair this blocker.')],historical_replicates=0,inner_precision_ok=None,
                prerequisites=options['prerequisites'],forward_execution=dict(status='PENDING'),limitations=LIMITATIONS,interpretation='Source evidence is inadequate; no confidence or deployment conclusion was fabricated.')
            continue
        horizons=RULES['evaluation_deadlines'] if phase=='evaluation' else [search.horizon_calendar_days]
        if phase=='funded' and (date.fromisoformat(c.period.last_session)-date.fromisoformat(c.period.first_session)).days+1<horizons[0]:raise ValueError('OOS must cover the frozen Funded horizon.')
        primary={};stress=[];total=len(horizons)*2+5;done=0;reused_paths=0
        def execute(candidate,n,horizon,label,**kw):
            nonlocal done,reused_paths
            runner.notify(label,done,total)
            key=sha256(canonical(dict(version=VERSION,implementation=implementation(),phase_implementation=phase_identity,
                configuration=asdict(candidate),search=asdict(search),source=binding['frozen_manifest'] if candidate.source==ic.source else check['manifest'],paths=n,horizon=horizon,scenario={k:asdict(v) if hasattr(v,'__dataclass_fields__') else v for k,v in kw.items()})).encode()).hexdigest()
            prior=analyses.load_refits(key,1) if analysis_id else {}
            source_row=is_rows[check['frozen_candidate_id']] if candidate.source==ic.source else row
            existing=source_row.get('paths',[])
            reusable=not kw and len(existing)==n and phase=='funded'
            if not kw and len(existing)==n and phase=='evaluation':
                observed=normalize_eval(existing,horizon)
                reusable=all(p['funded'] and p['calendar_days_to_funded']<=horizon for p in observed)
            if prior:value=prior[0]['replicate']['result'];reused_paths+=n
            elif reusable:
                value=dict(configuration=asdict(candidate),paths=existing,summary=summarize(existing,phase,horizon),reused_from='sealed_original_IS' if candidate.source==ic.source else 'verified_OOS_point_capture');reused_paths+=n
            else:value=runner.run(candidate,n,horizon,**kw)
            if analysis_id and not prior:analyses.save_refits(analysis_id,key,[dict(replicate=dict(replicate=0,result=value),precision=True,history_keys=[key],preparation_cache_bytes=0)])
            done+=1;runner.notify(label,done,total);return value
        for role,candidate in [('is',ic),('oos',c)]:
            primary[role]=[execute(candidate,RULES['account_paths'],h,f'{role.upper()} account comparison · {h} days') for h in horizons]
        for block in RULES['stress_blocks']:
            stress.append(dict(name=f'OOS block {block}',role='oos',**execute(c,RULES['stress_paths'],horizons[-1],f'OOS block {block}',block=block)))
        stress.append(dict(name='OOS additional execution cost',role='oos',**execute(c,RULES['stress_paths'],horizons[-1],'OOS execution cost stress',extra_cost=True)))
        grid=pd.bdate_range(ic.period.first_session,ic.period.last_session);mid=len(grid)//2
        for name,part in [('IS earlier half',grid[:mid]),('IS later half',grid[mid:])]:
            period=ResearchPeriod(str(part[0].date()),str(part[-1].date()))
            stress.append(dict(name=name,role='is',**execute(ic,RULES['stress_paths'],horizons[-1],name,period=period)))
        one_search=replace(search,candidates=(c,));one_check=[check]
        start_data=run_start_sensitivity(runs,one_search,one_check,saved,checkpoint,progress,datasets=datasets)
        start=start_data['candidates'][0]
        result=insights(primary,stress,start,phase,evidence,options['prerequisites'],
            optional_breach_cap=search.constraints.maximum_account_breach_probability if phase=='funded' else None)
        result['workload']=dict(nested_refits=0,declared_account_paths=sum(len(v['paths']) for values in primary.values() for v in values)+sum(len(v['paths']) for v in stress),reused_account_paths=reused_paths,chronological_starts=len(start['paths']))
        result['account_comparison']={role:[v['summary'] for v in values] for role,values in primary.items()}
        result['stress_scenarios']=[{k:v for k,v in s.items() if k!='paths'} for s in stress]
        result['start_sensitivity']={k:v for k,v in start.items() if k!='paths'}
        result['start_sensitivity']['observations']=[dict(start_date=p['start_date'],cutoff_exclusive=p['cutoff_exclusive'],**{k:p['result'].get(k) for k in ('outcome','acquisition_completed','paid_fees','calendar_days_to_funded','cash_received','pending_cash')}) for p in start['paths']]
        row['prop_qualification']=result
        details.append(dict(frozen_candidate_id=check['frozen_candidate_id'],primary=primary,stress=stress,account_starts=start_data))
        verify_phase_source(runs,ic.source,binding['frozen_manifest']['source'])
    if not reused:calculations['qualification_complementary']=details
    calculations.pop('qualification_bootstrap',None)
    capture_inputs(runs,Path(staged),replace(search,candidates=tuple(is_candidates),source_backtest_id=is_candidates[0].source.source_backtest_id),dict(candidates=captures))
    calculations.update(qualification_policy=saved,qualification_rules=deepcopy(RULES),qualification_implementation=implementation(),
        assessment_kind=options['kind'],selection_status='assessment_only_no_reselection')
    if options['kind']=='forward_review':
        from ..prop_sim_forward import verified_observation,execution_check
        forward,_=verified_observation(options['forward_capture'],options['simulation_id'],phase,options['base_report']['analysis_id'],analyses)
        cid=forward['source_check']['policy_snapshot']['package']['candidate_id'];row=next(r for r in calculations['candidates'] if r['frozen_candidate_id']==cid)
        if row['prop_qualification']['status']!='GO':raise ValueError('Forward review requires evidence ready for paper review.')
        row['prop_qualification']['forward_execution']=execution_check(forward,options['forward_capture']['reviewed_episode_ids'],options['forward_capture']['notes'])
        row['prop_qualification']['forward_execution']['source']=options['forward_capture'];calculations['forward_execution_review']=row['prop_qualification']['forward_execution']
    return calculations
