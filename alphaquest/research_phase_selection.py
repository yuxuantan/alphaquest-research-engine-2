"""Strict nested phase handoff and declared independent selection rules.

Account simulation and chronological replay remain in the existing phase owners.
This module only validates complete membership and freezes immutable identities.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
from .research_folds import SESSION_CONVENTION
from .prop.evaluation_optimization import pareto_sort
from .prop.funded_optimization import OBJECTIVE as FUNDED_OBJECTIVE
from .prop.phase_dispatch import module_for
from .prop.phase_profiles import SizingConfiguration

VERSION='nested-phase-selection-v1'


from .prop.adapter import canonical

def digest(value):return sha256(canonical(value).encode()).hexdigest()


def require(condition,message):
    if not condition:raise ValueError(message)


class Contract(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)


class EvaluationSelector(Contract):
    mode: Literal['pareto_family','min_cost_under_time_cap','min_time_under_cost_cap']='pareto_family'
    tie_policy: Literal['keep_all_exact_ties','configuration_id']='keep_all_exact_ties'
    maximum_cost_per_funded: Decimal | None=None
    maximum_expected_calendar_days: Decimal | None=None
    minimum_pass_probability: Decimal | None=None

    @field_validator('maximum_cost_per_funded','maximum_expected_calendar_days','minimum_pass_probability',mode='before')
    @classmethod
    def reject_bool(cls,value):
        if type(value) is bool:raise ValueError('Numeric limits cannot be booleans.')
        return value

    @model_validator(mode='after')
    def coherent(self):
        for value in (self.maximum_cost_per_funded,self.maximum_expected_calendar_days,self.minimum_pass_probability):
            if value is not None and (not value.is_finite() or value<0):raise ValueError('Selection limits must be finite nonnegative values.')
        if self.minimum_pass_probability is not None and self.minimum_pass_probability>1:raise ValueError('Pass probability is from 0 to 1.')
        if self.mode=='min_cost_under_time_cap' and self.maximum_expected_calendar_days is None:raise ValueError('Cost selection requires a predeclared time cap.')
        if self.mode=='min_time_under_cost_cap' and self.maximum_cost_per_funded is None:raise ValueError('Time selection requires a predeclared cost cap.')
        if self.mode=='pareto_family' and self.tie_policy!='keep_all_exact_ties':raise ValueError('The full frontier retains all exact objective ties.')
        return self


class FundedSelector(Contract):
    mode: Literal['maximum_expected_received_cash']='maximum_expected_received_cash'
    tie_policy: Literal['keep_all_exact_ties','configuration_id']='keep_all_exact_ties'
    minimum_expected_cash: Decimal | None=None

    @field_validator('minimum_expected_cash',mode='before')
    @classmethod
    def reject_bool(cls,value):
        if type(value) is bool:raise ValueError('Cash threshold cannot be boolean.')
        return value

    @model_validator(mode='after')
    def coherent(self):
        if self.minimum_expected_cash is not None and not self.minimum_expected_cash.is_finite():raise ValueError('Cash threshold must be finite.')
        return self


class Policy(Contract):
    micros: StrictInt=Field(ge=1,le=60)
    sizing: dict | None=None

    @model_validator(mode='after')
    def coherent(self):
        if self.sizing is not None:
            value=SizingConfiguration(**self.sizing)
            if value.policy['kind']=='fixed_contracts' and value.policy['contracts']!=self.micros:
                raise ValueError('Fixed policy quantity must equal the declared micros identity.')
        return self


class PhaseStudy(Contract):
    phase: Literal['evaluation','funded']
    profiles: list[dict]=Field(min_length=1)
    policies: list[Policy]=Field(min_length=1)
    simulation: dict
    sampling: dict
    costs: dict
    search_settings: dict
    selector: dict
    retry: dict | None=None

    @model_validator(mode='after')
    def coherent(self):
        (EvaluationSelector if self.phase=='evaluation' else FundedSelector).model_validate(self.selector)
        if len({canonical(profile) for profile in self.profiles})!=len(self.profiles):raise ValueError('Duplicate profile.')
        if len({canonical(policy.model_dump(mode='json')) for policy in self.policies})!=len(self.policies):raise ValueError('Duplicate sizing policy.')
        if self.phase=='funded' and self.retry is not None:raise ValueError('Funded selection cannot use evaluation retry economics.')
        require(not set(self.search_settings)&{'candidates','source_backtest_id','mode'},'Coordinator owns source membership and phase.')
        return self


def validate_native_policies(studies,required_baselines=()):
    """Preview-time rejection, before costly inner work or any outer reads."""
    for study in studies:
        for policy in study.policies:
            if policy.sizing is not None and SizingConfiguration(**policy.sizing).needs_stop:
                raise ValueError('native_rerun_required: a saved native path cannot support state-dependent risk sizing or cushion guards.')
    for baseline in required_baselines:
        if baseline.get('required') and baseline.get('source_kind')=='native_backtest' and baseline.get('sizing_kind')!='fixed_contracts':
            raise ValueError('required_baseline_unavailable: native risk baseline needs an account-state strategy rerun; it cannot be silently dropped.')


def complete_qualified_membership(plan_candidates,qualification):
    """Reject incomplete admission output; retain every PASS, not a ranking."""
    expected={candidate['id']:candidate for candidate in plan_candidates}
    require(len(expected)==len(plan_candidates),'Duplicate declared signal configurations.')
    rows=qualification['candidates'];actual={row['candidate_id']:row for row in rows}
    require(len(actual)==len(rows) and set(actual)==set(expected),'Qualification must report every declared configuration exactly once.')
    require(all(row['status'] in ('PASS','FAIL','INSUFFICIENT_EVIDENCE') for row in rows),'Unknown qualification status.')
    approved=sorted(id for id,row in actual.items() if row['status']=='PASS')
    require(sorted(qualification['approved_ids'])==approved and len(set(qualification['approved_ids']))==len(approved),'Approved IDs differ from complete PASS membership.')
    for id,row in actual.items():
        require(row['strategy_id']==expected[id]['strategy_id'] and canonical(row['parameters'])==canonical(expected[id]['parameters']),'Qualification strategy/parameters differ from frozen candidate identity.')
    insufficient=sorted(id for id,row in actual.items() if row['status']=='INSUFFICIENT_EVIDENCE')
    status='QUALIFIED_SET' if approved else 'INSUFFICIENT_EVIDENCE' if insufficient else 'NO_QUALIFIED_CONFIGURATION'
    return dict(status=status,configuration_ids=approved,configurations=[deepcopy(expected[id]) for id in approved],
                excluded=[dict(configuration_id=id,status=actual[id]['status'],reasons=actual[id].get('reasons',[])) for id in sorted(actual) if id not in approved],
                qualification_sha256=digest(qualification),insufficient_configuration_ids=insufficient)


def policy_training_metadata(campaign_id,outer,membership,input_identity):
    return dict(phase='inner',role='policy_train',campaign_id=campaign_id,outer_fold=outer['index'],
                window=deepcopy(outer['train']),information_cutoff_session=outer['train']['last_session'],
                qualification_sha256=membership['qualification_sha256'],input_identity=input_identity,
                cold_start=True,controlled_oos=False,
                selection_scope='approved configurations only; copied signal parameters, no signal reoptimization')


def build_training_context(plan,outer,membership,records,artifact_hashes):
    require(all(type(plan['session_inventory']['counts'][day]) is int and plan['session_inventory']['counts'][day]>0 for day in outer['train']['sessions']),'Every native training session requires actual observed bars.')
    expected=set(membership['configuration_ids'])
    require(set(records)==expected and set(artifact_hashes)==expected,'Every qualified configuration needs one complete outer-training report.')
    by_id={c['id']:c for c in membership['configurations']};sources={}
    for id in sorted(expected):
        record=records[id];meta=record['run_metadata'];research=meta.get('research',{})
        require(record['status']=='complete','Training report is incomplete.')
        require(research.get('phase')=='inner' and research.get('role')=='policy_train','Training source has wrong research role.')
        require(research.get('campaign_id')==plan['campaign_id'] and research.get('outer_fold')==outer['index'],'Training source belongs to another campaign/fold.')
        require(canonical(research.get('window'))==canonical(outer['train']) and research.get('information_cutoff_session')==outer['train']['last_session'],'Training source crosses the fold information boundary.')
        require(research.get('qualification_sha256')==membership['qualification_sha256'],'Training source qualification identity differs.')
        strategy=meta['strategy']
        require(strategy['id']==by_id[id]['strategy_id'] and canonical(strategy['parameters'])==canonical(by_id[id]['parameters']),'Signal parameters were changed during prop handoff.')
        expected_strategy=deepcopy(by_id[id].get('strategy'))
        if expected_strategy is not None:
            expected_strategy.pop('session_flattening',None)
            actual_strategy=deepcopy(strategy);actual_strategy.pop('session_flattening',None)
            require(canonical(actual_strategy)==canonical(expected_strategy),'Training strategy implementation provenance changed.')
        require(meta['dataset']['sha256']==plan['dataset']['sha256'],'Training dataset identity changed.')
        require(research.get('input_identity')==plan['input_identity'],'Training source protocol identity differs.')
        require(record['id'] not in sources,'One training report cannot masquerade as two configurations.')
        sources[record['id']]=dict(configuration_id=id,strategy_id=strategy['id'],parameters=deepcopy(strategy['parameters']),
            strategy_provenance_sha256=digest(strategy),manifest_sha256=digest(record),artifact_sha256=deepcopy(artifact_hashes[id]))
    result=dict(version='nested-phase-training-v1',campaign_id=plan['campaign_id'],outer_fold_index=outer['index'],
        qualification_sha256=membership['qualification_sha256'],input_identity=plan['input_identity'],engine_identity=plan['engine_identity'],
        train_window=deepcopy(outer['train']),information_cutoff_session=outer['train']['last_session'],
        qualified_configuration_ids=membership['configuration_ids'],training_sources=sources,
        session_inventory=deepcopy({day:plan['session_inventory']['counts'][day] for day in outer['train']['sessions']}))
    result['context_sha256']=digest(result)
    return result


def build_search(study,context):
    """Cartesian product only over all qualified sources and predeclared policies."""
    candidates=[]
    for run_id in sorted(context['training_sources']):
        for profile in sorted(study.profiles,key=canonical):
            for policy in sorted(study.policies,key=lambda p:canonical(p.model_dump(mode='json'))):
                row=dict(source=dict(source_backtest_id=run_id),profile=deepcopy(profile),micros=policy.micros,
                         simulation=deepcopy(study.simulation),sampling=deepcopy(study.sampling),costs=deepcopy(study.costs),
                         period=dict(first_session=context['train_window']['first_session'],last_session=context['train_window']['last_session']))
                if policy.sizing is not None:row['sizing']=deepcopy(policy.sizing)
                if study.retry is not None:row['retry']=deepcopy(study.retry)
                candidates.append(row)
    require(candidates,'An empty qualified set cannot launch a phase search.')
    if study.phase=='evaluation':
        constraints=EvaluationSelector.model_validate(study.selector).model_dump(mode='json',exclude_none=True)
        constraints={key:float(value) for key,value in constraints.items() if key not in ('mode','tie_policy')}
        declared=study.search_settings.get('constraints',{})
        require(not declared or canonical(declared)==canonical(constraints),'Evaluation constraints must match the predeclared selector limits.')
    raw=dict(mode=study.phase+'_optimization',source_backtest_id=min(context['training_sources']),candidates=candidates,**deepcopy(study.search_settings))
    if study.phase=='evaluation':raw['constraints']=constraints
    # Reuse the real phase contract, without running simulations or reading bars.
    search=module_for(study.phase).parse_request(raw)
    from .prop.phase_profiles import profile_settings, positive_integer
    for candidate in search.candidates:
        profile_settings(candidate.profile,candidate.costs)
        positive_integer('micros',candidate.micros,60 if study.phase=='evaluation' else 40)
        require(candidate.micros<=candidate.simulation.max_micros,'Position size exceeds the simulation exposure cap.')
    return json.loads(canonical(asdict(search)))


def _unresolved(calculations):
    return sorted(set(calculations.get('unresolved_candidates',[]))|{r['candidate_id'] for r in calculations['candidates'] if r['status']!='estimated'})


from .prop.phase_search import stable_phase_policy_identity as stable_policy_identity


def select_evaluation(calculations,selector):
    selector=EvaluationSelector.model_validate(selector)
    unresolved=_unresolved(calculations)
    if unresolved:return dict(status='INSUFFICIENT_EVIDENCE',selected_ids=[],unresolved_ids=unresolved,reason='complete_candidate_family_not_resolved')
    # Constraints and nondominance belong to the Evaluation owner. This layer
    # applies only the predeclared preference within its retained frontier.
    frontier=list(calculations['frontier'])
    feasible=[row for row in calculations['candidates'] if row.get('feasible',True)]
    excluded=[dict(candidate_id=row['candidate_id'],constraints=row.get('constraint_violations',[]))
              for row in calculations['candidates'] if not row.get('feasible',True)]
    require(set(frontier)<=set(row['candidate_id'] for row in feasible),'Evaluation frontier includes an excluded candidate.')
    if not frontier:return dict(status='NO_FEASIBLE_POLICY',selected_ids=[],excluded=excluded)
    ids=frontier
    if selector.mode!='pareto_family':
        by_id={row['candidate_id']:row for row in feasible}
        keys=('cost_per_funded','expected_calendar_days_to_funded') if selector.mode=='min_cost_under_time_cap' else ('expected_calendar_days_to_funded','cost_per_funded')
        point=lambda id:tuple(Decimal(str(by_id[id]['metrics'][key])) for key in keys)
        best=min(point(id) for id in frontier)
        ids=sorted(id for id in frontier if point(id)==best)
        if selector.tie_policy=='configuration_id':ids=sorted(ids,key=lambda id:stable_policy_identity(by_id[id],'evaluation'))[:1]
    return dict(status='FROZEN_FAMILY' if len(ids)>1 else 'FROZEN_POLICY',selected_ids=sorted(ids),
                feasible_frontier=frontier,excluded=excluded,selector=selector.model_dump(mode='json'),
                certification='estimated_training_economics_only; no future/provider certification')


def select_funded(calculations,selector,search_request):
    selector=FundedSelector.model_validate(selector)
    require(calculations.get('objective')==FUNDED_OBJECTIVE,'Funded objective must be expected trader receipts within its horizon.')
    unresolved=_unresolved(calculations)
    if unresolved:return dict(status='INSUFFICIENT_EVIDENCE',selected_ids=[],unresolved_ids=unresolved,reason='complete_candidate_family_not_resolved')
    # Risk constraints have already been applied by the independent funded owner.
    feasible=[row for row in calculations['candidates'] if row['feasible']]
    if selector.minimum_expected_cash is not None:
        feasible=[row for row in feasible if row['metrics'][FUNDED_OBJECTIVE] is not None and Decimal(str(row['metrics'][FUNDED_OBJECTIVE]))>=selector.minimum_expected_cash]
    if not feasible:return dict(status='NO_FEASIBLE_POLICY',selected_ids=[])
    require(all(row['metrics'][FUNDED_OBJECTIVE] is not None and Decimal(str(row['metrics'][FUNDED_OBJECTIVE])).is_finite() for row in feasible),'Missing funded cash objective.')
    best=max(Decimal(str(row['metrics'][FUNDED_OBJECTIVE])) for row in feasible)
    ids=sorted(row['candidate_id'] for row in feasible if Decimal(str(row['metrics'][FUNDED_OBJECTIVE]))==best)
    if selector.tie_policy=='configuration_id':
        by_id={row['candidate_id']:row for row in feasible}
        ids=sorted(ids,key=lambda id:stable_policy_identity(by_id[id],'funded'))[:1]
    return dict(status='FROZEN_FAMILY' if len(ids)>1 else 'FROZEN_POLICY',selected_ids=ids,
        selector=selector.model_dump(mode='json'),constraints=deepcopy(search_request.get('constraints',{})),
        horizon_calendar_days=search_request['horizon_calendar_days'],receipt_delay_calendar_days=search_request['receipt_delay_calendar_days'],
        certification='point-estimate choice; Monte Carlo error is not total future uncertainty')


def study_defaults():
    """Current local model defaults; fees/calendar/settlement are declarations."""
    from .prop.phase_profiles import EvaluationProfile, FundedProfile, rule_version
    from .prop.evaluation_optimization import SequentialRetry
    profiles = dict(
        evaluation=[asdict(EvaluationProfile('apex-50k-eod',rule_version('apex-50k-eod'),'30','40'))],
        funded=[asdict(FundedProfile(name,rule_version(name))) for name in ('apex-50k-eod','lucidflex-50k')])
    common=dict(policies=[dict(micros=1),dict(micros=3)],simulation=dict(simulations=256,seed=42,max_micros=40),
                costs=dict(mode='source'),selector={})
    calendar=dict(closures=[],timezone='America/Chicago',version='user-declared-weekdays-v1')
    evaluation=dict(common,phase='evaluation',profiles=[profiles['evaluation'][0]],
        sampling=dict(block_weekdays=5,chain_simulations=256,chain_seed=45),
        retry=asdict(SequentialRetry()),search_settings=dict(calendar=calendar),
        selector=EvaluationSelector().model_dump(mode='json'))
    funded=dict(common,phase='funded',profiles=[profiles['funded'][0]],sampling=dict(block_weekdays=5),
        search_settings=dict(calendar=calendar,receipt_delay_calendar_days=0,constraints={},
                             bootstrap_replicates=100,bootstrap_seed=137,near_tie_cash=0),
        selector=FundedSelector().model_dump(mode='json'))
    return dict(economic_studies=dict(evaluation=evaluation,funded=funded),economic_profiles=profiles)


def resolved_study(study, outer):
    """Target dates are fold metadata, fixed before outcome/bar evaluation."""
    value=study.model_dump(mode='json')
    settings=value['search_settings']
    start=outer['test']['first_session']
    cutoff=(date.fromisoformat(outer['test']['last_session'])+timedelta(days=1)).isoformat()
    calendar=settings.setdefault('calendar',{})
    closures=calendar.get('closures',[])
    require(type(closures) is list and len(set(closures))==len(closures),'Declare unique calendar closure dates.')
    require(all(type(day) is str and date.fromisoformat(day).isoformat()==day for day in closures),'Calendar closures require canonical dates.')
    if 'start_dates' in calendar and calendar['start_dates']!=[start]:
        raise ValueError('Nested phase forecast start dates are derived from the outer fold.')
    calendar['start_dates']=[start]
    horizon=(date.fromisoformat(cutoff)-date.fromisoformat(start)).days
    if study.phase=='funded':
        if 'horizon_calendar_days' in settings and settings['horizon_calendar_days']!=horizon:
            raise ValueError('Nested funded forecast horizon must match the outer fold cutoff.')
        settings['horizon_calendar_days']=horizon
        coverage=cutoff
    else:
        from .prop.evaluation_optimization import SequentialRetry
        retry=SequentialRetry(**(value['retry'] or {}))
        coverage=(date.fromisoformat(start)+timedelta(days=retry.max_calendar_days)).isoformat()
    if 'coverage_end' in calendar and calendar['coverage_end']<coverage:
        raise ValueError('Declared forecast calendar does not cover the frozen horizon or acquisition guard.')
    calendar.setdefault('coverage_end',coverage)
    # Declare closures once for the full development history. Each fold keeps
    # only closures in its applicable forecast coverage without learning them
    # from missing bars.
    calendar['closures']=[day for day in calendar.get('closures',[]) if start<=day<=calendar['coverage_end']]
    return PhaseStudy.model_validate(value)


def outer_window(outer):
    return dict(outer['test'],cutoff_date_exclusive=(date.fromisoformat(outer['test']['last_session'])+timedelta(days=1)).isoformat())


def freeze_policy(campaign_id,outer,study,context,report,report_sha256,row):
    """A self-verifiable package; its enclosing journal supplies the read gate."""
    window=outer_window(outer)
    calendar=deepcopy(report['request']['calendar'])
    calendar['coverage_end']=window['cutoff_date_exclusive']
    calendar['closures']=[day for day in calendar.get('closures',[]) if window['first_session']<=day<window['cutoff_date_exclusive']]
    result=dict(schema_version='nested-phase-freeze-v1',campaign_id=campaign_id,outer_fold_index=outer['index'],
        phase=study.phase,candidate_id=row['candidate_id'],configuration=deepcopy(row['manifest']['configuration']),
        strategy=deepcopy(row['manifest']['strategy']),training_context_sha256=context['context_sha256'],
        training_analysis_id=report['id'],training_report_sha256=report_sha256,
        training_candidate_manifest_sha256=digest(row['manifest']),implementation=deepcopy(report['implementation']),
        selector=(EvaluationSelector if study.phase=='evaluation' else FundedSelector).model_validate(study.selector).model_dump(mode='json'),
        provider_rules=deepcopy(report.get('provider_rules')),deployment_readiness=deepcopy(report.get('deployment_readiness')),
        outer_window=window,calendar=calendar,
        interpretation='Frozen training selection; chronological outer observations have not been used.')
    if study.phase=='funded':
        result['receipt_amount_convention']='kernel_entitlement_unrounded'
        result['receipt_delay_calendar_days']=report['request']['receipt_delay_calendar_days']
    result['package_sha256']=digest(result)
    return result
