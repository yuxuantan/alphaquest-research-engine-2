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

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator
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
    mode: Literal['maximum_expected_received_cash','conservative_expected_received_cash']='maximum_expected_received_cash'
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
        if self.phase=='funded':
            mode=FundedSelector.model_validate(self.selector).mode
            if (mode=='conservative_expected_received_cash') != (self.search_settings.get('conservative_objective') is not None):
                raise ValueError('Conservative funded selection requires its explicit historical-mean objective configuration; maximum mean selection must omit it.')
        require(not set(self.search_settings)&{'candidates','source_backtest_id','mode'},'Coordinator owns source membership and phase.')
        return self


class BaselineDeclaration(Contract):
    """A predeclared measured reference, never an automatically qualified policy."""
    id: str = Field(min_length=1,max_length=120)
    phase: Literal['evaluation','funded']
    source_configuration_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    profile: dict
    policy: Policy
    required: StrictBool=True

    @model_validator(mode='after')
    def coherent(self):
        if not self.id.strip() or self.id!=self.id.strip():
            raise ValueError('Reference ID must be a nonempty readable name without surrounding whitespace.')
        return self


def baseline_study(reference,studies,candidates):
    """Resolve only declared signal/profile membership; no performance input."""
    matches=[c for c in candidates if c['id']==reference.source_configuration_id]
    require(len(matches)==1,'Reference source configuration is absent or stale; preview the current declared sources.')
    phase=[study for study in studies if study.phase==reference.phase]
    require(len(phase)==1,'Each reference requires its declared independent phase study.')
    study=phase[0]
    if (reference.policy.sizing is not None and SizingConfiguration(**reference.policy.sizing).needs_stop
            and study.search_settings.get('native_execution') is None):
        raise ValueError('required_baseline_unavailable: native risk references require the explicit native strategy execution backend.')
    require(any(canonical(reference.profile)==canonical(profile) for profile in study.profiles),
            'Reference profile must match a declared profile in the same phase study.')
    value=study.model_dump(mode='json')
    value['profiles']=[reference.profile];value['policies']=[reference.policy.model_dump(mode='json')]
    return PhaseStudy.model_validate(value),matches[0]


def validate_native_policies(studies,required_baselines=()):
    """Preview-time rejection, before costly inner work or any outer reads."""
    for study in studies:
        for policy in study.policies:
            if study.search_settings.get('native_execution') is not None:
                continue
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


def application_scope(outer, *, context=False):
    """Terminal applications have their own authority, never a fabricated fold."""
    if 'application_id' not in outer:
        return {('outer_fold_index' if context else 'outer_fold'): outer['index']}
    from uuid import UUID
    require('index' not in outer and 'outer_fold' not in outer and 'outer_fold_index' not in outer,
            'A terminal procedure application cannot claim an outer-fold identity.')
    require(type(outer['application_id']) is str and UUID(outer['application_id']).hex == outer['application_id'],
            'Procedure application requires a canonical identifier.')
    value=outer.get('procedure_sha256')
    require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),
            'Procedure application requires a frozen procedure hash.')
    require(outer.get('application_role') in ('final_fit','current_development'), 'Unknown procedure application role.')
    return {key:outer[key] for key in ('application_id','procedure_sha256','application_role')}


def training_role(outer, reference=False):
    if 'application_id' in outer:
        return 'procedure_reference_train' if reference else 'procedure_policy_train'
    return 'baseline_train' if reference else 'policy_train'


def policy_training_metadata(campaign_id,outer,membership,input_identity):
    return dict(phase='inner',role=training_role(outer),campaign_id=campaign_id,**application_scope(outer),
                window=deepcopy(outer['train']),information_cutoff_session=outer['train']['last_session'],
                qualification_sha256=membership['qualification_sha256'],input_identity=input_identity,
                cold_start=True,controlled_oos=False,
                selection_scope='approved configurations only; copied signal parameters, no signal reoptimization')


