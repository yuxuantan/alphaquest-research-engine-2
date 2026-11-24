"""OOS integration for frozen native percentage policies; no candidate selection."""
from copy import deepcopy
from dataclasses import asdict,replace
from hashlib import sha256
from pathlib import Path
from .adapter import canonical


def qualify_native(calculations,search,assessment,runs,checks,checkpoint,progress,staged,analyses,*,analysis_id,datasets):
    from .oos_qualification import RULES,implementation,evidence,definitions,decide,LIMITATIONS
    from .native_oos_bootstrap import run,VERSION
    from .native_search import prepare_native_candidate,verify_native_candidate
    from .phase_profiles import SavedTradeSource,ResearchPeriod,verify_phase_source
    from .phase_search import capture_inputs,check_candidates
    from .assessment_review import distribution
    options=assessment['prop_sim_review'];saved=options['policy']
    if options['implementation']!=implementation() or saved['rules']!=RULES:raise ValueError('Native qualification implementation or rules changed.')
    if saved['policy_sha256']!=sha256(canonical({k:v for k,v in saved.items() if k!='policy_sha256'}).encode()).hexdigest():raise ValueError('Qualification policy identity changed.')
    phase=search.mode.removesuffix('_optimization');details=[];captures=[];candidates=[];cache={}
    configs={canonical(asdict(c)):c for c in search.candidates}
    reused=calculations.get('qualification_implementation')==implementation() and calculations.get('qualification_native_model')==VERSION
    for index,row in enumerate(calculations['candidates']):
        check=next(c for c in checks if c['candidate_id']==row['candidate_id']);candidate=configs[canonical(check['manifest']['configuration'])]
        binding=next(b for b in assessment['sources'] if b['frozen_candidate_id']==check['frozen_candidate_id'])
        original=binding['frozen_manifest']['configuration']
        is_candidate=replace(candidate,source=SavedTradeSource(**original['source']),period=ResearchPeriod(**original['period']))
        verify_phase_source(runs,is_candidate.source,binding['frozen_manifest']['source'])
        is_search=replace(search,candidates=(is_candidate,),source_backtest_id=is_candidate.source.source_backtest_id)
        is_check=check_candidates(runs,is_search,datasets=datasets)[0]
        candidates.append(is_candidate);captures.append(dict(candidate_id=check['frozen_candidate_id'],manifest=is_check['manifest']))
        row['outcome_summary']=distribution(row,phase)
        if reused and row.get('prop_qualification'):continue
        evidence_rows=evidence(check,row,phase,getattr(search,'horizon_calendar_days',None))
        base=assessment['is_metrics'][check['frozen_candidate_id']]
        point={key:row['metrics'][key]/base[key] if row['metrics'].get(key) is not None and base.get(key,0)>0 else None for key,_,_,_ in definitions(phase)}
        if all(e['passed'] for e in evidence_rows):
            is_inputs,_=prepare_native_candidate(datasets,runs,is_search,is_candidate,is_check,checkpoint=checkpoint,cache=cache,progress=progress)
            oos_inputs,_=prepare_native_candidate(datasets,runs,search,candidate,check,private_admission=True,checkpoint=checkpoint,cache=cache,progress=progress)
            def notify(value):progress(dict(value,candidate_index=index+1,candidate_count=len(calculations['candidates'])))
            data=run(is_inputs,oos_inputs,is_candidate,candidate,search,checkpoint,notify,resume=(analyses,analysis_id) if analysis_id else None)
            result=decide(point,[r['ratios'] for r in data['replicates']],phase,evidence_rows,inner_precision_ok=data['inner_precision_ok'])
            details.append(dict(frozen_candidate_id=check['frozen_candidate_id'],**data))
            verify_native_candidate(datasets,runs,is_search,is_candidate,is_check,cache=cache)
            verify_native_candidate(datasets,runs,search,candidate,check,private_admission=True,cache=cache)
        else:result=decide(point,[],phase,evidence_rows,inner_precision_ok=False)
        result.update(prerequisites=options['prerequisites'],forward_execution=dict(status='PENDING',minimum_sessions=20,minimum_closed_trades=30),
            limitations=LIMITATIONS+['Native outer resampling changes origin frequencies; all original prices and prior-only prefixes remain intact. Missing calendar-shape evidence is inconclusive.'],retrospective=True,native_model=VERSION)
        if not options['prerequisites']['passed']:result['status']='NO_GO'
        row['prop_qualification']=result
    if not reused:calculations['qualification_bootstrap']=details
    capture_inputs(runs,Path(staged),replace(search,candidates=tuple(candidates),source_backtest_id=candidates[0].source.source_backtest_id),dict(candidates=captures))
    calculations.update(qualification_policy=saved,qualification_rules=deepcopy(RULES),qualification_implementation=implementation(),
        qualification_native_model=VERSION,assessment_kind=options['kind'],selection_status='assessment_only_no_reselection')
    if options['kind']=='account_starts':
        from .native_account_starts import run as start_replay
        starts=[]
        for check in checks:
            candidate=configs[canonical(check['manifest']['configuration'])]
            if saved['phase']!=phase or saved['start_plan']['period']!=asdict(candidate.period):raise ValueError('Native account-start coverage differs from the frozen policy.')
            inputs,_=prepare_native_candidate(datasets,runs,search,candidate,check,private_admission=True,checkpoint=checkpoint,cache=cache,progress=progress)
            row=start_replay(inputs,candidate,search,saved,checkpoint,progress);row['frozen_candidate_id']=check['frozen_candidate_id'];starts.append(row)
            verify_native_candidate(datasets,runs,search,candidate,check,private_admission=True,cache=cache)
        calculations['account_start_sensitivity']=dict(plan=saved['start_plan'],candidates=starts,status='COMPLETE' if saved['start_plan']['starts'] else 'INCONCLUSIVE',simulations=len(starts)*len(saved['start_plan']['starts']),interpretation='Actual chronological native percentage execution at coverage-only starts. No resampling, replacement or selection; overlapping windows are dependent.')
    if options['kind']=='forward_review':
        from ..prop_sim_forward import verified_observation,execution_check
        forward,_=verified_observation(options['forward_capture'],options['simulation_id'],phase,options['base_report']['analysis_id'],analyses)
        candidate_id=forward['source_check']['policy_snapshot']['package']['candidate_id']
        row=next(r for r in calculations['candidates'] if r['frozen_candidate_id']==candidate_id)
        if row['prop_qualification']['status']!='GO':raise ValueError('Forward review requires historical GO.')
        row['prop_qualification']['forward_execution']=execution_check(forward,options['forward_capture']['reviewed_episode_ids'],options['forward_capture']['notes'])
        row['prop_qualification']['forward_execution']['source']=options['forward_capture'];calculations['forward_execution_review']=row['prop_qualification']['forward_execution']
    return calculations
