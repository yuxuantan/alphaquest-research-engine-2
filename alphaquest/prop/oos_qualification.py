"""Frozen Prop Sim historical non-inferiority assessment, not a new account engine.

Resample source-session blocks, then call the existing phase owners unchanged.
Saved MC paths are never the historical resampling units. Earlier reports stay
readable; this policy has its own implementation identity and sealed artifacts.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import numpy as np
import pandas as pd

from .adapter import canonical

RULES = dict(version='prop-oos-qualification-v1', minimum_complete_months=12,
    minimum_closed_trades=100, evaluation_cost_ratio_max=1.5,
    evaluation_time_ratio_max=1.5, funded_receipts_ratio_min=.70,
    confidence=.95, maximum_family_tests=12, historical_replicates=10000,
    history_seed=13742, minimum_outer_block_weekdays=5,
    maximum_inner_relative_standard_error=.05,
    forward_minimum_sessions=20, forward_minimum_closed_trades=30,
    forward_maximum_unexplained_discrepancies=0)
LIMITATIONS = [
    'Nominal block-bootstrap percentile bounds assume a representative, weakly dependent stationary history. They are not guaranteed future coverage.',
    'The family budget covers at most four frozen Evaluation sizes × two metrics plus four Funded sizes × one metric. It does not repair earlier adaptive strategy search or already-accessed OOS.',
    'Inner account paths retain the requested count and fixed random streams. Their numerical error is checked separately; MC precision is not additional market history.',
    'GO qualifies the historical model for forward execution review, not provider certification, full replacement-account profitability or automatic live trading.',
]


def implementation():
    from . import assessment_review,oos_bootstrap,parallel
    from .. import prop_sim_forward,forward_monitoring
    return dict(version=RULES['version'], files={
        'oos_qualification.py':sha256(Path(__file__).read_bytes()).hexdigest(),
        'assessment_review.py':sha256(Path(assessment_review.__file__).read_bytes()).hexdigest(),
        'oos_bootstrap.py':sha256(Path(oos_bootstrap.__file__).read_bytes()).hexdigest(),
        'parallel.py':sha256(Path(parallel.__file__).read_bytes()).hexdigest(),
        'prop_sim_forward.py':sha256(Path(prop_sim_forward.__file__).read_bytes()).hexdigest()},
        forward_implementation=forward_monitoring.implementation_identity(),numpy=np.__version__)


def policy(phase, period, horizon, *, prior_access=True, closures=()):
    from .assessment_review import start_plan
    value=dict(version=RULES['version'],phase=phase,rules=deepcopy(RULES),
        implementation=implementation(),declared_at_utc=datetime.now(timezone.utc).isoformat(),
        declaration_timing='retrospective' if prior_access else 'before_first_prop_oos_result',
        start_plan=start_plan(period,180 if phase=='evaluation' else horizon,5,closures),
        interpretation='Fixed robustness policy; no required dollar declaration. Strategy OOS was already accessed. Economic limits remain optional historical assessments.')
    value['policy_sha256']=sha256(canonical(value).encode()).hexdigest()
    return value


def complete_months(period):
    first,last=map(date.fromisoformat,(period['first_session'],period['last_session']))
    return sum(first<=stamp.date() and (stamp+pd.offsets.MonthEnd()).date()<=last
               for stamp in pd.date_range(first.replace(day=1),last,freq='MS'))


def definitions(phase):
    if phase=='evaluation':
        return [('cost_per_funded','Acquisition cost',1.5,True),
                ('expected_calendar_days_to_funded','Funding time',1.5,True)]
    if phase=='funded':return [('expected_funded_cash_payouts_within_horizon','Mean trader receipts',.70,False)]
    raise ValueError('Unknown qualification phase.')


def evidence(check, point_row, phase, horizon):
    manifest=check['manifest'];period=manifest['configuration']['period']
    months=complete_months(period);trades=manifest['source']['backtest']['summary']['trades_taken']
    days=(date.fromisoformat(period['last_session'])-date.fromisoformat(period['first_session'])).days+1
    result=[dict(label='Complete OOS calendar months',actual=months,required=12,passed=months>=12),
        dict(label='Closed OOS source trades',actual=trades,required=100,passed=trades>=100),
        dict(label='Complete account estimates',actual=point_row['status'],required='estimated',passed=point_row['status']=='estimated')]
    if phase=='funded':result.append(dict(label='Full frozen Funded horizon',actual=days,required=horizon,passed=days>=horizon))
    return result


def decide(point, replicates, phase, evidence_rows, *, inner_precision_ok=True):
    """Simultaneous nominal 95% bounds; no-go needs an opposite-side bound."""
    tail=(1-RULES['confidence'])/(2*RULES['maximum_family_tests'])
    checks=[]
    for key,label,limit,maximum in definitions(phase):
        values=[r.get(key) for r in replicates]
        finite=bool(values) and all(v is not None and np.isfinite(v) and v>=0 for v in values)
        low,high=map(float,np.quantile(values,[tail,1-tail],method='inverted_cdf')) if finite else (None,None)
        status=('PASS' if (high<=limit if maximum else low>=limit) else
                'FAIL' if (low>limit if maximum else high<limit) else 'INSUFFICIENT_EVIDENCE') if finite else 'INSUFFICIENT_EVIDENCE'
        checks.append(dict(metric=key,label=label,point_ratio=point.get(key),lower=low,upper=high,
            limit=limit,direction='maximum' if maximum else 'minimum',status=status))
    adequate=all(row['passed'] for row in evidence_rows) and inner_precision_ok
    status=('INSUFFICIENT_EVIDENCE' if not adequate else 'NO_GO' if any(c['status']=='FAIL' for c in checks)
            else 'GO' if all(c['status']=='PASS' for c in checks) else 'INSUFFICIENT_EVIDENCE')
    return dict(status=status,evidence=evidence_rows,checks=checks,inner_precision_ok=inner_precision_ok,
        confidence=RULES['confidence'],family_test_budget=RULES['maximum_family_tests'],tail_probability=tail,
        historical_replicates=len(replicates),interpretation='GO supports forward review under the saved historical model. Insufficient evidence is not approval. The bounds do not imply a 95% probability of future success.')


def _means(days,candidate,search,checkpoint,*,funded_preparation=None):
    """Same local phase calculation and path counts as the admitted search."""
    from .evaluation_profiles import calendar_evaluation_paths
    from .funded_profiles import _dated_funded_paths
    if candidate.sizing is not None:raise ValueError('Qualification currently supports the Prop Sim fixed-quantity saved-source policy only.')
    if search.mode=='funded_optimization':
        paths,_,_=_dated_funded_paths(days,candidate.profile,candidate.micros,search.horizon_calendar_days,
            search.calendar,search.receipt_delay_calendar_days,candidate.simulation,candidate.sampling,checkpoint=checkpoint,
            preparation=funded_preparation)
        cash=np.array([p['cash_received'] for p in paths]);mean=float(cash.mean())
        groups=[cash[[p['start_date']==s for p in paths]] for s in search.calendar.start_dates]
        se=float(np.sqrt(sum(np.var(g,ddof=1)/len(g) for g in groups))/len(groups))
        return {'expected_funded_cash_payouts_within_horizon':mean},se/mean if mean>0 else None
    if candidate.profile.profile_id=='lucidflex-50k':
        paths,_=calendar_evaluation_paths(days,candidate.profile,candidate.micros,candidate.simulation,
            candidate.sampling,candidate.retry,search.calendar,checkpoint=checkpoint)
        if not all(p['acquisition_completed'] for p in paths):return {},None
        arrays={'cost_per_funded':[p['paid_fees'] for p in paths],
                'expected_calendar_days_to_funded':[p['calendar_days_to_funded'] for p in paths]}
        means={k:float(np.mean(v)) for k,v in arrays.items()}
        errors=[float(np.std(v,ddof=1)/np.sqrt(len(v)))/means[k] for k,v in arrays.items() if means[k]>0]
        return means,max(errors) if len(errors)==2 else None
    from .native_analysis import evaluation_model
    from .phase_profiles import profile_settings
    from .evaluation_optimization import acquisition_metrics
    settings=profile_settings(candidate.profile,candidate.costs)
    checkpoint()
    raw=evaluation_model(days,candidate.micros,candidate.simulation.simulations,candidate.simulation.seed,
        candidate.sampling.block_weekdays,settings,max_micros=candidate.simulation.max_micros)
    component=SimpleNamespace(outcomes=[str(v) for v in raw['outcomes']],
        duration_weekdays=[int(v) for v in raw['days']],censoring=SimpleNamespace(censored_paths=0))
    result=acquisition_metrics(component,candidate.profile,candidate.retry,search.calendar,candidate.sampling)
    metrics=result['metrics'];keys=('cost_per_funded','expected_calendar_days_to_funded')
    means={k:float(metrics[k]) for k in keys if metrics.get(k) is not None}
    errors=[result['uncertainty'].get(se)/means[k] for k,se in zip(keys,('cost_se','calendar_mean_se'))
        if means.get(k,0)>0 and result['uncertainty'].get(se) is not None]
    return means,float(max(errors)) if len(errors)==2 else None


def _book_classes(days):
    classes={};codes=[]
    for day in days:
        key=canonical(day)
        if key not in classes:classes[key]=len(classes)
        codes.append(classes[key])
    return np.asarray(codes,dtype=np.int32)


def historical_ratios(is_days,oos_days,is_candidate,oos_candidate,search,checkpoint,progress):
    from .oos_bootstrap import run
    return run(is_days,oos_days,is_candidate,oos_candidate,search,checkpoint,progress)


def qualify(calculations,search,assessment,runs,checks,checkpoint,progress,staged,analyses):
    from .assessment_review import distribution,run_start_sensitivity
    from .phase_profiles import SavedTradeSource,ResearchPeriod,prepare_phase_source,verify_phase_source
    from .phase_search import capture_inputs
    options=assessment['prop_sim_review'];saved=options['policy']
    if options['implementation']!=implementation() or saved['rules']!=RULES:
        raise ValueError('Qualification implementation or policy changed after declaration.')
    if saved['policy_sha256']!=sha256(canonical({k:v for k,v in saved.items() if k!='policy_sha256'}).encode()).hexdigest():
        raise ValueError('Qualification policy identity changed.')
    phase=search.mode.removesuffix('_optimization');detail=[];is_candidates=[];is_captures=[]
    reused=calculations.get('qualification_implementation')==implementation() and calculations.get('qualification_rules')==RULES
    eligible_count=sum(all(e['passed'] for e in evidence(
        next(c for c in checks if c['candidate_id']==row['candidate_id']),row,phase,
        getattr(search,'horizon_calendar_days',None))) for row in calculations['candidates'])
    for row in calculations['candidates']:
        check=next(c for c in checks if c['candidate_id']==row['candidate_id'])
        candidate=next(c for c in search.candidates if asdict(c)==check['manifest']['configuration'])
        binding=next(m for m in assessment['sources'] if m['frozen_candidate_id']==check['frozen_candidate_id'])
        original=binding['frozen_manifest']['configuration']
        is_candidate=replace(candidate,source=SavedTradeSource(**original['source']),period=ResearchPeriod(**original['period']))
        verify_phase_source(runs,is_candidate.source,binding['frozen_manifest']['source'])
        is_candidates.append(is_candidate)
        snapshot,is_days,_=prepare_phase_source(runs,is_candidate.source,is_candidate.profile,is_candidate.micros,
            is_candidate.simulation,is_candidate.period,is_candidate.costs,is_candidate.sizing)
        is_captures.append(dict(candidate_id=check['frozen_candidate_id'],manifest=dict(configuration=asdict(is_candidate),source=snapshot)))
        row['outcome_summary']=distribution(row,phase)
        evidence_rows=evidence(check,row,phase,getattr(search,'horizon_calendar_days',None))
        if reused and row.get('prop_qualification'):
            continue
        point={key:row['metrics'][key]/assessment['is_metrics'][check['frozen_candidate_id']][key]
            if row['metrics'].get(key) is not None and assessment['is_metrics'][check['frozen_candidate_id']].get(key,0)>0 else None
            for key,_,_,_ in definitions(phase)}
        if all(e['passed'] for e in evidence_rows):
            oos_snapshot,oos_days,_=prepare_phase_source(runs,candidate.source,candidate.profile,candidate.micros,
                candidate.simulation,candidate.period,candidate.costs,candidate.sizing)
            def refit_progress(value):
                progress(dict(value,candidate_index=len(detail)+1,candidate_count=eligible_count,
                    overall_completed=len(detail)*value['total']+value['completed'],
                    overall_total=eligible_count*value['total']))
            data=historical_ratios(is_days,oos_days,is_candidate,candidate,search,checkpoint,refit_progress)
            verify_phase_source(runs,candidate.source,oos_snapshot)
            result=decide(point,[r['ratios'] for r in data['replicates']],phase,evidence_rows,inner_precision_ok=data['inner_precision_ok'])
            detail.append(dict(frozen_candidate_id=check['frozen_candidate_id'],**data))
        else:result=decide(point,[],phase,evidence_rows,inner_precision_ok=False)
        result.update(prerequisites=options['prerequisites'],forward_execution=dict(status='PENDING',minimum_sessions=20,minimum_closed_trades=30),
            limitations=LIMITATIONS,retrospective=True)
        if not options['prerequisites']['passed']:result['status']='NO_GO'
        row['prop_qualification']=result
        verify_phase_source(runs,is_candidate.source,snapshot)
    if not reused:calculations['qualification_bootstrap']=detail
    capture_inputs(runs,Path(staged),replace(search,candidates=tuple(is_candidates),
        source_backtest_id=is_candidates[0].source.source_backtest_id),dict(candidates=is_captures))
    calculations.update(qualification_policy=saved,qualification_rules=deepcopy(RULES),qualification_implementation=implementation(),
        assessment_kind=options['kind'],selection_status='assessment_only_no_reselection')
    calculations.pop('account_start_sensitivity',None)
    if options['kind']=='account_starts':
        calculations['account_start_sensitivity']=run_start_sensitivity(runs,search,checks,saved,checkpoint,progress)
    if options['kind']=='forward_review':
        from ..prop_sim_forward import verified_observation,execution_check
        forward,records=verified_observation(options['forward_capture'],options['simulation_id'],phase,
            options['base_report']['analysis_id'],analyses)
        candidate_id=forward['source_check']['policy_snapshot']['package']['candidate_id']
        row=next(r for r in calculations['candidates'] if r['frozen_candidate_id']==candidate_id)
        if row['prop_qualification']['status']!='GO':raise ValueError('Forward review requires historical GO.')
        row['prop_qualification']['forward_execution']=execution_check(forward,
            options['forward_capture']['reviewed_episode_ids'],options['forward_capture']['notes'])
        row['prop_qualification']['forward_execution']['source']=options['forward_capture']
        calculations['forward_execution_review']=row['prop_qualification']['forward_execution']
    return calculations