def _training_context_sources(plan,outer,candidates,records,artifact_hashes,role,evidence):
    require(all(type(plan['session_inventory']['counts'][day]) is int and plan['session_inventory']['counts'][day]>0 for day in outer['train']['sessions']),'Every native training session requires actual observed bars.')
    by_id={c['id']:c for c in candidates};expected=set(by_id)
    require(set(records)==expected and set(artifact_hashes)==expected,'Every admitted configuration needs one complete outer-training report.')
    sources={}
    for id in sorted(expected):
        record=records[id];meta=record['run_metadata'];research=meta.get('research',{})
        require(record['status']=='complete','Training report is incomplete.')
        require(research.get('phase')=='inner' and research.get('role')==role,'Training source has wrong research role.')
        require(research.get('campaign_id')==plan['campaign_id'] and all(research.get(k)==v for k,v in application_scope(outer).items()),'Training source belongs to another campaign/fold/application.')
        if 'application_id' in outer:
            require('outer_fold' not in research,'Terminal source must not claim an outer fold.')
        require(canonical(research.get('window'))==canonical(outer['train']) and research.get('information_cutoff_session')==outer['train']['last_session'],'Training source crosses the fold information boundary.')
        require(all(canonical(research.get(key))==canonical(value) for key,value in evidence.items()),'Training source admission evidence differs.')
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
    return dict(campaign_id=plan['campaign_id'],**application_scope(outer,context=True),
        input_identity=plan['input_identity'],engine_identity=plan['engine_identity'],
        train_window=deepcopy(outer['train']),information_cutoff_session=outer['train']['last_session'],
        training_sources=sources,session_inventory=deepcopy({day:plan['session_inventory']['counts'][day] for day in outer['train']['sessions']}))


def build_training_context(plan,outer,membership,records,artifact_hashes):
    result=_training_context_sources(plan,outer,membership['configurations'],records,artifact_hashes,training_role(outer),
        dict(qualification_sha256=membership['qualification_sha256']))
    result.update(version=('procedure-training-v1' if 'application_id' in outer else 'nested-phase-training-v1'),qualification_sha256=membership['qualification_sha256'],
        qualified_configuration_ids=membership['configuration_ids'])
    result['context_sha256']=digest(result)
    return result


def reference_training_metadata(campaign_id,outer,reference,input_identity):
    declarations=[reference.model_dump(mode='json')]
    return dict(phase='inner',role=training_role(outer,True),campaign_id=campaign_id,**application_scope(outer),
        window=deepcopy(outer['train']),information_cutoff_session=outer['train']['last_session'],
        reference_ids=[reference.id],reference_declaration_sha256=digest(declarations),
        admission_scope='predeclared_reference',input_identity=input_identity,cold_start=True,
        recommendation_eligible=False,controlled_oos=False)


def build_reference_context(plan,outer,reference,candidate,record,artifact_hashes):
    declarations=[reference.model_dump(mode='json')]
    evidence=dict(reference_ids=[reference.id],reference_declaration_sha256=digest(declarations),
        admission_scope='predeclared_reference',recommendation_eligible=False)
    result=_training_context_sources(plan,outer,[candidate],{candidate['id']:record},{candidate['id']:artifact_hashes},
        training_role(outer,True),evidence)
    result.update(version=('procedure-reference-v1' if 'application_id' in outer else 'nested-phase-reference-v1'),admission_scope='predeclared_reference',
        reference_ids=[reference.id],source_configuration_ids=[candidate['id']],
        reference_declaration_sha256=digest(declarations),reference_declarations=declarations,
        recommendation_eligible=False)
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
    objective=('historical_lower_mean_cash' if selector.mode=='conservative_expected_received_cash' else FUNDED_OBJECTIVE)
    require(calculations.get('objective')==objective,'Funded calculation objective differs from the predeclared receipt selector.')
    unresolved=_unresolved(calculations)
    if unresolved:return dict(status='INSUFFICIENT_EVIDENCE',selected_ids=[],unresolved_ids=unresolved,reason='complete_candidate_family_not_resolved')
    # Risk constraints have already been applied by the independent funded owner.
    feasible=[row for row in calculations['candidates'] if row['feasible']]
    if selector.minimum_expected_cash is not None:
        feasible=[row for row in feasible if row['metrics'][objective] is not None and Decimal(str(row['metrics'][objective]))>=selector.minimum_expected_cash]
    if not feasible:return dict(status='NO_FEASIBLE_POLICY',selected_ids=[])
    require(all(row['metrics'][objective] is not None and Decimal(str(row['metrics'][objective])).is_finite() for row in feasible),'Missing funded cash objective.')
    best=max(Decimal(str(row['metrics'][objective])) for row in feasible)
    ids=sorted(row['candidate_id'] for row in feasible if Decimal(str(row['metrics'][objective]))==best)
    if selector.tie_policy=='configuration_id':
        by_id={row['candidate_id']:row for row in feasible}
        ids=sorted(ids,key=lambda id:stable_policy_identity(by_id[id],'funded'))[:1]
    return dict(status='FROZEN_FAMILY' if len(ids)>1 else 'FROZEN_POLICY',selected_ids=ids,
        selector=selector.model_dump(mode='json'),objective=objective,constraints=deepcopy(search_request.get('constraints',{})),
        horizon_calendar_days=search_request['horizon_calendar_days'],receipt_delay_calendar_days=search_request['receipt_delay_calendar_days'],
        certification=('Historical lower estimate of a conditional mean; finite-history resampling and Monte Carlo precision do not certify future outcomes.'
            if selector.mode=='conservative_expected_received_cash' else 'point-estimate choice; Monte Carlo error is not total future uncertainty'))


