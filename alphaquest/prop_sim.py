"""Qualified campaign sources -> existing independent phase campaigns/reports."""
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from typing import Literal
from uuid import UUID, uuid5

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from .campaign_broad import invoke
from .campaign_monte_carlo import POLICY as MC_POLICY
from .campaign_oos import context as oos_context, results as oos_results
from .optimization_cache import artifacts, digest
from .research_campaigns import CampaignRequest,FreezeRequest
from .prop.phase_profiles import rule_version
from .prop.assessment_review import AssessmentLimits


PROFILE='apex-50k-eod'
SIZE_LIMITS=dict(evaluation=60,funded=40)
PROFILES={PROFILE:dict(name='Apex 50K EOD',limits=SIZE_LIMITS,price='49',activation='129',commission='0.51',broker='Rithmic'),
    'lucidflex-50k':dict(name='LucidFlex 50K',limits=dict(evaluation=40,funded=40),price='80.50',activation='0',commission='0.50',broker='Lucid')}
DISCLOSURE=('Sizing uses only the selected configuration’s declared IS history. Eligibility has already used OOS and full-period Monte Carlo, so this is post-screening research, not an untouched final holdout. '
            'Saved fixed-signal trades are scaled to whole MNQ contracts with native held-OHLC adverse bounds. Account stops/pauses do not rerun strategy signals; execution, gaps and size-dependent fills remain assumptions. '
            'Evaluation and Funded objectives are independent. Calendars below are declared weekday scenarios, not verified exchange calendars. '
            'Local account rules are versioned model assumptions, not newly certified provider rules. Fees are editable scenarios; receipt delay is a modeled assumption. No portfolio allocation or combined annual net projection is calculated.')


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS workflow_prop_sim_deletions (id TEXT PRIMARY KEY, deleted TEXT NOT NULL, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS workflow_prop_simulations (id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS workflow_prop_sim_phases (simulation_id TEXT NOT NULL, phase TEXT NOT NULL, campaign_id TEXT NOT NULL UNIQUE, PRIMARY KEY(simulation_id,phase))')


class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    workflow_id: UUID
    oos_job_id: UUID
    monte_carlo_id: UUID
    candidate: StrictInt = Field(ge=1,le=4)


class Configuration(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID
    profile_id: Literal['apex-50k-eod','lucidflex-50k'] = PROFILE
    daily_loss_limit: StrictBool = True
    evaluation_consistency_percent: StrictInt = 40
    selections: list[Selection] = Field(min_length=1,max_length=1)
    evaluation_minimum_micros: StrictInt = Field(default=1,ge=1,le=60)
    evaluation_maximum_micros: StrictInt = Field(default=10,ge=1,le=60)
    funded_minimum_micros: StrictInt = Field(default=1,ge=1,le=40)
    funded_maximum_micros: StrictInt = Field(default=10,ge=1,le=40)
    simulations: StrictInt = Field(default=1000,ge=8,le=20000)
    seed: StrictInt = Field(default=42,ge=0,lt=2**32-3)
    block_weekdays: StrictInt = Field(default=5)
    evaluation_price: StrictStr = '49'
    activation_fee: StrictStr = '129'
    start_date: StrictStr
    closures: list[StrictStr] = Field(default_factory=list,max_length=3660)
    funded_horizon_calendar_days: StrictInt = Field(default=90,ge=1,le=365)
    receipt_delay_calendar_days: StrictInt = Field(default=2,ge=0,le=365)
    maximum_funded_breach_probability: float | None = Field(default=None,ge=0,le=1)
    commission_per_mnq_side: StrictStr = '0.51'

    @model_validator(mode='before')
    @classmethod
    def profile_defaults(cls,value):
        if isinstance(value,dict) and value.get('profile_id')=='lucidflex-50k':
            value=dict(value)
            if value.get('evaluation_consistency_percent')==50 and 'evaluation_price' not in value:
                raise ValueError('Enter the purchase price including the 50% consistency add-on; no add-on price is assumed.')
            for field,key in [('evaluation_price','price'),('activation_fee','activation'),('commission_per_mnq_side','commission')]:
                value.setdefault(field,PROFILES['lucidflex-50k'][key])
        return value

    @model_validator(mode='before')
    @classmethod
    def legacy_shared_range(cls,value):
        """Read old declarations without mutating their saved settings/reports."""
        if isinstance(value,dict) and {'minimum_micros','maximum_micros'} & value.keys():
            if any(f'{phase}_{bound}_micros' in value for phase in SIZE_LIMITS for bound in ('minimum','maximum')):
                raise ValueError('Use either legacy shared sizes or separate phase sizes, not both.')
            value=dict(value)
            minimum=value.pop('minimum_micros',1);maximum=value.pop('maximum_micros',10)
            for phase in SIZE_LIMITS:
                value.update({f'{phase}_minimum_micros':minimum,f'{phase}_maximum_micros':maximum})
        return value

    @model_validator(mode='after')
    def ordered_ranges(self):
        if self.evaluation_consistency_percent not in (40,50):
            raise ValueError('Choose 40% standard or 50% add-on Evaluation consistency.')
        if self.profile_id != 'lucidflex-50k' and self.evaluation_consistency_percent != 40:
            raise ValueError('The consistency add-on applies only to LucidFlex.')
        for phase in SIZE_LIMITS:
            if getattr(self,f'{phase}_maximum_micros')>PROFILES[self.profile_id]['limits'][phase]:
                raise ValueError(f'{PROFILES[self.profile_id]["name"]} {phase} supports at most {PROFILES[self.profile_id]["limits"][phase]} MNQ.')
            if getattr(self,f'{phase}_minimum_micros')>getattr(self,f'{phase}_maximum_micros'):
                raise ValueError(f'{phase.title()} minimum size must not exceed its maximum size.')
        if self.profile_id==PROFILE and not self.daily_loss_limit:raise ValueError('Apex requires its daily loss limit.')
        if self.profile_id=='lucidflex-50k' and Decimal(self.activation_fee)!=0:raise ValueError('LucidFlex has no activation fee; use zero.')
        return self

    @field_validator('evaluation_price','activation_fee','commission_per_mnq_side')
    @classmethod
    def money(cls,value):
        try:number=Decimal(value)
        except InvalidOperation as exc:raise ValueError('Enter a numeric cost amount.') from exc
        if not number.is_finite() or not 0<=number<=100000:raise ValueError('Costs must be finite, nonnegative amounts ≤100000.')
        return value


def qualified(request,selection):
    """Authoritative qualification for listing, check and launch; no client verdicts."""
    workflow_id=selection.workflow_id.hex;job_id=selection.oos_job_id.hex;mc_id=selection.monte_carlo_id.hex
    workflows=request.app.state.campaign_workflows
    saved,_=workflows.phase(workflow_id,'oos')
    with workflows.runs.connect() as db:
        current=db.execute('SELECT job_id FROM campaign_oos_state WHERE workflow_id=?',(workflow_id,)).fetchone()
    if not current or current[0]!=job_id:raise ValueError('Select the current completed OOS assessment.')
    _,_,identity,job,_=oos_context(request,workflow_id,job_id)
    if job['status']!='complete':raise ValueError('OOS is not complete.')
    result=oos_results(request,workflow_id,job_id)
    candidate=next((i for i in result['items'] if i['trial']==selection.candidate and i['qualifies']),None)
    if not candidate:raise ValueError('This configuration did not pass verified OOS acceptance.')
    analyses=request.app.state.prop_analyses
    with analyses.connect() as db:
        latest=db.execute('SELECT a.id,a.status FROM analyses a JOIN campaign_sanity_jobs c ON c.analysis_id=a.id WHERE c.workflow_id=? AND c.oos_job_id=? ORDER BY a.created DESC LIMIT 1',(workflow_id,job_id)).fetchone()
    if not latest or latest!=(mc_id,'complete'):raise ValueError('Select a configuration from the latest completed Monte Carlo assessment.')
    if not analyses.fingerprint(mc_id):raise ValueError('Monte Carlo evidence integrity check failed.')
    report=json.loads((analyses.root/mc_id/'report.json').read_text())
    if report['policy']!=MC_POLICY or report['frozen_identity']!=identity or report['plan']!=saved['declaration']['plan']:
        raise ValueError('Monte Carlo policy or frozen campaign identity is incompatible.')
    mc=next((i for i in report['candidates'] if i['candidate']==selection.candidate),None)
    if (not mc or not mc['qualifies'] or not mc['evidence_passed']
            or mc['observed']['days']<MC_POLICY['minimum_observed_days']
            or mc['closed_trades']<MC_POLICY['minimum_closed_trades']
            or len(mc['scenarios'])!=len(MC_POLICY['block_lengths'])
            or {s['mean_block_days'] for s in mc['scenarios']}!=set(MC_POLICY['block_lengths'])
            or not all(s['qualifies'] and s['net_profit_p05']>0 for s in mc['scenarios'])):
        raise ValueError('This configuration did not pass the current Monte Carlo criteria.')
    if (mc['parameters']!=candidate['parameters'] or mc['broad_trial']!=candidate['broad_trial']
            or mc['narrow_trial']!=candidate['narrow_trial'] or mc['oos_admission']!=candidate['admission']):
        raise ValueError('Monte Carlo and OOS configuration identities differ.')
    for proof,id in zip(mc['sources'],(candidate['is_run_id'],candidate['run_id']),strict=True):
        native=workflows.runs.get(id)
        if proof['run_id']!=id or proof['manifest_sha256']!=digest(native) or proof['artifacts']!=artifacts(workflows.runs.root,native):
            raise ValueError('Qualified native source evidence changed.')
    from .prop.commissions import source_instrument
    native=workflows.runs.get(candidate['is_run_id'])
    if source_instrument(native) not in ('NQ','MNQ'):raise ValueError('This local prop model requires a saved NQ or MNQ dataset symbol.')
    return dict(selection=selection.model_dump(mode='json'),source_backtest_id=candidate['is_run_id'],
        strategy_id=saved['declaration']['strategy_id'],dataset=saved['declaration']['dataset'],parameters=candidate['parameters'],
        plan=saved['declaration']['plan'],broad_trial=candidate['broad_trial'],narrow_trial=candidate['narrow_trial'],
        oos_report_id=candidate['run_id'],monte_carlo_report_sha256=analyses.fingerprint(mc_id)['files']['report.json'],
        frozen_identity=identity,qualification='mechanics, IS Broad, IS Narrow, OOS and Monte Carlo passed')


def candidates(request):
    runs=request.app.state.runs;analyses=request.app.state.prop_analyses
    with runs.connect() as db:
        workflows=[r[0] for r in db.execute('SELECT workflow_id FROM campaign_oos_state')]
    items=[];unavailable=[]
    for workflow in workflows:
        with runs.connect() as db:job=db.execute('SELECT job_id FROM campaign_oos_state WHERE workflow_id=?',(workflow,)).fetchone()[0]
        with analyses.connect() as db:
            latest=db.execute('SELECT a.id,a.status FROM analyses a JOIN campaign_sanity_jobs c ON c.analysis_id=a.id WHERE c.workflow_id=? AND c.oos_job_id=? ORDER BY a.created DESC LIMIT 1',(workflow,job)).fetchone()
        if not latest or latest[1]!='complete':continue
        try:
            if not analyses.fingerprint(latest[0]):raise ValueError('Monte Carlo evidence is unavailable or changed.')
            report=json.loads((analyses.root/latest[0]/'report.json').read_text())
            for candidate in report['candidates']:
                if not candidate['qualifies']:continue
                ref=Selection(workflow_id=workflow,oos_job_id=job,monte_carlo_id=latest[0],candidate=candidate['candidate'])
                try:items.append(qualified(request,ref))
                except (ValueError,KeyError,OSError) as exc:unavailable.append(dict(workflow_id=workflow,candidate=candidate['candidate'],reason=str(exc)))
        except (ValueError,KeyError,OSError) as exc:unavailable.append(dict(workflow_id=workflow,reason=str(exc)))
    return dict(items=items,unavailable=unavailable,maximum_selected_configurations=1)


def declarations(body,source):
    if body.block_weekdays not in (1,5,10):raise ValueError('Block length must be 1, 5 or 10 weekdays.')
    account=PROFILES[body.profile_id]
    profile=dict(profile_id=body.profile_id,rule_version=rule_version(body.profile_id),daily_loss_limit=body.daily_loss_limit)
    # The saved source bounds may start on the prior Chicago session date.
    from .prop.phase_lifecycle import instant, session_date
    native=source['_native']
    first=max(source['plan']['is_start'],session_date(instant(native['period_start_utc'])).isoformat())
    last=min(source['plan']['is_end'],session_date(instant(native['period_end_utc'])).isoformat())
    common=dict(is_window=dict(first_session=first,last_session=last),
        costs=dict(mode='override',broker=account['broker'],per_side=body.commission_per_mnq_side,instrument='auto'))
    calendar=dict(start_dates=[body.start_date],closures=body.closures)
    definitions={}
    for phase in ('evaluation','funded'):
        minimum=getattr(body,f'{phase}_minimum_micros');maximum=getattr(body,f'{phase}_maximum_micros')
        phase_profile=dict(profile)
        sampling=dict(block_weekdays=body.block_weekdays)
        settings=dict(calendar=calendar)
        if phase=='evaluation':
            phase_profile['consistency_percent']=body.evaluation_consistency_percent
            phase_profile.update(evaluation_price=body.evaluation_price,activation_fee=body.activation_fee)
            sampling.update(chain_simulations=body.simulations,chain_seed=body.seed if body.profile_id=='lucidflex-50k' else body.seed+3)
        else:
            phase_profile['approval_day_counts']=True
            settings.update(horizon_calendar_days=body.funded_horizon_calendar_days,
                receipt_delay_calendar_days=body.receipt_delay_calendar_days,bootstrap_replicates=100,
                constraints=dict(maximum_account_breach_probability=body.maximum_funded_breach_probability,maximum_position_size=maximum))
        definitions[phase]=CampaignRequest.model_validate(dict(common,campaign_id=uuid5(body.request_id,phase).hex,
            sources=[dict(backtest_id=source['source_backtest_id'],sizes=list(range(minimum,maximum+1)))],
            simulation=dict(simulations=body.simulations,seed=body.seed,max_micros=account['limits'][phase]),
            phase=phase,profile=phase_profile,sampling=sampling,search_settings=settings,
            **(dict(retry=dict(activation_delay_sessions=0)) if phase=='evaluation' and body.profile_id=='lucidflex-50k' else {})))
    return definitions


def check(request,body):
    source=qualified(request,body.selections[0])
    source['_native']=request.app.state.runs.get(source['source_backtest_id'])
    definitions=declarations(body,source);source.pop('_native')
    checks={}
    for phase,declaration in definitions.items():
        try:checks[phase]=request.app.state.campaigns.expand(declaration)
        except ValueError as exc:raise ValueError(f'{phase.title()} sizing search: {exc}') from exc
    return dict(status='compatible',source=source,phases=checks,disclosure=DISCLOSURE),definitions


def public(request,id):
    with request.app.state.prop_analyses.connect() as db:row=db.execute('SELECT payload FROM workflow_prop_simulations WHERE id=?',(id,)).fetchone()
    if not row:raise KeyError('Prop simulation not found.')
    result=json.loads(row[0])
    result['phases']={}
    for phase,campaign_id in result['campaign_ids'].items():
        campaign=request.app.state.campaigns.get(campaign_id)
        analysis=campaign.get('analysis') or {}
        result['phases'][phase]=dict(campaign_id=campaign_id,status=campaign['status'],analysis_id=campaign['analysis_id'],
            progress=analysis.get('progress'),error=analysis.get('error'),candidate_count=campaign['manifest']['candidate_search_count'])
    return result


def launch(request,body):
    analyses=request.app.state.prop_analyses;id=body.request_id.hex
    with analyses.lock:
        with analyses.connect() as db:
            if db.execute('SELECT 1 FROM workflow_prop_sim_deletions WHERE id=?',(id,)).fetchone():raise ValueError('This saved simulation was deleted. Use a new request ID for another simulation.')
        with analyses.connect() as db:previous=db.execute('SELECT payload FROM workflow_prop_simulations WHERE id=?',(id,)).fetchone()
        if previous:
            previous_body=Configuration.model_validate(json.loads(previous[0])['configuration'])
            if previous_body.model_dump(mode='json')!=body.model_dump(mode='json'):raise ValueError('This request ID already belongs to a different simulation.')
            # Revalidate qualification on every explicit launch, even for a cached result.
            qualified(request,body.selections[0])
            saved=json.loads(previous[0])
            for campaign_id in saved['campaign_ids'].values():request.app.state.campaigns.run(campaign_id)
            return public(request,id)
        checked,definitions=check(request,body)
        for declaration in definitions.values():request.app.state.campaigns.create(declaration)
        result=dict(id=id,created_at_utc=datetime.now(timezone.utc).isoformat(),configuration=body.model_dump(mode='json'),
                    qualification=checked['source'],disclosure=DISCLOSURE,campaign_ids={p:d.campaign_id for p,d in definitions.items()})
        with analyses.connect() as db:
            db.execute('INSERT INTO workflow_prop_simulations VALUES (?,?,?)',(id,result['created_at_utc'],json.dumps(result)))
            db.executemany('INSERT INTO workflow_prop_sim_phases VALUES (?,?,?)',[(id,p,d.campaign_id) for p,d in definitions.items()])
        for phase in ('evaluation','funded'):request.app.state.campaigns.run(result['campaign_ids'][phase])
    return public(request,id)


router=APIRouter(prefix='/api/prop-sim')


@router.get('/candidates')
async def sources(request:Request):return await invoke(candidates,request)


def account_defaults(id):
    from .prop import native_engine,lucid_engine
    from .prop.phase_profiles import EvaluationProfile,FundedProfile
    from .prop.rule_provenance import profile_review
    account=PROFILES[id];lucid=id=='lucidflex-50k'
    return dict(profile_id=id,name=account['name'],rule_version=rule_version(id),disclosure=DISCLOSURE,size_limits=account['limits'],
        rule_provenance=dict(evaluation=profile_review(EvaluationProfile(id,rule_version(id),account['price'],account['activation']),'evaluation'),
            funded=profile_review(FundedProfile(id,rule_version(id)),'funded')),
        evaluation_rules=dict(account_size=50000,profit_target=3000,maximum_drawdown=2000,
            daily_loss_limit=1200 if lucid else 1000,expiry_weekdays=None if lucid else 21,
            consistency=.4 if lucid else None,inactivity_calendar_days=30 if lucid else None),
        funded_rules=asdict((lucid_engine if lucid else native_engine).Rules()),maximum_selected_configurations=1,
        supported_evaluation_consistency_percent=[40,50] if lucid else [],
        notes=('40% standard or 50% add-on Evaluation consistency; enter the actual purchase fee including options. No activation fee or provider Evaluation expiry. Calendar inactivity is modeled. DLL-on uses the preserved fixed $1,200 soft stop assumption. Live trading after the fifth payout is outside this simulation.' if lucid else
            'Preserved local model: 21-session Evaluation expiry/inactivity and exactly 50% Funded consistency; reviewed provider calendar/boundary rules differ.'),
        report_limits=dict(size_dependent_path_cap=False),
        defaults=dict(profile_id=id,daily_loss_limit=True,evaluation_consistency_percent=40,evaluation_minimum_micros=1,evaluation_maximum_micros=10,
            funded_minimum_micros=1,funded_maximum_micros=10,simulations=1000,seed=42,block_weekdays=5,
            evaluation_price=account['price'],activation_fee=account['activation'],commission_per_mnq_side=account['commission'],
            funded_horizon_calendar_days=90,receipt_delay_calendar_days=2,maximum_funded_breach_probability=None))


@router.get('/defaults')
def defaults():
    profiles={id:account_defaults(id) for id in PROFILES}
    return dict(profiles[PROFILE],profiles=profiles)


@router.post('/check')
async def preview(body:Configuration,request:Request):
    checked,_=await invoke(check,request,body);return checked


@router.post('',status_code=202)
async def run(body:Configuration,request:Request):return await invoke(launch,request,body)


@router.get('')
async def history(request:Request):
    def read():
        with request.app.state.prop_analyses.connect() as db:
            return dict(items=[json.loads(r[0]) for r in db.execute('SELECT payload FROM workflow_prop_simulations ORDER BY created DESC LIMIT 50')])
    return await invoke(read)


@router.get('/{id}')
async def status(id:UUID,request:Request):return await invoke(public,request,id.hex)


@router.get('/{id}/results/{phase}')
async def results(id:UUID,phase:str,request:Request):
    if phase not in ('evaluation','funded'):raise HTTPException(404,'Unknown phase.')
    saved=await invoke(public,request,id.hex)
    return await invoke(request.app.state.campaigns.report,saved['campaign_ids'][phase])


@router.post('/{id}/cancel')
async def stop(id:UUID,request:Request):
    saved=await invoke(public,request,id.hex)
    for phase in saved['phases'].values():
        if phase['analysis_id'] and phase['status'] in ('queued','running'):
            await invoke(request.app.state.prop_analyses.cancel_phase,phase['analysis_id'])
    return await invoke(public,request,id.hex)


class FrozenAssessment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID
    kind: Literal['oos','is_robustness','precision','account_starts','qualification','forward_review']
    paths: StrictInt | None = Field(default=None,ge=8,le=20000)


class PolicyRevision(AssessmentLimits):
    previous_policy_sha256: StrictStr = Field(pattern=r'^[0-9a-f]{64}$')
    reason: StrictStr = Field(min_length=1,max_length=2000)


def phase_campaign(request,id,phase):
    if phase not in ('evaluation','funded'):raise KeyError('Unknown phase.')
    saved=public(request,id)
    return saved,saved['campaign_ids'][phase]


@router.get('/{id}/validation/{phase}')
async def validation(id:UUID,phase:str,request:Request):
    def read():
        saved,cid=phase_campaign(request,id.hex,phase);store=request.app.state.campaigns;campaign=store.get(cid)
        frozen=campaign['frozen']
        from .prop.phase_dispatch import implementations_compatible, module_for
        compatible=implementations_compatible(campaign['manifest']['numerical_implementation'],module_for(phase).implementation_identity())
        from .prop.assessment_review import implementation
        from .prop.oos_qualification import RULES
        policy=saved.get('assessment_policies',{}).get(phase)
        return dict(campaign_id=cid,numerical_implementation_compatible=compatible,assessment_policy=policy,qualification_rules=RULES,
            assessment_policy_history=saved.get('assessment_policy_history',{}).get(phase,[policy] if policy else []),
            review_implementation_compatible=policy is None or policy['implementation']==implementation(),
            frozen=None if frozen is None else {k:frozen[k] for k in ('candidate_ids','names','rationale','package_sha256','created_at_utc')},
            assessments=store.assessments(cid),disclosure='Strategy qualification already accessed OOS. Frozen-size assessment is additional research, not an untouched holdout. No OOS reselection.')
    return await invoke(read)


@router.post('/{id}/validation/{phase}/policy')
async def declare_assessment_policy(id:UUID,phase:str,body:AssessmentLimits,request:Request):
    return await invoke(lambda:save_assessment_policy(request,id.hex,phase,body))


@router.post('/{id}/validation/{phase}/policy/revisions')
async def revise_assessment_policy(id:UUID,phase:str,body:PolicyRevision,request:Request):
    limits=AssessmentLimits.model_validate(body.model_dump(exclude={'previous_policy_sha256','reason'}))
    return await invoke(lambda:save_assessment_policy(request,id.hex,phase,limits,body))


def save_assessment_policy(request,id,phase,body,revision=None):
    from .prop.adapter import canonical,source_record
    from .prop.phase_search import saved_oos_period
    from .prop.assessment_review import implementation,start_plan
    from hashlib import sha256
    body.for_phase(phase)
    if revision is not None and not revision.reason.strip():
        raise ValueError('Explain why the assessment limits are being revised.')
    analyses=request.app.state.prop_analyses
    with analyses.lock:
        saved,cid=phase_campaign(request,id,phase)
        policies=saved.get('assessment_policies',{})
        previous=policies.get(phase)
        limits=body.model_dump(mode='json')
        if revision is None and previous:
            if previous['limits']!=limits:
                raise ValueError('Saved assessment limits are immutable. Use Revise assessment limits to save a new version.')
            return previous
        if revision is not None:
            if not previous:raise ValueError('Declare initial assessment limits before revising them.')
            if revision.previous_policy_sha256!=previous['policy_sha256']:
                if (previous.get('previous_policy_sha256')==revision.previous_policy_sha256
                        and previous['limits']==limits and previous.get('revision_reason')==revision.reason.strip()):
                    return previous
                raise ValueError('Assessment limits changed in another session. Reload before saving your revision.')
            if previous['limits']==limits and previous['implementation']==implementation():
                raise ValueError('No assessment limits changed.')
        source=source_record(request.app.state.runs,saved['qualification']['oos_report_id'])
        prior=[a for a in request.app.state.campaigns.assessments(cid) if a.get('kind')=='oos']
        horizon=body.maximum_calendar_days_to_funded if phase=='evaluation' else saved['configuration']['funded_horizon_calendar_days']
        policy=dict(version='prop-oos-review-v1',phase=phase,limits=limits,revision=previous.get('revision',1)+1 if previous else 1,
            implementation=implementation(),declared_at_utc=datetime.now(timezone.utc).isoformat(),
            declaration_timing='retrospective' if prior else 'before_first_prop_oos_result',
            prior_oos_attempts=len(prior),prior_completed_oos_assessments=sum(a['status']=='complete' for a in prior),
            start_plan=start_plan(saved_oos_period(source),horizon,body.account_start_count,saved['configuration']['closures']))
        if revision is not None:
            policy.update(previous_policy_sha256=previous['policy_sha256'],revision_reason=revision.reason.strip())
        policy['policy_sha256']=sha256(canonical(policy).encode()).hexdigest()
        with analyses.connect() as db:
            payload=json.loads(db.execute('SELECT payload FROM workflow_prop_simulations WHERE id=?',(id,)).fetchone()[0])
            history=payload.setdefault('assessment_policy_history',{}).setdefault(phase,[previous] if previous else [])
            history.append(policy)
            payload.setdefault('assessment_policies',{})[phase]=policy
            db.execute('UPDATE workflow_prop_simulations SET payload=? WHERE id=?',(canonical(payload),id))
        return policy


@router.post('/{id}/validation/{phase}/freeze')
async def freeze_choices(id:UUID,phase:str,body:FreezeRequest,request:Request):
    def freeze():
        if len(body.candidate_ids)>4:raise ValueError('Freeze at most four size choices per phase.')
        _,cid=phase_campaign(request,id.hex,phase)
        return request.app.state.campaigns.freeze(cid,body)
    return await invoke(freeze)


@router.post('/{id}/validation/{phase}',status_code=202)
async def assess_choices(id:UUID,phase:str,body:FrozenAssessment,request:Request):
    def assess():
        saved,cid=phase_campaign(request,id.hex,phase)
        if body.kind in ('oos','account_starts','qualification','forward_review') and body.paths is not None:raise ValueError('OOS uses the frozen path count; account starts are deterministic. Do not override paths.')
        if body.kind=='forward_review':raise ValueError('Use the forward review form with its captured observation assessment.')
        if body.kind in ('is_robustness','precision') and body.paths is None:raise ValueError('Declare diagnostic paths explicitly.')
        store=request.app.state.campaigns
        attempts=store.assessments(cid)
        previous=next((a for a in attempts if a['request_id']==body.request_id.hex),None)
        if previous:
            if previous.get('kind')!=body.kind or previous.get('paths')!=body.paths:
                raise ValueError('Assessment request ID already belongs to another declaration.')
            store.begin_assessment(cid,body.request_id.hex)  # Verify sealed evidence on idempotent reopen too.
            return previous
        options=None
        robustness=next((a for a in reversed(attempts) if a.get('kind')=='qualification' and a['status']=='complete'),None)
        if body.kind=='qualification' or body.kind=='account_starts' and robustness:
            from .prop.oos_qualification import policy as robustness_policy,implementation
            from .prop.phase_search import saved_oos_period
            from .prop.adapter import source_record
            qualification=qualified(request,Selection.model_validate(saved['configuration']['selections'][0]))
            selected=store.get(cid)['frozen']
            if not selected:raise ValueError('Freeze the IS size choices before OOS qualification.')
            if len(selected['candidate_ids'])>4:raise ValueError('Qualification covers at most four frozen sizes per phase.')
            source=source_record(request.app.state.runs,saved['qualification']['oos_report_id'])
            policy=robustness_policy(phase,saved_oos_period(source),saved['configuration']['funded_horizon_calendar_days'],closures=saved['configuration']['closures'])
            options=dict(qualification=True,simulation_id=id.hex,policy=policy,implementation=implementation(),kind=body.kind,
                prerequisites=dict(passed=True,qualification=qualification['qualification'],snapshot=qualification))
            if body.kind=='account_starts' and (robustness.get('report_options') or {}).get('implementation')!=implementation():
                raise ValueError('Run the current OOS qualification before account-start sensitivity.')
            base=robustness or next((a for a in reversed(attempts) if a.get('kind')=='oos' and a['status']=='complete'),None)
            if base:
                fingerprint=request.app.state.prop_analyses.fingerprint(base['analysis_id'])
                if not fingerprint:raise ValueError('Saved OOS evidence changed; no results were reused.')
                options['base_report']=dict(analysis_id=base['analysis_id'],sha256=fingerprint['files']['report.json'])
        elif body.kind in ('oos','account_starts') and saved.get('assessment_policies',{}).get(phase):
            from .prop.assessment_review import implementation
            policy=saved.get('assessment_policies',{}).get(phase)
            if policy is None:raise ValueError('Save explicit OOS assessment limits before running OOS.')
            if policy['implementation']!=implementation():raise ValueError('Assessment review implementation changed; save a policy revision before a new assessment.')
            options=dict(policy=policy,implementation=implementation(),kind=body.kind)
            base=next((a for a in reversed(attempts) if a.get('kind')=='oos' and a['status']=='complete'),None)
            if body.kind=='account_starts' and base is None:raise ValueError('Complete an OOS assessment before account-start sensitivity.')
            if body.kind=='account_starts' and (base.get('report_options') or {}).get('policy',{}).get('policy_sha256')!=policy['policy_sha256']:
                raise ValueError('Run OOS assessment with the current policy revision before account-start sensitivity. Saved MC results will be reused.')
            if base:
                fingerprint=request.app.state.prop_analyses.fingerprint(base['analysis_id'])
                if not fingerprint:raise ValueError('Saved OOS evidence changed; no results were reused.')
                options['base_report']=dict(analysis_id=base['analysis_id'],sha256=fingerprint['files']['report.json'])
        elif body.kind=='account_starts':
            raise ValueError('Complete OOS qualification before account-start sensitivity.')
        sources={saved['qualification']['source_backtest_id']:saved['qualification']['oos_report_id']}
        return store.assess_saved(cid,body.request_id.hex,body.kind,body.paths,sources,report_options=options)
    return await invoke(assess)


class ForwardReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID
    analysis_id: UUID
    reviewed_episode_ids: list[StrictStr] = Field(max_length=100000)
    notes: StrictStr = Field(min_length=1,max_length=4000)


@router.get('/{id}/validation/{phase}/forward')
async def forward_launcher(id:UUID,phase:str,request:Request):
    def read():
        phase_campaign(request,id.hex,phase)
        from .prop_sim_forward import launcher
        return launcher(request.app.state.prop_analyses,id.hex,phase)
    return await invoke(read)


def forward_preview(request,id,phase,analysis_id):
    from .prop_sim_forward import current_report,verified_observation,execution_check
    from .prop.adapter import canonical
    from hashlib import sha256
    analyses=request.app.state.prop_analyses
    _,cid=phase_campaign(request,id,phase)
    qualification=current_report(analyses,id,phase,cid)
    fingerprint=analyses.fingerprint(analysis_id)
    if not fingerprint:raise ValueError('Complete a saved forward observation assessment first.')
    capture=dict(analysis_id=analysis_id,sha256=fingerprint['files']['report.json'])
    report,_=verified_observation(capture,id,phase,qualification['id'],analyses)
    episodes=[dict(id=sha256(canonical(e).encode()).hexdigest(),trade=e) for e in report['calculations']['metrics']['episodes']]
    return dict(capture=capture,qualification_analysis_id=qualification['id'],episodes=episodes,
        preview=execution_check(report,[],'')),qualification


@router.get('/{id}/validation/{phase}/forward-review/{analysis_id}')
async def preview_forward_review(id:UUID,phase:str,analysis_id:UUID,request:Request):
    return await invoke(lambda:forward_preview(request,id.hex,phase,analysis_id.hex)[0])


@router.post('/{id}/validation/{phase}/forward-review',status_code=202)
async def save_forward_review(id:UUID,phase:str,body:ForwardReview,request:Request):
    def save():
        if not body.notes.strip():raise ValueError('Record the manual signal and execution parity review.')
        analyses=request.app.state.prop_analyses;store=request.app.state.campaigns
        with analyses.lock:
            saved,cid=phase_campaign(request,id.hex,phase)
            previous=next((a for a in store.assessments(cid) if a['request_id']==body.request_id.hex),None)
            if previous:
                capture=(previous.get('report_options') or {}).get('forward_capture',{})
                if (previous.get('kind')!='forward_review' or capture.get('analysis_id')!=body.analysis_id.hex
                        or capture.get('reviewed_episode_ids')!=body.reviewed_episode_ids or capture.get('notes')!=body.notes):
                    raise ValueError('Request ID already belongs to another forward review.')
                store.begin_assessment(cid,body.request_id.hex)
                return previous
            preview,qualification=forward_preview(request,id.hex,phase,body.analysis_id.hex)
            valid={e['id'] for e in preview['episodes']}
            if len(set(body.reviewed_episode_ids))!=len(body.reviewed_episode_ids) or not set(body.reviewed_episode_ids)<=valid:
                raise ValueError('Trade review must reference unique closed episodes from the saved observation.')
            options=dict(qualification['assessment']['prop_sim_review'])
            options.update(kind='forward_review',base_report=dict(analysis_id=qualification['id'],
                sha256=analyses.fingerprint(qualification['id'])['files']['report.json']),
                forward_capture=dict(preview['capture'],reviewed_episode_ids=body.reviewed_episode_ids,notes=body.notes))
            qualified(request,Selection.model_validate(saved['configuration']['selections'][0]))
            with analyses.connect() as db:
                db.execute('INSERT OR IGNORE INTO campaign_analyses VALUES (?,?)',(cid,body.analysis_id.hex))
            return store.assess_saved(cid,body.request_id.hex,'forward_review',None,
                {saved['qualification']['source_backtest_id']:saved['qualification']['oos_report_id']},report_options=options)
    return await invoke(save)


@router.get('/{id}/validation/{phase}/{attempt_id}')
async def validation_report(id:UUID,phase:str,attempt_id:UUID,request:Request,summary:bool=False):
    def read():
        _,cid=phase_campaign(request,id.hex,phase);store=request.app.state.campaigns
        attempt=next((a for a in store.assessments(cid) if a['request_id']==attempt_id.hex),None)
        if not attempt or not attempt.get('analysis_id'):raise KeyError('Assessment report not found.')
        analyses=request.app.state.prop_analyses;aid=attempt['analysis_id']
        if not analyses.fingerprint(aid):raise ValueError('Assessment is incomplete or its evidence changed.')
        report=json.loads((analyses.root/aid/'report.json').read_text())
        if summary:
            calculations=dict(report['calculations'])
            calculations.pop('qualification_bootstrap',None)
            fields=('candidate_id','frozen_candidate_id','configuration','metrics','status','scenario','uncertainty','is_comparison','chronological_replay','outcome_summary','economic_assessment','prop_qualification')
            calculations['candidates']=[{k:r[k] for k in fields if k in r} for r in calculations['candidates']]
            return dict(id=report['id'],model_version=report['model_version'],calculations=calculations)
        return report
    return await invoke(read)

def deletion_preview(request,id,db):
    """Metadata-only deletion plan over the existing catalogue and owner guards."""
    analyses=request.app.state.prop_analyses;campaigns=request.app.state.campaigns
    old=db.execute('SELECT payload FROM workflow_prop_sim_deletions WHERE id=?',(id,)).fetchone()
    if old:return json.loads(old[0])['receipt']
    row=db.execute('SELECT payload FROM workflow_prop_simulations WHERE id=?',(id,)).fetchone()
    if not row:raise KeyError('Prop simulation not found.')
    saved=json.loads(row[0]);expected=saved['campaign_ids']
    refs=dict(db.execute('SELECT phase,campaign_id FROM workflow_prop_sim_phases WHERE simulation_id=?',(id,)))
    if refs!=expected:raise ValueError('Saved simulation references are inconsistent; no results were removed.')
    plans={phase:campaigns._deletion_preview(db,cid,releasing_prop_sim=id) for phase,cid in expected.items()}
    active=sorted({a['id'] for p in plans.values() for a in p['retained_analyses'] if a['status'] in ('queued','running')})
    released=[cid for phase,cid in expected.items() if plans[phase]['deletable']]
    retained_campaigns=[dict(id=cid,reasons=plans[phase]['blockers']) for phase,cid in expected.items() if not plans[phase]['deletable']]
    ids=sorted({a['id'] for p in plans.values() for a in p['retained_analyses']})
    remove=[];retain=[]
    for aid in ids:
        try:
            record=analyses.deletion_check(db,aid,releasing_campaigns=released)
            if not record:raise ValueError('Report catalogue entry is unavailable; existing evidence is kept.')
            remove.append(aid)
        except ValueError as exc:retain.append(dict(id=aid,reason=str(exc)))
    monitors=[r[0] for r in db.execute("SELECT id FROM forward_monitors WHERE json_extract(declaration,'$.policy_binding.application_id')=?",(id,))]
    result=dict(id=id,deleted=False,deletable=not active and not monitors,active_analyses=active,dependent_forward_monitors=monitors,
        campaign_ids_to_delete=released,retained_campaigns=retained_campaigns,
        analysis_ids_to_delete=remove,retained_analyses=retain,
        source_backtest_id=saved['qualification']['source_backtest_id'],profile_id=saved['configuration'].get('profile_id',PROFILE),
        strategy_id=saved['qualification']['strategy_id'],created_at_utc=saved['created_at_utc'],
        interpretation='Delete this saved simulation, its unused phase campaigns and unshared reports. Keep datasets, source backtests, campaign phases, OOS/Monte Carlo and results used elsewhere.')
    result['confirmation_sha256']=digest(dict(preview=result,parent=saved,phase_plans=plans))
    return result


class DeleteSimulation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirmation_sha256: StrictStr = Field(pattern=r'^[0-9a-f]{64}$')


def remove_simulation(request,id,body):
    """Atomically release catalogue links and stage files; retry cleanup safely."""
    import shutil
    analyses=request.app.state.prop_analyses;campaigns=request.app.state.campaigns;moved=[]
    with analyses.lock:
        try:
            with analyses.connect() as db:
                db.execute('BEGIN IMMEDIATE');preview=deletion_preview(request,id,db)
                if body.confirmation_sha256!=preview['confirmation_sha256']:
                    raise ValueError('Simulation dependencies changed. Review the deletion again.')
                if not preview.get('deleted'):
                    if not preview['deletable']:raise ValueError('This simulation has active jobs or bound forward monitors. Preserve their frozen policy and evidence.')
                    snapshot=json.loads(db.execute('SELECT payload FROM workflow_prop_simulations WHERE id=?',(id,)).fetchone()[0])
                    db.execute('DELETE FROM workflow_prop_sim_phases WHERE simulation_id=?',(id,))
                    for cid in preview['campaign_ids_to_delete']:
                        current=campaigns._deletion_preview(db,cid)
                        if not current['deletable']:raise ValueError('A phase campaign acquired another dependency; review deletion again.')
                        campaigns.delete_in_transaction(db,cid,current)
                    for aid in preview['analysis_ids_to_delete']:
                        if UUID(aid).hex!=aid:raise ValueError('Invalid report identity; no results were removed.')
                        record=analyses.deletion_check(db,aid)
                        destination=analyses.root/aid;staged=analyses.root/('.deleted-'+aid)
                        if destination.is_symlink() or staged.is_symlink():raise OSError('Refusing to remove a symbolic-link report directory.')
                        if staged.exists():
                            if destination.exists():raise OSError('Conflicting staged report deletion; no results were removed.')
                            if record:staged.rename(destination)
                        if destination.exists():destination.rename(staged);moved.append((staged,destination))
                        analyses.remove_catalogue_record(db,aid)
                    db.execute('DELETE FROM workflow_prop_simulations WHERE id=?',(id,))
                    preview=dict(preview,deleted=True,deletable=False,deleted_at_utc=datetime.now(timezone.utc).isoformat(),cleanup_pending=[])
                    db.execute('INSERT INTO workflow_prop_sim_deletions VALUES (?,?,?)',
                        (id,preview['deleted_at_utc'],json.dumps(dict(receipt=preview,simulation_snapshot=snapshot))))
        except BaseException:
            for staged,destination in reversed(moved):
                if staged.exists():staged.rename(destination)
            raise
        pending=[]
        for aid in preview['analysis_ids_to_delete']:
            staged=analyses.root/('.deleted-'+aid)
            if staged.is_symlink():pending.append(aid);continue
            if staged.exists():
                try:shutil.rmtree(staged)
                except OSError:pending.append(aid)
        preview['cleanup_pending']=pending
        with analyses.connect() as db:
            stored=json.loads(db.execute('SELECT payload FROM workflow_prop_sim_deletions WHERE id=?',(id,)).fetchone()[0])
            stored['receipt']=preview;db.execute('UPDATE workflow_prop_sim_deletions SET payload=? WHERE id=?',(json.dumps(stored),id))
        return preview


@router.get('/{id}/deletion')
async def preview_deletion(id:UUID,request:Request):
    def read():
        with request.app.state.prop_analyses.lock,request.app.state.prop_analyses.connect() as db:return deletion_preview(request,id.hex,db)
    return await invoke(read)


@router.delete('/{id}')
async def delete_simulation(id:UUID,body:DeleteSimulation,request:Request):
    import sqlite3
    try:return await invoke(remove_simulation,request,id.hex,body)
    except sqlite3.Error as exc:
        raise HTTPException(409,'Could not finish deletion bookkeeping. Retry this deletion; source data is kept.') from exc