def study_defaults():
    """Current local model defaults; fees/calendar/settlement are declarations."""
    from .prop.phase_profiles import EvaluationProfile, FundedProfile, rule_version
    from .prop.evaluation_optimization import SequentialRetry
    from .prop.funded_optimization import FundedHistoricalMean
    from .prop.native_replay import defaults as native_defaults
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
    return dict(economic_studies=dict(evaluation=evaluation,funded=funded),economic_profiles=profiles,
        baseline=dict(id='One MNQ reference',policy=dict(micros=1),required=True),
        conservative_objective=asdict(FundedHistoricalMean()),
        native_execution=native_defaults()['native_forecast'])


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
    native=settings.get('native_execution')
    if native is not None:
        require(isinstance(native,dict),'Native execution must be an explicit object.')
        if 'horizon_calendar_days' in native and native['horizon_calendar_days']!=horizon:
            raise ValueError('Nested native forecast horizon must match the frozen outer/application cutoff.')
        native['horizon_calendar_days']=horizon
        native['early_closes']={day:close for day,close in native.get('early_closes',{}).items() if start<=day<=cutoff}
    if study.phase=='funded':
        if 'horizon_calendar_days' in settings and settings['horizon_calendar_days']!=horizon:
            raise ValueError('Nested funded forecast horizon must match the outer fold cutoff.')
        settings['horizon_calendar_days']=horizon
        coverage=cutoff
    else:
        from .prop.evaluation_optimization import SequentialRetry
        retry=SequentialRetry(**(value['retry'] or {}))
        coverage=(date.fromisoformat(start)+timedelta(days=retry.max_calendar_days)).isoformat() if native is None else cutoff
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
    result=dict(schema_version=('procedure-phase-freeze-v1' if 'application_id' in outer else 'nested-phase-freeze-v1'),campaign_id=campaign_id,**application_scope(outer,context=True),
        phase=study.phase,candidate_id=row['candidate_id'],configuration=deepcopy(row['manifest']['configuration']),
        strategy=deepcopy(row['manifest']['strategy']),training_context_sha256=context['context_sha256'],
        training_analysis_id=report['id'],training_report_sha256=report_sha256,
        training_candidate_manifest_sha256=digest(row['manifest']),implementation=deepcopy(report['implementation']),
        selector=(EvaluationSelector if study.phase=='evaluation' else FundedSelector).model_validate(study.selector).model_dump(mode='json'),
        provider_rules=deepcopy(report.get('provider_rules')),deployment_readiness=deepcopy(report.get('deployment_readiness')),
        outer_window=window,calendar=calendar,
        interpretation='Frozen training selection; chronological outer observations have not been used.')
    if 'application_id' in outer:
        result['source_configuration_id']=context['training_sources'][row['manifest']['configuration']['source']['source_backtest_id']]['configuration_id']
    if report['request'].get('native_execution') is not None:
        result['native_execution']=deepcopy(report['request']['native_execution'])
    if study.phase=='funded':
        result['receipt_amount_convention']='kernel_entitlement_unrounded'
        result['receipt_delay_calendar_days']=report['request']['receipt_delay_calendar_days']
    result['package_sha256']=digest(result)
    return result


def freeze_reference(campaign_id,outer,study,context,report,report_sha256,row,reference):
    result=freeze_policy(campaign_id,outer,study,context,report,report_sha256,row)
    result.pop('package_sha256')
    result.update(package_role='predeclared_reference',baseline_id=reference.id,
        reference_declaration_sha256=context['reference_declaration_sha256'],recommendation_eligible=False,
        selector=dict(mode='predeclared_reference',selection_uses_forecast_or_outer_results=False),
        interpretation='Predeclared measured reference; edge status and forecast feasibility do not make it a recommended policy.')
    result['package_sha256']=digest(result)
    return result


def replay_native_package(datasets,runs,analyses,campaign_id,analysis_id,record,package,*,
                          checkpoint=lambda:None,progress=lambda message:None):
    """Apply an already sealed policy through the normal native backtest owner.

    The caller's journal authorizes this outer source before reaching this
    function. The shared phase verifier checks the actual training artifacts and
    frozen mapping again; no selection or forecast is performed on these bars.
    """
    from uuid import uuid4
    from .prop.phase_profiles import (SavedTradeSource,EvaluationProfile,FundedProfile,SourceCosts,
        ReplayWindow,verify_frozen_replay)
    from .prop.phase_search import PhaseCalendar
    from .prop.evaluation_optimization import SequentialRetry
    from .prop.native_replay import NativeReplayRequest,check_replay,execute_checked_replay
    require(package.get('native_execution') is not None,'Native outer replay requires its explicit frozen execution law.')
    require(package['campaign_id']==campaign_id,'Native outer policy belongs to another campaign.')
    config=package['configuration'];phase=package['phase'];window=package['outer_window']
    calendar=deepcopy(package['calendar'])
    calendar['start_dates']=tuple(calendar['start_dates']);calendar['closures']=tuple(calendar.get('closures',[]))
    common=dict(runs=runs,source=SavedTradeSource(**dict(config['source'],source_backtest_id=record['id'])),
        phase=phase,profile=(EvaluationProfile if phase=='evaluation' else FundedProfile)(**config['profile']),
        micros=config['micros'],max_micros=config['simulation']['max_micros'],costs=SourceCosts(**config['costs']),
        sizing=SizingConfiguration(**config['sizing']) if config.get('sizing') else None,
        window=ReplayWindow(window['first_session'],window['cutoff_date_exclusive']),
        calendar=PhaseCalendar(**calendar),binding=package)
    if phase=='evaluation':common['retry']=SequentialRetry(**config['retry'])
    else:common.update(receipt_delay_calendar_days=package['receipt_delay_calendar_days'],
        receipt_amount_convention=package['receipt_amount_convention'])
    checkpoint();verify_frozen_replay(**common)
    request=dict(mode='native_phase_replay',phase=phase,source_backtest_id=record['id'],
        profile=config['profile'],micros=config['micros'],max_micros=config['simulation']['max_micros'],
        sizing=config.get('sizing'),costs=config['costs'],
        period=dict(first_session=window['sessions'][0],last_session=window['sessions'][-1]))
    if phase=='evaluation':request['retry']=config['retry']
    else:request.update(receipt_delay_calendar_days=package['receipt_delay_calendar_days'],
        receipt_amount_convention=package['receipt_amount_convention'])
    request=NativeReplayRequest.model_validate(request)
    check=check_replay(datasets,runs,request,admitted_record=record)
    run_id=uuid4().hex
    with analyses.lock,analyses.connect() as db:
        db.execute('INSERT INTO campaign_sources VALUES (?,?)',(campaign_id,run_id))
        db.execute('INSERT INTO analysis_sources VALUES (?,?)',(analysis_id,run_id))
    research=deepcopy(record['run_metadata']['research'])
    research.update(native_uncontrolled_source_id=record['id'],native_controlled_replay=True)
    try:
        child,result=execute_checked_replay(datasets,runs,request,check,admitted_record=record,
            research_metadata=research,run_id=run_id,
            control_metadata=dict(analysis_id=analysis_id,frozen_package_sha256=package['package_sha256']),
            replay_cutoff_date_exclusive=window['cutoff_date_exclusive'],checkpoint=checkpoint,progress=progress)
    except Exception:
        if runs.get(run_id) is None:
            with analyses.lock,analyses.connect() as db:
                db.execute('DELETE FROM campaign_sources WHERE campaign_id=? AND source_id=?',(campaign_id,run_id))
                db.execute('DELETE FROM analysis_sources WHERE analysis_id=? AND source_id=?',(analysis_id,run_id))
        raise
    result.update(frozen_binding=dict(package_sha256=package['package_sha256'],
        training_analysis_id=package['training_analysis_id'],training_report_sha256=package['training_report_sha256']),
        native_source_check=check,native_controlled_backtest_id=child['id'],native_uncontrolled_source_id=record['id'])
    return child,result
